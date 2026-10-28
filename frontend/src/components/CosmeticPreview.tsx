import { scoreMaximum } from '../moisture/hydrationEstimate'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { getCosmeticPreview, type AnalysisMetricScore, type MetricCode, type PreviewRequest, type PreviewResponse, type ProductCategory } from '../api/cosmetics'
import { ApiError } from '../api/client'
import { analyzeSkinPhoto, type SkinAnalysis } from '../api/skin'
import { applyMoistureScore, moistureScoringMessage } from '../api/moisture'
import MoisturePanel from './MoisturePanel'
import { useMoistureResult } from '../hooks/useMoistureResult'
import { summarize } from '../moisture/autoMeasurement'
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

export default function CosmeticPreview({ onAnalysis, onRecommendation, active = true }: {
  active?: boolean
  onAnalysis?: (value: SkinAnalysis) => void
  onRecommendation?: (value: CosmeticSessionResult) => void
}) {
  const [inputMode, setInputMode] = useState<'photo' | 'analysis' | 'development'>('photo')
  const [analysisJson, setAnalysisJson] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [manualMoisture, setManualMoisture] = useState('')
  const [analysis, setAnalysis] = useState<SkinAnalysis | null>(null)
  const [measurementScope, setMeasurementScope] = useState(0)
  const moistureResult = useMoistureResult(analysis?.id ?? null, measurementScope, active)
  const linkedElsewhere = analysis && moistureResult.targetAnalysisId !== null && analysis.id !== moistureResult.targetAnalysisId
  const relativeMoisture = linkedElsewhere ? analysis.moisture_measurement ?? null : moistureResult.receipt ?? (moistureResult.draft ? summarize(moistureResult.draft) : analysis?.moisture_measurement ?? null)
  const [stage, setStage] = useState<'analysis' | 'recommendation' | null>(null)
  const cachedAnalysis = useRef<{ file: File; moisture: number | null; value: SkinAnalysis } | null>(null)
  const [scores, setScores] = useState(initialScores)
  const [hasMoisture, setHasMoisture] = useState(true)
  const [category, setCategory] = useState<ProductCategory | ''>('')
  const [avoidTriggers, setAvoidTriggers] = useState(true)
  const [avoidDryness,setAvoidDryness]=useState(false)
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

  useEffect(() => {
    const observation = moistureResult.receipt
    if (observation && analysis?.id === observation.analysis_id && analysis.moisture_measurement?.measurement_id !== observation.measurement_id) {
      const updated = { ...analysis, moisture_measurement: observation, scores: applyMoistureScore(analysis.scores, observation), moisture_source: observation.used_for_scoring ? 'sensor' as const : analysis.moisture_source }
      setAnalysis(updated); onAnalysis?.(updated)
      if (cachedAnalysis.current?.value.id === updated.id) cachedAnalysis.current.value = updated
    }
  }, [moistureResult.receipt, analysis, onAnalysis])

  const recommendationMeasurement = useRef<string | null>(null)
  useEffect(() => {
    const observed = analysis?.moisture_measurement
    if (inputMode !== 'photo' || loading || !result || !observed || !(observed?.used_for_scoring || ['cheek-auto-v2', 'skin-auto-v3','skin-auto-v4','skin-auto-v5','skin-auto-v6'].includes(observed?.algorithm_version ?? '')) || !submittedRequest.current) return
    const key = `${analysis!.id}:${observed.measurement_id}`
    if (recommendationMeasurement.current === key) return
    recommendationMeasurement.current = key
    const auxiliary = (observed!.recommendation_eligible || (observed!.used_for_scoring && observed!.estimation_version)) ? { moisture_analysis_id: analysis!.id, moisture_measurement_id: observed!.measurement_id } : { moisture_analysis_id: undefined, moisture_measurement_id: undefined }
    if (JSON.stringify(submittedRequest.current.scores) === JSON.stringify(analysis!.scores) && submittedRequest.current.moisture_measurement_id === auxiliary.moisture_measurement_id) return
    const body = { ...submittedRequest.current, ...auxiliary, scores: analysis!.scores }
    filterRequest.current?.abort(); filterRequest.current = null
    moreRequest.current?.abort(); moreRequest.current = null
    setPendingCategory(null); setLoadingGroup(null)
    const controller = new AbortController(); activeRequest.current = controller
    setLoading(true); setStage('recommendation'); setStale(true); setError('')
    void getCosmeticPreview(body, controller.signal).then(data => {
      if (controller.signal.aborted) return
      submittedRequest.current = body; setResult(data); setStale(false)
    }).catch(e => {
      if (!controller.signal.aborted) setError(`수분을 반영한 추천 갱신 실패. 표시된 제품은 이전 결과입니다. 분석 시작으로 재시도하세요. ${e instanceof Error ? e.message : ''}`)
    }).finally(() => { if (!controller.signal.aborted) { setLoading(false); setStage(null) } })
  }, [analysis, inputMode, loading, result])

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
      let auxiliary: Pick<PreviewRequest, 'moisture_analysis_id' | 'moisture_measurement_id'> = {}
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
        if (value.moisture_measurement?.recommendation_eligible || (value.moisture_measurement?.used_for_scoring && value.moisture_measurement?.estimation_version)) auxiliary = { moisture_analysis_id: value.id, moisture_measurement_id: value.moisture_measurement.measurement_id }
      }
      if (inputMode === 'analysis') {
        const parsed: unknown = JSON.parse(analysisJson)
        const rows = Array.isArray(parsed) ? parsed
          : parsed && typeof parsed === 'object' && 'scores' in parsed ? parsed.scores : undefined
        if (!Array.isArray(rows)) throw new Error('피부 분석 응답 또는 scores 배열을 입력해 주세요.')
        analysisScores = rows as AnalysisMetricScore[] // 서버에서 코드·범위·방향·라벨을 검증
      }
      const body: PreviewRequest = {
        ...auxiliary,
        score_semantics: inputMode === 'development' ? 'development_assumption' : 'photo_v1',
        scores: analysisScores ?? { ...scores, moisture: hasMoisture ? scores.moisture : null },
        category: null, avoid_redness_triggers: avoidTriggers, avoid_dryness_triggers:avoidDryness,
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
      <PageIntro eyebrow="BOA · SKIN & CARE" title="피부 분석 · 화장품 추천">정면 사진을 촬영하거나 선택하세요.</PageIntro>
      <ProgressSteps labels={['사진 입력', '피부 분석', '성분 기반 추천']} current={result ? 3 : stage === 'recommendation' ? 2 : loading || analysis ? 1 : 0} />
      {active && inputMode === 'photo' && <MoisturePanel key={measurementScope} analysisId={analysis?.id ?? null} onComplete={moistureResult.complete} completedResult={moistureResult.draft} onRestart={moistureResult.clear} />}
      {relativeMoisture && <div className="form-card" aria-label="자동 수분 측정 결과"><strong>최근 측정 기록 · {relativeMoisture.normalized_score != null ? `수분 ${relativeMoisture.normalized_score}/${scoreMaximum(relativeMoisture)}` : relativeMoisture.resolution_limited ? '신호 부족 · 수분값 확정 불가' : relativeMoisture.experimental_index != null ? `센서 반응 지수 ${relativeMoisture.experimental_index.toFixed(['skin-auto-v4','skin-auto-v5','skin-auto-v6'].includes(relativeMoisture.algorithm_version ?? '') ? 1 : 2)}%` : `이전 센서 변화율 ${relativeMoisture.relative_percent.toFixed(2)}%`}</strong><p role="status">{
        moistureResult.status === 'saved' ? `분석 #${moistureResult.receipt?.analysis_id}에 저장 완료 · ${moistureScoringMessage(moistureResult.receipt!)}` :
        moistureResult.status === 'saving' ? '현재 분석에 수분 결과 저장 중…' :
        moistureResult.status === 'error' ? '측정은 완료됐지만 서버 저장에 실패했습니다.' :
        '측정 완료 · 사진을 선택하고 분석을 시작하면 수분 항목에 자동 연결합니다.'}</p>
        {moistureResult.error && <p role="alert">{moistureResult.error} <button type="button" onClick={moistureResult.retry}>같은 결과 저장 재시도</button></p>}
      </div>}
      <form onSubmit={submit} className={inputMode === 'photo' && !!photo && !result ? 'has-floating-action' : undefined}>
        <fieldset disabled={loading} className="analysis-fieldset"><legend className="sr-only">피부 분석 입력</legend>

          <div className="analysis-layout"><section className="form-card input-panel"><div className="card-heading"><span className="step-number">01</span><div><h3 id="skin-input-title" className="section-target" tabIndex={-1}>{inputMode === 'photo' ? '분석할 사진' : '분석 입력 확인'}</h3><p>{inputMode === 'photo' ? '얼굴이 선명하게 보이는 정면 사진을 사용해 주세요.' : '실제 사진 분석과 구분되는 연동 확인 도구입니다.'}</p></div></div>
          {inputMode === 'photo' && <SinglePhotoUpload file={photo} disabled={loading} onChange={file => {
            // The first photo belongs to the pending measurement. Replacing or
            // deleting an existing photo starts a different measurement context.
            if (photo !== null) setMeasurementScope(x => x + 1)
            clearResult(); setPhoto(file); cachedAnalysis.current = null
          }} />}
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
          </section><section className="form-card options-panel"><div className="card-heading"><span className="step-number">02</span><div><h3>분석 및 추천</h3><p>분석 결과로 화장품을 조회합니다.</p></div></div>
          {inputMode === 'photo' && <details className="filter-details moisture-options"><summary>수분 측정값 추가 <small>선택{manualMoisture !== '' ? ` · ${manualMoisture}점` : ''}</small></summary><label className="field">직접 입력 · 기존 100점 척도<input type="number" min={0} max={100} step={1} value={manualMoisture} onChange={e => { setMeasurementScope(x => x + 1); clearResult(); setManualMoisture(e.target.value) }} placeholder="0–100" /><small>기존 0~100 수동 입력용입니다. 새 0~60 센서 지수는 측정기 연결로 자동 반영됩니다.</small></label></details>}
          <details className="filter-details"><summary>성분 제외 조건</summary><label className="field">직접 제외할 성분<input type="text" value={excluded} maxLength={1500} onChange={e => { clearResult(); setExcluded(e.target.value) }} placeholder="예: 향료, 살리실릭애씨드" /><small>정확한 성분명을 쉼표로 구분해 입력하세요.</small></label><label className="check-row"><input type="checkbox" checked={avoidTriggers} onChange={e => { clearResult(); setAvoidTriggers(e.target.checked) }} />홍조가 ‘개선 필요’이면 프로젝트 주의 성분 제외</label><label className="check-row"><input type="checkbox" checked={avoidDryness} onChange={e => { clearResult(); setAvoidDryness(e.target.checked) }} />수분 부족이면 향료·에탄올·변성알코올 제외</label></details>
          <div className={`analysis-actionbar${inputMode === 'photo' && !!photo && !result ? ' floating-action' : ''}`}>
            <div><strong>{loading ? stage === 'analysis' ? '사진 분석 중' : '추천 제품 조회 중' : photo ? '사진 입력 완료' : inputMode === 'photo' ? '사진을 입력하세요' : '추천 조회'}</strong><small>{loading ? '완료될 때까지 기다려 주세요.' : '원본 사진은 보관하지 않습니다.'}</small></div>
            <button className="recommend-button" type="submit" disabled={loading || (inputMode === 'photo' && !photo)}>{loading ? '처리 중…' : inputMode === 'photo' ? '분석 시작' : '추천 제품 확인하기'}<Icon name="arrow" size={18} /></button>
          </div>
          </section></div>
          <details className="developer-tools"><summary>연동 테스트 도구 {inputMode !== 'photo' && <span className="category-pill">테스트 모드</span>}</summary><label className="field">입력 방식<select value={inputMode} onChange={e => { setMeasurementScope(x => x + 1); clearResult(); setInputMode(e.target.value as 'photo' | 'analysis' | 'development') }}><option value="photo">사진 분석 후 자동 추천</option><option value="analysis">분석 결과 JSON · 연동 확인</option><option value="development">임시 점수 실험 · 개발용 가정</option></select></label></details>
        </fieldset>
      </form>
      {result && <div className="result-shortcut"><p role="status">추천 조회 완료 · {result.recommendations.length ? `${result.recommendations.length}개 제품을 확인할 수 있습니다.` : '제품이 없는 이유를 아래에서 확인해 주세요.'}</p><SectionJump targetId="results-title">결과로 이동</SectionJump></div>}
      {loading && <div className="request-progress" role="status"><span className="spinner" /><div><strong>{stage === 'analysis' ? '사진에서 피부 지표를 분석하고 있어요' : '분석 점수에 맞는 성분을 비교하고 있어요'}</strong><p>완료되면 아래에 결과가 표시됩니다. 메뉴를 이동해도 요청은 계속 진행됩니다.</p></div></div>}
      {analysis && <p className="saved-status"><Icon name="check" size={16} />피부 분석 #{analysis.id} 완료 · 실제 분석 점수를 추천에 전달했습니다.</p>}
      {analysis && !result && <MetricScores scores={analysis.scores} moisture={relativeMoisture} />}
      {error && <p role="alert" className="error-box">{error}</p>}
      <div aria-live="polite" aria-busy={loading || pendingCategory !== null}>
        {result && <section className="recommendation-results" aria-labelledby="results-title">
          <div className="results-heading"><h3 id="results-title" className="section-target" tabIndex={-1}>{dailyCare ? '일상 관리용 제품' : '화장품 추천 결과'}</h3><span>{category ? categoryNames[category] : '전체'} · {result.recommendations.length}개 제품{!dailyCare && ` · 개선 대상 ${result.target_count}개 지표`}</span></div>
          {result.hydration_policy && result.hydration_policy.strategy!==result.recommendation_notice && <p className="result-explanation">{result.hydration_policy.strategy}</p>}
          <p className="section-kicker">01 / 피부 지표</p><MetricScores moisture={relativeMoisture} scores={result.assessments.map(a => ({ metric_code: a.code, metric_name: a.name, score: a.score, category_name: a.category, higher_is_better: !['redness', 'trouble'].includes(a.code) }))} />
          {result.sensor_auxiliary && <p className="result-explanation">{result.sensor_auxiliary.applied ? '센서 상대 지수를 추천에 보조 반영했습니다. 기존 조건이 같은 후보 안에서만 보습 성분을 우선합니다.' : '별도 수분 점수가 있어 센서 지수를 중복 반영하지 않았습니다.'}</p>}
          {dailyCare ? <p className="result-explanation">{result.recommendation_notice}</p>
            : <p className="result-explanation">성분을 기준으로 조회한 제품입니다. 매칭 점수는 제품 효과를 뜻하지 않습니다.</p>}
          <div className="result-category-panel">
            <p className="section-kicker">02 / 추천 제품</p><p id="category-filter-label">제품 종류</p>
            <div className="category-filters" role="group" aria-labelledby="category-filter-label">
              {(['', 'moisturizer', 'serum', 'toner'] as const).map(value => <button type="button" key={value} aria-pressed={category === value}
                disabled={loading || (category === value && pendingCategory === null)} onClick={() => void filterCategory(value)}>{value ? categoryNames[value] : '전체'}</button>)}
            </div>
            {pendingCategory !== null ? <p role="status">{pendingCategory ? categoryNames[pendingCategory] : '전체'} 제품을 다시 조회하고 있어요. 완료 전까지 기존 결과를 표시합니다.</p>
              : null}
            {filterError && <div className="error-box" role="alert">{filterError}<br />기존 결과를 유지했습니다. <button type="button" className="secondary" disabled={pendingCategory !== null} onClick={() => void filterCategory(failedCategory)}>필터 다시 조회</button></div>}
          </div>
          {result.applied_exclusions.length > 0 && <p className="exclusion-summary">제외 적용: {result.applied_exclusions.join(', ')}</p>}
          {result.exclusion_details.length > 0 && <details><summary>자동 배제 근거와 적용 한계</summary>{result.exclusion_details.map(rule => <p key={rule.rule_code}><strong>{rule.ingredient}</strong> · {rule.rationale}<br />{rule.limitations}{' '}<a href={rule.evidence_url} target="_blank" rel="noopener noreferrer">근거 ↗</a></p>)}</details>}
          {!result.recommendations.length && <CosmeticEmptyState result={result} />}
          {result.tie_groups.map(group => <section className="tie-group" key={group.key} aria-label="같은 정렬 조건의 제품">
          <p className="tie-group-summary">같은 추천 조건의 제품 {group.total}개 중 {result.recommendations.filter(p => p.ranking_group === group.key).length}개 표시</p>
          <ul className="product-list">{result.recommendations.filter(p => p.ranking_group === group.key).map(product =>
            <CosmeticProductCard key={product.product_id} product={product} dailyCare={dailyCare} scorableTargetCount={result.scorable_target_count} />)}</ul>
          {group.next_offset !== null && <button className="tie-more-button" type="button" disabled={pendingCategory !== null || loadingGroup !== null || stale}
            onClick={() => loadMore(group)}>{loadingGroup === group.key ? '제품을 불러오는 중…' : `같은 조건 제품 ${Math.min(5, group.total - group.next_offset)}개 더보기`}</button>}
          </section>)}
          <details className="scope-details"><summary>추천 기준과 분석 한계</summary>{!dailyCare && <p>성분 매칭은 효과의 크기나 확률이 아닙니다. 개선 대상 {result.target_count}개 중 현재 규칙으로 매칭 가능한 지표는 {result.scorable_target_count}개입니다. 같은 지표에 여러 성분이 있어도 1점입니다.</p>}<p>{dailyCare ? '활성 보습 성분 규칙에 해당하는 성분이 포함된 제품을 고릅니다. 개선 점수는 부여하지 않으며, 기획·세트 의심 제품은 후순위로 표시합니다.' : '매칭 지표 수를 우선하며 기획·세트 의심 제품은 후순위로 표시합니다.'} 같은 정렬 조건 안의 표시 순서는 효과의 우열을 뜻하지 않습니다.</p>
          <p>{result.ranking_basis}</p>
          {result.deferred_metrics.some(code => ['brightness', 'uniformity', 'trouble'].includes(code)) && <p>사진의 밝기·명도 편차·붉은 반점으로는 색소침착이나 모공 막힘을 확인할 수 없어 관련 성분 매칭을 보류합니다.</p>}
          {result.deferred_metrics.includes('redness') && <p>홍조 가점은 근거 검토 중으로 보류합니다. 홍조는 조건부 배제에만 사용합니다.</p>}
          </details>
          <details className="method-details"><summary>추천 범위와 제한 확인</summary><p>전체 {result.stats.total_products.toLocaleString()}개 중 조건을 충족한 제품은 {result.stats.eligible_products.toLocaleString()}개입니다.</p><ul><li>종류 조건 제외: {result.stats.unsupported_category}</li><li>전성분 확인 미완료: {result.stats.incomplete_ingredients}</li><li>사용 방식 조건 제외: {result.stats.excluded_by_usage}</li><li>제외 성분 포함: {result.stats.excluded_by_ingredient}</li>{dailyCare ? <li>일상 관리 성분 기준 미충족: {result.stats.no_daily_care_ingredient ?? 0}</li> : <li>개선 지표 매칭 없음: {result.stats.no_matching_metric}</li>}</ul>{result.notices.filter(note => !note.startsWith('정렬 기준:') && !note.startsWith('제품명·종류로')).map(note => <p key={note}>{note}</p>)}<small>{result.rule_version}</small></details>
          <div className="result-return"><a className="button" href="#/results">이번 분석 결과 모아보기</a><SectionJump targetId="skin-input-title">입력·추천 조건으로 돌아가기</SectionJump></div>
        </section>}
      </div>
    </section>
  )
}
