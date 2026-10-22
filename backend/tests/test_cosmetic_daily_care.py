"""일상 관리 제안은 개선 점수·누락값 추정·배제 우회를 만들지 않는다."""
import asyncio
import unittest

from sqlalchemy import event

import test_cosmetic_recommendation as f
from app.schemas.cosmetic import CosmeticPreviewRequest
from app.services.cosmetic_pagination import StaleRecommendationError
from app.services.cosmetic_recommendation import recommend
from app.services.cosmetic_rule_types import load_seed_bundle


GOOD = dict(moisture=None, redness=6, brightness=68, trouble=9, uniformity=100)


def request(**changes):
    return CosmeticPreviewRequest.model_validate(dict(scores=GOOD) | changes)


class DailyCareTests(unittest.TestCase):
    def test_screenshot_scores_produce_care_without_inventing_moisture(self):
        result = f.run([f.product()], request())
        self.assertEqual(result.recommendation_mode, "daily_care")
        self.assertEqual(result.daily_care_reason, "no_improvement_targets")
        self.assertEqual((result.target_count, result.scorable_target_count), (0, 0))
        self.assertEqual(result.missing_metrics, ["moisture"])
        self.assertNotIn("moisture", [a.code for a in result.assessments])
        self.assertIn("수분은 미측정", result.recommendation_notice)
        item = result.recommendations[0]
        self.assertEqual((item.match_count, item.matches, item.matched_group_count), (0, [], 0))
        self.assertEqual(item.daily_care_ingredients, ["글리세린", "판테놀"])
        self.assertEqual({r.ingredient for r in item.daily_care_rules}, set(item.daily_care_ingredients))

    def test_good_normal_and_missing_moisture_do_not_change_basis(self):
        for moisture in (None, 50, 90):
            with self.subTest(moisture=moisture):
                r = f.run([f.product()], request(scores=GOOD | {"moisture": moisture}))
                self.assertEqual(r.recommendation_mode, "daily_care")
                self.assertEqual(r.recommendations[0].match_count, 0)

    def test_deferred_photo_concerns_not_claimed_as_improved(self):
        r = f.run([f.product()], request(scores=GOOD | dict(brightness=20, trouble=92, uniformity=20)))
        self.assertEqual(r.daily_care_reason, "no_supported_matching_rules")
        self.assertEqual(set(r.deferred_metrics), {"brightness", "trouble", "uniformity"})
        self.assertEqual(r.recommendations[0].matches, [])

    def test_measured_dryness_keeps_existing_improvement_path(self):
        r = f.run([f.product()], request(scores=GOOD | {"moisture": 20}))
        self.assertEqual(r.recommendation_mode, "improvement")
        self.assertIsNone(r.daily_care_reason)
        self.assertEqual(r.recommendations[0].match_count, 1)
        self.assertEqual(r.recommendations[0].daily_care_ingredients, [])

    def test_exclusions_and_usage_filters_partition_catalog(self):
        rows = [f.product(1), f.product(2, category="unknown"), f.product(3, parse_status="review"),
                f.product(4, ingredients=("판테놀", "향료")), f.product(5, ingredients=("정제수",)),
                f.product(6, product_name="워시오프 세럼")]
        r = f.run(rows, request(excluded_ingredients=["향료"], avoid_redness_triggers=False))
        self.assertEqual([p.product_id for p in r.recommendations], [1])
        stats = r.stats.model_dump()
        self.assertEqual(stats.pop("total_products"), sum(stats.values()))
        self.assertEqual(r.stats.no_matching_metric, 0)
        self.assertEqual(r.stats.no_daily_care_ingredient, 1)

    def test_redness_opt_in_applies_to_daily_care(self):
        p = f.product(ingredients=("판테놀", "향료"))
        for red, enabled, count in ((80, True, 0), (80, False, 1), (10, True, 1)):
            with self.subTest(red=red, enabled=enabled):
                r = f.run([p], request(scores=GOOD | {"redness": red}, avoid_redness_triggers=enabled))
                self.assertEqual(len(r.recommendations), count)
                self.assertEqual(r.recommendation_mode, "daily_care")
                if count == 0:
                    self.assertEqual(r.stats.excluded_by_ingredient, 1)

    def test_exact_active_moisture_rules_only(self):
        names = ["판 테 놀", "판테닐에틸에터", "세라마이드엔피", "소듐하이알루로네이트", "살리실릭애씨드", "나이아신아마이드"]
        r = f.run([f.product(i, ingredients=(n,)) for i, n in enumerate(names, 1)], request())
        self.assertEqual([p.product_id for p in r.recommendations], [1])
        self.assertEqual(r.stats.no_daily_care_ingredient, 5)

    def test_deactivated_rules_are_not_reenabled_for_daily_care(self):
        bundle = load_seed_bundle()
        bundle = bundle.model_copy(update={"rules": tuple(r.model_copy(update={"status": "deferred"})
                                   if r.metric == "moisture" else r for r in bundle.rules)})
        result = recommend(request(), f.definitions(), [f.product()], f.KNOWN, rule_bundle=bundle)
        self.assertEqual(result.recommendations, [])
        self.assertIn("활성 보습 성분 규칙", result.empty_reason)

    def test_no_fallback_when_improvement_products_excluded_or_absent(self):
        for rows, fields in (([f.product()], {"excluded_ingredients": ["판테놀"]}),
                             ([f.product(ingredients=("정제수",))], {})):
            r = f.run(rows, request(scores=GOOD | {"moisture": 20}, **fields))
            self.assertEqual(r.recommendation_mode, "improvement")
            self.assertEqual(r.recommendations, [])

    def test_category_filter_and_empty_catalog_are_explicit(self):
        rows = [f.product(1, category="toner"), f.product(2, category="moisturizer"), f.product(3)]
        for category, expected in ((None, [1, 2, 3]), ("toner", [1]), ("moisturizer", [2]), ("serum", [3])):
            r = f.run(rows, request(category=category))
            self.assertEqual([p.product_id for p in r.recommendations], expected)
        self.assertIn("제품 데이터", f.run([], request()).empty_reason)

    def test_care_is_not_ranked_by_ingredient_count(self):
        rows = [f.product(3, ingredients=("글리세린", "판테놀")), f.product(2, ingredients=("글리세린",)),
                f.product(1, product_name="세럼 기획")]
        r = f.run(rows, request(ranking_policy="concern_groups"))
        self.assertEqual([p.product_id for p in r.recommendations], [2, 3, 1])
        self.assertEqual([p.ranking_tie_count for p in r.recommendations], [2, 2, 1])
        self.assertEqual(r.ranking_policy_version, "cosmetic-daily-care-v1")

    def test_daily_pagination_and_changed_conditions(self):
        rows = [f.product(i) for i in range(1, 9)]
        first = f.run(rows, request())
        page_fields = dict(tie_group=first.tie_groups[0].key, tie_offset=5, snapshot_token=first.snapshot_token)
        second = f.run(rows, request(**page_fields))
        self.assertEqual([p.product_id for p in second.recommendations], [6, 7, 8])
        self.assertIsNone(second.tie_groups[0].next_offset)
        self.assertEqual(first.snapshot_token, second.snapshot_token)
        for changes in ({"scores": GOOD | {"moisture": 20}}, {"category": "serum"}, {"excluded_ingredients": ["판테놀"]}):
            with self.subTest(changes=changes), self.assertRaises(StaleRecommendationError):
                f.run(rows, request(**page_fields, **changes))


class DailyCareApiTests(unittest.TestCase):
    setUp = f.ApiDatabaseTests.setUp
    tearDown = f.ApiDatabaseTests.tearDown

    def test_score_array_to_database_products_without_writes(self):
        rows = [dict(metric_code=code, metric_name=f.METRICS[code][0], score=score,
                     category_name="양호", higher_is_better=f.METRICS[code][1])
                for code, score in GOOD.items() if score is not None]
        statements = []
        event.listen(self.engine, "before_cursor_execute", lambda conn, cursor, statement, parameters, context, executemany: statements.append(statement))
        status, data = asyncio.run(f.asgi_request({"scores": rows}))
        self.assertEqual(status, 200)
        self.assertEqual(data["recommendation_mode"], "daily_care")
        self.assertEqual(data["recommendations"][0]["daily_care_ingredients"], ["판테놀"])
        self.assertEqual(data["recommendations"][0]["match_count"], 0)
        self.assertTrue(all(s.lstrip().upper().startswith("SELECT") for s in statements))

    def test_daily_care_exclusions_not_bypassed_in_api(self):
        status, data = asyncio.run(f.asgi_request(request(excluded_ingredients=["판테놀"]).model_dump()))
        self.assertEqual(status, 200)
        self.assertEqual(data["recommendations"], [])
        self.assertEqual(data["stats"]["excluded_by_ingredient"], 1)


if __name__ == "__main__":
    unittest.main()
