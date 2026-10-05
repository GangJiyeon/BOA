"""관측 이관은 격리 SQLite에서 검증한다. 사용자 DB 연결 없음."""
from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.cosmetic import Brand, Product, Ingredient, ProductIngredient
from app.models.cosmetic_observation import CosmeticObservationBatch, ProductIngredientObservation
from app.services.cosmetic_observation_import import ObservationImportError, import_observations, read_snapshot

PARENTS = [Brand.__table__, Product.__table__, Ingredient.__table__, ProductIngredient.__table__]
OBSERVATIONS = [CosmeticObservationBatch.__table__, ProductIngredientObservation.__table__]


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "source.db"
        with sqlite3.connect(self.path) as conn:
            conn.executescript("""
                CREATE TABLE cosmetics(id TEXT PRIMARY KEY, name TEXT, brand TEXT, source_url TEXT,
                    ingredients_raw TEXT, normalization_status TEXT, source_hash TEXT);
                CREATE TABLE ingredients(id INTEGER PRIMARY KEY, name TEXT);
                CREATE TABLE cosmetic_formulas(id TEXT PRIMARY KEY, cosmetic_id TEXT);
                CREATE TABLE primary_formulas(cosmetic_id TEXT PRIMARY KEY, formula_id TEXT);
                CREATE TABLE formula_ingredients(formula_id TEXT, ingredient_id INTEGER, position INTEGER,
                    raw_token TEXT, amount_text TEXT, PRIMARY KEY(formula_id,position));
                INSERT INTO cosmetics VALUES('A7','제품','브랜드','https://example.com/A7','우레아(5%),정제수,우레아','normalized','record-hash');
                INSERT INTO ingredients VALUES(7,'우레아'),(8,'정제수');
                INSERT INTO cosmetic_formulas VALUES('A7:1','A7');
                INSERT INTO primary_formulas VALUES('A7','A7:1');
                INSERT INTO formula_ingredients VALUES('A7:1',7,1,'우레아(5%)','5%'),
                    ('A7:1',8,2,'정제수',''),('A7:1',7,3,'우레아','');
            """)
        self.source = read_snapshot(self.path)
        self.engine = create_engine("sqlite://")
        event.listen(self.engine, "connect", lambda c, r: c.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine, tables=PARENTS)
        with Session(self.engine) as db, db.begin():
            db.add(Brand(brand_id=50, brand_name="브랜드"))
            db.flush()
            db.add(Product(product_id=101, brand_id=50, product_name="제품", source_url="https://example.com/A7",
                           ingredients_raw="우레아(5%),정제수,우레아", parse_status="normalized"))
            db.add_all([Ingredient(ingredient_id=205, ingredient_name="우레아"), Ingredient(ingredient_id=206, ingredient_name="정제수")])
            db.flush()
            db.add_all([ProductIngredient(product_id=101, ingredient_id=205), ProductIngredient(product_id=101, ingredient_id=206)])
        self.migration = self.load_migration()

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def load_migration(self):
        path = Path(__file__).resolve().parents[1] / "alembic/versions/2026_10_05_0200-d0610a1b2c3d_create_cosmetic_observations.py"
        spec = importlib.util.spec_from_file_location("observation_migration", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def migrate(self):
        with self.engine.begin() as conn:
            with patch.object(self.migration, "op", Operations(MigrationContext.configure(conn))):
                self.migration.upgrade()

    def apply(self):
        with Session(self.engine) as db, db.begin():
            return import_observations(db, self.source, apply=True)

    def test_source_is_read_only_and_repeated_ingredient_rows_preserved(self):
        before = self.path.read_bytes()
        source = read_snapshot(self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(len(source.observations), 3)
        self.assertEqual(source.observations[0]["amount_text"], "5%")
        self.assertEqual(source.observations[2]["amount_text"], "")
        self.assertEqual(source.source_file_sha256, hashlib.sha256(before).hexdigest())

    def test_dry_run_before_migration_never_writes(self):
        statements = []
        event.listen(self.engine, "before_cursor_execute", lambda c, cur, sql, p, ctx, many: statements.append(sql))
        with Session(self.engine) as db, db.begin():
            report = import_observations(db, self.source)
        self.assertEqual(report["action"], "dry_run")
        self.assertTrue(report["migration_required"])
        self.assertEqual(report["would_insert_observations"], 3)
        self.assertTrue(all(s.lstrip().upper().startswith(("SELECT", "PRAGMA")) for s in statements))
        self.assertEqual(report["existing_catalog_writes"], 0)

    def test_apply_requires_migration(self):
        with self.assertRaisesRegex(ObservationImportError, "alembic"):
            self.apply()

    def test_mapping_uses_identity_not_source_numeric_ids_and_repeat_is_noop(self):
        self.migrate()
        first = self.apply()
        self.assertEqual(first["action"], "insert")
        self.assertEqual(first["amounts_present"], 1)
        self.assertEqual(first["unique_product_ingredient_pairs"], 2)
        with Session(self.engine) as db:
            rows = db.scalars(select(ProductIngredientObservation).order_by(ProductIngredientObservation.source_position)).all()
            self.assertEqual([r.product_id for r in rows], [101]*3)
            self.assertEqual([r.ingredient_id for r in rows], [205,206,205])
            self.assertEqual([r.review_status for r in rows], ["unreviewed"]*3)
            self.assertEqual(db.scalar(select(func.count()).select_from(ProductIngredient)), 2)
        self.assertEqual(self.apply()["action"], "unchanged")

    def test_dry_run_after_migration_inserts_nothing(self):
        self.migrate()
        with Session(self.engine) as db, db.begin():
            report = import_observations(db, self.source)
            self.assertFalse(report["migration_required"])
            self.assertEqual(db.scalar(select(func.count()).select_from(CosmeticObservationBatch)), 0)

    def test_missing_link_aborts_before_any_insert(self):
        self.migrate()
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM product_ingredients WHERE ingredient_id=206"))
        with self.assertRaisesRegex(ObservationImportError, "연결"):
            self.apply()
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CosmeticObservationBatch)), 0)

    def test_duplicate_target_url_rejected(self):
        with Session(self.engine) as db, db.begin():
            db.add(Product(product_id=102, brand_id=50, product_name="제품", source_url="https://example.com/A7"))
        with Session(self.engine) as db, self.assertRaisesRegex(ObservationImportError, "URL"):
            import_observations(db, self.source)

    def test_wrong_raw_formula_rejected(self):
        with Session(self.engine) as db, db.begin():
            db.get(Product,101).ingredients_raw = "다른 전성분"
        with Session(self.engine) as db, self.assertRaisesRegex(ObservationImportError, "원문"):
            import_observations(db, self.source)

    def test_extra_catalog_link_is_not_silently_accepted(self):
        with Session(self.engine) as db, db.begin():
            db.add(Ingredient(ingredient_id=207, ingredient_name="향료"))
            db.flush()
            db.add(ProductIngredient(product_id=101, ingredient_id=207))
        with Session(self.engine) as db, self.assertRaisesRegex(ObservationImportError, "연결"):
            import_observations(db, self.source)

    def test_missing_source_file_does_not_create_empty_database(self):
        missing = Path(self.temp.name) / "missing.db"
        with self.assertRaisesRegex(ObservationImportError, "파일이 없습니다"):
            read_snapshot(missing)
        self.assertFalse(missing.exists())

    def test_duplicate_source_url_and_partial_migration_rejected(self):
        duplicate = dict(self.source.products[0], id="another")
        with Session(self.engine) as db, self.assertRaisesRegex(ObservationImportError, "URL"):
            import_observations(db, replace(self.source, products=(*self.source.products, duplicate)))
        Base.metadata.create_all(self.engine, tables=[CosmeticObservationBatch.__table__])
        with Session(self.engine) as db, self.assertRaisesRegex(ObservationImportError, "일부만"):
            import_observations(db, self.source)

    def test_pending_unrelated_writes_are_not_flushed(self):
        with Session(self.engine) as db:
            db.add(Ingredient(ingredient_id=207, ingredient_name="추가 성분"))
            with self.assertRaisesRegex(ObservationImportError, "전용"):
                import_observations(db, self.source)
            db.rollback()
        with Session(self.engine) as db:
            self.assertIsNone(db.get(Ingredient,207))

    def test_repeat_executes_only_reads(self):
        self.migrate()
        self.apply()
        statements = []
        event.listen(self.engine, "before_cursor_execute", lambda c,cur,s,p,ctx,many: statements.append(s))
        self.assertEqual(self.apply()["action"], "unchanged")
        self.assertTrue(all(s.lstrip().upper().startswith(("SELECT", "PRAGMA")) for s in statements))

    def test_normalized_ingredient_collision_rejected(self):
        with Session(self.engine) as db, db.begin():
            db.add(Ingredient(ingredient_id=207, ingredient_name="우 레 아"))
        with Session(self.engine) as db, self.assertRaisesRegex(ObservationImportError, "성분명"):
            import_observations(db, self.source)

    def test_partial_deletion_and_content_edit_detected_without_repair(self):
        self.migrate()
        self.apply()
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE product_ingredient_observations SET amount_text='99%' WHERE source_position=1"))
        with self.assertRaisesRegex(ObservationImportError, "덮어쓰지"):
            self.apply()
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM product_ingredient_observations WHERE source_position=1"))
        with self.assertRaisesRegex(ObservationImportError, "일부 삭제"):
            self.apply()

    def test_failed_insert_rolls_back_batch_and_all_observations(self):
        self.migrate()
        def fail(c, cur, sql, p, ctx, many):
            if sql.startswith("INSERT INTO product_ingredient_observations"):
                raise RuntimeError("injected insert failure")
        event.listen(self.engine, "before_cursor_execute", fail)
        with self.assertRaises(RuntimeError):
            self.apply()
        event.remove(self.engine, "before_cursor_execute", fail)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CosmeticObservationBatch)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(ProductIngredientObservation)), 0)

    def test_post_insert_content_mismatch_rolls_back_everything(self):
        self.migrate()
        with self.engine.begin() as conn:
            conn.execute(text("""CREATE TRIGGER corrupt_observation AFTER INSERT ON product_ingredient_observations
                BEGIN UPDATE product_ingredient_observations SET amount_text='changed'
                WHERE batch_id=NEW.batch_id AND source_formula_id=NEW.source_formula_id
                AND source_position=NEW.source_position; END"""))
        with self.assertRaisesRegex(ObservationImportError, "덮어쓰지"):
            self.apply()
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CosmeticObservationBatch)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(ProductIngredientObservation)), 0)

    def test_wal_source_and_orphan_ingredient_are_rejected(self):
        wal = Path(str(self.path)+"-wal")
        wal.touch()
        with self.assertRaisesRegex(ObservationImportError, "WAL"):
            read_snapshot(self.path)
        wal.unlink()
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE formula_ingredients SET ingredient_id=999 WHERE position=1")
        with self.assertRaisesRegex(ObservationImportError, "성분 연결"):
            read_snapshot(self.path)

    def test_source_formula_owner_must_match(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE cosmetic_formulas SET cosmetic_id='other'")
        with self.assertRaisesRegex(ObservationImportError, "소유 제품"):
            read_snapshot(self.path)

    def test_source_physical_hash_change_does_not_duplicate_same_logical_data(self):
        self.migrate()
        self.apply()
        with Session(self.engine) as db, db.begin():
            result = import_observations(db, replace(self.source, source_file_sha256="a"*64), apply=True)
        self.assertEqual(result["action"], "unchanged")

    def test_schema_matches_model_and_downgrade_preserves_catalog(self):
        self.migrate()
        self.apply()
        wanted = {t.name for t in PARENTS+OBSERVATIONS}
        with self.engine.begin() as conn:
            ctx = MigrationContext.configure(conn, opts={"include_object": lambda obj,n,k,r,c: k!="table" or n in wanted})
            self.assertEqual(compare_metadata(ctx, Base.metadata), [])
            with patch.object(self.migration, "op", Operations(ctx)):
                self.migration.downgrade()
            self.assertEqual(conn.scalar(select(func.count()).select_from(Product)), 1)
            self.assertEqual(conn.scalar(select(func.count()).select_from(ProductIngredient)), 2)

    def test_composite_fk_and_unreviewed_status_are_enforced(self):
        self.migrate()
        self.apply()
        for sql in ("UPDATE product_ingredient_observations SET ingredient_id=999",
                    "UPDATE product_ingredient_observations SET review_status='effective'"):
            with self.subTest(sql=sql), self.assertRaises(IntegrityError), self.engine.begin() as conn:
                conn.execute(text(sql))


if __name__ == "__main__":
    unittest.main()
