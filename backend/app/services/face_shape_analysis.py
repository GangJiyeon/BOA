"""얼굴형 분석 로직 (공통 모듈)
사진에서 추출된 랜드마크 좌표를 받아 비율을 계산하고, 6종 얼굴형으로 분류한다.
헤어 추천은 사진 3장을 찍으므로, 3세트의 비율을 중앙값으로 취합해 최종 얼굴형을 정한다.

이 모듈은 DB나 API, MediaPipe를 전혀 모른다.
입력은 이미 추출된 좌표점(dict)이고, 출력도 순수 파이썬 값이다.
실제 사진 → 좌표 추출(MediaPipe 호출)은 이 모듈 밖에서 처리해서 여기로 넘겨준다.

기대하는 랜드마크 포인트 형식 (2D 좌표, (x, y) 튜플):
    left_eye, right_eye       : 좌우 눈 중심 (roll 보정, 스케일 기준)
    forehead_left, forehead_right : 이마 폭 양 끝점
    cheek_left, cheek_right   : 광대(얼굴 최대 폭) 양 끝점
    jaw_left, jaw_right       : 턱선 양 끝점
    top                       : 이마 최상단(헤어라인)   
    chin                      : 턱 끝
    nose_base                 : 코 밑(하관 비율 계산용)
"""

import math
import statistics
from typing import Dict, List, Tuple, Any

Point = Tuple[float, float]

FACE_SHAPES = ["계란형", "둥근형", "사각형", "긴형", "하트형", "다이아몬드"]

REQUIRED_POINTS = [
    "left_eye", "right_eye",
    "forehead_left", "forehead_right",
    "cheek_left", "cheek_right",
    "jaw_left", "jaw_right",
    "top", "chin", "nose_base",
]

# 얼굴형별 "이상적인 비율" 프로필 (MVP 휴리스틱, 실측 데이터로 튜닝 필요)
# length_width: 세로/가로, forehead_cheek: 이마/광대, jaw_cheek: 턱/광대, lower_face: 하관/전체길이
FACE_SHAPE_PROFILES = {
    "계란형":    {"length_width": 1.45, "forehead_cheek": 0.90, "jaw_cheek": 0.80, "lower_face": 0.33},
    "둥근형":    {"length_width": 1.05, "forehead_cheek": 0.92, "jaw_cheek": 0.92, "lower_face": 0.30},
    "사각형":    {"length_width": 1.15, "forehead_cheek": 0.97, "jaw_cheek": 0.97, "lower_face": 0.32},
    "긴형":      {"length_width": 1.70, "forehead_cheek": 0.90, "jaw_cheek": 0.85, "lower_face": 0.36},
    "하트형":    {"length_width": 1.35, "forehead_cheek": 1.05, "jaw_cheek": 0.68, "lower_face": 0.30},
    "다이아몬드": {"length_width": 1.40, "forehead_cheek": 0.80, "jaw_cheek": 0.78, "lower_face": 0.32},
}


def _distance(p1: Point, p2: Point) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def check_quality_gate(
    yaw: float, pitch: float, roll: float,
    max_yaw: float = 15.0, max_pitch: float = 15.0, max_roll: float = 10.0,
) -> Tuple[bool, str]:
    """
    촬영 품질 게이트. 정면 각도(yaw/pitch/roll)가 임계값 안일 때만 통과.
    MediaPipe의 얼굴 변환 행렬에서 추정한 각도를 넘겨받는다고 가정한다.
    실패하면 (False, 사유)를 반환해서 재촬영 안내에 사용한다.
    """
    if abs(yaw) > max_yaw:
        return False, f"좌우 각도(yaw={yaw:.1f}°)가 기준({max_yaw}°)을 벗어났습니다. 정면을 봐주세요."
    if abs(pitch) > max_pitch:
        return False, f"상하 각도(pitch={pitch:.1f}°)가 기준({max_pitch}°)을 벗어났습니다. 고개를 들거나 숙이지 마세요."
    if abs(roll) > max_roll:
        return False, f"기울기(roll={roll:.1f}°)가 기준({max_roll}°)을 벗어났습니다. 고개를 기울이지 마세요."
    return True, "통과"


def normalize_points(points: Dict[str, Point]) -> Dict[str, Point]:
    """
    두 눈을 잇는 선을 수평으로 회전(roll 보정)한다.
    (참고: 이후 계산에 유클리드 거리를 쓰므로 회전 자체가 비율값을 바꾸진 않지만,
     좌우 대칭 랜드마크 오차를 줄이고 이후 영역 분할 등에 필요해 표준 절차로 유지한다.)
    """
    missing = [k for k in REQUIRED_POINTS if k not in points]
    if missing:
        raise ValueError(f"필수 랜드마크 포인트 누락: {missing}")

    lx, ly = points["left_eye"]
    rx, ry = points["right_eye"]
    angle = math.atan2(ry - ly, rx - lx)  # 눈 사이 선의 현재 기울기

    cos_a, sin_a = math.cos(-angle), math.sin(-angle)
    cx = (lx + rx) / 2
    cy = (ly + ry) / 2

    def rotate(p: Point) -> Point:
        x, y = p[0] - cx, p[1] - cy
        return (x * cos_a - y * sin_a + cx, x * sin_a + y * cos_a + cy)

    return {k: rotate(v) for k, v in points.items()}


def calculate_ratios(points: Dict[str, Point]) -> Dict[str, float]:
    """정규화된 랜드마크에서 얼굴형 판별용 4개 비율을 계산한다."""
    cheek_width = _distance(points["cheek_left"], points["cheek_right"])
    face_length = _distance(points["top"], points["chin"])

    if cheek_width == 0 or face_length == 0:
        raise ValueError("광대 폭 또는 얼굴 길이가 0입니다. 랜드마크 좌표를 확인하세요.")

    forehead_width = _distance(points["forehead_left"], points["forehead_right"])
    jaw_width = _distance(points["jaw_left"], points["jaw_right"])
    lower_face_length = _distance(points["nose_base"], points["chin"])

    return {
        "length_width": face_length / cheek_width,
        "forehead_cheek": forehead_width / cheek_width,
        "jaw_cheek": jaw_width / cheek_width,
        "lower_face": lower_face_length / face_length,
    }


def aggregate_median_ratios(ratios_list: List[Dict[str, float]]) -> Dict[str, float]:
    """3장(또는 N장)의 비율을 항목별 중앙값으로 취합한다."""
    if not ratios_list:
        raise ValueError("취합할 비율 데이터가 없습니다.")
    keys = ratios_list[0].keys()
    return {k: statistics.median(r[k] for r in ratios_list) for k in keys}


def score_face_shapes(ratios: Dict[str, float]) -> Dict[str, float]:
    """
    입력 비율과 각 얼굴형 프로필 간의 유사도를 계산해 6종 각각의 점수를 매긴다.
    점수는 전체 합이 1이 되도록 정규화되어, top1 점수를 곧 신뢰도로 사용할 수 있다.
    (프로필 수치는 MVP 휴리스틱이며 실측 데이터로 검증/튜닝이 필요하다)
    """
    inverse_distances = {}
    for shape, profile in FACE_SHAPE_PROFILES.items():
        squared_diff_sum = sum(
            (ratios[key] - profile[key]) ** 2 for key in profile
        )
        distance = math.sqrt(squared_diff_sum)
        inverse_distances[shape] = 1 / (distance + 1e-6)  # 거리가 가까울수록 큰 값

    total = sum(inverse_distances.values())
    return {shape: value / total for shape, value in inverse_distances.items()}


def classify_face_shape(scores: Dict[str, float]) -> Dict[str, Any]:
    """
    점수 딕셔너리에서 1위/2위 얼굴형과 신뢰도(1위 점수)를 뽑는다.
    1·2위 점수 차가 작으면(0.1 미만) 신뢰도가 낮다는 의미로 볼 수 있다.
    """
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top1_shape, top1_score = ranked[0]
    top2_shape, top2_score = ranked[1]

    return {
        "face_shape": top1_shape,
        "top2": top2_shape,
        "confidence": round(top1_score, 4),
        "score_gap": round(top1_score - top2_score, 4),
    }


def analyze_face_shape(
    landmark_sets: List[Dict[str, Point]],
    source: str = "triple",
) -> Dict[str, Any]:
    """
    전체 파이프라인: 랜드마크 세트 목록(1개 또는 3개) → 정규화 → 비율계산
    → (여러 장이면) 중앙값 취합 → 6종 점수화 → 최종 분류.

    source: "single"(사진 1장) 또는 "triple"(사진 3장). 공통 저장소에 이 값과
    함께 저장해서, 나중에 3장 촬영을 하면 triple 값으로 덮어쓰는 데 사용한다.

    반환값의 ratios는 models.hair.FaceAnalysis.ratios(JSONB)에 그대로 저장한다.
    top2는 models.hair.FaceAnalysis.top2(단일 문자열)에 맞춰 2위 얼굴형 이름 하나만 반환한다.
    """
    ratios_list = []
    for points in landmark_sets:
        normalized = normalize_points(points)
        ratios_list.append(calculate_ratios(normalized))

    final_ratios = aggregate_median_ratios(ratios_list) if len(ratios_list) > 1 else ratios_list[0]
    scores = score_face_shapes(final_ratios)
    classification = classify_face_shape(scores)

    return {
        "face_shape": classification["face_shape"],
        "top2": classification["top2"],
        "confidence": classification["confidence"],
        "source": source,
        "ratios": {k: round(v, 4) for k, v in final_ratios.items()},
        "all_scores": {k: round(v, 4) for k, v in scores.items()},
    }