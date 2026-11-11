import { useEffect, useRef, useState } from 'react'
import { saveMoistureResult, type CompletedReceipt } from '../api/moisture'
import type { CompletedMeasurement } from '../moisture/autoMeasurement'

// A result can be measured before photo analysis, but can bind to only ONE
// analysis in the same photo/context. Retry always reuses that immutable pair.
export function useMoistureResult(analysisId: number | null, scope: number, active: boolean) {
  const [draft, setDraft] = useState<CompletedMeasurement | null>(null)
  const [receipt, setReceipt] = useState<CompletedReceipt | null>(null)
  const [status, setStatus] = useState<'empty' | 'pending' | 'saving' | 'saved' | 'error'>('empty')
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const binding = useRef<{ scope: number; id: string; analysisId: number | null } | null>(null)
  const request = useRef<AbortController | null>(null)
  useEffect(() => {
    request.current?.abort(); binding.current = null
    setDraft(null); setReceipt(null); setStatus('empty'); setError('')
  }, [scope])
  // Navigation hides the panel, but must not cancel an already completed result.
  useEffect(() => {
    const identity = binding.current
    if (!draft || !identity || identity.scope !== scope || identity.id !== draft.measurement_id) return
    if (receipt?.measurement_id === draft.measurement_id) return
    if (identity.analysisId === null) identity.analysisId = analysisId
    const target = identity.analysisId
    if (target === null) { setStatus('pending'); return }
    const controller = new AbortController(); request.current = controller
    setStatus('saving'); setError('')
    void saveMoistureResult(draft, target, controller.signal).then(value => {
      if (controller.signal.aborted || binding.current !== identity) return
      setReceipt(value); setStatus('saved')
    }).catch(e => {
      if (controller.signal.aborted || binding.current !== identity) return
      setStatus('error'); setError(e instanceof Error ? e.message : '측정 결과 저장 실패')
    })
    return () => controller.abort()
  }, [draft, analysisId, scope, retry, receipt])
  const complete = (result: CompletedMeasurement) => {
    if (!active || binding.current?.id === result.measurement_id) return
    request.current?.abort()
    binding.current = { scope, id: result.measurement_id, analysisId }
    setDraft(result); setReceipt(null); setStatus('pending'); setError('')
  }
  const clear = () => {
    request.current?.abort(); binding.current = null
    setDraft(null); setReceipt(null); setStatus('empty'); setError('')
  }
  return { draft, receipt, status, error, complete, clear, targetAnalysisId: binding.current?.analysisId ?? null, retry: () => setRetry(x => x + 1) }
}
