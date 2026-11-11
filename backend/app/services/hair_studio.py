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
Do NOT change the face shape in any way: same jawline, same chin, same cheeks, same cheekbones, same face width, same temples, same forehead width, same ears and neck.
Do NOT slim, narrow, contour, V-line, reshape, beautify, retouch or smooth the face. Do NOT enlarge the eyes or change the nose, lips or chin length.
Where the original hair covered the cheeks, jaw or forehead, reveal the SAME person's real face edge continuing the existing contour at the exact same width - never a slimmer or sharper one.
Do NOT copy the face, face shape or jawline of any reference image."""

STYLE_PROMPT = FACE_LOCK + """

The FIRST image shows the SAME photo of one person three times, side by side (left, middle and right panels). Edit ALL THREE panels. Keep the face, facial features, skin, eyebrows, makeup, expression, pose, clothing and background exactly identical.
Change only the hair to {target}: {style}. Match cut, length, volume, parting and bangs.
Completely remove the original hair, including any hair behind the neck or on the shoulders. {length_rule}
CRITICAL - IDENTICAL HAIRCUT IN ALL PANELS: the three panels must have the exact same hair silhouette, pixel for pixel - same length (the ends stop at exactly the same height), same outline, same volume, same parting, same bangs, same strands. Only the hair COLOR differs between panels. Do not make any panel longer, shorter, fuller or flatter.
LEFT panel hair color: natural dark brown (like level 4 hair). MIDDLE panel hair color: medium natural brown (like level 7 hair, a soft milk-tea brown). RIGHT panel hair color: light ash platinum blonde, even from root to tip with no dark roots. All three panels must have clearly visible strand texture, natural shine and soft highlights. Keep the three-panel layout, the split positions, and each panel's own framing exactly as in the input.
Do not change the eyebrows.
CRITICAL: keep the exact head angle, head tilt, gaze direction, face size and face position of the FIRST image. Do NOT rotate the head to frontal.
Keep the exact same framing and zoom: same head size in the frame, same shoulder width, same body shape and clothing position. Do not crop, zoom or reframe. Do not change the person's body or gender presentation; only the hair changes.{ref_note} Photorealistic, same lighting as the original.
FINAL CHECK: the face outline, jaw and chin must overlay the FIRST image pixel-for-pixel. If in doubt, keep the original face exactly."""

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


def hair_mask_fine(img: np.ndarray) -> np.ndarray:
    """가닥 경계까지 따라가는 머리 마스크 (밝은 베이스용)

    저해상도 분할 마스크는 잔머리를 놓쳐, 밝은 베이스를 어둡게 칠하면 바깥 가닥이 플래티넘으로 남아 흰 테두리가 됨
    """
    hair, face, _, _ = segment(img)
    t = np.clip((_guided_filter(img, hair.astype(np.float32)) - 0.3) / 0.4, 0, 1)
    m = t * t * (3 - 2 * t) * (1 - np.clip((face - 0.4) / 0.3, 0, 1))  # 얼굴 피부 쪽은 자름
    # 가장자리가 덜 칠해지면 플래티넘이 남아 흰 테두리 (흰 배경에서 심함) → 한 칸 넓히고 반쯤 칠해지는 곳을 더 칠함
    m = np.sqrt(cv2.dilate(m.astype(np.float32), np.ones((3, 3), np.uint8)))
    # 너무 또렷하면 오려 붙인 느낌 → 살짝 흐림 (더 흐리면 흰 테두리가 다시 보임)
    m = cv2.GaussianBlur(m, (0, 0), 1.5 * img.shape[1] / 800)
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


def _warp_contour(gen: np.ndarray, lb: np.ndarray, lid: float) -> np.ndarray:
    """gen 얼굴 윤곽(눈 아래)을 base 윤곽에 맞춰 조각별 변형 (AI가 좁힌 턱선 되돌림)

    눈 아래 윤곽점만 base 위치로, 이마 쪽 윤곽·눈코입·이미지 테두리는 고정, 사이는 삼각형별 affine
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
    map_x = a[..., 0, 0] * xx + a[..., 0, 1] * yy + a[..., 0, 2]
    map_y = a[..., 1, 0] * xx + a[..., 1, 1] * yy + a[..., 1, 2]
    return cv2.remap(gen, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _align_lower_face_contour(gen_oval: np.ndarray, base_oval: np.ndarray, lid: float, limit: float) -> np.ndarray:
    """눈 아래 얼굴 윤곽점만 base 위치로 이동 (랜드마크 오검출 변위 제한)"""
    dst = gen_oval.copy()
    lower = gen_oval[:, 1] > lid
    ids = np.flatnonzero(lower)
    dst[ids] += np.clip(base_oval[ids] - gen_oval[ids], -limit, limit)
    return dst


def _align_body(base: np.ndarray, gen: np.ndarray, lb: np.ndarray) -> np.ndarray:
    """턱 아래(몸·옷·배경)를 몸 기준으로 다시 정렬, 목 부근에서 얼굴 기준 정렬과 이어 붙임

    AI가 몸을 몇 % 작게·옆으로 그려 원래 긴 머리 자리(어깨·팔)를 gen으로 채우면 몸이 어긋남
    머리카락 뺀 턱 아래 영역으로 ECC affine, 실패하거나 변환이 크면 그대로
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
    scale = np.linalg.norm(warp[:, :2], axis=0)
    if np.any(np.abs(scale - 1) > 0.2) or np.any(np.abs(warp[:, 2]) > w * 0.15):
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
    m, _ = cv2.estimateAffinePartial2D(landmarks(gen)[ANCHORS], lb[ANCHORS])
    if m is None:
        raise ValueError("합성 결과를 원본에 맞추지 못했습니다")
    aligned = cv2.warpAffine(gen, m, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
    brow, lid = lb[BROWS, 1].min(), lb[UPPER_LIDS, 1].min()
    aligned = _warp_contour(aligned, lb, lid)
    aligned = _align_body(base, aligned, lb)

    old_hair, face, old_bg, _ = segment(base)
    new_hair, gen_skin, new_bg, _ = segment(aligned)
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

    # 숱 적은 앞머리는 반투명으로 잡혀 원본 이마가 비치고 가닥 끝이 잘림 → 윗눈꺼풀 바로 위까지 gen 통째로
    # (눈썹도 gen, 톤은 위에서 맞춤), 그 아래 경계 구간은 앞머리를 더 낮은 기준으로 잡음
    # 둘 다 배경인 곳은 제외 (얼굴 폭 직사각형이 사진 위쪽 배경까지 덮어 띠가 생김)
    person = (old_bg < 0.5) | (new_bg < 0.5)
    mask = np.where(inside & person & (yy < lid - gap * 0.1), 1.0, mask)
    band = inside & (yy >= brow - gap * 0.15) & (yy < lid - gap * 0.2)
    mask = np.where(band, np.maximum(mask, np.clip((new_hair - 0.08) / 0.25, 0, 1)), mask)
    # 턱 아래(목·어깨·옷·배경)는 몸 기준으로 맞춘 gen 통째로, 얼굴 피부는 원본
    # (원래 긴 머리에 가려졌던 목·어깨를 gen으로 채우면 원본 피부와 톤·그늘이 달라 경계선이 보임)
    below = np.clip((yy - lb[152, 1]) / (h * 0.03), 0, 1)
    mask = np.maximum(mask, below * (1 - keep_face))
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


def _style_ref(style: HairStyleCatalog) -> bytes | None:
    """카탈로그 사진이 로컬 static에 있으면 참조 이미지로 사용"""
    if not style.image or not style.image.startswith("/static/"):
        return None
    path = Path(style.image.lstrip("/"))
    if not path.is_file():
        return None
    # 카탈로그 사진은 표에서 잘라 옆 칸 이름표가 섞여 있음 (F027에 "Flower perm" → 생머리가 곱슬로 생성)
    # 사람 밖 배경을 흰색으로 덮어 글자 제거
    img = decode_image(path.read_bytes())
    bg = cv2.GaussianBlur((segment(img)[2] > 0.5).astype(np.float32), (0, 0), 1)[..., None]
    return encode_jpeg((img * (1 - bg) + 255 * bg).astype(np.uint8))


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
            ref_note=" The SECOND image is only a hairstyle reference; ignore its pose, face, face shape, jawline and framing.",
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


def _base_files(name: str, img: np.ndarray) -> dict[str, bytes]:
    mask = hair_mask_fine(img) if name == "light" else hair_mask(img)
    return {f"{name}.jpg": encode_jpeg(img), f"{name}_mask.png": cv2.imencode(".png", mask)[1].tobytes()}


# 칸끼리 머리 겹침이 이보다 낮으면 한 번 더 생성 (그래도 낮으면 실루엣 고정 후처리로 맞춤)
PANEL_OVERLAP = 0.85
def hair_overlap(a: np.ndarray, b: np.ndarray) -> float:
    """두 사진 머리 영역 겹침 비율 (b는 a 크기로 맞춤)"""
    x = segment(a)[0] > 0.5
    y = segment(cv2.resize(b, (a.shape[1], a.shape[0])))[0] > 0.5
    return float((x & y).sum() / max(1, (x | y).sum()))


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


def lock_silhouette(dark: np.ndarray, light: np.ndarray) -> np.ndarray:
    """밝은 베이스 머리 실루엣을 어두운 베이스에 맞춤 (색을 바꿀 때 머리 길이가 달라 보이지 않게)

    어두운 쪽만 머리인 곳만 어두운 머리를 밝은 쪽 색 분포로 채우고 나머지는 밝은 쪽 그대로
    (가장자리에 어두운 베이스 픽셀을 섞으면 밝은 색 염색 때 검은 외곽선이 생김)
    """
    md = (hair_mask(dark).astype(np.float32) / 255)[..., None]
    ml = (hair_mask(light).astype(np.float32) / 255)[..., None]
    lab_d = cv2.cvtColor(dark, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab_l = cv2.cvtColor(light, cv2.COLOR_BGR2LAB).astype(np.float32)
    wd, wl = md[..., 0] > 0.8, ml[..., 0] > 0.8
    if wd.sum() < 500 or wl.sum() < 500:
        return light
    mu_d, sd_d = lab_d[wd].mean(0), lab_d[wd].std(0) + 1e-3
    mu_l, sd_l = lab_l[wl].mean(0), lab_l[wl].std(0) + 1e-3
    fill = cv2.cvtColor(np.clip((lab_d - mu_d) / sd_d * sd_l + mu_l, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)
    only_dark = np.clip(md - ml, 0, 1)
    return (only_dark * fill + (1 - only_dark) * light).astype(np.uint8)


def generate(photo: bytes, style: HairStyleCatalog, asset_dir: str) -> str | None:
    """사진 + 스타일 → 어두운 갈색(mid)·중간 갈색(brown)·밝은 금발(light) 베이스 저장, 원래 머리색 반환

    Flash 1회로 세 칸을 같이 그림 (Lite 탈색은 뭉개지고 뿌리가 남음)
    색을 바꿀 때 베이스에서 멀수록 마스크 오차가 드러남 → 중간톤용 베이스를 따로 둠
    """
    settings = get_settings()
    orig = decode_image(photo)
    landmarks(orig)  # 얼굴 없으면 AI 호출 전에 실패
    grid, aspect, pad = _panels(orig)

    ref = _style_ref(style)
    images = [encode_jpeg(grid)] + ([ref] if ref else [])
    for _ in range(2):
        raw = decode_image(
            edit_image(settings.studio_style_model, images, style_prompt(style, ref is not None), aspect, size=PANEL_SIZE), 4096
        )
        dark_raw, brown_raw, light_raw = _split(raw, grid.shape, pad, orig.shape[:2])
        if min(hair_overlap(dark_raw, brown_raw), hair_overlap(dark_raw, light_raw)) >= PANEL_OVERLAP:
            break
    # 모든 베이스를 원본 위에 (밝은 쪽을 어두운 베이스 위에 붙이면 가장자리에 어두운 머리가 비침)
    mid = transplant_hair(orig, dark_raw)
    brown = lock_silhouette(mid, transplant_hair(orig, brown_raw))
    light = lock_silhouette(mid, transplant_hair(orig, light_raw))

    _write(asset_dir, {**_base_files("mid", mid), **_base_files("brown", brown), **_base_files("light", light)})
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
