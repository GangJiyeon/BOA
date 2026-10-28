import { scoreMaximum, levelDescription } from '../moisture/hydrationEstimate'
import { api } from './client'
import { rawSubmission, type Measurement } from '../moisture/protocol'
export type MoistureReceipt = {
  analysis_id: number | null
  measurement: Measurement
  server_received_at: string
  calibration_status: 'uncalibrated'
  persisted: false
  used_for_scoring: false
}
export function validateMoisture(measurement: Measurement, analysisId: number | null, signal?: AbortSignal) {
  return api<MoistureReceipt>('/skin/moisture/validate', {
    method: 'POST', body: JSON.stringify({ analysis_id: analysisId, measurement: rawSubmission(measurement) }), signal,
  })
}

import type { CompletedMeasurement, MeasurementSummary } from '../moisture/autoMeasurement'
export type CompletedReceipt = MeasurementSummary & {
  measurement_id: string; analysis_id: number; site: 'left_cheek' | 'skin'; measured_at: string;
  algorithm_version: 'cheek-auto-v1' | 'cheek-auto-v2' | 'skin-auto-v3' | 'skin-auto-v4' | 'skin-auto-v5' | 'skin-auto-v6' | 'skin-fixed-3s-v1'; baseline: number;
  persisted: true; used_for_scoring: boolean; recommendation_eligible?: boolean; signal_policy?: string;
  scoring_status?: string; calibrated_score?: number | null; score_category?: string | null; score_metric_name?: string | null;
  reference_value?: number | null; reference_unit?: string | null; calibration_version?: string | null;
  unit: 'relative_moisture_percent' | 'capacitance_contact_fraction_percent' | 'boa_moisture_score'
}
export function saveMoistureResult(result: CompletedMeasurement, analysisId: number, signal?: AbortSignal) {
  return api<CompletedReceipt>('/skin/moisture/results', {
    method: 'POST', body: JSON.stringify({ analysis_id: analysisId, result }), signal,
  })
}

export function applyMoistureScore(scores: import('./cosmetics').AnalysisMetricScore[], receipt: CompletedReceipt) {
  const score=receipt.normalized_score ?? receipt.calibrated_score
  if (!receipt.used_for_scoring || score == null || !receipt.score_category) return scores
  return [{ metric_code: 'moisture' as const, metric_name: receipt.score_metric_name ?? '수분',
    score, category_name: receipt.score_category, higher_is_better: true },
    ...scores.filter(s => s.metric_code !== 'moisture')]
}
export function moistureScoringMessage(receipt: CompletedReceipt) {
  if(receipt.normalized_score != null && receipt.used_for_scoring)return `수분 ${receipt.normalized_score}/${scoreMaximum(receipt)}${receipt.estimated_state_label?` · ${levelDescription(receipt)} 추정`:''} · 분석·추천 반영`
  if (receipt.used_for_scoring) return `보정 수분 점수 ${receipt.calibrated_score}/100 · 추천 입력에 반영`
  const messages: Record<string, string> = {
    resolution_limited: '미세 반응 · 출력 분해능에 비해 신호가 작아 추천 반영 보류',
    experimental_auxiliary: '상대 수분 지수 저장 · 추천 동점 후보의 보습 성분 보조 반영 가능',
    index_saturated: '상대 지수 상한 도달 · 추천 보조 반영 보류',
    calibration_missing: '피부 수분 보정 모델 없음 · 센서값은 추천에 미반영',
    calibration_unreviewed: '보정 모델 검토 전 · 센서값은 추천에 미반영',
    calibration_invalid: '보정 모델 파일 오류 · 센서값은 추천에 미반영',
    outside_calibration_range: '보정 실험 범위 밖 · 센서값은 추천에 미반영',
    calibration_incompatible: '측정 방식과 보정 모델 불일치 · 센서값은 추천에 미반영',
    score_definition_invalid: '수분 점수 구간 설정 오류 · 센서값은 추천에 미반영',
  }
  return messages[receipt.scoring_status ?? 'calibration_missing'] ?? '센서값은 추천에 미반영'
}
