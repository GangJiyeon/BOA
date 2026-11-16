import { api } from './client'
import type { CompletedReceipt } from './moisture'
import type { AnalysisMetricScore } from './cosmetics'

export type SkinAnalysis = {
  moisture_measurement?: CompletedReceipt | null
  id: number
  logic_version: string
  moisture_source: 'none' | 'manual' | 'sensor'
  scores: AnalysisMetricScore[]
}

export function analyzeSkinPhoto(file: File, moisture: number | null, signal?: AbortSignal, manualScale: 60 | 100 = 100) {
  const form = new FormData()
  form.append('file', file)
  form.append('moisture_source', moisture === null ? 'none' : 'manual')
  if (moisture !== null) form.append(manualScale === 60 ? 'manual_moisture_index' : 'moisture_score', String(moisture))
  // 현재 S3 없이 사진을 분석하는 경로로 통합 흐름을 확인한다.
  return api<SkinAnalysis>('/skin/analyses/debug', { method: 'POST', body: form, signal })
}

export const getSkinAnalysis = (id: number, signal?: AbortSignal) => api<SkinAnalysis>(`/skin/analyses/${id}`, { signal })

export type SkinColorSample = { lightness: number; a: number; b: number }

// 헤어색 추천에 필요한 톤 분석 응답 필드만 사용한다.
export type SkinToneSample = { undertone: string; confidence: string; raw: { L: number } }

export function measureSkinTone(file: File, signal?: AbortSignal) {
  const body = new FormData()
  body.append('file', file)
  return api<SkinToneSample>('/skin/tone', { method: 'POST', body, signal })
}
