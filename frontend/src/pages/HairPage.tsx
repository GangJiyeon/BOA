import { useEffect, useRef, useState, type FormEvent } from 'react'
import { analyzeFace, getHairStyles, recommendHair, type FaceAnalysis, type HairResult, type HairStyle, type Sex } from '../api/hair'
import { SectionJump, TaskStatus } from '../components/Shared'
import PhotoUpload from '../components/PhotoUpload'
import PageIntro, { ProgressSteps } from '../components/PageIntro'
import Icon from '../components/Icon'
import { useTask } from '../hooks/useTask'
import type { HairSessionResult } from '../types/sessionResults'

export default function HairPage({ onResult }: { onResult: (value: HairSessionResult) => void }) {
  const task = useTask()
  const [styles, setStyles] = useState<HairStyle[]>([])
  const [catalogError, setCatalogError] = useState('')
  const [catalogLoaded, setCatalogLoaded] = useState(false)
  const [revision, setRevision] = useState(0)
  const [photos, setPhotos] = useState<File[]>([])
  const [sex, setSex] = useState<Sex>('female')
  const [length, setLength] = useState('')
  const [texture, setTexture] = useState('')
  const [analysis, setAnalysis] = useState<FaceAnalysis | null>(null)
  const cache = useRef<FaceAnalysis | null>(null)
  const [result, setResult] = useState<HairResult | null>(null)
  const [stage, setStage] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    getHairStyles(controller.signal).then(value => { if (!controller.signal.aborted) { setStyles(value); setCatalogLoaded(true) } }).catch((err: Error) => { if (!controller.signal.aborted) setCatalogError(err.message) })
    return () => controller.abort()
  }, [revision])
  function clear(newPhoto: boolean) { task.reset(); setAnalysis(null); setResult(null); setStage(''); if (newPhoto) cache.current = null }
  function submit(event: FormEvent) {
    event.preventDefault(); if (task.busy) return; setResult(null)
    void task.run(async signal => {
      if (![1, 3].includes(photos.length)) throw new Error('얼굴 사진은 1장 또는 3장을 선택해 주세요.')
      if (photos.some(file => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type))) throw new Error('JPG, PNG, WEBP 사진을 사용해 주세요.')
      setStage(cache.current ? '헤어 추천 중' : '얼굴형 분석 중')
      const face = cache.current ?? await analyzeFace(photos, sex, signal)
      if (signal.aborted) return
      cache.current = face; setAnalysis(face); setStage('헤어 추천 중')
      const value = await recommendHair(face.id, length, texture, signal)
      if (!signal.aborted) { setResult(value); onResult({ result: value, analysis: face }); setStage('완료') }
    })
  }
  const available = styles.filter(style => style.sex === sex || style.sex === 'unisex')
  const lengths = [...new Set(available.map(style => style.length))]
  const textures = [...new Set(available.map(style => style.texture))]
  const labels: Record<string, string> = { short: '짧게', medium: '중간', long: '길게', straight: '직모', wavy: '웨이브', curly: '컬' }
  return <section><PageIntro eyebrow="FACE & HAIR" title="얼굴형 · 헤어 추천">얼굴형을 분석하고 원하는 길이와 질감으로 나에게 어울리는 스타일을 찾아보세요.</PageIntro><ProgressSteps labels={['사진 입력', '얼굴형 분석', '스타일 추천']} current={result ? 3 : stage === '헤어 추천 중' ? 2 : task.busy || analysis ? 1 : 0} />
    {catalogError && <p role="alert" className="error-box">헤어 목록 조회 실패: {catalogError} <button onClick={() => { setCatalogError(''); setCatalogLoaded(false); setRevision(n => n + 1) }}>다시 조회</button></p>}
    {catalogLoaded && !styles.length && <p className="empty-box">헤어 스타일 데이터가 없습니다. 백엔드에서 카탈로그를 가져온 뒤 다시 조회해 주세요. <button onClick={() => { setCatalogError(''); setCatalogLoaded(false); setRevision(n => n + 1) }}>다시 조회</button></p>}
    <form onSubmit={submit}><fieldset className="analysis-fieldset" disabled={task.busy}><legend className="sr-only">헤어 분석 입력</legend><div className="analysis-layout">
      <section className="form-card input-panel"><div className="card-heading"><span className="step-number">01</span><div><h3 id="hair-input-title" className="section-target" tabIndex={-1}>얼굴형을 확인할 사진</h3><p>빠른 분석은 정면 1장, 여러 각도는 3장으로.</p></div></div><PhotoUpload files={photos} multiple disabled={task.busy} onChange={files => { clear(true); setPhotos(files) }} /></section>
      <section className="form-card options-panel"><div className="card-heading"><span className="step-number">02</span><div><h3>원하는 스타일</h3><p>선호 없음으로 얼굴형 중심 추천도 가능해요.</p></div></div>
      <label className="field">스타일 구분<select value={sex} onChange={e => { clear(true); setSex(e.target.value as Sex); setLength(''); setTexture('') }}><option value="female">여성 스타일</option><option value="male">남성 스타일</option><option value="unisex">공용 스타일</option></select></label>
      <label className="field">선호 길이<select value={length} onChange={e => { clear(false); setLength(e.target.value) }}><option value="">선호 없음</option>{lengths.map(value => <option key={value} value={value}>{labels[value] ?? value}</option>)}</select></label>
      <label className="field">선호 질감<select value={texture} onChange={e => { clear(false); setTexture(e.target.value) }}><option value="">선호 없음</option>{textures.map(value => <option key={value} value={value}>{labels[value] ?? value}</option>)}</select></label>
      {!catalogLoaded && !catalogError && <p role="status">스타일 선택지를 불러오고 있어요…</p>}
      {catalogLoaded && styles.length > 0 && !available.length && <p role="status" className="input-note">선택한 스타일 구분에 등록된 헤어가 없습니다. 다른 구분을 선택해 주세요.</p>}
      <button className="recommend-button" type="submit" disabled={!catalogLoaded || !available.length || photos.length === 2}>{task.busy ? '분석하고 있어요…' : '얼굴 분석하고 헤어 추천받기'}<Icon name="arrow" size={18} /></button><p className="input-note">길이·질감은 현재 등록된 헤어 카탈로그에서 선택합니다.</p>
      </section></div></fieldset></form>
    {result && <div className="result-shortcut"><p role="status">헤어 추천 완료 · {result.recommendations.length}개 스타일</p><SectionJump targetId="hair-result-title">결과로 이동</SectionJump></div>}
    {task.busy && <div className="request-progress" role="status"><span className="spinner" /><div><strong>{stage}…</strong><p>완료되면 얼굴형과 추천 스타일을 함께 보여드릴게요.</p></div></div>}<TaskStatus busy={false} error={task.error} />
    {analysis && <div className="face-result"><span className="feature-icon"><Icon name="hair" size={28} /></span><div><span className="eyebrow">YOUR FACE SHAPE</span><h3>{analysis.face_shape}</h3><p>얼굴 분석 #{analysis.id}{analysis.top2 && ` · 차순위 ${analysis.top2}`}</p></div><span className="category-pill">분석 완료</span></div>}
    {result && <><HairResults result={result} titleId="hair-result-title" /><div className="result-return"><a className="button" href="#/results">이번 분석 결과 모아보기</a><SectionJump targetId="hair-input-title">사진·스타일 조건으로 돌아가기</SectionJump></div></>}
  </section>
}
export function HairResults({ result, titleId }: { result: HairResult; titleId?: string }) {
  return <section className="hair-results"><div className="results-heading"><h3 id={titleId} className="section-target" tabIndex={-1}>헤어 추천 #{result.run_id}</h3><span>{result.recommendations.length}개 스타일</span></div>{!result.recommendations.length && <p className="empty-box">현재 조건에 맞는 스타일이 없습니다. 선호 조건이나 카탈로그를 확인해 주세요.</p>}
    <ul className="hair-grid">{result.recommendations.map(style => <li className="hair-card" key={style.style_id}>
      <HairImage key={style.image} url={style.image} name={style.name} /><div className="hair-card-body"><span className="hair-rank">추천 {style.rank}</span><h4>{style.name}</h4><p className="hair-score">매칭 점수 <strong>{style.score.toFixed(2)}</strong></p>{style.note && <details><summary>스타일 안내</summary><p>{style.note}</p></details>}</div>
    </li>)}</ul>
  </section>
}
function HairImage({ url, name }: { url: string | null; name: string }) {
  const [failed, setFailed] = useState(false)
  // 카탈로그에는 /static/hair/... 경로가 저장된다.
  return url && (url.startsWith('/static/') || /^https?:\/\//.test(url)) && !failed
    ? <img className="hair-image" src={url} alt={name} loading="lazy" onError={() => setFailed(true)} />
    : <div className="hair-image image-placeholder">사진 준비 중</div>
}
