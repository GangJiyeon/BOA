import { api } from './client'

export type Health = {
  status: string
  db: boolean
}

export const getHealth = (signal?: AbortSignal) => api<Health>('/health', { signal })
