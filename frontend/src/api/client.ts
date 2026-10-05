export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail: unknown = body?.detail
    const message = typeof detail === 'string' ? detail
      : Array.isArray(detail) ? detail.map((item) => `${item.loc?.join('.') ?? '입력'}: ${item.msg ?? '확인 필요'}`).join(' / ')
      : res.statusText
    throw new ApiError(res.status, message)
  }
  return res.json() as Promise<T>
}
