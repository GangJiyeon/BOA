import asyncio
from dataclasses import replace
import unittest

from pydantic import ValidationError
from sqlalchemy import event

import test_cosmetic_recommendation as f
from app.services.cosmetic_pagination import PaginationInputError, StaleRecommendationError


def next_request(body, result, group=None):
    group = group or result.tie_groups[0]
    return f.request(**(body.model_dump() | {
        "tie_group": group.key, "tie_offset": group.next_offset,
        "snapshot_token": result.snapshot_token,
    }))


class TiePaginationTests(unittest.TestCase):
    def test_all_31_ties_once_for_every_policy(self):
        items = [f.product(i, ingredients=("글리세린",)) for i in range(1, 32)]
        for mode in ("metric_count", "concern_groups", "explicit_priority"):
            with self.subTest(mode=mode):
                body = f.request(ranking_policy=mode, **({"priority_metric": "moisture"} if mode == "explicit_priority" else {}))
                page = f.run(items, body)
                self.assertEqual([p.product_id for p in page.recommendations], [1, 2, 3, 4, 5])
                ids = [p.product_id for p in page.recommendations]
                token = page.snapshot_token
                while page.tie_groups[0].next_offset is not None:
                    page = f.run(list(reversed(items)), next_request(body, page))
                    self.assertEqual(page.snapshot_token, token)
                    self.assertLessEqual(len(page.recommendations), 5)
                    ids.extend(p.product_id for p in page.recommendations)
                self.assertEqual(ids, list(range(1, 32)))
                self.assertEqual(page.tie_groups[0].total, 31)

    def test_partial_initial_group_does_not_skip_or_cross_bundle_boundary(self):
        items = [f.product(1), f.product(2)]
        items += [f.product(i, ingredients=("글리세린",)) for i in range(3, 11)]
        items += [f.product(11, ingredients=("글리세린",), product_name="테스트 세트")]
        body = f.request()
        first = f.run(items, body)
        self.assertEqual([g.total for g in first.tie_groups], [2, 8])
        self.assertEqual(first.tie_groups[1].next_offset, 3)
        page = f.run(items, next_request(body, first, first.tie_groups[1]))
        self.assertEqual([p.product_id for p in page.recommendations], [6, 7, 8, 9, 10])
        self.assertIsNone(page.tie_groups[0].next_offset)

    def test_equal_score_different_ingredients_still_same_group(self):
        result = f.run([f.product(1, ingredients=("글리세린",)), f.product(2, ingredients=("살리실릭애씨드",))])
        self.assertEqual(len(result.tie_groups), 1)
        self.assertEqual(result.tie_groups[0].total, 2)

    def test_priority_membership_separates_otherwise_equal_groups(self):
        result = f.run([f.product(1, ingredients=("글리세린",)), f.product(2, ingredients=("살리실릭애씨드",))],
                       f.request(ranking_policy="explicit_priority", priority_metric="moisture"))
        self.assertEqual([g.total for g in result.tie_groups], [1, 1])

    def test_stale_input_and_product_details_rejected(self):
        items = [f.product(i) for i in range(1, 8)]
        body = f.request()
        page_body = next_request(body, f.run(items, body))
        with self.assertRaises(StaleRecommendationError):
            f.run(items, page_body.model_copy(update={"avoid_redness_triggers": False}))
        with self.assertRaises(StaleRecommendationError):
            f.run(items[:-1] + [replace(items[-1], brand_name="변경된 브랜드")], page_body)
        with self.assertRaises(StaleRecommendationError):
            f.run(items[:-1], page_body)

    def test_snapshot_tracks_rules_and_thresholds(self):
        from app.services.cosmetic_rule_types import load_seed_bundle
        from app.services.cosmetic_recommendation import recommend
        items = [f.product(i) for i in range(1, 8)]
        body = f.request()
        page_body = next_request(body, f.run(items, body))
        bundle = load_seed_bundle().model_copy(update={"description": "새 규칙 설명"})
        with self.assertRaises(StaleRecommendationError):
            recommend(page_body, f.definitions(), items, f.KNOWN, rule_bundle=bundle)
        defs = f.definitions()
        defs[0] = replace(defs[0], name="수분 지표")
        with self.assertRaises(StaleRecommendationError):
            f.run(items, page_body, defs)

    def test_empty_catalog_and_last_group(self):
        self.assertEqual(f.run([]).tie_groups, [])
        result = f.run([f.product()])
        self.assertIsNone(result.tie_groups[0].next_offset)

    def test_invalid_page_contract(self):
        for fields in ({"tie_offset": 1}, {"tie_group": "g-1"}, {"snapshot_token": "a" * 64},
                       {"tie_offset": -1}, {"tie_offset": True},
                       {"tie_group": "oops", "snapshot_token": "a" * 64}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                f.request(**fields)
        first = f.run([f.product()])
        for group, offset in (("g-999", 0), ("g-1", 1)):
            with self.assertRaises(PaginationInputError):
                f.run([f.product()], f.request(tie_group=group, tie_offset=offset, snapshot_token=first.snapshot_token))


class TiePaginationApiTests(unittest.TestCase):
    setUp = f.ApiDatabaseTests.setUp
    tearDown = f.ApiDatabaseTests.tearDown

    def test_page_is_read_only_and_stale_returns_409(self):
        status, first = asyncio.run(f.asgi_request(f.request().model_dump()))
        self.assertEqual(status, 200)
        statements = []
        event.listen(self.engine, "before_cursor_execute",
                     lambda conn, cursor, statement, parameters, context, executemany: statements.append(statement))
        body = f.request(tie_group=first["tie_groups"][0]["key"], snapshot_token=first["snapshot_token"]).model_dump()
        status, page = asyncio.run(f.asgi_request(body))
        self.assertEqual(status, 200)
        self.assertEqual(page["recommendations"], first["recommendations"])
        self.assertTrue(statements)
        self.assertTrue(all(s.lstrip().upper().startswith("SELECT") for s in statements))
        status, _ = asyncio.run(f.asgi_request(body | {"snapshot_token": "0" * 64}))
        self.assertEqual(status, 409)

    def test_invalid_group_returns_422(self):
        _, first = asyncio.run(f.asgi_request(f.request().model_dump()))
        status, _ = asyncio.run(f.asgi_request(f.request(tie_group="g-999", snapshot_token=first["snapshot_token"]).model_dump()))
        self.assertEqual(status, 422)
