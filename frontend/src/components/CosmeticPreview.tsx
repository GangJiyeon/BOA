import { useEffect, useRef, useState, type FormEvent } from 'react'
import { getCosmeticPreview, type AnalysisMetricScore, type MetricCode, type PreviewRequest, type PreviewResponse, type ProductCategory } from '../api/cosmetics'
import { ApiError } from '../api/client'
import { analyzeSkinPhoto, type SkinAnalysis } from '../api/skin'
import SinglePhotoUpload from './SinglePhotoUpload'
import PageIntro, { ProgressSteps } from './PageIntro'
import MetricScores from './MetricScores'
import Icon from './Icon'
import CosmeticProductCard from './CosmeticProductCard'
import { cosmeticCategoryNames as categoryNames } from '../utils/cosmeticLabels'
import CosmeticEmptyState from './CosmeticEmptyState'
import { SectionJump } from './Shared'
import type { CosmeticSessionResult } from '../types/sessionResults'

const metrics: { code: MetricCode; name: string; direction: string }[] = [
  { code: 'moisture', name: '수분', direction: '높을수록 수분이 충분' },
  { code: 'redness', name: '홍조', direction: '높을수록 홍조가 강함' },
  { code: 'brightness', name: '밝기', direction: '높을수록 밝음' },
  { code: 'trouble', name: '트러블', direction: '높을수록 트러블이 많음' },
  { code: 'uniformity', name: '균일도', direction: '높을수록 피부 톤이 균일' },
]
const initialScores = { moisture: 25, redness: 75, brightness: 30, trouble: 75, uniformity: 30 }

export default function CosmeticPreview({ onAnalysis, onRecommendation }: {
  onAnalysis?: (value: SkinAnalysis) => void
  onRecommendation?: (value: CosmeticSessionResult) => void
}) {
  const [inputMode, setInputMode] = useState<'photo' | 'analysis' | 'development'>('photo')
  const [analysisJson, setAnalysisJson] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [manualMoisture, setManualMoisture] = useState('')
  const [analysis, setAnalysis] = useState<SkinAnalysis | null>(null)
  const [stage, setStage] = useState<'analysis' | 'recommendation' | null>(null)
  const cachedAnalysis = useRef<{ file: File; moisture: number | null; value: SkinAnalysis } | null>(null)
  const [scores, setScores] = useState(initialScores)
  const [hasMoisture, setHasMoisture] = useState(true)
  const [category, setCategory] = useState<ProductCategory | ''>('')
  const [avoidTriggers, setAvoidTriggers] = useState(true)
  const [excluded, setExcluded] = useState('')
  const [result, setResult] = useState<PreviewResponse | null>(null)
  const dailyCare = result?.recommendation_mode === 'daily_care'
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const activeRequest = useRef<AbortController | null>(null)
  const submittedRequest = useRef<PreviewRequest | null>(null)
  const moreRequest = useRef<AbortController | null>(null)
  const [loadingGroup, setLoadingGroup] = useState<string | null>(null)
  const [stale, setStale] = useState(false)
  const filterRequest = useRef<AbortController | null>(null)
  const [pendingCategory, setPendingCategory] = useState<ProductCategory | '' | null>(null)
  const [filterError, setFilterError] = useState('')
  const [failedCategory, setFailedCategory] = useState<ProductCategory | ''>('')
  useEffect(() => () => activeRequest.current?.abort(), [])
  useEffect(() => () => moreRequest.current?.abort(), [])
  useEffect(() => () => filterRequest.current?.abort(), [])
  // 필터와 추가 페이지도 완료된 결과만 상위 화면에 전달한다.
  useEffect(() => {
    if (result) onRecommendation?.({ response: result, inputMode, analysis: inputMode === 'photo' ? analysis : null, category: category || null })
  }, [result, inputMode, analysis, category, onRecommendation])

  function clearResult() {
    filterRequest.current?.abort(); filterRequest.current = null
    setPendingCategory(null); setFilterError(''); setCategory('')
    activeRequest.current?.abort()
    setLoading(false); setStage(null); setAnalysis(null)
    moreRequest.current?.abort()
    moreRequest.current = null
    submittedRequest.current = null
    setLoadingGroup(null); setStale(false); setResult(null); setError('')
  }

  async function loadMore(group: PreviewResponse['tie_groups'][number]) {
    if (!result || !submittedRequest.current || filterRequest.current || moreRequest.current || stale || group.next_offset === null) return
    const controller = new AbortController()
    moreRequest.current = controller
    setLoadingGroup(group.key); setError('')
    try {
      const page = await getCosmeticPreview({ ...submittedRequest.current,
        tie_group: group.key, tie_offset: group.next_offset, snapshot_token: result.snapshot_token,
      }, controller.signal)
      if (controller.signal.aborted) return
      setResult(previous => {
        if (!previous || previous.snapshot_token !== page.snapshot_token) return previous
        const ids = new Set(previous.recommendations.map(p => p.product_id))
        return { ...previous,
          recommendations: [...previous.recommendations, ...page.recommendations.filter(p => !ids.has(p.product_id))],
          tie_groups: previous.tie_groups.map(g => page.tie_groups.find(next => next.key === g.key) ?? g),
        }
      })
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : '추가 제품 조회에 실패했습니다.')
        if (err instanceof ApiError && err.status === 409) setStale(true)
      }
    } finally {
      if (moreRequest.current === controller) { moreRequest.current = null; setLoadingGroup(null) }
    }
  }

  async function filterCategory(next: ProductCategory | '') {
    if (!submittedRequest.current || loading) return
    filterRequest.current?.abort()
    moreRequest.current?.abort(); moreRequest.current = null; setLoadingGroup(null)
    const controller = new AbortController()
    filterRequest.current = controller
    setPendingCategory(next); setFilterError(''); setError('')
    // 확정된 분석 점수와 제외 조건을 재사용한다. 사진 분석은 다시 호출하지 않는다.
    const body: PreviewRequest = { ...submittedRequest.current, category: next || null }
    try {
      const data = await getCosmeticPreview(body, controller.signal)
      if (controller.signal.aborted) return
      submittedRequest.current = body
      setResult(data); setCategory(next); setStale(false)
    } catch (err) {
      if (!controller.signal.aborted) {
        setFailedCategory(next)
        setFilterError(`${next ? categoryNames[next] : '전체'} 조회 실패: ${err instanceof Error ? err.message : '다시 시도해 주세요.'}`)
      }
    } finally {
      if (filterRequest.current === controller) { filterRequest.current = null; setPendingCategory(null) }
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (loading) return
    clearResult()
    const controller = new AbortController()
    activeRequest.current = controller
    setLoading(true)
    try {
      let analysisScores: AnalysisMetricScore[] | undefined
      if (inputMode === 'photo') {
        if (!photo) throw new Error('정면 얼굴 사진을 선택해 주세요.')
        if (!['image/jpeg', 'image/png', 'image/webp'].includes(photo.type)) throw new Error('JPG, PNG, WEBP 사진을 사용해 주세요.')
        const moisture = manualMoisture.trim() === '' ? null : Number(manualMoisture)
        if (moisture !== null && (!Number.isInteger(moisture) || moisture < 0 || moisture > 100)) {
          throw new Error('수분은 0–100 정수로 입력하거나 미측정이면 비워 주세요.')
        }
        setStage('analysis')
        const cached = cachedAnalysis.current
        const value = cached?.file === photo && cached.moisture === moisture ? cached.value
          : await analyzeSkinPhoto(photo, moisture, controller.signal)
        if (controller.signal.aborted) return
        cachedAnalysis.current = { file: photo, moisture, value }
        setAnalysis(value)
        onAnalysis?.(value)
        analysisScores = value.scores
      }
      if (inputMode === 'analysis') {
        const parsed: unknown = JSON.parse(analysisJson)
        const rows = Array.isArray(parsed) ? parsed
          : parsed && typeof parsed === 'object' && 'scores' in parsed ? parsed.scores : undefined
        if (!Array.isArray(rows)) throw new Error('피부 분석 응답 또는 scores 배열을 입력해 주세요.')
        analysisScores = rows as AnalysisMetricScore[] // 서버에서 코드·범위·방향·라벨을 검증
      }
      const body: PreviewRequest = {
        score_semantics: inputMode === 'development' ? 'development_assumption' : 'photo_v1',
        scores: analysisScores ?? { ...scores, moisture: hasMoisture ? scores.moisture : null },
        category: null, avoid_redness_triggers: avoidTriggers,
        excluded_ingredients: excluded.split(',').map(s => s.trim()).filter(Boolean),
      }
      setStage('recommendation')
      const data = await getCosmeticPreview(body, controller.signal)
      if (!controller.signal.aborted) { submittedRequest.current = body; setResult(data) }
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : '추천 조회에 실패했습니다.')
    } finally {
      if (!controller.signal.aborted) { setLoading(false); setStage(null) }
    }
  }

  return (
    <section className="cosmetic-preview" aria-label="피부 분석 및 화장품 추천">
      <PageIntro eyebrow="SKIN & COSMETICS" title="피부 분석 · 화장품 추천">사진 속 피부 상태를 살펴보고, 분석 결과에 맞는 성분과 제품을 확인하세요.</PageIntro>
      <ProgressSteps labels={['사진 입력', '피부 분석', '성분 기반 추천']} current={result ? 3 : stage === 'recommendation' ? 2 : loading || analysis ? 1 : 0} />
      <form onSubmit={submit}>
        <fieldset disabled={loading} className="analysis-fieldset"><legend className="sr-only">피부 분석 입력</legend>
          <details className="developer-tools"><summary>연동 테스트 도구 {inputMode !== 'photo' && <span className="category-pill">테스트 모드</span>}</summary><label className="field">입력 방식<select value={inputMode} onChange={e => { clearResult(); setInputMode(e.target.value as 'photo' | 'analysis' | 'development') }}><option value="photo">사진 분석 후 자동 추천</option><option value="analysis">분석 결과 JSON · 연동 확인</option><option value="development">임시 점수 실험 · 개발용 가정</option></select></label></details>
          <div className="analysis-layout"><section className="form-card input-panel"><div className="card-heading"><span className="step-number">01</span><div><h3 id="skin-input-title" className="section-target" tabIndex={-1}>{inputMode === 'photo' ? '분석할 사진' : '분석 입력 확인'}</h3><p>{inputMode === 'photo' ? '정면에서 얼굴이 크게 나온 사진을 준비해 주세요.' : '실제 사진 분석과 구분되는 연동 확인 도구입니다.'}</p></div></div>
          {inputMode === 'photo' && <SinglePhotoUpload file={photo} disabled={loading} onChange={file => { clearResult(); setPhoto(file); cachedAnalysis.current = null }} />}
          {inputMode === 'analysis' && <label>분석 결과 JSON<textarea rows={10} value={analysisJson}
            onChange={e => { clearResult(); setAnalysisJson(e.target.value) }} placeholder={'{"scores": [...]}'}/>
            <small>전체 분석 응답 또는 scores 배열을 붙여넣으세요. 수분이 없으면 미측정으로 처리합니다.</small></label>}
          {inputMode === 'development' && <>
          <p>색소·모공 막힘 관련 고민을 가정한 규칙 실험입니다. 실제 사진 분석값에 그대로 적용하지 않습니다.</p>
          <div className="metric-grid">
            {metrics.map(m => (
              <div className="metric-input" key={m.code}>
                <div className="metric-label"><label htmlFor={`score-${m.code}`}>{m.name}</label><output>{m.code === 'moisture' && !hasMoisture ? '미측정' : scores[m.code]}</output></div>
                <input id={`score-${m.code}`} type="range" min="0" max="100" step="1" value={scores[m.code]}
                  disabled={m.code === 'moisture' && !hasMoisture}
                  onChange={e => { clearResult(); setScores(previous => ({ ...previous, [m.code]: Number(e.target.value) })) }} />
                <small>{m.direction}</small>
              </div>
            ))}
          </div>
          <label className="check-row"><input type="checkbox" checked={!hasMoisture} onChange={e => { clearResult(); setHasMoisture(!e.target.checked) }} />수분 미측정 — 나머지 4개 지표만 사용</label>
          </>}
          </section><section className="form-card options-panel"><div className="card-heading"><span className="step-number">02</span><div><h3>분석·추천 시작</h3><p>전체 기초 제품에서 먼저 추천해 드립니다.</p></div></div>
          {inputMode === 'photo' && <label className="field">수분 점수 <span className="optional-label">선택</span><input type="number" min={0} max={100} step={1} value={manualMoisture} onChange={e => { clearResult(); setManualMoisture(e.target.value) }} placeholder="0–100 · 미측정이면 비워두세요" /><small>센서 연결 전 측정값을 직접 입력합니다. 사진으로 수분을 추정하지 않습니다.</small></label>}
          <p className="recommendation-scope">보습제·세럼·토너를 함께 비교합니다.<br />제품 종류는 추천 결과에서 골라볼 수 있어요.</p>
          <details className="filter-details"><summary>성분 제외 조건</summary><label className="field">직접 제외할 성분<input type="text" value={excluded} maxLength={1500} onChange={e => { clearResult(); setExcluded(e.target.value) }} placeholder="예: 향료, 살리실릭애씨드" /><small>정확한 성분명을 쉼표로 구분해 입력하세요.</small></label><label className="check-row"><input type="checkbox" checked={avoidTriggers} onChange={e => { clearResult(); setAvoidTriggers(e.target.checked) }} />홍조가 ‘개선 필요’이면 프로젝트 주의 성분 제외</label></details>
          <button className="recommend-button" type="submit">{loading ? stage === 'analysis' ? '사진을 분석하고 있어요…' : '성분을 비교하고 있어요…' : inputMode === 'photo' ? '사진 분석하고 추천 확인하기' : '추천 제품 확인하기'}<Icon name="arrow" size={18} /></button>
          <p className="input-note">분석 점수를 저장하고 추천에 사용합니다. 이 업로드 경로는 원본 사진을 저장하지 않습니다.</p>
          </section></div>
        </fieldset>
      </form>
      {result && <div className="result-shortcut"><p role="status">추천 조회 완료 · {result.recommendations.length ? `${result.recommendations.length}개 제품을 확인할 수 있습니다.` : '제품이 없는 이유를 아래에서 확인해 주세요.'}</p><SectionJump targetId="results-title">결과로 이동</SectionJump></div>}
      {loading && <div className="request-progress" role="status"><span className="spinner" /><div><strong>{stage === 'analysis' ? '사진에서 피부 지표를 분석하고 있어요' : '분석 점수에 맞는 성분을 비교하고 있어요'}</strong><p>완료되면 아래에 결과가 표시됩니다. 메뉴를 이동해도 요청은 계속 진행됩니다.</p></div></div>}
      {analysis && <p className="saved-status"><Icon name="check" size={16} />피부 분석 #{analysis.id} 완료 · 실제 분석 점수를 추천에 전달했습니다.</p>}
      {analysis && !result && <MetricScores scores={analysis.scores} />}
      {error && <p role="alert" className="error-box">{error}</p>}
      <div aria-live="polite" aria-busy={loading || pendingCategory !== null}>
        {result && <section className="recommendation-results" aria-labelledby="results-title">
          <div className="results-heading"><h3 id="results-title" className="section-target" tabIndex={-1}>{dailyCare ? '일상 관리용 제품 제안' : '추천 결과'}</h3><span>{category ? categoryNames[category] : '전체'} · {result.recommendations.length}개 제품{!dailyCare && ` · 개선 대상 ${result.target_count}개 지표`}</span></div>
          <MetricScores scores={result.assessments.map(a => ({ metric_code: a.code, metric_name: a.name, score: a.score, category_name: a.category, higher_is_better: !['redness', 'trouble'].includes(a.code) }))} />
          {dailyCare ? <p className="result-explanation">{result.recommendation_notice}</p>
            : <p className="result-explanation">성분 매칭은 효과의 크기나 확률이 아닙니다. 개선 대상 {result.target_count}개 중 현재 규칙으로 매칭 가능한 지표는 {result.scorable_target_count}개입니다. 같은 지표에 여러 성분이 있어도 1점입니다.</p>}
          <details className="scope-details"><summary>추천 기준과 분석 한계</summary><p>{dailyCare ? '활성 보습 성분 규칙에 해당하는 성분이 포함된 제품을 고릅니다. 개선 점수는 부여하지 않으며, 기획·세트 의심 제품은 후순위로 표시합니다.' : '매칭 지표 수를 우선하며 기획·세트 의심 제품은 후순위로 표시합니다.'} 같은 정렬 조건 안의 표시 순서는 효과의 우열을 뜻하지 않습니다.</p>
          {dailyCare && <p>{result.ranking_basis}</p>}
          {result.deferred_metrics.some(code => ['brightness', 'uniformity', 'trouble'].includes(code)) && <p>사진의 밝기·명도 편차·붉은 반점으로는 색소침착이나 모공 막힘을 확인할 수 없어 관련 성분 매칭을 보류합니다.</p>}
          {result.deferred_metrics.includes('redness') && <p>홍조 가점은 근거 검토 중으로 보류합니다. 홍조는 조건부 배제에만 사용합니다.</p>}
          </details>
          <div className="result-category-panel">
            <p id="category-filter-label">제품 종류로 보기</p>
            <div className="category-filters" role="group" aria-labelledby="category-filter-label">
              {(['', 'moisturizer', 'serum', 'toner'] as const).map(value => <button type="button" key={value} aria-pressed={category === value}
                disabled={loading || (category === value && pendingCategory === null)} onClick={() => void filterCategory(value)}>{value ? categoryNames[value] : '전체'}</button>)}
            </div>
            {pendingCategory !== null ? <p role="status">{pendingCategory ? categoryNames[pendingCategory] : '전체'} 제품을 다시 조회하고 있어요. 완료 전까지 기존 결과를 표시합니다.</p>
              : <p>현재 {category ? categoryNames[category] : '전체 기초 제품'} 결과입니다. 제품 종류를 바꿔도 사진은 다시 분석하지 않습니다.</p>}
            {filterError && <div className="error-box" role="alert">{filterError}<br />기존 결과를 유지했습니다. <button type="button" className="secondary" disabled={pendingCategory !== null} onClick={() => void filterCategory(failedCategory)}>필터 다시 조회</button></div>}
          </div>
          {result.applied_exclusions.length > 0 && <p className="exclusion-summary">제외 적용: {result.applied_exclusions.join(', ')}</p>}
          {result.exclusion_details.length > 0 && <details><summary>자동 배제 근거와 적용 한계</summary>{result.exclusion_details.map(rule => <p key={rule.rule_code}><strong>{rule.ingredient}</strong> · {rule.rationale}<br />{rule.limitations}{' '}<a href={rule.evidence_url} target="_blank" rel="noopener noreferrer">근거 ↗</a></p>)}</details>}
          {!result.recommendations.length && <CosmeticEmptyState result={result} />}
          {result.tie_groups.map(group => <section className="tie-group" key={group.key} aria-label="같은 정렬 조건의 제품">
          <p className="tie-group-summary">같은 정렬 조건의 제품 {group.total}개 중 {result.recommendations.filter(p => p.ranking_group === group.key).length}개 표시</p>
          <ul className="product-list">{result.recommendations.filter(p => p.ranking_group === group.key).map(product =>
            <CosmeticProductCard key={product.product_id} product={product} dailyCare={dailyCare} scorableTargetCount={result.scorable_target_count} />)}</ul>
          {group.next_offset !== null && <button className="tie-more-button" type="button" disabled={pendingCategory !== null || loadingGroup !== null || stale}
            onClick={() => loadMore(group)}>{loadingGroup === group.key ? '제품을 불러오는 중…' : `같은 조건 제품 ${Math.min(5, group.total - group.next_offset)}개 더보기`}</button>}
          </section>)}
          <details className="method-details"><summary>추천 범위와 제한 확인</summary><p>전체 {result.stats.total_products.toLocaleString()}개 중 조건을 충족한 제품은 {result.stats.eligible_products.toLocaleString()}개입니다.</p><ul><li>종류 조건 제외: {result.stats.unsupported_category}</li><li>전성분 확인 미완료: {result.stats.incomplete_ingredients}</li><li>사용 방식 조건 제외: {result.stats.excluded_by_usage}</li><li>제외 성분 포함: {result.stats.excluded_by_ingredient}</li>{dailyCare ? <li>일상 관리 성분 기준 미충족: {result.stats.no_daily_care_ingredient ?? 0}</li> : <li>개선 지표 매칭 없음: {result.stats.no_matching_metric}</li>}</ul>{result.notices.filter(note => !note.startsWith('정렬 기준:') && !note.startsWith('제품명·종류로')).map(note => <p key={note}>{note}</p>)}<small>{result.rule_version}</small></details>
          <div className="result-return"><a className="button" href="#/results">이번 분석 결과 모아보기</a><SectionJump targetId="skin-input-title">입력·추천 조건으로 돌아가기</SectionJump></div>
        </section>}
      </div>
    </section>
  )
}
