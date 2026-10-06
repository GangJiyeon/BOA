import PageIntro from '../components/PageIntro'
import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import type { Actor, GuestSession } from '../api/account'
import { endKiosk, getKiosk, registerKiosk, revokeKiosk, startKiosk, type Kiosk } from '../api/kiosk'
import { CaptureConsent, TaskStatus } from '../components/Shared'
import { useTerms } from '../hooks/useTerms'
import { useTask } from '../hooks/useTask'

export default function KioskPage({ actor, onActorChange, onSession, onEnd, onStart }: { actor: Actor | null; onActorChange: () => Promise<void>; onSession: (session: GuestSession) => void; onEnd: () => void; onStart: () => void }) {
  const task = useTask()
  const { terms, error, retry } = useTerms()
  const [kiosk, setKiosk] = useState<Kiosk | null>(null)
  const [admin, setAdmin] = useState('')
  const [face, setFace] = useState(false)
  const [age, setAge] = useState(false)
  const [message, setMessage] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    getKiosk(controller.signal).then(value => { if (!controller.signal.aborted) setKiosk(value) }).catch((err: Error) => { if (!controller.signal.aborted && !(err instanceof ApiError && err.status === 404)) setMessage(err.message) })
    return () => controller.abort()
  }, [actor])
  const faceTerm = terms.find(t => t.type === 'FACE_IMAGE')
  return <section><PageIntro eyebrow="KIOSK MANAGEMENT" title="키오스크">기기를 등록하고 사용자별 분석 세션을 관리하세요.</PageIntro>
    <form className="form-card" onSubmit={event => {
      event.preventDefault(); if (task.busy) return; setMessage('')
      void task.run(async signal => {
        if (actor?.kind === 'kiosk' && kiosk) {
          if (kiosk.session_active) throw new Error('사용자 종료 후 기기 등록을 해제해 주세요.')
          await revokeKiosk(admin, kiosk.kiosk_id, signal)
          if (signal.aborted) return
          setAdmin(''); onEnd(); setKiosk(null); await onActorChange(); setMessage('기기 등록을 해제했습니다. 일반 계정으로 이용할 수 있습니다.')
          return
        }
        const value = await registerKiosk(admin, signal)
        if (signal.aborted) return
        setAdmin(''); onEnd(); setFace(false); setAge(false); setKiosk({ ...value, session_active: false }); await onActorChange(); setMessage('기기를 등록했습니다.')
      })
    }}><h3>{actor?.kind === 'kiosk' ? '관리자 기기 해제' : '관리자 기기 등록'}</h3><label className="field">관리자 코드<input type="password" autoComplete="off" required value={admin} onChange={e => setAdmin(e.target.value)} /></label><button disabled={task.busy || !actor || actor.kind === 'member' || (actor.kind === 'kiosk' && (!kiosk || kiosk.session_active))}>{actor?.kind === 'kiosk' ? '이 기기 등록 해제' : '이 기기 등록'}</button>{actor?.kind === 'kiosk' && kiosk?.session_active && <p>사용자 종료 후 기기 등록을 해제할 수 있습니다.</p>}{actor?.kind === 'member' && <p>공용 기기 등록 전 회원 계정에서 로그아웃해 주세요.</p>}</form>
    {kiosk && actor?.kind === 'kiosk' && <form className="form-card" onSubmit={event => {
      event.preventDefault(); if (task.busy || !faceTerm || !face || !age) return
      void task.run(async signal => {
        const session = await startKiosk(faceTerm.id, signal)
        if (signal.aborted) return
        onSession(session); setFace(false); setAge(false); setKiosk({ ...kiosk, session_active: true }); await onActorChange(); onStart()
      })
    }}><h3>기기 #{kiosk.kiosk_id} · {kiosk.session_active ? '사용 중' : '대기 중'}</h3>
      {error && <p role="alert">{error} <button type="button" onClick={() => { setFace(false); setAge(false); retry() }}>약관 다시 조회</button></p>}
      <CaptureConsent terms={terms} face={face} age={age} onFace={setFace} onAge={setAge} />
      <div className="actions"><button disabled={task.busy || !faceTerm || !face || !age}>새 사용자 시작</button><button type="button" disabled={task.busy || !kiosk.session_active} className="secondary" onClick={() => void task.run(async signal => {
        await endKiosk(signal)
        if (signal.aborted) return
        onEnd(); setFace(false); setAge(false); setKiosk({ ...kiosk, session_active: false }); await onActorChange(); setMessage('사용자를 종료했습니다. 화면의 분석 결과를 지웠습니다.')
      })}>사용자 종료</button></div>
    </form>}
    <TaskStatus busy={task.busy} error={task.error} />{message && <p role="status">{message}</p>}
  </section>
}
