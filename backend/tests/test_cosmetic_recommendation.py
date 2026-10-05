"""실행: backend에서 python -m unittest discover -s tests -v (추가 테스트 패키지 불필요)."""

import asyncio
from dataclasses import replace
import json
import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite://")

from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.main import app
from app.models.cosmetic_rule import CategoryIngredient, CosmeticRuleEvidence, CosmeticRuleSet
from app.services.cosmetic_rule_types import load_seed_bundle
from app.services.cosmetic_rule_repository import seed_rule_bundle
from app.models.cosmetic import Brand, Ingredient, Product, ProductIngredient
from app.models.image import Image
from app.models.skin import SkinAnalysis, SkinMetric, SkinMetricCategory, SkinScore
from app.schemas.cosmetic import CosmeticPreviewRequest
from app.services.cosmetic_recommendation import (
    MetricDefinition, ProductCandidate, RecommendationConfigurationError,
    RecommendationInputError, assess_scores, recommend,
)
from app.services.cosmetic_usage import classify_usage
from app.services.cosmetic_rules import METRICS
from scripts.seed_skin_metrics import seed_metrics


def definitions():
    return [MetricDefinition(code, name, direction, tuple(zip(
        ["개선 필요", "보통", "양호"] if direction else ["양호", "보통", "개선 필요"],
        [0, 34, 67], [33, 66, 100],
    ))) for code, (name, direction) in METRICS.items()]


def request(**changes):
    body = {"scores": {"moisture": 20, "redness": 80, "brightness": 20, "trouble": 80, "uniformity": 20}}
    body.update(changes)
    return CosmeticPreviewRequest.model_validate(body)


def product(product_id=1, ingredients=("글리세린", "판테놀", "나이아신아마이드", "살리실릭애씨드"), **changes):
    return replace(ProductCandidate(product_id, "테스트 세럼", "브랜드", "serum", "normalized", ",".join(ingredients), frozenset(ingredients)), **changes)


KNOWN = {"글리세린", "판테놀", "나이아신아마이드", "살리실릭애씨드", "향료", "세틸알코올", "에탄올", "변성알코올", "멘톨", "판테닐에틸에터"}


def run(products, body=None, defs=None):
    return recommend(body or request(), defs or definitions(), products, KNOWN, rule_bundle=load_seed_bundle())


class EngineTests(unittest.TestCase):
    def test_multiple_ingredients_for_same_metric_count_once(self):
        result = run([product()])
        self.assertEqual(result.recommendations[0].match_count, 4)
        self.assertEqual(result.recommendations[0].matches[0].ingredients, ["글리세린", "판테놀"])

    def test_exclusion_overrides_matches(self):
        result = run([product(ingredients=(*KNOWN,))])
        self.assertEqual(result.recommendations, [])
        self.assertEqual(result.stats.excluded_by_ingredient, 1)

    def test_redness_filter_only_when_needed_and_enabled(self):
        p = product(ingredients=("판테놀", "향료"))
        self.assertEqual(len(run([p], request(avoid_redness_triggers=False)).recommendations), 1)
        scores = request().scores.model_dump() | {"redness": 10}
        self.assertEqual(len(run([p], request(scores=scores)).recommendations), 1)

    def test_user_exclusion_applies_even_if_redness_filter_disabled(self):
        self.assertEqual(run([product()], request(excluded_ingredients=["판테놀"], avoid_redness_triggers=False)).stats.excluded_by_ingredient, 1)

    def test_fatty_alcohol_is_not_ethanol(self):
        self.assertEqual(len(run([product(ingredients=("판테놀", "세틸알코올"))]).recommendations), 1)

    def test_unknown_exclusion_is_rejected_instead_of_silently_ignored(self):
        for bad in ["판테노르", " "]:
            with self.subTest(bad=bad), self.assertRaises(RecommendationInputError):
                run([product()], request(excluded_ingredients=[bad]))

    def test_whitespace_normalized_for_exact_ingredient(self):
        self.assertEqual(run([product()], request(excluded_ingredients=[" 판 테 놀 "])).stats.excluded_by_ingredient, 1)

    def test_substring_and_derivative_not_matched(self):
        self.assertEqual(run([product(ingredients=("판테닐에틸에터",))]).recommendations, [])

    def test_unreviewed_and_missing_links_are_not_candidates(self):
        products = [product(i, parse_status=status) for i, status in enumerate(["missing", "multi_formula", "review", None], 1)]
        products += [product(5, ingredients=()), product(6, ingredients_raw=" ")]
        self.assertEqual(run(products).stats.incomplete_ingredients, 6)

    def test_makeup_unknown_category_and_requested_category_filtered(self):
        products = [product(1, category="lip,makeup"), product(2, category=None), product(3), product(4, category="toner")]
        result = run(products, request(category="toner"))
        self.assertEqual([r.product_id for r in result.recommendations], [4])
        self.assertEqual(result.stats.unsupported_category, 3)

    def test_top_five_order_and_bundle_tiebreak_stable(self):
        products = [product(i) for i in reversed(range(1, 9))]
        products[7] = replace(products[7], product_name="테스트 세럼 1+1 기획")
        result = run(products)
        self.assertEqual([r.product_id for r in result.recommendations], [2, 3, 4, 5, 6])
        self.assertEqual([r.rank for r in result.recommendations], [1, 2, 3, 4, 5])
        self.assertEqual(result.stats.eligible_products, 8)

    def test_matching_count_precedes_bundle_tiebreak(self):
        result = run([product(1, ingredients=("판테놀",)), product(2, product_name="고득점 세트")])
        self.assertEqual(result.recommendations[0].product_id, 2)

    def test_missing_moisture_not_treated_as_dry(self):
        result = run([product()], request(scores=request().scores.model_dump() | {"moisture": None}))
        self.assertEqual(result.target_count, 4)
        self.assertEqual(result.missing_metrics, ["moisture"])
        self.assertEqual(result.recommendations[0].match_count, 3)

    def test_good_scores_return_no_forced_recommendations(self):
        result = run([product()], request(scores={"moisture": 90, "redness": 10, "brightness": 90, "trouble": 10, "uniformity": 90}))
        self.assertEqual(result.target_count, 0)
        self.assertEqual(result.recommendations, [])
        self.assertIsNotNone(result.empty_reason)

    def test_boundary_and_inverse_direction(self):
        for score, expected_up, expected_down in [(0, True, False), (33, True, False), (34, False, False), (66, False, False), (67, False, True), (100, False, True)]:
            with self.subTest(score=score):
                result = assess_scores(request(scores={code: score for code in METRICS}), definitions())
                for assessment in result:
                    self.assertEqual(assessment.needs_improvement, expected_up if METRICS[assessment.code][1] else expected_down)

    def test_db_thresholds_are_used(self):
        defs = definitions()
        defs[0] = replace(defs[0], categories=(("개선 필요", 0, 10), ("보통", 11, 66), ("양호", 67, 100)))
        self.assertFalse(assess_scores(request(), defs)[0].needs_improvement)

    def test_configuration_gaps_overlap_and_wrong_direction_fail(self):
        for change in [
            {"categories": (("개선 필요", 0, 20), ("보통", 22, 100))},
            {"categories": (("개선 필요", 0, 50), ("보통", 50, 100))},
            {"categories": (("보통", 0, 100),)},
            {"higher_is_better": False},
        ]:
            with self.subTest(change=change), self.assertRaises(RecommendationConfigurationError):
                assess_scores(request(), [replace(definitions()[0], **change), *definitions()[1:]])
        with self.assertRaises(RecommendationConfigurationError):
            assess_scores(request(), [])

    def test_invalid_input_is_not_coerced_or_ignored(self):
        for invalid in [-1, 101, 20.1, True, "20"]:
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                request(scores=request().scores.model_dump() | {"redness": invalid})
        with self.assertRaises(ValidationError):
            request(scores={"redness": 20})
        with self.assertRaises(ValidationError):
            request(top_n=100)

    def test_unsafe_urls_not_returned(self):
        p = product(image_url="javascript:alert(1)", source_url="https://user:secret@example.com/")
        result = run([p]).recommendations[0]
        self.assertIsNone(result.image_url)
        self.assertIsNone(result.source_url)

    def test_redness_only_has_no_supported_bonus(self):
        result = run([product(ingredients=("판테놀",))], request(scores={"moisture": 90, "redness": 80, "brightness": 90, "trouble": 10, "uniformity": 90}))
        self.assertEqual(result.target_count, 1)
        self.assertEqual(result.scorable_target_count, 0)
        self.assertEqual(result.deferred_metrics, ["redness"])
        self.assertEqual(result.recommendations, [])

    def test_acid_policy_conditions_and_exact_matching(self):
        for acid in ("글라이콜릭애씨드", "락틱애씨드"):
            with self.subTest(acid=acid):
                p = product(ingredients=("판테놀", "살리실릭애씨드", acid))
                self.assertEqual(run([p]).stats.excluded_by_ingredient, 1)
                self.assertEqual(len(run([p], request(avoid_redness_triggers=False)).recommendations), 1)
                self.assertEqual(len(run([p], request(scores=request().scores.model_dump() | {"redness": 10})).recommendations), 1)
        self.assertEqual(len(run([product(ingredients=("판테놀", "소듐락테이트"))]).recommendations), 1)

    def test_actual_wash_off_serum_excluded_independently_of_redness(self):
        # SQLite A000000216836: 실제 제품명과 관련 성분 부분집합.
        p = product(product_name="[재구매1위/깐달걀세럼] 파넬 아하 오미자 도자기 워시오프 세럼 30ml", ingredients=("글리세린", "글라이콜릭애씨드", "락틱애씨드", "살리실릭애씨드"))
        self.assertEqual(classify_usage(p.product_name)[0], "rinse_off")
        for enabled in (True, False):
            result = run([p], request(avoid_redness_triggers=enabled))
            self.assertEqual(result.recommendations, [])
            self.assertEqual(result.stats.excluded_by_usage, 1)

    def test_peeling_and_cleanser_gift_are_uncertain(self):
        for name in ("[좁쌀순삭/각질순삭] 파파레서피 블레미쉬 필링 토너120ml", "[대용량] 오브제 포어 제로 필링 토너310ml", "[클렌저증정/진정PDRN] 헤브블루 살몬 케어링 센텔라 크림100ml 기획(+버블 클렌저30ml)"):
            with self.subTest(name=name):
                self.assertEqual(classify_usage(name)[0], "uncertain")
                self.assertEqual(run([product(product_name=name)]).stats.excluded_by_usage, 1)

    def test_face_body_cream_remains_inferred_candidate(self):
        p = product(product_name="[온가족 페이스&바디크림] 유리아쥬 제모스 C8+ 끄렘400ml", category="moisturizer")
        result = run([p]).recommendations[0]
        self.assertEqual(result.usage_mode, "leave_on_candidate")
        self.assertIn("미확인", result.usage_basis)

    def test_statistics_partition_catalog(self):
        result = run([product(1), product(2, category="unknown"), product(3, parse_status="review"), product(4, ingredients=("향료",)), product(5, ingredients=("정제수",)), product(6, product_name="워시오프 세럼")])
        stats = result.stats.model_dump()
        self.assertEqual(stats.pop("total_products"), sum(stats.values()))


async def asgi_request(body):
    messages = []
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": json.dumps(body).encode(), "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    path = "/api/cosmetics/recommendations/preview"
    await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "", "headers": [(b"content-type", b"application/json")], "server": ("test", 80), "client": ("test", 123)}, receive, send)
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    data = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, json.loads(data)


class ApiDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        tables = [Image.__table__, SkinMetric.__table__, SkinMetricCategory.__table__, SkinAnalysis.__table__, SkinScore.__table__, Brand.__table__, Product.__table__, Ingredient.__table__, ProductIngredient.__table__, CosmeticRuleSet.__table__, CosmeticRuleEvidence.__table__, CategoryIngredient.__table__]
        Image.metadata.create_all(self.engine, tables=tables)
        with Session(self.engine) as db:
            seed_metrics(db)
            db.add(Brand(brand_id=1, brand_name="테스트 브랜드"))
            db.add(Product(product_id=1, brand_id=1, product_name="테스트 세럼", product_category="serum", parse_status="normalized", ingredients_raw="판테놀,나이아신아마이드"))
            db.add_all([Ingredient(ingredient_id=1, ingredient_name="판테놀"), Ingredient(ingredient_id=2, ingredient_name="나이아신아마이드")])
            db.flush()
            db.add_all([ProductIngredient(product_id=1, ingredient_id=1), ProductIngredient(product_id=1, ingredient_id=2)])
            extra_names = sorted({r.ingredient for r in load_seed_bundle().rules} - {"판테놀", "나이아신아마이드"})
            db.add_all([Ingredient(ingredient_id=i, ingredient_name=name) for i, name in enumerate(extra_names, 3)])
            db.flush()
            seed_rule_bundle(db, load_seed_bundle(), apply=True)
            db.commit()

        def override_db():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = override_db

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_api_returns_real_db_matches_without_writes(self):
        statements = []
        event.listen(self.engine, "before_cursor_execute", lambda conn, cursor, statement, parameters, context, executemany: statements.append(statement))
        status, data = asyncio.run(asgi_request(request().model_dump()))
        self.assertEqual(status, 200)
        self.assertEqual(data["recommendations"][0]["match_count"], 3)
        self.assertEqual(data["recommendations"][0]["brand_name"], "테스트 브랜드")
        self.assertTrue(all(s.lstrip().upper().startswith("SELECT") for s in statements))
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(SkinAnalysis)), 0)

    def test_missing_seed_returns_actionable_503(self):
        with Session(self.engine) as db:
            db.query(SkinMetricCategory).delete()
            db.commit()
        status, data = asyncio.run(asgi_request(request().model_dump()))
        self.assertEqual(status, 503)
        self.assertIn("판정 구간", data["detail"])

    def test_unknown_exclusion_and_invalid_scores_return_422(self):
        for body in [request(excluded_ingredients=["없는성분"]).model_dump(), {"scores": {"redness": 999}}]:
            status, _ = asyncio.run(asgi_request(body))
            self.assertEqual(status, 422)

    def test_empty_catalog_returns_empty_result(self):
        with Session(self.engine) as db:
            db.query(ProductIngredient).delete()
            db.query(Product).delete()
            db.commit()
        status, data = asyncio.run(asgi_request(request().model_dump()))
        self.assertEqual(status, 200)
        self.assertEqual(data["stats"]["total_products"], 0)
        self.assertEqual(data["recommendations"], [])

    def test_all_feature_routes_registered(self):
        paths = app.openapi()["paths"]
        for path in ["/api/cosmetics/recommendations/preview", "/api/skin/analyses", "/api/hair/recommend", "/api/hair/face-analysis"]:
            self.assertIn(path, paths)


if __name__ == "__main__":
    unittest.main()
