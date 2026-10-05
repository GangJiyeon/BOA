"""원본 SQLite를 읽어 별도 메모리 DB에서 관측 이관을 재현한다. 사용자 DB 미접속.

실행: python scripts/verify_cosmetic_observations.py SOURCE.db
설정 파일이나 DATABASE_URL을 사용하지 않으며, 이 도구의 INSERT는 메모리 DB에만 실행한다.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, insert, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.cosmetic import Brand, Product, Ingredient, ProductIngredient
from app.services.cosmetic_observation_import import fingerprint, import_observations, read_snapshot


def verify(path: Path):
    source = read_snapshot(path)
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda c, r: c.execute("PRAGMA foreign_keys=ON"))
    parents = [Brand.__table__, Product.__table__, Ingredient.__table__, ProductIngredient.__table__]
    Base.metadata.create_all(engine, tables=parents)
    brands = {name: i for i, name in enumerate(sorted({p["brand"] for p in source.products}), 1)}
    # 숫자 ID가 원본과 달라도 올바르게 대응하는지 검증한다.
    products = {p["id"]: i for i, p in enumerate(source.products, 1001)}
    ingredients = {r["id"]: i for i, r in enumerate(source.ingredients, 7001)}
    links = {}
    for r in source.observations:
        key = (products[r["source_product_id"]], ingredients[r["source_ingredient_id"]])
        links[key] = min(links.get(key, r["source_position"]), r["source_position"])
    try:
        with engine.begin() as conn:
            conn.execute(insert(Brand), [dict(brand_id=i, brand_name=name) for name, i in brands.items()])
            conn.execute(insert(Ingredient), [dict(ingredient_id=ingredients[r["id"]], ingredient_name=r["name"]) for r in source.ingredients])
            conn.execute(insert(Product), [dict(product_id=products[r["id"]], brand_id=brands[r["brand"]],
                         product_name=r["name"], ingredients_raw=r["ingredients_raw"], parse_status=r["normalization_status"],
                         source_url=r["source_url"]) for r in source.products])
            conn.execute(insert(ProductIngredient), [dict(product_id=p, ingredient_id=i, position=pos) for (p, i), pos in links.items()])
        def catalog_hashes():
            with engine.connect() as conn:
                return {t.name: fingerprint([dict(r) for r in conn.execute(select(t).order_by(*t.primary_key.columns)).mappings()]) for t in parents}
        before = catalog_hashes()
        with Session(engine) as db, db.begin():
            pre_migration = import_observations(db, source)
        revision = Path(__file__).resolve().parents[1] / "alembic/versions/2026_10_05_0200-d0610a1b2c3d_create_cosmetic_observations.py"
        spec = importlib.util.spec_from_file_location("observation_migration", revision)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with engine.begin() as conn:
            with patch.object(module, "op", Operations(MigrationContext.configure(conn))):
                module.upgrade()
        with Session(engine) as db, db.begin():
            dry = import_observations(db, source)
        with Session(engine) as db, db.begin():
            applied = import_observations(db, source, apply=True)
        with Session(engine) as db, db.begin():
            repeat = import_observations(db, source, apply=True)
        assert before == catalog_hashes(), "기존 카탈로그 내용이 달라졌습니다."
        assert pre_migration["migration_required"] and not dry["migration_required"]
        assert repeat["action"] == "unchanged"
        assert applied["observations"] == len(source.observations)
        return {"database": "isolated in-memory SQLite only", "catalog_unchanged": True,
                "pre_migration": pre_migration, "dry_run": dry, "applied": applied, "repeat": repeat}
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.source), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
