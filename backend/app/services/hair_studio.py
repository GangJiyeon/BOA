"""AI 스튜디오 헤어 합성

1. 원본 사진과 카탈로그 스타일로 중간 갈색 결과 한 장을 생성.
2. 생성 결과를 원본에 정렬하고 원본 얼굴을 우선해 합성.
3. 합성 JPG와 염색 마스크 PNG를 저장해 브라우저에서 색 변경에 사용.
"""

import hashlib
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
from app.services.gemini_image import ASPECT_RATIOS, ImageGenError, closest_aspect, edit_image

logger = logging.getLogger("uvicorn.error")

SEG_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite"
MAX_SIDE = 1024

# AI가 얼굴을 갸름하게(V라인) 다시 그려 원래 머리 자리 턱선이 어긋나는 문제 → 얼굴 고정 규칙을 앞뒤로 반복
FACE_LOCK = """ABSOLUTE RULE - THE FACE IS LOCKED. This is a hair-only edit, NOT a beauty filter.
It must stay the SAME PERSON with the same identity: copy the eyes, nose, lips, skin tone, makeup and blush from the FIRST image exactly; do not redraw or regenerate the face.
Do NOT change the face shape in any way: same jawline, same chin, same cheeks, same cheekbones, same face width, same temples, same forehead width, same ears and neck.
Do NOT slim, narrow, contour, V-line, reshape, beautify, retouch or smooth the face. Do NOT enlarge the eyes or change the nose, lips or chin length.
Where the original hair covered the cheeks, jaw or forehead, reveal the SAME person's real face edge continuing the existing contour at the exact same width - never a slimmer or sharper one.
Do NOT copy the face, face shape or jawline of any reference image."""

# AI가 얼굴을 5~9% 키우고 아래로 내려 그려 정렬 후 사진 위쪽이 비고 이마 위가 잘림 → 구도 고정을 따로 강하게
FRAME_LOCK = """ABSOLUTE RULE - THE FRAMING IS LOCKED. This is an in-place, pixel-aligned edit of the photo, NOT a new photo.
The edit keeps the exact same camera distance, crop and composition as the FIRST image. Do NOT crop, zoom in or out, or move the person down, up or sideways.
The face keeps EXACTLY the same size. The top of the head, eyes, mouth, chin, shoulders and the edges of the clothing stay at exactly the same pixel positions. Keep the same empty background space above the head as in the FIRST image.
If the new hair is taller or wider than the original, it grows into the existing background or is cut off by the photo edge; never shrink, lower or move the person to make room for it.
Keep the same facial expression and mouth shape (a smile stays the same smile, open lips and visible teeth stay as they are)."""

# 중간 갈색 한 장만 그림 (프리셋이 전부 어두운 톤, 앞머리 가닥도 중간 갈색에서 충분히 잡힘)
# 얼굴 크기·위치는 고정하고, 모발 질감과 앞머리 숱은 목표 스타일을 따른다.
STYLE_PROMPT ="""THE MOST IMPORTANT RULE - CHANGE ONLY THE HAIR. NOTHING ELSE.
This is a hair-only edit of an existing photo. ONLY the hair pixels may change. EVERYTHING that is not hair must stay EXACTLY as in the source photo, pixel for pixel:
- the background, lighting and camera framing: unchanged.
- the face size, face width, face shape, jawline, cheeks and proportions: unchanged. Do NOT slim, narrow, enlarge or shrink the face, not even slightly.
- the eyes, eyebrows (shape, thickness, color, position), nose, lips, ears, skin, moles and expression: unchanged.
- the neck, shoulders, body and clothing: unchanged.
If any change other than the hair would happen, do NOT make it. When in doubt, copy the source pixels.

TASK: replace the person's haircut with {target}.
TARGET HAIRCUT: {style}
{length_rule}
Reconstruct the cut, parting, fringe placement, density, volume and strand flow to implement this target. The original haircut is NOT locked. A recolor or minor cleanup of the original hairstyle is not sufficient. Replace conflicting original fringe gaps, pointed clumps and parting; retain only features that actually match the target. Keep the anatomical head shape beneath the new haircut natural and unchanged.
{ref_note}

""" + FACE_LOCK + """

""" + FRAME_LOCK + """

The FIRST image is the source photo. The face, head and shoulders stay at exactly the same size and pixel position as in the source photo.
Remove leftover original hair behind the neck or on the shoulders where it does not belong to the target haircut.
HAIR COLOR: medium natural brown (level 7).
BANGS ARE HAIR TOO: redraw the fringe from the target haircut. Do NOT copy or recolor the source photo's fringe strands, their gaps or their placement; the source fringe is replaced, not kept.
The hair has ONE uniform dye color from roots to ends, including sides, inner layers and nape. This color instruction overrides source/reference colors and any coloring terms in the style description. No ombre, balayage, dark roots, bleached ends or two-tone sections.
Render natural strands with soft, color-preserving shine. No white strand outlines, silver or gray streaks, blown-out highlights, coarse tonal bands or jagged compression texture.
HAIR SURFACE: follow the target texture and strand flow. Preserve intentional tight curls, irregular perm texture, shaggy layers, braids, locs and afro volume when present in the target; do not relax the target curl pattern or force every style into smooth, long curves. Remove only image noise, compression artifacts and stray fuzz that are not part of the target style. The finish is soft and natural like a real salon photo: smooth, gently flowing strands with soft natural shine; never crunchy, wiry, frizzy, stiff or plastic-looking.
FRINGE ONLY: follow the target's fringe presence, density, strand thickness, separation and placement. Preserve fine, sparse see-through bangs and their natural forehead gaps when specified; preserve dense bangs when specified. Do not impose a minimum fringe density or thicken fine strands. If the target has no bangs, keep the forehead open. Avoid artificial translucent haze over the forehead while preserving actual fine strands. The rest of the hair also follows the target texture.
AROUND THE HAIR: where skin shows between fringe strands, keep the same warm natural skin tone and brightness as the cheeks, with at most a soft shadow directly under each strand and no gray or dark band on the forehead. Do not tint the eyebrows with the hair color. No glow, halo or color cast around the hair outline.
Keep the FIRST image's face, eyebrows, ears, skin, head angle, gaze, clothing and background. Do NOT rotate the head to frontal. Keep the body proportions. Face preservation does not mean preserving the original hairstyle.
FINAL CHECK: only the hair is different from the source photo. The face, eyebrows, face size and background are identical."""

FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
BROWS = [70, 63, 105, 66, 107, 336, 296, 334, 293, 300]
UPPER_LIDS = [159, 386]
# 눈 윤곽 (눈꺼풀·눈꼬리)
EYES = [[33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246],
        [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]]
# 눈썹 윤곽 (윗선 바깥→안, 아랫선 안→바깥)
BROW_POLYS = [[70, 63, 105, 66, 107, 55, 65, 52, 53, 46], [300, 293, 334, 296, 336, 285, 295, 282, 283, 276]]

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
            base_options=BaseOptions(model_asset_path=str(path), delegate=BaseOptions.Delegate.CPU),
            output_confidence_masks=True))
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


# 같은 사진을 여러 번 재지 않게 최근 결과 재사용 (합성 한 번에 같은 사진을 10번 넘게 잼)
_CACHE_SIZE = 16
_cache: dict[tuple, object] = {}


def _cached(kind: str, img: np.ndarray, fn):
    key = (kind, img.shape, hashlib.blake2b(np.ascontiguousarray(img).data, digest_size=16).digest())
    with _lock:
        if key in _cache:
            return _cache[key]
    value = fn(img)
    with _lock:
        if len(_cache) >= _CACHE_SIZE:
            _cache.pop(next(iter(_cache)))
        _cache[key] = value
    return value


def landmarks(img: np.ndarray) -> np.ndarray:
    """468(+10)개 얼굴 랜드마크 픽셀 좌표, 얼굴 없으면 ValueError"""
    return _cached("lm", img, _landmarks).copy()


def _landmarks(img: np.ndarray) -> np.ndarray:
    with _lock:
        res = _get_mesh().process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    if not res.multi_face_landmarks:
        raise ValueError("얼굴을 찾지 못했습니다. 정면 사진으로 다시 시도해 주세요")
    h, w = img.shape[:2]
    return np.array([(p.x * w, p.y * h) for p in res.multi_face_landmarks[0].landmark], np.float32)


# 사진 거절 기준: 고개 기울기(°), 좌우 돌림(코끝 위치 -1~1, 정상 사진 최대 0.19), 얼굴 폭(px, 가닥·눈썹 판정 최소 해상도)
PHOTO_MAX_ROLL, PHOTO_MAX_YAW, PHOTO_MIN_FACE = 10.0, 0.35, 120


def _roll(lb: np.ndarray) -> float:
    """고개 기울기 (눈꼬리 두 점 각도, °)"""
    d = lb[263] - lb[33]
    return float(np.degrees(np.arctan2(d[1], d[0])))


def _yaw(lb: np.ndarray) -> float:
    """고개 좌우 돌림 (코끝이 두 눈꼬리 사이 어디인지, 정면 0, -1~1)"""
    return float(2 * (lb[1, 0] - lb[33, 0]) / max(lb[263, 0] - lb[33, 0], 1) - 1)


def prepare_photo(img: np.ndarray) -> np.ndarray:
    """합성에 쓸 사진 검사, 못 쓰면 ValueError (AI 호출 전), 통과하면 그대로

    고개가 기울거나 옆을 보면 AI가 얼굴을 세우고 옮겨 그려 정렬·각도가 망가짐
    """
    lb = landmarks(img)
    if abs(_roll(lb)) > PHOTO_MAX_ROLL:
        raise ValueError("고개가 기울어진 사진이에요. 고개를 똑바로 세운 정면 사진으로 다시 시도해 주세요")
    if abs(_yaw(lb)) > PHOTO_MAX_YAW:
        raise ValueError("얼굴이 옆으로 돌아간 사진이에요. 정면을 바라본 사진으로 다시 시도해 주세요")
    oval = lb[FACE_OVAL]
    if float(oval[:, 0].max() - oval[:, 0].min()) < PHOTO_MIN_FACE:
        raise ValueError("얼굴이 너무 작게 나온 사진이에요. 얼굴이 더 크게 나온 사진으로 다시 시도해 주세요")
    return img


def _generation_issue(orig: np.ndarray, raw: np.ndarray) -> str | None:
    """AI 결과가 원본과 구도·각도가 크게 달라 합성하면 망가지는지, 문제면 이유"""
    lb = landmarks(orig)
    try:
        lr = landmarks(raw)
    except ValueError:
        return "얼굴 없음"
    # 합성과 같은 기준 (얼굴 점 전체)
    m, _ = cv2.estimateAffinePartial2D(lr[:468], lb[:468], method=cv2.LMEDS)
    if m is None:
        return "정렬 실패"
    if abs(float(np.linalg.norm(m[:, 0])) - 1) > GEN_MAX_SCALE:
        return "얼굴 크기"
    if abs(_roll(lr) - _roll(lb)) > GEN_MAX_ROLL:
        return "고개 기울기"
    if abs(_yaw(lr) - _yaw(lb)) > GEN_MAX_YAW:
        return "고개 돌림"
    y0, y1, x0, x1 = _valid_box(orig, m, raw.shape[:2])
    if (y1 - y0) * (x1 - x0) / (orig.shape[0] * orig.shape[1]) < GEN_MIN_KEEP:
        return "구도"
    return None


def segment(img: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(머리 확률, 얼굴 피부 확률, 배경 확률, 몸 피부 확률), 0~1·이미지 크기"""
    return tuple(m.copy() for m in _cached("seg", img, _segment))


def _segment(img: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    with _lock:
        masks = _get_segmenter().segment(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        ).confidence_masks
        picked = [masks[i].numpy_view().copy() for i in (1, 3, 0, 2)]
    size = (img.shape[1], img.shape[0])
    hair, face, bg, body = (cv2.resize(m, size, interpolation=cv2.INTER_LINEAR) for m in picked)
    return hair, face, bg, body


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

    둘 다 피부가 보이는 눈 아래 볼로 차이를 재고, 부족하면 이마로 잼
    (원래 앞머리가 이마를 덮었으면 그 사이 이마가 머리 그림자로 어두워, 이마 기준이면 gen 이마를 어둡게 끌어내림)
    """
    both = (face > 0.6) & (gen_skin > 0.6) & (old_hair < 0.2) & (new_hair < 0.2) & inside
    ref = both & (yy > lid) & (yy < lid + (lid - brow) * 3)
    if ref.sum() < 200:
        ref = both & (yy < brow)
    if ref.sum() < 200:
        return gen
    lab_b = cv2.cvtColor(base, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab_g = cv2.cvtColor(gen, cv2.COLOR_BGR2LAB).astype(np.float32)
    shift = np.clip(np.median(lab_b[ref], 0) - np.median(lab_g[ref], 0), -30, 30)
    # 앞머리 사이로 비치는 피부도 보정되게 피부 확률만 사용 (머리카락은 피부 확률이 낮아 거의 안 바뀜)
    weight = cv2.GaussianBlur(np.clip(gen_skin * 1.5, 0, 1).astype(np.float32), (0, 0), 3)[..., None]
    return cv2.cvtColor(np.clip(lab_g + shift * weight, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def _match_background(base, gen, old_bg, new_bg) -> np.ndarray:
    """gen 배경색을 base 배경색에 맞춤 (원래 머리 지운 자리에 밝은 테두리 생기는 것 방지)

    둘 다 배경인 픽셀로 차이를 재고, gen 배경에만 적용
    """
    ref = (old_bg > 0.9) & (new_bg > 0.9)
    if ref.sum() < 500:
        return gen
    lab_b = cv2.cvtColor(base, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab_g = cv2.cvtColor(gen, cv2.COLOR_BGR2LAB).astype(np.float32)
    shift = np.clip(np.median(lab_b[ref], 0) - np.median(lab_g[ref], 0), -40, 40)
    weight = cv2.GaussianBlur(new_bg.astype(np.float32), (0, 0), 2)[..., None]
    return cv2.cvtColor(np.clip(lab_g + shift * weight, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def _match_region_tone(base, gen, segs, lb, yy) -> np.ndarray:
    """턱 아래 AI 목 피부색을 원본 목 피부(둘 다 피부인 곳 중앙값)에 맞춤 (볼 기준 보정만으로는 목이 밝게 남음)

    이마는 안 맞춤 (원본 이마 번들거림 기준으로 밝히면 눈썹 사이·위가 하얀 띠로 뜸)
    """
    face, body, gen_skin, gbody, old_hair, new_hair = segs
    h = base.shape[0]
    brow, lid, chin = lb[BROWS, 1].min(), lb[UPPER_LIDS, 1].min(), lb[152, 1]
    gap = lid - brow
    lab_b = cv2.cvtColor(base, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab = cv2.cvtColor(gen, cv2.COLOR_BGR2LAB).astype(np.float32)
    clear = (old_hair < 0.2) & (new_hair < 0.2)
    gsk = np.maximum(gbody, gen_skin)
    ref = (np.maximum(body, face) > 0.6) & (gsk > 0.6) & clear & (yy > chin + gap * 0.3)
    if ref.sum() > 300:
        d = np.clip(np.median(lab_b[ref], 0) - np.median(lab[ref], 0), -30, 30)
        wgt = np.clip((gsk - 0.4) / 0.3, 0, 1) * (new_hair < 0.2) * np.clip((yy - chin) / (h * 0.03), 0, 1)
        lab += d * cv2.GaussianBlur(wgt.astype(np.float32), (0, 0), 3)[..., None]
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


# 눈썹·눈두덩을 세로로 지나는 가닥: 가로로 메운 밝기보다 이만큼(L) 이상 어두우면 가닥
BROW_STRAND_MIN = 8.0


def _brow_strands(base: np.ndarray, lb: np.ndarray, gap: float) -> np.ndarray:
    """원본 눈썹~윗눈꺼풀 위를 세로로 지나는 앞머리 가닥 (0/1)

    눈썹·쌍꺼풀 선은 가로, 가닥은 세로·비스듬히 → 가로 막대로 닫힘 연산하면 눈썹·쌍꺼풀은 그대로, 가는 세로 가닥만 메워짐
    메워진 밝기와 원래 밝기 차이가 큰 곳 = 가닥 (눈썹 둘레~윗눈꺼풀 위, 눈 자체는 제외)
    """
    h, w = base.shape[:2]
    zone = np.zeros((h, w), np.uint8)
    for poly in BROW_POLYS:
        pts = lb[poly].round().astype(np.int32)
        # 눈썹부터 그 아래 윗눈꺼풀 높이까지 (눈썹 다각형을 아래로 늘림)
        low = pts.copy()
        low[:, 1] = np.maximum(low[:, 1], int(lb[UPPER_LIDS, 1].min()))
        cv2.fillPoly(zone, [cv2.convexHull(np.vstack([pts, low]))], 1)
    kz = max(3, int(gap * 0.25)) | 1
    zone = cv2.dilate(zone, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kz, kz)))
    eyes = np.zeros((h, w), np.uint8)
    for eye in EYES:
        cv2.fillConvexPoly(eyes, cv2.convexHull(lb[eye].round().astype(np.int32)), 1)
    zone = zone * (1 - cv2.dilate(eyes, np.ones((5, 5), np.uint8)))
    L = cv2.cvtColor(base, cv2.COLOR_BGR2LAB)[..., 0]
    kl = max(5, int(gap * 0.15)) | 1
    closed = cv2.morphologyEx(L, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (kl, 1)))
    lines = ((closed.astype(np.int16) - L.astype(np.int16)) > BROW_STRAND_MIN).astype(np.uint8) * zone
    # 점 잡티는 빼고 세로로 이어진 것만 (세로 길이가 굵기보다 긴 덩어리)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(lines, 8)
    keep = np.zeros(n, np.uint8)
    for k in range(1, n):
        x, y, bw, bh, area = stats[k]
        keep[k] = bh >= max(4, gap * 0.08) and bh >= bw * 0.8
    return cv2.dilate(keep[lab], np.ones((3, 3), np.uint8))


def _fill_rows(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """mask 픽셀을 같은 줄 좌우 픽셀 사이 직선 보간으로 메움 (눈썹처럼 가로 구조가 이어짐, 둘레 평균처럼 회색으로 번지지 않음)"""
    out = img.copy()
    for y in np.flatnonzero(mask.any(1)):
        row = mask[y] > 0
        xs = np.flatnonzero(~row)
        if len(xs) < 2:
            continue
        miss = np.flatnonzero(row)
        for c in range(img.shape[2]):
            out[y, miss, c] = np.interp(miss, xs, img[y, xs, c].astype(np.float32)).astype(np.uint8)
    # 줄마다 따로 메워 생긴 가로 줄무늬 → 메운 곳만 세로로 살짝 흐림
    soft = cv2.GaussianBlur(out, (1, 9), 0, sigmaY=2.5)
    m = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 1.0)[..., None]
    return (out * (1 - m) + soft * m).astype(np.uint8)


def _ai_brows(base: np.ndarray, ai: np.ndarray, lb: np.ndarray, la: np.ndarray, gap: float) -> np.ndarray:
    """두 눈썹 모두 AI 눈썹으로 (원본 눈썹 위치·길이에 맞춰 옮기고 크기만, 휘지 않음)

    2026-11-26: 원본 눈썹 유지는 앞머리 가닥 메운 자리 얼룩·한쪽만 바꿀 때 짝짝이·섞기 번짐 → 항상 AI 눈썹
    눈썹 하나 통째로 (일부만 바꾸면 이음매 어색)
    피부 톤은 원본: AI 덩어리의 저주파(피부 톤·음영)를 원본 피부 저주파로 교체, 털·결만 AI
    (평균색 하나로만 맞추면 AI 눈썹뼈 그늘이 둘레 얼룩으로 남음)
    """
    h, w = base.shape[:2]
    out = base
    # 피부 톤 잴 때 눈썹 털을 확실히 지우는 크기 (작으면 굵은 눈썹 진하기까지 톤으로 빠져 눈썹이 연해짐)
    kc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(5, int(gap * 0.9)) | 1,) * 2)
    sig = max(3.0, gap * 0.25)

    def skin_tone(lab: np.ndarray) -> np.ndarray:
        return cv2.GaussianBlur(np.stack([cv2.morphologyEx(lab[..., i], cv2.MORPH_CLOSE, kc) for i in range(3)], -1), (0, 0), sig)

    for poly in BROW_POLYS:
        region = np.zeros((h, w), np.uint8)
        cv2.fillPoly(region, [lb[poly].round().astype(np.int32)], 1)
        if not region.any():
            continue
        m, _ = cv2.estimateAffinePartial2D(la[poly], lb[poly])
        if m is None:
            continue
        brow = cv2.warpAffine(ai, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        k = max(3, int(gap * 0.3)) | 1
        ell = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        mask = cv2.dilate(region, ell)
        # 원본 눈썹 지운 피부 → 톤 기준
        clean = cv2.inpaint(out, mask * 255, max(3, int(gap * 0.15)), cv2.INPAINT_TELEA)
        lab_a = cv2.cvtColor(brow, cv2.COLOR_BGR2LAB).astype(np.float32)
        lab_a += skin_tone(cv2.cvtColor(clean, cv2.COLOR_BGR2LAB).astype(np.float32)) - skin_tone(lab_a)
        brow = cv2.cvtColor(np.clip(lab_a, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)
        soft = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), max(1.5, gap * 0.08))[..., None]
        out = (out * (1 - soft) + brow * soft).astype(np.uint8)
    return out


OLD_STRAND_MIN, OLD_STRAND_RAMP = 6.0, 12.0
# 가닥 후보 덩어리 중 가로 폭이 세로 길이의 이 배수 이상이면 눈썹 아랫선·쌍꺼풀 선으로 보고 안 메움
FLAT_RATIO = 2.0


def _old_strands(base: np.ndarray, lb: np.ndarray, gap: float) -> np.ndarray:
    """원본 얼굴 위 가는 앞머리 가닥 알파 (0~1): 이마~윗눈꺼풀 위 + 미간·콧대 구간, 눈썹·눈 제외 (합성 전 원본에서 메워 지움)"""
    h, w = base.shape[:2]
    L = cv2.cvtColor(base, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32)
    k = max(5, int(w * 0.02)) | 1
    skin = cv2.morphologyEx(L, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    # 염색용(SEE_THROUGH_MIN)보다 낮은 기준 (가는 가닥은 피부보다 L 6~25만 어두움, 더 잡혀도 그 자리는 AI 피부라 티 안 남)
    alpha = np.clip((skin - L - OLD_STRAND_MIN) / OLD_STRAND_RAMP, 0, 1)
    yy, xx = np.mgrid[0:h, 0:w]
    bridge = ((xx > lb[133, 0] + gap * 0.15) & (xx < lb[362, 0] - gap * 0.15)
              & (yy > lb[BROWS, 1].min()) & (yy < lb[6, 1])).astype(np.uint8)
    # 눈은 넓게 제외 (쌍꺼풀 선이 가닥으로 잡혀 지워짐), 눈썹은 바로 테두리까지만 제외 (눈썹 끝에 걸친 가닥이 토막으로 남음)
    eyes = np.zeros((h, w), np.uint8)
    for eye in EYES:
        cv2.fillConvexPoly(eyes, cv2.convexHull(lb[eye].round().astype(np.int32)), 1)
    ke = max(3, int(gap * 0.2)) | 1
    eyes = cv2.dilate(eyes, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ke, ke)))
    brows = np.zeros((h, w), np.uint8)
    for poly in BROW_POLYS:
        cv2.fillPoly(brows, [lb[poly].round().astype(np.int32)], 1)
    brows = cv2.dilate(brows, np.ones((3, 3), np.uint8))
    x0, x1 = lb[FACE_OVAL, 0].min(), lb[FACE_OVAL, 0].max()
    upper = ((xx > x0) & (xx < x1) & (yy > lb[10, 1] - gap * 1.5) & (yy < lb[UPPER_LIDS, 1].min() - gap * 0.1)).astype(np.uint8)
    zone = np.maximum(upper, bridge) * (1 - eyes) * (1 - brows)
    alpha = alpha * cv2.GaussianBlur(zone.astype(np.float32), (0, 0), 1.5)
    # 가닥은 세로·비스듬히, 눈썹 아랫선·쌍꺼풀 선은 가로 → 가로로 긴 덩어리는 제외 (메우면 눈썹 아래가 얼룩짐)
    n, lab, stats, _ = cv2.connectedComponentsWithStats((alpha > 0.2).astype(np.uint8), 8)
    flat = np.zeros(n, np.uint8)
    for k in range(1, n):
        flat[k] = stats[k, cv2.CC_STAT_WIDTH] >= stats[k, cv2.CC_STAT_HEIGHT] * FLAT_RATIO
    drop = cv2.dilate(flat[lab], np.ones((5, 5), np.uint8))
    return alpha * (1 - drop)


# AI 얼굴이 원본과 이보다 크게 다르면 (폭·눈~턱 길이 비율) 잘못 생성으로 봄, 그 아래는 무조건 붙임
FIT_MAX = 0.12
# 다중 해상도 섞기 단계 수 (낮은 해상도일수록 넓게 섞여 색·조명 경계가 사라짐, 가장 고운 단계는 가닥이 살아 있게 좁게)
BLEND_LEVELS = 6


def overlap_matrix(lg: np.ndarray, lb: np.ndarray) -> np.ndarray:
    """AI 얼굴 점 전체가 원본과 최대한 겹치게 하는 변환 (회전·균일 크기·이동, 튀는 점은 무시)"""
    m, _ = cv2.estimateAffinePartial2D(lg[:468], lb[:468], method=cv2.LMEDS)
    if m is None:
        raise ValueError("합성 결과를 원본에 맞추지 못했습니다")
    return m


def face_ratio(la: np.ndarray, lb: np.ndarray) -> tuple[float, float]:
    """눈 맞춤 후 AI 얼굴 / 원본 얼굴 (광대 폭 비율, 눈~턱 길이 비율)"""
    width = float(np.linalg.norm(la[454] - la[234]) / np.linalg.norm(lb[454] - lb[234]))
    eye = lambda lm: lm[[33, 263]].mean(0)
    length = float(np.linalg.norm(la[152] - eye(la)) / np.linalg.norm(lb[152] - eye(lb)))
    return width, length


def _pyramid_blend(a: np.ndarray, b: np.ndarray, mask: np.ndarray, levels: int = BLEND_LEVELS) -> np.ndarray:
    """다중 해상도 섞기: mask=1이면 a, 0이면 b (색·조명은 넓게, 질감·가닥은 좁게 이어짐)"""
    a, b = a.astype(np.float32), b.astype(np.float32)
    m = mask.astype(np.float32)
    ga, gb, gm = [a], [b], [m]
    for _ in range(levels):
        ga.append(cv2.pyrDown(ga[-1]))
        gb.append(cv2.pyrDown(gb[-1]))
        gm.append(cv2.pyrDown(gm[-1]))
    out = ga[-1] * gm[-1][..., None] + gb[-1] * (1 - gm[-1][..., None])
    for i in range(levels - 1, -1, -1):
        size = (ga[i].shape[1], ga[i].shape[0])
        la = ga[i] - cv2.pyrUp(ga[i + 1], dstsize=size)
        lb_ = gb[i] - cv2.pyrUp(gb[i + 1], dstsize=size)
        out = cv2.pyrUp(out, dstsize=size) + la * gm[i][..., None] + lb_ * (1 - gm[i][..., None])
    return np.clip(out, 0, 255).astype(np.uint8)


def fit_ai(base: np.ndarray, gen: np.ndarray) -> np.ndarray:
    """AI 사진을 원본에 겹칠 변환 (회전·균일 크기·이동만, 휘지 않음)

    휘어서 맞추면 주변 머리가 늘어나고 구겨짐 → 통째로만 옮기고 원본 얼굴을 붙여 경계를 섞음
    얼굴 비율이 FIT_MAX 넘게 다르면 ValueError (고개 돌림 등 붙일 수 없는 결과만)
    """
    h, w = base.shape[:2]
    lb = landmarks(base)
    m = overlap_matrix(landmarks(gen), lb)
    la = landmarks(cv2.warpAffine(gen, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE))
    width, length = face_ratio(la, lb)
    if abs(width - 1) > FIT_MAX or abs(length - 1) > FIT_MAX:
        raise ValueError("합성이 사진과 맞지 않게 만들어졌어요. 정면을 바라본 다른 사진으로 다시 시도해 주세요")
    return m


def transplant_hair(base: np.ndarray, gen: np.ndarray, fit=None) -> np.ndarray:
    """원본 사진 위에 AI 머리를 얹음 (결과 크기 = 원본, 원본 얼굴은 크기·위치·모양 그대로)

    1. AI 이미지를 원본에 통째로 겹침 (회전·크기·위치만, 휘지 않음)
    2. 원본은 윗눈꺼풀 바로 위~턱 끝 얼굴 + 원본 자리에 옮긴 AI 눈썹, 이마·눈썹 둘레는 원본 톤 맞춘 AI 피부
       얼굴 위로 내려온 AI 머리(앞머리 등)는 맨 위
    3. 다중 해상도로 섞음 (이마·볼 경계의 색·질감 차이가 이어짐)
    """
    h, w = base.shape[:2]
    lb = landmarks(base)
    m = fit if fit is not None else fit_ai(base, gen)
    aligned = cv2.warpAffine(gen, m, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
    brow, lid = lb[BROWS, 1].min(), lb[UPPER_LIDS, 1].min()
    gap = lid - brow
    old_hair, face, old_bg, body = segment(base)

    new_hair, gen_skin, new_bg, gbody = segment(aligned)
    yy, xx = np.mgrid[0:h, 0:w]
    inside = (xx > lb[FACE_OVAL, 0].min()) & (xx < lb[FACE_OVAL, 0].max())
    aligned = _match_skin_tone(base, aligned, face, gen_skin, old_hair, new_hair, inside, yy, brow, lid)
    aligned = _match_background(base, aligned, old_bg, new_bg)
    aligned = _match_region_tone(base, aligned, (face, body, gen_skin, gbody, old_hair, new_hair), lb, yy)

    # 원본은 윗눈꺼풀 바로 위~턱 끝 얼굴 윤곽 안 (귀 제외), 나머지(이마·목·옷·배경)는 AI
    # 2026-11-26: 예전엔 눈썹 조금 위부터 원본 → 원본 앞머리 지운 자리(inpaint) 회색 얼룩이 눈썹 둘레에 남음
    # 눈썹은 _ai_brows가 원본 눈썹 자리에 옮긴 AI 눈썹 덩어리를 그대로 씀 (눈썹·눈 간격은 원본 그대로)
    oval = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(oval, cv2.convexHull(lb[FACE_OVAL].round().astype(np.int32)), 1)
    above_lid = np.clip((yy - (lid - gap * 0.45)) / max(1.0, gap * 0.2), 0, 1)
    brow_patch = np.zeros((h, w), np.uint8)
    for poly in BROW_POLYS:
        cv2.fillPoly(brow_patch, [lb[poly].round().astype(np.int32)], 1)
    kp = max(3, int(gap * 0.3)) | 1
    brow_patch = cv2.GaussianBlur(cv2.dilate(brow_patch, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kp, kp))).astype(np.float32), (0, 0), max(1.5, gap * 0.1))
    face_keep = oval.astype(np.float32) * np.maximum(above_lid, brow_patch)
    # 원래 머리가 덮던 곳은 AI 피부, 눈썹 자리는 제외 (눈썹을 지나는 원본 가닥 몇 개 때문에 AI로 바꾸면 눈썹이 조각나 보임)
    brow_zone = np.zeros((h, w), np.uint8)
    for poly in BROW_POLYS:
        cv2.fillPoly(brow_zone, [lb[poly].round().astype(np.int32)], 1)
    kb = max(3, int(gap * 0.1)) | 1
    brow_zone = cv2.GaussianBlur(cv2.dilate(brow_zone, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kb, kb))).astype(np.float32), (0, 0), max(1.5, gap * 0.06))
    face_keep = face_keep * (1 - np.clip((old_hair - 0.3) / 0.3, 0, 1) * (1 - brow_zone))
    # 얼굴 위 가는 원본 가닥(분할이 놓침)은 원본 주변 피부로 메움 (AI 피부로 채우면 눈 위에 AI 눈꺼풀·속눈썹이 어긋나 튀어나옴)
    strands = _old_strands(base, lb, gap)
    kt = max(3, int(gap * 0.08)) | 1
    strand_core = cv2.dilate((strands > 0.2).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kt, kt)))
    if strand_core.any():
        base = cv2.inpaint(base, strand_core * 255, max(3, int(gap * 0.1)), cv2.INPAINT_TELEA)
    # 눈썹·눈두덩을 세로로 지나는 가닥은 같은 줄 좌우로 메움
    brow_strands = _brow_strands(base, lb, gap)
    if brow_strands.any():
        base = _fill_rows(base, brow_strands)
    # 눈썹은 AI 눈썹을 원본 눈썹 자리로 옮겨 씀
    base = _ai_brows(base, aligned, lb, landmarks(aligned), gap)
    # 맨 위: 얼굴 위로 내려온 AI 머리
    face_keep = face_keep * (1 - np.clip((new_hair - 0.3) / 0.4, 0, 1))
    keep = cv2.GaussianBlur(face_keep.astype(np.float32), (0, 0), max(1.5, gap * 0.04))
    return _pyramid_blend(base, aligned, keep)


# ------------------------------------------------------------------
# 생성 파이프라인
# ------------------------------------------------------------------

def new_asset_dir() -> str:
    return secrets.token_urlsafe(24)


def asset_url(asset_dir: str, name: str) -> str:
    return f"/{get_settings().studio_dir.strip('/')}/{asset_dir}/{name}"


def asset_exists(asset_dir: str, name: str) -> bool:
    return (Path(get_settings().studio_dir) / asset_dir / name).is_file()


# 참조 사진 얼굴을 덮는 색 (피부색이면 AI가 얼굴로 읽어 그대로 그림)
REF_FACE_GRAY = 150


def _style_ref(style: HairStyleCatalog) -> bytes | None:
    """카탈로그 사진이 로컬 static에 있으면 참조 이미지로 사용"""
    if not style.image or not style.image.startswith("/static/"):
        return None
    path = Path(style.image.lstrip("/"))
    if not path.is_file():
        return None
    # 카탈로그 사진은 표에서 잘라 옆 칸 이름표가 섞여 있음 (F027에 "Flower perm" → 생머리가 곱슬로 생성)
    # 사람 밖 배경을 흰색으로 덮어 글자 제거
    # 선명한 정면 사진이면 AI가 참조 모델 얼굴·구도를 그대로 그림 (사람이 바뀜) → 얼굴 피부를 회색으로 가림, 머리는 그대로
    img = decode_image(path.read_bytes())
    _, face, bg, _ = segment(img)
    bg = cv2.GaussianBlur((bg > 0.5).astype(np.float32), (0, 0), 1)[..., None]
    # 이마까지 가리면 앞머리 가닥도 같이 지워져 AI가 이마를 훤히 드러낸 듬성한 앞머리로 그림 → 눈썹 아래만 가림
    cover = face > 0.4
    try:
        lb = landmarks(img)
        top = lb[BROWS, 1].min() + (lb[UPPER_LIDS, 1].min() - lb[BROWS, 1].min()) * 0.3
        cover &= np.mgrid[0:img.shape[0], 0:img.shape[1]][0] > top
    except ValueError:
        pass
    face = cv2.GaussianBlur(cover.astype(np.float32), (0, 0), 2)[..., None]
    out = img * (1 - bg) + 255 * bg
    return encode_jpeg((out * (1 - face) + REF_FACE_GRAY * face).astype(np.uint8))


# 원래 머리가 길면 AI가 뒤쪽에 남겨두는 경우가 있어 길이 한계를 명시 (남자 스타일은 더 짧게)
LENGTH_RULES = {
    ("male", "short"): "The new hair is a SHORT men's cut: short back and sides, ears visible, ends at the top of the neck. No hair on the neck below the hairline, none on the shoulders.",
    ("male", "medium"): "The new hair is a MEDIUM men's cut: it may lightly cover the ears and ends at the nape, above the collar. No hair below the collar or on the shoulders.",
    ("male", "long"): "The new hair is a LONG men's style: follow the target length from chin to shoulders or below as specified. Preserve a tied bun, braids or an afro when these define the target; do not force loose shoulder-length hair onto every long style.",
    ("female", "short"): "The new hair is SHORT: match the specified pixie or bob length, from cropped ears/nape to chin-length. A bob may reach just below the chin but must stay above the shoulders. Do not turn a bob into a pixie. Show ears only as appropriate for the target.",
    ("female", "medium"): "The new hair is MEDIUM length: it must end between the chin and the shoulders. No hair below the shoulders.",
    ("female", "long"): "The new hair is LONG: it falls past the shoulders.",
}


def length_rule(style: HairStyleCatalog) -> str:
    male = getattr(style.sex, "value", style.sex) == "male"
    rule = LENGTH_RULES.get(("male" if male else "female", style.length), "")
    # 여성 사진에 남자 컷을 넣으면 AI가 단발로 바꾸는 경향
    if male and style.length in ("short", "medium"):
        rule += " This is a men's haircut: keep it this short even if the person looks feminine. Do not turn it into a bob."
    return rule


def style_prompt(style: HairStyleCatalog, has_ref: bool) -> str:
    male = getattr(style.sex, "value", style.sex) == "male"
    desc = f"{'a men' + chr(39) + 's haircut, ' if male else ''}{style.name} ({style.length} length, {style.texture})"
    if style.guide:
        # 이전 M011 설명에 남아 있는 참조 사진 무시 지시는 새 참조 규칙과 충돌한다.
        guide = style.guide.replace(
            "참고 사진에서는 대략적인 길이와 외곽 형태만 참고하며, 숱·가닥 굵기·분리감·결·컬·마감 질감은 이 설명을 우선한다.",
            "",
        ).strip()
        desc += f" - {guide}"
    if has_ref:
        return STYLE_PROMPT.format(
            target="the hairstyle shown in the SECOND image and described below",
            style=desc,
            length_rule=length_rule(style),
            ref_note=(
                "REFERENCE ROLES: the FIRST image defines the person's identity, anatomy, pose and framing. "
                "The SECOND image defines the target HAIRCUT: match silhouette, length relative to chin/shoulders, "
                "layering, parting, fringe presence or absence, fringe density, curl size, curl placement and volume. "
                "Use text to identify the style and the reference to resolve vague names and approximate length categories. "
                "Preserve deliberate waves, tight curls and shaggy layers. Do not add bangs when the reference has none. "
                "Discard ALL color information from the SECOND image. Its face is masked gray on purpose: take only the hair from it. "
                "Do not copy its skull proportions, pose, framing, clothing or background."
            ),
        )
    return STYLE_PROMPT.format(target="this hairstyle", style=desc, length_rule=length_rule(style), ref_note="")


def hair_hex(img: np.ndarray) -> str | None:
    """사진 속 원래 머리색 (머리 픽셀 Lab 중앙값), 머리가 거의 안 보이면 None"""
    hair = segment(img)[0] > 0.8
    if hair.sum() < 500:
        return None
    lab = np.median(cv2.cvtColor(img, cv2.COLOR_BGR2LAB)[hair], 0).astype(np.uint8)
    b, g, r = cv2.cvtColor(lab[None, None], cv2.COLOR_LAB2BGR)[0, 0]
    return f"#{r:02x}{g:02x}{b:02x}"


def _save_debug(asset_dir: str, images: dict[str, np.ndarray]) -> None:
    """static 밖에 PNG로 저장 (원본 얼굴이 URL로 노출되지 않게)"""
    dbg = Path(get_settings().studio_debug_dir) / asset_dir
    dbg.mkdir(parents=True, exist_ok=True)
    for name, img in images.items():
        (dbg / f"{name}.png").write_bytes(cv2.imencode(".png", img)[1].tobytes())


def _write(asset_dir: str, files: dict[str, bytes]) -> None:
    out = Path(get_settings().studio_dir) / asset_dir
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (out / name).write_bytes(data)


def _base_files(name: str, img: np.ndarray, mask: np.ndarray) -> dict[str, bytes]:
    return {f"{name}.jpg": encode_jpeg(img), f"{name}_mask.png": cv2.imencode(".png", mask)[1].tobytes()}


# 피부보다 이 값 이상 어두워야 가닥으로 봄 (그늘·잡티 제외, L 0~255)
SEE_THROUGH_MIN = 20


def base_hair_mask(img: np.ndarray) -> np.ndarray:
    """머리 분할 마스크에 이마 위의 가는 가닥을 더함."""
    strands = see_through_strands(img)
    return np.maximum(hair_mask(img), (strands * 255).astype(np.uint8))


def see_through_strands(img: np.ndarray) -> np.ndarray:
    """이마 위 시스루 가닥 알파 (0~1)

    분할 모델은 이마 위 1~2px 가닥을 놓쳐 염색이 안 됨 → 이마 구간만 자기 픽셀로 계산
    짙은 가닥은 주변 피부보다 확연히 어두움, 가닥보다 굵은 닫힘 연산으로 가닥을 지운 밝기를 피부 기준으로 사용
    """
    w = img.shape[1]
    L = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32)
    k = max(5, int(w * 0.02)) | 1
    skin = cv2.morphologyEx(L, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    hair = segment(img)[0] > 0.9
    hair_l = float(np.median(L[hair])) if hair.sum() > 100 else 60.0
    alpha = np.clip((skin - L - SEE_THROUGH_MIN) / np.maximum(skin - hair_l - SEE_THROUGH_MIN, 1), 0, 1)
    return alpha * forehead_zone(img)


def forehead_zone(img: np.ndarray) -> np.ndarray:
    """앞머리 구간 (0~1, 경계 부드럽게): 얼굴 폭 안, 헤어라인 위쪽부터 윗눈꺼풀 바로 위까지, 눈썹 제외

    눈썹은 가닥처럼 어두워 가닥으로 잡힘 → 눈썹 윤곽 랜드마크 다각형을 넓혀서 제외
    """
    h, w = img.shape[:2]
    lb = landmarks(img)
    brow, lid = lb[BROWS, 1].min(), lb[UPPER_LIDS, 1].min()
    gap = lid - brow
    x0, x1 = lb[FACE_OVAL, 0].min(), lb[FACE_OVAL, 0].max()
    top = lb[10, 1] - gap * 1.5
    yy, xx = np.mgrid[0:h, 0:w]
    zone = ((xx > x0) & (xx < x1) & (yy > top) & (yy < lid - gap * 0.1)).astype(np.float32)
    brows = np.zeros((h, w), np.uint8)
    for poly in BROW_POLYS:
        cv2.fillPoly(brows, [lb[poly].round().astype(np.int32)], 1)
    k = max(3, int(gap * 0.2)) | 1
    brows = cv2.dilate(brows, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    return cv2.GaussianBlur(zone * (1 - brows), (0, 0), max(2.0, gap * 0.1))


# 잘못 생성 판정 (정상 19건 최대: 크기 3.3%·기울기 0.8°·돌림 0.065·남는 넓이 최소 88%, 망한 건: 12.2°·60%)
# 크기는 정렬이 비율로 맞춰서 크게 키운 것만 거름 (얼굴을 5~9% 키운 결과도 합성은 정상, 잘리는 넓이는 GEN_MIN_KEEP이 거름)
GEN_MAX_SCALE, GEN_MAX_ROLL, GEN_MAX_YAW, GEN_MIN_KEEP = 0.12, 4.0, 0.15, 0.8


# 원본 최대 1024px과 비슷한 1K로 생성
OUTPUT_SIZE = "1K"


def _pad_input(img: np.ndarray) -> tuple[np.ndarray, str, tuple[int, int]]:
    """AI 출력 비율에 맞춘 이미지와 위·왼쪽 패딩 크기를 반환."""
    h, w = img.shape[:2]
    aspect = closest_aspect(w, h)
    ratio = ASPECT_RATIOS[aspect]
    ph, pw = max(h, round(w / ratio)), max(w, round(h * ratio))
    top, left = (ph - h) // 2, (pw - w) // 2
    padded = cv2.copyMakeBorder(img, top, ph - h - top, left, pw - w - left, cv2.BORDER_REPLICATE)
    # AI가 가장자리 복사 줄무늬를 따라 그리지 않도록 패딩만 흐림
    pad = np.ones(padded.shape[:2], bool)
    pad[top:top + h, left:left + w] = False
    padded[pad] = cv2.GaussianBlur(padded, (0, 0), max(h, w) * 0.05)[pad]
    return padded, aspect, (top, left)


def _crop_output(raw: np.ndarray, padded_shape: tuple[int, int], pad: tuple[int, int], size: tuple[int, int]) -> np.ndarray:
    """AI 출력을 입력 크기로 되돌리고 패딩을 제거."""
    top, left = pad
    h, w = size
    raw = cv2.resize(raw, (padded_shape[1], padded_shape[0]), interpolation=cv2.INTER_AREA)
    return raw[top:top + h, left:left + w]


# 앞머리 끝 쪽 염색 알파를 이만큼 낮춤 (진하게 칠하면 이마 위 가닥이 덩어리처럼 무거움)
FRINGE_SOFT = 0.25


def soften_fringe(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """헤어라인 아래 이마 위 가닥만 마스크를 연하게 (위쪽 머리 덩어리는 그대로, uint8)"""
    lb = landmarks(img)
    gap = lb[UPPER_LIDS, 1].min() - lb[BROWS, 1].min()
    yy = np.mgrid[0:img.shape[0], 0:img.shape[1]][0]
    ramp = np.clip((yy - (lb[10, 1] - gap * 0.5)) / (gap * 0.8), 0, 1)
    return (mask * (1 - FRINGE_SOFT * forehead_zone(img) * ramp)).astype(np.uint8)


def compose_bases(orig: np.ndarray, brown_raw: np.ndarray) -> dict[str, bytes]:
    """AI 결과 → 원본 위 합성·마스크 → 저장할 파일 (AI 재호출 없이 다시 만들 때도 사용)"""
    fit = fit_ai(orig, brown_raw)
    brown = transplant_hair(orig, brown_raw, fit)
    mask = soften_fringe(brown, base_hair_mask(brown))
    y0, y1, x0, x1 = _valid_box(orig, fit, brown_raw.shape[:2])
    crop = lambda img: np.ascontiguousarray(img[y0:y1, x0:x1])
    return _base_files("brown", crop(brown), crop(mask))


# 자른 뒤 남길 여유 (정렬 보간으로 경계 1~2px가 흐림)
CROP_PAD = 2


def _valid_box(orig: np.ndarray, fit: np.ndarray, raw_shape: tuple[int, int]) -> tuple[int, int, int, int]:
    """실제 AI 출력 픽셀이 남은 직사각형 (y0, y1, x0, x1)

    정렬 과정에서 복제된 가장자리를 피하도록 이미지와 마스크에 같은 크롭을 적용.
    빈 픽셀이 가장 많은 변부터 한 줄씩 안쪽으로
    """
    h, w = orig.shape[:2]
    valid = cv2.warpAffine(np.full(raw_shape, 255, np.uint8), fit, (w, h), flags=cv2.INTER_NEAREST, borderValue=0) == 255
    y0, y1, x0, x1 = 0, h, 0, w
    while y1 - y0 > h // 2 and x1 - x0 > w // 2 and not valid[y0:y1, x0:x1].all():
        v = valid[y0:y1, x0:x1]
        bad = {"t": (~v[0]).sum(), "b": (~v[-1]).sum(), "l": (~v[:, 0]).sum(), "r": (~v[:, -1]).sum()}
        side = max(bad, key=bad.get)
        y0 += side == "t"
        y1 -= side == "b"
        x0 += side == "l"
        x1 -= side == "r"
    if (y0, y1, x0, x1) == (0, h, 0, w):
        return 0, h, 0, w
    return y0 + CROP_PAD, y1 - CROP_PAD, x0 + CROP_PAD, x1 - CROP_PAD


def generate(photo: bytes, style: HairStyleCatalog, asset_dir: str) -> str | None:
    """사진 + 스타일 → 중간 갈색(brown) 베이스 저장, 원래 머리색 반환

    Flash 1회로 한 장 그림 (Lite 탈색은 뭉개지고 뿌리가 남음), 프리셋 색은 전부 이 베이스 위에 칠함
    """
    settings = get_settings()
    orig = prepare_photo(decode_image(photo))  # 못 쓰는 사진은 AI 호출 전에 실패
    padded, aspect, pad = _pad_input(orig)

    ref = _style_ref(style)
    images = [encode_jpeg(padded)] + ([ref] if ref else [])
    # 1회만 생성 (재시도하면 2분 넘음)
    raw = decode_image(edit_image(settings.studio_style_model, images, style_prompt(style, ref is not None), aspect, size=OUTPUT_SIZE), 4096)
    brown_raw = _crop_output(raw, padded.shape[:2], pad, orig.shape[:2])
    # AI가 구도·각도를 바꿔 그리면 합성이 망가짐 → 엉망인 결과 대신 다시 시도 안내 (실패는 비회원 횟수에서 안 셈)
    issue = _generation_issue(orig, brown_raw)
    if issue:
        logger.info("[스튜디오] 잘못 생성 (%s)", issue)
        if settings.studio_debug:  # 판정 기준 조정용
            _save_debug(asset_dir, {"orig": orig, "bad_brown": brown_raw})
        raise ValueError("합성이 사진과 맞지 않게 만들어졌어요. 정면을 바라본 다른 사진으로 다시 시도해 주세요")
    _write(asset_dir, compose_bases(orig, brown_raw))
    if settings.studio_debug:
        _save_debug(asset_dir, {"orig": orig, "brown_raw": brown_raw})
    return hair_hex(orig)


def process_render(render_id: int, photo: bytes) -> None:
    """백그라운드 작업, 자체 세션 사용 (원본 사진은 메모리에서만 쓰고 버림)"""
    with SessionLocal() as db:
        render = db.get(HairRender, render_id)
        if render is None:
            return
        style = db.get(HairStyleCatalog, render.style_id)
        try:
            render.hair_hex = generate(photo, style, render.asset_dir)
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
