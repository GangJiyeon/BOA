from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, func, insert, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.cosmetic import Brand, Ingredient, Product, ProductIngredient


REQUIRED_SOURCE_TABLES = {
    "cosmetics",
    "ingredients",
    "primary_formulas",
    "formula_ingredients",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="beauty_catalog SQLite 데이터를 BOA PostgreSQL 화장품 테이블로 이관합니다."
    )
    parser.add_argument(
        "source",
        nargs="?",
        default="data/beauty_catalog.db",
        help="원본 SQLite DB 경로 (기본값: data/beauty_catalog.db)",
    )
    return parser.parse_args()


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def scalar_count(session: Session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def main() -> None:
    args = parse_args()
    source_path = Path(args.source)

    if not source_path.exists():
        raise SystemExit(f"[오류] 원본 DB를 찾을 수 없습니다: {source_path.resolve()}")

    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row

    source_tables = {
        row["name"]
        for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    missing_tables = REQUIRED_SOURCE_TABLES - source_tables
    if missing_tables:
        raise SystemExit(
            f"[오류] 원본 DB에 필요한 테이블이 없습니다: {sorted(missing_tables)}"
        )

    source_product_count = source.execute(
        "SELECT COUNT(*) AS n FROM cosmetics"
    ).fetchone()["n"]
    source_ingredient_count = source.execute(
        "SELECT COUNT(*) AS n FROM ingredients"
    ).fetchone()["n"]

    source_link_count = source.execute(
        """
        SELECT COUNT(*) AS n
        FROM (
            SELECT
                pf.cosmetic_id,
                fi.ingredient_id,
                MIN(fi.position) AS position
            FROM primary_formulas AS pf
            JOIN formula_ingredients AS fi
              ON fi.formula_id = pf.formula_id
            GROUP BY pf.cosmetic_id, fi.ingredient_id
        )
        """
    ).fetchone()["n"]

    print("=== BOA 화장품 데이터 이관 시작 ===")
    print(f"원본 SQLite: {source_path.resolve()}")
    print(f"원본 제품: {source_product_count}")
    print(f"원본 성분: {source_ingredient_count}")
    print(f"대표 성분 연결(중복 제거): {source_link_count}")

    engine = create_engine(get_settings().database_url)

    with Session(engine) as session:
        existing = {
            "brands": scalar_count(session, Brand),
            "products": scalar_count(session, Product),
            "ingredients": scalar_count(session, Ingredient),
            "product_ingredients": scalar_count(session, ProductIngredient),
        }

        if any(existing.values()):
            print("[중단] 대상 PostgreSQL 화장품 테이블이 비어 있지 않습니다.")
            print(existing)
            print(
                "중복 삽입을 막기 위해 자동으로 중단했습니다. "
                "현재 데이터 삭제/재이관 여부를 먼저 결정하세요."
            )
            return

        try:
            brand_names = [
                row["brand"]
                for row in source.execute(
                    "SELECT DISTINCT brand FROM cosmetics ORDER BY brand"
                ).fetchall()
            ]

            brand_objects = [Brand(brand_name=name) for name in brand_names]
            session.add_all(brand_objects)
            session.flush()

            brand_id_by_name = {
                brand.brand_name: brand.brand_id for brand in brand_objects
            }
            print(f"[1/4] 브랜드 {len(brand_objects)}개 준비")

            ingredient_rows = source.execute(
                """
                SELECT id, name, normalized_key
                FROM ingredients
                ORDER BY id
                """
            ).fetchall()

            ingredient_objects = [
                Ingredient(
                    ingredient_name=row["name"],
                    name_inci=None,
                    normalized_key=row["normalized_key"],
                )
                for row in ingredient_rows
            ]
            session.add_all(ingredient_objects)
            session.flush()

            ingredient_id_by_source_id = {
                row["id"]: obj.ingredient_id
                for row, obj in zip(ingredient_rows, ingredient_objects)
            }
            print(f"[2/4] 성분 {len(ingredient_objects)}개 준비")

            product_rows = source.execute(
                """
                SELECT
                    id,
                    name,
                    brand,
                    category,
                    ingredients_raw,
                    image_url,
                    normalization_status,
                    source_url,
                    collected_at
                FROM cosmetics
                ORDER BY id
                """
            ).fetchall()

            product_objects = []
            source_product_ids = []

            for row in product_rows:
                product = Product(
                    brand_id=brand_id_by_name[row["brand"]],
                    product_name=row["name"],
                    product_category=row["category"],
                    ingredients_raw=row["ingredients_raw"] or None,
                    image_url=row["image_url"] or None,
                    parse_status=row["normalization_status"],
                    source_url=row["source_url"] or None,
                    collected_at=parse_datetime(row["collected_at"]),
                )
                product_objects.append(product)
                source_product_ids.append(row["id"])

            session.add_all(product_objects)
            session.flush()

            product_id_by_source_id = {
                source_id: obj.product_id
                for source_id, obj in zip(source_product_ids, product_objects)
            }
            print(f"[3/4] 제품 {len(product_objects)}개 준비")

            link_rows = source.execute(
                """
                SELECT
                    pf.cosmetic_id,
                    fi.ingredient_id,
                    MIN(fi.position) AS position
                FROM primary_formulas AS pf
                JOIN formula_ingredients AS fi
                  ON fi.formula_id = pf.formula_id
                GROUP BY pf.cosmetic_id, fi.ingredient_id
                ORDER BY pf.cosmetic_id, MIN(fi.position)
                """
            ).fetchall()

            batch = []
            inserted_links = 0

            for row in link_rows:
                batch.append(
                    {
                        "product_id": product_id_by_source_id[row["cosmetic_id"]],
                        "ingredient_id": ingredient_id_by_source_id[
                            row["ingredient_id"]
                        ],
                        "position": row["position"],
                    }
                )

                if len(batch) >= 5000:
                    session.execute(insert(ProductIngredient), batch)
                    inserted_links += len(batch)
                    batch.clear()

            if batch:
                session.execute(insert(ProductIngredient), batch)
                inserted_links += len(batch)

            print(f"[4/4] 제품-성분 연결 {inserted_links}개 준비")

            session.commit()

        except Exception:
            session.rollback()
            raise

    with Session(engine) as session:
        result = {
            "brands": scalar_count(session, Brand),
            "products": scalar_count(session, Product),
            "ingredients": scalar_count(session, Ingredient),
            "product_ingredients": scalar_count(session, ProductIngredient),
        }

    source.close()

    print("=== 이관 완료 ===")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
