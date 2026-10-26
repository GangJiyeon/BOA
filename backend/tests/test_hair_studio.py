import base64
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from app.services import gemini_image, hair_studio, quota


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


def style(**kw):
    base = {"name": "칼단발", "sex": "female", "length": "short", "texture": "straight", "guide": None, "image": None}
    return SimpleNamespace(**{**base, **kw})


class GeminiImageTest(unittest.TestCase):
    def test_closest_aspect(self):
        self.assertEqual(gemini_image.closest_aspect(765, 1024), "3:4")
        self.assertEqual(gemini_image.closest_aspect(1080, 1920), "9:16")
        self.assertEqual(gemini_image.closest_aspect(500, 500), "1:1")

    def test_returns_first_image_part(self):
        body = {"candidates": [{"content": {"parts": [{"text": "ok"}, {"inlineData": {"data": base64.b64encode(b"img").decode()}}]}}]}
        with patch.object(gemini_image.httpx, "post", return_value=FakeResponse(200, body)) as post:
            self.assertEqual(gemini_image.edit_image("m", [b"a", b"b"], "p", "3:4"), b"img")
        sent = post.call_args.kwargs["json"]
        self.assertEqual(len(sent["contents"][0]["parts"]), 3)
        self.assertEqual(sent["generationConfig"]["imageConfig"]["aspectRatio"], "3:4")

    def test_errors(self):
        with patch.object(gemini_image.httpx, "post", return_value=FakeResponse(429, {})):
            with self.assertRaises(gemini_image.ImageGenError):
                gemini_image.edit_image("m", [b"a"], "p", "1:1")
        with patch.object(gemini_image.httpx, "post", return_value=FakeResponse(200, {"candidates": []})):
            with self.assertRaises(gemini_image.ImageGenError):
                gemini_image.edit_image("m", [b"a"], "p", "1:1")


class HairStudioTest(unittest.TestCase):
    def test_prompt_with_and_without_reference(self):
        with_ref = hair_studio.style_prompt(style(guide="층 없는 단발"), has_ref=True)
        self.assertIn("SECOND image", with_ref)
        self.assertIn("층 없는 단발", with_ref)
        self.assertIn("Do NOT rotate the head", with_ref)
        self.assertIn("No hair below the chin", with_ref)  # short
        self.assertIn("past the shoulders", hair_studio.style_prompt(style(length="long"), has_ref=True))
        self.assertIn("above the collar", hair_studio.style_prompt(style(sex="male", length="medium"), has_ref=True))
        self.assertIn("Do not crop, zoom or reframe", with_ref)
        without = hair_studio.style_prompt(style(), has_ref=False)
        self.assertNotIn("SECOND image", without)
        self.assertIn("칼단발", without)

    def test_style_ref_only_from_local_static(self):
        self.assertIsNone(hair_studio._style_ref(style(image=None)))
        self.assertIsNone(hair_studio._style_ref(style(image="https://example.com/a.jpg")))
        self.assertIsNone(hair_studio._style_ref(style(image="/static/hair/__missing__.jpg")))

    def test_decode_image_limits_size(self):
        big = np.zeros((3000, 1500, 3), np.uint8)
        img = hair_studio.decode_image(cv2.imencode(".jpg", big)[1].tobytes())
        self.assertEqual(max(img.shape[:2]), hair_studio.MAX_SIDE)
        with self.assertRaises(ValueError):
            hair_studio.decode_image(b"not an image")

    def test_asset_dir_is_unguessable_and_url(self):
        a, b = hair_studio.new_asset_dir(), hair_studio.new_asset_dir()
        self.assertNotEqual(a, b)
        self.assertGreaterEqual(len(a), 30)
        self.assertEqual(hair_studio.asset_url("abc", "light.jpg"), "/static/studio/abc/light.jpg")


class QuotaTest(unittest.TestCase):
    def test_studio_limit_from_settings(self):
        settings = SimpleNamespace(guest_daily_limit_skin=3, guest_daily_limit_hair=3, guest_daily_limit_studio=2)
        with patch.object(quota, "get_settings", return_value=settings):
            self.assertEqual(quota._limit("studio"), 2)
            self.assertEqual(quota._limit("hair"), 3)


if __name__ == "__main__":
    unittest.main()
