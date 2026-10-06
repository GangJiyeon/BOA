import { useState, type FormEvent } from 'react'
import PageIntro from '../components/PageIntro'
import { getHairResult, type HairResult } from '../api/hair'
import { getSkinAnalysis, type SkinAnalysis } from '../api/skin'
import { SkinSummary, SectionJump, TaskStatus } from '../components/Shared'
import { useTask } from '../hooks/useTask'
import { HairResults } from './HairPage'
import MetricScores from '../components/MetricScores'
import CosmeticProductCard from '../components/CosmeticProductCard'
import { cosmeticCategoryNames } from '../utils/cosmeticLabels'
import type { CosmeticSessionResult, HairSessionResult } from '../types/sessionResults'

export default function ResultsPage({ latestSkin, latestHair, cosmetics, hasSharedToken }: {
  latestSkin: SkinAnalysis | null
  latestHair: HairSessionResult | null
  cosmetics: CosmeticSessionResult | null
  hasSharedToken: boolean
}) {
  const task = useTask()
  const [kind, setKind] = useState<'skin' | 'hair'>('skin')
  const [id, setId] = useState('')
  const [queriedSkin, setQueriedSkin] = useState<SkinAnalysis | null>(null)
  const [queriedHair, setQueriedHair] = useState<HairResult | null>(null)
  const result = cosmetics?.response
  const dailyCare = result?.recommendation_mode === 'daily_care'
  const hasResults = Boolean(latestSkin || latestHair || cosmetics)
  const testInput = cosmetics && cosmetics.inputMode !== 'photo'
  function resetQuery() { task.reset(); setQueriedSkin(null); setQueriedHair(null) }
  function queryId(event: FormEvent) {
    event.preventDefault()
    if (task.busy) return
    setQueriedSkin(null); setQueriedHair(null)
    void task.run(async signal => {
      const number = Number(id)
      if (!Number.isSafeInteger(number) || number <= 0) throw new Error('올바른 분석 번호를 입력해 주세요.')
      if (kind === 'skin') { const value = await getSkinAnalysis(number, signal); if (!signal.aborted) setQueriedSkin(value) }
      else { const value = await getHairResult(number, signal); if (!signal.aborted) setQueriedHair(value) }
    })
  }
  return <section className="session-results">
    <PageIntro eyebrow="YOUR RESULTS" title="이번 분석 결과">마지막으로 완료한 피부·화장품과 헤어 결과를 한곳에서 확인하세요.</PageIntro>
    <p className="session-note">이번 이용 중 완료한 결과입니다. 새로고침하거나 이용 세션을 바꾸면 이 목록은 초기화됩니다.</p>
    {hasSharedToken && <p className="input-note">공유 링크 조회는 준비 중입니다. 아래에는 이 화면에서 직접 실행한 결과만 표시합니다.</p>}
    {!hasResults && <div className="empty-box"><h3>아직 완료한 분석이 없어요</h3><p>피부 분석이나 헤어 추천을 진행하면 이곳에 결과가 모입니다.</p><div className="actions"><a className="button" href="#/skin">피부 분석 시작</a><a className="button secondary" href="#/hair">헤어 추천 시작</a></div></div>}
    {hasResults && <>
      <div className="result-overview" aria-label="완료한 결과 요약">
        <div><span>피부 지표</span><strong>{latestSkin ? '분석 완료' : testInput ? '테스트 입력' : '미실행'}</strong><SectionJump targetId="session-skin-title">피부 결과 보기</SectionJump></div>
        <div><span>화장품</span><strong>{result ? `${result.recommendations.length}개 확인` : '추천 미완료'}</strong><SectionJump targetId="session-cosmetic-title">화장품 결과 보기</SectionJump></div>
        <div><span>얼굴형 · 헤어</span><strong>{latestHair ? `${latestHair.result.recommendations.length}개 스타일` : '미실행'}</strong><SectionJump targetId="session-hair-title">헤어 결과 보기</SectionJump></div>
      </div>
      <section className="session-result-section" aria-labelledby="session-skin-title">
        <div className="results-heading"><h3 id="session-skin-title" className="section-target" tabIndex={-1}>피부 지표</h3><a className="text-action" href="#/skin">사진·분석 조건 변경 →</a></div>
        {latestSkin ? <SkinSummary analysis={latestSkin} /> : result ? <div className="form-card">
          <p className="input-note">{cosmetics?.inputMode === 'development' ? '개발용 가정 점수입니다. 실제 사진 분석 결과가 아닙니다.' : '연동 확인용 JSON 입력 결과입니다. 이 화면에서 사진을 분석해 저장한 결과가 아닙니다.'}</p>
          <MetricScores scores={result.assessments.map(a => ({ metric_code: a.code, metric_name: a.name, score: a.score, category_name: a.category, higher_is_better: !['redness', 'trouble'].includes(a.code) }))} />
        </div> : <p className="empty-box">아직 피부 분석을 진행하지 않았습니다.</p>}
      </section>
      <section className="session-result-section" aria-labelledby="session-cosmetic-title">
        <div className="results-heading"><h3 id="session-cosmetic-title" className="section-target" tabIndex={-1}>{dailyCare ? '일상 관리용 화장품 제안' : '화장품 추천'}</h3><a className="text-action" href="#/skin">제품 종류 변경·더보기 →</a></div>
        {result ? <>
          <p className="result-explanation">{result.recommendation_notice || '성분표에서 확인한 매칭을 바탕으로 고른 후보이며, 제품 효과를 보증하지 않습니다.'}</p>
          <p className="input-note">{cosmetics?.category ? cosmeticCategoryNames[cosmetics.category] : '전체 기초 제품'} · 현재 확인한 {result.recommendations.length}개 제품{testInput && ' · 연동 테스트 결과'}</p>
          {result.applied_exclusions.length > 0 && <p className="exclusion-summary">제외 적용: {result.applied_exclusions.join(', ')}</p>}
          {!result.recommendations.length && <div className="empty-box"><p>{result.empty_reason || '현재 조건에 맞는 제품이 없습니다.'}</p><a className="text-action" href="#/skin">입력·추천 조건 확인 →</a></div>}
          <ul className="product-list">{result.recommendations.map(product => <CosmeticProductCard key={product.product_id} product={product} dailyCare={dailyCare} scorableTargetCount={result.scorable_target_count} />)}</ul>
          {result.deferred_metrics.length > 0 && <p className="input-note">성분 매칭 보류 지표: {result.assessments.filter(a => result.deferred_metrics.includes(a.code)).map(a => a.name).join(' · ')}. 이 지표의 개선 효과로 제품을 선정하지 않았습니다.</p>}
        </> : <div className="empty-box"><p>{latestSkin ? '피부 점수는 확인됐지만, 이 분석의 화장품 추천 결과는 아직 없습니다.' : '피부·화장품 화면에서 추천을 진행해 주세요.'}</p><a className="text-action" href="#/skin">화장품 추천 확인 →</a></div>}
      </section>
      <section className="session-result-section" aria-labelledby="session-hair-title">
        <div className="results-heading"><h3 id="session-hair-title" className="section-target" tabIndex={-1}>얼굴형 · 헤어</h3><a className="text-action" href="#/hair">사진·스타일 조건 변경 →</a></div>
        {latestHair ? <>
          <div className="form-card"><h4>얼굴형: {latestHair.analysis.face_shape}</h4>{latestHair.analysis.top2 && <p>차순위 얼굴형: {latestHair.analysis.top2}</p>}</div>
          <HairResults result={latestHair.result} />
        </> : <div className="empty-box"><p>아직 헤어 추천을 진행하지 않았습니다.</p><a className="text-action" href="#/hair">헤어 추천 시작 →</a></div>}
      </section>
    </>}
    <details className="form-card result-debug-tools" onToggle={event => { if (!event.currentTarget.open) resetQuery() }}>
      <summary>개발용 도구 · 분석 번호로 연결 확인</summary>
      <p className="input-note">저장된 결과의 API 연결을 확인하는 도구입니다. 조회한 결과는 이번 분석 목록에 추가하지 않습니다.</p>
      <form onSubmit={queryId}><div className="form-grid"><label className="field">결과 종류<select value={kind} onChange={e => { resetQuery(); setKind(e.target.value as 'skin' | 'hair') }}><option value="skin">피부 분석</option><option value="hair">헤어 추천</option></select></label><label className="field">번호<input type="number" min={1} step={1} required value={id} onChange={e => { resetQuery(); setId(e.target.value) }} /></label></div><button disabled={task.busy}>번호로 조회</button></form>
      <TaskStatus busy={task.busy} error={task.error} />
      {queriedSkin && <SkinSummary analysis={queriedSkin} />}{queriedHair && <HairResults result={queriedHair} />}
    </details>
  </section>
}
