"""필터를 통과한 전체 후보에 적용하는 API/오프라인 공용 순위 정책."""
from collections import Counter
from dataclasses import dataclass

from app.schemas.cosmetic import CosmeticRecommendationItem, MetricCode, RankingMode

# 현재 규칙의 밝기/균일도는 색소 관련 나이아신아마이드 근거를 공유한다.
# 논문 URL 개수를 세거나 이를 임상 근거의 강도로 취급하지 않는다.
GROUPS = {"moisture": "hydration", "redness": "redness", "brightness": "pigmentation",
          "trouble": "blemish", "uniformity": "pigmentation"}
POLICY_VERSION = "cosmetic-ranking-v1"
RANKING_BASES = {
    "metric_count": "매칭 지표 수 → 세트 의심 후순위 → 제품 ID",
    "concern_groups": "매칭 고민 그룹 수(밝기·균일도 통합) → 세트 의심 후순위 → 제품 ID",
    "explicit_priority": "지정 고민 매칭 여부 → 매칭 고민 그룹 수(밝기·균일도 통합) → 세트 의심 후순위 → 제품 ID",
}


@dataclass(frozen=True)
class RankedCandidate:
    product: CosmeticRecommendationItem
    rank: int
    group_count: int
    priority_matched: bool
    tie_count: int


def rank_candidates(candidates: list[CosmeticRecommendationItem], mode: RankingMode,
                    *, priority: MetricCode | None = None,
                    scorable_metrics: frozenset[str] = frozenset()) -> list[RankedCandidate]:
    """임의 가중치 없이 정렬한다. 입력 후보/기존 점수/설명을 수정하지 않는다.

    concern_groups는 밝기·균일도를 하나의 고민 그룹으로 세는 설계 가설이다.
    explicit_priority는 사용자가 지정한 평가 가능한 개선 지표를 먼저 만족시킨다.
    그 외는 그룹 수, 세트 여부, ID 순. 자동으로 가장 심각한 지표를 추측하지 않는다.
    호출자는 반드시 동일 요청의 필터를 통과한 전체 후보를 전달해야 한다.
    """
    if mode not in {"metric_count", "concern_groups", "explicit_priority"}:
        raise ValueError("알 수 없는 순위 정책")
    if mode == "explicit_priority":
        if priority not in GROUPS or priority not in scorable_metrics:
            raise ValueError("우선 고민은 평가 가능한 개선 지표 중에서 명시적으로 지정해야 합니다.")
    elif priority is not None:
        raise ValueError("우선 고민은 explicit_priority 정책에서만 사용합니다.")
    if len({p.product_id for p in candidates}) != len(candidates):
        raise ValueError("중복 제품 ID")
    features = {}
    for item in candidates:
        metrics = {m.metric_code for m in item.matches}
        if not metrics or len(metrics) != len(item.matches) or item.match_count != len(metrics):
            raise ValueError("후보의 매칭 지표/점수가 일치하지 않습니다.")
        groups = len({GROUPS[m] for m in metrics})
        preferred = priority in metrics if priority is not None else False
        key = ((-item.match_count,) if mode == "metric_count" else
               (-groups,) if mode == "concern_groups" else (-int(preferred), -groups))
        features[item.product_id] = (key + (item.bundle_suspected,), groups, preferred)
    ties = Counter(f[0] for f in features.values())
    ordered = sorted(candidates, key=lambda p: (*features[p.product_id][0], p.product_id))
    return [RankedCandidate(p, i, features[p.product_id][1], features[p.product_id][2],
                            ties[features[p.product_id][0]]) for i, p in enumerate(ordered, 1)]
