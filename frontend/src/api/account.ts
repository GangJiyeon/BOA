import { api } from './client'
import type { SkinAnalysis } from './skin'
export type Actor = { kind: 'anonymous' | 'guest' | 'member' | 'kiosk' }
export type Term = { id: number; type: string; version: string; required: boolean; effective_at: string }
export type GuestSession = { qr_token: string; expires_at: string }
export type Language = 'ko' | 'en' | 'zh' | 'ja'
export type Member = { email: string; language: Language; nationality: string | null; resides_in_korea: boolean | null; google_linked: boolean }
export type Quota = Record<'skin' | 'hair', { limit: number | null; used: number; remaining: number | null }>
export type QrResults = { expires_at: string; skin: SkinAnalysis[]; hair: Record<string, unknown>[] }
export const getActor = (signal?: AbortSignal) => api<Actor>('/actor', { signal })
export const getTerms = (signal?: AbortSignal) => api<Term[]>('/terms/current', { signal })
export const getQuota = (signal?: AbortSignal) => api<Quota>('/guest/quota', { signal })
export const startGuest = (faceTermsId: number, signal?: AbortSignal) => api<GuestSession>('/guest/session', {
  method: 'POST', body: JSON.stringify({ face_terms_id: faceTermsId, age_confirmed: true }), signal,
})
export const sendCode = (email: string, signal?: AbortSignal) => api<{ resend_seconds: number; dev_code: string | null }>('/auth/email/send', {
  method: 'POST', body: JSON.stringify({ email }), signal,
})
export const verifyCode = (email: string, code: string, signal?: AbortSignal) => api<{ signup_required: boolean; signup_token: string | null; language: Language | null }>('/auth/email/verify', {
  method: 'POST', body: JSON.stringify({ email, code }), signal,
})
export const signup = (body: { signup_token: string; language: Language; nationality: string; resides_in_korea: boolean; agreed_terms_ids: number[] }, signal?: AbortSignal) => api<{ user_id: number; language: Language }>('/auth/signup', {
  method: 'POST', body: JSON.stringify(body), signal,
})
export const getMember = (signal?: AbortSignal) => api<Member>('/me', { signal })
export const updateLanguage = (language: Language, signal?: AbortSignal) => api<Member>('/me', { method: 'PATCH', body: JSON.stringify({ language }), signal })
export const logout = (signal?: AbortSignal) => api<void>('/auth/logout', { method: 'POST', signal })
export const refreshLogin = (signal?: AbortSignal) => api<void>('/auth/refresh', { method: 'POST', signal })
export const getQrResults = (token: string, signal?: AbortSignal) => api<QrResults>(`/qr/${encodeURIComponent(token)}`, { signal })
export const claimQrResults = (token: string, signal?: AbortSignal) => api<{ skin_count: number }>(`/qr/${encodeURIComponent(token)}/claim`, { method: 'POST', signal })

export const termNames: Record<string, string> = { SERVICE: '서비스 이용', PRIVACY: '개인정보 수집·이용', AGE_14: '만 14세 이상', FACE_IMAGE: '얼굴 이미지 처리', PHOTO_STORAGE: '사진 보관', MARKETING: '마케팅 수신' }
