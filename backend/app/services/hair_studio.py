"""AI 스튜디오 헤어 합성

1. 원본 + 카탈로그 스타일 사진 → 밝은 애쉬 블론드 베이스 (style 모델)
2. 밝은 베이스 → 중간 브라운 베이스 (recolor 모델, 색만 변경)
3. 원본 사진 위에 AI 결과의 머리카락만 옮겨 붙임 (얼굴·얼굴형은 원본 픽셀 그대로)
4. 베이스별 머리 마스크 PNG 저장 → 프론트에서 40색 프리셋으로 색만 바꿈

어두운 색은 중간 베이스, 밝은 색은 밝은 베이스에서 바꿔야 앞머리가 덜 끊김
"""

import logging
import secrets
import shutil
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import httpx
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import HairRender, HairStyleCatalog
from app.services.gemini_image import ImageGenError, closest_aspect, edit_image

logger = logging.getLogger("uvicorn.error")

SEG_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite"
MAX_SIDE = 1024
FILES = ("light.jpg", "light_mask.png", "mid.jpg", "mid_mask.png")

STYLE_PROMPT = """Edit the FIRST image (the person). Keep the face, facial features, skin, eyebrows, makeup, expression, pose, clothing and background exactly identical.
Change only the hair to {target}: {style}. Match cut, length, volume, parting and bangs.
Completely remove the original hair, including any hair behind the neck or on the shoulders. {length_rule}
Hair color: light ash platinum blonde with clearly visible strand texture, natural shading and highlights - not white, not gray.
Do not lighten the eyebrows.
CRITICAL: keep the exact head angle, head tilt, gaze direction, face size and face position of the FIRST image. Do NOT rotate the head to frontal.
Keep the exact same framing and zoom: same head size in the frame, same shoulder width, same body shape and clothing position. Do not crop, zoom or reframe. Do not change the person's body or gender presentation; only the hair changes.{ref_note} Photorealistic, same lighting as the original."""

MID_PROMPT = """Recolor ONLY the hair in this photo to medium natural brown (like level 6 hair, a soft milk-tea brown), clearly visible strand texture, natural depth and soft highlights.
Keep the exact same hairstyle, every strand, bangs, shape, volume, hair texture and shine pattern. Keep face, skin, eyebrows, makeup, clothes, background, framing and lighting exactly identical."""

# 정렬 기준점: 눈꼬리·코·입꼬리·턱 (머리카락 영향 적은 점)
ANCHORS = [33, 133, 362, 263, 1, 4, 61, 291, 13, 14, 152, 168, 6, 197]
FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
BROWS = [70, 63, 105, 66, 107, 336, 296, 334, 293, 300]
UPPER_LIDS = [159, 386]

# MediaPipe 그래프는 스레드 안전하지 않음 (백그라운드 작업 동시 실행 대비)
_lock = threading.Lock()
_mesh = None
_segmenter = None


def _get_mesh():
    global _mesh
    if _mesh is None:
        _mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, refine_landmarks=True)
    return _mesh


def _get_segmenter():
    global _segmenter
    if _segmenter is None:
        path = Path(get_settings().hair_seg_model_path)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(httpx.get(SEG_MODEL_URL, timeout=60, follow_redirects=True).raise_for_status().content)
        _segmenter = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=str(path)), output_confidence_masks=True))
    return _segmenter


# ------------------------------------------------------------------
# 이미지 처리
# ------------------------------------------------------------------

def decode_image(data: bytes, max_side: int = MAX_SIDE) -> np.ndarray:
    """바이트 → BGR (EXIF 회전 반영, 긴 변 max_side 이하)"""
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("이미지를 읽을 수 없습니다")
    scale = min(1.0, max_side / max(img.shape[:2]))
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return img


def encode_jpeg(img: np.ndarray, quality: int = 92) -> bytes:
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()


def landmarks(img: np.ndarray) -> np.ndarray:
    """468(+10)개 얼굴 랜드마크 픽셀 좌표, 얼굴 없으면 ValueError"""
    with _lock:
        res = _get_mesh().process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    if not res.multi_face_landmarks:
        raise ValueError("얼굴을 찾지 못했습니다. 정면 사진으로 다시 시도해 주세요")
    h, w = img.shape[:2]
    return np.array([(p.x * w, p.y * h) for p in res.multi_face_landmarks[0].landmark], np.float32)


def segment(img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(머리 확률, 얼굴 피부 확률), 0~1·이미지 크기"""
    with _lock:
        masks = _get_segmenter().segment(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        ).confidence_masks
        hair, face = masks[1].numpy_view().copy(), masks[3].numpy_view().copy()
    size = (img.shape[1], img.shape[0])
    return cv2.resize(hair, size, interpolation=cv2.INTER_LINEAR), cv2.resize(face, size, interpolation=cv2.INTER_LINEAR)


def hair_mask(img: np.ndarray, thr: float = 0.5, soft: float = 0.2, feather: int = 3) -> np.ndarray:
    """색 변경용 머리 마스크 (uint8, 경계 부드럽게)"""
    t = np.clip((segment(img)[0] - (thr - soft / 2)) / soft, 0, 1)
    m = t * t * (3 - 2 * t)
    k = 2 * feather + 1
    for _ in range(2):
        m = cv2.blur(m, (k, k), borderType=cv2.BORDER_REPLICATE)
    return (m * 255).astype(np.uint8)


def _match_skin_tone(base, gen, face, gen_skin, old_hair, new_hair, inside, yy, brow, lid) -> np.ndarray:
    """gen 피부색을 base 피부색에 맞춤 (이마 톤 차이 보정, 머리카락은 그대로)

    둘 다 피부가 보이는 이마 픽셀로 차이를 재고, 부족하면 눈 아래 볼로 잼
    """
    both = (face > 0.6) & (gen_skin > 0.6) & (old_hair < 0.2) & (new_hair < 0.2) & inside
    ref = both & (yy < brow)
    if ref.sum() < 200:
        ref = both & (yy > lid) & (yy < lid + (lid - brow) * 3)
    if ref.sum() < 200:
        return gen
    lab_b = cv2.cvtColor(base, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab_g = cv2.cvtColor(gen, cv2.COLOR_BGR2LAB).astype(np.float32)
    shift = np.clip(np.median(lab_b[ref], 0) - np.median(lab_g[ref], 0), -30, 30)
    # 앞머리 사이로 비치는 피부도 보정되게 피부 확률만 사용 (머리카락은 피부 확률이 낮아 거의 안 바뀜)
    weight = cv2.GaussianBlur(np.clip(gen_skin * 1.5, 0, 1).astype(np.float32), (0, 0), 3)[..., None]
    return cv2.cvtColor(np.clip(lab_g + shift * weight, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def transplant_hair(base: np.ndarray, gen: np.ndarray) -> np.ndarray:
    """base 사진 위에 gen의 머리카락만 옮겨 붙임 (결과 크기 = base)

    gen → base 위치로 정렬 후, 새 머리 + 원래 머리가 있던 자리(얼굴 피부 제외) + 이마만 gen 사용
    눈썹 아래 얼굴·얼굴형·옷은 base 픽셀 그대로
    """
    h, w = base.shape[:2]
    lb = landmarks(base)
    m, _ = cv2.estimateAffinePartial2D(landmarks(gen)[ANCHORS], lb[ANCHORS])
    if m is None:
        raise ValueError("합성 결과를 원본에 맞추지 못했습니다")
    aligned = cv2.warpAffine(gen, m, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)

    old_hair, face = segment(base)
    new_hair, gen_skin = segment(aligned)
    brow, lid = lb[BROWS, 1].min(), lb[UPPER_LIDS, 1].min()
    gap = lid - brow
    yy, xx = np.mgrid[0:h, 0:w]
    inside = (xx > lb[FACE_OVAL, 0].min()) & (xx < lb[FACE_OVAL, 0].max())
    aligned = _match_skin_tone(base, aligned, face, gen_skin, old_hair, new_hair, inside, yy, brow, lid)

    # 원래 머리는 가는 가닥까지 지우도록 넓게, 얼굴 피부는 남김 (새 앞머리가 덮는 곳 제외)
    k = max(3, int(w * 0.035)) | 1
    old = cv2.dilate((old_hair > 0.12).astype(np.float32), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    keep_face = cv2.erode((face > 0.5).astype(np.float32), np.ones((5, 5), np.uint8))
    mask = np.maximum(np.clip((new_hair - 0.2) / 0.4, 0, 1), old * (1 - keep_face))

    # 숱 적은 앞머리는 반투명으로 잡혀 원본 이마가 비침 → 눈썹 위는 gen 통째로 (톤은 위에서 맞춤),
    # 눈썹~윗눈꺼풀 사이는 앞머리를 더 낮은 기준으로 잡음
    mask = np.where(inside & (yy < brow - gap * 0.15), 1.0, mask)
    band = inside & (yy >= brow - gap * 0.15) & (yy < lid - gap * 0.2)
    mask = np.where(band, np.maximum(mask, np.clip((new_hair - 0.08) / 0.25, 0, 1)), mask)
    mask = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 2.5)[..., None]
    return (aligned * mask + base * (1 - mask)).astype(np.uint8)


# ------------------------------------------------------------------
# 생성 파이프라인
# ------------------------------------------------------------------

def new_asset_dir() -> str:
    return secrets.token_urlsafe(24)


def asset_url(asset_dir: str, name: str) -> str:
    return f"/{get_settings().studio_dir.strip('/')}/{asset_dir}/{name}"


def _style_ref(style: HairStyleCatalog) -> bytes | None:
    """카탈로그 사진이 로컬 static에 있으면 참조 이미지로 사용"""
    if not style.image or not style.image.startswith("/static/"):
        return None
    path = Path(style.image.lstrip("/"))
    return path.read_bytes() if path.is_file() else None


# 원래 머리가 길면 AI가 뒤쪽에 남겨두는 경우가 있어 길이 한계를 명시 (남자 스타일은 더 짧게)
LENGTH_RULES = {
    ("male", "short"): "The new hair is a SHORT men's cut: short back and sides, ears visible, ends at the top of the neck. No hair on the neck below the hairline, none on the shoulders.",
    ("male", "medium"): "The new hair is a MEDIUM men's cut: it may lightly cover the ears and ends at the nape, above the collar. No hair below the collar or on the shoulders.",
    ("male", "long"): "The new hair is a LONG men's style: it ends between the chin and the shoulders.",
    ("female", "short"): "The new hair is SHORT: it must end above the jawline at the sides and at the nape of the neck at the back. No hair below the chin, none on the shoulders. Show the neck and ears as needed.",
    ("female", "medium"): "The new hair is MEDIUM length: it must end between the chin and the shoulders. No hair below the shoulders.",
    ("female", "long"): "The new hair is LONG: it falls past the shoulders.",
}


def length_rule(style: HairStyleCatalog) -> str:
    male = getattr(style.sex, "value", style.sex) == "male"
    rule = LENGTH_RULES.get(("male" if male else "female", style.length), "")
    # 여성 사진에 남자 컷을 넣으면 AI가 단발로 바꾸는 경향
    if male:
        rule += " This is a men's haircut: keep it this short even if the person looks feminine. Do not turn it into a bob."
    return rule


def style_prompt(style: HairStyleCatalog, has_ref: bool) -> str:
    male = getattr(style.sex, "value", style.sex) == "male"
    desc = f"{'a men' + chr(39) + 's haircut, ' if male else ''}{style.name} ({style.length} length, {style.texture})"
    if style.guide:
        desc += f" - {style.guide}"
    if has_ref:
        return STYLE_PROMPT.format(
            target="match the hairstyle shown in the SECOND image",
            style=desc,
            length_rule=length_rule(style),
            ref_note=" The SECOND image is only a hairstyle reference; ignore its pose, face and framing.",
        )
    return STYLE_PROMPT.format(target="this hairstyle", style=desc, length_rule=length_rule(style), ref_note="")


def generate(photo: bytes, style: HairStyleCatalog) -> dict[str, bytes]:
    """사진 + 스타일 → 저장할 파일들 (FILES 순서)"""
    settings = get_settings()
    orig = decode_image(photo)
    landmarks(orig)  # 얼굴 없으면 AI 호출 전에 실패
    aspect = closest_aspect(orig.shape[1], orig.shape[0])

    ref = _style_ref(style)
    images = [encode_jpeg(orig)] + ([ref] if ref else [])
    light_raw = edit_image(settings.studio_style_model, images, style_prompt(style, ref is not None), aspect)
    light = transplant_hair(orig, decode_image(light_raw))

    # 중간 베이스도 머리만 가져옴 (두 베이스 얼굴·크기 동일)
    mid_raw = edit_image(settings.studio_recolor_model, [encode_jpeg(light)], MID_PROMPT, aspect)
    mid = transplant_hair(light, decode_image(mid_raw))

    return {
        "light.jpg": encode_jpeg(light),
        "light_mask.png": cv2.imencode(".png", hair_mask(light))[1].tobytes(),
        "mid.jpg": encode_jpeg(mid),
        "mid_mask.png": cv2.imencode(".png", hair_mask(mid))[1].tobytes(),
    }


def process_render(render_id: int, photo: bytes) -> None:
    """백그라운드 작업, 자체 세션 사용 (원본 사진은 메모리에서만 쓰고 버림)"""
    settings = get_settings()
    with SessionLocal() as db:
        render = db.get(HairRender, render_id)
        if render is None:
            return
        style = db.get(HairStyleCatalog, render.style_id)
        try:
            files = generate(photo, style)
            out = Path(settings.studio_dir) / render.asset_dir
            out.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (out / name).write_bytes(data)
            render.status = "done"
        except (ImageGenError, ValueError) as e:
            render.status, render.error = "failed", str(e)[:300]
        except Exception:
            logger.exception("[스튜디오] 합성 실패 render_id=%s", render_id)
            render.status, render.error = "failed", "합성 중 오류가 발생했습니다"
        render.finished_at = datetime.now(UTC)
        db.commit()


def cleanup_renders(db: Session) -> int:
    """보관 기간 지난 행 삭제 + DB에 없는 폴더 삭제, 커밋은 호출하는 쪽에서"""
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(days=settings.studio_keep_days)
    count = db.execute(
        delete(HairRender).where(HairRender.created_at < cutoff).execution_options(synchronize_session=False)
    ).rowcount
    root = Path(settings.studio_dir)
    if root.is_dir():
        alive = set(db.scalars(select(HairRender.asset_dir)))
        for child in root.iterdir():
            if child.is_dir() and child.name not in alive:
                shutil.rmtree(child, ignore_errors=True)
    return count
