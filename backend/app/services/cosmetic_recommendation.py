"""DB와 독립적인 추천 엔진: 검증 → 후보 필터 → 지표별 1점 → 최대 5개."""

from dataclasses import asdict, dataclass
import re
from urllib.parse import urlparse

from app.schemas.cosmetic import (
    CosmeticPreviewRequest, CosmeticPreviewResponse, CosmeticRecommendationItem,
    IngredientMatch, MetricAssessment, RecommendationStats, RuleExplanation,
)
from app.services.cosmetic_rules import METRICS, NOTICES, ENGINE_VERSION, SUPPORTED_CATEGORIES, normalize_name
from app.services.cosmetic_rule_types import RuleBundle

from app.services.cosmetic_usage import classify_usage
from app.services.cosmetic_explanations import explain_match, shared_evidence
from app.services.cosmetic_ranking import (
    rank_candidates, rank_daily_care_candidates, POLICY_VERSION, RANKING_BASES,
    DAILY_CARE_POLICY_VERSION, DAILY_CARE_RANKING_BASIS,
)
from app.services.cosmetic_pagination import paginate_ties


class RecommendationConfigurationError(ValueError):
    pass


class RecommendationInputError(ValueError):
    pass


@dataclass(frozen=True)
class MetricDefinition:
    code: str
    name: str
    higher_is_better: bool
    # (name, min_score, max_score)
    categories: tuple[tuple[str, int, int], ...]


@dataclass(frozen=True)
class ProductCandidate:
    product_id: int
    product_name: str
    brand_name: str
    category: str | None
    parse_status: str | None
    ingredients_raw: str | None
    ingredients: frozenset[str]
    image_url: str | None = None
    source_url: str | None = None


def assess_scores(request: CosmeticPreviewRequest, definitions: list[MetricDefinition]) -> list[MetricAssessment]:
    by_code = {d.code: d for d in definitions}
    if len(by_code) != len(definitions):
        raise RecommendationConfigurationError("중복된 지표 코드가 있습니다.")
    assessments = []
    for code, score in request.normalized_scores.model_dump().items():
        if score is None:
            continue
        definition = by_code.get(code)
        if definition is None or definition.higher_is_better != METRICS[code][1]:
            raise RecommendationConfigurationError(f"{code} 지표 정의가 없거나 점수 방향이 맞지 않습니다.")
        ranges = definition.categories
        if (not ranges or any(low < 0 or high > 100 or low > high for _, low, high in ranges)
                or any(sum(low <= n <= high for _, low, high in ranges) != 1 for n in range(101))
                or sum(name == "개선 필요" for name, _, _ in ranges) != 1):
            raise RecommendationConfigurationError(f"{code} 판정 구간의 누락·중복 또는 개선 필요 라벨을 확인하세요.")
        _, concern_low, concern_high = next(r for r in ranges if r[0] == "개선 필요")
        if ((definition.higher_is_better and (concern_low != 0 or concern_high == 100))
                or (not definition.higher_is_better and (concern_high != 100 or concern_low == 0))):
            raise RecommendationConfigurationError(f"{code} 개선 필요 구간이 점수 방향과 맞지 않습니다.")
        category = next(name for name, low, high in ranges if low <= score <= high)
        if isinstance(request.scores, list):
            supplied = next(s for s in request.scores if s.metric_code == code)
            if supplied.higher_is_better != definition.higher_is_better:
                raise RecommendationInputError(f"{code} 점수 방향이 현재 지표 정의와 다릅니다.")
            if supplied.category_name != category:
                raise RecommendationInputError(f"{code} 상태 라벨이 현재 판정 기준과 다릅니다. 분석 기준을 확인해 주세요.")
        assessments.append(MetricAssessment(
            code=code, name=definition.name, score=score, category=category,
            needs_improvement=category == "개선 필요",
        ))
    return assessments


def safe_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlparse(value.strip())
        if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username:
            return value.strip()
    except ValueError:
        pass
    return None


def recommend(
    request: CosmeticPreviewRequest,
    definitions: list[MetricDefinition],
    products: list[ProductCandidate],
    known_ingredients: set[str],
    *, rule_bundle: RuleBundle,
) -> CosmeticPreviewResponse:
    assessments = assess_scores(request, definitions)
    targets = {a.code: a for a in assessments if a.needs_improvement}
    known = {normalize_name(n): n for n in sorted(known_ingredients)}
    user_exclusions = {normalize_name(n) for n in request.excluded_ingredients}
    unknown = user_exclusions - known.keys()
    if unknown:
        raise RecommendationInputError("DB에서 찾을 수 없는 제외 성분: " + ", ".join(sorted(unknown)))
    exclusion_names = {known[n] for n in user_exclusions}
    notices = list(NOTICES)
    evidence = {e.code: e for e in rule_bundle.evidence}
    active = [r for r in sorted(rule_bundle.rules, key=lambda r: r.code) if r.status == "active"
              and r.metric in targets and r.category == targets[r.metric].category
              and (r.condition == "always" or request.avoid_redness_triggers)]
    if request.score_semantics == "photo_v1":
        # 평균 명도/명도 편차/붉은 반점 비율은 색소침착·면포 검출값이 아니다.
        unsupported = {"brightness", "uniformity", "trouble"}
        active = [r for r in active if r.metric not in unsupported]
        notices.append("사진의 밝기·명도 균일도·붉은 반점 점수는 색소침착·모공 막힘을 확인하지 않아 해당 성분 매칭을 보류합니다.")
    matching_rules = [r for r in active if r.effect == "match"]
    deferred = sorted(set(targets) - {r.metric for r in matching_rules})
    scorable = frozenset(set(targets) - set(deferred))
    if request.priority_metric is not None and request.priority_metric not in scorable:
        raise RecommendationInputError("우선 고민은 측정되어 개선 필요로 판정되고 활성 매칭 규칙이 있는 지표여야 합니다.")
    # 제품 부족/배제 조건을 우회하는 대체 추천이 아니다.
    # 개선 매칭 규칙 자체가 없는 경우에만 별도 탐색 경로를 사용한다.
    daily_care = not matching_rules
    daily_rules = [r for r in sorted(rule_bundle.rules, key=lambda r: r.code)
                   if r.status == "active" and r.metric == "moisture"
                   and r.category == "개선 필요" and r.effect == "match" and r.condition == "always"] if daily_care else []
    ranking_basis = DAILY_CARE_RANKING_BASIS if daily_care else RANKING_BASES[request.ranking_policy]
    policy_version = DAILY_CARE_POLICY_VERSION if daily_care else POLICY_VERSION
    recommendation_notice = (
        ("현재 측정값에 개선 필요 지표가 없어 일상 관리용 제품을 제안합니다. " if not targets else
         "개선 지표에 적용할 성분 매칭 규칙이 없어, 해당 고민 개선 추천과 별도로 일상 관리용 제품을 제안합니다. ")
        + "활성 보습 성분 규칙의 함유 여부로 고른 후보이며, 피부 상태에 대한 맞춤 효과나 제품의 효능을 확인한 것은 아닙니다."
    ) if daily_care else "개선 필요 지표에 연결된 성분을 함유한 후보 제품입니다."
    if request.normalized_scores.moisture is None:
        recommendation_notice += " 수분은 미측정이며, 건조하거나 충분하다고 추정하지 않습니다."
    notices = [n for n in notices if not n.startswith("동점은")]
    notices.append("정렬 기준: " + ranking_basis + ". ID는 적합도 점수가 아닌 동점 순서입니다.")
    if daily_care:
        notices.append("일상 관리 제안에는 개선 지표 점수를 부여하지 않습니다. 성분 종류가 많다고 우선하지 않으며 농도·제형과 개인 적합도는 미확인입니다.")
    if not daily_care and request.ranking_policy != "metric_count":
        notices.append("밝기·균일도를 한 고민 그룹으로 세는 프로젝트 정책입니다. 서로 같은 지표라는 임상 판정은 아닙니다.")
    for code in deferred:
        notices.append(f"{METRICS[code][0]} 지표에 적용할 활성 매칭 규칙이 없어 가점을 보류합니다.")

    def explain(rule):
        source = evidence[rule.evidence_code]
        return RuleExplanation(rule_code=rule.code, ingredient=rule.ingredient, effect=rule.effect,
                               evidence_url=source.url, evidence_summary=source.summary,
                               limitations=source.limitations, rationale=rule.rationale)

    automatic_exclusions = [r for r in active if r.effect == "exclude"]
    exclusion_names.update(r.ingredient for r in automatic_exclusions)
    if automatic_exclusions:
        notices.append("조건부 배제는 주사 피부 관리 안내를 참고한 프로젝트 정책입니다. 홍조 점수로 질환을 진단하지 않습니다.")
    exclusions = {normalize_name(n) for n in exclusion_names}
    stats = RecommendationStats(total_products=len(products))
    ranked = []
    for product in products:
        if (product.category not in SUPPORTED_CATEGORIES
                or (request.category is not None and product.category != request.category)):
            stats.unsupported_category += 1
            continue
        if (product.parse_status != "normalized" or not product.ingredients
                or not (product.ingredients_raw or "").strip()):
            stats.incomplete_ingredients += 1
            continue
        usage_mode, usage_basis = classify_usage(product.product_name)
        if usage_mode != "leave_on_candidate":
            stats.excluded_by_usage += 1
            continue
        ingredient_names = {normalize_name(n): n for n in sorted(product.ingredients)}
        if exclusions.intersection(ingredient_names):
            stats.excluded_by_ingredient += 1
            continue
        matches = []
        for code, assessment in targets.items():
            rules = [r for r in matching_rules if r.metric == code and r.usage_scope == usage_mode
                     and normalize_name(r.ingredient) in ingredient_names]
            if rules:
                matches.append(IngredientMatch(
                    metric_code=code, metric_name=assessment.name,
                    ingredients=sorted({ingredient_names[normalize_name(r.ingredient)] for r in rules}),
                    evidence_urls=sorted({evidence[r.evidence_code].url for r in rules}),
                    rule_details=[explain(r) for r in sorted(rules, key=lambda r: r.code)],
                    interpretation=explain_match(code),
                ))
        care_rules = [r for r in daily_rules if r.usage_scope == usage_mode
                      and normalize_name(r.ingredient) in ingredient_names]
        care_ingredients = sorted({ingredient_names[normalize_name(r.ingredient)] for r in care_rules})
        if daily_care and not care_rules:
            stats.no_daily_care_ingredient += 1
            continue
        if not daily_care and not matches:
            stats.no_matching_metric += 1
            continue
        bundle = bool(re.search(r"세트|기획|듀오|더블|\d\s*\+\s*\d", product.product_name))
        ranked.append(CosmeticRecommendationItem(
            rank=0, product_id=product.product_id, product_name=product.product_name,
            brand_name=product.brand_name, category=product.category,
            image_url=safe_url(product.image_url), source_url=safe_url(product.source_url),
            match_count=len(matches), matches=matches,
            daily_care_ingredients=care_ingredients,
            daily_care_rules=[explain(r) for r in care_rules],
            shared_evidence_groups=shared_evidence(matches),
            recommendation_reason=("일상 관리용 성분 함유: " + ", ".join(care_ingredients) if daily_care else
                                   " / ".join(f"{m.metric_name}: {', '.join(m.ingredients)} 함유" for m in matches)),
            bundle_suspected=bundle, usage_mode=usage_mode, usage_basis=usage_basis,
        ))
    ordered = (rank_daily_care_candidates(ranked) if daily_care else
               rank_candidates(ranked, request.ranking_policy,
                               priority=request.priority_metric, scorable_metrics=scorable))
    stats.eligible_products = len(ranked)
    results, tie_groups, snapshot_token = paginate_ties(request, ordered, {
        "engine": ENGINE_VERSION, "policy": policy_version,
        "mode": "daily_care" if daily_care else "improvement",
        "rules": rule_bundle.model_dump(mode="json"), "definitions": [asdict(d) for d in definitions],
        "stats": stats.model_dump(),
    })
    if request.priority_metric is not None and ranked and not any(r.priority_matched for r in ordered):
        notices.append("지정한 우선 고민에 매칭되는 후보가 없어 나머지 고민 그룹 기준으로 정렬했습니다.")
    return CosmeticPreviewResponse(
        recommendation_mode="daily_care" if daily_care else "improvement",
        daily_care_reason=("no_improvement_targets" if not targets else "no_supported_matching_rules") if daily_care else None,
        recommendation_notice=recommendation_notice,
        score_basis=("일상 관리용 성분 함유 여부로 선정하며 개선 지표 점수를 부여하지 않음" if daily_care else
                     "개선 필요로 판정된 지표 중 성분 규칙과 매칭된 지표 수"),
        score_semantics=request.score_semantics,
        tie_groups=tie_groups, snapshot_token=snapshot_token,
        engine_version=ENGINE_VERSION, rule_version=rule_bundle.version, target_count=len(targets), assessments=assessments,
        ranking_policy=request.ranking_policy, ranking_policy_version=policy_version,
        ranking_basis=ranking_basis, priority_metric=request.priority_metric,
        scorable_target_count=len(targets) - len(deferred), deferred_metrics=deferred,
        missing_metrics=["moisture"] if request.normalized_scores.moisture is None else [],
        exclusion_details=[explain(r) for r in automatic_exclusions],
        applied_exclusions=sorted(exclusion_names), recommendations=results, stats=stats,
        notices=notices,
        empty_reason=("추천할 제품 데이터가 아직 없습니다." if not products else
                      "일상 관리 후보에 사용할 활성 보습 성분 규칙이 없습니다." if daily_care and not daily_rules else
                      "제품 종류·제외 성분·전성분 확인 조건과 일상 관리 성분 기준을 충족하는 제품이 없습니다." if daily_care else
                      "필터와 초기 성분 규칙을 충족하는 제품이 없습니다.") if not results else None,
    )
