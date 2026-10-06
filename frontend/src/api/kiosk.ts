import { api } from './client'
import type { GuestSession } from './account'
export type Kiosk = { kiosk_id: number; registered_at: string; session_active: boolean }
export const getKiosk = (signal?: AbortSignal) => api<Kiosk>('/kiosk/me', { signal })
export const registerKiosk = (adminCode: string, signal?: AbortSignal) => api<Omit<Kiosk, 'session_active'>>('/kiosk/register', { method: 'POST', body: JSON.stringify({ admin_code: adminCode }), signal })
export const startKiosk = (faceTermsId: number, signal?: AbortSignal) => api<GuestSession>('/kiosk/session', { method: 'POST', body: JSON.stringify({ face_terms_id: faceTermsId, age_confirmed: true }), signal })
export const endKiosk = (signal?: AbortSignal) => api<void>('/kiosk/session', { method: 'DELETE', signal })

export const revokeKiosk = (adminCode: string, kioskId: number, signal?: AbortSignal) => api<Omit<Kiosk, 'session_active'>>('/kiosk/revoke', { method: 'POST', body: JSON.stringify({ admin_code: adminCode, kiosk_id: kioskId }), signal })
