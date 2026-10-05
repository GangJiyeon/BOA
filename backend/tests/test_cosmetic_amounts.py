from decimal import localcontext
import json
import unittest

from app.services.cosmetic_amounts import parse_amount


class AmountTests(unittest.TestCase):
    def test_missing_is_not_zero(self):
        for raw in [None, "", " \t\n"]:
            result = parse_amount(raw)
            self.assertEqual(result.status, "missing")
            self.assertEqual(result.raw_text, raw)
            self.assertEqual(result.declarations, ())

    def test_explicit_zero_is_preserved(self):
        result = parse_amount("0ppm")
        self.assertEqual(result.status, "single")
        self.assertEqual(result.declarations[0].conditional_percent, "0")

    def test_units_case_spacing_and_commas(self):
        for raw, value, unit, percent in [
            (" 20,000PPM ", "20000", "ppm", "2"),
            ("5 %", "5", "%", "5"),
            ("0.001ppb", "0.001", "ppb", "0.0000000001"),
            ("100 ppm", "100", "ppm", "0.01"),
        ]:
            with self.subTest(raw=raw):
                r = parse_amount(raw)
                self.assertEqual(r.status, "single")
                self.assertEqual(r.raw_text, raw)
                self.assertEqual((r.declarations[0].value, r.declarations[0].unit,
                                  r.declarations[0].conditional_percent), (value, unit, percent))

    def test_mass_has_no_concentration(self):
        r = parse_amount("49,750mg")
        self.assertEqual(r.issue, "denominator_missing")
        self.assertIsNone(r.declarations[0].conditional_percent)

    def test_activity_has_no_guessed_conversion(self):
        r = parse_amount("1,030IU/g")
        self.assertEqual(r.status, "single")
        self.assertEqual(r.declarations[0].unit, "IU/g")
        self.assertIsNone(r.declarations[0].conditional_percent)

    def test_consistent_dual_keeps_both(self):
        r = parse_amount("0.75%/ 7,500ppm")
        self.assertEqual(r.status, "dual")
        self.assertTrue(r.dual_consistent_if_same_basis)
        self.assertEqual(len(r.declarations), 2)

    def test_inconsistent_dual_is_flagged_not_corrected(self):
        r = parse_amount("1%/ 7,500ppm")
        self.assertEqual(r.issue, "inconsistent_dual")
        self.assertFalse(r.dual_consistent_if_same_basis)
        self.assertEqual(r.declarations[0].value, "1")

    def test_unsupported_dual_units(self):
        for raw in ["1mg/2ppm", "1%/1%", "300IU/g/1%"]:
            self.assertEqual(parse_amount(raw).issue, "unsupported_dual_units")

    def test_real_malformed_number_is_not_repaired(self):
        r = parse_amount("10.020.7%")
        self.assertEqual(r.status, "unparsed")
        self.assertEqual(r.declarations, ())

    def test_unsupported_forms_not_partially_matched(self):
        for raw in ["1,00ppm", "-1%", "1e2ppm", "NaN%", "약 5%", "1~5%",
                    "<1%", "5% 이상", "1mg/ml", ".5%", "５%", "1%/2ppm/3ppb"]:
            with self.subTest(raw=raw):
                self.assertEqual(parse_amount(raw).status, "unparsed")

    def test_fraction_bounds(self):
        for raw in ["100.01%", "1,000,001ppm", "1,000,000,001ppb"]:
            self.assertEqual(parse_amount(raw).issue, "fraction_out_of_range")
        for raw in ["100%", "1,000,000ppm", "1,000,000,000ppb"]:
            self.assertEqual(parse_amount(raw).declarations[0].conditional_percent, "100")

    def test_non_strings_rejected(self):
        for raw in [0, False, 0.5, [], {}]:
            with self.assertRaises(TypeError):
                parse_amount(raw)

    def test_long_input_bounded(self):
        self.assertEqual(parse_amount("0" * 257).issue, "text_too_long")
        self.assertEqual(parse_amount("0" * 51 + "%").issue, "number_too_long")

    def test_decimal_context_does_not_round_conversion(self):
        with localcontext() as ctx:
            ctx.prec = 2
            self.assertEqual(parse_amount("123.456ppm").declarations[0].conditional_percent, "0.0123456")

    def test_no_interpretation_claims_verification(self):
        for raw in [None, "5%", "5%/50,000ppm", "1mg", "bad"]:
            r = parse_amount(raw)
            self.assertFalse(r.concentration_verified)
            self.assertEqual(r.basis, "unknown")
            self.assertEqual(json.loads(json.dumps(r.to_dict()))["raw_text"], raw)
