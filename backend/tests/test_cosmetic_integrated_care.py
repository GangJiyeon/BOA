"""Exercise every state combination through the photo recommendation contract."""
from itertools import product
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.orm import Session

import test_cosmetic_recommendation as f
from app.schemas.cosmetic import CosmeticPreviewRequest
from app.services.cosmetic_rule_types import RuleBundle
from app.services.cosmetic_rule_repository import load_database_rules, seed_rule_bundle


GOOD = dict(moisture=90, redness=10, brightness=90, trouble=10, uniformity=90)


def request(scores, **options):
    return CosmeticPreviewRequest(
        scores=scores, ranking_policy="concern_groups", **options,
    )


class IntegratedCareTests(unittest.TestCase):
    def test_all_243_state_combinations_use_only_concern_matches(self):
        for states in product(("개선 필요", "보통", "양호"), repeat=5):
            scores = {}
            concerns = set()
            for (code, (_, higher)), state in zip(f.METRICS.items(), states):
                scores[code] = 50 if state == "보통" else (
                    20 if (state == "개선 필요") == higher else 90
                )
                if state == "개선 필요":
                    concerns.add(code)
            with self.subTest(states=states):
                result = f.run([f.product()], request(scores))
                self.assertEqual(result.deferred_metrics, [])
                self.assertEqual(result.scorable_target_count, len(concerns))
                self.assertEqual(
                    {m.metric_code for m in result.recommendations[0].matches}, concerns,
                )
                self.assertEqual(
                    [s.action for s in result.metric_strategies],
                    [{"개선 필요": "candidate", "보통": "maintain", "양호": "no_extra"}[s] for s in states],
                )

    def test_each_photo_concern_changes_candidate_selection(self):
        rows = [f.product(1, ingredients=("글리세린",)),
                f.product(2, ingredients=("나이아신아마이드",))]
        baseline = f.run(rows, request(GOOD))
        self.assertEqual([p.product_id for p in baseline.recommendations], [1])
        for code, (_, higher) in f.METRICS.items():
            scores = GOOD | {code: 20 if higher else 90}
            with self.subTest(metric=code):
                result = f.run(rows, request(scores))
                expected = [1] if code == "moisture" else [2]
                self.assertEqual([p.product_id for p in result.recommendations], expected)
                self.assertEqual(result.recommendations[0].matches[0].metric_code, code)

    def test_redness_support_survives_dryness_and_other_concerns(self):
        rows = [f.product(1, ingredients=("나이아신아마이드", "글리세린", "다이메티콘")),
                f.product(9, ingredients=("나이아신아마이드", "글리세린", "다이메티콘", "판테놀"))]
        for moisture in (20, 50, 90):
            with self.subTest(moisture=moisture):
                result = f.run(rows, request(GOOD | dict(moisture=moisture, redness=90, trouble=90)))
                self.assertEqual(result.recommendations[0].product_id, 9)
                self.assertEqual(result.recommendations[0].redness_care_ingredients, ["판테놀"])

    def test_exclusion_beats_all_five_matches_and_support(self):
        result = f.run([f.product()], request(
            dict(moisture=20, redness=90, brightness=20, trouble=90, uniformity=20),
            excluded_ingredients=["나이아신아마이드"],
        ))
        self.assertEqual(result.recommendations, [])
        self.assertEqual(result.stats.excluded_by_ingredient, 1)

    def test_photo_spots_do_not_activate_comedone_only_rule(self):
        result = f.run([f.product(ingredients=("살리실릭애씨드",))], request(GOOD | {"trouble": 90}))
        self.assertEqual(result.recommendations, [])
        self.assertEqual(result.recommendation_mode, "improvement")
        self.assertEqual(result.stats.no_matching_metric, 1)

    def test_missing_moisture_is_explicit_and_adds_no_dryness_policy(self):
        result = f.run([f.product()], request(GOOD | {"moisture": None, "trouble": 90}))
        self.assertEqual(result.metric_strategies[0].action, "unmeasured")
        self.assertEqual(result.hydration_policy["state"], "unmeasured")
        self.assertEqual([m.metric_code for m in result.recommendations[0].matches], ["trouble"])

    def test_legacy_rule_fingerprint_and_photo_deferral_remain_reproducible(self):
        path = Path(__file__).parents[1] / "app/data/cosmetic_rules_hydration_v1.json"
        bundle = RuleBundle.model_validate_json(path.read_text())
        self.assertEqual(bundle.fingerprint(), "f25a7c24e910704915efd44e7c361c89b831f13c1cab130f2f88ca6308d32574")
        result = f.run([f.product()], request(GOOD | {"trouble": 90}), bundle=bundle)
        self.assertEqual(result.deferred_metrics, ["trouble"])


class PhotoRuleMigrationTests(unittest.TestCase):
    setUp = f.ApiDatabaseTests.setUp
    tearDown = f.ApiDatabaseTests.tearDown

    def test_upgrade_preserves_old_rule_hash_and_new_history_blocks_downgrade(self):
        from app.models.cosmetic_rule import CategoryIngredient, CosmeticRuleEvidence, CosmeticRuleSet
        from app.services.cosmetic_rule_types import load_seed_bundle

        root = Path(__file__).parents[1]
        legacy = RuleBundle.model_validate_json((root / "app/data/cosmetic_rules_hydration_v1.json").read_text())
        with Session(self.engine) as db, db.begin():
            db.query(CategoryIngredient).delete()
            db.query(CosmeticRuleEvidence).delete()
            db.query(CosmeticRuleSet).delete()
            seed_rule_bundle(db, legacy, apply=True)
        with self.engine.begin() as conn:
            conn.execute(text("ALTER TABLE category_ingredients DROP COLUMN photo_eligible"))

        path = root / "alembic/versions/2026_11_06_0000-f1110a1b2c3d_cosmetic_photo_rules.py"
        spec = importlib.util.spec_from_file_location("photo_rule_migration_test", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with self.engine.begin() as conn:
            with patch.object(migration, "op", Operations(MigrationContext.configure(conn))):
                migration.upgrade()
        with Session(self.engine) as db, db.begin():
            self.assertEqual(load_database_rules(db, legacy.version).fingerprint(), legacy.fingerprint())
            seed_rule_bundle(db, load_seed_bundle(), apply=True)
            self.assertEqual(load_database_rules(db).fingerprint(), load_seed_bundle().fingerprint())
        with self.assertRaisesRegex(RuntimeError, "lossy downgrade"):
            with self.engine.begin() as conn:
                with patch.object(migration, "op", Operations(MigrationContext.configure(conn))):
                    migration.downgrade()


if __name__ == "__main__":
    unittest.main()
