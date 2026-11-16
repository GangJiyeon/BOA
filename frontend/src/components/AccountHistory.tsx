import { useEffect, useState } from 'react'
import { getAnalysisHistory, type AnalysisHistory, type AnalysisHistoryItem, type AnalysisHistoryKind } from '../api/account'
import { getSkinAnalysis, type SkinAnalysis } from '../api/skin'
import { getHairResult, type HairResult } from '../api/hair'
import { useTask } from '../hooks/useTask'
import { SkinSummary, TaskStatus } from './Shared'
import { HairResults } from '../pages/HairPage'

const names = { skin: '피부 분석', hair: '헤어 추천' }
const dateFormat = new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Seoul' })
function dateLabel(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '날짜 정보 없음' : dateFormat.format(date)
}
type Detail = { kind: 'skin'; value: SkinAnalysis } | { kind: 'hair'; value: HairResult }

export default function AccountHistory({ disabled = false }: { disabled?: boolean }) {
  const [kind, setKind] = useState<AnalysisHistoryKind>('all')
  const [offset, setOffset] = useState(0)
  const [revision, setRevision] = useState(0)
  const [page, setPage] = useState<AnalysisHistory | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [detail, setDetail] = useState<Detail | null>(null)
  const [selected, setSelected] = useState<AnalysisHistoryItem | null>(null)
  const task = useTask()

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(''); setPage(null)
    getAnalysisHistory(kind, offset, controller.signal).then(value => {
      if (!controller.signal.aborted) setPage(value)
    }).catch((err: unknown) => {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : '분석 이력을 불러오지 못했습니다.')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [kind, offset, revision])

  function clearDetail() { task.reset(); setDetail(null); setSelected(null) }
  function open(item: AnalysisHistoryItem) {
    if (disabled || task.busy) return
    setDetail(null); setSelected(item)
    void task.run(async signal => {
      if (item.kind === 'skin') {
        const value = await getSkinAnalysis(item.id, signal)
        if (!signal.aborted) setDetail({ kind: 'skin', value })
      } else {
        const value = await getHairResult(item.id, signal)
        if (!signal.aborted) setDetail({ kind: 'hair', value })
      }
    })
  }

  return <section className="account-history" aria-labelledby="account-history-title">
    <div className="results-heading"><h4 id="account-history-title">내 분석 이력</h4><button type="button" className="secondary" disabled={disabled || loading} onClick={() => { clearDetail(); setOffset(0); setRevision(value => value + 1) }}>이력 새로고침</button></div>
    <p className="input-note">계정에 저장된 피부 분석과 헤어 추천 기록입니다. 최신순으로 표시하며 날짜는 한국 시간 기준입니다.</p>
    <label className="field">이력 종류<select value={kind} disabled={disabled} onChange={event => { clearDetail(); setKind(event.target.value as AnalysisHistoryKind); setOffset(0) }}><option value="all">전체</option><option value="skin">피부 분석</option><option value="hair">헤어 추천</option></select></label>
    {loading && <p role="status">분석 이력을 불러오는 중입니다.</p>}
    {error && <p role="alert" className="error-box">{error} <button type="button" disabled={disabled} onClick={() => setRevision(value => value + 1)}>이력 다시 조회</button></p>}
    {page && <>
      {!page.items.length ? <p className="empty-box">{offset ? '이 페이지에 남아 있는 기록이 없습니다. 이전 페이지나 새로고침을 이용해 주세요.' : '아직 저장된 분석 이력이 없습니다.'}</p> : <ul className="account-history-list">{page.items.map(item => <li key={`${item.kind}:${item.id}`}>
        <div><strong>{names[item.kind]} · #{item.id}</strong><br /><time dateTime={item.created_at}>{dateLabel(item.created_at)}</time></div>
        <button type="button" className="secondary" aria-label={`${names[item.kind]} ${item.id}번 결과 보기`} disabled={disabled || task.busy} onClick={() => open(item)}>결과 보기</button>
      </li>)}</ul>}
      <nav className="actions" aria-label="분석 이력 페이지">
        <button type="button" className="secondary" disabled={disabled || offset === 0} onClick={() => { clearDetail(); setOffset(Math.max(0, offset - 20)) }}>이전 기록</button>
        <span>{Math.floor(offset / 20) + 1}페이지</span>
        <button type="button" className="secondary" disabled={disabled || !page.has_more} onClick={() => { clearDetail(); setOffset(offset + 20) }}>다음 기록</button>
      </nav>
    </>}
    {selected && <section className="account-history-detail" aria-label="선택한 분석 결과">
      <div className="results-heading"><h5>{names[selected.kind]} · #{selected.id}</h5><button type="button" className="secondary" disabled={disabled} onClick={clearDetail}>결과 닫기</button></div>
      <TaskStatus busy={task.busy} error={task.error} />
      {task.error && <button type="button" disabled={disabled || task.busy} onClick={() => open(selected)}>결과 다시 조회</button>}
      {detail?.kind === 'skin' && <SkinSummary analysis={detail.value} />}
      {detail?.kind === 'hair' && <HairResults result={detail.value} />}
    </section>}
  </section>
}
