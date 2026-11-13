"""Regressions for concern-specific ingredients and contextual selection."""
import asyncio
from contextlib import redirect_stdout
import io
import json
import unittest
from unittest.mock import patch

from sqlalchemy import event

import test_cosmetic_recommendation as f
from app.schemas.cosmetic import CosmeticPreviewRequest
from app.services.cosmetic_usage import care_name_signals


GOOD = dict(moisture=80, redness=10, brightness=80, trouble=10, uniformity=80)


def request(**scores):
    return CosmeticPreviewRequest(scores=GOOD | scores, ranking_policy="care_context")


class CareContextTests(unittest.TestCase):
    def test_new_ingredients_have_distinct_photo_care_scopes(self):
        rows = [f.product(1, ingredients=("아스코빅애씨드",)),
                f.product(2, ingredients=("아세틸글루코사민",)),
                f.product(3, ingredients=("소듐아스코빌포스페이트",)),
                f.product(4, ingredients=("3-O-에틸아스코빅애씨드",))]
        for metric in ("brightness", "uniformity"):
            with self.subTest(metric=metric):
                result = f.run(rows, request(**{metric: 20}))
                self.assertEqual([p.product_id for p in result.recommendations], [1, 2])
                self.assertTrue(all(p.match_count == 1 for p in result.recommendations))
        result = f.run(rows, request(trouble=80))
        self.assertEqual([p.product_id for p in result.recommendations], [3])

    def test_many_ingredients_and_repeated_words_do_not_inflate_score(self):
        rows = [f.product(1, ingredients=("나이아신아마이드",), product_name="미백 세럼"),
                f.product(2, ingredients=("나이아신아마이드", "아스코빅애씨드", "아세틸글루코사민"),
                          product_name="미백 잡티 기미 브라이트닝 세럼")]
        result = f.run(rows, request(brightness=20, uniformity=20))
        self.assertEqual([p.product_id for p in result.recommendations], [1, 2])
        self.assertEqual([p.match_count for p in result.recommendations], [2, 2])
        self.assertEqual([p.matched_group_count for p in result.recommendations], [1, 1])
        self.assertEqual(result.tie_groups[0].total, 2)

    def test_same_ingredient_products_follow_the_actual_concern(self):
        rows = [f.product(1, ingredients=("나이아신아마이드",), product_name="트러블 관리 세럼"),
                f.product(9, ingredients=("나이아신아마이드",), product_name="미백 잡티 세럼")]
        tone = f.run(rows, request(brightness=20))
        trouble = f.run(rows, request(trouble=80))
        self.assertEqual([p.product_id for p in tone.recommendations], [9, 1])
        self.assertEqual([p.product_id for p in trouble.recommendations], [1, 9])
        self.assertEqual(tone.recommendations[0].product_name_claims, {"pigmentation": ["미백", "잡티"]})

    def test_name_claim_cannot_replace_matching_ingredient(self):
        result = f.run([f.product(1, ingredients=("정제수",), product_name="미백 잡티 세럼")], request(brightness=20))
        self.assertEqual(result.recommendations, [])

    def test_unrelated_claim_does_not_get_a_priority(self):
        rows = [f.product(1, ingredients=("나이아신아마이드",), product_name="기본 세럼"),
                f.product(2, ingredients=("나이아신아마이드",), product_name="수분 보습 장벽 세럼")]
        result = f.run(rows, request(brightness=20))
        self.assertEqual([p.product_id for p in result.recommendations], [1, 2])
        self.assertTrue(all(not p.product_name_claims for p in result.recommendations))

    def test_gifts_do_not_supply_the_main_product_claim(self):
        for name in ("미백 세럼 (+여드름 토너 증정)", "[트러블 세럼 샘플 증정] 미백 크림", "미백 세럼 + 트러블 토너"):
            with self.subTest(name=name):
                claims, _ = care_name_signals(name)
                self.assertEqual(claims, {"pigmentation": ["미백"]})
        _, exfoliation = care_name_signals("Alpha moisturizing cream")
        self.assertEqual(exfoliation, [])

    def test_care_context_checks_dryness_and_redness_before_name_priority(self):
        rows = [f.product(1, ingredients=("나이아신아마이드", "글리세린", "판테놀"), product_name="트러블 BHA 각질 세럼"),
                f.product(9, ingredients=("나이아신아마이드", "글리세린", "판테놀"), product_name="기본 세럼")]
        for state in (dict(moisture=20, trouble=80), dict(redness=80, trouble=80)):
            with self.subTest(state=state):
                result = f.run(rows, request(**state))
                self.assertEqual([p.product_id for p in result.recommendations], [9, 1])
                self.assertTrue(result.recommendations[1].context_cautions)
        result = f.run(rows, request(trouble=80))
        self.assertEqual([p.product_id for p in result.recommendations], [1, 9])
        self.assertTrue(all(not p.context_cautions for p in result.recommendations))

    def test_exclusion_wins_over_product_purpose(self):
        body = request(brightness=20).model_copy(update={"excluded_ingredients": ["향료"]})
        rows = [f.product(1, ingredients=("나이아신아마이드", "향료"), product_name="미백 세럼"),
                f.product(2, ingredients=("나이아신아마이드",), product_name="기본 세럼")]
        result = f.run(rows, body)
        self.assertEqual([p.product_id for p in result.recommendations], [2])
        self.assertEqual(result.stats.excluded_by_ingredient, 1)

    def test_legacy_ranking_modes_keep_their_contract(self):
        rows = [f.product(1, ingredients=("나이아신아마이드",), product_name="기본 세럼"),
                f.product(9, ingredients=("나이아신아마이드",), product_name="미백 세럼")]
        for mode in ("metric_count", "concern_groups"):
            result = f.run(rows, request(brightness=20).model_copy(update={"ranking_policy": mode}))
            self.assertEqual([p.product_id for p in result.recommendations], [1, 9])
            self.assertTrue(all(not p.product_name_claims for p in result.recommendations))


class CareContextApiTests(unittest.TestCase):
    setUp = f.ApiDatabaseTests.setUp
    tearDown = f.ApiDatabaseTests.tearDown

    def test_new_rule_version_and_context_round_trip_without_database_writes(self):
        statements = []
        event.listen(self.engine, "before_cursor_execute", lambda c, cur, sql, p, ctx, many: statements.append(sql))
        status, data = asyncio.run(f.asgi_request(request(brightness=20).model_dump()))
        self.assertEqual(status, 200)
        self.assertEqual(data["rule_version"], "cosmetic-rules-2026-11-06-integrated-v2")
        self.assertEqual(data["ranking_policy"], "care_context")
        self.assertEqual(data["recommendations"][0]["context_cautions"], [])
        self.assertTrue(all(sql.lstrip().upper().startswith("SELECT") for sql in statements))

    def test_replay_tool_uses_the_real_api_contract_for_all_sixteen_cases(self):
        from scripts import verify_cosmetic_personalization as replay

        def api_response(request, timeout):
            self.assertEqual(timeout, 60)
            status, data = asyncio.run(f.asgi_request(json.loads(request.data)))
            self.assertEqual(status, 200)
            return io.BytesIO(json.dumps(data).encode("utf-8"))

        output = io.StringIO()
        with patch("sys.argv", ["verify_cosmetic_personalization.py", "--api", "http://test"]), \
                patch.object(replay, "urlopen", side_effect=api_response) as transport, \
                redirect_stdout(output):
            replay.main()
        self.assertEqual(transport.call_count, 16)
        self.assertIn("PASS: 16 API/engine scenarios completed", output.getvalue())


if __name__ == "__main__":
    unittest.main()
