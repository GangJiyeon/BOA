import Icon from '../components/Icon'
import type { SkinAnalysis } from '../api/skin'
import type { HairResult } from '../api/hair'
import type { CosmeticSessionResult } from '../types/sessionResults'
export default function LandingPage({ skin, hair, cosmetics }: { skin: SkinAnalysis | null; hair: HairResult | null; cosmetics: CosmeticSessionResult | null }) {
  const services = [
    { route: 'skin', icon: 'skin' as const, title: '피부 분석 · 화장품 추천', description: '사진 분석 후 성분에 맞는 제품 조회', label: '사진 입력', primary: true },
    { route: 'hair', icon: 'hair' as const, title: '얼굴형 · 헤어 추천', description: '얼굴형과 선호 조건으로 스타일 조회', label: '사진 입력', primary: true },
    { route: 'studio', icon: 'sparkles' as const, title: 'AI Studio', description: '사진에 추천 스타일 적용', label: '준비 중', primary: false },
    { route: 'results', icon: 'results' as const, title: '이번 분석 결과', description: '피부·화장품·헤어 결과 확인', label: '결과 확인', primary: false },
    { route: 'start', icon: 'user' as const, title: '시작 · 계정', description: '비회원 시작, 이메일 인증 및 로그인', label: '계정 화면', primary: false },
    { route: 'kiosk', icon: 'kiosk' as const, title: '키오스크', description: '기기 등록 및 분석 세션 관리', label: '기기 관리', primary: false },
  ]
  return <section className="tablet-home">
    <header className="tablet-home-heading"><div><h1>기능 선택</h1><p>사용할 기능을 선택하세요.</p></div><span className="tablet-mode-label"><Icon name="kiosk" size={20} />터치 화면</span></header>
    <div className="service-grid">{services.map(service => <a key={service.route} href={`#/${service.route}`} className={`service-tile${service.primary ? ' primary-tile' : ''}`}><div className="tile-top"><span className="tile-icon"><Icon name={service.icon} size={30} /></span>{service.route === 'studio' && <span className="availability">준비 중</span>}</div><h2>{service.title}</h2><p>{service.description}</p><span className="tile-action">{service.label}<Icon name="arrow" size={21} /></span></a>)}</div>
    {(skin || hair || cosmetics) && <section className="recent-strip"><Icon name="results" size={24} /><div><h3>최근 분석 결과</h3><p>{[skin && '피부 분석', cosmetics && `화장품 ${cosmetics.response.recommendations.length}개`, hair && '헤어 추천'].filter(Boolean).join(' · ')}</p></div><a className="button secondary" href="#/results">결과 확인 <Icon name="arrow" /></a></section>}
  </section>
}
