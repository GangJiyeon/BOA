// 머리 영역만 Lab 공간에서 목표색으로 옮김 (헤어 컬러 테스터 render 이식)
// 마스크는 백엔드가 만든 PNG 사용, 브라우저에서 분할 모델 안 돌림
import { DEFAULT_TUNING, type HairColor } from './palette'

export type PreparedBase = {
  width: number
  height: number
  src: Uint8ClampedArray
  L: Float32Array
  A: Float32Array
  B: Float32Array
  mask: Float32Array
  meanL: number
  meanA: number
  meanB: number
}

const S2L = new Float32Array(256)
for (let i = 0; i < 256; i++) { const c = i / 255; S2L[i] = c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4) }
const L2S = new Uint8ClampedArray(4097)
for (let i = 0; i <= 4096; i++) { const v = i / 4096; L2S[i] = Math.round(255 * (v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(v, 1 / 2.4) - 0.055)) }
const fLab = (t: number) => t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116
const fInv = (t: number) => { const t3 = t * t * t; return t3 > 0.008856 ? t3 : (t - 16 / 116) / 7.787 }
const lin = (v: number) => L2S[Math.max(0, Math.min(4096, (v * 4096) | 0))]

export function rgbToLab(r: number, g: number, b: number): [number, number, number] {
  const R = S2L[r], G = S2L[g], B = S2L[b]
  const x = fLab((0.4124564 * R + 0.3575761 * G + 0.1804375 * B) / 0.95047)
  const y = fLab(0.2126729 * R + 0.7151522 * G + 0.072175 * B)
  const z = fLab((0.0193339 * R + 0.119192 * G + 0.9503041 * B) / 1.08883)
  return [116 * y - 16, 500 * (x - y), 200 * (y - z)]
}

export function labToRgb(L: number, a: number, b: number, out: Uint8ClampedArray, o: number) {
  const fy = (L + 16) / 116, fx = fy + a / 500, fz = fy - b / 200
  const X = 0.95047 * fInv(fx), Y = fInv(fy), Z = 1.08883 * fInv(fz)
  out[o] = lin(3.2404542 * X - 1.5371385 * Y - 0.4985314 * Z)
  out[o + 1] = lin(-0.969266 * X + 1.8760108 * Y + 0.041556 * Z)
  out[o + 2] = lin(0.0556434 * X - 0.2040259 * Y + 1.0572252 * Z)
}

export function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16)
  return [n >> 16 & 255, n >> 8 & 255, n & 255]
}

export function labToHex(lightness: number, a: number, b: number): string {
  const rgb = new Uint8ClampedArray(3)
  labToRgb(lightness, a, b, rgb, 0)
  return '#' + Array.from(rgb, channel => channel.toString(16).padStart(2, '0')).join('')
}

// image·mask 픽셀(RGBA)로 Lab 값과 머리 평균색 미리 계산
export function prepareBase(image: ImageData, maskPixels: Uint8ClampedArray): PreparedBase {
  const { width, height, data } = image
  const n = width * height
  const L = new Float32Array(n), A = new Float32Array(n), B = new Float32Array(n), mask = new Float32Array(n)
  let sw = 0, sl = 0, sa = 0, sb = 0
  for (let i = 0, p = 0; i < n; i++, p += 4) {
    const [l, a, b] = rgbToLab(data[p], data[p + 1], data[p + 2])
    L[i] = l; A[i] = a; B[i] = b
    const m = maskPixels[p] / 255
    mask[i] = m
    if (m > 0.6) { sw += m; sl += l * m; sa += a * m; sb += b * m }
  }
  return { width, height, src: data, L, A, B, mask, meanL: sw ? sl / sw : 50, meanA: sw ? sa / sw : 0, meanB: sw ? sb / sw : 0 }
}

// 이 밝기(L) 미만 목표색은 윤기 유지 방식 (흑발·블루블랙·소프트블랙·다크브라운·와인·버건디·딥퍼플·네이비)
const DARK_L = 25
// 머리 평균 밝기가 이보다 높으면 밝은 베이스
const LIGHT_BASE_L = 50

// 목표색 맞춤: 칠한 결과의 머리 평균 Lab이 목표색과 같아지게 밝기·색을 더 옮김 (채도 감쇠·밝기 압축·색역 잘림 보정)
// 반복 횟수, 표본 간격(픽셀), 보정 한계 (Lab): 1회·8px 간격이면 렌더 23→13ms(보정 없음 11ms), 32색 평균 오차 1.0·최대 3.3
const MATCH_ITERS = 1, MATCH_STEP = 8, MATCH_MAX = 30

export function renderColor(base: PreparedBase, color: HairColor, out: Uint8ClampedArray) {
  const t = { ...DEFAULT_TUNING, ...color }
  const [tL0, tA0, tB0] = rgbToLab(...hexToRgb(color.hex))
  const tL = tL0 + t.lOff, tA = tA0 * t.chroma, tB = tB0 * t.chroma
  // 어두운 목표색은 명암 폭을 줄이고 밝은 목표색은 조금 키움
  // 밝은 베이스에서 어둡게 내릴 때는 명암 그대로 (비율로 줄이면 결이 1/3로 줄어 떡져 보임)
  // 어두운 베이스는 원래 계산 유지 (어두운 색은 이 계산으로 잘 나옴)
  const lightBase = base.meanL > LIGHT_BASE_L
  const kEff = lightBase && tL < base.meanL ? 1 : t.tex * Math.min(1.25, Math.max(0.45, (tL + 10) / (base.meanL + 10)))
  // 아주 어두운 목표색은 비율로 깎으면 결·명암이 절반으로 줄어 칠한 덩어리처럼 보임 → 윤기(밝은 쪽)는 그대로, 그림자만 절반
  const dark = tL < DARK_L
  const KNEE = 78, TOE = 6
  const tmp = new Uint8ClampedArray(3)
  const { src, L: Ls, A: As, B: Bs, mask, meanL, meanA, meanB } = base
  // 픽셀 i의 칠한 색 → tmp (RGB), cL·cA·cB는 목표색 맞춤 보정
  const shade = (i: number, cL: number, cA: number, cB: number) => {
    const a = mask[i]
    // 밝은 베이스 가장자리는 배경과 섞여 어두운 걸 그대로 옮기면 검은 외곽선이 생김 → 마스크 0.5~0.95 구간에서 명암 차이를 줄임
    const e = lightBase ? Math.min(1, Math.max(0, (a - 0.5) / 0.45)) : 1
    const d = (Ls[i] - meanL) * e * e * (3 - 2 * e)
    let L = tL + cL + (dark ? (d > 0 ? d : d * 0.5) : d * kEff)
    // 100/0에서 딱 잘리지 않게 부드럽게 눌러줌
    if (L > KNEE) L = KNEE + (100 - KNEE) * (1 - Math.exp(-(L - KNEE) / (100 - KNEE)))
    else if (L < TOE) L = TOE * Math.exp((L - TOE) / TOE)
    // 아주 어둡거나 밝은 곳은 채도 낮춤
    const f = Math.sqrt(Math.sin(Math.PI * Math.min(0.98, Math.max(0.02, L / 100))))
    labToRgb(L, (tA + cA) * f + (As[i] - meanA) * t.vari, (tB + cB) * f + (Bs[i] - meanB) * t.vari, tmp, 0)
  }
  let cL = 0, cA = 0, cB = 0
  for (let it = 0; it < MATCH_ITERS; it++) {
    let n = 0, sl = 0, sa = 0, sb = 0
    for (let i = 0; i < mask.length; i += MATCH_STEP) {
      if (mask[i] <= 0.6) continue
      shade(i, cL, cA, cB)
      const [l, a, b] = rgbToLab(tmp[0], tmp[1], tmp[2])
      sl += l; sa += a; sb += b; n++
    }
    if (!n) break
    const clamp = (v: number) => Math.max(-MATCH_MAX, Math.min(MATCH_MAX, v))
    cL = clamp(cL + tL - sl / n); cA = clamp(cA + tA - sa / n); cB = clamp(cB + tB - sb / n)
  }
  for (let i = 0, p = 0; i < mask.length; i++, p += 4) {
    const a = mask[i]
    let r = src[p], g = src[p + 1], b = src[p + 2]
    if (a >= 0.004) {
      shade(i, cL, cA, cB)
      r += (tmp[0] - r) * a; g += (tmp[1] - g) * a; b += (tmp[2] - b) * a
    }
    out[p] = r; out[p + 1] = g; out[p + 2] = b; out[p + 3] = 255
  }
}

// 밝은 쪽 베이스를 어둡게 내리는 건 자연스럽고, 어두운 베이스를 밝히면 회색·떡짐 → 밝혀야 하는 거리에 가중치
const LIGHTEN_COST = 1.6
// 가장 밝은 베이스(light)는 앞머리 마스크가 가장 불안정 → 바로 아래 베이스(brown)를 이만큼(L)까지 밝혀도 되면 그쪽 사용
// (brown 평균 L 26에서 허니블론드 L 62까지 얼룩 없음, 베이지블론드 L 70부터 가닥 명암이 진해짐)
const LIGHT_AVOID_LIFT = 38

// 목표색 밝기에 가장 가까운 베이스 (사진마다 베이스 밝기가 달라 고정 경계 대신 실제 머리 평균 밝기로)
export function pickBase<K extends string>(bases: Partial<Record<K, PreparedBase>>, hex: string): K | null {
  const [tL] = rgbToLab(...hexToRgb(hex))
  const list = (Object.entries(bases) as [K, PreparedBase | undefined][])
    .filter((e): e is [K, PreparedBase] => Boolean(e[1])).sort((a, b) => a[1].meanL - b[1].meanL)
  let best: K | null = null, bestCost = Infinity
  for (const [k, b] of list) {
    const cost = b.meanL < tL ? (tL - b.meanL) * LIGHTEN_COST : b.meanL - tL
    if (cost < bestCost) { bestCost = cost; best = k }
  }
  if (list.length > 1 && best === list[list.length - 1][0]) {
    const [k, b] = list[list.length - 2]
    if (tL - b.meanL <= LIGHT_AVOID_LIFT) return k
  }
  return best
}

export async function loadPixels(url: string, width?: number, height?: number, signal?: AbortSignal, cache: RequestCache = 'default'): Promise<ImageData> {
  const res = await fetch(url, { signal, cache })
  if (!res.ok) throw new Error('합성 이미지를 불러오지 못했습니다.')
  const bitmap = await createImageBitmap(await res.blob())
  const w = width ?? bitmap.width, h = height ?? bitmap.height
  const canvas = document.createElement('canvas')
  canvas.width = w; canvas.height = h
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) throw new Error('이 브라우저에서는 색 변경을 사용할 수 없습니다.')
  ctx.drawImage(bitmap, 0, 0, w, h)
  bitmap.close()
  return ctx.getImageData(0, 0, w, h)
}
