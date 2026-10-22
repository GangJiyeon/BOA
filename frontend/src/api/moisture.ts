import { api } from './client'
import type { Measurement } from '../moisture/protocol'
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
    method: 'POST', body: JSON.stringify({ analysis_id: analysisId, measurement }), signal,
  })
}
