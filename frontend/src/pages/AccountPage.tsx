import PageIntro from '../components/PageIntro'
import { useEffect, useState, type FormEvent } from 'react'
import { getActor, getMember, googleLogin, logout, signup, startGuest, type Actor, type GuestSession, type Member, termNames } from '../api/account'
import { CaptureConsent, TaskStatus } from '../components/Shared'
import { useTerms } from '../hooks/useTerms'
import { useTask } from '../hooks/useTask'
import GoogleLoginButton from '../components/GoogleLoginButton'
import AccountPreferences from '../components/AccountPreferences'
import AccountHistory from '../components/AccountHistory'
import Icon from '../components/Icon'

function settingsView() { return new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('view') === 'settings' }

type Props = { actor: Actor | null; onActorChange: () => Promise<void>; onSession: (session: GuestSession) => void; onLogin: () => void; onLogout: () => void; onSignup: () => void; onStart: () => void }
export default function AccountPage({ actor, onActorChange, onSession, onLogin, onLogout, onSignup, onStart }: Props) {
  const task = useTask()
  const { terms, error: termsError, retry } = useTerms()
  const [face, setFace] = useState(false)
  const [age, setAge] = useState(false)
  const [signupToken, setSignupToken] = useState<string | null>(null)
  const [nationality, setNationality] = useState('KR')
  const [resides, setResides] = useState(true)
  const [agreed, setAgreed] = useState<number[]>([])
  const [member, setMember] = useState<Member | null>(null)
  const [message, setMessage] = useState('')
  const [showSettings, setShowSettings] = useState(settingsView)
  useEffect(() => {
    const update = () => { setShowSettings(settingsView()); setMessage(''); task.reset() }
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
    // hash 주소에 따라 설정 화면을 전환하고 진행 중인 화면 작업은 취소한다.
  }, [])
  useEffect(() => {
    if (actor?.kind !== 'member') return
    const controller = new AbortController()
    getMember(controller.signal).then(value => { if (!controller.signal.aborted) { setMember(value) } }).catch((err: Error) => { if (!controller.signal.aborted) setMessage(err.message) })
    return () => controller.abort()
  }, [actor])
  const faceTerm = terms.find(t => t.type === 'FACE_IMAGE')
  const requiredReady = ['SERVICE', 'PRIVACY', 'AGE_14', 'FACE_IMAGE'].every(type => terms.some(t => t.type === type && agreed.includes(t.id)))
  function loginWithGoogle(googleCode: string) {
    setMessage('')
    void task.run(async signal => {
      const value = await googleLogin(googleCode, signal)
      if (signal.aborted) return
      if (value.signup_required) {
        if (!value.signup_token) throw new Error('가입 토큰이 응답에 없습니다. 다시 로그인해 주세요.')
        setSignupToken(value.signup_token); setMessage('구글 계정 확인 완료. 가입 정보를 입력해 주세요.')
      } else { onLogin(); setSignupToken(null); setMessage('로그인했습니다.'); await onActorChange() }
    })
  }
  function join(event: FormEvent) {
    event.preventDefault(); if (task.busy || !signupToken || !requiredReady) return
    void task.run(async signal => {
      await signup({ signup_token: signupToken, nationality, resides_in_korea: resides, agreed_terms_ids: agreed }, signal)
      if (signal.aborted) return
      onSignup(); setSignupToken(null); setMessage('가입했습니다.'); await onActorChange()
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
  return <section className="account-page"><PageIntro eyebrow={actor?.kind === 'member' ? 'MY ACCOUNT' : 'WELCOME TO BOA'} title={actor?.kind === 'member' ? (showSettings ? '계정 설정' : '내 계정') : '시작하기 · 계정'}>{actor?.kind === 'member' ? (showSettings ? '약관 동의와 계정 이용 설정을 관리하세요.' : '내 정보와 저장된 분석 기록을 확인하세요.') : '비회원으로 시작하거나 Google 계정으로 로그인하세요.'}</PageIntro>
    <p><a className="text-action" href="#/kiosk">키오스크 기기 관리</a></p>
    {actor?.kind !== 'member' && termsError && <p role="alert" className="error-box">{termsError} <button type="button" onClick={() => { setFace(false); setAge(false); setAgreed([]); retry() }}>약관 다시 조회</button></p>}
    {actor?.kind === 'member' ? showSettings ? <>
      <a className="account-back" href="#/start" aria-disabled={task.busy} onClick={event => { if (task.busy) event.preventDefault() }}>← 내 계정으로</a>
      <section className="form-card account-settings">
        <AccountPreferences task={task} onMessage={setMessage} onDeleted={async () => {
          // 서버 삭제 성공 후에만 계정 정보와 이번 이용의 입력·결과를 비운다.
          onLogout(); setMember(null); setSignupToken(null)
          setFace(false); setAge(false); setAgreed([])
          setMessage('회원 탈퇴가 완료되었습니다.')
          await onActorChange()
        }} />
      </section>
    </> : <>
      <section className="form-card account-profile" aria-label="회원 정보">
        <div className="account-profile-top">
          <div className="account-identity"><span className="account-avatar"><Icon name="user" size={24} /></span><div><span className="account-caption">로그인 계정</span><strong className="account-email">{member?.email ?? '계정 정보를 불러오는 중입니다.'}</strong>{member?.nationality && <span className="account-nationality">국적 {member.nationality}</span>}</div></div>
          <div className="account-profile-actions"><button type="button" disabled={task.busy} onClick={onStart}>피부 분석으로 이동</button><button type="button" className="text-button" disabled={task.busy} onClick={() => void task.run(async signal => { await logout(signal); if (signal.aborted) return; onLogout(); setMember(null); setMessage('로그아웃했습니다.'); await onActorChange() })}>로그아웃</button></div>
        </div>
        <div className="account-profile-bottom">
          <a className="account-settings-link" href="#/start?view=settings" aria-disabled={task.busy} onClick={event => { if (task.busy) event.preventDefault() }}>약관 및 계정 관리 <span aria-hidden="true">→</span></a>
        </div>
      </section>
      {member && <section className="form-card account-history-card"><AccountHistory disabled={task.busy} /></section>}
    </> : <div className="form-columns">
      <form className="form-card" onSubmit={beginGuest}>
        <h3>비회원 시작</h3>
        {actor?.kind === 'kiosk' ? <p>이 기기는 키오스크입니다. 키오스크 메뉴에서 사용자를 시작해 주세요.</p> : <>
          {actor?.kind === 'guest' ? <p>현재 비회원 세션을 이어갑니다. 이번 분석 결과와 입력한 사진·조건이 유지됩니다.</p>
            : <CaptureConsent terms={terms} face={face} age={age} onFace={setFace} onAge={setAge} />}
          <button type="submit" disabled={task.busy || !actor || (actor.kind !== 'guest' && (!faceTerm || !face || !age))}>{actor?.kind === 'guest' ? '세션 이어서 시작' : '동의하고 시작'}</button>
        </>}
      </form>
      <section className="form-card"><h3>로그인</h3>{actor?.kind === 'kiosk' ? <p>일반 계정으로 로그인하려면 <a href="#/kiosk">키오스크 등록을 해제</a>해 주세요.</p> : <>
        {!import.meta.env.VITE_GOOGLE_CLIENT_ID && <p className="input-note">이 환경에서는 비회원으로 이용해 주세요.</p>}
        <GoogleLoginButton disabled={task.busy} onCode={loginWithGoogle} onError={setMessage} /></>}
      </section>
    </div>}
    {signupToken && <form className="form-card" onSubmit={join}><h3>가입 정보</h3><div className="form-grid">
      <label className="field">국적 코드<input value={nationality} required pattern="[A-Z]{2}" maxLength={2} placeholder="KR" onChange={e => setNationality(e.target.value.toUpperCase())} /></label></div>
      <label className="check-row"><input type="checkbox" checked={resides} onChange={e => setResides(e.target.checked)} />한국에 거주합니다.</label>
      <p className="input-note">약관 본문 연결 준비 중 · 아래는 가입 API 확인용 동의 항목입니다.</p>
      {terms.map(term => <label key={term.id} className="check-row"><input type="checkbox" checked={agreed.includes(term.id)} onChange={e => setAgreed(ids => e.target.checked ? [...ids, term.id] : ids.filter(id => id !== term.id))} />{termNames[term.type] ?? term.type} · {term.version} · {term.required ? '필수' : '선택'}</label>)}
      <button type="submit" disabled={task.busy || !requiredReady}>가입하기</button>
    </form>}
    <TaskStatus busy={task.busy} error={task.error} />{message && <p role="status">{message}</p>}
  </section>
}
