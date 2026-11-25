export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function errorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const messages = detail.flatMap(item => {
      if (!item || typeof item !== 'object' || typeof item.msg !== 'string') return []
      const location = Array.isArray(item.loc) ? item.loc.join('.') : '입력'
      return [`${location}: ${item.msg}`]
    })
    if (messages.length) return messages.join(' / ')
  }
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string' && detail.message.trim()) return detail.message
  return fallback
}

export const SESSION_EXPIRED_EVENT = 'boa:session-expired'

let refreshPromise: Promise<void> | null = null
let refreshVersion = 0
let refreshError: unknown = null

async function request(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`/api${path}`, { credentials: 'same-origin', ...init })
  } catch (err) {
    if (init.signal?.aborted || (err instanceof Error && err.name === 'AbortError')) throw err
    throw new ApiError(0, '서버에 연결할 수 없습니다. 백엔드 실행과 네트워크를 확인해 주세요.')
  }
}

// 탭 간 갱신 공유: 리프레시 토큰은 쓸 때마다 교체돼서 두 탭이 동시에 갱신하면 늦은 쪽이 401 → 로그아웃
const REFRESH_LOCK = 'boa-auth-refresh'
const REFRESHED_AT_KEY = 'boa-auth-refreshed-at'
let lastRefreshedAt = 0

function refreshedAt(): number {
  try { return Math.max(lastRefreshedAt, Number(window.localStorage.getItem(REFRESHED_AT_KEY)) || 0) }
  catch { return lastRefreshedAt }
}

function markRefreshed() {
  lastRefreshedAt = Date.now()
  try { window.localStorage.setItem(REFRESHED_AT_KEY, String(lastRefreshedAt)) } catch { /* 저장 불가 환경은 탭 내부 값만 사용 */ }
}

// 갱신은 모든 탭 통틀어 한 번에 하나, 기다리는 동안 다른 탭이 갱신했으면 생략 (쿠키 공유라 새 토큰이 이미 있음)
async function refreshOnce(sentAt: number): Promise<Response | null> {
  const run = async () => {
    if (refreshedAt() > sentAt) return null
    const response = await request('/auth/refresh', { method: 'POST' })
    // 잠금 안에서 기록해야 다음 탭이 바로 확인 가능
    if (response.ok) markRefreshed()
    return response
  }
  const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined
  return locks ? locks.request(REFRESH_LOCK, run) : run()
}

function refreshSession(sentAt: number): Promise<void> {
  if (!refreshPromise) {
    // 개별 요청 취소가 다른 요청의 쿠키 갱신을 취소하지 않도록 signal을 공유하지 않는다.
    refreshPromise = (async () => {
      try {
        const response = await refreshOnce(sentAt)
        if (!response) { refreshError = null; return }
        if (!response.ok) {
          if (response.status === 401 && typeof window !== 'undefined') {
            window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
          }
          throw new ApiError(response.status, response.status === 401
            ? '로그인이 만료되었습니다. 다시 로그인해 주세요.'
            : '로그인 상태를 갱신하지 못했습니다. 잠시 후 다시 시도해 주세요.')
        }
        refreshError = null
      } catch (err) {
        refreshError = err
        throw err
      } finally {
        refreshVersion += 1
        refreshPromise = null
      }
    })()
  }
  return refreshPromise
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  // FormData 경계는 브라우저가 생성한다.
  if (!(init?.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const options = { ...init, headers }
  const version = refreshVersion
  const sentAt = Date.now()
  let res = await request(path, options)
  // 로그인·가입 자체의 401(인증 코드/가입 토큰 오류)은 갱신 대상이 아니다.
  if (res.status === 401 && !path.startsWith('/auth/')) {
    init?.signal?.throwIfAborted()
    if (version === refreshVersion) await refreshSession(sentAt)
    else if (refreshError) throw refreshError
    init?.signal?.throwIfAborted()
    res = await request(path, options)
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const fallback = res.status >= 500
      ? '서버에서 요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.'
      : res.status === 401 ? '로그인 상태를 확인해 주세요.'
      : res.status === 404 ? '요청한 결과를 찾을 수 없습니다.'
      : `요청을 처리하지 못했습니다. HTTP ${res.status}`
    throw new ApiError(res.status, errorMessage(body?.detail, fallback))
  }
  if (res.status === 204) return undefined as T
  try { return await res.json() as T }
  catch (err) {
    if (init?.signal?.aborted || (err instanceof Error && err.name === 'AbortError')) throw err
    throw new ApiError(res.status, '서버 응답 형식이 올바르지 않습니다. API 연결 주소를 확인해 주세요.')
  }
}
