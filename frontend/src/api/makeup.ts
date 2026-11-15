import type { BrowRegion } from '../studio/makeup'
import { api } from './client'

export type FaceLandmarks = { points: [number, number][] }



// 코 모양·광대 폭 분석 (백엔드 nose_shape_analysis·cheek_analysis 결과)
export type FaceFeatures = { cheek_correction?: { relative_width: number; forehead_ratio: number; jaw_ratio: number; wide: number; narrow: number }; nose_correction?: { wide_wings: number; round_tip: number; upturned: number; drooping: number }; face_shape?: string; face_ratios?: { length_width: number; forehead_cheek: number; jaw_cheek: number; lower_face: number }; nose_tags: string[]; nose_ratios: { width_ratio: number; bulbous_ratio: number; symmetry_deviation: number; upturn: number }; cheek_width_ratio: number }
export type MakeupPreparation = FaceLandmarks & { brow_regions?: Partial<Record<'left' | 'right', BrowRegion>>; brow_base_png: string; width: number; height: number; features?: FaceFeatures | null }

// 피부톤 측정 (백엔드 /skin/tone, 사진·결과 저장 없음)
export type SkinTone = {
  brightness_level: 'bright' | 'medium' | 'deep'; brightness_label: string
  undertone: 'warm' | 'neutral' | 'cool'; undertone_label: string
  confidence: 'high' | 'low'
  palette: { tone_name: string; cushion: string; lip: string[]; blush: string[]; eye: string[]; point: string }
  notices: string[]
  raw?: { ita_deg?: number }
}
export function analyzeSkinTone(photo: Blob, signal?: AbortSignal) {
  const form=new FormData()
  form.append('file',photo,photo instanceof File?photo.name:'tone.jpg')
  return api<SkinTone>('/skin/tone',{method:'POST',body:form,signal})
}

// 브라우저에서 크기·방향을 정규화한 사진을 보냄. 전처리 결과는 메모리에서만 사용.
export function prepareMakeupPhoto(photo: Blob, signal?: AbortSignal) {
  const form=new FormData()
  form.append('photo',photo,'makeup.png')
  return api<MakeupPreparation>('/makeup/prepare',{method:'POST',body:form,signal})
}
