"""트러블 점수(개수 기준)와 하안부(턱·입 주변) 인정 기준 테스트.

배경: 면적 비율 점수는 중간 정도 여드름부터 100점으로 꽉 차서 중간·심함을 구분하지 못했다.
그래서 덩어리 개수로 점수를 매기고, 수염·그늘로 가짜 덩어리가 잘 생기는 하안부는
충분히 붉은 덩어리만 센다.
"""

import unittest

import cv2
import numpy as np

from app.services import skin_analysis as sa

SIZE = 300          # 가짜 얼굴 영역 크기 (px). 얼굴 너비로도 쓴다
FACE_WIDTH = float(SIZE)


def _index_map(dots: list[tuple[int, int, float]]) -> np.ndarray:
    """홍조 지수 0의 매끈한 피부에, 주변보다 value만큼 붉은 지름 9px 점을 찍는다."""
    index_map = np.zeros((SIZE, SIZE), dtype=np.float32)
    for x, y, value in dots:
        cv2.circle(index_map, (x, y), 4, float(value), thickness=-1)
    return index_map


def _grid(n: int, value: float, y0: int = 40) -> list[tuple[int, int, float]]:
    """가장자리에서 떨어진 곳에 점 n개를 격자로 배치한다."""
    return [(40 + (i % 8) * 30, y0 + (i // 8) * 30, value) for i in range(n)]


class TroubleCountScoreTest(unittest.TestCase):
    def test_anchor_points(self):
        for count, score in sa.TROUBLE_COUNT_POINTS:
            self.assertEqual(sa._trouble_count_score(count), score)

    def test_monotonic_and_capped(self):
        scores = [sa._trouble_count_score(n) for n in range(0, 50)]
        self.assertEqual(scores, sorted(scores))      # 개수가 늘면 점수가 줄지 않는다
        self.assertEqual(sa._trouble_count_score(100), 100)
        self.assertEqual(sa._trouble_count_score(0), 0)


class TroubleBlobCountTest(unittest.TestCase):
    def setUp(self):
        self.skin = np.full((SIZE, SIZE), 255, dtype=np.uint8)

    def test_counts_each_dot(self):
        index_map = _index_map(_grid(6, 3.0))
        score, ratio, _, count = sa._trouble(index_map, self.skin, FACE_WIDTH)
        self.assertEqual(count, 6)
        self.assertEqual(score, sa._trouble_count_score(6))
        self.assertGreater(ratio, 0)

    def test_clean_skin_is_zero(self):
        score, ratio, _, count = sa._trouble(_index_map([]), self.skin, FACE_WIDTH)
        self.assertEqual((score, count), (0, 0))
        self.assertEqual(ratio, 0)

    def test_score_ignores_dot_size(self):
        # 같은 개수면 점이 커도 점수는 같다 (면적 방식은 큰 점 하나에 크게 휘둘렸다)
        small = _index_map(_grid(4, 3.0))
        big = np.zeros_like(small)
        for x, y, v in _grid(4, 3.0):
            cv2.circle(big, (x, y), 6, v, thickness=-1)
        self.assertEqual(sa._trouble(small, self.skin, FACE_WIDTH)[0],
                         sa._trouble(big, self.skin, FACE_WIDTH)[0])


class LowerFaceStrictTest(unittest.TestCase):
    """하안부(strict)에 걸친 덩어리는 최고점 LOWER_FACE_MIN_PEAK 이상만 센다."""

    def setUp(self):
        self.skin = np.full((SIZE, SIZE), 255, dtype=np.uint8)
        self.strict = np.zeros_like(self.skin)
        self.strict[SIZE // 2:, :] = 255   # 아래 절반을 하안부로 가정

    def test_faint_dot_counted_outside_but_not_inside_lower_face(self):
        faint = 1.2   # 임계값 0.8은 넘지만 하안부 기준 1.8에는 못 미침
        self.assertLess(faint, sa.LOWER_FACE_MIN_PEAK)
        upper = _index_map([(80, 60, faint)])
        lower = _index_map([(80, 240, faint)])
        self.assertEqual(sa._trouble(upper, self.skin, FACE_WIDTH, strict=self.strict)[3], 1)
        self.assertEqual(sa._trouble(lower, self.skin, FACE_WIDTH, strict=self.strict)[3], 0)

    def test_strong_dot_counted_in_lower_face(self):
        index_map = _index_map([(80, 240, 3.0), (200, 240, 3.0)])
        self.assertEqual(sa._trouble(index_map, self.skin, FACE_WIDTH, strict=self.strict)[3], 2)

    def test_no_strict_keeps_previous_behavior(self):
        index_map = _index_map([(80, 240, 1.2)])
        self.assertEqual(sa._trouble(index_map, self.skin, FACE_WIDTH)[3], 1)


class LowerFaceSettingsTest(unittest.TestCase):
    def test_margins_are_sane(self):
        for ratio in (sa.LOWER_FACE_JAW_MARGIN_RATIO, sa.LOWER_FACE_LIP_MARGIN_RATIO,
                      sa.LOWER_FACE_NOSE_MARGIN_RATIO):
            self.assertGreater(ratio, 0)
            self.assertLess(ratio, 0.2)
        self.assertGreater(sa.LOWER_FACE_MIN_PEAK, sa.TROUBLE_THRESHOLD)

    def test_landmark_indices_exist_in_face_mesh(self):
        for idx in sa.LOWER_FACE_OVAL + sa.LIP_OUTLINE:
            self.assertTrue(0 <= idx < 468)


if __name__ == "__main__":
    unittest.main()
