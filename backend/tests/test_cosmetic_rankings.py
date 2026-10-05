import unittest
from app.services.cosmetic_ranking import rank_candidates
from scripts.audit_cosmetic_quality import scenarios
import test_cosmetic_recommendation as f


def candidates():
    # 나이아신아마이드 하나의 두 지표 vs 수분+트러블의 두 그룹.
    return f.run([f.product(1, ingredients=("나이아신아마이드",)),
                  f.product(2, ingredients=("글리세린", "살리실릭애씨드")),
                  f.product(3, ingredients=("글리세린",))],
                 scenarios()["redness_filter_off"]).recommendations


class RankingTests(unittest.TestCase):
    def test_current_policy_keeps_metric_count_and_id_order(self):
        self.assertEqual([r.product.product_id for r in rank_candidates(candidates(), "metric_count")], [1,2,3])

    def test_pigment_pair_counts_once_without_losing_match_count(self):
        rows = rank_candidates(candidates(), "concern_groups")
        self.assertEqual([r.product.product_id for r in rows], [2,1,3])
        self.assertEqual((rows[1].group_count, rows[1].product.match_count), (1,2))

    def test_priority_precedes_group_count(self):
        rows = rank_candidates(candidates(), "explicit_priority", priority="brightness",
                               scorable_metrics=frozenset({"brightness","moisture","trouble"}))
        self.assertEqual(rows[0].product.product_id, 1)
        self.assertTrue(rows[0].priority_matched)

    def test_unavailable_priority_rejected_including_missing_moisture(self):
        for priority in (None,"redness","moisture","invalid"):
            with self.assertRaises(ValueError):
                rank_candidates(candidates(), "explicit_priority", priority=priority,
                                scorable_metrics=frozenset({"trouble"}))

    def test_priority_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            rank_candidates(candidates(), "concern_groups", priority="trouble")

    def test_no_match_is_fabricated_for_priority(self):
        rows = rank_candidates(candidates()[2:], "explicit_priority", priority="trouble",
                               scorable_metrics=frozenset({"trouble"}))
        self.assertFalse(rows[0].priority_matched)

    def test_one_metric_many_ingredients_does_not_gain_groups(self):
        items=f.run([f.product(ingredients=("글리세린","판테놀"))],scenarios()["moisture_only"]).recommendations
        self.assertEqual(rank_candidates(items,"concern_groups")[0].group_count,1)

    def test_excluded_product_never_reenters(self):
        items=f.run([f.product(1, ingredients=("글리세린","향료")),f.product(2)],scenarios()["five_concerns"]).recommendations
        for mode in ("metric_count","concern_groups"):
            self.assertEqual([r.product.product_id for r in rank_candidates(items,mode)],[2])

    def test_ties_count_all_candidates_and_bundle_separately(self):
        base=candidates()[2]
        items=[base.model_copy(update={"product_id":i}) for i in range(1,9)]
        items.append(base.model_copy(update={"product_id":9,"bundle_suspected":True}))
        rows=rank_candidates(items,"concern_groups")
        self.assertEqual(rows[0].tie_count,8)
        self.assertEqual(rows[-1].tie_count,1)

    def test_order_deterministic_without_mutating_input(self):
        items=candidates(); before=[p.model_dump() for p in items]
        a=rank_candidates(items,"concern_groups")
        b=rank_candidates(list(reversed(items)),"concern_groups")
        self.assertEqual(a,b)
        self.assertEqual(before,[p.model_dump() for p in items])

    def test_duplicate_ids_and_inconsistent_matches_rejected(self):
        base=candidates()[0]
        for items in ([base,base],[base.model_copy(update={"match_count":99})]):
            with self.assertRaises(ValueError):rank_candidates(items,"metric_count")

    def test_empty_candidates(self):
        self.assertEqual(rank_candidates([],"metric_count"),[])
