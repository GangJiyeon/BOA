"""AI 스튜디오 헤어 합성

1. 원본 + 카탈로그 스타일 사진 → 세 가지 머리색 베이스 (style 모델)
2. 각 베이스의 머리카락만 원본 사진 위에 옮겨 붙임 (얼굴·얼굴형은 원본 픽셀 그대로)
3. 베이스별 머리 마스크 PNG 저장 → 프론트에서 32색 프리셋으로 색만 바꿈

각 색상은 가장 가까운 베이스에서 바꿔 앞머리와 머리 경계가 덜 끊기게 함
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
FRAME_LOCK = """ABSOLUTE RULE - THE FRAMING IS LOCKED. This is an in-place, pixel-aligned edit of each panel, NOT a new photo.
Every panel keeps the exact same camera distance, crop and composition as the FIRST image. Do NOT crop, zoom in or out, or move the person down, up or sideways.
The face keeps EXACTLY the same size. The top of the head, eyes, mouth, chin, shoulders and the edges of the clothing stay at exactly the same pixel positions. Keep the same empty background space above the head as in the FIRST image.
If the new hair is taller or wider than the original, it grows into the existing background or is cut off by the panel edge; never shrink, lower or move the person to make room for it.
Keep the same facial expression and mouth shape (a smile stays the same smile, open lips and visible teeth stay as they are)."""

# 밝은 칸은 펄 블론드 (베이지는 피부와 색 거리 약 8로 앞머리 가닥·이마 구분 안 됨, 펄은 피부보다 밝고 색 거리 약 12)
# 얼굴 크기·위치는 고정하고, 모발 질감과 앞머리 숱은 목표 스타일을 따른다.
STYLE_PROMPT ="""TASK: replace the person's haircut with {target}.
TARGET HAIRCUT: {style}
{length_rule}
Reconstruct the cut, parting, fringe placement, density, volume and strand flow to implement this target. The original haircut is NOT locked. A recolor or minor cleanup of the original hairstyle is not sufficient. Replace conflicting original fringe gaps, pointed clumps and parting; retain only features that actually match the target. Keep the anatomical head shape beneath the new haircut natural and unchanged.
{ref_note}

""" + FACE_LOCK + """

""" + FRAME_LOCK + """

The FIRST image contains the same source photo in three side-by-side panels. Edit ALL THREE panels with the SAME target haircut. Only the dye color differs.
Remove leftover original hair behind the neck or on the shoulders where it does not belong to the target haircut.
LEFT panel hair color: natural dark brown (level 4).
MIDDLE panel hair color: medium natural brown (level 7).
RIGHT panel hair color: very light pearl blonde (level 10), visibly much lighter than the middle, pale and luminous with a faint cool tint; natural hair texture and soft shading between strands stay visible.
Each panel has ONE uniform dye color from roots to ends, including sides, inner layers and nape. These color instructions override source/reference colors and any coloring terms in the style description. No ombre, balayage, dark roots, bleached ends or two-tone sections.
Render natural strands with soft, color-preserving shine. No white strand outlines, silver or gray streaks, blown-out highlights, coarse tonal bands or jagged compression texture.
HAIR SURFACE: follow the target texture and strand flow. Preserve intentional tight curls, irregular perm texture, shaggy layers, braids, locs and afro volume when present in the target; do not relax the target curl pattern or force every style into smooth, long curves. Remove only image noise, compression artifacts and stray fuzz that are not part of the target style. The finish is soft and natural like a real salon photo: smooth, gently flowing strands with soft natural shine; never crunchy, wiry, frizzy, stiff or plastic-looking.
FRINGE ONLY: follow the target's fringe presence, density, strand thickness, separation and placement. Preserve fine, sparse see-through bangs and their natural forehead gaps when specified; preserve dense bangs when specified. Do not impose a minimum fringe density or thicken fine strands. If the target has no bangs, keep the forehead open. Avoid artificial translucent haze over the forehead while preserving actual fine strands. The rest of the hair also follows the target texture.
AROUND THE HAIR (all panels): where skin shows between fringe strands, keep the same warm natural skin tone and brightness as the cheeks, with at most a soft shadow directly under each strand and no gray or dark band on the forehead. Do not tint the eyebrows with the hair color. No glow, halo or color cast around the hair outline; the skin and background right next to the hair stay identical across the three panels.
Keep the FIRST image's face, eyebrows, ears, skin, head angle, gaze, clothing and background. Do NOT rotate the head to frontal. Keep the three-panel layout and body proportions. Face preservation does not mean preserving the original hairstyle."""

# 윤곽 맞춤 때 고정할 점: 눈꼬리·코·입꼬리·턱
ANCHORS = [33, 133, 362, 263, 1, 4, 61, 291, 13, 14, 152, 168, 6, 197]
# 머리 정렬 기준점: 눈꼬리·콧대·코·눈썹 (머리는 얼굴 위쪽에 붙음, 입·턱까지 쓰면 AI 표정 차이에 끌려 눈썹 위가 평균 3.7px·최대 6.9px 뜸 → 2.2·3.2px)
# 아래 얼굴은 원본, 턱선·몸은 따로 맞춤
HAIR_ANCHORS = [33, 133, 362, 263, 168, 6, 197, 1, 4, 70, 63, 105, 66, 107, 336, 296, 334, 293, 300]
FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
BROWS = [70, 63, 105, 66, 107, 336, 296, 334, 293, 300]
UPPER_LIDS = [159, 386]
# 눈·코·입 (AI·원본 얼굴이 원래 달라 색 차이로 가닥 판정하면 오판)
FACE_CORE = [33, 133, 362, 263, 61, 291, 1, 4, 13, 14, 152, 168]
# 눈 윤곽 (눈꺼풀·눈꼬리)
EYES = [[33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246],
        [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]]
# 눈 보호 범위 (눈썹~눈 간격 대비, 아이라인 꼬리·쌍꺼풀까지)
EYE_GUARD = 0.7
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


def landmarks(img: np.ndarray) -> np.ndarray:
    """468(+10)개 얼굴 랜드마크 픽셀 좌표, 얼굴 없으면 ValueError"""
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


def _generation_issue(orig: np.ndarray, raws: list[np.ndarray]) -> str | None:
    """AI 결과가 원본과 구도·각도가 크게 달라 합성하면 망가지는지, 문제면 이유"""
    lb = landmarks(orig)
    for raw in raws:
        try:
            lr = landmarks(raw)
        except ValueError:
            return "얼굴 없음"
        m, _ = cv2.estimateAffinePartial2D(lr[HAIR_ANCHORS], lb[HAIR_ANCHORS])
        if m is None:
            return "정렬 실패"
        if abs(float(np.linalg.norm(m[:, 0])) - 1) > GEN_MAX_SCALE:
            return "얼굴 크기"
        if abs(_roll(lr) - _roll(lb)) > GEN_MAX_ROLL:
            return "고개 기울기"
        if abs(_yaw(lr) - _yaw(lb)) > GEN_MAX_YAW:
            return "고개 돌림"
    y0, y1, x0, x1 = _valid_box(orig, raws)
    if (y1 - y0) * (x1 - x0) / (orig.shape[0] * orig.shape[1]) < GEN_MIN_KEEP:
        return "구도"
    return None


def segment(img: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(머리 확률, 얼굴 피부 확률, 배경 확률, 몸 피부 확률), 0~1·이미지 크기"""
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


def _guided_filter(img: np.ndarray, p: np.ndarray, r: int = 8, eps: float = 1e-3) -> np.ndarray:
    """컬러 guided filter (He et al.), p를 img 경계에 맞춰 다듬음"""
    box = lambda x: cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1))
    guide = img.astype(np.float32) / 255
    mean_i = [box(guide[..., c]) for c in range(3)]
    mean_p = box(p)
    cov_ip = np.stack([box(guide[..., c] * p) - mean_i[c] * mean_p for c in range(3)], -1)
    var = np.empty(p.shape + (3, 3), np.float32)
    for i in range(3):
        for j in range(3):
            var[..., i, j] = box(guide[..., i] * guide[..., j]) - mean_i[i] * mean_i[j] + (eps if i == j else 0)
    a = np.einsum("...ij,...j->...i", np.linalg.inv(var), cov_ip)
    b = mean_p - sum(a[..., c] * mean_i[c] for c in range(3))
    return sum(box(a[..., c]) * guide[..., c] for c in range(3)) + box(b)


def _refine_hair_tiles(img: np.ndarray, coarse: np.ndarray) -> np.ndarray:
    """머리 ROI와 겹치는 조각의 분할 확률을 혼합. 사진은 변형하지 않음."""
    h, w = coarse.shape
    ys, xs = np.where(coarse > 0.35)
    if len(xs) < 64:
        return coarse
    margin = max(16, round(max(xs.max() - xs.min(), ys.max() - ys.min()) * 0.18))
    x0, x1 = max(0, xs.min() - margin), min(w, xs.max() + margin + 1)
    y0, y1 = max(0, ys.min() - margin), min(h, ys.max() + margin + 1)
    rh, rw = y1 - y0, x1 - x0
    total, weights = coarse.copy(), np.ones((h, w), np.float32)

    def add(x: int, y: int, tw: int, th: int) -> None:
        prob = segment(np.ascontiguousarray(img[y:y + th, x:x + tw]))[0]
        wx = np.sin(np.pi * (np.arange(tw) + 0.5) / tw) ** 2
        wy = np.sin(np.pi * (np.arange(th) + 0.5) / th) ** 2
        weight = (wy[:, None] * wx[None, :] * 2).astype(np.float32)
        total[y:y + th, x:x + tw] += prob * weight
        weights[y:y + th, x:x + tw] += weight

    add(x0, y0, rw, rh)
    side = max(256, round(max(rh, rw) * 0.65))
    tw, th = min(side, rw), min(side, rh)
    if tw < rw or th < rh:
        nx = max(1, int(np.ceil((rw - tw) / (tw * 0.5))) + 1)
        ny = max(1, int(np.ceil((rh - th) / (th * 0.5))) + 1)
        for y in np.linspace(y0, y1 - th, ny).round().astype(int):
            for x in np.linspace(x0, x1 - tw, nx).round().astype(int):
                add(x, y, tw, th)
    return np.clip(total / weights, 0, 1)


def hair_mask_fine(img: np.ndarray) -> np.ndarray:
    """가닥 경계까지 따라가는 머리 마스크 (밝은 베이스용)

    저해상도 분할 마스크는 잔머리를 놓쳐, 밝은 베이스를 어둡게 칠하면 바깥 가닥이 플래티넘으로 남아 흰 테두리가 됨
    """
    hair, face, _, _ = segment(img)
    hair = _refine_hair_tiles(img, hair)
    t = np.clip((_guided_filter(img, hair.astype(np.float32)) - 0.3) / 0.4, 0, 1)
    m = t * t * (3 - 2 * t) * (1 - np.clip((face - 0.4) / 0.3, 0, 1))  # 얼굴 피부 쪽은 자름
    # 외곽 팽창·강도 증가는 적용하지 않음. 추출한 범위와 강도를 그대로 유지.
    # 경계만 살짝 부드럽게 처리.
    m = cv2.GaussianBlur(m, (0, 0), 1.5 * img.shape[1] / 800)
    return (m * 255).astype(np.uint8)


# 밝은 베이스 이마에 새로 더하는 가닥 상한 = 이마 구간 넓이 비율 (놓친 가닥 몇 개는 5% 안팎)
LIGHT_ADD_MAX = 0.15
# 가닥으로 볼 최대 굵기 = 눈썹~윗눈꺼풀 간격 비율 (이보다 넓게 뭉친 추가분은 피부 덩어리)
LIGHT_ADD_WIDTH = 0.3
# 볼 피부와 a·b 거리가 이 값 이하면 피부색 그대로 (같은 사진 피부 픽셀 편차 2~4, Lab 0~255)
SKIN_AB_MIN = 3.0
# 머리 a·b 거리의 이 비율 이상이면 가닥 색 (펄 머리 약 11, 이마 피부 3~7)
SKIN_AB_HAIR = 0.6
# 눈썹 제외 범위 = 눈썹~윗눈꺼풀 간격 비율 (경계 고리까지 덮게), 아래로 더 내리는 폭 (눈썹 꼬리 아래 조각)
BROW_GUARD, BROW_GUARD_DOWN = 0.35, 0.3
# 눈썹 자리 색 비교 가중치 (L, a, b): 밝은 머리 하이라이트는 밝기 편차가 커서 L 비중 낮춤
BROW_LAB_W = np.array([0.4, 1, 1], np.float32)
# 눈썹 색이 머리색과 이 거리 안이면 머리가 눈썹을 덮은 것 (가중 Lab), 머리·눈썹 거리 차이 이 폭에서 0→1
BROW_COVERED, BROW_SOFT = 10.0, 8.0


def _cheek_skin_lab(img: np.ndarray) -> np.ndarray | None:
    """볼 피부 Lab 중앙값 (윗눈꺼풀 아래, 얼굴 확률 높고 머리 확률 낮은 곳)"""
    h, w = img.shape[:2]
    lb = landmarks(img)
    brow, lid = lb[BROWS, 1].min(), lb[UPPER_LIDS, 1].min()
    hair, face, _, _ = segment(img)
    yy, xx = np.mgrid[0:h, 0:w]
    inside = (xx > lb[FACE_OVAL, 0].min()) & (xx < lb[FACE_OVAL, 0].max())
    ref = (face > 0.6) & (hair < 0.2) & inside & (yy > lid) & (yy < lid + (lid - brow) * 3)
    if ref.sum() < 200:
        return None
    return np.median(cv2.cvtColor(img, cv2.COLOR_BGR2LAB)[ref], 0).astype(np.float32)


def _skin_color_alpha(img: np.ndarray) -> np.ndarray:
    """이마 피부와 a·b가 먼 정도 0~1 (밝은 머리는 피부와 밝기가 비슷해도 붉은기·노란기가 확연히 적음)

    기준은 이마에서 보이는 피부 (볼은 블러셔로 붉어 기준이면 맨 이마가 가닥으로 잡힘), 이마가 거의 안 보이면 볼
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    hair_p, face, _, _ = segment(img)
    ref = (forehead_zone(img) > 0.5) & (face > 0.6) & (hair_p < 0.2)
    skin = np.median(lab[ref], 0) if ref.sum() > 200 else _cheek_skin_lab(img)
    if skin is None:
        return np.zeros(img.shape[:2], np.float32)
    dab = np.hypot(lab[..., 1] - skin[1], lab[..., 2] - skin[2])
    hair = hair_p > 0.9
    d1 = max(SKIN_AB_MIN + 2, (float(np.median(dab[hair])) if hair.sum() > 100 else 15.0) * SKIN_AB_HAIR)
    return np.clip((dab - SKIN_AB_MIN) / (d1 - SKIN_AB_MIN), 0, 1).astype(np.float32)


def _brow_region(img: np.ndarray, polys: list[list[int]]) -> np.ndarray:
    """눈썹 윤곽을 넓힌 영역 0~1 (아래로 더 넓힘, 경계 부드럽게)"""
    h, w = img.shape[:2]
    lb = landmarks(img)
    gap = lb[UPPER_LIDS, 1].min() - lb[BROWS, 1].min()
    brows = np.zeros((h, w), np.uint8)
    for poly in polys:
        cv2.fillPoly(brows, [lb[poly].round().astype(np.int32)], 1)
    k = max(3, int(gap * BROW_GUARD)) | 1
    brows = cv2.dilate(brows, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    brows = np.maximum(brows, np.roll(brows, max(1, int(gap * BROW_GUARD_DOWN)), axis=0)).astype(np.float32)
    return cv2.GaussianBlur(brows, (0, 0), max(1.5, gap * 0.05))


def _visible_brows(img: np.ndarray) -> np.ndarray:
    """보이는 눈썹만 0~1: 눈썹 자리 픽셀이 머리색에 가까우면 제외 안 함 (사이드뱅·눈썹 가로지르는 가닥은 칠함)

    눈썹 색 = 눈썹 안쪽 진한 30%, 비교 대상은 눈썹~볼 피부 색 선분 (눈썹 가장자리는 둘이 섞인 색)
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32) * BROW_LAB_W
    skin = _cheek_skin_lab(img)
    hair_px = (segment(img)[0] > 0.9) & (forehead_zone(img) < 0.05)
    if skin is None or hair_px.sum() < 100:
        return _brow_region(img, BROW_POLYS)
    skin = skin * BROW_LAB_W
    hair = np.median(lab[hair_px], 0)
    lb = landmarks(img)
    d_hair = np.linalg.norm(lab - hair, axis=-1)
    out = np.zeros(img.shape[:2], np.float32)
    for poly in BROW_POLYS:
        core = np.zeros(img.shape[:2], np.uint8)
        cv2.fillPoly(core, [lb[poly].round().astype(np.int32)], 1)
        px = lab[core > 0]
        if len(px) < 20:
            continue
        brow = np.median(px[px[:, 0] <= np.percentile(px[:, 0], 30)], 0)
        if np.linalg.norm(brow - hair) < BROW_COVERED:
            continue  # 머리가 덮음
        seg = skin - brow
        t = np.clip(((lab - brow) @ seg) / max(float(seg @ seg), 1e-3), 0, 1)[..., None]
        d_brow = np.linalg.norm(lab - (brow + t * seg), axis=-1)
        hairlike = np.clip((d_brow - d_hair) / BROW_SOFT + 0.5, 0, 1).astype(np.float32)
        # 픽셀마다 판정이 오락가락해 눈썹 둘레가 지글지글 → 원본 엣지 따라 다듬고 확실히 머리일 때만
        hairlike = np.clip(_guided_filter(img, hairlike, max(2, round(img.shape[1] * 0.004)), 1e-2), 0, 1)
        t = np.clip((hairlike - 0.55) / 0.3, 0, 1)
        hairlike = t * t * (3 - 2 * t)
        out = np.maximum(out, _brow_region(img, [poly]) * (1 - hairlike))
    return out


def light_hair_mask(img: np.ndarray) -> np.ndarray:
    """밝은 베이스 마스크: hair_mask_fine + 이마 구간에서 피부와 색이 먼 가닥 추가, 보이는 눈썹 제외 (uint8)

    분할 모델이 펄 앞머리 가닥 일부를 놓쳐 염색 때 하얀 줄로 남음 (펄은 피부와 밝기는 비슷하지만 색이 확연히 다름)
    더하기만 해서 원래 칠하던 곳은 그대로, 눈썹(보이는 것만)은 더한 가닥에서 제외
    """
    fine = hair_mask_fine(img).astype(np.float32) / 255
    z = forehead_zone(img)
    r = max(3, round(img.shape[1] * 0.006))  # 앞머리 가닥이 얇아 반경 작게 (폭 658px에서 4px)
    alpha = np.clip(_guided_filter(img, _skin_color_alpha(img), r, 1e-3), 0, 1)
    # 눈썹 빼기는 새로 더한 가닥에만 (분할 마스크까지 지우면 눈썹 꼬리를 덮은 머리가 군데군데 지워져 얼룩)
    add = alpha * z * (1 - _visible_brows(img))
    # 놓친 가닥은 가늘고, 잘못 잡힌 피부는 넓은 덩어리 → 가닥보다 굵은 열림 연산에 남는 덩어리는 뺌
    extra = np.clip(add - fine, 0, 1).astype(np.float32)
    lb = landmarks(img)
    kw = max(3, int((lb[UPPER_LIDS, 1].min() - lb[BROWS, 1].min()) * LIGHT_ADD_WIDTH)) | 1
    blob = cv2.GaussianBlur(cv2.morphologyEx(extra, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kw, kw))), (0, 0), 2)
    extra = np.clip(extra - blob * 1.5, 0, 1)
    add = fine + extra
    # 더할 양이 이마 구간의 이 비율을 넘으면 피부를 가닥으로 잘못 본 것 → 더하지 않음 (덩어리로 칠하느니 안 칠함)
    if extra.sum() > LIGHT_ADD_MAX * max(float(z.sum()), 1):
        return (fine * 255).astype(np.uint8)
    m = np.maximum(fine, add)
    return (np.clip(m, 0, 1) * 255).astype(np.uint8)


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


# 머리 가운데 맞춤 이동 한계 (얼굴 폭 대비, 넘으면 원래 머리가 한쪽으로 쏠린 사진으로 보고 한계까지만)
CENTER_MAX = 0.06
# 사진 좌우 끝에서 이동을 0으로 되돌리는 폭 (이미지 폭 대비, 끝 픽셀을 늘리면 줄무늬)
CENTER_EDGE = 0.12


def _center_hair(gen: np.ndarray, old_hair: np.ndarray, lb: np.ndarray, brow: float, lid: float) -> np.ndarray:
    """AI 머리를 원본 머리(두상) 가운데에 맞춰 좌우 이동

    눈·눈썹으로 맞춰도 AI가 두상·가르마를 얼굴보다 한쪽으로 치우쳐 그림 (실루엣 가운데 약 12px 차이)
    정수리~눈썹 높이에서 원본·AI 머리 실루엣 가운데 차이의 중앙값만큼 눈썹 위만, 사진 좌우 끝은 0으로 되돌림
    """
    h, w = gen.shape[:2]
    fw = float(np.linalg.norm(lb[454] - lb[234]))
    new = segment(gen)[0] > 0.5
    old = old_hair > 0.5
    gap = lid - brow
    diffs = []
    for y in range(max(0, int(lb[10, 1] - gap * 3)), int(brow), 4):
        xo, xn = np.flatnonzero(old[y]), np.flatnonzero(new[y])
        if len(xo) and len(xn) and xo[-1] - xo[0] > fw * 0.6 and xn[-1] - xn[0] > fw * 0.6:
            diffs.append((xo[0] + xo[-1]) / 2 - (xn[0] + xn[-1]) / 2)
    if len(diffs) < 5:
        return gen
    dx = float(np.clip(np.median(diffs), -fw * CENTER_MAX, fw * CENTER_MAX))
    if abs(dx) < 2:
        return gen
    x = np.arange(w, dtype=np.float32)
    edge = w * CENTER_EDGE
    fade = np.clip(np.minimum(x, w - 1 - x) / edge, 0, 1)
    fade = fade * fade * (3 - 2 * fade)
    # 두상(눈썹 위)만 이동, 눈 높이부터는 0 (통째로 옮기면 볼 옆 머리·AI 볼 경계가 원본 볼 위로 밀려 얼굴이 깎여 보임)
    vy = np.clip((lid - np.arange(h, dtype=np.float32)) / max(1.0, lid - brow + gap), 0, 1)
    vy = vy * vy * (3 - 2 * vy)
    mx = (x[None, :] - dx * fade[None, :] * vy[:, None]).astype(np.float32)
    my = np.broadcast_to(np.arange(h, dtype=np.float32)[:, None], (h, w)).copy()
    return cv2.remap(gen, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


# 이마 피부 밝기 맞춤 비율·어둡게는 이만큼(L)까지만 (원래 앞머리 그늘로 원본 이마가 어두운 경우)
# 0.85면 눈썹 위가 분홍빛으로 하얗게 떠 가닥 끝이 끊겨 보임, 0이면 곱슬 앞머리 사이 이마가 갈색으로 칙칙 → 0.25
FORE_RELIGHT, FORE_DARKEN_MAX = 0.25, 15


def _relight_forehead(base, gen, segs, inside, yy, brow_low, gap, top) -> np.ndarray:
    """AI 이마 피부(앞머리 사이)를 그 자리 원본 이마 밝기·색에 맞춤, 가닥은 그대로

    AI가 앞머리 그늘을 진하게 그려 이마가 원본보다 L 60쯤 어두움 → 원본 얼굴과 눈썹 높이에서 색 차이
    한 값으로 통째로 옮기면 번들거리는 곳 기준이라 눈썹 위가 하얀 띠로 뜸 → 피부 픽셀만 넓게 흐린 평균끼리 자리마다 비교
    """
    face, gen_skin, old_hair, new_hair = segs
    lab_b = cv2.cvtColor(base, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab = cv2.cvtColor(gen, cv2.COLOR_BGR2LAB).astype(np.float32)
    ov = ((face > 0.5) & (old_hair < 0.3)).astype(np.float32)
    sk = (np.clip((gen_skin - 0.3) / 0.4, 0, 1) * (new_hair < 0.3)).astype(np.float32)
    sig = max(3.0, gap * 0.6)
    bo, bs = cv2.GaussianBlur(ov, (0, 0), sig), cv2.GaussianBlur(sk, (0, 0), sig)
    lo = cv2.GaussianBlur(lab_b * ov[..., None], (0, 0), sig) / np.maximum(bo, 1e-3)[..., None]
    lg = cv2.GaussianBlur(lab * sk[..., None], (0, 0), sig) / np.maximum(bs, 1e-3)[..., None]
    # 원본 이마가 머리로 가려져 비교할 피부가 없는 곳은 안 바꿈
    conf = np.clip(bo / 0.3, 0, 1) * np.clip(bs / 0.2, 0, 1)
    diff = np.clip(lo - lg, -60, 60)
    diff[..., 0] = np.maximum(diff[..., 0], -FORE_DARKEN_MAX)
    # 위쪽은 원본 이마 윗선(10번)까지만 (가르마 두피까지 밝히면 정수리에 하얀 번들거림)
    region = np.clip((brow_low + gap * 0.3 - yy) / (gap * 0.6), 0, 1) * np.clip((yy - top) / (gap * 0.5), 0, 1) * inside
    wgt = cv2.GaussianBlur(sk, (0, 0), 1.5) * region * conf * FORE_RELIGHT
    return cv2.cvtColor(np.clip(lab + diff * wgt[..., None], 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def _match_region_tone(base, gen, segs, lb, inside, yy, brow_low) -> np.ndarray:
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


# 턱선 맞춤 범위 = 윤곽선에서 이미지 폭 비율 (밖의 옆머리·옷은 그대로), 변형량 흐림 폭 (삼각형 경계 꺾임 펴기)
CONTOUR_BAND, CONTOUR_BLUR = 0.06, 0.015


def _warp_contour(gen: np.ndarray, lb: np.ndarray, lid: float) -> np.ndarray:
    """gen 얼굴 윤곽(눈 아래)을 base 윤곽에 맞춰 조각별 변형 (AI가 좁힌 턱선 되돌림)

    눈 아래 윤곽점만 base 위치로, 이마 쪽 윤곽·눈코입·이미지 테두리는 고정, 사이는 삼각형별 affine
    변형량은 흐린 뒤 윤곽선 근처(CONTOUR_BAND)에만 적용
    """
    h, w = gen.shape[:2]
    lg = landmarks(gen)
    oval, fixed = np.array(FACE_OVAL), np.array(ANCHORS)
    src_oval = lg[oval]
    dst_oval = _align_lower_face_contour(src_oval, lb[oval], lid, w * 0.05)
    src = np.concatenate([src_oval, lg[fixed]])
    dst = np.concatenate([dst_oval, lg[fixed]])
    edge = [(x, y) for x in np.linspace(0, w - 1, 5) for y in np.linspace(0, h - 1, 5) if x in (0, w - 1) or y in (0, h - 1)]
    src = np.concatenate([src, np.float32(edge)])
    dst = np.clip(np.concatenate([dst, np.float32(edge)]), 0, [w - 1, h - 1]).astype(np.float32)

    # dst 기준 삼각분할 → 픽셀마다 dst→src affine으로 역매핑
    subdiv = cv2.Subdiv2D((0, 0, w, h))
    index = {}
    for i, p in enumerate(dst):
        key = (round(float(p[0]), 2), round(float(p[1]), 2))
        if key not in index:
            index[key] = i
            subdiv.insert((float(p[0]), float(p[1])))
    tri_img = np.zeros((h, w), np.int32)
    mats = [np.float32([[1, 0, 0], [0, 1, 0]])]
    for t in subdiv.getTriangleList():
        ids = [index.get((round(float(t[k]), 2), round(float(t[k + 1]), 2))) for k in (0, 2, 4)]
        if None in ids:
            continue
        mats.append(cv2.getAffineTransform(dst[ids], src[ids]).astype(np.float32))
        cv2.fillConvexPoly(tri_img, dst[ids].round().astype(np.int32), len(mats) - 1)
    a = np.stack(mats)[tri_img]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx = a[..., 0, 0] * xx + a[..., 0, 1] * yy + a[..., 0, 2] - xx
    dy = a[..., 1, 0] * xx + a[..., 1, 1] * yy + a[..., 1, 2] - yy
    # 삼각형 경계마다 턱선이 꺾여 각지고 울퉁불퉁 → 변형량을 흐림
    dx = cv2.GaussianBlur(dx, (0, 0), w * CONTOUR_BLUR)
    dy = cv2.GaussianBlur(dy, (0, 0), w * CONTOUR_BLUR)
    # 삼각형이 이미지 테두리까지 이어져 옆머리·옷까지 휘어짐 → 아래쪽 윤곽선 근처에만 적용
    line = np.zeros((h, w), np.uint8)
    low = src_oval[:, 1] > lid - (lid - lb[BROWS, 1].min())
    pts = dst_oval.round().astype(np.int32)
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        if low[i] and low[j]:
            cv2.line(line, tuple(int(v) for v in pts[i]), tuple(int(v) for v in pts[j]), 1, 2)
    t = np.clip(1 - cv2.distanceTransform(1 - line, cv2.DIST_L2, 5) / (w * CONTOUR_BAND), 0, 1)
    wt = t * t * (3 - 2 * t)
    # 턱 근처 머리카락까지 휘어 보임 → 머리 픽셀은 변형 안 함 (얼굴형은 피부만으로 맞춤)
    hair = cv2.GaussianBlur(np.clip((segment(gen)[0] - 0.2) / 0.4, 0, 1).astype(np.float32), (0, 0), 1.5)
    wt = wt * (1 - hair)
    return cv2.remap(gen, xx + dx * wt, yy + dy * wt, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _align_lower_face_contour(gen_oval: np.ndarray, base_oval: np.ndarray, lid: float, limit: float) -> np.ndarray:
    """눈 아래 얼굴 윤곽점만 base 위치로 이동 (랜드마크 오검출 변위 제한)"""
    dst = gen_oval.copy()
    lower = gen_oval[:, 1] > lid
    ids = np.flatnonzero(lower)
    dst[ids] += np.clip(base_oval[ids] - gen_oval[ids], -limit, limit)
    return dst




# 몸 정렬 허용 범위: 크기 ±10%, 가로·세로 크기 차이 5%, 회전·기울어짐 3° (AI가 몸을 몇 % 작게 그리는 정도만 보정)
BODY_MAX_SCALE, BODY_MAX_ANISO, BODY_MAX_DEG = 0.1, 0.05, 3.0


def _align_body(base: np.ndarray, gen: np.ndarray, lb: np.ndarray) -> np.ndarray:
    """턱 아래(몸·옷·배경)를 몸 기준으로 다시 정렬, 목 부근에서 얼굴 기준 정렬과 이어 붙임

    AI가 몸을 몇 % 작게·옆으로 그려 원래 긴 머리 자리(어깨·팔)를 gen으로 채우면 몸이 어긋남
    머리카락 뺀 턱 아래 영역으로 ECC affine, 실패하거나 변환이 크면 그대로
    옷 반복 무늬에 속아 기울어짐·회전이 큰 엉뚱한 해가 나옴 (몸이 비틀리고 가장자리 복사 줄무늬) → 크기·회전·기울어짐 모두 검사
    """
    h, w = base.shape[:2]
    chin = float(lb[152, 1])
    region = np.zeros((h, w), np.uint8)
    region[int(chin + h * 0.03):] = 1
    region[(segment(base)[0] > 0.2) | (segment(gen)[0] > 0.2)] = 0
    if region.sum() < h * w * 0.05:
        return gen
    gray = lambda img: cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32), (0, 0), 2)
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        _, warp = cv2.findTransformECC(
            gray(base), gray(gen), warp, cv2.MOTION_AFFINE,
            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), region, 5,
        )
    except cv2.error:
        return gen
    a = warp[:, :2]
    sx, sy = np.linalg.norm(a, axis=0)
    rot = np.degrees(np.arctan2(a[1, 0], a[0, 0]))
    shear = np.degrees(np.arcsin(np.clip(a[:, 0] @ a[:, 1] / (sx * sy), -1, 1)))
    if (abs(sx - 1) > BODY_MAX_SCALE or abs(sy - 1) > BODY_MAX_SCALE or abs(sx - sy) > BODY_MAX_ANISO
            or abs(rot) > BODY_MAX_DEG or abs(shear) > BODY_MAX_DEG or np.any(np.abs(warp[:, 2]) > w * 0.15)):
        return gen
    body = cv2.warpAffine(gen, warp, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)
    t = np.clip((np.arange(h, dtype=np.float32) - chin) / (h * 0.12), 0, 1)[:, None, None]
    return (gen * (1 - t) + body * t).astype(np.uint8)


def transplant_hair(base: np.ndarray, gen: np.ndarray) -> np.ndarray:
    """base 사진 위에 gen의 머리카락만 옮겨 붙임 (결과 크기 = base)

    gen → base 위치로 정렬 후, 새 머리 + 원래 머리가 있던 자리(얼굴 피부 제외) + 이마 + 턱 아래는 gen 사용
    눈 아래 얼굴·얼굴형은 base 픽셀 그대로
    """
    h, w = base.shape[:2]
    lb = landmarks(base)
    m, _ = cv2.estimateAffinePartial2D(landmarks(gen)[HAIR_ANCHORS], lb[HAIR_ANCHORS])
    if m is None:
        raise ValueError("합성 결과를 원본에 맞추지 못했습니다")
    aligned = cv2.warpAffine(gen, m, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
    brow, lid = lb[BROWS, 1].min(), lb[UPPER_LIDS, 1].min()
    old_hair, face, old_bg, body = segment(base)
    aligned = _center_hair(aligned, old_hair, lb, brow, lid)
    aligned = _warp_contour(aligned, lb, lid)
    aligned = _align_body(base, aligned, lb)

    new_hair, gen_skin, new_bg, gbody = segment(aligned)
    gap = lid - brow
    yy, xx = np.mgrid[0:h, 0:w]
    inside = (xx > lb[FACE_OVAL, 0].min()) & (xx < lb[FACE_OVAL, 0].max())
    aligned = _match_skin_tone(base, aligned, face, gen_skin, old_hair, new_hair, inside, yy, brow, lid)
    aligned = _match_background(base, aligned, old_bg, new_bg)

    # 원래 머리는 가는 가닥까지 지우도록 넓게, 얼굴 피부는 남김 (새 앞머리가 덮는 곳 제외)
    k = max(3, int(w * 0.035)) | 1
    old = cv2.dilate((old_hair > 0.12).astype(np.float32), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    keep_face = cv2.erode((face > 0.5).astype(np.float32), np.ones((5, 5), np.uint8))
    mask = np.maximum(np.clip((new_hair - 0.2) / 0.4, 0, 1), old * (1 - keep_face))
    # 피부 위 얇은 원래 머리 가닥은 분할 모델이 놓쳐 얼굴로 남음 (눈꼬리 옆 잘린 가닥) → 원래 머리 근처에서 base가 gen 피부보다 확연히 어두운 곳은 gen
    near = cv2.dilate((old_hair > 0.3).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k * 3 | 1, k * 3 | 1))) > 0
    dl = cv2.cvtColor(aligned, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32) - cv2.cvtColor(base, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32)
    strand = near & (gen_skin > 0.5) & (new_hair < 0.2)
    mask = np.maximum(mask, np.where(strand, np.clip((dl - 15) / 20, 0, 1), 0))

    # 숱 적은 앞머리는 반투명으로 잡혀 원본 이마가 비치고 가닥 끝이 잘림 → 눈썹 아랫선 바로 아래까지 gen 통째로
    # (눈썹도 gen, 톤은 위에서 맞춤), 그 아래 경계 구간은 앞머리를 더 낮은 기준으로 잡음
    # 윗눈꺼풀 바로 위까지 통째로 쓰면 gen 쌍꺼풀 선이 원본 쌍꺼풀 위에 겹쳐 두 겹으로 보임 → 눈두덩은 원본 피부
    # 둘 다 배경인 곳은 제외 (얼굴 폭 직사각형이 사진 위쪽 배경까지 덮어 띠가 생김)
    person = (old_bg < 0.5) | (new_bg < 0.5)
    brow_low = float(lb[[p for poly in BROW_POLYS for p in poly[5:]], 1].max()) + gap * 0.1
    mask = np.where(inside & person & (yy < brow_low), 1.0, mask)
    band = inside & (yy >= brow - gap * 0.15) & (yy < lid - gap * 0.2)
    mask = np.where(band, np.maximum(mask, np.clip((new_hair - 0.08) / 0.25, 0, 1)), mask)
    # 턱 아래(목·어깨·옷·배경)는 몸 기준으로 맞춘 gen 통째로, 얼굴 피부는 원본
    # (원래 긴 머리에 가려졌던 목·어깨를 gen으로 채우면 원본 피부와 톤·그늘이 달라 경계선이 보임)
    below = np.clip((yy - lb[152, 1]) / (h * 0.03), 0, 1)
    mask = np.maximum(mask, below * (1 - keep_face))
    # 원본 얼굴이 AI 얼굴보다 넓으면 볼 위로 흘러내린 AI 가닥이 원본 피부에 덮여 머리가 턱선 따라 휘어 보임
    # → AI 머리 근처, 눈코입 밖에서 AI·원본 색이 확연히 다르면 AI 가닥 (피부·윤곽은 원본 그대로)
    near_new = cv2.dilate((new_hair > 0.3).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k * 2 | 1, k * 2 | 1))) > 0
    inner = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(inner, cv2.convexHull(lb[FACE_CORE].round().astype(np.int32)), 1)
    inner = cv2.dilate(inner, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))) > 0
    dlab = np.linalg.norm(cv2.cvtColor(aligned, cv2.COLOR_BGR2LAB).astype(np.float32) - cv2.cvtColor(base, cv2.COLOR_BGR2LAB).astype(np.float32), axis=-1)
    # 눈두덩은 제외 (AI 쌍꺼풀 선이 색 차이로 가닥으로 잡혀 원본 쌍꺼풀 위에 두 겹)
    mask = np.maximum(mask, np.where(near_new & ~inner & (yy > lid + gap * 0.6), np.clip((dlab - 18) / 20, 0, 1), 0))
    # AI가 칸마다 눈썹을 연하게·다르게 그림 (밝은 칸은 회색으로 흐려짐) → 눈썹은 원본, AI 머리가 확실히 덮은 곳만 AI
    # 원래 머리가 덮던 눈썹은 원본에 없으니 AI 그대로
    browm = np.zeros((h, w), np.uint8)
    for poly in BROW_POLYS:
        cv2.fillPoly(browm, [lb[poly].round().astype(np.int32)], 1)
    kb = max(3, int(gap * BROW_GUARD)) | 1
    browm = cv2.dilate(browm, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kb, kb))).astype(np.float32)
    browm = cv2.GaussianBlur(browm, (0, 0), max(1.5, gap * 0.08))
    mask = mask * (1 - browm * (1 - np.clip((new_hair - 0.3) / 0.4, 0, 1)) * (old_hair < 0.3))
    aligned = _match_region_tone(base, aligned, (face, body, gen_skin, gbody, old_hair, new_hair), lb, inside, yy, brow_low)
    aligned = _relight_forehead(base, aligned, (face, gen_skin, old_hair, new_hair), inside, yy, brow_low, gap, float(lb[10, 1]))
    # 눈·눈코입 안쪽은 원본 고정, AI 머리가 확실히 덮은 곳만 AI
    # (원래 옆머리 지우는 범위·가닥 판정이 눈꼬리까지 닿아 AI 눈꼬리·쌍꺼풀이 섞여 눈이 깨져 보임)
    guard = np.zeros((h, w), np.uint8)
    for eye in EYES:
        cv2.fillConvexPoly(guard, cv2.convexHull(lb[eye].round().astype(np.int32)), 1)
    ke = max(3, int(gap * EYE_GUARD)) | 1
    guard = cv2.dilate(guard, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ke * 2 | 1, ke))) | inner.astype(np.uint8)
    guard = cv2.GaussianBlur(guard.astype(np.float32), (0, 0), max(2.0, gap * 0.1))
    mask = mask * (1 - guard * (1 - np.clip((new_hair - 0.5) / 0.3, 0, 1)))
    mask = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 2.5)[..., None]
    return (aligned * mask + base * (1 - mask)).astype(np.uint8)


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


def base_hair_mask(img: np.ndarray, ref_strands: np.ndarray | None = None) -> np.ndarray:
    """어두운·중간 베이스 마스크: 분할 마스크 + 이마 위 시스루 가닥 (uint8)

    중간 베이스는 피부색에 가까운 밝은 갈색 가닥을 자기 픽셀로 못 잡음
    → 가닥 위치가 거의 같은 어두운 베이스의 가닥(ref_strands)을 같이 사용
    """
    strands = see_through_strands(img)
    if ref_strands is not None:
        strands = np.maximum(strands, ref_strands)
    return np.maximum(hair_mask(img), (strands * 255).astype(np.uint8))


def see_through_strands(img: np.ndarray) -> np.ndarray:
    """이마 위 시스루 가닥 알파 (0~1, 어두운·중간 베이스용)

    분할 모델은 이마 위 1~2px 가닥을 놓쳐 염색이 안 됨 → 이마 구간만 자기 픽셀로 계산
    짙은 가닥은 주변 피부보다 확연히 어두움, 가닥보다 굵은 닫힘 연산으로 가닥을 지운 밝기를 피부 기준으로 사용
    (칸끼리는 앞머리 숱이 달라 서로 비교할 수 없음)
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


# 한 번에 그리는 칸 수 (어두운 갈색·중간 갈색·밝은 플래티넘), 칸이 좁아져 2K로 받음 (칸당 원본의 약 1.4배)
PANELS = 3
PANEL_SIZE = "2K"


def _panels(img: np.ndarray, n: int = PANELS) -> tuple[np.ndarray, str, tuple[int, int]]:
    """같은 사진 n장 나란히 + 출력 비율에 맞게 바깥쪽 패딩 → (입력, 비율, (위, 왼쪽) 패딩)

    여러 칸을 새로 그리게 하면 얼굴을 정면으로 돌려 구도가 바뀜 → 이미 나란히 놓인 사진들을 고치게 함
    """
    h, w = img.shape[:2]
    aspect = closest_aspect(w * n, h)
    ratio = ASPECT_RATIOS[aspect]
    ph, pw = max(h, round(w * n / ratio)), max(w * n, round(h * ratio))
    top, left = (ph - h) // 2, (pw - w * n) // 2
    grid = cv2.copyMakeBorder(np.hstack([img] * n), top, ph - h - top, left, pw - w * n - left, cv2.BORDER_REPLICATE)
    # 가장자리 복사 줄무늬를 AI가 따라 그려 정수리 위에 섞임 → 늘린 부분만 흐림
    pad = np.ones(grid.shape[:2], bool)
    pad[top:top + h, left:left + w * n] = False
    grid[pad] = cv2.GaussianBlur(grid, (0, 0), max(h, w) * 0.05)[pad]
    return grid, aspect, (top, left)


def _split(raw: np.ndarray, grid_shape: tuple, pad: tuple[int, int], size: tuple[int, int], n: int = PANELS) -> list[np.ndarray]:
    """여러 칸 결과를 입력 크기로 되돌려 왼쪽부터 칸별 사진으로"""
    (top, left), (h, w) = pad, size
    raw = cv2.resize(raw, (grid_shape[1], grid_shape[0]), interpolation=cv2.INTER_AREA)
    return [raw[top:top + h, left + w * i:left + w * (i + 1)] for i in range(n)]


# 앞머리 끝 쪽 염색 알파를 이만큼 낮춤 (진하게 칠하면 이마 위 가닥이 덩어리처럼 무거움)
# 밝은 베이스는 제외 (펄 베이스가 비쳐 이마 위에 밝은 가로 띠가 생김)
FRINGE_SOFT = 0.25


def soften_fringe(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """헤어라인 아래 이마 위 가닥만 마스크를 연하게 (위쪽 머리 덩어리는 그대로, uint8)"""
    lb = landmarks(img)
    gap = lb[UPPER_LIDS, 1].min() - lb[BROWS, 1].min()
    yy = np.mgrid[0:img.shape[0], 0:img.shape[1]][0]
    ramp = np.clip((yy - (lb[10, 1] - gap * 0.5)) / (gap * 0.8), 0, 1)
    return (mask * (1 - FRINGE_SOFT * forehead_zone(img) * ramp)).astype(np.uint8)


def compose_bases(orig: np.ndarray, dark_raw: np.ndarray, brown_raw: np.ndarray, light_raw: np.ndarray) -> dict[str, bytes]:
    """칸별 AI 결과 → 원본 위 합성·마스크 → 저장할 파일 (AI 재호출 없이 다시 만들 때도 사용)"""
    # 모든 베이스를 원본 위에 (밝은 쪽을 어두운 베이스 위에 붙이면 가장자리에 어두운 머리가 비침)
    mid = transplant_hair(orig, dark_raw)
    # 칸끼리 실루엣 맞춤은 안 함 (어두운 칸에만 있는 머리를 밝은 색으로 칠해 넣으면 외곽이 뿌옇게 빛나고 이마에 유령 가닥)
    brown = transplant_hair(orig, brown_raw)
    light = transplant_hair(orig, light_raw)
    mid_strands = see_through_strands(mid)
    masks = {"mid": soften_fringe(mid, base_hair_mask(mid)), "brown": soften_fringe(brown, base_hair_mask(brown, mid_strands)),
             "light": light_hair_mask(light)}
    y0, y1, x0, x1 = _valid_box(orig, [dark_raw, brown_raw, light_raw])
    crop = lambda img: np.ascontiguousarray(img[y0:y1, x0:x1])
    return {**_base_files("mid", crop(mid), crop(masks["mid"])), **_base_files("brown", crop(brown), crop(masks["brown"])),
            **_base_files("light", crop(light), crop(masks["light"]))}


# 자른 뒤 남길 여유 (정렬 보간으로 경계 1~2px가 흐림)
CROP_PAD = 2


def _valid_box(orig: np.ndarray, raws: list[np.ndarray]) -> tuple[int, int, int, int]:
    """세 칸 모두 AI 칸 안인 직사각형 (y0, y1, x0, x1)

    얼굴 정렬로 칸 밖이 된 가장자리는 늘린 픽셀이라 줄무늬, 거울·메우기도 티남 → 세 베이스 같은 크기로 잘라냄
    빈 픽셀이 가장 많은 변부터 한 줄씩 안쪽으로
    """
    h, w = orig.shape[:2]
    lb = landmarks(orig)
    valid = np.ones((h, w), bool)
    for raw in raws:
        m, _ = cv2.estimateAffinePartial2D(landmarks(raw)[HAIR_ANCHORS], lb[HAIR_ANCHORS])
        if m is not None:
            valid &= cv2.warpAffine(np.full(raw.shape[:2], 255, np.uint8), m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0) == 255
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
    """사진 + 스타일 → 어두운 갈색(mid)·중간 갈색(brown)·밝은 금발(light) 베이스 저장, 원래 머리색 반환

    Flash 1회로 세 칸을 같이 그림 (Lite 탈색은 뭉개지고 뿌리가 남음)
    색을 바꿀 때 베이스에서 멀수록 마스크 오차가 드러남 → 중간톤용 베이스를 따로 둠
    """
    settings = get_settings()
    orig = prepare_photo(decode_image(photo))  # 못 쓰는 사진은 AI 호출 전에 실패
    grid, aspect, pad = _panels(orig)

    ref = _style_ref(style)
    images = [encode_jpeg(grid)] + ([ref] if ref else [])
    # 1회만 생성 (재시도하면 2분 넘음), 칸끼리 머리 차이는 실루엣 고정 후처리로 맞춤
    raw = decode_image(edit_image(settings.studio_style_model, images, style_prompt(style, ref is not None), aspect, size=PANEL_SIZE), 4096)
    panels = _split(raw, grid.shape, pad, orig.shape[:2])
    # AI가 구도·각도를 바꿔 그리면 합성이 망가짐 → 엉망인 결과 대신 다시 시도 안내 (실패는 비회원 횟수에서 안 셈)
    issue = _generation_issue(orig, panels)
    if issue:
        logger.info("[스튜디오] 잘못 생성 (%s)", issue)
        if settings.studio_debug:  # 판정 기준 조정용
            _save_debug(asset_dir, {"orig": orig, **{f"bad_{k}": p for k, p in zip(("mid", "brown", "light"), panels)}})
        raise ValueError("합성이 사진과 맞지 않게 만들어졌어요. 정면을 바라본 다른 사진으로 다시 시도해 주세요")
    dark_raw, brown_raw, light_raw = panels
    _write(asset_dir, compose_bases(orig, dark_raw, brown_raw, light_raw))
    if settings.studio_debug:
        _save_debug(asset_dir, {"orig": orig, "mid_raw": dark_raw, "brown_raw": brown_raw, "light_raw": light_raw})
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
