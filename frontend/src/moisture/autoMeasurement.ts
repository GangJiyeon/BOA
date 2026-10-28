import type { Measurement } from './protocol'
import { sensorReadiness } from './protocol'
import { estimateHydration, SUPPORTED_NORMALIZATIONS, DISPLAY_VERSION, type SensorProfile } from './hydrationEstimate'

// Fixed acquisition duration and protocol/data availability checks.
export const AUTO_CONFIG = Object.freeze({ version: 'skin-fixed-3s-v1' as const,
  airMs:2000,collectMs:3000,maxGapMs:350,staleMs:750,minSamples:25 })
export type Sample = { sequence: number; uptime_ms: number; count: number }
export type DiscardedSample = {sequence:number;uptime_ms:number;status:'not_ready'|'sensor_error';warning_flags:number;diagnostic_count:number|null}
export type CompletedMeasurement = {
  measurement_id: string; algorithm_version: 'cheek-auto-v1' | 'cheek-auto-v2' | 'skin-auto-v3' | 'skin-auto-v4' | 'skin-auto-v5' | 'skin-auto-v6' | typeof AUTO_CONFIG.version; site: 'left_cheek' | 'skin';
  window_end_uptime_ms?: number; normalization_version?: string; sensor_profile?: SensorProfile; measured_at: string; baseline: number; samples: Sample[];
  air_samples?: Sample[];
  discarded_samples?: DiscardedSample[];
  contact_threshold: number; release_threshold: number;
}
export type MeasurementSummary = { score_max?: number; moisture_level?: number; moisture_level_label?: string; discarded_sample_count?:number; warning_sample_count?:number; estimated_state?: 'low'|'normal'|'sufficient'; estimated_state_label?: string; estimation_version?: string; manufacturer_response?: number; manufacturer_index?: number; validation_level?: string; normalized_score?: number; normalization_version?: string; terminal_count?: number; algorithm_version?: string; relative_percent: number; mean_count: number; stddev_percent: number; range_percent: number; sample_count: number; duration_ms: number; capacitance_change_percent?: number; capacitance_range_pp?: number; capacitance_stddev_pp?: number; capacitance_drift_pp?: number; experimental_index?: number; index_saturated?: boolean; baseline?: number; response_lower?: number; response_upper?: number; response_step_pp?: number; resolution_limited?: boolean; drift_limit_pp?: number }
export type Phase = 'needs_calibration' | 'calibrating' | 'learning' | 'waiting' | 'collecting' | 'completed' | 'rejected'
export type AutoView = { phase: Phase; message: string; progress: number; contactThreshold: number; releaseThreshold: number }
// Historical sketch default: 30-count span. Comparison index, not hydration %.
export function legacySkinIndex(baseline: number, mean: number, span = 30): number {
  if (!Number.isFinite(baseline) || !Number.isFinite(mean) || !Number.isFinite(span) || span <= 0) throw new Error('Invalid index inputs')
  return Math.max(0, Math.min(100, (baseline - mean) * 100 / span))
}
// Fixed OUTPUT_GAIN=16, OFFSET=170, FIN=2. FREF divider is frozen within a
// calibration/measurement (v11=11; v12 surveys and selects 44/22/11).
// A ratio cancels the same reference clock and inductor, but not the offset.
export function capacitanceChange(baseline: number, count: number): number {
  return (((baseline + 170) / (count + 170)) ** 2 - 1) * 100
}
export function experimentalIndex(baseline: number, capPercent: number): number {
  if (baseline <= 30) return 0
  // Provisional display span inherited from the historical 30-count range. NOT AU.
  return Math.max(0, Math.min(100, capPercent / capacitanceChange(baseline, baseline - 30) * 100))
}
export const median = (xs: number[]) => {
  const sorted = [...xs].sort((a,b)=>a-b), n=sorted.length
  return n % 2 ? sorted[(n-1)/2] : (sorted[n/2-1]+sorted[n/2])/2
}
// Fraction of loaded equivalent capacitance added by contact, NOT skin water %.
export function contactResponse(baseline: number, count: number) {
  return 100 * (1 - ((count + 170) / (baseline + 170)) ** 2)
}
export function detectionThreshold(baseline: number, counts: number[]) {
  const values = counts.map(n => (baseline-n)*100/baseline)
  const mean=values.reduce((a,b)=>a+b,0)/values.length
  const sd=Math.sqrt(values.reduce((a,b)=>a+(b-mean)**2,0)/values.length)
  return Math.max(200/baseline, Math.abs(mean)+6*sd+100/baseline)
}
export function responsePrecision(baseline: number, counts: number[]) {
  const m=median(counts)
  const center=contactResponse(baseline,m)
  // Quantization only: independent +/- half-count bounds on reference and sample.
  // Not a clinical accuracy bound or a statistical confidence interval.
  const lower=contactResponse(baseline-0.5,m+0.5)
  const upper=contactResponse(baseline+0.5,m-0.5)
  const step=Math.abs(contactResponse(baseline,m-0.5)-contactResponse(baseline,m+0.5))
  return { response_lower: lower, response_upper: upper, response_step_pp: step,
    resolution_limited: Math.max(center-lower,upper-center) > Math.abs(center)*0.2 }
}
export function capStatistics(baseline: number, counts: number[], modern = false, guarded = false, stationary = false) {
  const values = counts.map(n => capacitanceChange(baseline, n))
  const mean = values.reduce((a,b) => a+b, 0) / values.length
  const k = Math.min(5, Math.floor(values.length / 2))
  const drift = k ? Math.abs(values.slice(-k).reduce((a,b)=>a+b,0)/k - values.slice(0,k).reduce((a,b)=>a+b,0)/k) : 0
  const index = modern ? median(counts.map(n=>contactResponse(baseline,n))) : experimentalIndex(baseline, mean)
  const edge=Math.min(...counts)
  const quantum=Math.abs(capacitanceChange(baseline,edge-0.5)-capacitanceChange(baseline,edge+0.5))
  let driftLimit=Math.min(1,Math.max(quantum,Math.abs(mean)*0.15))
  if (stationary && k > 1) {
    const sd=(xs:number[])=>{
      const avg=xs.reduce((a,b)=>a+b,0)/xs.length
      return Math.sqrt(xs.reduce((a,b)=>a+(b-avg)**2,0)/(xs.length-1))
    }
    // Engineering stationarity tolerance, NOT a clinical accuracy bound or CI.
    // Compare endpoint means against their local variation, with a 1-code floor.
    // Do not make drift acceptable simply because the contact response grew.
    driftLimit=Math.min(driftLimit,Math.max(quantum,3*Math.max(sd(values.slice(0,k)),sd(values.slice(-k)))))
  }
  return { ...(guarded ? {...responsePrecision(baseline,counts),
      drift_limit_pp: driftLimit} : {}), capacitance_change_percent: mean,
    capacitance_range_pp: Math.max(...values) - Math.min(...values),
    capacitance_stddev_pp: Math.sqrt(values.reduce((a,b)=>a+(b-mean)**2,0)/values.length),
    capacitance_drift_pp: drift, experimental_index: index, index_saturated: index >= 100 }
}
export const NORMALIZATION_VERSION = DISPLAY_VERSION
// BOA engineering display scale: 0..10% capacitance increase -> 1..100.
// This is a relative product score, not a clinically calibrated water percentage.
export function normalizedMoistureScore(baseline:number,count:number) {
  const response=Math.max(0,capacitanceChange(baseline,count))
  return Math.max(1,Math.min(100,Math.floor(response*10+0.5)))
}
const elapsed = (a: number, b: number) => (a - b) >>> 0
const relative = (count: number, baseline: number) => (baseline - count) * 100 / baseline
export function summarize(result: CompletedMeasurement): MeasurementSummary {
  const counts = result.samples.map(s => s.count)
  const mean = counts.reduce((a, b) => a + b, 0) / counts.length
  const pct = counts.map(n => relative(n, result.baseline))
  const avgPct = pct.reduce((a, b) => a + b, 0) / pct.length
  const fixed=result.algorithm_version==='skin-fixed-3s-v1'
  const terminal=fixed?median(result.samples.filter(s=>elapsed(s.uptime_ms,result.samples[0].uptime_ms)>=2000).map(s=>s.count)):null
  return { ...(fixed?{...(SUPPORTED_NORMALIZATIONS.includes(result.normalization_version??'')&&result.sensor_profile?estimateHydration(result.baseline,terminal!,result.sensor_profile.reference_divider,result.normalization_version):{normalized_score:normalizedMoistureScore(result.baseline,terminal!)}),normalization_version:result.normalization_version,terminal_count:terminal!}:{}), discarded_sample_count:result.discarded_samples?.length??0,warning_sample_count:result.discarded_samples?.filter(s=>s.warning_flags!==0).length??0, algorithm_version: result.algorithm_version, baseline: result.baseline, ...capStatistics(result.baseline, counts, ['skin-auto-v3','skin-auto-v4','skin-auto-v5','skin-auto-v6','skin-fixed-3s-v1'].includes(result.algorithm_version), ['skin-auto-v4','skin-auto-v5','skin-auto-v6'].includes(result.algorithm_version), result.algorithm_version === 'skin-auto-v6'), mean_count: mean, relative_percent: Math.max(0, Math.min(100, relative(mean, result.baseline))),
    stddev_percent: Math.sqrt(pct.reduce((a, b) => a + (b - avgPct) ** 2, 0) / pct.length),
    range_percent: Math.max(...pct) - Math.min(...pct), sample_count: counts.length,
    duration_ms: fixed ? 3000 : elapsed(result.samples.at(-1)!.uptime_ms, result.samples[0].uptime_ms) }
}
export class AutoMeasurement {
  private phase: Phase = 'needs_calibration'
  private message = '연결 후 기준값 보정을 눌러 주세요.'
  private baseline: number | null = null
  private air: Sample[] = []
  private samples: Sample[] = []
  private discarded: DiscardedSample[] = []
  private lastGoodHost = -Infinity
  private previous?: Measurement
  private lastHost = -Infinity
  private startHost = 0
  private startUptime = 0
  private firstReceived = ''
  private on = 2
  private off = 1
  private queued: CompletedMeasurement | null = null
  private blocked = false
  private profile?: SensorProfile
  private id: () => string
  constructor(id: () => string = () => crypto.randomUUID()) { this.id = id }
  isTerminal() { return this.phase === 'completed' || this.phase === 'rejected' }
  lastRejected(): CompletedMeasurement | null { return null }
  takeCompleted() { const result=this.queued;this.queued=null;return result }
  view(): AutoView {
    return {phase:this.phase,message:this.message,contactThreshold:this.on,releaseThreshold:this.off,
      progress:this.phase==='completed'?1:this.phase==='collecting'?Math.min(1,Math.max(0,(this.lastHost-this.startHost)/3000)):0}
  }
  reset(message='연결 후 기준값 보정을 눌러 주세요.') {
    this.phase='needs_calibration';this.message=message;this.baseline=null;this.air=[];this.samples=[]
    this.previous=undefined;this.lastHost=-Infinity;this.lastGoodHost=-Infinity;this.discarded=[];this.queued=null;this.blocked=false;this.profile=undefined
  }
  requestCalibration() {this.reset('공기 중 기준값 보정 중…');this.phase='calibrating';this.blocked=true}
  restoreCompleted(result:CompletedMeasurement) {
    this.phase='completed';this.baseline=result.baseline;this.on=result.contact_threshold;this.off=result.release_threshold
    this.message='측정 완료';this.queued=null
  }
  private fail(message:string) {this.phase='rejected';this.message=message;this.samples=[];this.queued=null}
  private finish(hostNow:number) {
    if(this.phase!=='collecting')return
    if(hostNow-this.lastGoodHost>AUTO_CONFIG.maxGapMs || this.samples.length<AUTO_CONFIG.minSamples || elapsed(this.samples.at(-1)!.uptime_ms,this.startUptime)<2650) {
      this.fail(this.discarded.some(s=>s.warning_flags&0x1000)
        ?'피부 접촉 중 센서 진폭 경고로 측정하지 못했습니다.'
        :'3초 동안 정상 표본이 충분하지 않았습니다. 측정 상세의 전체 기록을 확인해 주세요.');return
    }
    const result:CompletedMeasurement={measurement_id:this.id(),algorithm_version:AUTO_CONFIG.version,site:'skin',
      measured_at:new Date(Date.parse(this.firstReceived)+3000).toISOString(),baseline:this.baseline!,
      air_samples:[...this.air],samples:[...this.samples],contact_threshold:this.on,release_threshold:this.off,
      window_end_uptime_ms:(this.startUptime+3000)>>>0,normalization_version:NORMALIZATION_VERSION,sensor_profile:{...this.profile!},
      ...(this.discarded.length?{discarded_samples:[...this.discarded]}:{})}
    const terminal=this.samples.filter(x=>elapsed(x.uptime_ms,this.startUptime)>=2000)
    if(this.discarded.some(x=>elapsed(x.uptime_ms,this.startUptime)>=2000&&x.status==='sensor_error')){
      this.fail('측정 마지막 구간에 센서 오류가 있어 수분 상태를 판정하지 않았습니다. 전체 기록을 확인해 주세요.');return
    }
    if(terminal.length<5 || relative(median(terminal.map(x=>x.count)),this.baseline!)<=this.off) {
      this.fail('피부 접촉이 유지되지 않았습니다.');return
    }
    try { estimateHydration(result.baseline,median(terminal.map(x=>x.count)),this.profile!.reference_divider) }
    catch {this.fail('센서 신호가 실험 판정 기준의 계산 범위를 벗어났습니다.');return}
    this.restoreCompleted(result);this.queued=result
  }
  tick(hostNow:number) {
    if(this.phase==='collecting' && hostNow-this.startHost>=3000)this.finish(hostNow)
    else if(this.phase==='collecting' && hostNow-this.lastHost>AUTO_CONFIG.staleMs)this.fail('측정기 연결을 확인해 주세요.')
    if(this.phase==='learning' && hostNow-this.lastHost>AUTO_CONFIG.staleMs)this.air=[]
    const view=this.view()
    if(this.phase==='collecting')view.progress=Math.min(1,(hostNow-this.startHost)/3000)
    return view
  }
  push(m:Measurement,hostNow:number):CompletedMeasurement|null {
    if(this.isTerminal())return null
    // The timer closes the window at 3 seconds. Never add a later packet.
    if(this.phase==='collecting' && hostNow-this.startHost>=3000) {
      this.finish(hostNow);return this.takeCompleted()
    }
    const ref=m.reference
    const readiness=sensorReadiness(m)
    if(readiness || !m.sensor_profile) {
      if(this.phase==='collecting')this.fail('측정 중 센서 설정 정보가 사라졌습니다.')
      else this.reset(readiness??'센서 설정 확인 중…')
      return null
    }
    if(this.profile&&JSON.stringify(this.profile)!==JSON.stringify(m.sensor_profile)){this.fail('센서 설정이 바뀌었습니다. 기준값을 다시 보정해 주세요.');return null}
    if(!ref || ref.calibration!=='ready' || ref.baseline===null) {
      this.reset(ref?.calibration==='failed'?'기준값 보정에 실패했습니다.':'기준값을 보정해 주세요.')
      if(ref?.calibration==='calibrating'){this.phase='calibrating';this.message='공기 중 기준값 보정 중…'}
      return null
    }
    if(this.blocked)return null
    this.profile={...m.sensor_profile}
    let gap=false
    if(this.previous) {
      const step=(m.sequence-this.previous.sequence)&65535,dt=elapsed(m.device_uptime_ms,this.previous.device_uptime_ms)
      if(step===0&&dt===0)return null
      if(step===0||step>32768||dt===0||dt>0x7fffffff){this.fail('측정기가 다시 시작됐습니다. 기준값을 보정해 주세요.');return null}
      gap=step>4||dt<50||dt>AUTO_CONFIG.maxGapMs||hostNow-this.lastHost>AUTO_CONFIG.maxGapMs
    }
    const previousHost=this.lastHost
    this.previous=m;this.lastHost=hostNow
    if(this.baseline!==ref.baseline){
      if(this.phase==='collecting'){this.fail('측정 중 기준값이 바뀌었습니다.');return null}
      this.baseline=ref.baseline;this.phase='learning';this.air=[];this.message='기준값 확인 중 · 센서 면을 피부에서 떼어 주세요.'
    }
    const good=m.status==='valid'&&m.raw_value!==null&&!ref.amplitudeWarning&&ref.average===m.raw_value
    if(!good){
      if(this.phase==='collecting'){
        if(m.status==='valid'){this.fail('센서 원시값과 참조값이 일치하지 않습니다.');return null}
        this.discarded.push({sequence:m.sequence,uptime_ms:m.device_uptime_ms,status:m.status,
          warning_flags:ref.warning_flags??(ref.amplitudeWarning?0x1000:0),diagnostic_count:ref.average})
      }
      if(this.phase==='learning'&&m.status!=='not_ready')this.air=[]
      return null
    }
    const count=m.raw_value!
    if(count<=1||count>=4094){this.fail('센서 측정 범위를 벗어났습니다.');return null}
    const pct=relative(count,this.baseline!)
    if(this.phase==='learning') {
      const previousAir=this.air.at(-1)
      if(gap||Math.abs(pct)>2||(previousAir&&elapsed(m.device_uptime_ms,previousAir.uptime_ms)>AUTO_CONFIG.maxGapMs))this.air=[]
      if(Math.abs(pct)>2)return null
      this.air.push({sequence:m.sequence,uptime_ms:m.device_uptime_ms,count})
      if(elapsed(m.device_uptime_ms,this.air[0].uptime_ms)>=AUTO_CONFIG.airMs&&this.air.length>=16){
        this.on=detectionThreshold(this.baseline!,this.air.map(x=>x.count));this.off=this.on/2
        this.phase='waiting';this.message='센서를 피부에 대면 3초간 측정합니다.'
      }
      return null
    }
    if(this.phase==='waiting') {
      if(pct<this.on)return null
      this.phase='collecting';this.message='측정 중 · 3초간 유지해 주세요.';this.startHost=hostNow
      this.startUptime=m.device_uptime_ms;this.firstReceived=m.received_at;this.samples=[];this.discarded=[]
    }
    if(this.phase==='collecting') {
      if(gap){this.fail('측정 데이터가 끊겼습니다.');return null}
      const prior=this.samples.at(-1)
      if(prior&&(elapsed(m.device_uptime_ms,prior.uptime_ms)>AUTO_CONFIG.maxGapMs || hostNow-this.lastGoodHost>AUTO_CONFIG.maxGapMs)){
        this.fail('정상 표본 사이 간격이 너무 깁니다. 측정 상세의 전체 기록을 확인해 주세요.');return null
      }
      const dt=elapsed(m.device_uptime_ms,this.startUptime)
      if(dt>3000){
        if(hostNow-this.startHost<2650)this.fail('과거 데이터가 한꺼번에 도착했습니다. 연결을 확인해 주세요.')
        else this.lastHost=previousHost
        return null
      }
      this.samples.push({sequence:m.sequence,uptime_ms:m.device_uptime_ms,count})
      this.lastGoodHost=hostNow
    }
    return null
  }
}
