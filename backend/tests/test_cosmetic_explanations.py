import asyncio
import unittest
from sqlalchemy import event
import test_cosmetic_recommendation as fixtures
from app.services.cosmetic_explanations import explain_match, shared_evidence
from scripts.audit_cosmetic_quality import scenarios


class ExplanationTests(unittest.TestCase):
    def test_each_metric_is_an_explicit_assumption(self):
        for metric in ("moisture", "redness", "brightness", "trouble", "uniformity"):
            r = explain_match(metric)
            self.assertEqual(r.assumption_status, "development_assumption")
            self.assertFalse(r.product_efficacy_verified)
            self.assertEqual(len(r.unverified_items), 3)
            self.assertIn("정규화 성분명", r.match_basis)

    def test_amount_information_not_claimed_absent_or_used(self):
        r = explain_match("moisture")
        self.assertIn("평가하지 않았습니다", r.unverified_items[0])
        self.assertIn("미표기는 0%를 뜻하지 않습니다", r.unverified_items[0])

    def test_independent_calls_do_not_share_mutable_lists(self):
        explain_match("moisture").unverified_items.clear()
        self.assertEqual(len(explain_match("moisture").unverified_items), 3)

    def test_brightness_and_uniformity_share_actual_evidence(self):
        result = fixtures.run([fixtures.product()], scenarios()["brightness_uniformity"])
        product = result.recommendations[0]
        self.assertEqual(product.match_count, 2)
        self.assertEqual(len(product.shared_evidence_groups), 1)
        self.assertEqual(product.shared_evidence_groups[0].metric_codes, ["brightness", "uniformity"])
        self.assertEqual(product.shared_evidence_groups[0].evidence_url, product.matches[0].evidence_urls[0])

    def test_multiple_ingredients_in_one_metric_not_shared_effects(self):
        result = fixtures.run([fixtures.product()], scenarios()["moisture_only"])
        self.assertEqual(result.recommendations[0].shared_evidence_groups, [])
        self.assertEqual(result.recommendations[0].match_count, 1)

    def test_no_matches_produces_no_evidence_groups(self):
        self.assertEqual(shared_evidence([]), [])
        result = fixtures.run([fixtures.product()], scenarios()["all_good"])
        self.assertEqual(result.recommendations, [])
        self.assertEqual(result.explanation_version, "cosmetic-explanations-v1")

    def test_shared_groups_are_from_actual_matches_not_fixed_names(self):
        matches = fixtures.run([fixtures.product()]).recommendations[0].matches
        a = matches[0].model_copy(update={"evidence_urls": ["https://example.org/study"]})
        b = matches[1].model_copy(update={"evidence_urls": ["https://example.org/study"]})
        self.assertEqual(shared_evidence([a, b])[0].metric_codes, sorted([a.metric_code, b.metric_code]))


class ExplanationApiTests(unittest.TestCase):
    setUp = fixtures.ApiDatabaseTests.setUp
    tearDown = fixtures.ApiDatabaseTests.tearDown

    def test_api_additive_explanations_without_new_tables_or_writes(self):
        statements = []
        event.listen(self.engine, "before_cursor_execute",
                     lambda c, cur, s, p, ctx, many: statements.append(s))
        status, body = asyncio.run(fixtures.asgi_request(fixtures.request().model_dump()))
        self.assertEqual(status, 200)
        self.assertEqual(body["explanation_version"], "cosmetic-explanations-v1")
        product = body["recommendations"][0]
        self.assertEqual(product["match_count"], 3)
        self.assertEqual(len(product["shared_evidence_groups"]), 1)
        for match in product["matches"]:
            self.assertFalse(match["interpretation"]["product_efficacy_verified"])
            self.assertTrue(match["rule_details"][0]["evidence_summary"])
        self.assertTrue(statements)
        self.assertTrue(all(s.lstrip().upper().startswith("SELECT") for s in statements))
