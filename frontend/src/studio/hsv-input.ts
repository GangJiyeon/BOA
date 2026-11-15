// 색상 입력 변환만 담당. 염색 계산은 기존 LAB 렌더러를 사용한다.
import { hexToRgb, labToRgb, rgbToLab } from './recolor'
export type Hsv = { h: number; s: number; v: number }

export function hsvToHex({ h, s, v }: Hsv): string {
  const hue = ((h % 360) + 360) % 360 / 60
  const saturation = Math.max(0, Math.min(100, s)) / 100
  const value = Math.max(0, Math.min(100, v)) / 100
  const c = value * saturation, x = c * (1 - Math.abs(hue % 2 - 1)), m = value - c
  const rgb = hue < 1 ? [c, x, 0] : hue < 2 ? [x, c, 0] : hue < 3 ? [0, c, x] : hue < 4 ? [0, x, c] : hue < 5 ? [x, 0, c] : [c, 0, x]
  return '#' + rgb.map(channel => Math.round((channel + m) * 255).toString(16).padStart(2, '0')).join('')
}

export function hexToHsv(hex: string): Hsv {
  const n = parseInt(hex.slice(1), 16)
  const r = (n >> 16 & 255) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min
  const h = d === 0 ? 0 : max === r ? ((g - b) / d + 6) % 6 * 60 : max === g ? ((b - r) / d + 2) * 60 : ((r - g) / d + 4) * 60
  return { h, s: max ? d / max * 100 : 0, v: max * 100 }
}

// 머리카락으로 자연스럽게 칠해지는 범위 (LAB 기준, HSV는 같은 V라도 색마다 밝기가 달라 기준이 안 맞음)
// 너무 하얗거나 새까만 색, 형광색은 베이스 결이 깨져 부자연스러움
export const HAIR_MIN_L = 8
export const HAIR_MAX_L = 75
export const HAIR_MAX_CHROMA = 40

// 슬라이더 끝까지 밀어도 범위 안으로 살짝 당김 (색상은 유지)
export function clampHairColor(hex: string): string {
  const [L, a, b] = rgbToLab(...hexToRgb(hex))
  const chroma = Math.hypot(a, b)
  const k = chroma > HAIR_MAX_CHROMA ? HAIR_MAX_CHROMA / chroma : 1
  const out = new Uint8ClampedArray(3)
  labToRgb(Math.min(HAIR_MAX_L, Math.max(HAIR_MIN_L, L)), a * k, b * k, out, 0)
  return '#' + Array.from(out, v => v.toString(16).padStart(2, '0')).join('')
}
