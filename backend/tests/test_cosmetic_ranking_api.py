import asyncio
import unittest

from pydantic import ValidationError
from sqlalchemy import event

import test_cosmetic_recommendation as f


def products():
    return [f.product(1, ingredients=("나이아신아마이드",)),
            f.product(2, ingredients=("글리세린", "살리실릭애씨드")),
            f.product(3, ingredients=("글리세린",))]


class RankingEngineIntegrationTests(unittest.TestCase):
    def test_default_preserves_legacy_order(self):
        r = f.run(products())
        self.assertEqual([p.product_id for p in r.recommendations], [1, 2, 3])
        self.assertEqual(r.ranking_policy, "metric_count")
        self.assertEqual(r.recommendations[0].match_count, 2)
        self.assertEqual(r.recommendations[0].matched_group_count, 1)

    def test_groups_change_order_without_rewriting_metric_matches(self):
        r = f.run(products(), f.request(ranking_policy="concern_groups"))
        self.assertEqual([p.product_id for p in r.recommendations], [2, 1, 3])
        self.assertEqual(r.recommendations[1].match_count, 2)
        self.assertEqual(r.recommendations[1].ranking_tie_count, 2)
        self.assertIn("밝기·균일도 통합", r.ranking_basis)

    def test_explicit_priority_changes_order(self):
        r = f.run(products(), f.request(ranking_policy="explicit_priority", priority_metric="moisture"))
        self.assertEqual([p.product_id for p in r.recommendations], [2, 3, 1])
        self.assertEqual([p.priority_matched for p in r.recommendations], [True, True, False])

    def test_rank_whole_catalog_before_top_five(self):
        items = [f.product(i, ingredients=("나이아신아마이드",)) for i in range(1, 8)]
        items.append(f.product(99, ingredients=("글리세린",)))
        r = f.run(items, f.request(ranking_policy="explicit_priority", priority_metric="moisture"))
        self.assertEqual(r.recommendations[0].product_id, 99)
        self.assertEqual(r.recommendations[1].ranking_tie_count, 7)
        self.assertEqual(r.stats.eligible_products, 8)

    def test_user_exclusion_precedes_priority(self):
        r = f.run(products(), f.request(ranking_policy="explicit_priority", priority_metric="moisture",
                                       excluded_ingredients=["글리세린"]))
        self.assertEqual([p.product_id for p in r.recommendations], [1])
        self.assertFalse(r.recommendations[0].priority_matched)
        self.assertTrue(any("우선 고민에 매칭되는 후보가 없어" in n for n in r.notices))

    def test_missing_normal_or_deferred_priority_rejected_even_empty_catalog(self):
        for metric, scores in (("moisture", f.request().scores.model_dump() | {"moisture": None}),
                               ("moisture", f.request().scores.model_dump() | {"moisture": 90}),
                               ("redness", f.request().scores.model_dump())):
            with self.subTest(metric=metric, scores=scores), self.assertRaises(f.RecommendationInputError):
                f.run([], f.request(scores=scores, ranking_policy="explicit_priority", priority_metric=metric))

    def test_policy_priority_contract(self):
        for fields in ({"ranking_policy": "explicit_priority"}, {"priority_metric": "moisture"},
                       {"ranking_policy": "concern_groups", "priority_metric": "moisture"},
                       {"ranking_policy": "unknown"}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                f.request(**fields)

    def test_empty_result_still_explains_policy(self):
        r = f.run([], f.request(ranking_policy="concern_groups"))
        self.assertEqual(r.recommendations, [])
        self.assertEqual(r.ranking_policy, "concern_groups")
        self.assertIsNotNone(r.empty_reason)


class RankingApiTests(unittest.TestCase):
    setUp = f.ApiDatabaseTests.setUp
    tearDown = f.ApiDatabaseTests.tearDown

    def test_database_api_serializes_policy_without_writes(self):
        statements = []
        event.listen(self.engine, "before_cursor_execute",
                     lambda conn, cursor, statement, parameters, context, executemany: statements.append(statement))
        status, data = asyncio.run(f.asgi_request(f.request(ranking_policy="concern_groups").model_dump()))
        self.assertEqual(status, 200)
        self.assertEqual(data["ranking_policy"], "concern_groups")
        self.assertEqual(data["ranking_policy_version"], "cosmetic-ranking-v1")
        self.assertEqual(data["recommendations"][0]["matched_group_count"], 2)
        self.assertEqual(data["recommendations"][0]["match_count"], 3)
        self.assertTrue(statements)
        self.assertTrue(all(s.lstrip().upper().startswith("SELECT") for s in statements))

    def test_unavailable_priority_returns_422(self):
        status, data = asyncio.run(f.asgi_request(f.request(ranking_policy="explicit_priority", priority_metric="redness").model_dump()))
        self.assertEqual(status, 422)
        self.assertIn("활성 매칭 규칙", data["detail"])

    def test_malformed_priority_request_returns_422(self):
        body = f.request().model_dump() | {"ranking_policy": "explicit_priority"}
        status, _ = asyncio.run(f.asgi_request(body))
        self.assertEqual(status, 422)
