"""원본 카탈로그 제품명 및 경계 사례: 얼굴 추천 범위 검증."""
import unittest

from app.services.cosmetic_usage import classify_usage
import test_cosmetic_recommendation as f


class UsageScopeTests(unittest.TestCase):
    def test_actual_body_lotion_is_held_even_if_category_is_moisturizer(self):
        p = f.product(product_name="[저자극 바디로션] 오브제 맥스 올인원 로션 500ml", category="moisturizer")
        result = f.run([p])
        self.assertEqual(result.recommendations, [])
        self.assertEqual(result.stats.excluded_by_usage, 1)

    def test_actual_eye_only_product_is_held(self):
        p = f.product(product_name="토리든 셀메이징 저분자 콜라겐 탄력 아이크림 30ml", category="moisturizer")
        self.assertEqual(f.run([p]).stats.excluded_by_usage, 1)

    def test_actual_explicit_eye_for_face_remains_candidate(self):
        name = "AHC 유스 래스팅 리얼 아이크림 포 페이스 35ML"
        self.assertEqual(classify_usage(name)[0], "leave_on_candidate")

    def test_actual_face_body_remains_candidate(self):
        name = "[온가족 페이스&바디크림] 유리아쥬 제모스 끄렘 200ml"
        self.assertEqual(classify_usage(name)[0], "leave_on_candidate")

    def test_brand_and_noncosmetic_gifts_are_not_body_or_hair_products(self):
        for name in ("더바디샵 티트리 스킨 클리어링 토너 250ML",
                     "성분에디터 크림 기획 (+산리오 헤어핀)",
                     "세타필 시카세라 장벽 크림 기획 (+매일 쓰는 핸드타올)"):
            with self.subTest(name=name):
                self.assertEqual(classify_usage(name)[0], "leave_on_candidate")

    def test_gift_eye_cream_is_held_until_formula_ownership_is_known(self):
        self.assertEqual(classify_usage("얼굴 세럼 기획 (+아이크림 10ml)")[0], "uncertain")

    def test_face_word_does_not_override_other_usage(self):
        for name in ("페이스 크림 + 핸드크림", "아이크림 + 포 페이스 세럼", "페이스&바디 워시오프 크림"):
            with self.subTest(name=name):
                self.assertNotEqual(classify_usage(name)[0], "leave_on_candidate")

    def test_actual_face_wash_set_is_held(self):
        name = "[단독기획] 우르오스 중건성 페이셜케어 기획세트(스킨밀크200ml+페이스워시100g)"
        self.assertEqual(classify_usage(name)[0], "uncertain")

    def test_localized_products_are_not_full_face_candidates(self):
        for name in ("핸드크림", "풋로션", "립밤", "두피세럼", "헤어에센스", "Eye Cream", "BODY LOTION"):
            with self.subTest(name=name):
                self.assertEqual(classify_usage(name)[0], "uncertain")

    def test_unicode_and_english_rinse_off_names(self):
        for name in ("ＦＡＣＥ ＷＡＳＨ", "Cleansing Milk", "페이스 워시", "바디 워시"):
            with self.subTest(name=name):
                self.assertEqual(classify_usage(name)[0], "rinse_off")

    def test_empty_name_is_not_assumed_leave_on(self):
        self.assertEqual(classify_usage("  ")[0], "uncertain")

    def test_usage_hold_is_independent_of_redness_option(self):
        p = f.product(product_name="바디로션", ingredients=("글리세린",))
        result = f.run([p], f.request(avoid_redness_triggers=False))
        self.assertEqual(result.stats.excluded_by_usage, 1)
        self.assertEqual(result.stats.eligible_products, 0)

    def test_scope_filter_preserves_partition_and_rank_continuity(self):
        products = [f.product(1, product_name="아이크림"), f.product(2), f.product(3, product_name="바디로션")]
        result = f.run(products)
        self.assertEqual([p.product_id for p in result.recommendations], [2])
        self.assertEqual(result.recommendations[0].rank, 1)
        stats = result.stats.model_dump()
        self.assertEqual(stats.pop("total_products"), sum(stats.values()))
