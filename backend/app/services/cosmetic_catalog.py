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
    return recommend(request, definitions, products, set(known.values()), rule_bundle=rule_bundle)
