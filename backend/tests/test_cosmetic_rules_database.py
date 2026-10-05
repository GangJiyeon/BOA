"""실제 규칙 DB 경유, 시드 원자성·버전 무결성·추가 마이그레이션 회귀 검증."""
import asyncio
import importlib.util
from pathlib import Path
import unittest

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.autogenerate import compare_metadata
from sqlalchemy import create_engine, event, select, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from unittest.mock import patch

import test_cosmetic_recommendation as fixtures
from app.db.base import Base
from app.models.cosmetic import Ingredient, ProductIngredient
from app.models.cosmetic_rule import CategoryIngredient, CosmeticRuleEvidence, CosmeticRuleSet
from app.models.skin import SkinMetric, SkinMetricCategory
from app.services.cosmetic_rule_repository import load_database_rules, seed_rule_bundle
from app.services.cosmetic_rule_types import load_seed_bundle
from app.services.cosmetic_recommendation import RecommendationConfigurationError, recommend
from scripts.seed_skin_metrics import seed_metrics

RULE_TABLES = [CosmeticRuleSet.__table__, CosmeticRuleEvidence.__table__, CategoryIngredient.__table__]


class RuleDatabaseTests(unittest.TestCase):
    setUp = fixtures.ApiDatabaseTests.setUp
    tearDown = fixtures.ApiDatabaseTests.tearDown

    def test_database_bundle_roundtrip_and_idempotent_seed(self):
        with Session(self.engine) as db:
            self.assertEqual(load_database_rules(db).fingerprint(), load_seed_bundle().fingerprint())
            report = seed_rule_bundle(db, load_seed_bundle(), apply=True)
            self.assertEqual(report['action'], 'unchanged')
            self.assertEqual(db.scalar(select(func.count()).select_from(CategoryIngredient)), 20)

    def test_api_explains_sources_and_version_from_database(self):
        status, data = asyncio.run(fixtures.asgi_request(fixtures.request().model_dump()))
        self.assertEqual(status, 200)
        self.assertEqual(data['rule_version'], load_seed_bundle().version)
        detail = data['recommendations'][0]['matches'][0]['rule_details'][0]
        self.assertIn('evidence_summary', detail)
        self.assertTrue(detail['limitations'])
        self.assertEqual(len(data['exclusion_details']), 8)

    def test_no_file_fallback_when_database_rules_missing(self):
        with Session(self.engine) as db:
            db.query(CategoryIngredient).delete()
            db.query(CosmeticRuleEvidence).delete()
            db.query(CosmeticRuleSet).delete()
            db.commit()
        status, data = asyncio.run(fixtures.asgi_request(fixtures.request().model_dump()))
        self.assertEqual(status, 503)
        self.assertIn('시드', data['detail'])

    def test_missing_migration_has_actionable_503(self):
        Base.metadata.drop_all(self.engine, tables=RULE_TABLES)
        status, data = asyncio.run(fixtures.asgi_request(fixtures.request().model_dump()))
        self.assertEqual(status, 503)
        self.assertIn('alembic', data['detail'])

    def test_partial_rule_deletion_detected(self):
        with Session(self.engine) as db:
            db.query(CategoryIngredient).filter_by(code='redness-exclude-fragrance').delete()
            db.commit()
        status, _ = asyncio.run(fixtures.asgi_request(fixtures.request().model_dump()))
        self.assertEqual(status, 503)

    def test_same_version_changed_payload_refused_without_overwrite(self):
        changed = load_seed_bundle().model_copy(update={'description': '다른 내용'})
        with Session(self.engine) as db:
            with self.assertRaises(RecommendationConfigurationError):
                seed_rule_bundle(db, changed, apply=True)
            self.assertEqual(load_database_rules(db).description, load_seed_bundle().description)

    def test_engine_respects_database_category_and_deferred_status(self):
        with Session(self.engine) as db:
            bundle = load_database_rules(db)
        scores = {'moisture': 20, 'redness': 10, 'brightness': 90, 'trouble': 10, 'uniformity': 90}
        for name, count in [('하이알루로닉애씨드', 1), ('소듐하이알루로네이트', 0), ('세라마이드엔피', 0), ('우레아', 0)]:
            with self.subTest(name=name):
                result = recommend(fixtures.request(scores=scores), fixtures.definitions(), [fixtures.product(ingredients=(name,))], {name}, rule_bundle=bundle)
                self.assertEqual(len(result.recommendations), count)
        changed = bundle.model_copy(update={'rules': tuple(r.model_copy(update={'category':'보통'}) if r.code=='moisture-ha' else r for r in bundle.rules)})
        result = recommend(fixtures.request(scores=scores), fixtures.definitions(), [fixtures.product(ingredients=('하이알루로닉애씨드',))], {'하이알루로닉애씨드'}, rule_bundle=changed)
        self.assertEqual(result.recommendations, [])

    def test_new_exclusions_do_not_become_global_bans(self):
        with Session(self.engine) as db:
            bundle = load_database_rules(db)
        for name in ['우레아', '캠퍼']:
            p = fixtures.product(ingredients=('글리세린', name))
            for red, enabled, count in [(80,True,0), (10,True,1), (80,False,1)]:
                result = recommend(fixtures.request(scores=fixtures.request().scores.model_dump() | {'redness':red}, avoid_redness_triggers=enabled), fixtures.definitions(), [p], {'글리세린',name}, rule_bundle=bundle)
                self.assertEqual(len(result.recommendations), count)


class SeedAndMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        event.listen(self.engine, 'connect', lambda conn, record: conn.execute('PRAGMA foreign_keys=ON'))
        self.parent_tables = [SkinMetric.__table__, SkinMetricCategory.__table__, Ingredient.__table__]
        Base.metadata.create_all(self.engine, tables=self.parent_tables)
        path = Path(__file__).resolve().parents[1] / 'alembic/versions/2026_10_05_0000-c0510a1b2c3d_create_cosmetic_rule_tables.py'
        spec = importlib.util.spec_from_file_location('rule_migration', path)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        with self.engine.begin() as conn:
            with patch.object(self.migration, 'op', Operations(MigrationContext.configure(conn))):
                self.migration.upgrade()
        with Session(self.engine) as db:
            seed_metrics(db)
            # 실제 PostgreSQL ID를 가정하지 않고 다른 ID로도 연결되는지 확인.
            for i, name in enumerate(sorted({r.ingredient for r in load_seed_bundle().rules}), 101):
                db.add(Ingredient(ingredient_id=i, ingredient_name=name))
            db.commit()

    def tearDown(self):
        self.engine.dispose()

    def test_dry_run_has_no_writes_then_seed_and_repeat(self):
        statements=[]
        event.listen(self.engine, 'before_cursor_execute', lambda c, cur, sql, p, ctx, many: statements.append(sql))
        with Session(self.engine) as db:
            self.assertEqual(seed_rule_bundle(db, load_seed_bundle())['action'], 'dry_run')
            self.assertTrue(all(sql.lstrip().upper().startswith('SELECT') for sql in statements))
            self.assertEqual(db.scalar(select(func.count()).select_from(CosmeticRuleSet)), 0)
        with Session(self.engine) as db, db.begin():
            seed_rule_bundle(db, load_seed_bundle(), apply=True)
        with Session(self.engine) as db:
            self.assertEqual(seed_rule_bundle(db, load_seed_bundle(), apply=True)['action'], 'unchanged')
            self.assertEqual(load_database_rules(db).fingerprint(), load_seed_bundle().fingerprint())

    def test_missing_ingredient_rolls_back_everything(self):
        with Session(self.engine) as db, db.begin():
            db.query(Ingredient).filter_by(ingredient_name='판테놀').delete()
        with self.assertRaises(RecommendationConfigurationError):
            with Session(self.engine) as db, db.begin():
                seed_rule_bundle(db, load_seed_bundle(), apply=True)
        with Session(self.engine) as db:
            for cls in (CosmeticRuleSet, CosmeticRuleEvidence, CategoryIngredient):
                self.assertEqual(db.scalar(select(func.count()).select_from(cls)), 0)

    def test_normalized_name_collision_is_not_guessed(self):
        with Session(self.engine) as db, db.begin():
            db.add(Ingredient(ingredient_id=9999, ingredient_name='판 테 놀'))
        with Session(self.engine) as db:
            with self.assertRaises(RecommendationConfigurationError):
                seed_rule_bundle(db, load_seed_bundle(), apply=True)

    def test_migration_matches_models_and_downgrade_preserves_catalog(self):
        wanted = {t.name for t in self.parent_tables + RULE_TABLES}
        with self.engine.begin() as conn:
            context = MigrationContext.configure(conn, opts={'include_object': lambda obj, name, kind, reflected, compare_to: kind != 'table' or name in wanted})
            self.assertEqual(compare_metadata(context, Base.metadata), [])
            with patch.object(self.migration, 'op', Operations(context)):
                self.migration.downgrade()
            self.assertGreater(conn.scalar(select(func.count()).select_from(Ingredient)), 0)
            self.assertEqual(conn.scalar(select(func.count()).select_from(SkinMetric)), 5)

    def test_database_rejects_rule_with_conflicting_score(self):
        with Session(self.engine) as db, db.begin():
            seed_rule_bundle(db, load_seed_bundle(), apply=True)
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as conn:
                conn.execute(text("UPDATE category_ingredients SET match_score=1 WHERE effect='exclude'"))
