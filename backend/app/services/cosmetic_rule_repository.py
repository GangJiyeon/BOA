"""DB 규칙 조회 및 명시적 시드. 추천 중에는 SELECT만 수행한다."""
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.models.cosmetic import Ingredient
from app.models.cosmetic_rule import CategoryIngredient, CosmeticRuleEvidence, CosmeticRuleSet
from app.models.skin import SkinMetric, SkinMetricCategory
from app.services.cosmetic_rule_types import DEFAULT_RULE_VERSION, Evidence, Rule, RuleBundle
from app.services.cosmetic_recommendation import RecommendationConfigurationError, MetricDefinition, assess_scores
from app.schemas.cosmetic import CosmeticPreviewRequest
from app.services.cosmetic_rules import normalize_name


def load_database_rules(db: Session, version: str = DEFAULT_RULE_VERSION) -> RuleBundle:
    try:
        rule_set = db.get(CosmeticRuleSet, version)
        if rule_set is None:
            raise RecommendationConfigurationError("성분 규칙 시드가 없습니다. scripts/seed_cosmetic_rules.py로 검사 후 --apply 하세요.")
        evidence = tuple(Evidence(**{field: getattr(e, field) for field in Evidence.model_fields})
                         for e in db.scalars(select(CosmeticRuleEvidence).where(CosmeticRuleEvidence.rule_version == version)))
        rows = db.execute(select(CategoryIngredient, SkinMetric.code, SkinMetricCategory.name, Ingredient.ingredient_name)
                          .join(SkinMetricCategory, CategoryIngredient.category_id == SkinMetricCategory.id)
                          .join(SkinMetric, SkinMetricCategory.metric_id == SkinMetric.id)
                          .join(Ingredient, CategoryIngredient.ingredient_id == Ingredient.ingredient_id)
                          .where(CategoryIngredient.rule_version == version)).all()
        rules = []
        for row, metric, category, ingredient in rows:
            data = {field: getattr(row, field) for field in Rule.model_fields if field not in {"metric", "category", "ingredient"}}
            rules.append(Rule(**data, metric=metric, category=category, ingredient=ingredient))
        bundle = RuleBundle(version=version, description=rule_set.description, evidence=evidence, rules=tuple(rules))
        if bundle.fingerprint() != rule_set.content_hash:
            raise RecommendationConfigurationError("성분 규칙이 해당 버전의 기록과 다릅니다. 부분 삭제·직접 수정을 확인하고 새 버전으로 관리하세요.")
        return bundle
    except (SQLAlchemyError, ValidationError) as exc:
        raise RecommendationConfigurationError("성분 규칙 DB 조회/검증 실패. DB 연결과 alembic current, 판정 구간 및 규칙 시드를 확인하세요.") from exc


def seed_rule_bundle(db: Session, bundle: RuleBundle, *, apply: bool = False) -> dict:
    """호출자가 트랜잭션을 소유. 검증을 전부 마친 후 새 버전만 INSERT한다."""
    names = defaultdict(list)
    for row in db.scalars(select(Ingredient)):
        names[normalize_name(row.ingredient_name)].append(row)
    categories = defaultdict(list)
    for category, code in db.execute(select(SkinMetricCategory, SkinMetric.code).join(SkinMetric)):
        categories[(code, category.name)].append(category)
    ranges = defaultdict(list)
    for rows in categories.values():
        for category in rows:
            ranges[category.metric_id].append((category.name, category.min_score, category.max_score))
    definitions = [MetricDefinition(m.code, m.name, m.higher_is_better, tuple(ranges[m.id]))
                   for m in db.scalars(select(SkinMetric))]
    assess_scores(CosmeticPreviewRequest(scores={code: 50 for code in ("moisture", "redness", "brightness", "trouble", "uniformity")}), definitions)
    resolved = []
    errors = []
    for rule in bundle.rules:
        ingredients = names[normalize_name(rule.ingredient)]
        target = categories[(rule.metric, rule.category)]
        if len(ingredients) != 1 or ingredients[0].ingredient_name != rule.ingredient:
            errors.append(f"{rule.code}: 정확한 성분명 {rule.ingredient} 누락 또는 중복")
        elif len(target) != 1:
            errors.append(f"{rule.code}: {rule.metric}/{rule.category} 판정 구간 누락 또는 중복")
        else:
            resolved.append((rule, target[0].id, ingredients[0].ingredient_id))
    if errors:
        raise RecommendationConfigurationError("시드 중단 (쓰기 없음): " + "; ".join(errors))
    existing = db.get(CosmeticRuleSet, bundle.version)
    if existing:
        stored = load_database_rules(db, bundle.version)
        if stored.fingerprint() != bundle.fingerprint():
            raise RecommendationConfigurationError("같은 버전의 다른 규칙은 덮어쓰지 않습니다. 새 버전을 만드세요.")
    summary = dict(version=bundle.version, rules=len(bundle.rules), evidence=len(bundle.evidence),
                   active_matches=sum(r.status == "active" and r.effect == "match" for r in bundle.rules),
                   active_exclusions=sum(r.status == "active" and r.effect == "exclude" for r in bundle.rules),
                   deferred=sum(r.status == "deferred" for r in bundle.rules),
                   action="unchanged" if existing else ("insert" if apply else "dry_run"))
    if existing or not apply:
        return summary
    db.add(CosmeticRuleSet(version=bundle.version, description=bundle.description, content_hash=bundle.fingerprint()))
    db.flush()
    for evidence in bundle.evidence:
        db.add(CosmeticRuleEvidence(rule_version=bundle.version, **evidence.model_dump()))
    db.flush()
    for rule, category_id, ingredient_id in resolved:
        data = rule.model_dump(exclude={"metric", "category", "ingredient"})
        db.add(CategoryIngredient(rule_version=bundle.version, category_id=category_id, ingredient_id=ingredient_id, **data))
    db.flush()
    # 이식 후 표현이 원본 규칙과 동일한지 검증한다. 실패하면 호출자의 transaction이 rollback.
    load_database_rules(db, bundle.version)
    return summary
