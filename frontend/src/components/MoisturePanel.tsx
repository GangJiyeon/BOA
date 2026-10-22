import { useEffect, useRef, useState } from 'react'
import { useMoisture } from '../hooks/useMoisture'
import { validateMoisture } from '../api/moisture'
const labels = { disconnected: '연결 안 됨', connecting: '장치 연결 중', connected: '연결됨', error: '연결 실패' }
export default function MoisturePanel({ analysisId }: { analysisId: number | null }) {
  const sensor = useMoisture()
  const [receipt, setReceipt] = useState('')
  const [sending, setSending] = useState(false)
  const [now, setNow] = useState(() => Date.now())
  const request = useRef<AbortController | null>(null)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => { clearInterval(timer); request.current?.abort() }
  }, [])
  useEffect(() => { request.current?.abort(); setSending(false); setReceipt('') }, [analysisId, sensor.state])
  const value = sensor.measurement
  const stale = value !== null && now - Date.parse(value.received_at) > 3000
  async function send() {
    if (!value || stale || sending || sensor.state !== 'connected') return
    const controller = new AbortController(); request.current = controller
    setSending(true); setReceipt('')
    try {
      const result = await validateMoisture(value, analysisId, controller.signal)
      if (!controller.signal.aborted) setReceipt(`서버 검증 완료 · ${result.analysis_id ? `분석 #${result.analysis_id} 연결 확인` : '분석 전 수신 확인'} · DB 저장/점수 반영 없음`)
    } catch (e) { if (!controller.signal.aborted) setReceipt(e instanceof Error ? e.message : '전송 실패') }
    finally { if (!controller.signal.aborted) setSending(false) }
  }
  return <section className="form-card" aria-label="수분 측정기">
    <h3>수분 측정기 <small>· 보정 전 원시값</small></h3>
    <p role="status">{labels[sensor.state]}{stale ? ' · 수신 지연 (3초 이상)' : ''}</p>
    <div className="button-row">
      <button type="button" disabled={sensor.state === 'connecting' || sensor.state === 'connected'} onClick={() => sensor.connect()}>측정기 연결 / 재연결</button>{' '}
      <button type="button" className="secondary" disabled={sensor.state === 'disconnected'} onClick={sensor.disconnect}>측정 종료</button>{' '}
      {import.meta.env.DEV && import.meta.env.VITE_MOISTURE_MOCK === 'true' && <button type="button" className="secondary" disabled={sensor.state === 'connecting' || sensor.state === 'connected'} onClick={() => sensor.connect(true)}>개발용 Mock 시작</button>}
    </div>
    {value ? <p><strong>{value.source === 'ble_sensor' ? '센서 원시값' : '가상 데이터 · 실제 측정 아님'}: {value.raw_value ?? '유효값 없음'}</strong> {value.unit}<br />
      상태: {value.status} · 수신: {new Date(value.received_at).toLocaleTimeString()} · 순번 {value.sequence}</p> : <p>수신한 측정값이 없습니다.</p>}
    <p>보정 전 데이터이므로 수분 %, 건성/지성 판정 및 제품 추천 점수에 사용하지 않습니다. 화면을 이동하면 측정을 종료합니다.</p>
    {sensor.error && <p role="alert" className="error-box">{sensor.error}</p>}
    <button type="button" className="secondary" disabled={!value || stale || sending || sensor.state !== 'connected'} onClick={() => void send()}>{sending ? '전송 중…' : '현재 측정값 서버 전달 확인'}</button>
    <p role="status">{receipt}</p>
  </section>
}
