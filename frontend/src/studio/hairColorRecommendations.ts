import type { SkinColorSample, SkinToneSample } from '../api/skin'
import type { HairColor } from './palette'
import { hexToRgb, labToHex, rgbToLab } from './recolor'

export type HairColorRecommendation = {
  color: HairColor
  label: string
}

type Shade = { name: string; a: number; b: number; label: string }

// 어두운 자연색을 첫 후보로 유지하는 근거: https://doi.org/10.11459/kaogaku.24.1.13
// 웜/쿨 계열 선택은 살롱 가이드를 참고한 규칙이다. Lab 값은 BOA의 미리보기용 설계값이다.
// https://www.lorealprofessionnel.co.uk/hair-colour-advice/how-to-choose-a-hair-colour
// https://us.wella.professionalstore.com/en-US/blog/hair-color/copper-vs-red-how-to-create-the-best-formula
const shades = {
  cool: [
    { name: '딥 쿨 브라운', a: 5, b: 4, label: '붉은 기와 노란 기를 낮춘 어두운 브라운' },
    { name: '애쉬 브라운', a: 1, b: 4, label: '회색빛을 섞어 채도를 낮춘 브라운' },
    { name: '플럼 버건디', a: 22, b: -9, label: '자줏빛이 도는 포인트 색' },
  ],
  warm: [
    { name: '딥 체스트넛 브라운', a: 8, b: 11, label: '따뜻한 밤색이 도는 어두운 브라운' },
    { name: '베이지 브라운', a: 5, b: 13, label: '은은한 황금빛이 도는 밝은 브라운' },
    { name: '소프트 카퍼', a: 19, b: 24, label: '구릿빛이 도는 포인트 색' },
  ],
  neutral: [
    { name: '딥 뉴트럴 브라운', a: 6, b: 7, label: '웜·쿨 어느 쪽에도 크게 치우치지 않는 어두운 브라운' },
    { name: '토프 브라운', a: 3, b: 7, label: '회갈색이 도는 저채도 브라운' },
    { name: '로즈 브라운', a: 14, b: 3, label: '장밋빛이 은은하게 도는 포인트 색' },
  ],
} satisfies Record<string, Shade[]>

function makeColor(shade: Shade, lightness: number, neutral: Shade, weight: number): HairColor {
  const hex = labToHex(
    lightness,
    neutral.a + (shade.a - neutral.a) * weight,
    neutral.b + (shade.b - neutral.b) * weight,
  )
  const [displayLightness] = rgbToLab(...hexToRgb(hex))
  return { name: shade.name, hex, base: displayLightness < 30 ? 'mid' : displayLightness < 52 ? 'brown' : 'light' }
}

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
    basis = '중립톤으로 판정되어 차가운 색과 따뜻한 색을 함께 제안해요.'
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

  const colors = candidates.map((shade, index) => ({
    color: makeColor(shade, depths[index], shades.neutral[index], colorWeight),
    label: shade.label,
  }))
  return { colors, basis }
}
