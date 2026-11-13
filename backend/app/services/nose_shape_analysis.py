"""코 모양 축 판정 로직 (정면 메이크업 쉐딩용 입력 데이터)

목적: "코 모양을 하나로 분류"하는 게 아니라, 정면 사진 위에서 쉐딩을 넣을
다른 기능(메이크업 파트)이 참고할 수 있는 "코의 특징 정보"를 제공하는 것.

그래서 결과는 단일 라벨이 아니라 "해당하는 특징들의 리스트"로 반환한다.
(예: ["복코", "휜코"] — 콧끝이 넓으면서 동시에 콧대가 휜 경우 둘 다 해당 가능)
해당하는 특징이 하나도 없으면 ["보통"]으로 채워서 반환한다.

서로 독립된 3개 축으로 판정한다:
    - 폭   : 콧끝이 넓은지(복코)
    - 대칭 : 콧대가 좌우 중심축에서 벗어났는지(휜코)
    - 들림 : 코끝이 콧망울 선 대비 위/아래로 얼마나 치우쳤는지(들창코 / 화살코)
             → 콧망울 선보다 많이 올라가 있으면 들창코,
               많이 처져 있으면(콧날개는 위로, 코끝은 아래로 향해 화살표처럼
               보이는) 화살코 — 같은 축의 양쪽 극단으로 다룬다.

매부리코·낮은코처럼 콧대의 높낮이(깊이 정보)가 핵심인 유형은 제외했다.
정면 사진 한 장(또는 정면만 쓰는 메이크업 쉐딩)에서는 깊이(z)를 신뢰하기
어렵고, 애초에 정면 쉐딩에 필요한 정보도 아니기 때문이다.

이 모듈은 face_shape_analysis.py와 마찬가지로 DB·API·MediaPipe를 전혀
모른다. 입력은 이미 추출된 좌표점(dict)이고, 출력도 순수 파이썬 값이다.

기대하는 랜드마크 포인트 (landmark_extraction.LANDMARK_INDEX_MAP 기준):
    left_eye, right_eye       : 대칭축 계산 기준 (face_shape_analysis와 공유)
    forehead_left, forehead_right : 정규화 기준(얼굴 폭)
    nose_tip                  : 코끝
    nose_bridge_top           : 콧대 윗부분(미간 쪽)
    nose_base                 : 코 밑 (코끝 세로 길이 계산 기준)
    nostril_left, nostril_right : 좌우 콧망울(콧볼) 바깥쪽

보정 이력 (실측 라벨 샘플 기준, n이 적어 추가 데이터 모이면 재보정 필요):
    - 복코: "콧볼폭/얼굴폭" 하나만으로는 보통·복코 그룹이 겹쳐서 구분 안 됨
      → "콧볼폭/코끝세로길이"(코끝이 짧고 넓을수록 커지는 값)를 추가 기준으로
      넣고, 둘 중 하나만 넘어도(OR) 복코로 판정하도록 함. 재현율을 우선한
      선택이라, 보통인 사람을 복코로 잘못 태그하는 경우가 생길 수 있음.
    - 들창코/화살코: 원래 "화살코 = 콧볼 폭이 좁다"로 잡았었는데, 실측 라벨
      사진으로 확인해보니 화살코의 핵심은 폭이 아니라 "코끝이 콧망울 선보다
      아래로 처지는 것"(= upturn 값이 들창코와 반대로 아주 낮음)이었음.
      그래서 width 축에서 분리해, upturn 축의 반대쪽 극단으로 재정의함.
"""

import math
from typing import Dict, List, Tuple

Point = Tuple[float, float]

NOSE_REQUIRED_POINTS = [
    "left_eye", "right_eye",
    "forehead_left", "forehead_right",
    "nose_tip", "nose_bridge_top", "nose_base",
    "nostril_left", "nostril_right",
]

# 실측 라벨 샘플 기준으로 보정한 값 (보정 이력은 위 docstring 참고)
THRESHOLDS = {
    "width_wide": 0.38,       # 콧볼폭/얼굴폭 — 복코 판정 기준 1 (OR)
    "bulbous_ratio": 3.37,    # 콧볼폭/코끝세로길이 — 복코 판정 기준 2 (OR)
    "upturn_high": 0.108,     # 이상이면 들창코
    "upturn_low": 0.03,       # 이하면 화살코
    "symmetry": 0.03,         # 이상이면 휜코
}


def _distance(p1: Point, p2: Point) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def calculate_nose_ratios(points: Dict[str, Point]) -> Dict[str, float]:
    """정면 랜드마크에서 코 모양 축 판정용 비율들을 계산한다."""
    missing = [k for k in NOSE_REQUIRED_POINTS if k not in points]
    if missing:
        raise ValueError(f"코 모양 판정에 필요한 랜드마크 포인트 누락: {missing}")

    face_width = _distance(points["forehead_left"], points["forehead_right"])
    if face_width == 0:
        raise ValueError("얼굴 폭이 0입니다. 랜드마크 좌표를 확인하세요.")

    tip_width = _distance(points["nostril_left"], points["nostril_right"])
    tip_height = _distance(points["nose_tip"], points["nose_base"])

    eye_mid_x = (points["left_eye"][0] + points["right_eye"][0]) / 2
    symmetry_deviation = abs(points["nose_tip"][0] - eye_mid_x) / face_width

    nostril_mid_y = (points["nostril_left"][1] + points["nostril_right"][1]) / 2
    upturn = (nostril_mid_y - points["nose_tip"][1]) / tip_width if tip_width else 0.0

    return {
        "width_ratio": round(tip_width / face_width, 4),
        "bulbous_ratio": round(tip_width / tip_height, 4) if tip_height else 0.0,
        "symmetry_deviation": round(symmetry_deviation, 4),
        "upturn": round(upturn, 4),
    }


def classify_nose_axes(ratios: Dict[str, float]) -> List[str]:
    """3개 축을 독립적으로 판정해서, 해당하는 특징을 전부 리스트로 반환한다.

    - 복코: width_wide 또는 bulbous_ratio 둘 중 하나만 만족해도(OR) 태그
    - 들창코/화살코: upturn 하나의 축에서 양쪽 극단(elif)
    - 휜코: 대칭 축 단독
    여러 개 동시에 해당될 수 있다 (예: 복코 + 휜코).
    """
    tags = []

    if (ratios["width_ratio"] >= THRESHOLDS["width_wide"]
            or ratios["bulbous_ratio"] >= THRESHOLDS["bulbous_ratio"]):
        tags.append("복코")

    if ratios["upturn"] >= THRESHOLDS["upturn_high"]:
        tags.append("들창코")
    elif ratios["upturn"] <= THRESHOLDS["upturn_low"]:
        tags.append("화살코")

    if ratios["symmetry_deviation"] >= THRESHOLDS["symmetry"]:
        tags.append("휜코")

    return tags


def analyze_nose_shape(points: Dict[str, Point]) -> Dict[str, object]:
    """전체 파이프라인: 랜드마크 → 비율 계산 → 축별 판정.

    메이크업(쉐딩) 기능에 넘길 응답 형태.
    해당하는 특징이 하나도 없으면 ["보통"]으로 채워서 반환한다.
    """
    ratios = calculate_nose_ratios(points)
    tags = classify_nose_axes(ratios)
    if not tags:
        tags = ["보통"]
    return {
        "nose_tags": tags,
        "ratios": ratios,
    }