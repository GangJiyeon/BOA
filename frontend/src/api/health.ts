import { api } from './client'

export type Health = {
  status: string
  db: boolean
  s3: boolean
}

export const getHealth = () => api<Health>('/health')
