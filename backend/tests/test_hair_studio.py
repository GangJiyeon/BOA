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
    def test_padding_and_crop_restore_input(self):
        image = np.arange(15 * 40 * 3, dtype=np.uint8).reshape(15, 40, 3)
        padded, _, pad = hair_studio._pad_input(image)
        self.assertNotEqual(padded.shape, image.shape)
        np.testing.assert_array_equal(
            hair_studio._crop_output(padded, padded.shape[:2], pad, image.shape[:2]),
            image,
        )

    def test_see_through_strand_on_forehead_only(self):
        img = np.full((240, 240, 3), 200, np.uint8)
        img[20:140, 120] = 50  # 이마 위 1px 가닥
        img[150:156, 60:180] = 50  # 눈썹
        lb = np.zeros((478, 2), np.float32)
        lb[hair_studio.FACE_OVAL] = (120, 120)
        lb[hair_studio.FACE_OVAL[2:4]] = [(20, 120), (220, 120)]  # 10번(이마 위)은 아래서 따로 지정
        lb[10] = (120, 40)
        lb[hair_studio.BROWS] = (120, 150)
        for poly in hair_studio.BROW_POLYS:  # 눈썹 윤곽 사각형 (윗선 148, 아랫선 158)
            lb[poly[:5]] = [(x, 148) for x in np.linspace(60, 180, 5)]
            lb[poly[5:]] = [(x, 158) for x in np.linspace(180, 60, 5)]
        lb[hair_studio.UPPER_LIDS] = (120, 170)
        hair = np.zeros((240, 240), np.float32)
        hair[:15] = 1
        img[:15] = 50
        with patch.object(hair_studio, 'landmarks', return_value=lb), patch.object(hair_studio, 'segment', return_value=(hair,) * 4):
            alpha = hair_studio.see_through_strands(img)
        self.assertGreater(alpha[80, 120], 0.9)
        self.assertLess(alpha[80, 100], 0.05)  # 이마 피부
        self.assertLess(alpha[153, 100], 0.05)  # 눈썹 제외
        self.assertLess(alpha[80, 10], 0.05)  # 얼굴 폭 밖
        img2 = img.copy()
        img2[160:166, 120] = 50  # 눈썹 아래·눈꺼풀 위 가닥
        with patch.object(hair_studio, 'landmarks', return_value=lb), patch.object(hair_studio, 'segment', return_value=(hair,) * 4):
            self.assertGreater(hair_studio.see_through_strands(img2)[163, 120], 0.5)

    def test_base_files_share_given_mask(self):
        image = np.zeros((32, 32, 3), np.uint8)
        mask = np.full((32, 32), 128, np.uint8)
        files = hair_studio._base_files('mid', image, mask)
        decoded = cv2.imdecode(np.frombuffer(files['mid_mask.png'], np.uint8), cv2.IMREAD_GRAYSCALE)
        np.testing.assert_array_equal(decoded, mask)

    def test_pyramid_blend_keeps_each_side(self):
        a = np.full((64, 64, 3), 200, np.uint8)
        b = np.full((64, 64, 3), 40, np.uint8)
        mask = np.zeros((64, 64), np.float32)
        mask[:, :32] = 1

        out = hair_studio._pyramid_blend(a, b, mask, levels=3)

        self.assertTrue(np.all(np.abs(out[:, :8].astype(int) - 200) <= 2))
        self.assertTrue(np.all(np.abs(out[:, -8:].astype(int) - 40) <= 2))

    def test_face_ratio_width_and_length(self):
        lb = np.zeros((478, 2), np.float32)
        lb[33], lb[263], lb[234], lb[454], lb[152] = (40, 50), (60, 50), (20, 60), (80, 60), (50, 150)
        la = lb.copy()
        la[234], la[454], la[152] = (23, 60), (77, 60), (50, 160)

        width, length = hair_studio.face_ratio(la, lb)

        self.assertAlmostEqual(width, 0.9, places=3)
        self.assertAlmostEqual(length, 1.1, places=3)

    def test_female_reference_controls_cut_and_curls(self):
        prompt = hair_studio.style_prompt(style(name="단발 히피펌", texture="curly"), has_ref=True)
        self.assertIn("SECOND image defines the target HAIRCUT", prompt)
        self.assertIn("curl size, curl placement", prompt)
        self.assertIn("Do not turn a bob into a pixie", prompt)
        self.assertIn("do not relax the target curl pattern", prompt)
        self.assertNotIn("TEXTURE IS TEXT-ONLY", prompt)
        self.assertNotIn("treat those as low-quality photo artifacts", prompt)
        self.assertIn("THE FACE IS LOCKED", prompt)
        self.assertIn("ONE uniform dye color", prompt)

    def test_legacy_guide_does_not_override_reference_texture(self):
        legacy = "참고 사진에서는 대략적인 길이와 외곽 형태만 참고하며, 숱·가닥 굵기·분리감·결·컬·마감 질감은 이 설명을 우선한다."
        prompt = hair_studio.style_prompt(style(guide="가벼운 시스루 앞머리. " + legacy), True)
        self.assertIn("가벼운 시스루 앞머리", prompt)
        self.assertNotIn(legacy, prompt)
        self.assertIn("SECOND image defines the target HAIRCUT", prompt)

    def test_texture_and_fringe_have_no_conflicting_defaults(self):
        for has_ref in (True, False):
            for sex in ("male", "female"):
                for name, texture in (("시스루 댄디컷", "straight"), ("히피펌", "curly"), ("허쉬컷", "wavy")):
                    with self.subTest(has_ref=has_ref, sex=sex, name=name):
                        prompt = hair_studio.style_prompt(style(name=name, sex=sex, texture=texture), has_ref)
                        self.assertIn("Do not impose a minimum fringe density", prompt)
                        self.assertIn("keep the forehead open", prompt)
                        self.assertIn("do not relax the target curl pattern", prompt)
                        for conflict in ("medium to full density", "moderate thickness", "HAIR SURFACE: smooth", "flowing in long continuous curves", "No single-hair wisps", "treat those as low-quality photo artifacts"):
                            self.assertNotIn(conflict, prompt)

    def test_male_long_styles_have_no_short_cut_restrictions(self):
        for has_ref in (True, False):
            for name in ("오리지널 리프컷", "맨 번", "롱 울프컷", "드레드락", "아프로 헤어"):
                with self.subTest(has_ref=has_ref, name=name):
                    prompt = hair_studio.style_prompt(style(sex="male", length="long", name=name), has_ref)
                    self.assertIn("Preserve a tied bun, braids or an afro", prompt)
                    self.assertNotIn("keep it this short", prompt)
                    self.assertNotIn("Do not turn it into a bob", prompt)
        for length in ("short", "medium"):
            self.assertIn("keep it this short", hair_studio.length_rule(style(sex="male", length=length)))

    def test_prompt_with_and_without_reference(self):
        with_ref = hair_studio.style_prompt(style(sex="male", guide="층 없는 단발"), has_ref=True)
        self.assertIn("SECOND image", with_ref)
        self.assertIn("층 없는 단발", with_ref)
        self.assertIn("SECOND image defines the target HAIRCUT", with_ref)
        self.assertIn("fringe density, curl size, curl placement", with_ref)
        self.assertNotIn("TEXTURE IS TEXT-ONLY", with_ref)
        self.assertIn("sparse see-through bangs", with_ref)
        self.assertIn("Preserve a tied bun, braids or an afro", hair_studio.style_prompt(style(sex="male", length="long"), has_ref=True))
        self.assertIn("Discard ALL color information from the SECOND image", with_ref)
        self.assertNotIn("match the hairstyle shown in the SECOND image", with_ref)
        self.assertIn("Do NOT rotate the head", with_ref)
        self.assertIn("short back and sides", with_ref)  # male short
        self.assertIn("past the shoulders", hair_studio.style_prompt(style(length="long"), has_ref=True))
        self.assertIn("above the collar", hair_studio.style_prompt(style(sex="male", length="medium"), has_ref=True))
        self.assertIn("Do NOT crop, zoom in or out", with_ref)
        self.assertIn("THE FRAMING IS LOCKED", with_ref)
        self.assertIn("same empty background space above the head", with_ref)
        without = hair_studio.style_prompt(style(), has_ref=False)
        self.assertNotIn("SECOND image", without)
        self.assertIn("칼단발", without)
        for prompt in (with_ref, without):
            self.assertIn("ONE uniform dye color from roots to ends", prompt)
            self.assertIn("No ombre, balayage", prompt)
            self.assertIn("HAIR COLOR: medium natural brown", prompt)
            self.assertIn("Do NOT copy or recolor the source photo's fringe", prompt)
            self.assertNotIn("panel", prompt.lower())
            self.assertIn("CHANGE ONLY THE HAIR", prompt)
            self.assertNotIn("pearl blonde", prompt)
            self.assertIn("No white strand outlines", prompt)
            self.assertIn("FRINGE ONLY", prompt)
            self.assertIn("HAIR SURFACE: follow the target texture", prompt)
            self.assertIn("see-through bangs", prompt)
            self.assertIn("The face keeps EXACTLY the same size", prompt)
            self.assertIn("Do not tint the eyebrows", prompt)
            self.assertIn("Face preservation does not mean preserving the original hairstyle", prompt)

    def test_hair_hex_none_without_hair(self):
        empty = np.zeros((64, 64), np.float32)
        with patch.object(hair_studio, "segment", return_value=(empty, empty, empty, empty)):
            self.assertIsNone(hair_studio.hair_hex(np.full((64, 64, 3), 255, np.uint8)))

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


def fake_landmarks(cx=200.0, chin=300.0, face_w=160.0, roll=0.0, yaw=0.0) -> np.ndarray:
    """prepare_photo·생성 검사에 쓰는 점만 채운 가짜 랜드마크"""
    lb = np.zeros((478, 2), np.float32)
    t = np.radians(roll)
    ex = face_w * 0.35
    lb[33] = (cx - ex * np.cos(t), chin - 120 - ex * np.sin(t))
    lb[263] = (cx + ex * np.cos(t), chin - 120 + ex * np.sin(t))
    lb[1] = (cx + yaw * ex, chin - 70)
    lb[152] = (cx, chin)
    for i, k in enumerate(hair_studio.FACE_OVAL):
        a = 2 * np.pi * i / len(hair_studio.FACE_OVAL)
        lb[k] = (cx + face_w / 2 * np.cos(a), chin - 110 + 110 * np.sin(a))
    for k in hair_studio.ANCHORS + hair_studio.HAIR_ANCHORS:
        if not lb[k].any():
            lb[k] = (cx + (k % 7 - 3) * 10, chin - 60 + (k % 5) * 8)
    return lb


class PhotoCheckTest(unittest.TestCase):
    def test_rejects_tilted_turned_small(self):
        img = np.zeros((600, 450, 3), np.uint8)
        for kw, msg in [({"roll": 15}, "기울어진"), ({"yaw": 0.6}, "옆으로"), ({"face_w": 80}, "작게")]:
            with patch.object(hair_studio, "landmarks", return_value=fake_landmarks(**kw)), self.assertRaisesRegex(ValueError, msg):
                hair_studio.prepare_photo(img)

    def test_passes_frontal_photo_unchanged(self):
        img = np.zeros((600, 450, 3), np.uint8)
        with patch.object(hair_studio, "landmarks", return_value=fake_landmarks()):
            self.assertIs(hair_studio.prepare_photo(img), img)

    def test_generation_issue_flags_rescaled_face(self):
        orig = np.zeros((600, 450, 3), np.uint8)
        base = fake_landmarks()
        small = (base - base[152]) * 0.8 + base[152]  # AI가 얼굴을 20% 줄여 그림
        with patch.object(hair_studio, "landmarks", side_effect=[base, small]):
            self.assertEqual(hair_studio._generation_issue(orig, orig), "얼굴 크기")


class GenerateOnceTest(unittest.TestCase):
    def _run(self, issue):
        style = SimpleNamespace()
        with patch.object(hair_studio, "get_settings", return_value=SimpleNamespace(studio_style_model="m", studio_debug=False)), \
                patch.object(hair_studio, "decode_image", side_effect=lambda d, *a: np.zeros((8, 8, 3), np.uint8)), \
                patch.object(hair_studio, "prepare_photo", side_effect=lambda img: img), \
                patch.object(hair_studio, "_pad_input", return_value=(np.zeros((8, 24, 3), np.uint8), "16:9", (0, 0))), \
                patch.object(hair_studio, "_style_ref", return_value=None), \
                patch.object(hair_studio, "style_prompt", return_value="p"), \
                patch.object(hair_studio, "edit_image", return_value=b"x") as edit, \
                patch.object(hair_studio, "_crop_output", return_value=np.zeros((4, 4, 3), np.uint8)), \
                patch.object(hair_studio, "_generation_issue", return_value=issue), \
                patch.object(hair_studio, "compose_bases", return_value={}) as compose, \
                patch.object(hair_studio, "_write"), patch.object(hair_studio, "hair_hex", return_value=None):
            try:
                hair_studio.generate(b"photo", style, "asset")
            finally:
                self.calls = edit.call_count, compose.call_count

    def test_composes_after_single_call(self):
        self._run(None)
        self.assertEqual(self.calls, (1, 1))

    def test_fails_without_retry_when_broken(self):
        with self.assertRaisesRegex(ValueError, "다른 사진"):
            self._run("구도")
        self.assertEqual(self.calls, (1, 0))


class StudioQuotaTest(unittest.TestCase):
    def test_failed_renders_not_counted(self):
        from unittest.mock import MagicMock

        from app.services import quota

        db = MagicMock()
        db.scalar.return_value = 0
        quota._count(db, "studio", guest_id=1)
        sql = str(db.scalar.call_args[0][0])
        self.assertIn("hair_renders.status !=", sql)
        quota._count(db, "hair", guest_id=1)
        self.assertNotIn("status", str(db.scalar.call_args[0][0]))


class StyleRefTest(unittest.TestCase):
    def test_masks_reference_face_gray(self):
        img = np.full((40, 40, 3), 200, np.uint8)
        face = np.zeros((40, 40), np.float32)
        face[10:30, 10:30] = 1
        zero = np.zeros((40, 40), np.float32)
        with patch.object(hair_studio, "decode_image", return_value=img), \
                patch.object(hair_studio, "segment", return_value=(zero, face, zero, zero)), \
                patch.object(hair_studio.Path, "is_file", return_value=True), \
                patch.object(hair_studio.Path, "read_bytes", return_value=b"x"), \
                patch.object(hair_studio, "encode_jpeg", side_effect=lambda x: x):
            out = hair_studio._style_ref(SimpleNamespace(image="/static/hair/F001.jpg"))
        self.assertTrue(np.all(np.abs(out[20, 20].astype(int) - hair_studio.REF_FACE_GRAY) <= 1))
        self.assertTrue(np.all(out[2, 2] == 200))


if __name__ == "__main__":
    unittest.main()
