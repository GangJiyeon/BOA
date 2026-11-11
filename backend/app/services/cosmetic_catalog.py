"""현재 PostgreSQL 모델을 읽어 추천 엔진에 전달하는 어댑터. INSERT/UPDATE 없음."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cosmetic import Brand, Ingredient, Product, ProductIngredient
from app.models.skin import SkinMetric, SkinMetricCategory
from app.schemas.cosmetic import CosmeticPreviewRequest, CosmeticPreviewResponse
from app.services.cosmetic_rule_repository import load_database_rules
from app.services.cosmetic_recommendation import MetricDefinition, ProductCandidate, recommend


def preview_from_database(db: Session, request: CosmeticPreviewRequest) -> CosmeticPreviewResponse:
    rule_bundle = load_database_rules(db)
    categories = defaultdict(list)
    for row in db.scalars(select(SkinMetricCategory)).all():
        categories[row.metric_id].append((row.name, row.min_score, row.max_score))
    definitions = [
        MetricDefinition(m.code, m.name, m.higher_is_better, tuple(categories[m.id]))
        for m in db.scalars(select(SkinMetric)).all()
    ]
    known = {i.ingredient_id: i.ingredient_name for i in db.scalars(select(Ingredient)).all()}
    ingredients = defaultdict(set)
    for product_id, ingredient_id in db.execute(select(ProductIngredient.product_id, ProductIngredient.ingredient_id)):
        if ingredient_id in known:
            ingredients[product_id].add(known[ingredient_id])
    products = [
        ProductCandidate(
            p.product_id, p.product_name, brand_name, p.product_category,
            p.parse_status, p.ingredients_raw, frozenset(ingredients[p.product_id]),
            p.image_url, p.source_url,
        )
        for p, brand_name in db.execute(select(Product, Brand.brand_name).join(Brand, Product.brand_id == Brand.brand_id))
    ]
    auxiliary = None
    sensor_hydration = None
    if request.moisture_measurement_id is not None:
        from app.models.moisture import MoistureObservation
        from app.services.cosmetic_recommendation import RecommendationInputError
        row = db.scalar(select(MoistureObservation).where(
            MoistureObservation.measurement_id == request.moisture_measurement_id,
            MoistureObservation.analysis_id == request.moisture_analysis_id))
        if row is None:
            raise RecommendationInputError('해당 분석에 저장된 수분 측정이 없습니다.')
        from app.services.hydration_estimate import SUPPORTED_NORMALIZATIONS
        if row.payload.get('algorithm_version')=='skin-fixed-3s-v1' and row.payload.get('normalization_version') in SUPPORTED_NORMALIZATIONS:
            if not row.summary.get('used_for_scoring'):
                raise RecommendationInputError('수분 상태를 판정하지 못한 측정입니다.')
            from app.schemas.moisture import CompletedMoisture
            from app.services.moisture_normalization import normalize
            sensor_hydration=normalize(CompletedMoisture.model_validate(row.payload))
            # Canonicalize the presentation fields too, so changing a client UI
            # number cannot alter state, ranking, exclusions or pagination.
            if isinstance(request.scores,list):
                from app.schemas.cosmetic import AnalysisMetricScore
                moisture=AnalysisMetricScore(metric_code='moisture',metric_name='수분',
                    score=sensor_hydration['normalized_score'],
                    category_name=sensor_hydration['estimation_category'],higher_is_better=True)
                scores=[moisture]+[s for s in request.scores if s.metric_code!='moisture']
            else:
                scores=request.scores.model_copy(update={'moisture':sensor_hydration['normalized_score']})
            request=request.model_copy(update={'scores':scores})
        else:
            auxiliary = _legacy_auxiliary(row, request)
    return recommend(request, definitions, products, set(known.values()), rule_bundle=rule_bundle,
                     sensor_auxiliary=auxiliary, sensor_hydration=sensor_hydration)


def _legacy_auxiliary(row, request):
    from app.services.cosmetic_recommendation import RecommendationInputError
    if not row.summary.get('recommendation_eligible') or row.payload.get('algorithm_version') not in ('cheek-auto-v2', 'skin-auto-v3','skin-auto-v4','skin-auto-v5','skin-auto-v6'):
        raise RecommendationInputError('보조 추천에 사용할 수 없는 수분 측정입니다.')
    # Recompute from persisted samples, never accept a browser-provided score.
    from app.schemas.moisture import CompletedMoisture
    from app.services.cheek_signal import signal_statistics
    measured = CompletedMoisture.model_validate(row.payload)
    signal = signal_statistics(measured.baseline, [s.count for s in measured.samples], modern=measured.algorithm_version in ('skin-auto-v3','skin-auto-v4','skin-auto-v5','skin-auto-v6'), guarded=measured.algorithm_version in ('skin-auto-v4','skin-auto-v5','skin-auto-v6'), stationary=measured.algorithm_version == 'skin-auto-v6')
    if measured.algorithm_version in ('skin-auto-v4','skin-auto-v5','skin-auto-v6') and signal['resolution_limited']:
        raise RecommendationInputError('출력 분해능에 비해 반응이 작아 추천 반영을 보류합니다.')
    auxiliary = dict(measurement_id=row.measurement_id, analysis_id=row.analysis_id,
                     experimental_index=signal['experimental_index'], policy='skin-contact-fraction-tie-v1' if measured.algorithm_version in ('skin-auto-v3','skin-auto-v4','skin-auto-v5','skin-auto-v6') else 'cheek-aux-tie-v1',
                     applied=request.normalized_scores.moisture is None)
    return auxiliary
