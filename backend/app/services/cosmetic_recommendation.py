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
from app.services.cosmetic_ranking import rank_candidates, POLICY_VERSION, RANKING_BASES
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
    for code, score in request.scores.model_dump().items():
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
    matching_rules = [r for r in active if r.effect == "match"]
    deferred = sorted(set(targets) - {r.metric for r in matching_rules})
    scorable = frozenset(set(targets) - set(deferred))
    if request.priority_metric is not None and request.priority_metric not in scorable:
        raise RecommendationInputError("우선 고민은 측정되어 개선 필요로 판정되고 활성 매칭 규칙이 있는 지표여야 합니다.")
    notices = [n for n in notices if not n.startswith("동점은")]
    notices.append("정렬 기준: " + RANKING_BASES[request.ranking_policy] + ". ID는 적합도 점수가 아닌 동점 순서입니다.")
    if request.ranking_policy != "metric_count":
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
        if not matches:
            stats.no_matching_metric += 1
            continue
        bundle = bool(re.search(r"세트|기획|듀오|더블|\d\s*\+\s*\d", product.product_name))
        ranked.append(CosmeticRecommendationItem(
            rank=0, product_id=product.product_id, product_name=product.product_name,
            brand_name=product.brand_name, category=product.category,
            image_url=safe_url(product.image_url), source_url=safe_url(product.source_url),
            match_count=len(matches), matches=matches,
            shared_evidence_groups=shared_evidence(matches),
            recommendation_reason=" / ".join(f"{m.metric_name}: {', '.join(m.ingredients)} 함유" for m in matches),
            bundle_suspected=bundle, usage_mode=usage_mode, usage_basis=usage_basis,
        ))
    ordered = rank_candidates(ranked, request.ranking_policy,
                              priority=request.priority_metric, scorable_metrics=scorable)
    stats.eligible_products = len(ranked)
    results, tie_groups, snapshot_token = paginate_ties(request, ordered, {
        "engine": ENGINE_VERSION, "policy": POLICY_VERSION,
        "rules": rule_bundle.model_dump(mode="json"), "definitions": [asdict(d) for d in definitions],
        "stats": stats.model_dump(),
    })
    if request.priority_metric is not None and ranked and not any(r.priority_matched for r in ordered):
        notices.append("지정한 우선 고민에 매칭되는 후보가 없어 나머지 고민 그룹 기준으로 정렬했습니다.")
    return CosmeticPreviewResponse(
        tie_groups=tie_groups, snapshot_token=snapshot_token,
        engine_version=ENGINE_VERSION, rule_version=rule_bundle.version, target_count=len(targets), assessments=assessments,
        ranking_policy=request.ranking_policy, ranking_policy_version=POLICY_VERSION,
        ranking_basis=RANKING_BASES[request.ranking_policy], priority_metric=request.priority_metric,
        scorable_target_count=len(targets) - len(deferred), deferred_metrics=deferred,
        missing_metrics=["moisture"] if request.scores.moisture is None else [],
        exclusion_details=[explain(r) for r in automatic_exclusions],
        applied_exclusions=sorted(exclusion_names), recommendations=results, stats=stats,
        notices=notices,
        empty_reason=("현재 판정 기준에서 개선 필요로 분류된 지표가 없습니다." if not targets else
                      "개선 대상 지표에 활성 매칭 규칙이 없어 제품 추천을 보류합니다. 제품이 부적합하다는 뜻은 아닙니다." if not matching_rules else
                      "필터와 초기 성분 규칙을 충족하는 제품이 없습니다.") if not results else None,
    )
