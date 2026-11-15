import unittest

from app.services.nose_shape_analysis import THRESHOLDS, classify_nose_axes, makeup_nose_strengths


class NoseCorrectionTests(unittest.TestCase):
    def test_normal_noses_have_no_corrective_shadows(self):
        for width, bulbous, upturn in [(.3743, 3.2172, .0643), (.3689, 3.3518, .0531)]:
            ratios = dict(width_ratio=width, bulbous_ratio=bulbous, upturn=upturn, symmetry_deviation=0)
            self.assertEqual(classify_nose_axes(ratios), [])
            self.assertTrue(all(value == 0 for value in makeup_nose_strengths(ratios).values()))

    def test_width_and_tip_are_independent_and_start_at_classification_boundaries(self):
        base = dict(width_ratio=THRESHOLDS['width_wide'], bulbous_ratio=THRESHOLDS['bulbous_ratio'], upturn=.06)
        self.assertTrue(all(value == 0 for value in makeup_nose_strengths(base).values()))
        wide = makeup_nose_strengths({**base, 'width_ratio': .44})
        self.assertEqual(wide['wide_wings'], 1)
        self.assertEqual(wide['round_tip'], 0)
        round_tip = makeup_nose_strengths({**base, 'bulbous_ratio': 4.57})
        self.assertEqual(round_tip['wide_wings'], 0)
        self.assertEqual(round_tip['round_tip'], 1)

    def test_correction_is_bounded_and_continuous(self):
        values = [makeup_nose_strengths(dict(width_ratio=v, bulbous_ratio=3, upturn=.06))['wide_wings'] for v in [.37, .38, .3801, .4, .44, .6]]
        self.assertEqual(values, sorted(values))
        self.assertLess(values[2], .001)
        self.assertTrue(all(0 <= value <= 1 for value in values))


class CheekCorrectionTests(unittest.TestCase):
    def test_face_length_does_not_determine_cheek_width(self):
        from app.services.cheek_analysis import makeup_cheek_features
        points = dict(forehead_left=(-75, 10), forehead_right=(75, 10),
                      cheek_left=(-100, 80), cheek_right=(100, 80),
                      jaw_left=(-75, 150), jaw_right=(75, 150), top=(0, 0), chin=(0, 200))
        original = makeup_cheek_features(points)
        self.assertEqual(original, makeup_cheek_features({**points, 'chin': (0, 300)}))
        self.assertEqual(original['wide'], 0)
        self.assertEqual(original['narrow'], 0)
        broad = makeup_cheek_features({**points, 'cheek_left': (-120, 80), 'cheek_right': (120, 80)})
        self.assertGreater(broad['wide'], .9)
        self.assertEqual(broad['narrow'], 0)

    def test_cheek_width_is_scale_and_roll_invariant(self):
        import math
        from app.services.cheek_analysis import makeup_cheek_features
        points = dict(forehead_left=(-75, 10), forehead_right=(75, 10),
                      cheek_left=(-115, 80), cheek_right=(115, 80),
                      jaw_left=(-75, 150), jaw_right=(75, 150))
        a = .2
        transformed = {name: (3*(x*math.cos(a)-y*math.sin(a))+20, 3*(x*math.sin(a)+y*math.cos(a))+10)
                       for name, (x,y) in points.items()}
        first, second = makeup_cheek_features(points), makeup_cheek_features(transformed)
        for key in first:
            self.assertAlmostEqual(first[key], second[key])


class NosePoseTests(unittest.TestCase):
    def test_nose_upturn_and_symmetry_ignore_photo_roll(self):
        import math
        from app.services.nose_shape_analysis import calculate_nose_ratios
        points = dict(left_eye=(-30, 0), right_eye=(30, 0), forehead_left=(-70, 0), forehead_right=(70, 0),
                      nose_tip=(0, 65), nose_base=(0, 80), nose_bridge_top=(0, 20),
                      nostril_left=(-25, 68), nostril_right=(25, 68))
        a = .2
        rotated = {name: (x*math.cos(a)-y*math.sin(a), x*math.sin(a)+y*math.cos(a))
                   for name,(x,y) in points.items()}
        self.assertEqual(calculate_nose_ratios(points), calculate_nose_ratios(rotated))
