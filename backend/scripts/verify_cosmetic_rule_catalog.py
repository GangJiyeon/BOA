"""첨부 수집 DB를 읽어 별도 메모리 DB에서 규칙 이관과 실제 조회 어댑터를 검증한다.

사용자 PostgreSQL에 접속하지 않는다. 실행: python scripts/verify_cosmetic_rule_catalog.py SOURCE.db
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DATABASE_URL', 'sqlite://')
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import Session
from app.db.base import Base
from app.models.cosmetic import Brand, Product, Ingredient, ProductIngredient
from app.models.skin import SkinMetric, SkinMetricCategory
from app.models.cosmetic_rule import CategoryIngredient, CosmeticRuleEvidence, CosmeticRuleSet
from app.schemas.cosmetic import CosmeticPreviewRequest
from app.services.cosmetic_catalog import preview_from_database
from app.services.cosmetic_rule_repository import seed_rule_bundle
from app.services.cosmetic_rule_types import load_seed_bundle
from app.services.cosmetic_recommendation import recommend
from scripts.preview_cosmetics_from_sqlite import load_catalog, default_definitions
from scripts.seed_skin_metrics import seed_metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    products, known, source_ids = load_catalog(args.source)
    bundle = load_seed_bundle()
    engine = create_engine('sqlite://')
    event.listen(engine, 'connect', lambda conn, record: conn.execute('PRAGMA foreign_keys=ON'))
    tables = [Brand.__table__, Product.__table__, Ingredient.__table__, ProductIngredient.__table__, SkinMetric.__table__, SkinMetricCategory.__table__, CosmeticRuleSet.__table__, CosmeticRuleEvidence.__table__, CategoryIngredient.__table__]
    Base.metadata.create_all(engine, tables=tables)
    brands = {name: i for i, name in enumerate(sorted({p.brand_name for p in products}), 1)}
    ingredients = {name: i for i, name in enumerate(sorted(known), 1)}
    with engine.begin() as conn:
        conn.execute(Brand.__table__.insert(), [{'brand_id':i, 'brand_name':name} for name,i in brands.items()])
        conn.execute(Ingredient.__table__.insert(), [{'ingredient_id':i,'ingredient_name':name} for name,i in ingredients.items()])
        conn.execute(Product.__table__.insert(), [dict(product_id=p.product_id,brand_id=brands[p.brand_name],product_name=p.product_name,product_category=p.category,ingredients_raw=p.ingredients_raw,parse_status=p.parse_status,image_url=p.image_url,source_url=p.source_url) for p in products])
        conn.execute(ProductIngredient.__table__.insert(), [dict(product_id=p.product_id,ingredient_id=ingredients[name]) for p in products for name in p.ingredients])
    with Session(engine) as db, db.begin():
        seed_metrics(db)
        counts_before = [db.scalar(select(func.count()).select_from(t)) for t in (Product,Ingredient,ProductIngredient)]
        dry = seed_rule_bundle(db, bundle)
        applied = seed_rule_bundle(db, bundle, apply=True)
        repeat = seed_rule_bundle(db, bundle, apply=True)
        assert counts_before == [db.scalar(select(func.count()).select_from(t)) for t in (Product,Ingredient,ProductIngredient)]
    scenarios={
        'five_concerns':dict(moisture=25,redness=75,brightness=30,trouble=75,uniformity=30),
        'screenshot':dict(moisture=50,redness=75,brightness=30,trouble=75,uniformity=30),
        'moisture_only':dict(moisture=25,redness=10,brightness=80,trouble=10,uniformity=80),
        'all_good':dict(moisture=80,redness=10,brightness=80,trouble=10,uniformity=80),
    }
    results={}
    for name,scores in scenarios.items():
        request=CosmeticPreviewRequest(scores=scores, score_semantics="development_assumption")
        with Session(engine) as db:
            actual=preview_from_database(db,request)
        expected=recommend(request,default_definitions(),products,known,rule_bundle=bundle)
        assert actual.model_dump() == expected.model_dump(), name
        results[name]={'stats':actual.stats.model_dump(),'scorable_target_count':actual.scorable_target_count,
                       'top5':[{'id':source_ids[p.product_id],'name':p.product_name,'matches':p.match_count} for p in actual.recommendations]}
    coverage=Counter(name for p in products for name in p.ingredients)
    print(json.dumps({'database':'isolated in-memory SQLite; source read-only','source_counts':counts_before,'dry_run':dry,'applied':applied,'repeat':repeat,'coverage':{r.ingredient:coverage[r.ingredient] for r in bundle.rules},'scenarios':results},ensure_ascii=False,indent=2))
    engine.dispose()


if __name__=='__main__':
    main()
