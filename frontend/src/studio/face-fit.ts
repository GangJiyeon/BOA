// 얼굴 맞춤: 팀 분석 판정(얼굴형 face_shape·코 nose_correction·광대 cheek_correction)을 그대로 메이크업 배치 타입으로 옮김
import { faceShapeFromAnalysis, type FaceShape } from './makeup-looks'

export type NoseTech = 'straight' | 'box' | 'wing'
export type CheekType = 'wide' | 'narrow' | 'normal'
export type FaceFit = { face: FaceShape; nose: NoseTech; cheek: CheekType; tip: 'up' | 'down' | 'normal' }
export type FitInput = {
  face_shape?: string
  nose_correction?: { wide_wings: number; round_tip: number; upturned: number; drooping: number }
  cheek_correction?: { wide: number; narrow: number }
}

export function computeFit(input: FitInput | null | undefined): FaceFit | null {
  const face = faceShapeFromAnalysis(input?.face_shape)
  if (!input || !face) return null
  const n = input.nose_correction, c = input.cheek_correction
  // 코: 넓은 콧볼·둥근 코끝 판정 중 더 강한 쪽, 둘 다 아니면 곧은 콧대
  const nose: NoseTech = n && Math.max(n.wide_wings, n.round_tip) > 0 ? (n.wide_wings >= n.round_tip ? 'wing' : 'box') : 'straight'
  const cheek: CheekType = c?.wide ? 'wide' : c?.narrow ? 'narrow' : 'normal'
  const tip = n?.upturned ? 'up' : n?.drooping ? 'down' : 'normal'
  return { face, nose, cheek, tip }
}

const FACE_TEXT: Record<FaceShape, string> = {
  oval: '계란형 → 광대 아래 사선 블러셔, 이마·눈 밑·턱끝 하이라이트',
  round: '둥근형 → 광대 바깥에 높게 올린 블러셔, 이마·콧대·턱끝을 세로로 길게',
  square: '사각형 → 볼 중앙의 둥근 블러셔, 눈 둘레·턱끝 하이라이트',
  long: '긴형 → 눈 밑 가로 블러셔, 볼을 가로로 밝힘',
  heart: '역삼각·하트형 → 볼 중앙 가로 블러셔, 턱 양옆을 밝혀 아래를 채움',
  diamond: '다이아몬드형 → 광대 안쪽 블러셔, 이마 양옆·입꼬리 옆 하이라이트',
}
const NOSE_TEXT: Record<NoseTech, string> = {
  wing: '넓은 콧볼 → 콧볼을 감싸는 음영',
  box: '둥근 코끝 → 코끝을 상자처럼 감싸는 음영',
  straight: '코 → 눈썹 머리부터 이어지는 곧은 콧대',
}
const CHEEK_TEXT: Record<CheekType, string> = { wide: '넓은 광대 → 블러셔를 안쪽으로', narrow: '좁은 광대 → 블러셔·하이라이트를 바깥으로', normal: '' }
export function fitSummary(fit: FaceFit, face: FaceShape = fit.face) {
  return [FACE_TEXT[face], NOSE_TEXT[fit.nose], CHEEK_TEXT[fit.cheek]].filter(Boolean)
}
