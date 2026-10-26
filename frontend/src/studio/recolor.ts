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

function labToRgb(L: number, a: number, b: number, out: Uint8ClampedArray, o: number) {
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

export function renderColor(base: PreparedBase, color: HairColor, out: Uint8ClampedArray) {
  const t = { ...DEFAULT_TUNING, ...color }
  const [tL0, tA, tB] = rgbToLab(...hexToRgb(color.hex))
  const tL = tL0 + t.lOff
  // 어두운 목표색은 명암 폭을 줄이고 밝은 목표색은 조금 키움
  const kEff = t.tex * Math.min(1.25, Math.max(0.45, (tL + 10) / (base.meanL + 10)))
  const KNEE = 78, TOE = 6
  const tmp = new Uint8ClampedArray(3)
  const { src, L: Ls, A: As, B: Bs, mask, meanL, meanA, meanB } = base
  for (let i = 0, p = 0; i < mask.length; i++, p += 4) {
    const a = mask[i]
    let r = src[p], g = src[p + 1], b = src[p + 2]
    if (a >= 0.004) {
      let L = tL + (Ls[i] - meanL) * kEff
      // 100/0에서 딱 잘리지 않게 부드럽게 눌러줌
      if (L > KNEE) L = KNEE + (100 - KNEE) * (1 - Math.exp(-(L - KNEE) / (100 - KNEE)))
      else if (L < TOE) L = TOE * Math.exp((L - TOE) / TOE)
      // 아주 어둡거나 밝은 곳은 채도 낮춤
      const f = Math.sqrt(Math.sin(Math.PI * Math.min(0.98, Math.max(0.02, L / 100))))
      labToRgb(L, tA * t.chroma * f + (As[i] - meanA) * t.vari, tB * t.chroma * f + (Bs[i] - meanB) * t.vari, tmp, 0)
      r += (tmp[0] - r) * a; g += (tmp[1] - g) * a; b += (tmp[2] - b) * a
    }
    out[p] = r; out[p + 1] = g; out[p + 2] = b; out[p + 3] = 255
  }
}

export async function loadPixels(url: string, width?: number, height?: number, signal?: AbortSignal): Promise<ImageData> {
  const res = await fetch(url, { signal })
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
