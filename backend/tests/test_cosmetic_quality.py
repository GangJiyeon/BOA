"""효능 검증이 아닌 판정·순위 설명·감사 도구의 회귀 테스트."""

import asyncio
from dataclasses import replace
import unittest
import test_cosmetic_recommendation as base_tests

from sqlalchemy.orm import Session

from app.models.skin import SkinMetricCategory, SkinMetric
from app.services.cosmetic_recommendation import RecommendationConfigurationError, assess_scores
from app.services.cosmetic_rule_types import load_seed_bundle
from scripts.audit_cosmetic_quality import audit_rules, audit_scenario, scenarios
from test_cosmetic_recommendation import (
    KNOWN, definitions, product, request, run, asgi_request,
)


class QualityTests(unittest.TestCase):
    def test_improvement_band_must_be_at_unhealthy_end(self):
        for index, categories in [
            (0, (("양호", 0, 33), ("보통", 34, 66), ("개선 필요", 67, 100))),
            (1, (("개선 필요", 0, 33), ("보통", 34, 66), ("양호", 67, 100))),
            (0, (("양호", 0, 33), ("개선 필요", 34, 66), ("보통", 67, 100))),
            (1, (("개선 필요", 0, 100),)),
        ]:
            defs = definitions()
            defs[index] = replace(defs[index], categories=categories)
            with self.subTest(index=index, categories=categories), self.assertRaises(RecommendationConfigurationError):
                assess_scores(request(), defs)

    def test_duplicate_metric_definitions_rejected(self):
        with self.assertRaises(RecommendationConfigurationError):
            assess_scores(request(), [*definitions(), definitions()[0]])

    def test_custom_lower_is_better_threshold_supported(self):
        defs = definitions()
        defs[1] = replace(defs[1], categories=(("양호", 0, 50), ("보통", 51, 80), ("개선 필요", 81, 100)))
        self.assertFalse(assess_scores(request(), defs)[1].needs_improvement)

    def test_ranking_ties_count_entire_catalog_and_separate_bundles(self):
        products = [product(i) for i in range(1, 9)] + [product(9, product_name="세럼 기획")]
        result = run(products)
        self.assertEqual([p.ranking_tie_count for p in result.recommendations], [8] * 5)
        self.assertEqual(result.stats.eligible_products, 9)
        result = run([products[0], products[-1]])
        self.assertEqual([p.ranking_tie_count for p in result.recommendations], [1, 1])

    def test_redness_only_explains_rule_gap_not_product_failure(self):
        result = run([product()], scenarios()["redness_only"])
        self.assertIn("활성 매칭 규칙", result.empty_reason)
        self.assertIn("부적합하다는 뜻은 아닙니다", result.empty_reason)
        self.assertEqual(result.scorable_target_count, 0)

    def test_same_band_severity_does_not_invent_weight(self):
        products = [product(1), product(2, ingredients=("글리세린",))]
        low = run(products, scenarios()["concern_boundary"])
        extreme = run(products, scenarios()["extreme_concerns"])
        self.assertEqual(low.recommendations, extreme.recommendations)

    def test_shared_evidence_is_reported_not_an_independent_effect(self):
        products = [product(1, ingredients=("나이아신아마이드",))]
        report = audit_scenario(scenarios()["brightness_uniformity"], products, KNOWN,
                                {1: "source-1"}, load_seed_bundle())
        self.assertEqual(report["top5"][0]["match_count"], 2)
        self.assertEqual(report["shared_evidence_multi_metric_products"], 1)

    def test_audit_reconstructs_all_candidates_not_only_top_five(self):
        products = [product(i) for i in reversed(range(1, 13))]
        report = audit_scenario(request(), products, KNOWN, {i: str(i) for i in range(1, 13)}, load_seed_bundle())
        self.assertEqual(report["score_histogram"], {4: 12})
        self.assertEqual(report["ranking_groups"][0]["products"], 12)
        self.assertEqual([p["source_product_id"] for p in report["top5"]], ["1", "2", "3", "4", "5"])

    def test_rule_coverage_counts_product_once_with_normalized_names(self):
        report = audit_rules([product(ingredients=("글리세린", "글 리 세 린", "정제수"))],
                             KNOWN | {"정제수"}, load_seed_bundle())
        glycerin = next(r for r in report["ingredients"] if r["ingredient"] == "글리세린")
        self.assertEqual(glycerin["linked_products_before_filters"], 1)
        self.assertEqual(report["unreviewed_frequent_ingredients"],
                         [{"ingredient": "정제수", "linked_products_before_filters": 1}])

    def test_scenario_matrix_contract(self):
        cases = scenarios()
        self.assertEqual(len(cases), 18)
        for name, case in cases.items():
            with self.subTest(name=name):
                result = run([product()], case)
                self.assertLessEqual(len(result.recommendations), 5)
                self.assertTrue(all(p.match_count <= result.scorable_target_count for p in result.recommendations))
                self.assertEqual(result.target_count, result.scorable_target_count + len(result.deferred_metrics))
        self.assertEqual(run([product()], cases["normal_boundary"]).target_count, 0)
        self.assertEqual(run([product()], cases["missing_moisture"]).missing_metrics, ["moisture"])


class ApiQualityTests(unittest.TestCase):
    # 기존 DB/API 격리 fixture만 재사용하며 다른 테스트를 상속해 중복 집계하지 않는다.
    setUp = base_tests.ApiDatabaseTests.setUp
    tearDown = base_tests.ApiDatabaseTests.tearDown

    def test_inverted_database_range_returns_503(self):
        with Session(self.engine) as db:
            metric = db.query(SkinMetric).filter_by(code="moisture").one()
            low = db.query(SkinMetricCategory).filter_by(metric_id=metric.id, min_score=0).one()
            high = db.query(SkinMetricCategory).filter_by(metric_id=metric.id, min_score=67).one()
            # 이름/FK/규칙 해시는 유지하고 숫자 구간만 뒤집어 엔진의 새 검증을 통과시키려 한다.
            # min_score 유일 제약을 지키기 위해 비어 있는 100을 임시로 사용한다.
            low.min_score, low.max_score = 100, 100
            db.flush()
            high.min_score, high.max_score = 0, 33
            db.flush()
            low.min_score, low.max_score = 67, 100
            db.commit()
        status, data = asyncio.run(asgi_request(request().model_dump()))
        self.assertEqual(status, 503)
        self.assertIn("점수 방향", data["detail"])

    def test_api_returns_ranking_tie_count(self):
        status, data = asyncio.run(asgi_request(request().model_dump()))
        self.assertEqual(status, 200)
        self.assertEqual(data["recommendations"][0]["ranking_tie_count"], 1)


if __name__ == "__main__":
    unittest.main()
