"""피부 영역 정제(_refine_skin)의 어두운 쪽 허용 폭 테스트.

배경: 피부가 매끈하게 찍히는 웹캠에서는 밝기 허용 폭이 하한(8)까지 좁아져,
주변보다 어두워진 진한 트러블이 '피부 아님'으로 잘려 나갔다.
트러블 영역에서만 어두운 쪽 허용 폭을 넓혀 이를 막는다.
"""

import unittest

import numpy as np

from app.services import skin_analysis as sa


def _lab_with_blobs() -> np.ndarray:
    """밝기 150의 매끈한 피부에 밝기만 다른 사각 얼룩 3개를 넣은 가짜 Lab 이미지."""
    lab = np.full((80, 80, 3), 128, dtype=np.uint8)
    lab[:, :, 0] = 150
    lab[10:20, 10:20, 0] = 138   # 진한 트러블: 주변보다 12 어두움
    lab[10:20, 50:60, 0] = 162   # 하이라이트: 주변보다 12 밝음
    lab[50:60, 10:20, 0] = 100   # 머리카락·그늘 수준: 50 어두움
    return lab


class RefineSkinDarkToleranceTest(unittest.TestCase):
    def setUp(self):
        self.lab = _lab_with_blobs()
        self.mask = np.full((80, 80), 255, dtype=np.uint8)

    def test_default_cuts_both_sides_equally(self):
        # 기존 동작: 매끈한 피부(MAD=0)에서는 ±8을 벗어나면 모두 잘린다
        refined = sa._refine_skin(self.lab, self.mask, min_pixels=100)
        self.assertEqual(refined[15, 15], 0)   # 진한 트러블도 잘림 (고치려던 문제)
        self.assertEqual(refined[15, 55], 0)   # 하이라이트
        self.assertEqual(refined[55, 15], 0)   # 머리카락 수준
        self.assertEqual(refined[40, 40], 255)  # 일반 피부는 남음

    def test_dark_tolerance_keeps_moderately_dark_blemish(self):
        refined = sa._refine_skin(
            self.lab, self.mask, min_pixels=100, dark_tolerance=sa.TROUBLE_DARK_TOLERANCE
        )
        self.assertEqual(refined[15, 15], 255)  # 진한 트러블은 남는다
        self.assertEqual(refined[15, 55], 0)    # 밝은 쪽은 그대로 잘린다
        self.assertEqual(refined[55, 15], 0)    # 훨씬 어두운 것은 여전히 잘린다

    def test_tolerance_never_narrows_the_default(self):
        # 허용 폭을 기본 하한보다 작게 줘도 기존보다 더 잘라내지는 않는다
        base = sa._refine_skin(self.lab, self.mask, min_pixels=100)
        narrow = sa._refine_skin(self.lab, self.mask, min_pixels=100, dark_tolerance=1.0)
        self.assertTrue(np.array_equal(base, narrow))


if __name__ == "__main__":
    unittest.main()
