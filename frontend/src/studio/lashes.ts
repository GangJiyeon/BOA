import type { FaceLite, PreparedFace, Pt } from './makeup'

// 위 속눈썹 에셋: 좌우 크롭 + 뿌리선(base, 열별 높이 0~1) + 눈 길이에 맞출 구간(span, 가로 0~1)
// left = 사진 왼쪽 눈(눈꼬리가 왼쪽), right = 좌우 반전
type LashSide = { url: string; width: number; height: number; span: [number, number]; base: number[] }
// 에셋별 보정: skip = 눈머리 쪽을 더 비워 눈꼬리 쪽으로 옮김, size = 털 길이 배율, inner = 시작점 털 길이 배율
type LashFit = { skip?: number; size?: number; inner?: number }
// lower: 아래 속눈썹 (원본에 쓸 만한 아래 속눈썹이 있는 에셋만, 위아래 뒤집어 뿌리가 아래)
export type LashAsset = { id: string; label: string; preview: string; left: LashSide; right: LashSide; lower?: { left: LashSide; right: LashSide }; fit?: LashFit }
type LashPair = { left: ImageBitmap; right: ImageBitmap }
export type LashImages = Partial<Record<string, LashPair & { lower?: LashPair }>>
// style: 'none' 또는 에셋 id, lower: 아래 속눈썹 진하기 (0이면 없음)
export type LashSettings = { style: string; amount: number; lower: number }
// 아래 속눈썹은 있는 에셋이면 기본으로 옅게
// 2026-11-15 "아주 살짝 진하게": 위 .6→.66, 아래 .35→.38
export const DEFAULT_LASHES: LashSettings = { style: 'none', amount: 0.66, lower: 0.38 }

// 위·아래 눈꺼풀 윤곽 (사진 왼쪽 → 오른쪽 순)
const UPPER_LIDS = { left: [33, 246, 161, 160, 159, 158, 157, 173, 133], right: [362, 398, 384, 385, 386, 387, 388, 466, 263] }
const LOWER_LIDS = { left: [33, 7, 163, 144, 145, 153, 154, 155, 133], right: [362, 382, 381, 380, 374, 373, 390, 249, 263] }

// 크게 그린 에셋을 1/10 이하로 줄이면 털이 픽셀보다 얇아져 점선처럼 끊김
// → 목표 크기로 미리 부드럽게 줄이고 알파를 1-(1-a)^k로 진하게
const ALPHA_BOOST = 3
// 털 끝 흐림: 뿌리에서 멀어질수록 진하게 올린 알파를 이 비율까지 덜어냄 (끝까지 진하면 뭉툭한 인조 속눈썹처럼 보임)
const TIP_FADE = 0.45
// 뿌리 쪽(털 길이의 이 비율까지)은 알파를 더 진하게 → 뭉친 털 사이 가는 털이 이어져 뿌리 라인이 끊겨 보이지 않음
const ROOT_BAND = 0.15, ROOT_BOOST = 3
const scaledCache = new WeakMap<ImageBitmap, { key: string; canvas: HTMLCanvasElement }>()
// sharp: 사진 속 눈 크기 기준 0(작음)~1(큼), 작은 눈일수록 알파를 덜 진하게
function scaledLash(image: ImageBitmap, scale: number, color: readonly number[], base: readonly number[], sharp: number) {
  const w = Math.max(1, Math.round(image.width * scale)), h = Math.max(1, Math.round(image.height * scale)), key = `${w}x${h}:${color.join(',')}:${sharp.toFixed(2)}`
  const cached = scaledCache.get(image)
  if (cached?.key === key) return cached.canvas
  const canvas = document.createElement('canvas'); canvas.width = w; canvas.height = h
  const ctx = canvas.getContext('2d', { willReadFrequently: true })!
  ctx.imageSmoothingQuality = 'high'; ctx.drawImage(image, 0, 0, w, h)
  const pixels = ctx.getImageData(0, 0, w, h), data = pixels.data
  // 에셋은 무채색이라 분홍 피부 위에서 남색처럼 보임 → 사용자 속눈썹 색으로 칠함
  for (let x = 0; x < w; x++) {
    const f = x / Math.max(1, w - 1) * (base.length - 1), j = Math.floor(f)
    const root = (base[j] + (base[Math.min(j + 1, base.length - 1)] - base[j]) * (f - j)) * h
    for (let y = 0; y < h; y++) {
      const i = (y * w + x) * 4, tip = Math.min(1, Math.max(0, (root - y) / Math.max(1, root)))
      data[i] = color[0]; data[i + 1] = color[1]; data[i + 2] = color[2]
      // 작은 눈: 털이 1px보다 가늘어 진하게 올리면 털 대신 두꺼운 검은 띠가 됨 → 덜 올림
      const boost = (1 + (ALPHA_BOOST - 1) * (.3 + .7 * sharp)) * (1 + ROOT_BOOST * (.35 + .65 * sharp) * Math.max(0, 1 - tip / ROOT_BAND))
      data[i + 3] = 255 * (1 - Math.pow(1 - data[i + 3] / 255, boost)) * (1 - TIP_FADE * tip * tip)
    }
  }
  ctx.putImageData(pixels, 0, 0)
  scaledCache.set(image, { key, canvas })
  return canvas
}

// 눈꺼풀 곡선: 눈 축 좌표계(첫 점 원점, x는 눈꼬리~눈머리 방향)에서 x → y, 점 사이는 Catmull-Rom
// 꺾인 선 방향으로 띠를 돌리면 꺾이는 점에서 털이 끊기고, 눈 축 하나로만 돌리면 눈꼬리 긴 털이 라인 위에 누움
// → 부드러운 곡선의 기울기로 띠마다 돌림
function lidCurve(poly: Pt[]) {
  const [ox, oy] = poly[0], [ex, ey] = poly[poly.length - 1]
  const angle = Math.atan2(ey - oy, ex - ox), cos = Math.cos(angle), sin = Math.sin(angle)
  const pts = poly.map(([x, y]) => [(x - ox) * cos + (y - oy) * sin, -(x - ox) * sin + (y - oy) * cos] as const)
  const n = pts.length
  const yAt = (x: number) => {
    // 눈 밖(눈꼬리 연장)은 끝 높이 그대로 (눈꼬리 기울기로 늘리면 아래로 처짐)
    if (x <= pts[0][0]) return pts[0][1]
    if (x >= pts[n - 1][0]) return pts[n - 1][1]
    let i = 0
    while (i < n - 2 && x > pts[i + 1][0]) i++
    const p0 = pts[Math.max(0, i - 1)][1], p1 = pts[i][1], p2 = pts[i + 1][1], p3 = pts[Math.min(n - 1, i + 2)][1]
    const t = (x - pts[i][0]) / ((pts[i + 1][0] - pts[i][0]) || 1)
    return 0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t)
  }
  return { origin: poly[0], angle, length: pts[n - 1][0], yAt }
}

// 붙이는 방식 (눈 길이 비율): 눈머리 쪽 비우는 구간·이어서 서서히 진해지는 구간, 눈꼬리 밖으로 늘리는 길이·띄우는 높이,
// 털 길이 배율(눈머리 쪽 → 눈꼬리 쪽), 아래 속눈썹이면 위아래 뒤집어 아래 눈꺼풀에
// offset: 눈꺼풀 선에서 눈 바깥쪽으로 옮기는 거리 (음수면 눈 쪽으로 묻음)
// trim: 에셋 눈머리 쪽을 이만큼(구간 비율) 잘라내고 나머지만 붙임
type Placement = { skip: number; fade: number; extend: number; lift: number; offset: number; lengthInner: number; lengthOuter: number; flip: boolean; trim: number }
// 위: 눈 라인 끝까지 딱 맞게 (띄우거나 눈 밖으로 늘리면 떠 보임), 눈머리만 살짝 비움
// 뿌리는 속눈썹 라인 안쪽으로 살짝 묻음 (라인 윗경계에 두면 라인과 뿌리 사이에 밝은 피부 줄이 보여 떠 보이고 끊겨 보임)
// 눈머리 쪽: 에셋 앞 15%는 잘라내고(앞쪽 긴 털이 시작점에서 튀어나와 어색), 시작점의 털은 0.5배에서 점점 길게
// 눈꼬리 쪽: 띄우지 않고 눈 끝보다 4%만 더 (딱 끝에서 멈추면 마지막 털이 짧고 옆으로 누워 끝까지 안 간 것처럼 보이고, 끝 앞에서 멈추면 풍성이 가로로 눌림)
const UPPER: Placement = { skip: .06, fade: .08, extend: .04, lift: 0, offset: -.02, lengthInner: .4, lengthOuter: 1.05, flip: false, trim: .15 }
// 눈머리 쪽에서 눈꺼풀 선이 이 기울기보다 가파르게 눈물샘 쪽으로 내려가면 털을 지움 (고개가 기울면 이 구간이 길어져 앞이 진해짐)
const STEEP_START = .7, STEEP_END = 1.1
// 띠 회전: 눈꺼풀 기울기의 이 비율만 따라감, 한도(라디안)까지
// (기울기를 다 따라가면 눈꼬리 쪽 털이 아래·바깥으로 누워 뒤가 비어 보이고, 아예 안 돌리면 띠 사이가 벌어져 끊겨 보임)
const TILT_FOLLOW = .5, MAX_TILT = .3
// 아래: 눈꼬리 쪽 2/3에만, 점막 아래로 조금 내려 붙임 (에셋의 아래 털은 원본에서 아주 짧아 그대로면 2~3px라 안 보임 → 세로로 늘림)
const LOWER: Placement = { skip: .3, fade: .15, extend: 0, lift: 0, offset: .05, lengthInner: 2, lengthOuter: 3, flip: true, trim: 0 }
function drawSide(ctx: CanvasRenderingContext2D, image: ImageBitmap, meta: LashSide, poly: Pt[], color: readonly number[], innerFirst: boolean, place: Placement) {
  const lid = lidCurve(poly), L = lid.length
  // 에셋은 사진 왼쪽 눈 기준(눈꼬리가 왼쪽, 반전본은 오른쪽) → 눈머리 쪽 끝을 trim만큼 잘라낸 구간을 붙임
  const sw = (meta.span[1] - meta.span[0]) * image.width
  const x0 = meta.span[0] * image.width + (innerFirst ? sw * place.trim : 0), x1 = meta.span[1] * image.width - (innerFirst ? 0 : sw * place.trim)
  // 눈머리가 곡선 시작점이면(오른쪽 눈) 시작을 뒤로 밀고, 아니면 끝을 당김
  const used = L * (1 - place.skip + place.extend), start = innerFirst ? L * place.skip : -L * place.extend
  const scale = used / Math.max(1, x1 - x0)
  const sharp = eyeSharpness(L)
  const small = scaledLash(image, scale, color, meta.base, sharp), W = small.width, H = small.height
  const alpha = ctx.globalAlpha, sign = place.flip ? -1 : 1
  // 눈머리 0 → 눈꼬리 1
  const outerness = (x: number) => innerFirst ? x / L : 1 - x / L
  const curveAt = (x: number) => {
    const u = Math.max(0, outerness(x) - .5) / (.5 + place.extend)
    return sign * lid.yAt(x) - L * place.lift * Math.min(1, u) ** 2 - L * place.offset
  }
  const smoothstep = (t: number) => { const c = Math.min(1, Math.max(0, t)); return c * c * (3 - 2 * c) }
  // 눈머리에서 떨어진 거리 → 투명도, 눈머리 쪽 절반에서 선이 눈물샘 쪽으로 가파르게 내려가는 곳도 지움
  const fadeAt = (x: number) => {
    const base = smoothstep((outerness(x) - place.skip) / place.fade)
    if (outerness(x) >= .5) return base
    const drop = (curveAt(x + 1) - curveAt(x - 1)) / 2 * (innerFirst ? -1 : 1)
    return base * smoothstep((STEEP_END - drop) / (STEEP_END - STEEP_START))
  }
  // 털 길이: 시작점에서 lengthInner → 눈꼬리 lengthOuter (시작점 기준이라 눈머리를 많이 비운 사진도 앞 털이 짧게 시작)
  const lengthAt = (x: number) => {
    const u = Math.min(1, Math.max(0, (outerness(x) - place.skip) / (1 - place.skip)))
    return place.lengthInner + (place.lengthOuter - place.lengthInner) * Math.sqrt(u) * u
  }
  const baseAt = (x: number) => {
    const f = Math.min(1, Math.max(0, x / W)) * (meta.base.length - 1), i = Math.floor(f)
    return (meta.base[i] + (meta.base[Math.min(i + 1, meta.base.length - 1)] - meta.base[i]) * (f - i)) * H
  }
  ctx.save()
  ctx.translate(lid.origin[0], lid.origin[1]); ctx.rotate(lid.angle)
  // 아래 속눈썹: 에셋은 뿌리가 아래라 위아래 뒤집어 그리면 털이 아래로
  if (place.flip) ctx.scale(1, -1)
  // 1px 세로 띠마다 뿌리를 눈꺼풀 곡선 위 점에 맞추고 그 자리 기울기로 돌림
  // 잘라낸 눈머리 쪽 열은 안 그림
  const cutLo = innerFirst ? x0 * scale : -Infinity, cutHi = innerFirst ? Infinity : x1 * scale
  for (let sx = 0; sx < W; sx++) {
    if (sx + .5 < cutLo || sx + .5 > cutHi) continue
    const mid = sx + .5, x = start + mid - x0 * scale, fade = fadeAt(x)
    if (fade <= 0) continue
    ctx.save()
    ctx.globalAlpha = alpha * fade
    ctx.translate(x, curveAt(x)); ctx.rotate(Math.max(-MAX_TILT, Math.min(MAX_TILT, TILT_FOLLOW * Math.atan(curveAt(x + .5) - curveAt(x - .5)))))
    // 띠 사이 틈이 안 보이게 반 픽셀 겹침, 뿌리 기준으로 세로만 늘림
    const k = lengthAt(x)
    ctx.drawImage(small, sx, 0, Math.min(1.5, W - sx), H, -.5, -baseAt(mid) * k, Math.min(1.5, W - sx), H * k)
    ctx.restore()
  }
  ctx.restore()
}

// 사진 속 눈 길이(px) → 0~1: 28px 이하는 털이 뭉개지는 크기, 60px 이상은 털이 또렷한 크기
const SMALL_EYE = 28, CLEAR_EYE = 60
function eyeSharpness(length: number) {
  const t = Math.min(1, Math.max(0, (length - SMALL_EYE) / (CLEAR_EYE - SMALL_EYE)))
  return t * t * (3 - 2 * t)
}

// 사진 속 속눈썹 색: 윗눈꺼풀 바로 위 띠에서 가장 어두운 10% 픽셀 평균 (색감·밝기 그대로 → 갈색 속눈썹은 갈색으로)
// 밝기는 범위로만 묶음: 너무 밝으면 피부가 섞인 것이라 상한까지 낮추고, 너무 어두우면 검게 뭉쳐 하한까지 올림
const FALLBACK_LASH = [38, 30, 28]
const LASH_LUMA_MIN = 22, LASH_LUMA_MAX = 70
const colorCache = new WeakMap<PreparedFace, number[]>()
export function lashColor(face: PreparedFace) {
  const cached = colorCache.get(face)
  if (cached) return cached
  const { width: w, height: h, src, points } = face
  const samples: [number, number, number, number][] = []
  for (const ids of [UPPER_LIDS.left, UPPER_LIDS.right]) {
    const eyeW = Math.hypot(points[ids[ids.length - 1]][0] - points[ids[0]][0], points[ids[ids.length - 1]][1] - points[ids[0]][1])
    const reach = Math.max(2, eyeW * 0.06)
    // 양 끝(눈꼬리·눈머리)은 피부가 섞여 빼고 가운데 점만
    for (let k = 1; k < ids.length - 1; k++) {
      const [x, y] = points[ids[k]], [ax, ay] = points[ids[k - 1]], [bx, by] = points[ids[k + 1]]
      let nx = by - ay, ny = -(bx - ax)
      const len = Math.hypot(nx, ny) || 1
      nx /= len; ny /= len
      if (ny > 0) { nx = -nx; ny = -ny }
      for (let t = 0; t <= reach; t += 0.5) {
        const px = Math.round(x + nx * t), py = Math.round(y + ny * t)
        if (px < 0 || py < 0 || px >= w || py >= h) continue
        const o = (py * w + px) * 4, r = src[o], g = src[o + 1], b = src[o + 2]
        samples.push([r * .299 + g * .587 + b * .114, r, g, b])
      }
    }
  }
  let color = FALLBACK_LASH
  if (samples.length >= 10) {
    samples.sort((a, b) => a[0] - b[0])
    const dark = samples.slice(0, Math.max(5, Math.floor(samples.length * 0.1)))
    const mean = [1, 2, 3].map(c => dark.reduce((sum, s) => sum + s[c], 0) / dark.length)
    const luma = mean[0] * .299 + mean[1] * .587 + mean[2] * .114
    const target = Math.min(LASH_LUMA_MAX, Math.max(LASH_LUMA_MIN, luma))
    color = mean.map(v => Math.min(255, Math.round(v * target / Math.max(1, luma))))
  }
  colorCache.set(face, color)
  return color
}

export function drawLashes(ctx: CanvasRenderingContext2D, face: FaceLite, catalog: readonly LashAsset[], images: LashImages, settings: LashSettings) {
  if (settings.amount <= 0 || settings.style === 'none') return
  const asset = catalog.find(a => a.id === settings.style)
  const loaded = asset && images[asset.id]
  if (!asset || !loaded) return
  // 워커에서 미리 구한 색 (화면 쪽엔 사진 픽셀이 없음)
  const color = face.lashRgb ?? lashColor(face as PreparedFace)
  ctx.save()
  // 작은 눈은 털이 뭉개져 덜 진하게
  const eyeLen = Math.hypot(face.points[263][0] - face.points[362][0], face.points[263][1] - face.points[362][1])
  // 사용자 눈매에 맞춘 진하기는 기본 강도(슬라이더 값)에 이미 반영됨, 여기선 작은 눈 보정만
  const fade = .7 + .3 * eyeSharpness(eyeLen)
  ctx.globalAlpha = Math.min(1, settings.amount) * fade
  // 왼쪽 눈 윤곽은 눈꼬리(33)부터, 오른쪽 눈은 눈머리(362)부터
  // 눈머리는 사진에서 찾은 시작점(몽고주름에 덮인 곳 제외)부터, 에셋별 보정 반영
  const fit = asset.fit ?? {}
  for (const side of ['left', 'right'] as const) {
    // 흰자가 보이기 시작하는 곳보다 조금 앞에서부터 서서히 (딱 거기서 시작하면 첫 털이 늦게 진해짐)
    const skip = Math.max(UPPER.skip, (face.lashStart?.[side] ?? 0) - .03) + (fit.skip ?? 0)
    const size = fit.size ?? 1
    drawSide(ctx, loaded[side], asset[side], UPPER_LIDS[side].map(i => face.upperLid[i] ?? face.points[i]) as Pt[], color, side === 'right', { ...UPPER, skip, lengthInner: (fit.inner ?? UPPER.lengthInner) * size, lengthOuter: UPPER.lengthOuter * size })
  }
  if (settings.lower > 0 && asset.lower && loaded.lower) {
    ctx.globalAlpha = Math.min(1, settings.lower) * fade
    for (const side of ['left', 'right'] as const) drawSide(ctx, loaded.lower[side], asset.lower[side], LOWER_LIDS[side].map(i => face.points[i]) as Pt[], color, side === 'right', LOWER)
  }
  ctx.restore()
}

export async function loadLashImages(asset: LashAsset, signal: AbortSignal) {
  const load = async (url: string) => {
    const response = await fetch(url, { signal })
    if (!response.ok) throw new Error('속눈썹 이미지를 불러오지 못했습니다.')
    return createImageBitmap(await response.blob())
  }
  const [left, right, lowerLeft, lowerRight] = await Promise.all([load(asset.left.url), load(asset.right.url), ...(asset.lower ? [load(asset.lower.left.url), load(asset.lower.right.url)] : [])])
  return { left, right, ...(lowerLeft && lowerRight ? { lower: { left: lowerLeft, right: lowerRight } } : {}) }
}
