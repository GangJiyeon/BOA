"""피부 지표 점수 산출.

사진에서 4개 지표(홍조·밝기·트러블·균일도)를, 센서값에서 수분 지표를
각각 0~100 점수로 만든다.

사진 분석 흐름
  1) 디코딩 → 긴 변 기준 축소 (연산량 고정)
  2) MediaPipe FaceMesh로 랜드마크 추출
  3) 이마·양볼·코·턱 다섯 부위를 원형 패치로 떼어냄
  4) 각 패치에서 그늘·머리카락·안경 같은 비피부 픽셀 제거
  5) 그레이월드 화이트밸런스로 조명 색상 보정 후 Lab 색공간 변환
  6) 지표별 원시값 계산 → 0~100 정규화

주의: 아래 임계값 상수는 샘플 사진으로 맞춰야 하는 잠정값이다.
"""

import hashlib
from collections.abc import Mapping

import cv2
import numpy as np

from app.services.errors import ErrorCode

# 사진에서 산출하는 지표 (수분은 센서/직접입력이므로 제외)
PHOTO_METRIC_CODES = ("redness", "brightness", "trouble", "uniformity")

# 아두이노 수분 센서의 ADC 출력 범위.
# 실측 캘리브레이션 전까지의 임시값이므로, 측정 후 이 두 값을 조정한다.
MOISTURE_RAW_MIN = 0
MOISTURE_RAW_MAX = 1023

# 분석 해상도. 크면 느려지고 작으면 트러블 탐지가 둔해진다.
MAX_IMAGE_SIDE = 1024

# 허용할 최소 얼굴 너비(px)의 기본값. 실제 값은 설정(MIN_FACE_WIDTH_PX)에서 주입한다.
# 얼굴이 작게 찍히면 작은 반점이 뭉개져 트러블 점수가 낮게 나온다.
DEFAULT_MIN_FACE_WIDTH = 250

# ── 지표별 정규화 구간 (원시값 lo → 0점, hi → 100점) ──────────────────
# 절대적인 임상 기준이 없으므로, 같은 조명에서 촬영한 표본 5장의 분포에서
# 33/67 분위수가 판정 구간 경계(33점/67점)에 오도록 역산한 값이다.
# 즉 "이 점수는 표본 분포상의 상대 위치"라는 의미이며, 표본이 늘어나면
# 분위수를 다시 계산해 갱신해야 한다.
BRIGHTNESS_RANGE = (100.0, 210.0)    # 피부 영역 L 채널 평균 (0~255)
REDNESS_RANGE = (6.0, 14.0)          # 볼·이마의 홍조 지수 (R/G 로그비)
TROUBLE_RANGE = (0.0, 0.028)         # 반점으로 탐지된 픽셀 비율
UNIFORMITY_STD_RANGE = (14.0, 27.0)  # 피부 영역 L 채널 표준편차 (낮을수록 균일)

# 트러블 판정 임계값은 사진마다 다르게 잡는다.
# 그 사진 피부의 평소 질감 변동폭(로버스트 표준편차)의 몇 배를 넘어야
# 트러블로 볼 것인가. 고정 임계값을 쓰면 밝게 찍힌 사진일수록 미세한
# 요철까지 또렷해져 점수가 부풀려진다.
# 홍조 지수를 uint8로 옮길 때 쓰는 배율.
# 지수 1단위를 16단계로 쪼개므로 변동폭(MAD) 계산의 양자화 오차가 작다.
# 담는 기준점은 그 사진 피부의 중앙값으로 잡아, 전체적으로 붉은 피부에서도
# 표현 범위(중앙값 ±8 지수)가 밀리지 않게 한다.
TROUBLE_INDEX_GAIN = 16.0

TROUBLE_SIGMA_FACTOR = 3.0
# 질감이 지나치게 평탄한 사진에서 임계값이 0에 수렴하지 않도록 둔 하한 (지수 단위)
TROUBLE_MIN_THRESHOLD = 0.8

# 트러블로 인정할 최소 덩어리 지름 (얼굴 너비 대비 비율).
# 실제 병변은 덩어리로 뭉쳐 있고 센서 노이즈는 흩어진 점이다.
# 이 필터가 없으면 밝게 찍힌 사진일수록 노이즈가 더 많이 잡혀 점수가 부풀려진다.
TROUBLE_MIN_BLOB_RATIO = 0.01

# 노출이 극단적인 사진은 어떤 보정으로도 정보를 복원할 수 없어 거부한다.
# 피부 영역 L 채널 평균 기준.
EXPOSURE_L_RANGE = (80.0, 235.0)

# 밝기 평균은 정상이어도 일부 영역만 날아가는(채널 포화) 사진이 있다.
# 포화된 곳은 색 정보가 사라져 트러블·홍조가 실제보다 낮게 나오므로,
# 피부 픽셀 중 이 비율을 넘게 포화되면 거부한다.
SATURATED_CHANNEL_LEVEL = 250
MAX_SATURATED_SKIN_RATIO = 0.05

# 피부 마스크 정제 강도. 중앙값에서 이 배수(MAD 기준)를 벗어난 픽셀은 버린다.
# 머리카락·그림자·안경처럼 피부가 아닌 것이 마스크에 섞이면 통계가 망가진다.
SKIN_MAD_FACTOR = 2.5

# 분석 부위 정의.
# 얼굴 윤곽 전체를 쓰면 머리카락선·턱 그늘이 섞이므로, 피부가 확실한
# 다섯 곳만 원형 패치로 떼어내 분석한다.
# (이름, 중심 랜드마크 번호들, 얼굴 너비 대비 반지름 비율)
REGIONS = (
    ("forehead", (10, 151), 0.07),   # 이마 — 두 점의 중간
    ("left_cheek", (50,), 0.08),     # 왼쪽 볼
    ("right_cheek", (280,), 0.08),   # 오른쪽 볼
    ("nose", (4,), 0.05),            # 코
    ("chin", (152, 200), 0.05),      # 턱 — 두 점의 중간
)

# 홍조는 볼과 이마로만 판단한다 (코·턱은 원래 붉은기가 있어 과대평가된다)
REDNESS_REGIONS = ("forehead", "left_cheek", "right_cheek")


class AnalysisError(ValueError):
    """입력 이미지나 센서값이 분석 불가능한 경우.

    code는 프론트엔드가 분기에 쓰는 식별자이고, detail에는 판단에 쓸
    실제 측정값을 담는다 (예: 얼굴 너비가 몇 px이었는지).
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = ErrorCode.IMAGE_UNREADABLE,
        detail: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def _linear_score(value: float, lo: float, hi: float) -> int:
    """원시값을 0~100으로 선형 변환한다. lo 이하는 0, hi 이상은 100."""
    if hi <= lo:
        raise AnalysisError(
            f"정규화 구간이 잘못되었습니다: ({lo}, {hi})", code=ErrorCode.CONFIG_INVALID
        )
    return _clamp(round((value - lo) / (hi - lo) * 100))


# ── 이미지 준비 ─────────────────────────────────────────────────────


def _decode(image_bytes: bytes) -> np.ndarray:
    """바이트를 BGR 이미지로 디코딩하고 긴 변을 MAX_IMAGE_SIDE로 맞춘다."""
    if not image_bytes:
        raise AnalysisError("이미지 데이터가 비어 있습니다", code=ErrorCode.IMAGE_EMPTY)

    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise AnalysisError(
            "이미지를 읽을 수 없습니다 (지원하지 않는 형식이거나 손상된 파일)",
            code=ErrorCode.IMAGE_UNREADABLE,
        )

    height, width = image.shape[:2]
    longest = max(height, width)
    if longest > MAX_IMAGE_SIDE:
        scale = MAX_IMAGE_SIDE / longest
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return image


def _detect_landmarks(image: np.ndarray) -> np.ndarray:
    """얼굴 랜드마크를 픽셀 좌표 배열로 반환한다. (468, 2)"""
    from mediapipe.python.solutions import face_mesh as mp_face_mesh

    height, width = image.shape[:2]
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # FaceMesh 인스턴스는 스레드 안전하지 않아 요청마다 새로 만든다.
    with mp_face_mesh.FaceMesh(
        static_image_mode=True, max_num_faces=1, refine_landmarks=False
    ) as mesh:
        result = mesh.process(rgb)

    if not result.multi_face_landmarks:
        raise AnalysisError(
            "사진에서 얼굴을 찾을 수 없습니다 (정면 얼굴 사진을 사용하세요)",
            code=ErrorCode.FACE_NOT_FOUND,
        )

    points = result.multi_face_landmarks[0].landmark
    return np.array([(p.x * width, p.y * height) for p in points], dtype=np.float32)


def _refine_skin(lab: np.ndarray, mask: np.ndarray, *, min_pixels: int = 500) -> np.ndarray:
    """윤곽 안에 섞여 들어온 비피부 픽셀을 걷어낸다.

    얼굴 윤곽을 볼록껍질로 잡으면 머리카락선, 턱 그늘, 안경테 같은 것이
    함께 들어온다. 이들은 밝기 분포에서 멀리 떨어진 값이므로,
    중앙값 기준 MAD(중앙값 절대편차)로 바깥쪽을 잘라낸다.
    """
    values = lab[:, :, 0][mask > 0]
    if values.size == 0:
        raise AnalysisError("피부 영역을 찾을 수 없습니다", code=ErrorCode.SKIN_AREA_TOO_SMALL)

    median = float(np.median(values))
    mad = float(np.median(np.abs(values.astype(np.float32) - median)))
    spread = max(mad * SKIN_MAD_FACTOR, 8.0)  # MAD가 0에 가까울 때를 대비한 하한

    inlier = (np.abs(lab[:, :, 0].astype(np.float32) - median) <= spread).astype(np.uint8) * 255
    refined = cv2.bitwise_and(mask, inlier)

    # 경계 한 겹은 머리카락·배경과 섞이기 쉬워 깎아낸다
    refined = cv2.erode(refined, np.ones((3, 3), np.uint8), iterations=1)

    if int(np.count_nonzero(refined)) < min_pixels:
        raise AnalysisError(
            "분석 가능한 피부 영역이 너무 작습니다", code=ErrorCode.SKIN_AREA_TOO_SMALL
        )
    return refined


def _region_masks(image: np.ndarray, landmarks: np.ndarray) -> dict[str, np.ndarray]:
    """부위별 원형 패치 마스크를 만든다. 이마·양볼·코·턱 5곳."""
    height, width = image.shape[:2]
    face_width = float(np.ptp(landmarks[:, 0]))

    masks: dict[str, np.ndarray] = {}
    for name, indices, ratio in REGIONS:
        center = landmarks[list(indices)].mean(axis=0)
        x, y = int(round(center[0])), int(round(center[1]))
        if not (0 <= x < width and 0 <= y < height):
            continue  # 얼굴이 화면 밖으로 잘린 경우 그 부위는 건너뛴다

        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.circle(mask, (x, y), max(3, int(face_width * ratio)), 255, thickness=-1)
        masks[name] = mask

    if not masks:
        raise AnalysisError(
            "얼굴이 화면 안에 충분히 들어오지 않았습니다", code=ErrorCode.FACE_OUT_OF_FRAME
        )
    return masks


def _white_balance(image: np.ndarray) -> np.ndarray:
    """이미지 전체 기준 그레이월드 보정을 적용한 BGR 이미지를 돌려준다.

    기준을 피부 영역으로 잡으면 피부 평균색이 회색으로 강제되어
    홍조 신호가 통째로 사라진다. 그래서 화면 전체를 기준으로 삼는다.
    절대 밝기까지 맞추지는 않으므로, 촬영 가이드(조명 조건)는 여전히 필요하다.
    """
    means = cv2.mean(image)[:3]  # B, G, R
    target = float(np.mean(means))

    balanced = image.astype(np.float32)
    for channel, mean in enumerate(means):
        if mean > 1.0:
            balanced[:, :, channel] *= target / mean

    return np.clip(balanced, 0, 255).astype(np.uint8)


# ── 지표별 계산 ─────────────────────────────────────────────────────


def _redness_index(image: np.ndarray) -> np.ndarray:
    """홍조 지수 맵. 100 * log10(R / G).

    a* 같은 절대 색차는 노출에 따라 압축되거나 벌어진다. 어두운 사진에서는
    붉은기가 있어도 값이 작게 나온다. 반면 R과 G의 비율은 노출이 바뀌어도
    함께 변하므로 거의 유지된다. 피부과에서 쓰는 Erythema Index와 같은 원리다.
    """
    blue_green_red = image.astype(np.float32) + 1.0  # log(0) 방지
    green = blue_green_red[:, :, 1]
    red = blue_green_red[:, :, 2]
    return 100.0 * np.log10(red / green)


def _brightness(lab: np.ndarray, skin: np.ndarray) -> tuple[int, float]:
    mean_l = cv2.mean(lab[:, :, 0], mask=skin)[0]
    return _linear_score(mean_l, *BRIGHTNESS_RANGE), mean_l


def _redness(index_map: np.ndarray, patches: np.ndarray) -> tuple[int, float]:
    mean_index = cv2.mean(index_map, mask=patches)[0]
    return _linear_score(mean_index, *REDNESS_RANGE), mean_index


def _trouble(
    index_map: np.ndarray, skin: np.ndarray, face_width: float
) -> tuple[int, float, float]:
    """평소 질감보다 유독 붉은 '덩어리'의 면적 비율로 트러블을 추정한다.

    임계값을 그 사진의 질감 변동폭에 맞춰 잡으므로, 촬영 밝기에 따라
    같은 피부가 다르게 판정되는 문제를 줄인다.
    """
    # 픽셀 단위 센서 노이즈 완화 (실수 상태에서 먼저 처리한다)
    smooth = cv2.GaussianBlur(index_map.astype(np.float32), (3, 3), 0)

    # 이 사진 피부의 지수 중앙값을 기준점으로 삼아 uint8 격자에 담는다.
    # medianBlur가 uint8만 받기 때문이며, 배경 추정용으로만 쓴다.
    center = float(np.median(smooth[skin > 0]))
    fine = (smooth - center) * TROUBLE_INDEX_GAIN
    scaled = np.clip(fine + 128.0, 0, 255).astype(np.uint8)

    # 얼굴 크기에 비례한 홀수 커널 (작은 반점만 남기고 넓은 홍조는 상쇄)
    kernel = max(3, int(face_width * 0.05) | 1)
    local_median = cv2.medianBlur(scaled, kernel).astype(np.float32) - 128.0

    # 주변 피부 대비 얼마나 붉은지 (양자화되지 않은 실수값으로 계산)
    deviation = fine - local_median

    # 이 사진 피부의 평소 변동폭 (MAD 기반 로버스트 표준편차)
    spread = 1.4826 * float(np.median(np.abs(deviation[skin > 0])))
    threshold = max(
        TROUBLE_MIN_THRESHOLD * TROUBLE_INDEX_GAIN, TROUBLE_SIGMA_FACTOR * spread
    )

    candidate = ((deviation > threshold) & (skin > 0)).astype(np.uint8)

    # 지름이 기준 미만인 조각은 노이즈로 보고 버린다
    min_diameter = max(2.0, face_width * TROUBLE_MIN_BLOB_RATIO)
    min_area = max(4, int(np.pi / 4 * min_diameter**2))

    count, _, stats, _ = cv2.connectedComponentsWithStats(candidate, connectivity=8)
    blemish_px = sum(
        int(stats[i, cv2.CC_STAT_AREA])
        for i in range(1, count)  # 0번은 배경
        if stats[i, cv2.CC_STAT_AREA] >= min_area
    )

    ratio = blemish_px / float(np.count_nonzero(skin))
    return _linear_score(ratio, *TROUBLE_RANGE), ratio, threshold / TROUBLE_INDEX_GAIN


def _uniformity(lab: np.ndarray, skin: np.ndarray) -> tuple[int, float]:
    """피부 톤 표준편차의 역방향 점수. 고를수록 높다."""
    _, std = cv2.meanStdDev(lab[:, :, 0], mask=skin)
    std_l = float(std[0][0])
    unevenness = _linear_score(std_l, *UNIFORMITY_STD_RANGE)
    return _clamp(100 - unevenness), std_l


# ── 공개 함수 ───────────────────────────────────────────────────────


def analyze_image_detail(
    image_bytes: bytes, *, min_face_width: int = DEFAULT_MIN_FACE_WIDTH
) -> tuple[dict[str, int], dict[str, float]]:
    """지표 점수 4개와, 정규화 전 원시값을 함께 돌려준다.

    원시값에는 부위별 측정치도 담긴다. 정규화 구간을 조정할 때와,
    "볼이 유독 붉다" 같은 부위별 안내를 만들 때 쓴다.
    """
    image = _decode(image_bytes)
    landmarks = _detect_landmarks(image)
    balanced = _white_balance(image)
    lab = cv2.cvtColor(balanced, cv2.COLOR_BGR2LAB)
    face_width = float(np.ptp(landmarks[:, 0]))

    # 얼굴이 너무 작으면 트러블 탐지가 둔해져 점수를 신뢰할 수 없다
    if face_width < min_face_width:
        raise AnalysisError(
            f"얼굴이 너무 작게 나왔습니다 (너비 {face_width:.0f}px, 최소 {min_face_width}px). "
            "얼굴이 화면에 더 크게 들어오도록 가까이에서 촬영해주세요.",
            code=ErrorCode.FACE_TOO_SMALL,
            detail={"face_width_px": round(face_width, 1), "required_px": min_face_width},
        )

    # 부위별 패치 → 각 패치 안에서 비피부 픽셀(그늘·머리카락·안경) 제거
    regions: dict[str, np.ndarray] = {}
    for name, mask in _region_masks(image, landmarks).items():
        try:
            regions[name] = _refine_skin(lab, mask, min_pixels=100)
        except AnalysisError:
            continue  # 해당 부위가 가려졌으면 제외하고 진행한다
    if not regions:
        raise AnalysisError(
            "분석 가능한 피부 영역을 찾지 못했습니다", code=ErrorCode.SKIN_AREA_TOO_SMALL
        )

    skin = np.zeros(image.shape[:2], dtype=np.uint8)
    for mask in regions.values():
        skin = cv2.bitwise_or(skin, mask)

    red_mask = np.zeros(image.shape[:2], dtype=np.uint8)
    for name in REDNESS_REGIONS:
        if name in regions:
            red_mask = cv2.bitwise_or(red_mask, regions[name])
    if int(np.count_nonzero(red_mask)) < 100:
        red_mask = skin  # 볼·이마가 모두 가려졌으면 전체로 대체

    brightness, mean_l = _brightness(lab, skin)

    # 노출이 극단적이면 어떤 보정으로도 피부 정보가 남아 있지 않다
    low, high = EXPOSURE_L_RANGE
    if mean_l < low:
        raise AnalysisError(
            f"사진이 너무 어둡습니다 (피부 밝기 {mean_l:.0f}, 최소 {low:.0f}). "
            "조명이 있는 곳에서 다시 촬영해주세요.",
            code=ErrorCode.IMAGE_TOO_DARK,
            detail={"mean_l": round(mean_l, 1), "required_min": low},
        )
    if mean_l > high:
        raise AnalysisError(
            f"사진이 너무 밝습니다 (피부 밝기 {mean_l:.0f}, 최대 {high:.0f}). "
            "직사광이나 강한 조명을 피해 다시 촬영해주세요.",
            code=ErrorCode.IMAGE_TOO_BRIGHT,
            detail={"mean_l": round(mean_l, 1), "required_max": high},
        )

    # 평균은 괜찮아도 하이라이트가 날아간 사진은 색 정보가 없어 거부한다
    skin_pixels = image[skin > 0]  # 보정 전 원본 기준으로 포화 여부를 본다
    saturated_ratio = float(
        np.mean(skin_pixels.max(axis=1) >= SATURATED_CHANNEL_LEVEL)
    )
    if saturated_ratio > MAX_SATURATED_SKIN_RATIO:
        raise AnalysisError(
            f"사진 일부가 하얗게 날아갔습니다 (포화 {saturated_ratio * 100:.0f}%, "
            f"최대 {MAX_SATURATED_SKIN_RATIO * 100:.0f}%). "
            "직사광이나 플래시 반사를 피해 다시 촬영해주세요.",
            code=ErrorCode.IMAGE_TOO_BRIGHT,
            detail={
                "saturated_ratio": round(saturated_ratio, 3),
                "required_max": MAX_SATURATED_SKIN_RATIO,
            },
        )

    index_map = _redness_index(balanced)
    redness, mean_index = _redness(index_map, red_mask)
    trouble, blemish_ratio, trouble_threshold = _trouble(index_map, skin, face_width)
    uniformity, std_l = _uniformity(lab, skin)

    scores = {
        "redness": redness,
        "brightness": brightness,
        "trouble": trouble,
        "uniformity": uniformity,
    }
    raw = {
        "redness_index": round(mean_index, 2),     # REDNESS_RANGE 기준
        "mean_l_skin": round(mean_l, 2),           # BRIGHTNESS_RANGE 기준
        "saturated_ratio": round(saturated_ratio, 3),
        "blemish_ratio": round(blemish_ratio, 5),  # TROUBLE_RANGE 기준
        "trouble_threshold": round(trouble_threshold, 2),  # 이 사진에 적용된 임계값
        "std_l_skin": round(std_l, 2),             # UNIFORMITY_STD_RANGE 기준
        "face_width_px": round(face_width, 1),
        "skin_px": int(np.count_nonzero(skin)),
    }
    # 부위별 측정치 (어느 부위가 붉은지/어두운지 확인용)
    for name, mask in regions.items():
        raw[f"{name}_idx"] = round(cv2.mean(index_map, mask=mask)[0], 2)
        raw[f"{name}_l"] = round(cv2.mean(lab[:, :, 0], mask=mask)[0], 2)

    return scores, raw


def analyze_image(
    image_bytes: bytes, *, min_face_width: int = DEFAULT_MIN_FACE_WIDTH
) -> dict[str, int]:
    """사진에서 지표 점수 4개를 산출한다."""
    scores, _ = analyze_image_detail(image_bytes, min_face_width=min_face_width)
    return scores


def analyze_image_dummy(seed_key: str) -> Mapping[str, int]:
    """사진 없이 쓰는 임시 점수.

    S3가 아직 준비되지 않은 환경에서 파이프라인을 돌려보기 위한 것이다.
    같은 seed_key면 같은 점수가 나오도록 해시를 쓴다.
    """
    digest = hashlib.sha256(seed_key.encode()).digest()
    return {
        code: _clamp(round(digest[i * 4] / 255 * 100))
        for i, code in enumerate(PHOTO_METRIC_CODES)
    }


def moisture_score_from_raw(raw: int) -> int:
    """센서 raw값(ADC)을 0~100 점수로 정규화한다."""
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise AnalysisError(
            f"수분 raw값은 정수여야 합니다: {raw!r}", code=ErrorCode.INVALID_MOISTURE_INPUT
        )
    if not MOISTURE_RAW_MIN <= raw <= MOISTURE_RAW_MAX:
        raise AnalysisError(
            f"수분 raw값은 {MOISTURE_RAW_MIN}~{MOISTURE_RAW_MAX} 범위여야 합니다: {raw}",
            code=ErrorCode.INVALID_MOISTURE_INPUT,
            detail={"min": MOISTURE_RAW_MIN, "max": MOISTURE_RAW_MAX},
        )

    span = MOISTURE_RAW_MAX - MOISTURE_RAW_MIN
    return _clamp(round((raw - MOISTURE_RAW_MIN) / span * 100))


def with_moisture(
    photo_scores: Mapping[str, int],
    *,
    moisture_source: str,
    moisture_raw: int | None = None,
    moisture_score: int | None = None,
) -> dict[str, int]:
    """사진 점수 4개에 수분 점수를 합쳐 라벨링 서비스에 넘길 형태로 만든다.

    moisture_source별 입력:
      sensor — moisture_raw (ADC 원시값)
      manual — moisture_score (0~100, 디버깅·센서 장애 시 대체 입력)
      none   — 없음 (사진 기반 4개 지표만 사용)
    """
    scores = dict(photo_scores)

    if moisture_source == "sensor":
        if moisture_raw is None:
            raise AnalysisError(
                "sensor일 때는 moisture_raw가 필요합니다",
                code=ErrorCode.INVALID_MOISTURE_INPUT,
            )
        scores["moisture"] = moisture_score_from_raw(moisture_raw)
    elif moisture_source == "manual":
        if moisture_score is None:
            raise AnalysisError(
                "manual일 때는 moisture_score가 필요합니다",
                code=ErrorCode.INVALID_MOISTURE_INPUT,
            )
        if not 0 <= moisture_score <= 100:
            raise AnalysisError(
                f"수분 점수는 0~100 범위여야 합니다: {moisture_score}",
                code=ErrorCode.INVALID_MOISTURE_INPUT,
            )
        scores["moisture"] = moisture_score
    elif moisture_source == "none":
        if moisture_raw is not None or moisture_score is not None:
            raise AnalysisError(
                "none일 때는 수분값을 보내지 않습니다", code=ErrorCode.INVALID_MOISTURE_INPUT
            )
    else:
        raise AnalysisError(
            f"알 수 없는 moisture_source입니다: {moisture_source}",
            code=ErrorCode.INVALID_MOISTURE_INPUT,
        )

    return scores
