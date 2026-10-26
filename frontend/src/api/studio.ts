import { api } from './client'

export type HairRenderBase = { image: string; mask: string }
export type HairRender = {
  id: number; style_id: string; status: 'pending' | 'done' | 'failed'; error: string | null; created_at: string
  light: HairRenderBase | null; mid: HairRenderBase | null
}

export function createHairRender(photo: File, styleId: string, runId: number | null, signal?: AbortSignal) {
  const form = new FormData()
  form.append('photo', photo)
  form.append('style_id', styleId)
  if (runId !== null) form.append('run_id', String(runId))
  return api<HairRender>('/studio/hair-renders', { method: 'POST', body: form, signal })
}
export const getHairRender = (id: number, signal?: AbortSignal) => api<HairRender>(`/studio/hair-renders/${id}`, { signal })
