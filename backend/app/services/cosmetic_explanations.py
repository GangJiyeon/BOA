"""표현 전용. DB 접근, 함량 판정, 점수/필터 계산을 하지 않는다."""
from app.schemas.cosmetic import IngredientMatch, MatchInterpretation, MetricCode, SharedEvidenceGroup

METRIC_ASSUMPTIONS: dict[MetricCode, str] = {
    "moisture": "입력 수분 점수가 피부 수분 상태를 나타낸다는 개발용 가정입니다. 센서 보정과 임계값의 타당성을 검증한 것은 아닙니다.",
    "redness": "입력 홍조 점수를 피부의 붉은 정도로 해석하는 개발용 가정입니다. 원인이나 질환을 진단하지 않습니다.",
    "brightness": "밝기를 색소 관련 피부색 지표로 해석하는 개발용 가정입니다. 조명·노출에 따른 사진 밝기에는 그대로 적용할 수 없습니다.",
    "trouble": "트러블을 여드름·모공 막힘 관련 지표로 해석하는 개발용 가정입니다. 모든 피부 이상을 뜻하거나 여드름을 진단하지 않습니다.",
    "uniformity": "균일도를 색소 관련 피부 톤의 고른 정도로 해석하는 개발용 가정입니다. 피부 요철·모공·조명 균일도까지 설명하지 않습니다.",
}


def explain_match(metric: MetricCode) -> MatchInterpretation:
    return MatchInterpretation(
        match_basis="저장된 정규화 성분명과 활성 규칙의 성분명이 일치했습니다. 제조사 최신 전성분을 재검증한 결과는 아닙니다.",
        metric_assumption=METRIC_ASSUMPTIONS[metric],
        unverified_items=[
            "함량 표기와 연구 농도의 대응은 이번 추천에서 평가하지 않았습니다. 미표기는 0%를 뜻하지 않습니다.",
            "완제품의 제형·성분 특성·사용 조건이 연구 조건과 같은지 확인하지 않았습니다.",
            "개별 제품의 개선 효과와 사용자에게 안전한지는 검증하지 않았습니다.",
        ],
    )


def shared_evidence(matches: list[IngredientMatch]) -> list[SharedEvidenceGroup]:
    grouped: dict[str, set[MetricCode]] = {}
    for match in matches:
        for url in match.evidence_urls:
            grouped.setdefault(url, set()).add(match.metric_code)
    return [SharedEvidenceGroup(evidence_url=url, metric_codes=sorted(metrics))
            for url, metrics in sorted(grouped.items()) if len(metrics) > 1]
