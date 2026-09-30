"""피부 지표 점수 산출.

사진에서 4개 지표(홍조·밝기·트러블·균일도)를, 센서값에서 수분 지표를 각각
0~100 점수로 만든다. 현재 사진 분석은 더미 구현이며, MediaPipe/OpenCV로
교체할 때는 analyze_image() 안쪽만 바꾸면 된다(호출부는 그대로).
"""

import hashlib
from collections.abc import Mapping

# 사진에서 산출하는 지표 (수분은 센서/직접입력이므로 제외)
PHOTO_METRIC_CODES = ("redness", "brightness", "trouble", "uniformity")

# 아두이노 수분 센서의 ADC 출력 범위.
# 실측 캘리브레이션 전까지의 임시값이므로, 측정 후 이 두 값을 조정한다.
MOISTURE_RAW_MIN = 0
MOISTURE_RAW_MAX = 1023


class AnalysisError(ValueError):
    """입력 이미지나 센서값이 분석 불가능한 경우."""


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def analyze_image(
    image_bytes: bytes | None = None, *, seed_key: str | None = None
) -> Mapping[str, int]:
    """사진에서 지표 점수 4개를 산출한다.

    TODO(CV): 현재는 더미 구현이다. 실제 구현 시 아래 순서로 교체한다.
      1) MediaPipe FaceMesh로 landmark 추출 → 볼·이마 ROI 마스크 생성
      2) 흰자위(또는 이마 기준 영역)를 화이트밸런스 기준점으로 잡아 조명 보정
      3) 지표별 계산 — 홍조: Lab a* 편차 / 밝기: Lab L 평균
         / 트러블: 색상 threshold + blob detection / 균일도: 톤 표준편차의 역수
      4) 각 원시값을 0~100으로 정규화

    같은 사진이면 같은 점수가 나오도록 해시 기반으로 값을 만든다.
    (요청마다 점수가 흔들리면 프론트·추천 쪽에서 재현이 안 되기 때문)
    """
    # 더미 단계에서는 S3에서 파일을 내려받지 않고 seed_key(s3_key)만으로 점수를 만든다.
    # 실제 CV 구현 후에는 image_bytes가 반드시 필요하다.
    if not image_bytes and not seed_key:
        raise AnalysisError("image_bytes 또는 seed_key 중 하나는 있어야 합니다")

    digest = hashlib.sha256(seed_key.encode() if seed_key else image_bytes).digest()
    # 지표마다 다른 바이트를 쓰고, 0~255를 0~100으로 환산한다.
    # (그냥 자르면 100 초과 값이 전부 100으로 몰려 점수가 한쪽으로 쏠린다)
    return {
        code: _clamp(round(digest[i * 4] / 255 * 100))
        for i, code in enumerate(PHOTO_METRIC_CODES)
    }


def moisture_score_from_raw(raw: int) -> int:
    """센서 raw값(ADC)을 0~100 점수로 정규화한다."""
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise AnalysisError(f"수분 raw값은 정수여야 합니다: {raw!r}")
    if not MOISTURE_RAW_MIN <= raw <= MOISTURE_RAW_MAX:
        raise AnalysisError(
            f"수분 raw값은 {MOISTURE_RAW_MIN}~{MOISTURE_RAW_MAX} 범위여야 합니다: {raw}"
        )

    span = MOISTURE_RAW_MAX - MOISTURE_RAW_MIN
    return _clamp(round((raw - MOISTURE_RAW_MIN) / span * 100))


def build_scores(
    image_bytes: bytes | None = None,
    *,
    seed_key: str | None = None,
    moisture_source: str,
    moisture_raw: int | None = None,
    moisture_score: int | None = None,
) -> dict[str, int]:
    """사진 점수 4개와 수분 점수를 합쳐 라벨링 서비스에 넘길 형태로 만든다.

    moisture_source별 입력:
      sensor — moisture_raw (ADC 원시값)
      manual — moisture_score (0~100, 디버깅·센서 장애 시 대체 입력)
      none   — 없음 (사진 기반 4개 지표만 사용)
    """
    scores = dict(analyze_image(image_bytes, seed_key=seed_key))

    if moisture_source == "sensor":
        if moisture_raw is None:
            raise AnalysisError("sensor일 때는 moisture_raw가 필요합니다")
        scores["moisture"] = moisture_score_from_raw(moisture_raw)
    elif moisture_source == "manual":
        if moisture_score is None:
            raise AnalysisError("manual일 때는 moisture_score가 필요합니다")
        if not 0 <= moisture_score <= 100:
            raise AnalysisError(f"수분 점수는 0~100 범위여야 합니다: {moisture_score}")
        scores["moisture"] = moisture_score
    elif moisture_source == "none":
        if moisture_raw is not None or moisture_score is not None:
            raise AnalysisError("none일 때는 수분값을 보내지 않습니다")
    else:
        raise AnalysisError(f"알 수 없는 moisture_source입니다: {moisture_source}")

    return scores
