import asyncio
import base64
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from app.services import makeup


def fixture():
    image = np.full((200, 200, 3), (145, 175, 200), np.uint8)
    points = np.zeros((478, 2), np.float32)
    points[234] = (25, 100)
    points[454] = (175, 100)
    for x, indexes in [(60, makeup.BROWS[0]), (140, makeup.BROWS[1])]:
        theta = np.linspace(0, 2 * np.pi, len(indexes), endpoint=False)
        points[list(indexes)] = np.column_stack((x + 19 * np.cos(theta), 65 + 5 * np.sin(theta)))
        cv2.ellipse(image, (x, 65), (17, 3), 0, 0, 360, (30, 35, 40), -1)
    for x, indexes in [(60, makeup.EYES[0]), (140, makeup.EYES[1])]:
        theta = np.linspace(0, 2 * np.pi, len(indexes), endpoint=False)
        points[list(indexes)] = np.column_stack((x + 18 * np.cos(theta), 90 + 6 * np.sin(theta)))
        cv2.ellipse(image, (x, 90), (17, 5), 0, 0, 360, (20, 20, 20), -1)
    return image, points


class EyebrowRemovalTests(unittest.TestCase):
    def test_brows_repaired_other_pixels_and_input_preserved(self):
        image, points = fixture()
        original = image.copy()
        cleaned, mask = makeup.remove_eyebrows(image, points)
        np.testing.assert_array_equal(image, original)
        np.testing.assert_array_equal(cleaned[mask == 0], original[mask == 0])
        for x in (60, 140):
            self.assertGreater(float(cleaned[65, x].mean()), float(original[65, x].mean()) + 50)
        np.testing.assert_array_equal(cleaned[82:99], original[82:99])
        self.assertLess(np.count_nonzero(mask), 200 * 200 * .08)

    def test_regions_cover_actual_postprocessing_support(self):
        image, points = fixture()
        _, mask = makeup.remove_eyebrows(image, points)
        regions = makeup.brow_regions(mask, points)
        self.assertEqual(set(regions), {'left', 'right'})
        ys, xs = np.where(mask > 0)
        for side, selected in [('left', xs < 100), ('right', xs >= 100)]:
            region = regions[side]
            cosine, sine = np.cos(region['angle']), np.sin(region['angle'])
            dx, dy = xs[selected]+.5-region['x'], ys[selected]+.5-region['y']
            self.assertTrue(np.all(np.abs(dx*cosine+dy*sine) <= region['width']/2+1e-6))
            self.assertTrue(np.all(np.abs(-dx*sine+dy*cosine) <= region['height']/2+1e-6))
            self.assertGreater(region['height'], 10, 'Postprocessing includes dilation and feathering beyond the landmark height')

    def test_invalid_landmarks_rejected(self):
        image, points = fixture()
        with self.assertRaises(ValueError):
            makeup.remove_eyebrows(image, points[:10])
        points[70] = np.nan
        with self.assertRaises(ValueError):
            makeup.remove_eyebrows(image, points)

    def test_prepare_endpoint_png_dimensions_and_validation(self):
        import test_cosmetic_recommendation  # isolated settings before route import
        import httpx
        from fastapi import FastAPI
        from app.api.routes import makeup as route
        from app.api.deps import require_analysis_actor

        image, points = fixture()
        app = FastAPI()
        app.include_router(route.router)
        app.dependency_overrides[require_analysis_actor] = lambda: object()

        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                with patch.object(route.hair_studio, 'landmarks', return_value=points):
                    result = await client.post('/makeup/prepare', files={'photo': ('face.png', cv2.imencode('.png', image)[1].tobytes(), 'image/png')})
                self.assertEqual(result.status_code, 200, result.text)
                body = result.json()
                self.assertEqual((body['width'], body['height']), (200, 200))
                self.assertEqual(len(body['points']), 478)
                self.assertEqual(set(body['brow_regions']), {'left', 'right'})
                decoded = cv2.imdecode(np.frombuffer(base64.b64decode(body['brow_base_png']), np.uint8), cv2.IMREAD_COLOR)
                expected, _ = makeup.remove_eyebrows(image, points)
                np.testing.assert_array_equal(decoded, expected)
                with patch.object(route, 'MAX_PHOTO_BYTES', 1):
                    too_large = await client.post('/makeup/prepare', files={'photo': ('large.png', b'123', 'image/png')})
                self.assertEqual(too_large.status_code, 413)
                invalid = await client.post('/makeup/prepare', files={'photo': ('bad.png', b'not an image', 'image/png')})
                self.assertEqual(invalid.status_code, 422)

        asyncio.run(run())
