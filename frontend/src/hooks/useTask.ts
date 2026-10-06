import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'

// 언마운트·입력 변경 시 취소하고, 같은 작업의 중복 제출은 막는다.
export function useTask() {
  const active = useRef<AbortController | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => () => active.current?.abort(), [])
  function reset() { active.current?.abort(); active.current = null; setBusy(false); setError('') }
  async function run(action: (signal: AbortSignal) => Promise<void>) {
    if (active.current) return
    const controller = new AbortController()
    active.current = controller; setBusy(true); setError('')
    try { await action(controller.signal) }
    catch (err) {
      if (!controller.signal.aborted) setError(err instanceof ApiError ? `${err.message}${err.status ? ` (${err.status})` : ''}` : err instanceof Error ? err.message : '요청에 실패했습니다.')
    } finally { if (active.current === controller) { active.current = null; setBusy(false) } }
  }
  return { busy, error, run, reset }
}
