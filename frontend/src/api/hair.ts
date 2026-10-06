import { api } from './client'
export type Sex = 'male' | 'female' | 'unisex'
export type FaceAnalysis = { id: number; sex: Sex; face_shape: string; top2: string | null; confidence: number | null; source: string; ratios: Record<string, number> | null; updated_at: string }
export type HairStyle = { style_id: string; name: string; sex: Sex; length: string; texture: string; image: string | null }
export type HairResult = {
  run_id: number; face_analysis_id: number; created_at: string;
  preferred_length: string | null; preferred_texture: string | null;
  recommendations: { rank: number; style_id: string; name: string; score: number; note: string | null; image: string | null }[]
}
export const getHairStyles = (signal?: AbortSignal) => api<HairStyle[]>('/hair/styles', { signal })
export function analyzeFace(files: File[], sex: Sex, signal?: AbortSignal) {
  const form = new FormData()
  for (const file of files) form.append('photos', file)
  form.append('sex', sex)
  return api<FaceAnalysis>('/hair/face-analysis/photos', { method: 'POST', body: form, signal })
}
export const recommendHair = (faceId: number, length: string, texture: string, signal?: AbortSignal) => api<HairResult>('/hair/recommend', {
  method: 'POST', body: JSON.stringify({ face_analysis_id: faceId, preferred_length: length || null, preferred_texture: texture || null, top_n: 5 }), signal,
})
export const getHairResult = (id: number, signal?: AbortSignal) => api<HairResult>(`/hair/recommend/${id}`, { signal })
