"""속눈썹 원본 PNG(한쪽 눈, 위·아래 같이 그린 것) → 위·아래 속눈썹 좌우 크롭·미리보기·뿌리선 (원본은 그대로)

1. 가장 큰 덩어리 = 위 속눈썹, 나머지 큰 덩어리 = 아래 속눈썹
   아래 속눈썹은 위아래로 뒤집어 위 속눈썹과 같은 모양(뿌리 아래, 털 위)으로 저장 → 그릴 때 다시 뒤집음
2. 기울어진 에셋은 위 속눈썹 덩어리의 주축이 수평이 되게 돌림 (아래 속눈썹이 아래로 오게)
3. 눈꼬리 쪽 = 털이 더 긴 쪽, 사진 왼쪽 눈용(눈꼬리가 왼쪽)과 오른쪽 눈용(좌우 반전)을 만듦
4. 뿌리선: 열마다 가장 아래 픽셀에 2차 곡선을 맞춤 (들쭉날쭉하면 띠가 어긋나 털이 끊겨 보임)
"""
from pathlib import Path
import hashlib
import json

import cv2
import numpy as np

root = Path(__file__).resolve().parents[1]
src_dir, out = root / 'static/makeup/lashes-src', root / 'static/makeup/lashes'
out.mkdir(parents=True, exist_ok=True)
LABELS = {'01_lash_overlay': '롱 꼬리', '02_lash_overlay': '가닥', '03_lash_overlay': '풍성',
          '05_lash_overlay': '내추럴', '06_lash_overlay': '뭉침'}
SAMPLES = 48
# 뿌리 높이: 열 알파의 아래쪽 이 비율 지점
ROOT_Q = 0.15
# 촘촘한 구간: 뿌리 띠(털 높이 비율) 알파가 중앙값의 이 비율 이상인 열
ROOT_BAND, SPAN_DENSITY = 0.15, 0.35
# 뿌리선 다항식 차수: 기본 2차, 1번은 가운데 평평·눈꼬리 급경사라 3차 (3차 이상을 다 쓰면 2·3번은 눈꼬리 긴 털 끝을 뿌리로 잡음)
DEG = {'01_lash_overlay': 3}
# 에셋별 붙이는 보정 (렌더러로 전달): skip = 눈머리 쪽을 더 비워 눈꼬리 쪽으로 옮김, size = 털 길이 배율
# inner: 시작점 털 길이 배율 (기본 .5, 뭉침은 앞도 조금 길게)
FIT = {'03_lash_overlay': {'size': .8}, '05_lash_overlay': {'skip': .1}, '06_lash_overlay': {'inner': .75}}
# 눈꼬리 쪽 구간을 원본 끝까지 (뭉침: 눈꼬리 끝 가는 털 몇 가닥이 눈 밖으로 빠지면 끝이 비어 보임)
FULL_OUTER = {'06_lash_overlay'}
# 눈꼬리가 원본 왼쪽인지 (원본 보고 지정, 털 길이로 자동 판단하면 1·2·5번이 반대로 잡힘), 없으면 자동
OUTER_LEFT = {'01_lash_overlay': False, '02_lash_overlay': False, '03_lash_overlay': True, '05_lash_overlay': False, '06_lash_overlay': True}


def split(img):
    """위 속눈썹(가장 큰 덩어리)·아래 속눈썹(나머지 큰 덩어리) 이미지와 각 중심"""
    a = (img[:, :, 3] > 40).astype(np.uint8)
    grown = cv2.dilate(a, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
    n, lab, st, cen = cv2.connectedComponentsWithStats(grown)
    order = sorted(range(1, n), key=lambda i: -st[i, cv2.CC_STAT_AREA])
    keep = lab == order[0]
    lower_ids = [i for i in order[1:] if st[i, cv2.CC_STAT_AREA] > 2000]
    upper, lower = img.copy(), img.copy()
    upper[~keep, 3] = 0
    lower[~np.isin(lab, lower_ids), 3] = 0
    return upper, (lower if lower_ids else None), (np.mean([cen[i] for i in lower_ids], 0) if lower_ids else None)


def level(img, lower_center, others=()):
    """위 속눈썹 주축이 수평이 되게 회전, 아래 속눈썹은 아래로 (others도 같은 변환)"""
    ys, xs = np.where(img[:, :, 3] > 40)
    pts = np.stack([xs, ys], 1).astype(np.float32)
    mean = pts.mean(0)
    vals, vecs = np.linalg.eigh(np.cov((pts - mean).T))
    major = vecs[:, np.argmax(vals)]
    angle = np.degrees(np.arctan2(major[1], major[0]))
    if angle > 90:
        angle -= 180
    if angle < -90:
        angle += 180
    if abs(angle) < 8:
        return img, list(others)
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D(tuple(mean), angle, 1)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    M[0, 2] += nw / 2 - mean[0]
    M[1, 2] += nh / 2 - mean[1]
    warp = lambda im: cv2.warpAffine(im, M, (nw, nh), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    rot, rest = warp(img), [warp(o) for o in others]
    if lower_center is not None:
        lc = M @ np.array([*lower_center, 1])
        if lc[1] < nh / 2:  # 아래 속눈썹이 위로 갔으면 뒤집음
            rot, rest = cv2.rotate(rot, cv2.ROTATE_180), [cv2.rotate(o, cv2.ROTATE_180) for o in rest]
    return rot, rest


def crop(img):
    ys, xs = np.where(img[:, :, 3] > 0)
    return img[max(0, ys.min() - 4):ys.max() + 5, max(0, xs.min() - 4):xs.max() + 5]


def outer_on_left(img):
    """눈꼬리 쪽은 털이 더 길게 위로 뻗음 → 왼쪽 1/4과 오른쪽 1/4의 털 높이 비교"""
    a = img[:, :, 3] > 40
    h, w = a.shape
    def reach(part):
        rows = np.where(part.any(1))[0]
        return (rows.max() - rows.min()) if len(rows) else 0
    return reach(a[:, :w // 4]) > reach(a[:, -w // 4:])


def roots(crop_img, deg=2):
    """뿌리선: 열마다 가장 아래 픽셀(아래 경계)에 2차 곡선을 맞춤, 크게 벗어난 점(처진 털·꼬리)은 빼고 다시 맞춤
    (뿌리 구간을 높이 비율로 미리 정하면 크게 휜 아치형(4·6번)은 가운데 뿌리가 빠져 곡선이 털 아래로 내려감)
    span: 곡선 가까이에 뿌리가 있는 열 범위 = 눈 길이에 맞출 구간"""
    ch, cw = crop_img.shape[:2]
    on = crop_img[:, :, 3] > 40
    cols = np.arange(cw)
    has = on.any(0)
    # 열마다 아래에서부터 알파 누적이 ROOT_Q에 닿는 높이 (맨 아래 픽셀은 처진 긴 털 끝이라 뿌리보다 낮게 잡힘, 1번 눈꼬리)
    alpha = crop_img[:, :, 3].astype(float) * on
    cum = np.cumsum(alpha[::-1], 0) / np.maximum(alpha.sum(0), 1)
    edge = np.where(has, ch - 1 - np.argmax(cum >= ROOT_Q, 0), np.nan).astype(float)
    edge = np.interp(cols, cols[has], edge[has])
    pts = cols[has]
    fit = np.polyfit(pts, edge[pts], deg)
    for _ in range(4):
        res = edge[pts] - np.polyval(fit, pts)
        mad = np.median(np.abs(res - np.median(res))) + 1
        keep = np.abs(res - np.median(res)) <= 2 * mad
        if keep.sum() < 3:
            break
        fit = np.polyfit(pts[keep], edge[pts][keep], deg)
    # span: 뿌리선 근처(털 높이의 15% 띠)에 알파가 충분히 모인 열 범위 = 털이 실제로 촘촘히 나는 구간
    # (곡선 가까이에 픽셀이 있는 열로 잡으면 눈꼬리 쪽 옆으로 누운 털 끝까지 들어가 촘촘한 부분이 눈꼬리 전에 끝남)
    fitted = np.polyval(fit, cols)
    band = max(3, ch * ROOT_BAND)
    rows_ = np.arange(ch)[:, None]
    near_root = (np.abs(rows_ - fitted[None, :]) <= band) & on
    density = np.convolve((crop_img[:, :, 3].astype(float) * near_root).sum(0), np.ones(9) / 9, 'same')
    dense = np.where(density >= np.median(density[density > 0]) * SPAN_DENSITY)[0] if (density > 0).any() else cols
    lo, hi = (int(dense.min()), int(dense.max())) if len(dense) else (0, cw - 1)
    span = [float(lo) / cw, float(hi) / cw]
    # 구간 밖(눈꼬리 긴 털)은 끝값 유지 (곡선을 늘리면 털이 눈꺼풀 아래로 묻힘)
    curve = np.polyval(fit, np.clip(cols, lo, hi))
    base = [round(float(np.interp(t * (cw - 1), cols, curve)) / ch, 4) for t in np.linspace(0, 1, SAMPLES)]
    return span, base


def lower_ok(lower, upper):
    """아래 속눈썹으로 쓸 만한지: 위 속눈썹 너비의 절반 이상·가로로 길고·열이 고르게 차 있어야 (조각만 떨어져 나온 것 제외)"""
    h, w = lower.shape[:2]
    filled = (lower[:, :, 3] > 40).any(0).mean()
    return w >= upper.shape[1] * .5 and w >= h * 2.5 and filled >= .5


catalog = []
for src in sorted(src_dir.glob('*.png')):
    image = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
    if image is None or image.ndim != 3 or image.shape[2] != 4:
        raise ValueError(f'알파 채널이 필요합니다: {src}')
    image[image[:, :, 3] < 12, 3] = 0
    upper, lower, lc = split(image)
    upper, rest = level(upper, lc, [lower] if lower is not None else [])
    upper = crop(upper)
    # OUTER_LEFT에 없는 에셋은 자동 판단
    flip = OUTER_LEFT.get(src.stem, None)
    outer_left = outer_on_left(upper) if flip is None else flip
    orient = lambda im: im if outer_left else cv2.flip(im, 1)
    left_img = orient(upper)
    version = hashlib.sha256(src.read_bytes()).hexdigest()[:10]

    def pair(img, kind, deg, full=False):
        res = []
        for side, im in (('left', img), ('right', cv2.flip(img, 1))):
            name = f'{src.stem}-{version}-{kind}{side}.png'
            cv2.imwrite(str(out / name), im)
            span, base = roots(im, deg)
            if full:  # 눈꼬리 쪽 끝(왼쪽 눈 기준 왼쪽, 반전본은 오른쪽)만 원본 끝까지
                span = [0.0, span[1]] if side == 'left' else [span[0], 1.0]
            res.append({'url': f'/static/makeup/lashes/{name}', 'width': im.shape[1], 'height': im.shape[0], 'span': span, 'base': base})
        return res
    sides = pair(left_img, '', DEG.get(src.stem, 2), src.stem in FULL_OUTER)
    # 아래 속눈썹: 위아래 뒤집어 뿌리를 아래로
    lower_img = orient(cv2.flip(crop(rest[0]), 0)) if rest else None
    lower_sides = pair(lower_img, 'lower-', 2) if lower_img is not None and lower_ok(lower_img, left_img) else None
    preview = np.zeros((80, 320, 4), np.uint8)
    for j, side in enumerate(sides):
        im = cv2.imread(str(out / Path(side['url']).name), cv2.IMREAD_UNCHANGED)
        scale = min(150 / im.shape[1], 70 / im.shape[0])
        small = cv2.resize(im, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        yy, xx = (80 - small.shape[0]) // 2, j * 160 + (160 - small.shape[1]) // 2
        preview[yy:yy + small.shape[0], xx:xx + small.shape[1]] = small
    cv2.imwrite(str(out / f'{src.stem}-{version}-preview.png'), preview)
    entry = {'id': src.stem, 'label': LABELS.get(src.stem, src.stem), 'preview': f'/static/makeup/lashes/{src.stem}-{version}-preview.png',
             'left': sides[0], 'right': sides[1]}
    if lower_sides:
        entry['lower'] = {'left': lower_sides[0], 'right': lower_sides[1]}
    if src.stem in FIT:
        entry['fit'] = FIT[src.stem]
    catalog.append(entry)
(out / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2))
print(f'{len(catalog)} lash pairs prepared ({sum("lower" in c for c in catalog)} with lower); source PNGs untouched')
