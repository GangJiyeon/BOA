"""광대 폭 비율 산출 로직 (정면 메이크업 쉐딩용 입력 데이터)

숫자(비율)를 계산해서 넘긴다.

이 모듈도 face_shape_analysis.py와 마찬가지로 DB·API·MediaPipe를 전혀
모른다. 입력은 이미 추출된 좌표점(dict)이고, 출력도 순수 파이썬 값이다.

기대하는 랜드마크 포인트 (face_shape_analysis.REQUIRED_POINTS에 이미 포함된
것들이라, 별도 추출 없이 그대로 재사용 가능):
    cheek_left, cheek_right : 광대(얼굴 최대 폭) 양 끝점
    top, chin               : 얼굴 세로 길이(헤어라인~턱끝) 기준점
"""

import math
from typing import Dict, Tuple

Point = Tuple[float, float]

CHEEK_REQUIRED_POINTS = ["cheek_left", "cheek_right", "top", "chin"]


def _distance(p1: Point, p2: Point) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def calculate_cheek_ratio(points: Dict[str, Point]) -> Dict[str, float]:
    """광대 폭을 얼굴 세로 길이 대비 비율로 계산한다.

    세로 길이(top~chin) 기준으로 정규화해서, 사진 크기·촬영 거리와
    무관하게 "옆으로 퍼진 정도"만 비교할 수 있게 한다.
    """
    missing = [k for k in CHEEK_REQUIRED_POINTS if k not in points]
    if missing:
        raise ValueError(f"광대 폭 계산에 필요한 랜드마크 포인트 누락: {missing}")

    face_length = _distance(points["top"], points["chin"])
    if face_length == 0:
        raise ValueError("얼굴 길이가 0입니다. 랜드마크 좌표를 확인하세요.")

    cheek_width = _distance(points["cheek_left"], points["cheek_right"])

    return {
        "cheek_width_ratio": round(cheek_width / face_length, 4),
    }