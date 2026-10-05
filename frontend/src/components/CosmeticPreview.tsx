import { useEffect, useRef, useState, type FormEvent } from 'react'
import { getCosmeticPreview, type AnalysisMetricScore, type MetricCode, type PreviewRequest, type PreviewResponse, type ProductCategory } from '../api/cosmetics'
import { ApiError } from '../api/client'
import { analyzeSkinPhoto, type SkinAnalysis } from '../api/skin'
import CosmeticMatchDetails from './CosmeticMatchDetails'

const metrics: { code: MetricCode; name: string; direction: string }[] = [
  { code: 'moisture', name: '수분', direction: '높을수록 수분이 충분' },
  { code: 'redness', name: '홍조', direction: '높을수록 홍조가 강함' },
  { code: 'brightness', name: '밝기', direction: '높을수록 밝음' },
  { code: 'trouble', name: '트러블', direction: '높을수록 트러블이 많음' },
  { code: 'uniformity', name: '균일도', direction: '높을수록 피부 톤이 균일' },
]
const categoryNames = { moisturizer: '보습제', serum: '세럼', toner: '토너' }
const initialScores = { moisture: 25, redness: 75, brightness: 30, trouble: 75, uniformity: 30 }

function ProductImage({ url, name }: { url: string | null; name: string }) {
  const [failed, setFailed] = useState(false)
  return url && !failed
    ? <img className="product-image" src={url} alt={name} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
    : <div className="product-image image-placeholder" aria-label="제품 이미지 없음">BOA</div>
}

export default function CosmeticPreview() {
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
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const activeRequest = useRef<AbortController | null>(null)
  const submittedRequest = useRef<PreviewRequest | null>(null)
  const moreRequest = useRef<AbortController | null>(null)
  const [loadingGroup, setLoadingGroup] = useState<string | null>(null)
  const [stale, setStale] = useState(false)
  useEffect(() => () => activeRequest.current?.abort(), [])
  useEffect(() => () => moreRequest.current?.abort(), [])

  function clearResult() {
    activeRequest.current?.abort()
    setLoading(false); setStage(null); setAnalysis(null)
    moreRequest.current?.abort()
    moreRequest.current = null
    submittedRequest.current = null
    setLoadingGroup(null); setStale(false); setResult(null); setError('')
  }

  async function loadMore(group: PreviewResponse['tie_groups'][number]) {
    if (!result || !submittedRequest.current || moreRequest.current || stale || group.next_offset === null) return
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

  async function submit(event: FormEvent) {
    event.preventDefault()
    clearResult()
    const controller = new AbortController()
    activeRequest.current = controller
    setLoading(true)
    try {
      let analysisScores: AnalysisMetricScore[] | undefined
      if (inputMode === 'photo') {
        if (!photo) throw new Error('정면 얼굴 사진을 선택해 주세요.')
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
        category: category || null, avoid_redness_triggers: avoidTriggers,
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
    <section className="cosmetic-preview" aria-labelledby="preview-title">
      <header className="preview-heading">
        <span className="eyebrow">COSMETIC MATCH</span>
        <h2 id="preview-title">피부 고민에 맞는 성분을 찾아보세요</h2>
        <p>사진 분석 결과를 자동으로 전달해 성분 매칭 후보를 확인합니다. 사진 분석 점수는 저장되며 원본 사진은 이 경로에서 저장하지 않습니다.</p>
      </header>
      <form onSubmit={submit} onChange={clearResult}>
        <fieldset disabled={loading}>
          <legend>피부 분석 결과</legend>
          <label>입력 방식<select value={inputMode} onChange={e => setInputMode(e.target.value as 'photo' | 'analysis' | 'development')}>
            <option value="photo">사진 분석 후 자동 추천</option>
            <option value="analysis">분석 결과 JSON · 연동 확인</option>
            <option value="development">임시 점수 실험 · 개발용 가정</option>
          </select></label>
          {inputMode === 'photo' && <>
            <label>정면 얼굴 사진<input type="file" accept="image/jpeg,image/png,image/webp"
              onChange={e => { setPhoto(e.target.files?.[0] ?? null); cachedAnalysis.current = null }} /></label>
            <label>수분 점수 · 센서 연결 전 직접 입력<input type="number" min={0} max={100} step={1}
              value={manualMoisture} onChange={e => setManualMoisture(e.target.value)} placeholder="미측정이면 비워두세요" /></label>
            <p>정면에서 얼굴이 크게 나온 사진을 사용하세요. 수분은 사진으로 추정하지 않습니다.</p>
          </>}
          {inputMode === 'analysis' && <label>분석 결과 JSON<textarea rows={10} value={analysisJson}
            onChange={e => setAnalysisJson(e.target.value)} placeholder={'{"scores": [...]}'}/>
            <small>전체 분석 응답 또는 scores 배열을 붙여넣으세요. 수분이 없으면 미측정으로 처리합니다.</small></label>}
          {inputMode === 'development' && <>
          <p>색소·모공 막힘 관련 고민을 가정한 규칙 실험입니다. 실제 사진 분석값에 그대로 적용하지 않습니다.</p>
          <div className="metric-grid">
            {metrics.map(m => (
              <div className="metric-input" key={m.code}>
                <div className="metric-label"><label htmlFor={`score-${m.code}`}>{m.name}</label><output>{m.code === 'moisture' && !hasMoisture ? '미측정' : scores[m.code]}</output></div>
                <input id={`score-${m.code}`} type="range" min="0" max="100" step="1" value={scores[m.code]}
                  disabled={m.code === 'moisture' && !hasMoisture}
                  onChange={e => setScores(previous => ({ ...previous, [m.code]: Number(e.target.value) }))} />
                <small>{m.direction}</small>
              </div>
            ))}
          </div>
          <label className="check-row"><input type="checkbox" checked={!hasMoisture} onChange={e => setHasMoisture(!e.target.checked)} />수분 미측정 — 나머지 4개 지표만 사용</label>
          </>}
          <div className="filter-grid">
            <label>제품 종류<select value={category} onChange={e => setCategory(e.target.value as ProductCategory | '')}>
              <option value="">전체 기초 제품</option><option value="moisturizer">보습제</option><option value="serum">세럼</option><option value="toner">토너</option>
            </select></label>
            <label>직접 제외할 성분<input type="text" value={excluded} maxLength={1500} onChange={e => setExcluded(e.target.value)} placeholder="예: 향료, 살리실릭애씨드" /><small>DB에 있는 정확한 성분명 · 쉼표로 구분</small></label>
          </div>
          <label className="check-row"><input type="checkbox" checked={avoidTriggers} onChange={e => setAvoidTriggers(e.target.checked)} />홍조가 ‘개선 필요’이면 프로젝트 주의 성분 제외 · 적용 목록은 결과에서 확인</label>
          <p className="input-note">개발용 판정과 성분 함유 여부를 이용한 후보 추천입니다. 제품의 실제 효능이나 안전성을 판정하지 않습니다.</p>
          <button className="recommend-button" type="submit">{loading ? stage === 'analysis' ? '사진을 분석하고 있어요…' : '성분을 비교하고 있어요…' : inputMode === 'photo' ? '사진 분석하고 추천 확인하기' : '추천 제품 확인하기'}<span aria-hidden="true"> →</span></button>
        </fieldset>
      </form>
      {analysis && <p>피부 분석 #{analysis.id} 완료 · 추천에 실제 분석 점수를 사용합니다.</p>}
      {error && <p role="alert" className="error-box">{error}</p>}
      <div aria-live="polite" aria-busy={loading}>
        {result && <section className="recommendation-results" aria-labelledby="results-title">
          <div className="results-heading"><h3 id="results-title">추천 결과</h3><span>{result.recommendations.length}개 제품 · 개선 대상 {result.target_count}개 지표</span></div>
          <div className="assessment-list">{result.assessments.map(a => <span key={a.code} className={a.needs_improvement ? 'assessment needs-care' : 'assessment'}>{a.name} {a.score} · {a.category}</span>)}{result.missing_metrics.includes('moisture') && <span className="assessment">수분 미측정</span>}</div>
          <p className="result-explanation">성분 매칭은 효과의 크기나 확률이 아닙니다. 개선 대상 {result.target_count}개 중 현재 규칙으로 매칭 가능한 지표는 {result.scorable_target_count}개입니다. 같은 지표에 여러 성분이 있어도 1점입니다.</p>
          <p>매칭 지표 수를 우선하며 기획·세트 의심 제품은 후순위로 표시합니다. 같은 정렬 조건 안의 표시 순서는 효과의 우열을 뜻하지 않습니다.</p>
          {result.deferred_metrics.some(code => ['brightness', 'uniformity', 'trouble'].includes(code)) && <p>사진의 밝기·명도 편차·붉은 반점으로는 색소침착이나 모공 막힘을 확인할 수 없어 관련 성분 매칭을 보류합니다.</p>}
          {result.deferred_metrics.includes('redness') && <p>홍조 가점은 근거 검토 중으로 보류합니다. 홍조는 조건부 배제에만 사용합니다.</p>}
          {result.applied_exclusions.length > 0 && <p className="exclusion-summary">제외 적용: {result.applied_exclusions.join(', ')}</p>}
          {result.exclusion_details.length > 0 && <details><summary>자동 배제 근거와 적용 한계</summary>{result.exclusion_details.map(rule => <p key={rule.rule_code}><strong>{rule.ingredient}</strong> · {rule.rationale}<br />{rule.limitations}{' '}<a href={rule.evidence_url} target="_blank" rel="noopener noreferrer">근거 ↗</a></p>)}</details>}
          {result.empty_reason && <p className="empty-box">{result.empty_reason}</p>}
          {result.tie_groups.map(group => <section className="tie-group" key={group.key} aria-label="같은 정렬 조건의 제품">
          <p className="tie-group-summary">같은 정렬 조건의 제품 {group.total}개 중 {result.recommendations.filter(p => p.ranking_group === group.key).length}개 표시</p>
          <ul className="product-list">{result.recommendations.filter(p => p.ranking_group === group.key).map(product => <li className="product-card" key={product.product_id}>
            <ProductImage key={`${product.product_id}-${product.image_url}`} url={product.image_url} name={product.product_name} />
            <div className="product-content"><p className="brand-name">{product.brand_name} · {categoryNames[product.category]}</p><h4>{product.product_name}</h4>
              <p className="match-score">{product.match_count}<span> / {result.scorable_target_count}개 평가 가능 지표에 성분 매칭</span></p>
              <p className="recommendation-reason">성분표 매칭: {product.recommendation_reason}</p>
              <p>성분 함유 후보이며, 이 제품의 효과가 검증됐다는 뜻은 아닙니다.</p>
              {(product.shared_evidence_groups ?? []).map(group => <p key={group.evidence_url}>
                <strong>{group.metric_codes.map(code => metrics.find(m => m.code === code)?.name ?? code).join(' · ')}: 근거 공유</strong><br />{group.explanation}
              </p>)}
              <div className="product-actions">{product.source_url && <a href={product.source_url} target="_blank" rel="noopener noreferrer">제품 정보 보기 ↗</a>}{product.bundle_suspected && <span>기획·세트 가능성</span>}</div>
              <CosmeticMatchDetails matches={product.matches} />
            </div>
          </li>)}</ul>
          {group.next_offset !== null && <button className="tie-more-button" type="button" disabled={loadingGroup !== null || stale}
            onClick={() => loadMore(group)}>{loadingGroup === group.key ? '제품을 불러오는 중…' : `같은 조건 제품 ${Math.min(5, group.total - group.next_offset)}개 더보기`}</button>}
          </section>)}
          <details className="method-details"><summary>추천 범위와 제한 확인</summary><p>전체 {result.stats.total_products.toLocaleString()}개 중 조건을 충족한 제품은 {result.stats.eligible_products.toLocaleString()}개입니다.</p><ul><li>종류 조건 제외: {result.stats.unsupported_category}</li><li>전성분 확인 미완료: {result.stats.incomplete_ingredients}</li><li>사용 방식 조건 제외: {result.stats.excluded_by_usage}</li><li>제외 성분 포함: {result.stats.excluded_by_ingredient}</li><li>개선 지표 매칭 없음: {result.stats.no_matching_metric}</li></ul>{result.notices.filter(note => !note.startsWith('정렬 기준:') && !note.startsWith('제품명·종류로')).map(note => <p key={note}>{note}</p>)}<small>{result.rule_version}</small></details>
        </section>}
      </div>
    </section>
  )
}
