"""피부톤(밝기 단계·언더톤) 분석 시험 스크립트.

앱에 넣기 전에 "얼마나 안정적으로 잴 수 있는가"를 확인하는 용도다.
기존 피부 분석의 얼굴 찾기·부위 패치·머리카락 제거를 그대로 쓰고,
그 위에서 피부톤 지표만 새로 계산한다. (앱 코드는 수정하지 않는다)

계산하는 지표
  ITA° = arctan((L* - 50) / b*)   밝기 단계 (호수 추정용). 클수록 밝다.
  h°   = atan2(b*, a*)            색상각 (언더톤). 클수록 노란 기(웜), 작을수록 붉은 기(쿨)
  부위: 이마·코·턱 (볼은 홍조 영향이 커서 뺀다)

비교하는 색 보정 방식
  none   보정 없음
  gray   그레이월드 (사진 전체 평균을 회색으로)
  sclera 흰자위 기준 (눈 흰자를 흰색 기준으로 삼아 조명 색을 지움)

시험 방법
  1) 실제 사진에서 위 지표를 계산한다.
  2) 같은 사진에 가상 조명색(따뜻한/차가운 조명)을 입혀 다시 계산하고,
     보정 방식별로 원래 값에서 얼마나 벗어나는지 본다.

사용법 (backend 폴더에서)
    .venv\\Scripts\\python scripts/validation/skin_tone_probe.py 사진폴더
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import cv2
import numpy as np

import _common as c

sa = c.sa

# 피부톤을 잴 부위 (볼은 홍조 때문에 쿨톤 쪽으로 치우쳐 뺀다)
TONE_REGIONS = ("forehead", "nose", "chin")
TONE_FALLBACK = ("left_cheek", "right_cheek")

# ITA° 구간 (피부과 분류 기준)
ITA_CLASSES = [(55, "매우 밝음"), (41, "밝음"), (28, "중간"), (10, "탠"), (-90, "어두움")]

# 가상 조명색: 채널별 이득 (B, G, R). 대략 3500K~7000K 조명 변화를 흉내 낸다
ILLUMINANTS = {
    "따뜻함 약": (0.85, 0.95, 1.00),
    "따뜻함 강": (0.70, 0.88, 1.00),
    "차가움 약": (1.00, 0.97, 0.90),
    "차가움 강": (1.00, 0.93, 0.80),
}

# 흰자위 추출용 MediaPipe 눈 윤곽·홍채 번호
LEFT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
RIGHT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
IRISES = [(468, 469), (473, 474)]  # (홍채 중심, 홍채 가장자리)
MIN_SCLERA_PX = 20

# b*(노란 기)가 이보다 작으면 ITA°를 계산하지 않는다.
# ITA°는 b*로 나누는 식이라 b*가 0에 가까우면 값이 ±90°로 튄다 (색이 바랜 웹캠 사진에서 발생)
MIN_B_FOR_ITA = 3.0


# ── 기본 계산 ────────────────────────────────────────────────────────


def to_lab(bgr: np.ndarray) -> np.ndarray:
    """표준 CIELAB (L* 0~100, a*·b* 부호 있음). OpenCV의 0~255 압축 Lab이 아니다."""
    return cv2.cvtColor(bgr.astype(np.float32) / 255.0, cv2.COLOR_BGR2LAB)


def tone_of(lab: np.ndarray, mask: np.ndarray) -> dict:
    """피부 마스크의 L*·a*·b* 평균과 ITA°·색상각을 계산한다."""
    L, a, b = (float(np.mean(lab[..., i][mask > 0])) for i in range(3))  # 중앙값은 JPEG 색 양자화로 계단처럼 튀어 평균을 쓴다
    # b*가 너무 작으면 ITA°가 의미 없으므로 nan으로 둔다
    ita = math.degrees(math.atan((L - 50.0) / b)) if b >= MIN_B_FOR_ITA else float("nan")
    hue = math.degrees(math.atan2(b, a))
    return {"L": L, "a": a, "b": b, "ita": ita, "hue": hue}


def ita_class(ita: float) -> str:
    if ita != ita:  # nan
        return "측정 불가"
    for lower, name in ITA_CLASSES:
        if ita > lower:
            return name
    return ITA_CLASSES[-1][1]


def apply_gains(bgr: np.ndarray, gains) -> np.ndarray:
    return np.clip(bgr.astype(np.float32) * np.array(gains, np.float32), 0, 255).astype(np.uint8)


# ── 색 보정 방식 ─────────────────────────────────────────────────────


def gains_gray_world(bgr: np.ndarray) -> np.ndarray:
    """사진 평균색을 회색으로 맞추는 이득."""
    means = bgr.reshape(-1, 3).astype(np.float32).mean(axis=0)
    return means.mean() / np.maximum(means, 1.0)


def sclera_mask(bgr: np.ndarray) -> np.ndarray | None:
    """눈 윤곽 안에서 홍채를 뺀 밝은 부분(흰자위) 마스크. 못 찾으면 None."""
    from mediapipe.python.solutions import face_mesh as mp_face_mesh

    h, w = bgr.shape[:2]
    with mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, refine_landmarks=True) as mesh:
        result = mesh.process(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    if not result.multi_face_landmarks:
        return None
    pts = np.array([(p.x * w, p.y * h) for p in result.multi_face_landmarks[0].landmark], np.float32)

    # 1) 눈 윤곽 다각형
    eyes = np.zeros((h, w), np.uint8)
    for contour in (LEFT_EYE, RIGHT_EYE):
        cv2.fillPoly(eyes, [pts[contour].round().astype(np.int32)], 255)
    # 2) 홍채 원을 조금 크게 빼서 홍채 테두리가 섞이지 않게 한다
    for center, edge in IRISES:
        radius = float(np.linalg.norm(pts[center] - pts[edge])) * 1.2
        cv2.circle(eyes, tuple(pts[center].round().astype(int)), int(math.ceil(radius)), 0, -1)
    # 3) 눈꺼풀 경계 한 겹 제거
    eyes = cv2.erode(eyes, np.ones((3, 3), np.uint8))
    if np.count_nonzero(eyes) < MIN_SCLERA_PX:
        return None

    # 4) 그 안에서 밝은 쪽 절반만 흰자로 본다 (속눈썹·그늘 제외)
    lightness = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[..., 0]
    cut = np.percentile(lightness[eyes > 0], 50)
    mask = ((eyes > 0) & (lightness >= cut)).astype(np.uint8) * 255
    return mask if np.count_nonzero(mask) >= MIN_SCLERA_PX else None


def gains_sclera(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """흰자위 중앙값 색을 회색(무채색)으로 맞추는 이득."""
    ref = np.median(bgr[mask > 0].astype(np.float32), axis=0)
    return ref.mean() / np.maximum(ref, 1.0)


# ── 사진 한 장 측정 ──────────────────────────────────────────────────


def measure(face_bgr: np.ndarray, skin_mask: np.ndarray, eye_mask: np.ndarray | None) -> dict:
    """보정 방식별 피부톤 지표."""
    out = {"none": tone_of(to_lab(face_bgr), skin_mask)}
    out["gray"] = tone_of(to_lab(apply_gains(face_bgr, gains_gray_world(face_bgr))), skin_mask)
    if eye_mask is not None:
        out["sclera"] = tone_of(to_lab(apply_gains(face_bgr, gains_sclera(face_bgr, eye_mask))), skin_mask)
    return out


def prepare(path: Path, profile: str, min_face_width: int):
    """얼굴 잘라내기·피부 패치는 기존 분석 코드를 그대로 쓴다."""
    data = path.read_bytes()
    prof = sa.get_camera_profile(profile)
    face = sa._prepare_face(data, min_face_width=min_face_width, channel_gains=prof.channel_gains)
    regions, _ = sa._build_skin_regions(face.image, face.lab, face.landmarks)
    names = [n for n in TONE_REGIONS if n in regions] or [n for n in TONE_FALLBACK if n in regions]
    mask = np.zeros(face.image.shape[:2], np.uint8)
    for n in names:
        mask |= regions[n]
    return face.image, mask, names


def main() -> None:
    parser = argparse.ArgumentParser(description="피부톤 분석 시험")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--profile", default=c.default_profile())
    parser.add_argument("--min-face-width", type=int, default=150, help="작은 시험 사진도 받도록 기본 150")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "output" / "skin_tone_probe.csv")
    args = parser.parse_args()

    photos = c.list_images(args.folder)
    if not photos:
        sys.exit(f"사진이 없습니다: {args.folder}")

    rows, drift = [], {}
    print("=" * 78)
    print("1. 실제 사진의 피부톤 (보정 방식별 ITA° / 색상각 h°)")
    print("=" * 78)
    print(f"  {'사진':<16}{'보정 없음':>18}{'그레이월드':>18}{'흰자위':>18}")
    for path in photos:
        try:
            image, mask, names = prepare(path, args.profile, args.min_face_width)
        except sa.AnalysisError as e:
            print(f"  {path.name:<16} 거절 ({e.code})")
            continue
        eye = sclera_mask(image)
        base = measure(image, mask, eye)

        cells = "".join(
            f"{(format(base[k]['ita'], '5.1f') + '° / ' + format(base[k]['hue'], '4.1f') + '°') if k in base else '흰자 못 찾음':>18}"
            for k in ("none", "gray", "sclera")
        )
        print(f"  {path.stem[:14]:<16}{cells}")

        row = {"file": path.name, "regions": "+".join(names), "sclera_px": int(np.count_nonzero(eye)) if eye is not None else 0}
        for k, v in base.items():
            row.update({f"{k}_{m}": round(x, 2) for m, x in v.items()})
        rows.append(row)

        # 가상 조명: 같은 사진에 조명색을 입혀 보정 방식별로 원래 값과의 차이를 잰다
        for light, gains in ILLUMINANTS.items():
            shifted = apply_gains(image, gains)
            eye_s = sclera_mask(shifted)
            res = measure(shifted, mask, eye_s)
            for k in ("none", "gray", "sclera"):
                if k in res and k in base:
                    d = drift.setdefault((light, k), {"ita": [], "hue": [], "flip": []})
                    d["ita"].append(res[k]["ita"] - base[k]["ita"])
                    d["hue"].append(res[k]["hue"] - base[k]["hue"])
                    d["flip"].append(ita_class(res[k]["ita"]) != ita_class(base[k]["ita"]))

    print("\n" + "=" * 78)
    print("2. 가상 조명 변화 — 원래 값에서 벗어난 정도 (평균 절댓값, 사진 전체)")
    print("=" * 78)
    print(f"  {'조명':<10}{'보정':<10}{'ΔITA°':>10}{'Δ색상각°':>12}{'ITA 단계 바뀜':>16}")
    for light in ILLUMINANTS:
        for k, label in (("none", "없음"), ("gray", "그레이"), ("sclera", "흰자위")):
            d = drift.get((light, k))
            if not d:
                continue
            ita = c.mean([abs(x) for x in d["ita"]])
            hue = c.mean([abs(x) for x in d["hue"]])
            flip = sum(d["flip"]) / len(d["flip"]) * 100
            print(f"  {light:<10}{label:<10}{ita:10.2f}{hue:12.2f}{flip:15.0f}%")

    if rows:
        c.save_csv(rows, args.out)


if __name__ == "__main__":
    main()
