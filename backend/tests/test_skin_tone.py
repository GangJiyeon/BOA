"""피부톤 분류·메이크업 색 계열 추천표 단위 테스트.

측정(measure_tone)은 실제 얼굴 사진이 필요해 여기서 다루지 않고,
scripts/validation/skin_tone_probe.py 와 실기기 촬영으로 검증한다.
"""

import unittest

from app.services import makeup_palette, skin_tone
from app.services.skin_analysis import CAMERA_PROFILES


class ClassificationTest(unittest.TestCase):
    """ITA°·색상각 → 밝기 단계·언더톤 분류 경계."""

    def setUp(self):
        self.th = skin_tone.TONE_THRESHOLDS["phone"]

    def test_brightness_levels(self):
        # 경계 초과/이하가 올바른 단계로 떨어지는지
        self.assertEqual(skin_tone.classify_brightness(55.0, self.th), "bright")
        self.assertEqual(skin_tone.classify_brightness(41.1, self.th), "bright")
        self.assertEqual(skin_tone.classify_brightness(41.0, self.th), "medium")  # 경계는 아래 단계
        self.assertEqual(skin_tone.classify_brightness(30.0, self.th), "medium")
        self.assertEqual(skin_tone.classify_brightness(28.0, self.th), "deep")
        self.assertEqual(skin_tone.classify_brightness(-70.0, self.th), "deep")

    def test_undertones(self):
        self.assertEqual(skin_tone.classify_undertone(55.0, self.th), "warm")
        self.assertEqual(skin_tone.classify_undertone(50.0, self.th), "warm")   # 웜 경계는 포함
        self.assertEqual(skin_tone.classify_undertone(45.0, self.th), "neutral")
        self.assertEqual(skin_tone.classify_undertone(40.0, self.th), "cool")   # 쿨 경계는 포함
        self.assertEqual(skin_tone.classify_undertone(20.0, self.th), "cool")

    def test_thresholds_exist_for_every_camera_profile(self):
        # 카메라 프로필이 늘어나면 톤 경계도 함께 정해야 한다는 걸 테스트로 상기시킨다
        self.assertEqual(set(skin_tone.TONE_THRESHOLDS), set(CAMERA_PROFILES))

    def test_unknown_profile_falls_back_to_phone(self):
        self.assertEqual(skin_tone.thresholds_for("없는프로필"), skin_tone.DEFAULT_THRESHOLDS)
        self.assertEqual(skin_tone.thresholds_for(" Phone "), skin_tone.TONE_THRESHOLDS["phone"])


class PaletteTest(unittest.TestCase):
    """추천표가 9칸 전부, 필요한 항목을 전부 갖추는지."""

    REQUIRED_KEYS = {"tone_name", "cushion", "lip", "blush", "eye", "point"}

    def test_all_nine_cells_exist(self):
        expected = {
            (b, u) for b in skin_tone.BRIGHTNESS_LEVELS for u in skin_tone.UNDERTONES
        }
        self.assertEqual(set(makeup_palette.PALETTES), expected)

    def test_every_cell_is_complete(self):
        for combo, cell in makeup_palette.PALETTES.items():
            with self.subTest(combo=combo):
                self.assertEqual(set(cell), self.REQUIRED_KEYS)
                for key in ("lip", "blush", "eye"):
                    self.assertTrue(cell[key], f"{combo} {key} 비어 있음")
                self.assertIn("범위", cell["cushion"])  # 호수는 항상 범위로 안내

    def test_recommend_attaches_notices(self):
        rec = makeup_palette.recommend("bright", "warm")
        self.assertEqual(rec["notices"], makeup_palette.NOTICES)

    def test_low_confidence_adds_lighting_notice(self):
        rec = makeup_palette.recommend("deep", "cool", confidence="low")
        self.assertEqual(rec["notices"][0], makeup_palette.LOW_CONFIDENCE_NOTICE)

    def test_unknown_combo_rejected(self):
        with self.assertRaises(ValueError):
            makeup_palette.recommend("bright", "spring")


if __name__ == "__main__":
    unittest.main()
