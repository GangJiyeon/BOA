"""원본 스냅샷 검증 → 정확한 URL/성분명 대응 → 원문만 새 이력 테이블에 저장.

효능/농도 추정과 기존 제품 수정은 하지 않는다. 트랜잭션은 호출자가 소유한다.
"""
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3

from sqlalchemy import inspect, insert, select
from sqlalchemy.orm import Session

from app.models.cosmetic import Brand, Ingredient, Product, ProductIngredient
from app.models.cosmetic_observation import CosmeticObservationBatch, ProductIngredientObservation
from app.services.cosmetic_rules import normalize_name

IMPORTER_VERSION = "cosmetic-observations-v1"
REVISION = "d0610a1b2c3d"


class ObservationImportError(ValueError):
    pass


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class SourceSnapshot:
    products: tuple[dict, ...]
    ingredients: tuple[dict, ...]
    observations: tuple[dict, ...]
    source_file_sha256: str

    @property
    def batch_id(self):
        return fingerprint([IMPORTER_VERSION, self.products, self.ingredients, self.observations])


def read_snapshot(path: Path) -> SourceSnapshot:
    """URI read-only + query_only. 논리 내용은 SQLite 읽기 트랜잭션으로 고정한다."""
    path = path.resolve()
    if not path.is_file():
        raise ObservationImportError("원본 SQLite 파일이 없습니다. 컨테이너 안의 실제 경로를 확인하세요.")
    # WAL을 복사하지 않은 중간 파일을 읽었다고 오인하지 않게 멈춘다.
    if Path(str(path) + "-wal").exists():
        raise ObservationImportError("WAL 파일이 있습니다. 수집 프로그램에서 일관된 백업을 만든 뒤 사용하세요.")
    with path.open("rb") as source_file:
        before = hashlib.file_digest(source_file, "sha256").hexdigest()
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        products = tuple(dict(r) for r in conn.execute("""
            SELECT id, name, brand, source_url, ingredients_raw, normalization_status, source_hash
            FROM cosmetics ORDER BY id
        """))
        ingredients = tuple(dict(r) for r in conn.execute("SELECT id, name FROM ingredients ORDER BY id"))
        if any(any(not isinstance(v, str) for v in p.values()) or not p["id"] or len(p["id"]) > 255 for p in products):
            raise ObservationImportError("원본 제품의 필수 문자열/식별자 형식이 잘못되었습니다.")
        if any(type(i["id"]) is not int or not isinstance(i["name"], str) or not i["name"].strip() for i in ingredients):
            raise ObservationImportError("원본 성분의 식별자/이름 형식이 잘못되었습니다.")
        primary = conn.execute("""
            SELECT pf.cosmetic_id, pf.formula_id, cf.cosmetic_id AS owner_id
            FROM primary_formulas pf LEFT JOIN cosmetic_formulas cf ON cf.id=pf.formula_id
        """).fetchall()
        product_by_id = {p["id"]: p for p in products}
        ingredient_ids = {i["id"] for i in ingredients}
        if not products or not ingredients or not primary:
            raise ObservationImportError("비어 있는 원본 카탈로그 또는 대표 처방입니다.")
        if any(r["cosmetic_id"] not in product_by_id or r["owner_id"] != r["cosmetic_id"] for r in primary):
            raise ObservationImportError("대표 처방의 소유 제품 연결이 잘못되었습니다.")
        rows = conn.execute("""
            SELECT pf.cosmetic_id AS source_product_id, pf.formula_id AS source_formula_id,
                   fi.ingredient_id AS source_ingredient_id, fi.position AS source_position,
                   fi.raw_token, fi.amount_text
            FROM primary_formulas pf JOIN formula_ingredients fi ON fi.formula_id=pf.formula_id
            ORDER BY pf.formula_id, fi.position
        """).fetchall()
        seen = set()
        observations = []
        for row in rows:
            item = dict(row)
            key = (item["source_formula_id"], item["source_position"])
            if (key in seen or type(item["source_position"]) is not int or not 0 <= item["source_position"] <= 2147483647
                    or not isinstance(item["source_formula_id"], str) or not 0 < len(item["source_formula_id"]) <= 255
                    or item["source_ingredient_id"] not in ingredient_ids
                    or not isinstance(item["raw_token"], str) or not isinstance(item["amount_text"], str)):
                raise ObservationImportError("성분 원문 행에 중복 위치·잘못된 성분 연결·누락이 있습니다.")
            seen.add(key)
            product = product_by_id[item["source_product_id"]]
            item.update(source_url=product["source_url"], source_record_hash=product["source_hash"],
                        review_status="unreviewed")
            observations.append(item)
        if {r["source_formula_id"] for r in observations} != {r["formula_id"] for r in primary}:
            raise ObservationImportError("대표 처방에 성분 원문 행이 없습니다.")
    except sqlite3.Error as exc:
        raise ObservationImportError("원본 SQLite 스키마/읽기 오류입니다. 올바른 수집 DB인지 확인하세요.") from exc
    finally:
        conn.close()
    with path.open("rb") as source:
        after = hashlib.file_digest(source, "sha256").hexdigest()
    if before != after or Path(str(path) + "-wal").exists():
        raise ObservationImportError("검사 중 원본이 바뀌었습니다. 수집을 종료한 일관된 복사본을 사용하세요.")
    return SourceSnapshot(products, ingredients, tuple(observations), after)


def resolve_rows(db: Session, source: SourceSnapshot) -> list[dict]:
    """원본 ID 순서를 가정하지 않는다. 원본 카탈로그 전체의 대응을 확인한다."""
    target_urls = defaultdict(list)
    for p, brand in db.execute(select(Product, Brand.brand_name).join(Brand)):
        target_urls[p.source_url].append((p, brand))
    products = {}
    urls_seen = set()
    for original in source.products:
        url = original["source_url"]
        if not url or not url.strip() or url in urls_seen or len(target_urls[url]) != 1:
            raise ObservationImportError(f"제품 {original['id']}: 원본 URL 누락/중복 또는 대상 제품이 없거나 중복입니다.")
        urls_seen.add(url)
        p, brand = target_urls[url][0]
        if (p.product_name != original["name"] or brand != original["brand"]
                or (p.ingredients_raw or "") != original["ingredients_raw"]
                or p.parse_status != original["normalization_status"]):
            raise ObservationImportError(f"제품 {original['id']}: 대상 이름·브랜드·성분 원문·정규화 상태가 원본과 다릅니다.")
        products[original["id"]] = p.product_id
    names = defaultdict(list)
    for ingredient in db.scalars(select(Ingredient)):
        names[normalize_name(ingredient.ingredient_name)].append(ingredient)
    ingredients = {}
    source_names = set()
    for original in source.ingredients:
        key = normalize_name(original["name"])
        candidates = names[key]
        if not key or key in source_names or len(candidates) != 1 or candidates[0].ingredient_name != original["name"]:
            raise ObservationImportError(f"원본 성분 {original['id']}: 정확한 성분명 누락/중복/정규화 충돌입니다.")
        source_names.add(key)
        ingredients[original["id"]] = candidates[0].ingredient_id
    expected_links = {(products[r["source_product_id"]], ingredients[r["source_ingredient_id"]]) for r in source.observations}
    product_ids = set(products.values())
    actual_links = {(p, i) for p, i in db.execute(select(ProductIngredient.product_id, ProductIngredient.ingredient_id)) if p in product_ids}
    if expected_links != actual_links:
        raise ObservationImportError("대상 제품-성분 연결이 원본과 다릅니다. 누락/추가 연결을 확인하세요. 자동 수정하지 않습니다.")
    batch_id = source.batch_id
    return sorted([dict(r, batch_id=batch_id, product_id=products[r["source_product_id"]],
                        ingredient_id=ingredients[r["source_ingredient_id"]]) for r in source.observations],
                  key=lambda r: (r["source_formula_id"], r["source_position"]))


def import_observations(db: Session, source: SourceSnapshot, *, apply: bool = False) -> dict:
    if db.new or db.dirty or db.deleted:
        raise ObservationImportError("이관 전용의 변경 사항 없는 세션을 사용하세요.")
    rows = resolve_rows(db, source)
    tables = set(inspect(db.connection()).get_table_names())
    needed = {CosmeticObservationBatch.__tablename__, ProductIngredientObservation.__tablename__}
    if tables & needed and not needed <= tables:
        raise ObservationImportError("관측 테이블이 일부만 있습니다. 마이그레이션 상태를 확인하세요.")
    migration_required = not needed <= tables
    if apply and migration_required:
        raise ObservationImportError(f"관측 테이블이 없습니다. alembic upgrade {REVISION} 검토 후 적용하세요.")
    batch_id = source.batch_id
    amount_count = sum(bool(r["amount_text"].strip()) for r in rows)
    payload_hash = fingerprint(rows)
    existing = None if migration_required else db.get(CosmeticObservationBatch, batch_id)
    if existing:
        actual = [dict(r) for r in db.execute(select(ProductIngredientObservation.__table__)
                  .where(ProductIngredientObservation.batch_id == batch_id)
                  .order_by(ProductIngredientObservation.source_formula_id, ProductIngredientObservation.source_position)).mappings()]
        actual.sort(key=lambda r: (r["source_formula_id"], r["source_position"]))
        if (existing.payload_hash != payload_hash or fingerprint(actual) != payload_hash
                or existing.record_count != len(rows) or existing.amount_count != amount_count
                or existing.importer_version != IMPORTER_VERSION):
            raise ObservationImportError("기존 관측 배치의 내용이 다르거나 일부 삭제되었습니다. 덮어쓰지 않습니다.")
    report = dict(action="unchanged" if existing else ("insert" if apply else "dry_run"),
                  migration_required=migration_required, required_revision=REVISION,
                  batch_id=batch_id, source_file_sha256=source.source_file_sha256,
                  source_products=len(source.products), source_ingredients=len(source.ingredients),
                  observations=len(rows), amounts_present=amount_count,
                  amounts_not_reported=len(rows) - amount_count,
                  unique_product_ingredient_pairs=len({(r["product_id"], r["ingredient_id"]) for r in rows}),
                  would_insert_batches=0 if existing else 1, would_insert_observations=0 if existing else len(rows),
                  existing_catalog_writes=0, recommendation_rules_changed=False)
    if existing or not apply:
        return report
    db.execute(insert(CosmeticObservationBatch), dict(batch_id=batch_id, source_file_sha256=source.source_file_sha256,
               payload_hash=payload_hash, importer_version=IMPORTER_VERSION, record_count=len(rows), amount_count=amount_count))
    for start in range(0, len(rows), 1000):
        db.execute(insert(ProductIngredientObservation), rows[start:start + 1000])
    # 저장 직후에도 전체 내용 해시를 대조한다. 실패하면 호출자의 트랜잭션이 전부 롤백한다.
    import_observations(db, source)
    return report
