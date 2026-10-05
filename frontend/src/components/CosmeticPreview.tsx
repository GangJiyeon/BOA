import { useEffect, useRef, useState, type FormEvent } from 'react'
import { getCosmeticPreview, type MetricCode, type PreviewRequest, type PreviewResponse, type ProductCategory } from '../api/cosmetics'
import { ApiError } from '../api/client'
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
    activeRequest.current?.abort()
    const controller = new AbortController()
    activeRequest.current = controller
    setLoading(true)
    clearResult()
    try {
      const body: PreviewRequest = {
        scores: { ...scores, moisture: hasMoisture ? scores.moisture : null },
        category: category || null, avoid_redness_triggers: avoidTriggers,
        excluded_ingredients: excluded.split(',').map(s => s.trim()).filter(Boolean),
      }
      const data = await getCosmeticPreview(body, controller.signal)
      if (!controller.signal.aborted) { submittedRequest.current = body; setResult(data) }
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : '추천 조회에 실패했습니다.')
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }

  return (
    <section className="cosmetic-preview" aria-labelledby="preview-title">
      <header className="preview-heading">
        <span className="eyebrow">COSMETIC MATCH</span>
        <h2 id="preview-title">피부 고민에 맞는 성분을 찾아보세요</h2>
        <p>임시 피부 점수를 입력해 실제 제품 DB에서 추천을 확인합니다. 입력값과 결과는 저장하지 않습니다.</p>
      </header>
      <form onSubmit={submit} onChange={clearResult}>
        <fieldset disabled={loading}>
          <legend>피부 점수 입력 <span>0–100 · 개발용 예시값</span></legend>
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
          <div className="filter-grid">
            <label>제품 종류<select value={category} onChange={e => setCategory(e.target.value as ProductCategory | '')}>
              <option value="">전체 기초 제품</option><option value="moisturizer">보습제</option><option value="serum">세럼</option><option value="toner">토너</option>
            </select></label>
            <label>직접 제외할 성분<input type="text" value={excluded} maxLength={1500} onChange={e => setExcluded(e.target.value)} placeholder="예: 향료, 살리실릭애씨드" /><small>DB에 있는 정확한 성분명 · 쉼표로 구분</small></label>
          </div>
          <label className="check-row"><input type="checkbox" checked={avoidTriggers} onChange={e => setAvoidTriggers(e.target.checked)} />홍조가 ‘개선 필요’이면 프로젝트 주의 성분 제외 · 적용 목록은 결과에서 확인</label>
          <p className="input-note">개발용 판정과 성분 함유 여부를 이용한 후보 추천입니다. 제품의 실제 효능이나 안전성을 판정하지 않습니다.</p>
          <button className="recommend-button" type="submit">{loading ? '성분을 비교하고 있어요…' : '추천 제품 확인하기'}<span aria-hidden="true"> →</span></button>
        </fieldset>
      </form>
      {error && <p role="alert" className="error-box">{error}</p>}
      <div aria-live="polite" aria-busy={loading}>
        {result && <section className="recommendation-results" aria-labelledby="results-title">
          <div className="results-heading"><h3 id="results-title">추천 결과</h3><span>{result.recommendations.length}개 제품 · 개선 대상 {result.target_count}개 지표</span></div>
          <div className="assessment-list">{result.assessments.map(a => <span key={a.code} className={a.needs_improvement ? 'assessment needs-care' : 'assessment'}>{a.name} {a.score} · {a.category}</span>)}{result.missing_metrics.includes('moisture') && <span className="assessment">수분 미측정</span>}</div>
          <p className="result-explanation">성분 매칭은 효과의 크기나 확률이 아닙니다. 개선 대상 {result.target_count}개 중 현재 규칙으로 매칭 가능한 지표는 {result.scorable_target_count}개입니다. 같은 지표에 여러 성분이 있어도 1점입니다.</p>
          <p>매칭 지표 수를 우선하며 기획·세트 의심 제품은 후순위로 표시합니다. 같은 정렬 조건 안의 표시 순서는 효과의 우열을 뜻하지 않습니다.</p>
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
