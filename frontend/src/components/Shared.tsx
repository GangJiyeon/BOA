import { type Term } from '../api/account'
import type { SkinAnalysis } from '../api/skin'
import MetricScores from './MetricScores'

export function SectionJump({ targetId, children }: { targetId: string; children: string }) {
  return <button type="button" className="secondary section-jump" onClick={() => {
    const target = document.getElementById(targetId)
    if (!target) return
    target.focus({ preventScroll: true })
    target.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
  }}>{children}</button>
}

export function TaskStatus({ busy, error }: { busy: boolean; error: string }) {
  return <div aria-live="polite" aria-busy={busy}>{busy && <p role="status">요청 중입니다…</p>}{error && <p role="alert" className="error-box">{error}</p>}</div>
}
export function CaptureConsent({ terms, face, age, onFace, onAge }: { terms: Term[]; face: boolean; age: boolean; onFace: (value: boolean) => void; onAge: (value: boolean) => void }) {
  const term = terms.find(t => t.type === 'FACE_IMAGE')
  return <>
    <p className="input-note">촬영 동의 폼 연결 확인용입니다. 약관 본문은 연결 준비 중입니다.</p>
    <label className="check-row"><input type="checkbox" checked={face} disabled={!term} onChange={e => onFace(e.target.checked)} />얼굴 이미지 처리 동의 {term ? `· ${term.version}` : '· 약관 조회 필요'}</label>
    <label className="check-row"><input type="checkbox" checked={age} onChange={e => onAge(e.target.checked)} />만 14세 이상입니다.</label>
  </>
}
export function SkinSummary({ analysis }: { analysis: SkinAnalysis }) {
  return <section className="form-card"><h3>피부 분석 #{analysis.id}</h3>
    <MetricScores scores={analysis.scores} />
  </section>
}
