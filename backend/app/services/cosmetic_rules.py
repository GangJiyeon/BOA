"""검토 가능한 초기 성분 규칙. 원문 일부 일치나 LLM 추론은 사용하지 않는다.

연구의 제형/농도와 수집 제품은 동일하지 않다. 이 규칙은 후보 탐색용이며
효능 확률, 치료 효과 또는 안전성 판정이 아니다. 근거와 한계는 docs 참고.
"""

import unicodedata

ENGINE_VERSION = "cosmetic-preview-v3.3"
METRICS = {
    "moisture": ("수분", True),
    "redness": ("홍조", False),
    "brightness": ("밝기", True),
    "trouble": ("트러블", False),
    "uniformity": ("균일도", True),
}
SUPPORTED_CATEGORIES = frozenset({"moisturizer", "serum", "toner"})


def normalize_name(value: str) -> str:
    """Unicode·대소문자·공백만 정규화. 유도체/부분 문자열을 같은 성분으로 보지 않음."""
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


NOTICES = (
    "제품명·종류로 사용 방식과 부위를 추정합니다. 워시오프·사용 방식 불명확·얼굴 추천 범위 미확인 제품은 제외하며, 제조사 사용법은 확인되지 않았습니다.",
    "개발용 추천 미리보기입니다. 입력 점수와 결과는 저장하지 않습니다.",
    "점수는 성분 규칙에 매칭된 지표 수이며, 제품 효능이나 효과 확률을 뜻하지 않습니다. 농도·제형은 확인되지 않았습니다.",
    "피부 판정 구간은 DB의 임시 개발 기준입니다. 사진 기반 점수 산출도 현재 더미 구현입니다.",
    "밝기·균일도는 같은 나이아신아마이드 근거를 공유할 수 있어 서로 독립적인 효과 점수가 아닙니다.",
    "동점은 기획·세트 의심 후순위, 이후 제품 ID 순입니다. ID는 효능·인기도·개인 적합도 순위가 아닙니다.",
    "전성분 정규화가 완료된 토너·세럼·보습제만 사용합니다. 제외 성분이 검출되지 않아도 안전성을 보증하지 않습니다.",
)
