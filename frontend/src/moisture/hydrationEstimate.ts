// Experimental prior from PNJ 2023, not clinically validated BOA cutoffs.
export const ESTIMATION_VERSION = 'hydration-estimate-pnj-2023-v1' as const
export const LEGACY_DISPLAY_VERSION = 'boa-capacitance-display-v2' as const
export const LINEAR60_VERSION = 'boa-moisture-60-v1' as const
export const DISPLAY_VERSION = 'boa-moisture-60-sqrt-v2' as const
export const SCORE60_VERSIONS: readonly string[] = [LINEAR60_VERSION, DISPLAY_VERSION]
export const SUPPORTED_NORMALIZATIONS: readonly string[] = [ESTIMATION_VERSION, LEGACY_DISPLAY_VERSION, ...SCORE60_VERSIONS]
export const REFERENCE_DIVIDER = 11 // legacy driver x10 argument becomes 0x200B
export type SensorProfile = { reference_divider: 11 | 22 | 44; output_gain: 16; offset: 170; sensor_divider: 2; verified: true; drive_current_code?:number }
export function estimateHydration(baseline:number,count:number,divider:number,normalizationVersion:string=DISPLAY_VERSION) {
  if(![11,22,44].includes(divider)||!Number.isFinite(count)||!(count>0&&count<baseline&&baseline<=4095))throw new Error('지원하지 않는 센서 설정 또는 접촉값')
  if (!SUPPORTED_NORMALIZATIONS.includes(normalizationVersion)) throw new Error('지원하지 않는 수분 척도')
  const air=(baseline+170)*REFERENCE_DIVIDER/divider-170,contact=(count+170)*REFERENCE_DIVIDER/divider-170
  if(air<=0||contact<0)throw new Error('공개 기준의 계산 범위를 벗어났습니다.')
  const response=Math.max(0,Math.min(100,100*(air-contact)/air)),index=Math.floor(response+1e-9)
  const score60 = scoreFromResponse(response, SCORE60_VERSIONS.includes(normalizationVersion)?normalizationVersion:LINEAR60_VERSION), grade = classification60(score60)
  const state=index<=22?'low':index<=45?'normal':'sufficient'
  const [lo,hi,start,end]=state==='low'?[0,23,1,33]:state==='normal'?[23,46,34,66]:[46,100,67,100]
  return { estimated_state:state as 'low'|'normal'|'sufficient',estimated_state_label:{low:'부족',normal:'보통',sufficient:'충분'}[state],
    normalized_score:SCORE60_VERSIONS.includes(normalizationVersion)?score60:normalizationVersion===LEGACY_DISPLAY_VERSION
      ?Math.max(1,Math.min(100,Math.floor(1000*(((baseline+170)/(count+170))**2-1)+.5)))
      :Math.max(start,Math.min(end,Math.floor(start+(end-start)*(response-lo)/(hi-lo)+.5))),
    manufacturer_response:response,manufacturer_index:index,estimation_version:SCORE60_VERSIONS.includes(normalizationVersion)?normalizationVersion:ESTIMATION_VERSION,
    ...(SCORE60_VERSIONS.includes(normalizationVersion)?grade:{score_max:100}),
    validation_level:'experimental_unvalidated' as const }
}


// The original classifier consumes truncated integers: transition at 13/23/28/40/46.
export const SOURCE_BREAKS = [0,13,23,28,40,46,100] as const
export const LEVEL_LABELS = ['매우 부족','부족','보통 중 낮음','보통','보통 중 높음','매우 높음'] as const
export function scoreFromResponse(input:number,version:string=DISPLAY_VERSION):number {
  if (!SCORE60_VERSIONS.includes(version)) throw new Error('지원하지 않는 0~60 척도')
  if(!Number.isFinite(input)||input<0||input>100)throw new Error('수분 반응 지수 범위 오류')
  const nearest=Math.round(input),response=Math.abs(input-nearest)<1e-9?nearest:input
  if(response===100)return 60
  const band=SOURCE_BREAKS.findIndex((hi,i)=>i>0&&response<hi)-1
  const fraction=(response-SOURCE_BREAKS[band]!)/(SOURCE_BREAKS[band+1]!-SOURCE_BREAKS[band]!)
  return band*10+Math.min(9,Math.floor(10*(version===DISPLAY_VERSION?Math.sqrt(fraction):fraction)))
}
export function classification60(score:number) {
  if(!Number.isInteger(score)||score<0||score>60)throw new Error('수분 점수는 0~60 정수여야 합니다.')
  const level=Math.min(6,Math.floor(score/10)+1),state=level<=2?'low':level<=5?'normal':'sufficient'
  return {score_max:60,moisture_level:level,moisture_level_label:LEVEL_LABELS[level-1]!,
    estimated_state:state as 'low'|'normal'|'sufficient',
    estimated_state_label:{low:'부족',normal:'보통',sufficient:'충분'}[state]}
}


type ScaleInfo = {score_max?:number; normalization_version?:string; moisture_level?:number; moisture_level_label?:string; estimated_state_label?:string}
export function scoreMaximum(info:ScaleInfo):number {
  return info.score_max??(SCORE60_VERSIONS.includes(info.normalization_version??'')?60:100)
}
export function levelDescription(info:ScaleInfo):string {
  return info.moisture_level!=null?`${info.moisture_level}/6단계 · ${info.moisture_level_label??''}`:info.estimated_state_label??''
}
