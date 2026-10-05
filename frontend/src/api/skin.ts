import { api } from './client'
import type { AnalysisMetricScore } from './cosmetics'

export type SkinAnalysis = {
  id: number
  logic_version: string
  moisture_source: 'none' | 'manual' | 'sensor'
  scores: AnalysisMetricScore[]
}

export function analyzeSkinPhoto(file: File, moisture: number | null, signal?: AbortSignal) {
  const form = new FormData()
  form.append('file', file)
  form.append('moisture_source', moisture === null ? 'none' : 'manual')
  if (moisture !== null) form.append('moisture_score', String(moisture))
  // 현재 S3 없이 사진을 분석하는 경로로 통합 흐름을 확인한다.
  return api<SkinAnalysis>('/skin/analyses/debug', { method: 'POST', body: form, signal })
}
