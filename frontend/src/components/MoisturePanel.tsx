import { scoreMaximum, levelDescription } from '../moisture/hydrationEstimate'
import { useEffect, useRef, useState } from 'react'
import { useMoisture } from '../hooks/useMoisture'
import { useAutoMoisture } from '../hooks/useAutoMoisture'
import { summarize, type CompletedMeasurement } from '../moisture/autoMeasurement'
import './MoisturePanel.css'
const labels = { disconnected: '연결 안 됨', connecting: '연결 중', connected: '연결됨', error: '연결 실패' }
export default function MoisturePanel({analysisId,onComplete,completedResult=null,onRestart}:{
  analysisId:number|null;onComplete:(r:CompletedMeasurement)=>void;completedResult?:CompletedMeasurement|null;onRestart?:()=>void
}) {
  const sensor=useMoisture(),epoch=useRef(0)
  const [error,setError]=useState(''),[pending,setPending]=useState(false)
  const automatic=useAutoMoisture(sensor.measurement,sensor.state==='connected',analysisId,onComplete,completedResult)
  useEffect(()=>{setPending(false);setError('');++epoch.current},[sensor.state,analysisId])
  useEffect(()=>{if(sensor.measurement?.reference?.calibration==='calibrating')setPending(false)},[sensor.measurement])
  useEffect(()=>{if(!pending)return;const id=setTimeout(()=>{setPending(false);setError('보정 응답이 없습니다. 연결을 확인해 주세요.')},6000);return()=>clearTimeout(id)},[pending])
  const ref=sensor.measurement?.reference,summary=automatic.result?summarize(automatic.result):null
  const busy=pending||automatic.view.phase==='calibrating',retry=automatic.result||automatic.view.phase==='rejected'
  async function calibrate(){
    const current=++epoch.current;onRestart?.();automatic.reset();setPending(true);setError('')
    try{await sensor.calibrate()}catch(e){if(epoch.current===current){setPending(false);setError(e instanceof Error?e.message:'보정 실패')}}
  }
  function download(name:string,data:unknown){
    const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}))
    const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  return <section className="form-card moisture-panel" aria-label="수분 측정기">
    <div className="moisture-heading"><h3>피부 수분 측정</h3><span>{labels[sensor.state]}</span></div>
    <p>센서를 피부에 가볍게 대고 3초간 유지하세요.</p>
    <div className="button-row">
      <button type="button" disabled={sensor.state==='connected'||sensor.state==='connecting'} onClick={()=>sensor.connect()}>측정기 연결</button>
      <button type="button" className="secondary" disabled={sensor.state!=='connected'||busy||![4,5].includes(sensor.measurement?.protocol_version??0)||!sensor.measurement?.sensor_profile||automatic.view.phase==='collecting'} onClick={()=>void calibrate()}>{retry?'다시 측정':busy?'보정 중…':'기준값 보정'}</button>
      <button type="button" className="secondary" disabled={sensor.state==='disconnected'} onClick={sensor.disconnect}>연결 해제</button>
    </div>
    <div className="moisture-reading">
      <span>수분 지수</span><strong>{summary?.normalized_score??'—'}<small>{summary?.normalized_score!=null?`/ ${scoreMaximum(summary!)}`:''}</small></strong>
      <p role="status">{automatic.view.message}</p>
      {automatic.view.phase==='collecting'&&<progress max={1} value={automatic.view.progress} aria-label="3초 측정 진행률"/>}
    </div>
    {summary?.normalized_score!=null&&<p className="moisture-captured">측정 완료 · 수분 {summary.normalized_score}/{scoreMaximum(summary)}{summary.estimated_state_label?` · ${levelDescription(summary)}`:''}</p>}
    <small className="moisture-note">{summary&&!summary.estimated_state?'이전 센서 점수 · 피부 상태 판정 아님':'피부 수분 상태 · 실험 추정'}</small>
    {(error||sensor.error)&&<p role="alert" className="error-box">{error||sensor.error}</p>}
    <details className="moisture-details"><summary>측정 상세</summary>
      {summary&&<p>측정 시간 3초 · 정상 {summary.sample_count}개 · 제외 {summary.discarded_sample_count??0}개 (경고 {summary.warning_sample_count??0}개)<br/>수분 지수 {summary.normalized_score}/{scoreMaximum(summary)} · 마지막 1초 중앙값 사용<br/>기준값 {automatic.result!.baseline} · 대표값 {summary.terminal_count}<br/>척도: {summary.normalization_version} · {summary.moisture_level?`${summary.moisture_level}/6단계`: '이전 척도'}<br/>구동 전류 코드 {automatic.result!.sensor_profile?.drive_current_code??'이전 펌웨어'}<br/>기준 신호 지수 {summary.manufacturer_index??'이전 기록'} · 분주비 {automatic.result!.sensor_profile?.reference_divider??'미기록'}<br/>새 측정은 0~60 정수 지수로 표시·분류·추천을 연결합니다. 동일 센서 선행연구의 6단계 경계를 차용한 실험 기준이며 실제 피부 수분율(%)은 아닙니다. 이전 기록은 당시 척도를 유지합니다.</p>}
      <p>앱: moisture-score60-sqrt-v2 · BLE v{sensor.measurement?.protocol_version??'대기'} · 설정 {sensor.measurement?.sensor_profile?'확인됨':'미확인'}<br/>수신: {sensor.measurement?.sequence??'없음'} · 기준값: {ref?.baseline??'보정 전'}</p>
      {automatic.result&&<button type="button" className="secondary" onClick={()=>download(`moisture-${automatic.result!.measurement_id}.json`,automatic.result)}>측정 데이터 내려받기</button>}
      <button type="button" className="secondary" onClick={()=>download('skin-moisture-audit.json',automatic.exportAudit())}>전체 기록 내려받기</button>
    </details>
  </section>
}
