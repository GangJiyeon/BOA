"""피부톤(밝기 단계·언더톤) 측정과 분류.

기존 피부 분석(skin_analysis.py)의 얼굴 찾기·부위 패치·머리카락 제거를
읽기 전용으로 재사용하고, 그 위에 피부톤 지표만 새로 계산한다.
기존 지표(홍조·밝기·트러블·균일도) 코드는 수정하지 않는다.

지표 (피부과 문헌에서 쓰는 분류각)
  ITA° = arctan((L* - 50) / b*)   밝기 단계. 클수록 밝은 피부.
  h°   = atan2(b*, a*)            색상각(언더톤). 클수록 노란 기(웜), 작을수록 붉은 기(쿨).

밝기 단계·쿠션 호수 계산 (보정 ITA 방식)
  1) 보정 ITA° = arctan((L* + l_offset - 50) / (b* × b_scale))
     - l_offset: 카메라가 피부를 어둡게/밝게 기록하는 정도 보정
     - b_scale : 카메라가 노란 기를 바래게 기록하는 정도 보정 (웹캠은 채도가 낮아 b*가 작게 찍힘)
  2) 보정 ITA° → ITA-호수 대응표(ITA_SHADE) → 추정 쿠션 호수
  3) 추정 호수 → 밝기 3단계 (20호 미만 밝음 / 24호 미만 중간 / 그 이상 어두움)
  밝기 단계와 쿠션 호수가 같은 값에서 나오므로 서로 어긋나지 않는다.
  카메라별 l_offset·b_scale은 app/data/tone_calibration.json 으로 덮어쓸 수 있고,
  이 파일은 scripts/calibrate_tone.py (정답 호수 CSV + 사진)로 만든다.

색 보정 방식 — scripts/validation/skin_tone_probe.py 실측으로 결정
  - 그레이월드(사진별 보정): 얼굴이 화면을 채우는 셀피에서는 같은 사람도 사진마다
    크게 흔들리고 b*가 무너져 측정 불가가 속출했다 → 쓰지 않는다.
  - 흰자위 기준 보정: 안경 반사에 취약하고 같은 사람 반복에서 ±5° 흔들렸다
    → 1차 버전에서는 쓰지 않는다 (검증 스크립트에 연구용으로만 남김).
  - 카메라 프로필 고정 보정만 적용: 같은 장소 반복 촬영에서 h° ±0.8°, ITA° ±1.3°로
    가장 안정적이었다. 키오스크(고정 기기·고정 장소) 전제에 맞는 선택이다.

주의: 이 모듈의 Lab은 표준 CIELAB(L* 0~100, a*·b* 부호 있음)이다.
      skin_analysis의 OpenCV 8비트 Lab(0~255 압축)과 단위가 다르다.
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, fields, replace
from pathlib import Path

import cv2
import numpy as np

from app.services import skin_analysis as sa
from app.services.errors import ErrorCode

# 피부톤을 잴 부위: 이마·양볼 (균일도·홍조와 같은 부위).
# 처음에는 볼을 홍조 때문에 빼고 이마·코·턱을 썼지만, 실측 결과가 반대였다.
#  - 코가 볼보다 더 붉었다 (갤럭시북 4명 a*: 코 13.8~17.1, 볼 12.6~14.6)
#  - 턱은 그늘·수염 자국 때문에 ITA°가 -5~-3°까지 떨어져 밝기 단계를 끌어내렸다
#    (턱 하나 때문에 같은 밝기의 사람이 '어두운 편'으로 판정됨)
#  - 이마는 4명 중 3명이 앞머리로 가려져, 실제로는 코·턱만으로 판정되고 있었다
# 한계: 볼 홍조가 심한 사람은 쿨 쪽으로 약간 치우칠 수 있다.
# 부위 정의는 밝기 점수와 공유하도록 skin_analysis에 둔다 (같은 값)
TONE_REGIONS = sa.TONE_REGIONS
# 위 부위가 모두 가려진 경우에만 코·턱으로 대체한다
TONE_FALLBACK = sa.TONE_FALLBACK

# b*(노란 기)가 이보다 작으면 측정 불가로 돌려보낸다.
# ITA°는 b*로 나누는 식이라 b*가 0에 가까우면 ±90°로 튄다 (색이 바랜 웹캠 사진에서 발생).
MIN_B_FOR_TONE = sa.MIN_B_FOR_ITA

# 조명이 한쪽으로 치우친 사진은 색상각이 왜곡된다. 메이크업 화면은 분석을 거치지 않고
# 들어올 수 있으므로 거절하는 대신 신뢰도를 낮춰 안내한다. (기준값은 기존 분석과 동일)
TONE_MIN_CHEEK_L_RATIO = 0.85


# ── 분류 경계 (잠정값) ───────────────────────────────────────────────
# 밝기 단계는 피부과 ITA° 분류(>41° 밝음, 28~41° 중간)를 따른다.
# 언더톤 경계(색상각)는 정답 데이터가 없어 잠정값이다.
# 기기마다 색 기록이 달라 경계도 카메라 프로필별로 둔다.
# 정답(쓰는 파운데이션 호수·톤)을 확보하면 calibrate_profile.py 결과와 비교해 보정한다.
@dataclass(frozen=True)
class ToneThresholds:
    """카메라 프로필별 분류 경계."""

    bright_min_ita: float  # ITA°가 이 값 초과면 밝은 편
    medium_min_ita: float  # 이 값 초과면 중간, 이하면 어두운 편
    warm_min_hue: float    # h°가 이 값 이상이면 웜
    cool_max_hue: float    # h°가 이 값 이하면 쿨 (사이는 뉴트럴)
    # ── 보정 ITA용 카메라 보정값 (tone_calibration.json으로 덮어쓸 수 있음) ──
    l_offset: float = 0.0  # 사진 L*에 더하는 값. 카메라가 피부를 어둡게 기록할수록 크다.
    b_scale: float = 1.0   # 사진 b*에 곱하는 값. 카메라가 노란 기를 바래게 기록할수록 크다.
    # 호수 계산 방식: "ita" = 보정 ITA°(L*·b*), "l" = L*만 (이전 방식, 노란 기 흔들림에 둔감)
    shade_method: str = "ita"


TONE_THRESHOLDS: dict[str, ToneThresholds] = {
    # 휴대폰: ITA 피부과 분류(>41° 밝음, 28~41° 중간)를 참고 단계(ita_level)로 쓴다
    # l_offset +1.55: 같은 사람을 휴대폰·갤럭시북으로 찍었을 때 휴대폰이 L* 약 7.6 밝았음 (9.15 − 7.6)
    # b_scale 1.0: 휴대폰 피부 b*(13~16)가 대응표 기준 노란 기(ITA_REF_B=15)와 비슷함
    "phone": ToneThresholds(bright_min_ita=41.0, medium_min_ita=28.0, warm_min_hue=50.0, cool_max_hue=40.0,
                            l_offset=1.55, b_scale=1.0),
    # 웹캠: 색이 바래 h°·ITA°가 전반적으로 낮게 나온다. 표본 확보 전 잠정값.
    "webcam": ToneThresholds(bright_min_ita=38.0, medium_min_ita=25.0, warm_min_hue=46.0, cool_max_hue=37.0),
    # 갤럭시북: 4명 모두 색상각 34~39°로 쿨 판정이 나오므로, 정답과 비교해 언더톤 경계 확인이 필요하다.
    # l_offset +9.15: 샘플3(실제 23호)의 L* 57.85를 호수표 23호 밝기(67)에 맞춤
    # b_scale 1.564: 샘플3의 b* 9.59가 23호 기준 ITA(48.6°)가 되도록 맞춤 (웹캠 채도 저하 보정)
    # 정답 1명 기준 잠정값 (2026-11-18). 정답이 늘면 scripts/calibrate_tone.py로 다시 맞춘다.
    "galaxybook": ToneThresholds(bright_min_ita=41.0, medium_min_ita=28.0, warm_min_hue=50.0, cool_max_hue=40.0,
                                 l_offset=9.15, b_scale=1.564),
}
DEFAULT_THRESHOLDS = TONE_THRESHOLDS["phone"]

# ── 보정 파일 (현장 보정 결과) ────────────────────────────────────────
# scripts/calibrate_tone.py 가 만든다. 파일이 없으면 위 기본값을 그대로 쓴다.
# 형식: {"profiles": {"galaxybook": {"l_offset": 9.15, "b_scale": 1.564, ...}}}
# 파일이 바뀌면 다음 요청부터 자동 반영된다 (서버 재시작 불필요).
CALIBRATION_PATH = Path(
    os.environ.get("TONE_CALIBRATION_PATH")
    or Path(__file__).resolve().parents[1] / "data" / "tone_calibration.json"
)
# 보정 파일에서 덮어쓸 수 있는 항목 (나머지 키는 기록용으로 무시)
SHADE_METHODS = ("ita", "l")
CALIBRATABLE_FIELDS = tuple(f.name for f in fields(ToneThresholds) if f.name != "shade_method")
_logger = logging.getLogger(__name__)
_calibration_cache: dict = {"mtime": None, "data": {}}


def load_calibration() -> dict:
    """보정 파일을 읽는다. 파일이 바뀌었을 때만 다시 읽고, 없거나 깨졌으면 빈 값."""
    try:
        mtime = CALIBRATION_PATH.stat().st_mtime
    except OSError:
        _calibration_cache.update(mtime=None, data={})
        return {}
    if mtime != _calibration_cache["mtime"]:
        try:
            data = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("최상위가 객체가 아님")
        except (OSError, ValueError) as e:  # 깨진 파일 때문에 분석이 멈추지 않게 기본값으로 진행
            _logger.warning("피부톤 보정 파일을 읽지 못해 기본값을 씁니다: %s (%s)", CALIBRATION_PATH, e)
            data = {}
        _calibration_cache.update(mtime=mtime, data=data)
    return _calibration_cache["data"]

# ── 쿠션 호수 추정 ──────────────────────────────────────────────────
# 호수별 밝기(L*): 프론트 makeup-looks.ts의 SHADE_L과 같은 값 (가상 메이크업 쿠션 색에도 쓰임)
SHADE_L: tuple[tuple[int, float], ...] = ((13, 79.0), (17, 76.0), (19, 74.0), (21, 71.0), (23, 67.0), (25, 63.0))
SHADE_MIN, SHADE_MAX = 11.0, 29.0
# 실제 판매 호수 (안내는 이 중 가장 가까운 호수로) 와, 믿을 수 있는 추정 범위
SHADE_STEPS = (13, 15, 17, 19, 21, 23, 25)
# 호수표(13~25호)에서 한 칸 넘게 벗어나면 피부가 아니라 사진 처리(보정 필터·과노출·어두운 사진) 영향으로 본다
# (예: 같은 사람 사진이 처리만 달라 L* 80/65 → 11호/23호로 갈림)
CUSHION_VALID_RANGE = (12.0, 26.0)
# 밝기 단계를 추정 호수로 나눈다 (호수 자체는 보정 ITA에서 나온다)
BRIGHT_MAX_SHADE = 20.0  # 이 호수 미만: 밝은 편
MEDIUM_MAX_SHADE = 24.0  # 이 호수 미만: 중간, 이상: 어두운 편

# ITA-호수 대응표: 호수표 L*를 기준 노란 기(b*=15, 휴대폰 실측 피부 수준)일 때의 ITA°로 바꾼 값
# 13호 62.6° · 17호 60.0° · 19호 58.0° · 21호 54.5° · 23호 48.6° · 25호 40.9°
ITA_REF_B = 15.0
ITA_SHADE: tuple[tuple[int, float], ...] = tuple(
    (s, round(math.degrees(math.atan((lv - 50.0) / ITA_REF_B)), 2)) for s, lv in SHADE_L
)


def _extrapolate(x: float, xs: list[float], ys: list[float]) -> float:
    """xs 오름차순 표에서 선형 보간. 표 밖은 양 끝 기울기로 연장."""
    if x <= xs[0]:
        return ys[0] + (x - xs[0]) * (ys[1] - ys[0]) / (xs[1] - xs[0])
    if x >= xs[-1]:
        return ys[-1] + (x - xs[-1]) * (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
    return float(np.interp(x, xs, ys))


def corrected_ita(L: float, b: float, th: "ToneThresholds") -> float | None:
    """카메라 보정을 적용한 ITA°. 노란 기가 너무 작아 계산이 불안정하면 None."""
    bb = b * th.b_scale
    if b < MIN_B_FOR_TONE or bb <= 0:
        return None
    return math.degrees(math.atan((L + th.l_offset - 50.0) / bb))


def shade_from_ita(ita: float) -> float:
    """보정 ITA° → 추정 쿠션 호수 (ITA가 클수록 밝은 = 낮은 호수)."""
    pairs = sorted(ITA_SHADE, key=lambda p: p[1])  # ITA 오름차순 (25호 → 13호)
    shade = _extrapolate(ita, [i for _, i in pairs], [float(s) for s, _ in pairs])
    return float(min(SHADE_MAX, max(SHADE_MIN, shade)))


def shade_from_l(L: float, th: "ToneThresholds") -> float:
    """사진 L*만으로 호수 추정 (노란 기가 너무 작아 ITA를 못 쓸 때의 대체 계산)."""
    pairs = sorted(SHADE_L, key=lambda p: p[1])  # L 오름차순 (25호 → 13호)
    shade = _extrapolate(L + th.l_offset, [lv for _, lv in pairs], [float(s) for s, _ in pairs])
    return float(min(SHADE_MAX, max(SHADE_MIN, shade)))


def estimate_shade(L: float, b: float, th: "ToneThresholds") -> float:
    """사진 피부 L*·b*(표준 CIELAB) → 추정 쿠션 호수 (연속값). 기본은 보정 ITA, 불가하면 L* 대체."""
    if th.shade_method == "l":
        return shade_from_l(L, th)
    ita = corrected_ita(L, b, th)
    return shade_from_ita(ita) if ita is not None else shade_from_l(L, th)


def level_from_shade(shade: float) -> str:
    """추정 호수 → 밝기 단계."""
    if shade < BRIGHT_MAX_SHADE:
        return "bright"
    if shade < MEDIUM_MAX_SHADE:
        return "medium"
    return "deep"


BRIGHTNESS_LEVELS = ("bright", "medium", "deep")
UNDERTONES = ("warm", "neutral", "cool")

BRIGHTNESS_LABELS = {"bright": "밝은 편", "medium": "중간", "deep": "어두운 편"}
UNDERTONE_LABELS = {"warm": "웜", "neutral": "뉴트럴", "cool": "쿨"}


@dataclass(frozen=True)
class SkinToneResult:
    """피부톤 측정·분류 결과."""

    brightness_level: str  # bright | medium | deep
    undertone: str         # warm | neutral | cool
    confidence: str        # high | low
    raw: dict              # L*, a*, b*, ITA°, h°, 사용 부위, 양볼 밝기 비율 등


def classify_brightness(ita: float, th: ToneThresholds) -> str:
    """ITA°를 밝기 3단계로 분류한다."""
    if ita > th.bright_min_ita:
        return "bright"
    if ita > th.medium_min_ita:
        return "medium"
    return "deep"


def classify_undertone(hue: float, th: ToneThresholds) -> str:
    """색상각 h°를 언더톤 3종으로 분류한다."""
    if hue >= th.warm_min_hue:
        return "warm"
    if hue <= th.cool_max_hue:
        return "cool"
    return "neutral"


def thresholds_for(camera_profile: str) -> ToneThresholds:
    """프로필 이름으로 분류 경계를 찾는다. 모르는 프로필이면 휴대폰 기준.

    보정 파일(tone_calibration.json)에 같은 프로필 값이 있으면 그 값으로 덮어쓴다.
    """
    name = (camera_profile or "").strip().lower()
    base = TONE_THRESHOLDS.get(name, DEFAULT_THRESHOLDS)
    override = load_calibration().get("profiles", {}).get(name)
    if not isinstance(override, dict):
        return base
    values = {}
    for key in CALIBRATABLE_FIELDS:
        if key in override:
            try:
                values[key] = float(override[key])
            except (TypeError, ValueError):
                _logger.warning("보정 파일 값이 숫자가 아니라 무시합니다: %s.%s=%r", name, key, override[key])
    method = override.get("shade_method")
    if method is not None:
        if method in SHADE_METHODS:
            values["shade_method"] = method
        else:
            _logger.warning("보정 파일 shade_method 값을 무시합니다 (ita 또는 l): %s=%r", name, method)
    return replace(base, **values) if values else base


def _to_cielab(bgr: np.ndarray) -> np.ndarray:
    """표준 CIELAB 변환 (L* 0~100, a*·b* 부호 있음)."""
    return cv2.cvtColor(bgr.astype(np.float32) / 255.0, cv2.COLOR_BGR2LAB)


def measure_tone(
    image_bytes: bytes,
    *,
    min_face_width: int = sa.DEFAULT_MIN_FACE_WIDTH,
    camera_profile: str = sa.DEFAULT_CAMERA_PROFILE,
) -> SkinToneResult:
    """사진 1장에서 피부톤(밝기 단계·언더톤)을 측정한다.

    얼굴 찾기 실패·측정 불가 시 skin_analysis.AnalysisError를 그대로 던진다.
    """
    profile = sa.get_camera_profile(camera_profile)
    face = sa._prepare_face(
        image_bytes, min_face_width=min_face_width, channel_gains=profile.channel_gains
    )
    # 부위 패치 + 머리카락 제거는 기존 로직 그대로
    regions, coverage = sa._build_skin_regions(face.image, face.lab, face.landmarks)

    mask, names = sa.tone_mask(regions, face.image.shape[:2])
    if not names:
        raise sa.AnalysisError(
            "피부톤을 잴 부위(이마·볼·코·턱)를 찾지 못했습니다",
            code=ErrorCode.SKIN_AREA_TOO_SMALL,
        )
    # 트러블 덩어리(붉은 병변)는 뺀다: a*를 올려 색상각을 쿨 쪽으로 밀기 때문 (피부 분석 밝기 점수와 같은 처리)
    trouble = sa.detect_face_trouble(face)
    full_px = int(np.count_nonzero(mask))
    mask = sa.exclude_trouble(mask, trouble.mask, face.face_width)

    # face.balanced = 카메라 프로필 고정 보정이 이미 적용된 이미지
    # 중앙값은 JPEG 색 양자화로 계단처럼 튀어 평균을 쓴다 (probe 스크립트와 동일)
    L, a, b = sa.cielab_mean(face.balanced, mask)

    if b < MIN_B_FOR_TONE:
        raise sa.AnalysisError(
            f"피부톤을 측정할 수 없습니다 (노란 기 b* {b:.1f}, 최소 {MIN_B_FOR_TONE}). "
            "카메라가 색을 회색빛으로 기록했거나 조명이 어둡습니다. 밝은 곳에서 다시 촬영해주세요.",
            code=ErrorCode.SKIN_COLOR_UNMEASURABLE,
            detail={"b": round(b, 2), "required_min": MIN_B_FOR_TONE, "camera_profile": camera_profile},
        )

    ita, hue = sa.ita_hue(L, a, b)

    # 조명 치우침 → 거절 대신 신뢰도 하향 (기존 _cheek_l_ratio 재사용, 비율이라 Lab 단위 무관)
    cheek_ratio = sa._cheek_l_ratio(face.lab, regions)
    balanced_light = cheek_ratio is not None and cheek_ratio >= TONE_MIN_CHEEK_L_RATIO
    confidence = "high" if balanced_light else "low"

    th = thresholds_for(camera_profile)
    ita_c = corrected_ita(L, b, th)  # b* 최소값은 위에서 확인했으므로 항상 계산됨
    shade = estimate_shade(L, b, th)
    shade_out_of_range = not (CUSHION_VALID_RANGE[0] <= shade <= CUSHION_VALID_RANGE[1])
    if shade_out_of_range:
        confidence = "low"
    return SkinToneResult(
        brightness_level=level_from_shade(shade),
        undertone=classify_undertone(hue, th),
        confidence=confidence,
        raw={
            "L": round(L, 2),
            "a": round(a, 2),
            "b": round(b, 2),
            "ita_deg": round(ita, 1),
            "hue_deg": round(hue, 1),
            "ita_corrected": None if ita_c is None else round(ita_c, 1),  # 카메라 보정 ITA° (호수·밝기 단계 근거)
            "l_offset": th.l_offset,
            "b_scale": th.b_scale,
            "shade_method": th.shade_method,
            "cushion_shade": round(shade, 1),  # 추정 쿠션 호수 (밝기 단계 근거)
            "cushion_out_of_range": shade_out_of_range,  # 추정이 호수표 범위를 벗어남 (사진 처리 의심)
            "ita_level": classify_brightness(ita, th),  # 참고: 보정 전 ITA°의 피부과 분류 단계
            "regions_used": names,
            "excluded_px": full_px - int(np.count_nonzero(mask)),  # 제외한 트러블 픽셀 (덩어리 + 여백)
            "cheek_l_ratio": None if cheek_ratio is None else round(cheek_ratio, 3),
            "face_width_px": round(face.face_width, 1),
            "camera_profile": camera_profile,
        },
    )
