import { PALETTE, type HairColor } from './palette'
import { hexToRgb, rgbToLab } from './recolor'

export type HairColorRecommendation = {
  color: HairColor
  label: string
}

const presets = PALETTE.flatMap(group => group.colors).map(color => {
  const [lightness] = rgbToLab(...hexToRgb(color.hex))
  return { color, lightness: lightness + (color.lOff ?? 0) }
})

// 화면에서 비교할 약·중·강 명도 차이 (L*). 스타일 선택을 돕는 기준값이다.
const targetContrasts = [12, 28, 44]
const labels = ['부드러운 대비', '중간 대비', '선명한 대비']

export function recommendHairColors(skinLightness: number): HairColorRecommendation[] {
  const available = presets.map(({ color, lightness }) => ({
    color,
    contrast: Math.abs(lightness - skinLightness),
  }))
  const selected = targetContrasts.map(target => {
    available.sort((a, b) => Math.abs(a.contrast - target) - Math.abs(b.contrast - target))
    return available.shift()!
  })
  return selected.sort((a, b) => a.contrast - b.contrast)
    .map(({ color }, index) => ({ color, label: labels[index] }))
}
