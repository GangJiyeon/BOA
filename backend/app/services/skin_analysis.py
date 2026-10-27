"""피부 지표 점수 산출.

사진에서 4개 지표(홍조·밝기·트러블·균일도)를, 센서값에서 수분 지표를
각각 0~100 점수로 만든다.

사진 분석 흐름
  1) 디코딩 → 축소본에서 MediaPipe FaceMesh로 얼굴 위치(랜드마크) 추출
  2) 원본에서 얼굴 부분만 잘라, 얼굴 너비가 ANALYSIS_FACE_WIDTH보다 크면 그 크기로 줄임 (확대는 안 함)
  3) 밝기·균일도·홍조: 이마·양볼·코·턱 다섯 부위를 원형 패치로 떼어냄
     트러블: 볼을 크게 잡은 넓은 패치(TROUBLE_REGIONS)를 씀
  4) 볼 밝기를 기준으로 머리카락(앞머리 등)을 걷어내고, 대부분 가려진 부위는 제외
     → 남은 픽셀에서 그늘·하이라이트 같은 이상치 제거
  5) 카메라 프로필(CAMERA_PROFILES)의 고정 색 보정 적용 후 Lab 색공간 변환
  6) 촬영 품질 검사: 노출 과부족·하이라이트 포화·조명 치우침이면 재촬영 요청
  7) 지표별 원시값 계산 → 0~100 정규화

주의: 아래 임계값 상수는 샘플 사진으로 맞춰야 하는 잠정값이다.
"""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import NamedTuple

import cv2
import numpy as np

from app.services.errors import ErrorCode

# 사진에서 산출하는 지표 (수분은 센서/직접입력이므로 제외)
PHOTO_METRIC_CODES = ("redness", "brightness", "trouble", "uniformity")

# 아두이노 수분 센서의 ADC 출력 범위.
# 실측 캘리브레이션 전까지의 임시값이므로, 측정 후 이 두 값을 조정한다.
MOISTURE_RAW_MIN = 0
MOISTURE_RAW_MAX = 1023

# 얼굴 위치(랜드마크)를 찾을 때 쓰는 축소본 해상도. 위치만 찾으면 되므로 작아도 된다.
MAX_IMAGE_SIDE = 1024

# 분석 해상도 상한. 원본에서 얼굴 부분만 잘라, 얼굴 너비가 이 값(px)보다 크면 이 값으로 줄인다.
# 실제 키오스크 기기(갤럭시북4 720p 웹캠)에서 얼굴 너비가 약 400px로 찍히므로 그에 맞췄다.
#  - 휴대폰 등 고해상도 테스트 사진도 키오스크와 같은 조건으로 분석되어,
#    테스트 결과를 실제 환경에 그대로 참고할 수 있다.
#  - 원본 그대로(2,000px 이상) 분석해도 정확도는 거의 같고 5~15배 느렸다
#    (지표 대부분이 평균값이고, 트러블 최소 크기도 얼굴 너비 대비 비율이기 때문).
# 더 좋은 카메라로 바꾸면 그 카메라의 얼굴 너비에 맞춰 이 값을 올린다.
ANALYSIS_FACE_WIDTH = 400

# 얼굴을 잘라낼 때 랜드마크 바깥으로 둘 여유 (얼굴 너비 대비)
FACE_CROP_MARGIN = 0.15

# 허용할 최소 얼굴 너비(px)의 기본값. 실제 값은 설정(MIN_FACE_WIDTH_PX)에서 주입한다.
# 얼굴이 작게 찍히면 작은 반점이 뭉개져 트러블 점수가 낮게 나온다.
DEFAULT_MIN_FACE_WIDTH = 250

# ── 지표별 정규화 구간 (원시값 lo → 0점, hi → 100점) ──────────────────
# 절대적인 임상 기준이 없으므로, 같은 조명에서 촬영한 표본 5장의 분포에서
# 33/67 분위수가 판정 구간 경계(33점/67점)에 오도록 역산한 값이다.
# 즉 "이 점수는 표본 분포상의 상대 위치"라는 의미이며, 표본이 늘어나면
# 분위수를 다시 계산해 갱신해야 한다.
BRIGHTNESS_RANGE = (100.0, 210.0)    # 피부 영역 L 채널 평균 (0~255)
REDNESS_RANGE = (6.0, 14.0)          # 볼·이마의 홍조 지수 (R/G 로그비). 기본(phone) 프로필 값
TROUBLE_RANGE = (0.0, 0.028)         # 반점으로 탐지된 픽셀 비율
# 균일도: 조명 흐름(큰 그늘)을 뺀 뒤 남은 국소 밝기 편차 (낮을수록 균일).
# 잠정값이다. 피부가 깨끗한 휴대폰 사진 2.8~3.1, 여드름 많은 얼굴 4.4, 웹캠 1.7~2.1이 나왔다.
# 실제 시연 기기(갤럭시북 웹캠) 표본으로 다시 맞춰야 한다.
UNIFORMITY_STD_RANGE = (2.5, 5.0)

# 홍조 지수를 uint8로 옮길 때 쓰는 배율.
# 지수 1단위를 16단계로 쪼개므로 국소 중앙값 계산의 양자화 오차가 작다.
# 담는 기준점은 그 사진 피부의 중앙값으로 잡아, 전체적으로 붉은 피부에서도
# 표현 범위(중앙값 ±8 지수)가 밀리지 않게 한다.
TROUBLE_INDEX_GAIN = 16.0

# 홍조 측정 가능 하한.
# 홍조 지수가 기준 범위 하한보다 '범위 폭 x 이 비율' 넘게 낮으면 측정 불가로 돌려보낸다.
# 사람 피부는 중립 조명에서 R/G가 일정 수준 이상이라, 이보다 훨씬 낮으면 피부가 아니라
# 카메라 색 처리(채도 저하·푸른 치우침)나 조명 때문이다. 이 값을 0점으로 내보내면
# '홍조 없음'으로 오해되어 엉뚱한 추천으로 이어진다.
# (표본: 휴대폰 8.7~10.7, 붉은 얼굴 16.6, 기기 보정 전 웹캠 2.2~2.4 → 웹캠은 측정 불가)
# 기준은 카메라 프로필의 홍조 범위에 연동되므로, 범위를 다시 맞추면 함께 옮겨간다.
REDNESS_INVALID_MARGIN = 0.25

# 균일도 계산 시 조명 흐름을 뽑는 블러 크기 (얼굴 너비 대비 가우시안 시그마).
# 이보다 큰 밝기 변화(얼굴 굴곡 그늘, 한쪽 조명)는 조명으로 보고 빼고, 작은 얼룩·잡티만 남긴다.
# 예전 방식(부위 전체 표준편차)은 한쪽 조명 사진을 가장 나쁘게(19.4),
# 여드름 많은 얼굴을 오히려 고르게(8.6) 판정했다. 이 방식으로는 각각 3.4, 4.4다.
UNIFORMITY_FLATTEN_SIGMA_RATIO = 0.02

# 트러블 계산 전에 홍조 지수 지도를 부드럽게 만드는 블러 크기 (얼굴 너비 대비).
# 웹캠 사진은 어두운 곳의 센서 노이즈와 색 정보 해상도(2x2) 때문에 작은 가짜 덩어리가 생긴다.
# 3x3 → 7x7(얼굴 400px 기준)로 키우면 웹캠 가짜 트러블이 49→22점으로 줄고,
# 여드름 얼굴은 100점 그대로, 작은 점(지름 1.5mm)은 오히려 더 잘 잡혔다(14→19점).
TROUBLE_BLUR_RATIO = 0.0175

# 트러블 판정 임계값 (홍조 지수 단위). 주변 피부보다 이만큼 더 붉으면 트러블 후보로 본다.
# 예전에는 사진마다 피부결 변동폭의 3배로 임계값을 올렸는데, 여드름이 많은 피부는
# 그 자체로 변동폭이 커서 임계값이 약 2배로 올라가 여드름 대부분을 놓쳤다
# (여드름 많은 표본: 임계값 0.8→1.46, 덩어리 27개→4개). 그래서 고정값을 쓴다.
# 피부가 깨끗한 실사진들은 원래부터 하한(0.8)이 적용되고 있어 결과가 같다.
TROUBLE_THRESHOLD = 0.8

# 트러블로 인정할 최소 덩어리 지름 (얼굴 너비 대비 비율).
# 실제 병변은 덩어리로 뭉쳐 있고 센서 노이즈는 흩어진 점이다.
# 이 필터가 없으면 밝게 찍힌 사진일수록 노이즈가 더 많이 잡혀 점수가 부풀려진다.
TROUBLE_MIN_BLOB_RATIO = 0.01

# 피부 영역 가장자리에 걸친 덩어리는 트러블에서 뺀다.
# 패치 경계 바로 바깥에 그늘·수염·머리카락처럼 덜 붉은 것이 있으면,
# 경계 안쪽 피부가 상대적으로 "유독 붉다"고 잘못 판정되기 때문이다.
# (표본: 턱 패치 경계 3px 안에 붙은 가짜 덩어리 2개, 실제 반점은 경계 비율 0%)
TROUBLE_EDGE_BAND_RATIO = 0.008   # 가장자리 띠 두께 (얼굴 너비 대비, 최소 2px)
TROUBLE_MAX_EDGE_SHARE = 0.5      # 덩어리 픽셀 중 이 비율 이상이 띠 안에 있으면 제외

# 조명이 한쪽으로 치우친 사진은 거부한다.
# 양볼 밝기 비율(어두운 쪽 / 밝은 쪽)이 이 값 미만이면 다시 촬영을 요청한다.
# 한쪽 조명은 균일도를 크게 왜곡한다 (같은 사람: 비율 0.76 → 균일도 '개선 필요',
# 비율 0.97 → '양호'). 표본: 정상 촬영 0.91~0.99, 한쪽 조명 0.76.
MIN_CHEEK_L_RATIO = 0.85

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

# ── 가림(앞머리 등) 판정 ─────────────────────────────────────────────
# 패치별 MAD 정제는 "패치 안의 다수"를 피부로 간주한다. 앞머리가 이마 패치를
# 대부분 덮으면 머리카락이 다수가 되어, 머리카락이 남고 피부가 버려진다.
# 그래서 패치 바깥의 기준(양볼)으로 먼저 머리카락을 걷어낸 뒤 MAD 정제를 한다.
#
# 피부 기준색을 잡을 부위. 볼은 앞머리에 거의 가려지지 않는다.
# 볼이 화면 밖으로 잘린 경우에만 코·턱으로 대체한다.
SKIN_REFERENCE_REGIONS = ("left_cheek", "right_cheek")
SKIN_REFERENCE_FALLBACK = ("nose", "chin")

# 기준 피부 밝기(L) 대비 이 비율보다 어두우면 머리카락으로 본다.
# 색(a*·b*) 차이는 쓰지 않는다. 붉은 트러블은 색이 기준과 달라도 어둡지는 않아서,
# 색으로 거르면 진짜 트러블까지 "피부 아님"으로 빠져버린다.
# 표본: 볼 기준 대비 앞머리 0.41, 그늘·수염 있는 턱 0.84.
HAIR_MAX_L_RATIO = 0.6

# 머리카락 경계에서 이 거리(얼굴 너비 대비)만큼은 피부라도 버린다.
# 머리카락 가닥 사이로 보이는 피부 틈이 "주변보다 붉은 덩어리"로 잡히는 것을 막는다.
HAIR_EDGE_MARGIN_RATIO = 0.015

# 머리카락을 걷어낸 뒤 패치에 남은 피부 비율이 이 값 미만이면
# 그 부위는 가려진 것으로 보고 통째로 뺀다. (남은 틈새만으로는 통계가 불안정하다)
MIN_REGION_COVERAGE = 0.4

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

# ── 트러블 분석 영역 ─────────────────────────────────────────────────
# 기존 패치(REGIONS)는 얼굴의 약 4%만 덮어서 볼 아래쪽처럼 트러블이 잘 생기는 곳이 빠진다.
# 트러블은 볼을 크게 잡은 패치로 찾는다 (분석 면적 약 3배).
# 얼굴 전체 윤곽도 시험했지만 콧볼 옆·인중·수염 부위처럼 원래 붉거나 수염 사이로
# 피부가 보이는 곳이 대량으로 트러블로 잡혀 채택하지 않았다.
# 턱은 수염 때문에 오탐이 많아 기존 크기를 유지한다.
# 밝기·균일도·홍조는 얼굴 굴곡의 그늘이 섞이지 않도록 기존 패치(REGIONS)를 유지한다.
TROUBLE_REGIONS = (
    ("forehead", (10, 151), 0.07),
    ("left_cheek", (50,), 0.13),          # 볼 (기존 0.08 → 0.13)
    ("right_cheek", (280,), 0.13),
    ("left_lower_cheek", (187,), 0.09),   # 볼 아래쪽 (신규)
    ("right_lower_cheek", (411,), 0.09),
    ("nose", (4,), 0.05),
    ("chin", (152, 200), 0.05),
)


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


def _decode_full(image_bytes: bytes) -> np.ndarray:
    """바이트를 원본 해상도 그대로 BGR 이미지로 디코딩한다."""
    if not image_bytes:
        raise AnalysisError("이미지 데이터가 비어 있습니다", code=ErrorCode.IMAGE_EMPTY)

    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise AnalysisError(
            "이미지를 읽을 수 없습니다 (지원하지 않는 형식이거나 손상된 파일)",
            code=ErrorCode.IMAGE_UNREADABLE,
        )
    return image


def _shrink(image: np.ndarray) -> tuple[np.ndarray, float]:
    """긴 변을 MAX_IMAGE_SIDE로 줄인 축소본과 배율(축소본/원본)을 돌려준다."""
    longest = max(image.shape[:2])
    if longest <= MAX_IMAGE_SIDE:
        return image, 1.0
    scale = MAX_IMAGE_SIDE / longest
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA), scale


def _decode(image_bytes: bytes) -> np.ndarray:
    """디코딩 후 축소본을 돌려준다 (진단 스크립트 호환용)."""
    return _shrink(_decode_full(image_bytes))[0]


def _crop_face(
    image: np.ndarray, landmarks: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """원본에서 얼굴 부분만 잘라, 얼굴 너비가 ANALYSIS_FACE_WIDTH보다 크면 그 크기로 줄인다.

    landmarks는 원본 좌표다. 잘라낸 이미지 좌표로 옮긴 랜드마크를 함께 돌려준다.
    """
    height, width = image.shape[:2]
    face_width = float(np.ptp(landmarks[:, 0]))
    margin = face_width * FACE_CROP_MARGIN

    # 얼굴 랜드마크를 감싸는 상자 + 여유, 화면 밖은 잘라낸다
    x0 = max(0, int(landmarks[:, 0].min() - margin))
    y0 = max(0, int(landmarks[:, 1].min() - margin))
    x1 = min(width, int(np.ceil(landmarks[:, 0].max() + margin)))
    y1 = min(height, int(np.ceil(landmarks[:, 1].max() + margin)))
    crop = image[y0:y1, x0:x1]

    # 줄이기만 하고 확대는 하지 않는다.
    # 저화질 사진을 확대하면 JPEG 압축 흔적(8x8 블록)까지 커져서 삼각형·직선 모양의
    # 가짜 트러블로 잡힌다 (웹캠 표본: 2배 확대 시 52점, 원본 크기 21점).
    scale = min(1.0, ANALYSIS_FACE_WIDTH / face_width)
    if scale < 1.0:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    moved = (landmarks - np.array([x0, y0], dtype=np.float32)) * scale
    return crop, moved


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


def _region_masks(
    image: np.ndarray, landmarks: np.ndarray, regions_def: tuple = REGIONS
) -> dict[str, np.ndarray]:
    """부위별 원형 패치 마스크를 만든다. 기본은 이마·양볼·코·턱 5곳(REGIONS)."""
    height, width = image.shape[:2]
    face_width = float(np.ptp(landmarks[:, 0]))

    masks: dict[str, np.ndarray] = {}
    for name, indices, ratio in regions_def:
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


def _skin_reference_l(lab: np.ndarray, masks: dict[str, np.ndarray]) -> float:
    """그 사람의 기준 피부 밝기(L 중앙값)를 구한다. 양볼 우선, 없으면 코·턱."""
    for group in (SKIN_REFERENCE_REGIONS, SKIN_REFERENCE_FALLBACK):
        values = [lab[:, :, 0][masks[name] > 0] for name in group if name in masks]
        if values:
            return float(np.median(np.concatenate(values)))
    raise AnalysisError(
        "피부 기준 영역(볼·코·턱)을 찾을 수 없습니다", code=ErrorCode.SKIN_AREA_TOO_SMALL
    )


def _hair_zone(lab: np.ndarray, reference_l: float, face_width: float) -> np.ndarray:
    """머리카락으로 판단되는 영역(경계 여유 포함) 마스크를 만든다."""
    # 1) 기준 피부보다 훨씬 어두운 픽셀 = 머리카락 후보
    dark = (lab[:, :, 0] < reference_l * HAIR_MAX_L_RATIO).astype(np.uint8) * 255

    # 2) 모공·점·수염 같은 작은 어두운 점은 머리카락이 아니므로 제거 (열림 연산)
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    # 3) 머리카락 경계 주변까지 넓혀서, 가닥 사이 피부 틈을 함께 제외
    margin = max(1, int(round(face_width * HAIR_EDGE_MARGIN_RATIO)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * margin + 1, 2 * margin + 1))
    return cv2.dilate(dark, kernel)


def _build_skin_regions(
    image: np.ndarray, lab: np.ndarray, landmarks: np.ndarray, regions_def: tuple = REGIONS
) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    """부위별 피부 마스크와, 부위별 피부 노출 비율(coverage)을 돌려준다.

    앞머리 등으로 가려진 부분은 빼고, 가려진 비율이 크면 그 부위 전체를 뺀다.
    이마를 깐 사람은 이마가 포함되고, 덮은 사람은 보이는 부위만으로 분석된다.
    """
    face_width = float(np.ptp(landmarks[:, 0]))
    masks = _region_masks(image, landmarks, regions_def)

    # 머리카락 영역은 패치 바깥 기준(볼 밝기)으로 판정한다
    reference_l = _skin_reference_l(lab, masks)
    not_hair = cv2.bitwise_not(_hair_zone(lab, reference_l, face_width))

    regions: dict[str, np.ndarray] = {}
    coverage: dict[str, float] = {}
    for name, mask in masks.items():
        # 패치에서 머리카락 영역을 뺀 나머지
        visible = cv2.bitwise_and(mask, not_hair)
        ratio = np.count_nonzero(visible) / max(1, np.count_nonzero(mask))
        coverage[name] = ratio
        if ratio < MIN_REGION_COVERAGE:
            continue  # 대부분 가려졌으면 이 부위는 제외

        # 남은 픽셀 안에서 그늘·하이라이트 등 이상치를 MAD로 정제
        try:
            regions[name] = _refine_skin(lab, visible, min_pixels=100)
        except AnalysisError:
            continue

    if not regions:
        raise AnalysisError(
            "분석 가능한 피부 영역을 찾지 못했습니다", code=ErrorCode.SKIN_AREA_TOO_SMALL
        )
    return regions, coverage


def _trouble_area(image: np.ndarray, lab: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
    """트러블을 찾을 피부 마스크. 넓은 패치(TROUBLE_REGIONS)에 같은 정제 과정을 적용한다."""
    regions, _ = _build_skin_regions(image, lab, landmarks, TROUBLE_REGIONS)
    area = np.zeros(lab.shape[:2], dtype=np.uint8)
    for mask in regions.values():
        area = cv2.bitwise_or(area, mask)
    return area


# 기기별 고정 색 보정 이득 (B, G, R).
# 예전에는 사진 전체 평균색을 회색으로 맞추는 그레이월드 보정을 썼는데,
#  - 얼굴이 화면을 크게 채우거나 피부가 붉으면 그 붉은색을 '조명 색'으로 보고 지워버리고
#    (붉은 얼굴 표본: 홍조 지수 16.6 → 5.0, 100점 → 0점)
#  - 몸 방향만 바꿔도 배경이 바뀌어 홍조가 흔들렸다 (변동 2.9% → 11%).
# 그래서 사진마다 보정하지 않고, 기기(카메라)별로 한 번 정한 고정값을 쓴다.
# 실제 키오스크 기기(갤럭시북4 웹캠)에서 색상표를 찍어 값을 정하기 전까지는 1.0(보정 없음).
DEVICE_CHANNEL_GAINS = (1.0, 1.0, 1.0)   # 기본(phone) 프로필 값


# ── 카메라 프로필 ───────────────────────────────────────────────────
# 카메라마다 색 처리 방식이 달라서, 같은 사람이라도 홍조 지수가 크게 다르다
# (같은 사람: 휴대폰 약 9.5, 720p 웹캠 2.2~2.5 — 웹캠은 피부를 거의 회색으로 기록함).
# 그래서 기기별 보정값을 프로필로 묶어 두고 설정(SKIN_CAMERA_PROFILE)으로 고른다.
# 새 기기를 쓰려면 그 기기로 찍은 표본으로 값을 정해 프로필을 하나 추가한다.
@dataclass(frozen=True)
class CameraProfile:
    """기기(카메라)별 보정값 묶음."""

    description: str
    channel_gains: tuple[float, float, float]  # 고정 색 보정 이득 (B, G, R)
    redness_range: tuple[float, float]         # 홍조 지수 lo → 0점, hi → 100점
    color_check: bool                          # 홍조 지수가 지나치게 낮으면 측정 불가로 돌려보낼지


CAMERA_PROFILES: dict[str, CameraProfile] = {
    # 휴대폰 사진으로 맞춘 기본값 (피부가 깨끗한 사람 약 9.5 → 40점대)
    "phone": CameraProfile(
        description="휴대폰 카메라 (기본값)",
        channel_gains=DEVICE_CHANNEL_GAINS,
        redness_range=REDNESS_RANGE,
        color_check=True,
    ),
    # 720p 웹캠 임시값. 표본이 1명·2장(Logitech)뿐이라 반드시 다시 맞춰야 한다.
    # 웹캠이 색을 휴대폰의 약 1/4로 바래게 기록하는 것(홍조 지수 2.3 / 9.5, 채도 5.5% / 27.8%)을
    # 근거로 phone 범위에 0.24를 곱해 정했다 → 같은 사람이 휴대폰과 비슷한 40점대로 나온다.
    "webcam": CameraProfile(
        description="720p 웹캠 임시값 (Logitech 1인 2장 기준, 재보정 필요)",
        channel_gains=(1.0, 1.0, 1.0),
        redness_range=(1.5, 3.5),
        color_check=True,
    ),
}
DEFAULT_CAMERA_PROFILE = "phone"


def get_camera_profile(name: str | None) -> CameraProfile:
    """이름으로 카메라 프로필을 찾는다. 없는 이름이면 설정 오류로 알린다."""
    key = (name or DEFAULT_CAMERA_PROFILE).strip().lower()
    if key not in CAMERA_PROFILES:
        raise AnalysisError(
            f"알 수 없는 카메라 프로필입니다: {name} (사용 가능: {', '.join(CAMERA_PROFILES)})",
            code=ErrorCode.CONFIG_INVALID,
            detail={"profile": name, "available": list(CAMERA_PROFILES)},
        )
    return CAMERA_PROFILES[key]


def _white_balance(image: np.ndarray) -> np.ndarray:
    """이미지 전체 기준 그레이월드 보정을 적용한 BGR 이미지를 돌려준다.

    기준을 피부 영역으로 잡으면 피부 평균색이 회색으로 강제되어
    홍조 신호가 통째로 사라진다. 그래서 화면 전체를 기준으로 삼는다.
    절대 밝기까지 맞추지는 않으므로, 촬영 가이드(조명 조건)는 여전히 필요하다.
    """
    return _apply_gains(image, _gray_world_gains(image))


def _gray_world_gains(image: np.ndarray) -> np.ndarray:
    """그레이월드 보정의 채널별 이득(B, G, R)을 계산한다."""
    means = np.array(cv2.mean(image)[:3])  # B, G, R
    target = float(np.mean(means))
    return np.where(means > 1.0, target / np.maximum(means, 1.0), 1.0).astype(np.float32)


def _apply_gains(image: np.ndarray, gains: np.ndarray) -> np.ndarray:
    """채널별 이득을 곱한 BGR 이미지를 돌려준다."""
    balanced = image.astype(np.float32) * gains.reshape(1, 1, 3)
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


def _redness(
    index_map: np.ndarray, patches: np.ndarray, redness_range: tuple[float, float] = REDNESS_RANGE
) -> tuple[int, float]:
    mean_index = cv2.mean(index_map, mask=patches)[0]
    return _linear_score(mean_index, *redness_range), mean_index


def _outer_edge_band(skin: np.ndarray, band_px: int) -> np.ndarray:
    """피부 영역의 바깥 테두리 띠(두께 band_px)를 돌려준다.

    피부 마스크 안쪽의 구멍(이상치 제거로 빠진 진한 반점 중심 등)은 채운 뒤 계산한다.
    구멍 둘레까지 '가장자리'로 치면 진짜 반점이 경계 효과로 오인되어 빠지기 때문이다.
    """
    filled = np.zeros_like(skin)
    contours, _ = cv2.findContours(skin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(filled, contours, -1, 255, thickness=-1)  # 바깥 윤곽만 채움 → 구멍 메움
    inner = cv2.erode(filled, np.ones((3, 3), np.uint8), iterations=band_px)
    return (skin > 0) & (inner == 0)


def _trouble(
    index_map: np.ndarray, skin: np.ndarray, face_width: float
) -> tuple[int, float, float]:
    """평소 질감보다 유독 붉은 '덩어리'의 면적 비율로 트러블을 추정한다.

    임계값을 그 사진의 질감 변동폭에 맞춰 잡으므로, 촬영 밝기에 따라
    같은 피부가 다르게 판정되는 문제를 줄인다.
    """
    # 픽셀 단위 센서 노이즈 완화 (실수 상태에서 먼저 처리한다)
    blur = max(3, int(round(face_width * TROUBLE_BLUR_RATIO)) | 1)  # 홀수 커널
    smooth = cv2.GaussianBlur(index_map.astype(np.float32), (blur, blur), 0)

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

    # 고정 임계값 (피부결이 거칠수록 올라가던 적응형 임계값은 여드름을 놓쳐서 제거)
    threshold = TROUBLE_THRESHOLD * TROUBLE_INDEX_GAIN

    candidate = ((deviation > threshold) & (skin > 0)).astype(np.uint8)

    # 지름이 기준 미만인 조각은 노이즈로 보고 버린다
    min_diameter = max(2.0, face_width * TROUBLE_MIN_BLOB_RATIO)
    min_area = max(4, int(np.pi / 4 * min_diameter**2))

    # 피부 영역 가장자리 띠 (경계 바깥의 그늘·수염 때문에 생기는 가짜 덩어리 판별용)
    band_px = max(2, int(round(face_width * TROUBLE_EDGE_BAND_RATIO)))
    edge_band = _outer_edge_band(skin, band_px)

    count, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, connectivity=8)
    blemish_px = 0
    for i in range(1, count):  # 0번은 배경
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < min_area:
            continue  # 너무 작은 조각은 노이즈
        # 덩어리 대부분이 가장자리 띠에 있으면 경계 효과로 보고 제외
        edge_share = np.count_nonzero(edge_band & (labels == i)) / area
        if edge_share >= TROUBLE_MAX_EDGE_SHARE:
            continue
        blemish_px += area

    ratio = blemish_px / float(np.count_nonzero(skin))
    return _linear_score(ratio, *TROUBLE_RANGE), ratio, threshold / TROUBLE_INDEX_GAIN


def _cheek_l_ratio(lab: np.ndarray, regions: dict[str, np.ndarray]) -> float | None:
    """양볼 밝기 비율 (어두운 쪽 / 밝은 쪽). 1.0이면 좌우가 고르게 비친 것.

    볼 하나라도 분석에서 빠졌으면 판단할 수 없으므로 None을 돌려준다.
    """
    if "left_cheek" not in regions or "right_cheek" not in regions:
        return None
    left = cv2.mean(lab[:, :, 0], mask=regions["left_cheek"])[0]
    right = cv2.mean(lab[:, :, 0], mask=regions["right_cheek"])[0]
    brighter = max(left, right)
    return min(left, right) / brighter if brighter > 0 else None


def _uniformity(
    lab: np.ndarray, skin: np.ndarray, face_width: float
) -> tuple[int, float, float]:
    """조명 흐름을 뺀 국소 밝기 편차의 역방향 점수. 고를수록 높다.

    1) 피부 픽셀만으로 밝기를 크게 블러해 '조명 흐름'(그늘·한쪽 조명)을 추정
       (피부 밖 픽셀이 섞이지 않도록 마스크로 나눠 주는 정규화 블러)
    2) 원래 밝기에서 조명 흐름을 빼면 얼룩·잡티 같은 국소 변화만 남는다
    3) 남은 값의 표준편차가 클수록 고르지 않다

    돌려주는 값: (점수, 조명 제거 후 표준편차, 참고용 예전 방식 표준편차)
    """
    lightness = lab[:, :, 0].astype(np.float32)
    mask = (skin > 0).astype(np.float32)
    sigma = max(1.0, face_width * UNIFORMITY_FLATTEN_SIGMA_RATIO)

    # 피부 영역만의 가중 평균 블러 = 조명 흐름
    weighted = cv2.GaussianBlur(lightness * mask, (0, 0), sigma)
    weight = cv2.GaussianBlur(mask, (0, 0), sigma)
    illumination = weighted / np.maximum(weight, 1e-3)

    residual = (lightness - illumination)[skin > 0]
    std_flat = float(residual.std())
    std_raw = float(lightness[skin > 0].std())  # 예전 방식 (비교용으로만 기록)

    unevenness = _linear_score(std_flat, *UNIFORMITY_STD_RANGE)
    return _clamp(100 - unevenness), std_flat, std_raw


class PreparedFace(NamedTuple):
    """분석 준비가 끝난 얼굴 이미지 묶음."""

    image: np.ndarray        # 잘라낸 얼굴 (원본 색, BGR)
    landmarks: np.ndarray    # 잘라낸 이미지 좌표의 랜드마크
    balanced: np.ndarray     # 화이트밸런스 적용본 (BGR)
    lab: np.ndarray          # balanced의 Lab 변환
    face_width: float        # 분석 해상도의 얼굴 너비 (최대 ANALYSIS_FACE_WIDTH)
    preview_face_width: float  # 축소본(긴 변 MAX_IMAGE_SIDE)에서의 얼굴 너비
    source_face_width: float   # 원본 사진에서의 얼굴 너비


def _prepare_face(
    image_bytes: bytes,
    *,
    min_face_width: int = DEFAULT_MIN_FACE_WIDTH,
    channel_gains: tuple[float, float, float] = DEVICE_CHANNEL_GAINS,
) -> PreparedFace:
    """디코딩 → 축소본에서 얼굴 찾기 → 원본에서 얼굴만 잘라 분석 해상도로 맞추기."""
    full = _decode_full(image_bytes)
    preview, scale = _shrink(full)
    preview_landmarks = _detect_landmarks(preview)
    preview_face_width = float(np.ptp(preview_landmarks[:, 0]))

    # 얼굴이 너무 작으면 트러블 탐지가 둔해져 점수를 신뢰할 수 없다
    # (기준은 기존과 같이 축소본 기준 너비로 판단한다)
    if preview_face_width < min_face_width:
        raise AnalysisError(
            f"얼굴이 너무 작게 나왔습니다 (너비 {preview_face_width:.0f}px, 최소 {min_face_width}px). "
            "얼굴이 화면에 더 크게 들어오도록 가까이에서 촬영해주세요.",
            code=ErrorCode.FACE_TOO_SMALL,
            detail={"face_width_px": round(preview_face_width, 1), "required_px": min_face_width},
        )

    # 색 보정은 사진마다 계산하지 않고 카메라 프로필의 고정값을 쓴다
    gains = np.array(channel_gains, dtype=np.float32)

    # 원본 좌표로 옮긴 랜드마크로 얼굴만 잘라낸다 (크면 ANALYSIS_FACE_WIDTH로 축소)
    source_landmarks = preview_landmarks / scale
    image, landmarks = _crop_face(full, source_landmarks)
    balanced = _apply_gains(image, gains)
    lab = cv2.cvtColor(balanced, cv2.COLOR_BGR2LAB)

    return PreparedFace(
        image=image,
        landmarks=landmarks,
        balanced=balanced,
        lab=lab,
        face_width=float(np.ptp(landmarks[:, 0])),
        preview_face_width=preview_face_width,
        source_face_width=preview_face_width / scale,
    )


# ── 공개 함수 ───────────────────────────────────────────────────────


def analyze_image_detail(
    image_bytes: bytes,
    *,
    min_face_width: int = DEFAULT_MIN_FACE_WIDTH,
    camera_profile: str = DEFAULT_CAMERA_PROFILE,
) -> tuple[dict[str, int], dict[str, float]]:
    """지표 점수 4개와, 정규화 전 원시값을 함께 돌려준다.

    원시값에는 부위별 측정치도 담긴다. 정규화 구간을 조정할 때와,
    "볼이 유독 붉다" 같은 부위별 안내를 만들 때 쓴다.
    """
    profile = get_camera_profile(camera_profile)  # 기기별 보정값 (색 보정·홍조 범위)
    face = _prepare_face(
        image_bytes, min_face_width=min_face_width, channel_gains=profile.channel_gains
    )
    image, landmarks, balanced, lab = face.image, face.landmarks, face.balanced, face.lab
    face_width = face.face_width  # 분석 해상도 기준 (최대 ANALYSIS_FACE_WIDTH)

    # 부위별 패치 → 머리카락으로 가려진 부분 제외 → 그늘·하이라이트 정제
    # 가려진 부위는 통째로 빠지므로, 이마를 깐 사람만 이마가 포함된다
    regions, coverage = _build_skin_regions(image, lab, landmarks)

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

    # 조명이 한쪽으로 치우치면 균일도·밝기가 피부가 아니라 조명을 재게 된다
    cheek_ratio = _cheek_l_ratio(lab, regions)
    if cheek_ratio is not None and cheek_ratio < MIN_CHEEK_L_RATIO:
        raise AnalysisError(
            f"조명이 한쪽으로 치우쳐 있습니다 (양볼 밝기 비율 {cheek_ratio:.3f}, "
            f"최소 {MIN_CHEEK_L_RATIO:.2f}). "
            "빛이 얼굴 정면에서 비치도록 방향을 바꿔 다시 촬영해주세요.",
            code=ErrorCode.LIGHTING_UNEVEN,
            detail={
                "cheek_l_ratio": round(cheek_ratio, 4),
                "left_cheek_l": round(cv2.mean(lab[:, :, 0], mask=regions["left_cheek"])[0], 1),
                "right_cheek_l": round(cv2.mean(lab[:, :, 0], mask=regions["right_cheek"])[0], 1),
                "required_min": MIN_CHEEK_L_RATIO,
            },
        )

    index_map = _redness_index(balanced)
    redness, mean_index = _redness(index_map, red_mask, profile.redness_range)

    # 홍조 지수가 보정 범위보다 지나치게 낮으면 피부색이 아니라 카메라·조명 문제다.
    # 0점(홍조 없음)으로 내보내지 않고 측정 불가로 돌려보낸다.
    red_lo, red_hi = profile.redness_range
    red_min_valid = red_lo - (red_hi - red_lo) * REDNESS_INVALID_MARGIN
    if profile.color_check and mean_index < red_min_valid:
        raise AnalysisError(
            f"피부색을 측정할 수 없습니다 (홍조 지수 {mean_index:.1f}, 측정 가능 최소 {red_min_valid:.1f}). "
            "카메라가 색을 회색·푸른빛으로 기록했거나 조명이 너무 어둡습니다. "
            "밝은 곳에서 다시 촬영하거나, 이 기기에 맞는 카메라 프로필(SKIN_CAMERA_PROFILE)을 설정해야 합니다.",
            code=ErrorCode.SKIN_COLOR_UNMEASURABLE,
            detail={
                "redness_index": round(mean_index, 2),
                "required_min": round(red_min_valid, 2),
                "camera_profile": camera_profile,
            },
        )
    # 트러블은 볼을 크게 잡은 넓은 패치에서 찾는다
    trouble_skin = _trouble_area(image, lab, landmarks)
    trouble, blemish_ratio, trouble_threshold = _trouble(index_map, trouble_skin, face_width)
    uniformity, std_l, std_l_raw = _uniformity(lab, skin, face_width)

    scores = {
        "redness": redness,
        "brightness": brightness,
        "trouble": trouble,
        "uniformity": uniformity,
    }
    raw = {
        "redness_index": round(mean_index, 2),     # 카메라 프로필의 홍조 범위 기준
        "mean_l_skin": round(mean_l, 2),           # BRIGHTNESS_RANGE 기준
        "saturated_ratio": round(saturated_ratio, 3),
        "blemish_ratio": round(blemish_ratio, 5),  # TROUBLE_RANGE 기준
        "trouble_threshold": round(trouble_threshold, 2),  # 적용된 임계값 (TROUBLE_THRESHOLD)
        "std_l_skin": round(std_l, 2),             # 조명 흐름 제거 후 편차 (UNIFORMITY_STD_RANGE 기준)
        "std_l_skin_raw": round(std_l_raw, 2),     # 참고: 예전 방식 편차 (조명 포함)
        "face_width_px": round(face.preview_face_width, 1),  # 축소본 기준 (최소 크기 검사용)
        "source_face_width_px": round(face.source_face_width, 1),  # 원본 사진에서의 얼굴 너비
        "skin_px": int(np.count_nonzero(skin)),                   # 패치(밝기·균일도·홍조) 픽셀
        "trouble_skin_px": int(np.count_nonzero(trouble_skin)),   # 트러블 분석 영역 픽셀
        "regions_used": len(regions),              # 분석에 쓰인 부위 수 (최대 5)
    }
    # 양볼 밝기 비율 (MIN_CHEEK_L_RATIO 기준). 볼 하나가 빠졌으면 기록하지 않는다
    if cheek_ratio is not None:
        raw["cheek_l_ratio"] = round(cheek_ratio, 3)
    # 부위별 피부 노출 비율. MIN_REGION_COVERAGE 미만이면 그 부위는 제외된 것
    for name, ratio in coverage.items():
        raw[f"{name}_coverage"] = round(ratio, 2)
    # 부위별 측정치 (어느 부위가 붉은지/어두운지 확인용)
    for name, mask in regions.items():
        raw[f"{name}_idx"] = round(cv2.mean(index_map, mask=mask)[0], 2)
        raw[f"{name}_l"] = round(cv2.mean(lab[:, :, 0], mask=mask)[0], 2)

    return scores, raw


def analyze_image(
    image_bytes: bytes,
    *,
    min_face_width: int = DEFAULT_MIN_FACE_WIDTH,
    camera_profile: str = DEFAULT_CAMERA_PROFILE,
) -> dict[str, int]:
    """사진에서 지표 점수 4개를 산출한다."""
    scores, _ = analyze_image_detail(
        image_bytes, min_face_width=min_face_width, camera_profile=camera_profile
    )
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
