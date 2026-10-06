import { useEffect, useState } from 'react'
import { getTerms, type Term } from '../api/account'

export function useTerms() {
  const [terms, setTerms] = useState<Term[]>([])
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    getTerms(controller.signal).then(data => {
      if (controller.signal.aborted) return
      setTerms(data)
      if (!data.length) setError('현재 약관이 없습니다. 약관 데이터를 준비해 주세요.')
    }).catch((err: Error) => { if (!controller.signal.aborted) setError(err.message) })
    return () => controller.abort()
  }, [revision])
  return { terms, error, retry: () => { setError(''); setTerms([]); setRevision(n => n + 1) } }
}
