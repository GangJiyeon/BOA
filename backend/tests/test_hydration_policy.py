import asyncio, unittest
from sqlalchemy import event
import test_cosmetic_recommendation as f
from app.services.cosmetic_pagination import StaleRecommendationError


def request(moisture=20,**changes):
    return f.request(scores=dict(moisture=moisture,redness=10,brightness=90,trouble=10,uniformity=90),**changes)


class HydrationPolicyTests(unittest.TestCase):
    def test_low_prefers_complementary_support_without_inflating_metric_count(self):
        rows=[f.product(1,ingredients=('글리세린',)),f.product(2,ingredients=('다이메티콘',)),f.product(9,ingredients=('글리세린','다이메티콘'))]
        r=f.run(rows,request())
        self.assertEqual(r.hydration_policy['state'],'low')
        self.assertEqual([p.product_id for p in r.recommendations],[9,1,2])
        self.assertTrue(all(p.match_count==1 for p in r.recommendations))
        self.assertEqual(r.recommendations[0].hydration_support,['humectant','water_loss_reduction'])
        self.assertEqual(r.recommendations[0].matches[0].ingredients,['글리세린','다이메티콘'])

    def test_normal_and_sufficient_use_explicit_maintenance_rules(self):
        for score,state in ((50,'normal'),(80,'sufficient')):
            with self.subTest(state=state):
                r=f.run([f.product(1,ingredients=('다이메티콘',))],request(score))
                self.assertEqual(r.hydration_policy['state'],state)
                self.assertEqual(r.recommendation_mode,'daily_care')
                p=r.recommendations[0];self.assertEqual(p.match_count,0)
                self.assertEqual(p.daily_care_rules[0].effect,'maintain')
                self.assertEqual(p.daily_care_ingredients,['다이메티콘'])
                self.assertFalse(r.hydration_policy['dryness_exclusion_enabled'])

    def test_dryness_exclusion_requires_both_low_state_and_opt_in(self):
        rows=[f.product(i,ingredients=('글리세린',n)) for i,n in enumerate(['향료','에탄올','변성알코올','세틸알코올','스테아릴알코올'],1)]
        allowed=f.run(rows,request(avoid_dryness_triggers=False))
        self.assertEqual(allowed.stats.eligible_products,5)
        low=f.run(rows,request(avoid_dryness_triggers=True))
        self.assertEqual([p.product_id for p in low.recommendations],[4,5])
        self.assertEqual(set(low.applied_exclusions),{'향료','에탄올','변성알코올'})
        self.assertEqual(low.stats.excluded_by_ingredient,3)
        for score in (50,80):
            r=f.run(rows,request(score,avoid_dryness_triggers=True))
            self.assertEqual(r.stats.eligible_products,5);self.assertEqual(r.applied_exclusions,[])

    def test_user_exclusion_wins_over_complementary_support(self):
        r=f.run([f.product(1,ingredients=('글리세린',)),f.product(9,ingredients=('글리세린','다이메티콘','향료'))],request(excluded_ingredients=['향료']))
        self.assertEqual([p.product_id for p in r.recommendations],[1])

    def test_high_hydration_does_not_become_an_oil_or_occlusive_ban(self):
        r=f.run([f.product(1,ingredients=('페트롤라툼',))],request(80,avoid_dryness_triggers=True))
        self.assertEqual(r.stats.eligible_products,1);self.assertEqual(r.applied_exclusions,[])
        self.assertEqual(r.recommendations[0].match_count,0)

    def test_missing_hydration_is_not_classified_or_excluded(self):
        r=f.run([f.product()],request(None,avoid_dryness_triggers=True))
        self.assertEqual(r.hydration_policy['state'],'unmeasured')
        self.assertFalse(r.hydration_policy['dryness_exclusion_enabled'])
        self.assertEqual(r.missing_metrics,['moisture'])

    def test_redness_and_dryness_options_are_independent(self):
        scores=dict(moisture=80,redness=80,brightness=90,trouble=10,uniformity=90)
        p=f.product(1,ingredients=('글리세린','향료'))
        r=f.run([p],f.request(scores=scores,avoid_redness_triggers=True,avoid_dryness_triggers=False))
        self.assertEqual(r.stats.excluded_by_ingredient,1)
        r=f.run([p],f.request(scores=scores,avoid_redness_triggers=False,avoid_dryness_triggers=True))
        self.assertEqual(r.stats.eligible_products,1)

    def test_hydration_policy_participates_in_pagination_snapshot(self):
        rows=[f.product(i) for i in range(1,8)]
        r=f.run(rows,request())
        with self.assertRaises(StaleRecommendationError):
            f.run(rows,request(avoid_dryness_triggers=True,tie_group=r.tie_groups[0].key,tie_offset=5,snapshot_token=r.snapshot_token))


class HydrationApiTests(unittest.TestCase):
    setUp=f.ApiDatabaseTests.setUp
    tearDown=f.ApiDatabaseTests.tearDown
    def test_rule_database_api_returns_state_and_optional_exclusions_without_writes(self):
        sql=[];event.listen(self.engine,'before_cursor_execute',lambda c,cu,s,p,co,m:sql.append(s))
        status,data=asyncio.run(f.asgi_request(request(avoid_dryness_triggers=True).model_dump()))
        self.assertEqual(status,200,data)
        self.assertEqual(data['hydration_policy']['state'],'low')
        self.assertEqual(set(data['applied_exclusions']),{'향료','에탄올','변성알코올'})
        self.assertEqual(data['rule_version'],'cosmetic-rules-2026-10-28-hydration-v1')
        self.assertTrue(all(s.lstrip().upper().startswith('SELECT') for s in sql))


class HydrationMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_prior_rule_version_and_blocks_lossy_downgrade(self):
        import importlib.util
        from pathlib import Path
        from unittest.mock import patch
        from sqlalchemy import create_engine, select, func
        from sqlalchemy.orm import Session
        from alembic.operations import Operations
        from alembic.migration import MigrationContext
        from app.db.base import Base
        from app.models.cosmetic import Ingredient
        from app.models.skin import SkinMetric,SkinMetricCategory
        from app.models.cosmetic_rule import CategoryIngredient
        from app.services.cosmetic_rule_repository import seed_rule_bundle,load_database_rules
        from app.services.cosmetic_rule_types import RuleBundle,load_seed_bundle
        from scripts.seed_skin_metrics import seed_metrics
        root=Path(__file__).parents[1]
        def migration(name):
            spec=importlib.util.spec_from_file_location(name,root/'alembic/versions'/name)
            result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
        old=migration('2026_10_05_0000-c0510a1b2c3d_create_cosmetic_rule_tables.py')
        new=migration('2026_10_28_0000-f0910a1b2c3d_hydration_policy.py')
        engine=create_engine('sqlite://')
        try:
            Base.metadata.create_all(engine,tables=[SkinMetric.__table__,SkinMetricCategory.__table__,Ingredient.__table__])
            with engine.begin() as conn:
                with patch.object(old,'op',Operations(MigrationContext.configure(conn))):old.upgrade()
            legacy=RuleBundle.model_validate_json((root/'app/data/cosmetic_rules_v1.json').read_text())
            with Session(engine) as db,db.begin():
                seed_metrics(db)
                for i,name in enumerate(sorted({r.ingredient for r in load_seed_bundle().rules}),1):db.add(Ingredient(ingredient_id=i,ingredient_name=name))
                db.flush();seed_rule_bundle(db,legacy,apply=True)
            with engine.begin() as conn:
                with patch.object(new,'op',Operations(MigrationContext.configure(conn))):new.upgrade()
            with Session(engine) as db,db.begin():
                self.assertEqual(load_database_rules(db,legacy.version).fingerprint(),legacy.fingerprint())
                seed_rule_bundle(db,load_seed_bundle(),apply=True)
                self.assertEqual(db.scalar(select(func.count()).select_from(CategoryIngredient)),55)
            with self.assertRaisesRegex(RuntimeError,'lossy downgrade'):
                with engine.begin() as conn:
                    with patch.object(new,'op',Operations(MigrationContext.configure(conn))):new.downgrade()
            with Session(engine) as db:self.assertEqual(db.scalar(select(func.count()).select_from(CategoryIngredient)),55)
        finally:engine.dispose()
