"""피부톤 조합(밝기 3단계 × 언더톤 3종)별 메이크업 색 계열 추천표.

제품 매칭이 아니라 색 계열 안내다. 성분 기반 화장품 추천과는 완전히 독립이다.
배정 근거는 퍼스널 컬러 이론의 일반적 색 배치이며, 임상 검증 자료가 아니므로
결과에는 항상 참고용 안내 문구(NOTICES)를 함께 내보낸다.

쿠션 '호수'는 정확한 호수 판정이 아니라 범위 안내다. 사진 기반 밝기 단계는
조명·기기에 따라 흔들릴 수 있어 한 호수를 찍지 않는다.
"""

from __future__ import annotations

from app.services.skin_tone import BRIGHTNESS_LEVELS, UNDERTONES

# (밝기 단계, 언더톤) → 색 계열 추천
PALETTES: dict[tuple[str, str], dict] = {
    ("bright", "warm"): {
        "tone_name": "밝은 웜톤",
        "cushion": "17~21호 범위 · 황조(옐로 베이스)",
        "lip": ["코랄", "피치", "살구"],
        "blush": ["피치", "애프리콧"],
        "eye": ["샴페인 골드", "베이지 브라운"],
        "point": "노란 기가 도는 밝은 피부라 골드·피치 계열이 혈색을 자연스럽게 살려줘요.",
    },
    ("bright", "neutral"): {
        "tone_name": "밝은 뉴트럴톤",
        "cushion": "17~21호 범위 · 뉴트럴 베이스",
        "lip": ["로즈 코랄", "MLBB 핑크베이지"],
        "blush": ["살구 핑크", "연한 코랄"],
        "eye": ["베이지", "로즈 브라운"],
        "point": "웜·쿨 어느 쪽에도 치우치지 않아 연한 색은 대부분 무난하게 어울려요.",
    },
    ("bright", "cool"): {
        "tone_name": "밝은 쿨톤",
        "cushion": "17~21호 범위 · 핑크조(핑크 베이스)",
        "lip": ["핑크", "로즈", "라즈베리"],
        "blush": ["라벤더 핑크", "로지 핑크"],
        "eye": ["쿨 핑크", "모브", "실버 베이지"],
        "point": "붉은 기가 도는 밝은 피부라 핑크·모브 계열이 얼굴을 맑아 보이게 해요.",
    },
    ("medium", "warm"): {
        "tone_name": "중간 웜톤",
        "cushion": "21~23호 범위 · 황조(옐로 베이스)",
        "lip": ["오렌지 브라운", "코랄 베이지"],
        "blush": ["베이지 코랄", "연한 테라코타"],
        "eye": ["웜 브라운", "카멜", "브론즈"],
        "point": "노란 기의 중간 피부라 브라운·카멜 계열이 차분하게 어울려요.",
    },
    ("medium", "neutral"): {
        "tone_name": "중간 뉴트럴톤",
        "cushion": "21~23호 범위 · 뉴트럴 베이스",
        "lip": ["로즈 브라운", "말린 장미"],
        "blush": ["모브 피치"],
        "eye": ["뉴트럴 브라운"],
        "point": "치우침이 없는 중간 피부라 로즈 브라운 계열이 실패가 적어요.",
    },
    ("medium", "cool"): {
        "tone_name": "중간 쿨톤",
        "cushion": "21~23호 범위 · 핑크조(핑크 베이스)",
        "lip": ["플럼", "베리"],
        "blush": ["모브", "쿨 로즈"],
        "eye": ["그레이 브라운", "모브"],
        "point": "붉은 기의 중간 피부라 플럼·베리 계열이 또렷한 인상을 줘요.",
    },
    ("deep", "warm"): {
        "tone_name": "딥 웜톤",
        "cushion": "23호 이상 범위 · 황조(옐로 베이스)",
        "lip": ["브릭", "테라코타"],
        "blush": ["테라코타"],
        "eye": ["카퍼", "다크 브라운"],
        "point": "노란 기의 깊은 피부라 브릭·카퍼 계열이 피부와 잘 녹아들어요.",
    },
    ("deep", "neutral"): {
        "tone_name": "딥 뉴트럴톤",
        "cushion": "23호 이상 범위 · 뉴트럴 베이스",
        "lip": ["브라운 레드", "딥 말린 장미"],
        "blush": ["딥 피치"],
        "eye": ["다크 브라운"],
        "point": "치우침이 없는 깊은 피부라 브라운 레드 계열이 안정적으로 어울려요.",
    },
    ("deep", "cool"): {
        "tone_name": "딥 쿨톤",
        "cushion": "23호 이상 범위 · 핑크조(핑크 베이스)",
        "lip": ["버건디", "와인"],
        "blush": ["플럼"],
        "eye": ["애쉬 브라운", "플럼"],
        "point": "붉은 기의 깊은 피부라 버건디·와인 계열이 고급스러운 인상을 줘요.",
    },
}

# 항상 함께 내보내는 참고용 안내
NOTICES = [
    "사진 기반 참고용 분류예요. 조명과 카메라에 따라 결과가 달라질 수 있어요.",
    "쿠션 호수는 정확한 호수가 아니라 범위 안내예요. 구매 전 매장에서 직접 테스트해 보세요.",
]

# 신뢰도가 낮을 때(조명 치우침 등) 추가하는 안내
LOW_CONFIDENCE_NOTICE = "조명이 고르지 않아 정확도가 낮을 수 있어요. 빛이 얼굴 정면에서 비치는 곳에서 다시 찍으면 더 정확해요."

# 호수 추정이 범위를 벗어났을 때 (보정 필터·과노출·너무 어두운 사진)
OUT_OF_RANGE_NOTICE = "사진이 지나치게 밝거나 어둡게 처리되어 쿠션 호수가 정확하지 않을 수 있어요. 보정 없는 사진을 사용해 주세요."


# 판매 호수와 안내 범위 (skin_tone.SHADE_STEPS와 같은 값)
SHADE_STEPS = (13, 15, 17, 19, 21, 23, 25)


def cushion_text(shade: float, base_text: str, *, wide: bool = False) -> str:
    """추정 호수 → '약 23호 (21~25호 범위) · 뉴트럴 베이스'.

    - 가장 가까운 판매 호수(13·15·…·25)로 안내한다 (22호처럼 흔치 않은 호수를 피함)
    - 범위는 그 호수 ±1칸(2호), 신뢰도가 낮으면 ±2칸(4호). 13~25호 밖으로 나가지 않는다.
    - 13호보다 밝거나 25호보다 어두우면 '13호 이하' / '25호 이상'으로 안내한다.
    프론트(cushionFromAnalysis)는 '숫자~숫자호' 범위의 가운데를 호수로 쓴다.
    """
    nearest = min(SHADE_STEPS, key=lambda s: abs(s - shade))
    step = 4 if wide else 2
    lo, hi = max(SHADE_STEPS[0], nearest - step), min(SHADE_STEPS[-1], nearest + step)
    if shade < SHADE_STEPS[0] - 1:
        label = f"{SHADE_STEPS[0]}호 이하"
    elif shade > SHADE_STEPS[-1] + 1:
        label = f"{SHADE_STEPS[-1]}호 이상"
    else:
        label = f"약 {nearest}호"
    return f"{label} ({lo}~{hi}호 범위) · {base_text}"


def recommend(
    brightness_level: str,
    undertone: str,
    *,
    confidence: str = "high",
    cushion_shade: float | None = None,
    cushion_out_of_range: bool = False,
) -> dict:
    """피부톤 조합에 맞는 색 계열 추천과 안내 문구를 돌려준다.

    cushion_shade(추정 호수)가 있으면 쿠션 문구를 고정 범위 대신 그 호수 기준으로 만든다.
    """
    if brightness_level not in BRIGHTNESS_LEVELS or undertone not in UNDERTONES:
        raise ValueError(f"알 수 없는 피부톤 조합: {brightness_level}/{undertone}")
    palette = PALETTES[(brightness_level, undertone)]
    if cushion_shade is not None:
        base_text = palette["cushion"].split("·", 1)[1].strip()  # '황조(옐로 베이스)' 등 베이스 부분
        wide = confidence == "low" or cushion_out_of_range
        palette = {**palette, "cushion": cushion_text(cushion_shade, base_text, wide=wide)}
    notices = list(NOTICES)
    if cushion_out_of_range:
        notices.insert(0, OUT_OF_RANGE_NOTICE)
    elif confidence == "low":
        notices.insert(0, LOW_CONFIDENCE_NOTICE)
    return {"palette": palette, "notices": notices}
