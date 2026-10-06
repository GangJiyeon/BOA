import PageIntro from '../components/PageIntro'
import { useEffect, useState, type FormEvent } from 'react'
import { getActor, getMember, logout, refreshLogin, sendCode, signup, startGuest, updateLanguage, verifyCode, type Actor, type GuestSession, type Language, type Member, termNames } from '../api/account'
import { CaptureConsent, TaskStatus } from '../components/Shared'
import { useTerms } from '../hooks/useTerms'
import { useTask } from '../hooks/useTask'

type Props = { actor: Actor | null; onActorChange: () => Promise<void>; onSession: (session: GuestSession) => void; onLogin: () => void; onLogout: () => void; onSignup: () => void; onStart: () => void }
export default function AccountPage({ actor, onActorChange, onSession, onLogin, onLogout, onSignup, onStart }: Props) {
  const task = useTask()
  const { terms, error: termsError, retry } = useTerms()
  const [face, setFace] = useState(false)
  const [age, setAge] = useState(false)
  const [email, setEmail] = useState('')
  const [sentEmail, setSentEmail] = useState('')
  const [code, setCode] = useState('')
  const [signupToken, setSignupToken] = useState<string | null>(null)
  const [devCode, setDevCode] = useState<string | null>(null)
  const [resendUntil, setResendUntil] = useState(0)
  const [now, setNow] = useState(() => Date.now())
  const [language, setLanguage] = useState<Language>('ko')
  const [nationality, setNationality] = useState('KR')
  const [resides, setResides] = useState(true)
  const [agreed, setAgreed] = useState<number[]>([])
  const [member, setMember] = useState<Member | null>(null)
  const [message, setMessage] = useState('')
  useEffect(() => {
    if (resendUntil <= Date.now()) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [resendUntil])
  useEffect(() => {
    if (actor?.kind !== 'member') return
    const controller = new AbortController()
    getMember(controller.signal).then(value => { if (!controller.signal.aborted) { setMember(value); setLanguage(value.language) } }).catch((err: Error) => { if (!controller.signal.aborted) setMessage(err.message) })
    return () => controller.abort()
  }, [actor])
  const seconds = Math.max(0, Math.ceil((resendUntil - now) / 1000))
  const faceTerm = terms.find(t => t.type === 'FACE_IMAGE')
  const requiredReady = ['SERVICE', 'PRIVACY', 'AGE_14', 'FACE_IMAGE'].every(type => terms.some(t => t.type === type && agreed.includes(t.id)))
  function send(event: FormEvent) {
    event.preventDefault(); setMessage('')
    void task.run(async signal => {
      const value = await sendCode(email.trim(), signal)
      if (signal.aborted) return
      setSentEmail(email.trim()); setDevCode(value.dev_code); setCode(''); setSignupToken(null)
      setNow(Date.now()); setResendUntil(Date.now() + value.resend_seconds * 1000)
      setMessage('인증 코드 요청을 처리했습니다. 코드를 입력해 주세요.')
    })
  }
  function verify(event: FormEvent) {
    event.preventDefault(); setMessage('')
    void task.run(async signal => {
      const value = await verifyCode(sentEmail, code, signal)
      if (signal.aborted) return
      if (value.signup_required) {
        if (!value.signup_token) throw new Error('가입 토큰이 응답에 없습니다. 다시 인증해 주세요.')
        setSignupToken(value.signup_token); setMessage('이메일 확인 완료. 가입 정보를 입력해 주세요.')
      } else { onLogin(); setSignupToken(null); setCode(''); setDevCode(null); setMessage('로그인했습니다.'); await onActorChange() }
    })
  }
  function join(event: FormEvent) {
    event.preventDefault(); if (task.busy || !signupToken || !requiredReady) return
    void task.run(async signal => {
      await signup({ signup_token: signupToken, language, nationality, resides_in_korea: resides, agreed_terms_ids: agreed }, signal)
      if (signal.aborted) return
      onSignup(); setSignupToken(null); setCode(''); setDevCode(null); setMessage('가입했습니다.'); await onActorChange()
    })
  }
  function beginGuest(event: FormEvent) {
    event.preventDefault()
    if (task.busy || !actor) return
    setMessage('')
    void task.run(async signal => {
      // 화면을 열어 둔 사이 세션이 만료됐을 수 있으므로 현재 상태를 확인한다.
      const currentActor = await getActor(signal)
      if (signal.aborted) return
      if (currentActor.kind === 'guest') {
        await onActorChange()
        if (!signal.aborted) { setMessage('기존 비회원 세션을 이어갑니다.'); onStart() }
        return
      }
      if (currentActor.kind !== 'anonymous') {
        await onActorChange()
        throw new Error('이용 상태가 변경되었습니다. 현재 계정 또는 키오스크에서 시작해 주세요.')
      }
      if (!faceTerm || !face || !age) {
        await onActorChange()
        throw new Error('비회원 이용을 시작하려면 동의 항목을 확인해 주세요.')
      }
      const session = await startGuest(faceTerm.id, signal)
      if (signal.aborted) return
      onSession(session)
      await onActorChange()
      if (!signal.aborted) { setMessage('비회원 세션을 시작했습니다.'); onStart() }
    })
  }
  return <section><PageIntro eyebrow="WELCOME TO BOA" title="시작하기 · 계정">비회원으로 시작하거나 이메일 인증 후 로그인하세요.</PageIntro>
    {termsError && <p role="alert" className="error-box">{termsError} <button type="button" onClick={() => { setFace(false); setAge(false); setAgreed([]); retry() }}>약관 다시 조회</button></p>}
    {actor?.kind === 'member' ? <section className="form-card"><h3>내 계정</h3>
      {member && <><p>{member.email} · {member.nationality ?? '국적 미설정'}</p><label className="field">사용 언어<LanguageSelect value={language} onChange={setLanguage} /></label>
        <button disabled={task.busy} onClick={() => void task.run(async signal => { const value = await updateLanguage(language, signal); if (!signal.aborted) { setMember(value); setMessage('언어 설정을 저장했습니다.') } })}>언어 저장</button></>}
      <div className="actions"><button onClick={onStart}>피부 분석으로 이동</button><button disabled={task.busy} onClick={() => void task.run(async signal => { await logout(signal); if (signal.aborted) return; onLogout(); setMember(null); setMessage('로그아웃했습니다.'); await onActorChange() })}>로그아웃</button></div>
    </section> : <div className="form-columns">
      <form className="form-card" onSubmit={beginGuest}>
        <h3>비회원 시작</h3>
        {actor?.kind === 'kiosk' ? <p>이 기기는 키오스크입니다. 키오스크 메뉴에서 사용자를 시작해 주세요.</p> : <>
          {actor?.kind === 'guest' ? <p>현재 비회원 세션을 이어갑니다. 이번 분석 결과와 입력한 사진·조건이 유지됩니다.</p>
            : <CaptureConsent terms={terms} face={face} age={age} onFace={setFace} onAge={setAge} />}
          <button type="submit" disabled={task.busy || !actor || (actor.kind !== 'guest' && (!faceTerm || !face || !age))}>{actor?.kind === 'guest' ? '세션 이어서 시작' : '동의하고 시작'}</button>
        </>}
      </form>
      <section className="form-card"><h3>이메일 로그인</h3>{actor?.kind === 'kiosk' ? <p>일반 계정으로 로그인하려면 <a href="#/kiosk">키오스크 등록을 해제</a>해 주세요.</p> : <><p className="input-note">현재 메일 발송은 서버 로그 출력 단계입니다. 테스트 코드는 백엔드 담당자에게 확인하세요.</p>
        <form onSubmit={send}><label className="field">이메일<input type="email" required autoComplete="email" value={email} onChange={e => { task.reset(); setEmail(e.target.value); setSentEmail(''); setSignupToken(null); setCode(''); setDevCode(null); setMessage('') }} /></label>
          <button type="submit" disabled={task.busy || seconds > 0}>{seconds ? `${seconds}초 후 재요청` : '인증 코드 요청'}</button></form>
        {sentEmail && !signupToken && <form onSubmit={verify}><label className="field">인증 코드<input required inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" value={code} onChange={e => setCode(e.target.value)} /></label>
          {devCode && <p>개발 환경 인증 코드: <strong>{devCode}</strong></p>}<button type="submit" disabled={task.busy}>코드 확인</button></form>}
        <button type="button" disabled className="secondary">Google 로그인 · 프런트 연결 준비 중</button></>}
      </section>
    </div>}
    {signupToken && <form className="form-card" onSubmit={join}><h3>가입 정보</h3><div className="form-grid">
      <label className="field">언어<LanguageSelect value={language} onChange={setLanguage} /></label>
      <label className="field">국적 코드<input value={nationality} required pattern="[A-Z]{2}" maxLength={2} placeholder="KR" onChange={e => setNationality(e.target.value.toUpperCase())} /></label></div>
      <label className="check-row"><input type="checkbox" checked={resides} onChange={e => setResides(e.target.checked)} />한국에 거주합니다.</label>
      <p className="input-note">약관 본문 연결 준비 중 · 아래는 가입 API 확인용 동의 항목입니다.</p>
      {terms.map(term => <label key={term.id} className="check-row"><input type="checkbox" checked={agreed.includes(term.id)} onChange={e => setAgreed(ids => e.target.checked ? [...ids, term.id] : ids.filter(id => id !== term.id))} />{termNames[term.type] ?? term.type} · {term.version} · {term.required ? '필수' : '선택'}</label>)}
      <button type="submit" disabled={task.busy || !requiredReady}>가입하기</button>
    </form>}
    <div className="actions"><button type="button" disabled={task.busy} className="secondary" onClick={() => void task.run(async signal => { try { await refreshLogin(signal); if (!signal.aborted) setMessage('로그인 상태를 갱신했습니다.') } finally { if (!signal.aborted) await onActorChange() } })}>로그인 세션 갱신</button></div>
    <TaskStatus busy={task.busy} error={task.error} />{message && <p role="status">{message}</p>}
  </section>
}
function LanguageSelect({ value, onChange }: { value: Language; onChange: (value: Language) => void }) {
  return <select value={value} onChange={e => onChange(e.target.value as Language)}><option value="ko">한국어</option><option value="en">English</option><option value="zh">中文</option><option value="ja">日本語</option></select>
}
