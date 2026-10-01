"""피부 지표 점수 산출.

사진에서 4개 지표(홍조·밝기·트러블·균일도)를, 센서값에서 수분 지표를
각각 0~100 점수로 만든다.

사진 분석 흐름
  1) 디코딩 → 긴 변 기준 축소 (연산량 고정)
  2) MediaPipe FaceMesh로 랜드마크 추출
  3) 얼굴 윤곽에서 눈·눈썹·입을 제외한 피부 마스크 생성
  4) 그레이월드 화이트밸런스로 조명 색상 보정 후 Lab 색공간 변환
  5) 지표별 원시값 계산 → 0~100 정규화

주의: 아래 임계값 상수는 샘플 사진으로 맞춰야 하는 잠정값이다.
"""

import hashlib
from collections.abc import Mapping
from functools import lru_cache

import cv2
import numpy as np

# 사진에서 산출하는 지표 (수분은 센서/직접입력이므로 제외)
PHOTO_METRIC_CODES = ("redness", "brightness", "trouble", "uniformity")

# 아두이노 수분 센서의 ADC 출력 범위.
# 실측 캘리브레이션 전까지의 임시값이므로, 측정 후 이 두 값을 조정한다.
MOISTURE_RAW_MIN = 0
MOISTURE_RAW_MAX = 1023

# 분석 해상도. 크면 느려지고 작으면 트러블 탐지가 둔해진다.
MAX_IMAGE_SIDE = 1024

# ── 지표별 정규화 구간 (원시값 lo → 0점, hi → 100점) ──────────────────
# 전부 샘플 사진으로 조정해야 하는 잠정값이다.
BRIGHTNESS_RANGE = (100.0, 210.0)    # 피부 영역 L 채널 평균 (0~255)
REDNESS_RANGE = (2.0, 15.0)          # 볼·이마의 a* 평균 (중립=0)
TROUBLE_RANGE = (0.0, 0.02)          # 반점으로 탐지된 픽셀 비율
UNIFORMITY_STD_RANGE = (10.0, 35.0)  # 피부 영역 L 채널 표준편차 (낮을수록 균일)

# 주변보다 이만큼 붉으면 트러블로 본다 (a* 기준, 국소 중앙값 대비)
TROUBLE_A_THRESHOLD = 3.0

# 피부 마스크 정제 강도. 중앙값에서 이 배수(MAD 기준)를 벗어난 픽셀은 버린다.
# 머리카락·그림자·안경처럼 피부가 아닌 것이 마스크에 섞이면 통계가 망가진다.
SKIN_MAD_FACTOR = 2.5

# 볼·이마에서 떼어내는 패치 반지름 (얼굴 너비 대비 비율)
PATCH_RADIUS_RATIO = 0.06
# 볼 중앙 / 이마 중앙에 해당하는 FaceMesh 랜드마크 번호
CHEEK_LANDMARKS = (50, 280)
FOREHEAD_LANDMARK = 151


class AnalysisError(ValueError):
    """입력 이미지나 센서값이 분석 불가능한 경우."""


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def _linear_score(value: float, lo: float, hi: float) -> int:
    """원시값을 0~100으로 선형 변환한다. lo 이하는 0, hi 이상은 100."""
    if hi <= lo:
        raise AnalysisError(f"정규화 구간이 잘못되었습니다: ({lo}, {hi})")
    return _clamp(round((value - lo) / (hi - lo) * 100))


# ── 이미지 준비 ─────────────────────────────────────────────────────


def _decode(image_bytes: bytes) -> np.ndarray:
    """바이트를 BGR 이미지로 디코딩하고 긴 변을 MAX_IMAGE_SIDE로 맞춘다."""
    if not image_bytes:
        raise AnalysisError("이미지 데이터가 비어 있습니다")

    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise AnalysisError("이미지를 읽을 수 없습니다 (지원하지 않는 형식이거나 손상된 파일)")

    height, width = image.shape[:2]
    longest = max(height, width)
    if longest > MAX_IMAGE_SIDE:
        scale = MAX_IMAGE_SIDE / longest
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return image


@lru_cache
def _landmark_groups():
    """FaceMesh의 부위별 랜드마크 번호 묶음. import 비용이 커서 한 번만 만든다."""
    from mediapipe.python.solutions import face_mesh_connections as conn

    def indices(connections) -> list[int]:
        return sorted({index for pair in connections for index in pair})

    return {
        "oval": indices(conn.FACEMESH_FACE_OVAL),
        "exclude": [
            indices(conn.FACEMESH_LEFT_EYE),
            indices(conn.FACEMESH_RIGHT_EYE),
            indices(conn.FACEMESH_LEFT_EYEBROW),
            indices(conn.FACEMESH_RIGHT_EYEBROW),
            indices(conn.FACEMESH_LIPS),
        ],
    }


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
        raise AnalysisError("사진에서 얼굴을 찾을 수 없습니다 (정면 얼굴 사진을 사용하세요)")

    points = result.multi_face_landmarks[0].landmark
    return np.array([(p.x * width, p.y * height) for p in points], dtype=np.float32)


def _skin_mask(image: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
    """얼굴 윤곽 안쪽에서 눈·눈썹·입을 제외한 피부 영역 마스크."""
    groups = _landmark_groups()
    mask = np.zeros(image.shape[:2], dtype=np.uint8)

    outline = cv2.convexHull(landmarks[groups["oval"]].astype(np.int32))
    cv2.fillConvexPoly(mask, outline, 255)

    # 눈·눈썹·입은 피부색 통계를 왜곡하므로 제외한다
    for part in groups["exclude"]:
        hull = cv2.convexHull(landmarks[part].astype(np.int32))
        cv2.fillConvexPoly(mask, hull, 0)

    if int(np.count_nonzero(mask)) < 500:
        raise AnalysisError("피부 영역이 너무 작습니다 (얼굴이 더 크게 나온 사진을 사용하세요)")
    return mask


def _refine_skin(lab: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """윤곽 안에 섞여 들어온 비피부 픽셀을 걷어낸다.

    얼굴 윤곽을 볼록껍질로 잡으면 머리카락선, 턱 그늘, 안경테 같은 것이
    함께 들어온다. 이들은 밝기 분포에서 멀리 떨어진 값이므로,
    중앙값 기준 MAD(중앙값 절대편차)로 바깥쪽을 잘라낸다.
    """
    values = lab[:, :, 0][mask > 0]
    if values.size == 0:
        raise AnalysisError("피부 영역을 찾을 수 없습니다")

    median = float(np.median(values))
    mad = float(np.median(np.abs(values.astype(np.float32) - median)))
    spread = max(mad * SKIN_MAD_FACTOR, 8.0)  # MAD가 0에 가까울 때를 대비한 하한

    inlier = (np.abs(lab[:, :, 0].astype(np.float32) - median) <= spread).astype(np.uint8) * 255
    refined = cv2.bitwise_and(mask, inlier)

    # 경계 한 겹은 머리카락·배경과 섞이기 쉬워 깎아낸다
    refined = cv2.erode(refined, np.ones((3, 3), np.uint8), iterations=1)

    if int(np.count_nonzero(refined)) < 500:
        raise AnalysisError("분석 가능한 피부 영역이 너무 작습니다")
    return refined


def _patch_mask(image: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
    """볼 2곳과 이마 1곳의 원형 패치 마스크. 홍조 측정에 쓴다."""
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    face_width = float(np.ptp(landmarks[:, 0]))
    radius = max(3, int(face_width * PATCH_RADIUS_RATIO))

    for index in (*CHEEK_LANDMARKS, FOREHEAD_LANDMARK):
        center = tuple(landmarks[index].astype(int))
        cv2.circle(mask, center, radius, 255, thickness=-1)
    return mask


def _white_balanced_lab(image: np.ndarray) -> np.ndarray:
    """이미지 전체 기준 그레이월드 보정 후 Lab으로 변환한다.

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

    balanced = np.clip(balanced, 0, 255).astype(np.uint8)
    return cv2.cvtColor(balanced, cv2.COLOR_BGR2LAB)


# ── 지표별 계산 ─────────────────────────────────────────────────────


def _brightness(lab: np.ndarray, skin: np.ndarray) -> tuple[int, float]:
    mean_l = cv2.mean(lab[:, :, 0], mask=skin)[0]
    return _linear_score(mean_l, *BRIGHTNESS_RANGE), mean_l


def _redness(lab: np.ndarray, patches: np.ndarray) -> tuple[int, float]:
    # OpenCV Lab에서 a 채널은 128이 중립이다
    mean_a = cv2.mean(lab[:, :, 1], mask=patches)[0] - 128.0
    return _linear_score(mean_a, *REDNESS_RANGE), mean_a


def _trouble(lab: np.ndarray, skin: np.ndarray, face_width: float) -> tuple[int, float]:
    """국소 중앙값보다 유독 붉은 픽셀의 비율로 트러블을 추정한다."""
    a_channel = lab[:, :, 1]

    # 얼굴 크기에 비례한 홀수 커널 (작은 반점만 남기고 넓은 홍조는 상쇄)
    kernel = max(3, int(face_width * 0.05) | 1)
    local_median = cv2.medianBlur(a_channel, kernel)

    deviation = a_channel.astype(np.int16) - local_median.astype(np.int16)
    blemish = (deviation > TROUBLE_A_THRESHOLD) & (skin > 0)

    ratio = float(np.count_nonzero(blemish)) / float(np.count_nonzero(skin))
    return _linear_score(ratio, *TROUBLE_RANGE), ratio


def _uniformity(lab: np.ndarray, skin: np.ndarray) -> tuple[int, float]:
    """피부 톤 표준편차의 역방향 점수. 고를수록 높다."""
    _, std = cv2.meanStdDev(lab[:, :, 0], mask=skin)
    std_l = float(std[0][0])
    unevenness = _linear_score(std_l, *UNIFORMITY_STD_RANGE)
    return _clamp(100 - unevenness), std_l


# ── 공개 함수 ───────────────────────────────────────────────────────


def analyze_image_detail(image_bytes: bytes) -> tuple[dict[str, int], dict[str, float]]:
    """지표 점수 4개와, 정규화 전 원시값을 함께 돌려준다.

    원시값은 정규화 구간(BRIGHTNESS_RANGE 등)을 샘플 사진에 맞춰
    조정할 때 쓰며, 디버그 엔드포인트에서만 노출한다.
    """
    image = _decode(image_bytes)
    landmarks = _detect_landmarks(image)

    lab = _white_balanced_lab(image)
    face_width = float(np.ptp(landmarks[:, 0]))

    # 윤곽 마스크 → 비피부 픽셀 제거
    skin = _refine_skin(lab, _skin_mask(image, landmarks))
    # 볼·이마 패치도 정제된 피부 영역 안쪽만 쓴다
    patches = cv2.bitwise_and(_patch_mask(image, landmarks), skin)
    if int(np.count_nonzero(patches)) < 100:
        patches = skin  # 패치가 가려졌으면 피부 전체로 대체

    redness, mean_a = _redness(lab, patches)
    brightness, mean_l = _brightness(lab, skin)
    trouble, blemish_ratio = _trouble(lab, skin, face_width)
    uniformity, std_l = _uniformity(lab, skin)

    scores = {
        "redness": redness,
        "brightness": brightness,
        "trouble": trouble,
        "uniformity": uniformity,
    }
    raw = {
        "mean_a_patch": round(mean_a, 2),      # REDNESS_RANGE 기준
        "mean_l_skin": round(mean_l, 2),       # BRIGHTNESS_RANGE 기준
        "blemish_ratio": round(blemish_ratio, 5),  # TROUBLE_RANGE 기준
        "std_l_skin": round(std_l, 2),         # UNIFORMITY_STD_RANGE 기준
        "face_width_px": round(face_width, 1),
        "skin_px": int(np.count_nonzero(skin)),
        "patch_px": int(np.count_nonzero(patches)),
    }
    return scores, raw


def analyze_image(image_bytes: bytes) -> dict[str, int]:
    """사진에서 지표 점수 4개를 산출한다."""
    scores, _ = analyze_image_detail(image_bytes)
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
        raise AnalysisError(f"수분 raw값은 정수여야 합니다: {raw!r}")
    if not MOISTURE_RAW_MIN <= raw <= MOISTURE_RAW_MAX:
        raise AnalysisError(
            f"수분 raw값은 {MOISTURE_RAW_MIN}~{MOISTURE_RAW_MAX} 범위여야 합니다: {raw}"
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
