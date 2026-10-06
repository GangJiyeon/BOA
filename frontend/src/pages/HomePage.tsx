import { useCallback, useEffect, useRef, useState } from 'react'
import { getHealth, type Health } from '../api/health'
import { getActor, getQuota, type Actor, type Quota } from '../api/account'
import type { SkinAnalysis } from '../api/skin'
import type { CosmeticSessionResult, HairSessionResult } from '../types/sessionResults'
import CosmeticPreview from '../components/CosmeticPreview'
import AccountPage from './AccountPage'
import HairPage from './HairPage'
import ResultsPage from './ResultsPage'
import KioskPage from './KioskPage'
import LandingPage from './LandingPage'
import Icon, { type IconName } from '../components/Icon'
import PageIntro from '../components/PageIntro'

const pages = [
  { id: 'home', label: '홈', icon: 'home' },
  { id: 'start', icon: 'user', label: '시작 · 계정' }, { id: 'skin', icon: 'skin', label: '피부 · 화장품' },
  { id: 'hair', icon: 'hair', label: '얼굴형 · 헤어' }, { id: 'results', icon: 'results', label: '이번 분석 결과' },
  { id: 'kiosk', icon: 'kiosk', label: '키오스크' }, { id: 'studio', icon: 'sparkles', label: 'AI Studio' },
] as const
type Page = typeof pages[number]['id']
function route() {
  const [path, query] = window.location.hash.slice(1).split('?')
  const page = path?.replace(/^\//, '')
  return { page: (pages.some(item => item.id === page) ? page : 'home') as Page, token: new URLSearchParams(query).get('token') ?? '' }
}
const actorNames = { anonymous: '비로그인', guest: '비회원', member: '회원', kiosk: '키오스크' }
export default function HomePage() {
  const [current, setCurrent] = useState(route)
  const [visited, setVisited] = useState(() => ({ skin: route().page === 'skin', hair: route().page === 'hair' }))
  const [sessionVersion, setSessionVersion] = useState(0)
  const [health, setHealth] = useState<Health | null>(null)
  const [healthError, setHealthError] = useState('')
  const [actor, setActor] = useState<Actor | null>(null)
  const [actorError, setActorError] = useState('')
  const [quota, setQuota] = useState<Quota | null>(null)
  const [quotaError, setQuotaError] = useState('')
  const [latestSkin, setLatestSkin] = useState<SkinAnalysis | null>(null)
  const [latestHair, setLatestHair] = useState<HairSessionResult | null>(null)
  const [latestCosmetics, setLatestCosmetics] = useState<CosmeticSessionResult | null>(null)
  const healthRequest = useRef<AbortController | null>(null)
  const actorRequest = useRef<AbortController | null>(null)
  const quotaRequest = useRef<AbortController | null>(null)
  const refreshQuota = useCallback(async () => {
    quotaRequest.current?.abort()
    const controller = new AbortController(); quotaRequest.current = controller
    try { const value = await getQuota(controller.signal); if (!controller.signal.aborted) { setQuota(value); setQuotaError('') } }
    catch (err) { if (!controller.signal.aborted) { setQuota(null); setQuotaError(err instanceof Error ? err.message : '횟수 조회 실패') } }
  }, [])
  const refreshActor = useCallback(async () => {
    actorRequest.current?.abort()
    const controller = new AbortController(); actorRequest.current = controller
    try {
      const value = await getActor(controller.signal)
      if (!controller.signal.aborted) { setActor(value); setActorError(''); await refreshQuota() }
    } catch (err) { if (!controller.signal.aborted) { setActor(null); setQuota(null); setActorError(err instanceof Error ? err.message : '세션 조회 실패') } }
  }, [refreshQuota])
  useEffect(() => {
    const update = () => {
      const next = route()
      setCurrent(next)
      if (next.page === 'skin' || next.page === 'hair') setVisited(value => ({ ...value, [next.page]: true }))
    }
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  useEffect(() => {
    document.getElementById('page-content')?.focus({ preventScroll: true })
    window.scrollTo({ top: 0, behavior: 'instant' })
    if (window.matchMedia('(max-width: 850px)').matches) {
      document.querySelector('.app-nav [aria-current="page"]')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    }
  }, [current.page])
  const refreshHealth = useCallback(async () => {
    healthRequest.current?.abort()
    const controller = new AbortController(); healthRequest.current = controller
    try { const value = await getHealth(controller.signal); if (!controller.signal.aborted) { setHealth(value); setHealthError('') } }
    catch (err) { if (!controller.signal.aborted) { setHealth(null); setHealthError(err instanceof Error ? err.message : '연결 확인 실패') } }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    healthRequest.current = controller
    getHealth(controller.signal).then(value => { if (!controller.signal.aborted) { setHealth(value); setHealthError('') } }).catch((err: Error) => { if (!controller.signal.aborted) setHealthError(err.message) })
    const initialActor = new AbortController()
    actorRequest.current = initialActor
    getActor(initialActor.signal).then(value => {
      if (!initialActor.signal.aborted) { setActor(value); setActorError(''); void refreshQuota() }
    }).catch((err: Error) => { if (!initialActor.signal.aborted) setActorError(err.message) })
    return () => { controller.abort(); healthRequest.current?.abort(); actorRequest.current?.abort(); quotaRequest.current?.abort() }
  }, [refreshQuota])
  const handleSkinAnalysis = useCallback((value: SkinAnalysis) => {
    setLatestSkin(value); setLatestCosmetics(null); void refreshQuota()
  }, [refreshQuota])
  const handleCosmeticResult = useCallback((value: CosmeticSessionResult) => {
    setLatestCosmetics(value); setLatestSkin(value.analysis)
  }, [])
  function clearSession() { setLatestSkin(null); setLatestHair(null); setLatestCosmetics(null); setSessionVersion(value => value + 1) }
  const startAnalysis = () => { window.location.hash = '/skin' }
  return <div className="app-shell">
    <a className="skip-link" href="#page-content" onClick={event => { event.preventDefault(); document.getElementById('page-content')?.focus() }}>본문으로 이동</a>
    <aside className="sidebar"><a href="#/home" className="brand" aria-label="BOA 홈"><span className="brand-symbol">b.</span><span>BOA<small>BEAUTY ON YOUR TERMS</small></span></a>
      <p className="nav-caption">MY BEAUTY JOURNEY</p>
      <nav className="app-nav" aria-label="주요 메뉴">{pages.map(page => <a key={page.id} href={`#/${page.id}`} aria-current={current.page === page.id ? 'page' : undefined}><Icon name={page.icon as IconName} /><span>{page.label}</span>{page.id === 'studio' && <small>준비 중</small>}</a>)}</nav>
      <div className="sidebar-bottom"><Icon name="sparkles" /><p>나를 위한 선택의 시작.</p><small>BOA PROJECT · 2026</small></div>
    </aside>
    <div className="workspace"><header className="topbar"><span className="breadcrumb">BOA <span>/</span> {pages.find(page => page.id === current.page)?.label}</span><div className="topbar-actions"><span className={`connection-badge ${health?.db ? 'connected' : ''}`}><i />{health?.db ? '서비스 연결됨' : healthError || (health && !health.db) ? '연결 확인 필요' : '연결 확인 중'}</span><a href="#/start" className="account-link" aria-label="계정 화면 열기"><Icon name="user" size={17} />{actor ? actorNames[actor.kind] : actorError ? '세션 확인 실패' : '확인 중'}</a></div></header>
    <main id="page-content" tabIndex={-1}>
    {(healthError || actorError) && <div role="alert" className="error-box">{healthError && `백엔드 연결 실패: ${healthError}`}{actorError && ` 세션 확인 실패: ${actorError}`} <button onClick={() => { void refreshHealth(); void refreshActor() }}>연결 다시 확인</button></div>}
    <div className="page-content">
      {current.page === 'home' && <LandingPage skin={latestSkin} hair={latestHair?.result ?? null} cosmetics={latestCosmetics} />}
      {visited.skin && <div hidden={current.page !== 'skin'} key={`skin:${sessionVersion}`}><CosmeticPreview onAnalysis={handleSkinAnalysis} onRecommendation={handleCosmeticResult} /></div>}
      {visited.hair && <div hidden={current.page !== 'hair'} key={`hair:${sessionVersion}`}><HairPage onResult={value => { setLatestHair(value); void refreshQuota() }} /></div>}
      {current.page === 'start' && <AccountPage actor={actor} onActorChange={refreshActor} onSession={clearSession} onLogin={clearSession} onLogout={clearSession} onSignup={clearSession} onStart={startAnalysis} />}
      {current.page === 'results' && <ResultsPage key={current.token} latestSkin={latestSkin} latestHair={latestHair} cosmetics={latestCosmetics} hasSharedToken={Boolean(current.token)} />}
      {current.page === 'kiosk' && <KioskPage actor={actor} onActorChange={refreshActor} onSession={clearSession} onEnd={clearSession} onStart={startAnalysis} />}
      {current.page === 'studio' && <section><PageIntro eyebrow="COMING NEXT" title="AI Studio">추천받은 스타일을 나의 얼굴에 미리 보는 다음 단계입니다.</PageIntro><div className="studio-placeholder"><span className="feature-icon"><Icon name="sparkles" size={36} /></span><h3>새로운 나를 미리 만나는 공간</h3><p>생성 기능을 연결하고 있습니다.<br />지금은 피부·헤어 분석과 추천을 먼저 확인해 보세요.</p><button disabled>미리보기 생성 · 준비 중</button><a href="#/home">분석 시작 화면으로 →</a></div></section>}
    </div>
    <footer className="app-footer"><span>BOA · 나에게 맞는 뷰티 추천</span><details><summary>연결 상태 확인</summary><ul className="health-status"><li>API: {health?.status ?? '연결 확인 필요'}</li><li>DB: {health?.db ? '연결됨' : '연결 확인 필요'}</li><li>S3: {health?.s3 ? '설정됨' : '미설정'}</li>{quota && <li>횟수 조회 · 피부 {quota.skin.remaining ?? '제한 없음'} / 헤어 {quota.hair.remaining ?? '제한 없음'}</li>}</ul>{quotaError && <p>{quotaError}</p>}<p>중간발표 버전 · 세션별 저장과 사용 횟수 적용은 연결 준비 중입니다.</p><button className="secondary" onClick={() => { void refreshHealth(); void refreshActor() }}>상태 다시 확인</button></details></footer>
    </main></div>
  </div>
}
