import type { SkinColorSample, SkinToneSample } from '../api/skin'
import { PALETTE, type HairColor } from './palette'
import { hexToRgb, rgbToLab } from './recolor'

export type HairColorRecommendation = {
  color: HairColor
  label: string
}

type Shade = readonly [a: number, b: number]

// 어두운 자연색을 첫 후보로 유지하는 근거: https://doi.org/10.11459/kaogaku.24.1.13
// 웜/쿨 계열 선택은 살롱 가이드를 참고한 규칙이다. Lab 값은 BOA의 미리보기용 설계값이다.
// https://www.lorealprofessionnel.co.uk/hair-colour-advice/how-to-choose-a-hair-colour
// https://us.wella.professionalstore.com/en-US/blog/hair-color/copper-vs-red-how-to-create-the-best-formula
const shades: Record<'cool' | 'warm' | 'neutral', [Shade, Shade, Shade]> = {
  cool: [[5, 4], [1, 4], [22, -9]],
  warm: [[8, 11], [5, 13], [19, 24]],
  neutral: [[6, 7], [3, 7], [14, 3]],
}
const hasAccent = new Set(['레드', '핑크 · 퍼플 · 블루'])
const presets = PALETTE.flatMap(({ group, colors }) => colors.map(color => ({
  color, accent: hasAccent.has(group), lab: rgbToLab(...hexToRgb(color.hex)),
})))
const naturalColors = presets.filter(preset => !preset.accent)
const accentColors = presets.filter(preset => preset.accent)
const labels = ['어두운 기본색', '일상에서 쓰기 좋은 색', '포인트 색']

export function recommendHairColors(sample: SkinColorSample | SkinToneSample): {
  colors: HairColorRecommendation[]
  basis: string
} {
  const lightness = 'raw' in sample ? sample.raw?.L : sample.lightness
  if (!Number.isFinite(lightness) || lightness < 0 || lightness > 100) {
    throw new Error('사진에서 피부 밝기를 읽지 못했어요. 다시 시도해 주세요.')
  }

  const confidence = 'confidence' in sample ? sample.confidence : undefined
  const toneWeight = confidence === 'high' ? 1 : confidence === 'medium' ? 0.7 : 0
  const undertone = 'undertone' in sample ? sample.undertone : undefined
  const measuredTone = toneWeight > 0 ? undertone : undefined

  let candidates = shades.neutral
  let colorWeight = 1
  let basis = confidence === 'low'
    ? '피부톤 판정이 불확실해 기본 색 계열을 제안해요.'
    : '피부톤 판정 정보가 없어 기본 색 계열을 제안해요.'

  if (measuredTone === 'neutral') {
    candidates = [shades.neutral[0], shades.cool[1], shades.warm[2]]
    basis = '중립톤 판정에 맞춰 자연스러운 색과 포인트 색을 함께 제안해요.'
  } else if (measuredTone === 'warm' || measuredTone === 'cool') {
    candidates = shades[measuredTone]
    colorWeight = toneWeight
    basis = measuredTone === 'warm'
      ? '웜톤 판정에 맞춰 따뜻한 색 계열을 제안해요.'
      : '쿨톤 판정에 맞춰 차가운 색 계열을 제안해요.'
  }

  // 피부 명도는 둘째·셋째 후보만 제한된 범위에서 조정한다.
  const adjustment = Math.min(1, Math.max(0, (lightness - 35) / 40))
  const depths = [23, 30 + 12 * adjustment, 27 + 8 * adjustment]

  const used = new Set<string>()
  const colors = candidates.map(([a, b], index) => {
    const [neutralA, neutralB] = shades.neutral[index]
    const target = [depths[index], neutralA + (a - neutralA) * colorWeight, neutralB + (b - neutralB) * colorWeight]
    const pool = index === 2 ? accentColors : naturalColors
    let best: HairColor | undefined
    let bestDistance = Infinity
    for (const { color, lab } of pool) {
      if (used.has(color.hex)) continue
      const distance = lab.reduce((sum, component, axis) => sum + (component - target[axis]) ** 2, 0)
      if (distance < bestDistance) { best = color; bestDistance = distance }
    }
    if (!best) throw new Error('스튜디오 추천 색상을 고르지 못했어요.')
    used.add(best.hex)
    return { color: best, label: labels[index] }
  })
  return { colors, basis }
}
