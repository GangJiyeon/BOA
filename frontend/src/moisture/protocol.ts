export const SERVICE_UUID = '98b10000-e8f2-537e-4f6c-d104768a1214'
export const MEASUREMENT_UUID = '98b10001-e8f2-537e-4f6c-d104768a1214'
export const REFERENCE_UUID = '98b10002-e8f2-537e-4f6c-d104768a1214'
export const FRESH_UUID = '98b10004-e8f2-537e-4f6c-d104768a1214'
export const DRIVEN_UUID = '98b10006-e8f2-537e-4f6c-d104768a1214'
export const PROFILED_UUID = '98b10005-e8f2-537e-4f6c-d104768a1214'
import type { SensorProfile } from './hydrationEstimate'
export const COMMAND_UUID = '98b10003-e8f2-537e-4f6c-d104768a1214'
export type Measurement = {
  protocol_version: 1 | 2 | 3 | 4 | 5
  sensor_profile?: SensorProfile
  reference?: { calibration: 'uncalibrated' | 'calibrating' | 'ready' | 'failed'; baseline: number | null; average: number | null; percent: number | null; amplitudeWarning: boolean; warning_flags?: number; amplitude_direction?: 'none'|'low'|'high'|'both'|'unknown' }
  source: 'ble_sensor' | 'ble_simulation' | 'mock'
  status: 'valid' | 'sensor_error' | 'not_ready'
  raw_value: number | null
  unit: 'fdc2112_count'
  sequence: number
  device_uptime_ms: number
  received_at: string
}
// 12 bytes, little endian. No physical hydration percentage is implied.
export function decodeMeasurement(data: DataView, now = new Date()): Measurement {
  if (data.byteLength < 1) throw new Error('빈 BLE 패킷')
  const version = data.getUint8(0)
  if (!((version === 1 && data.byteLength === 12) || ([2,3,4,5].includes(version) && data.byteLength === 20))) throw new Error('지원하지 않는 BLE 패킷 길이/버전')
  const flags = data.getUint8(1), status = data.getUint8(2)
  const raw = data.getUint16(4, true)
  if (flags > 1 || status > 2 || (version === 1 ? data.getUint8(3) !== 0 : data.getUint8(3) > 3) || (status === 0 ? raw > 4095 : raw !== 65535)) {
    throw new Error('잘못된 BLE 측정 데이터')
  }
  let reference: Measurement['reference']
  let sensor_profile: SensorProfile | undefined
  if (version >= 2) {
    const calibration = data.getUint8(3)
    const baseline = data.getUint16(12, true), average = data.getUint16(14, true)
    const driveInfo = version===5 ? data.getUint16(16,true) : 65535
    const percent = version===5 ? 65535 : data.getUint16(16, true), metadata = data.getUint16(18, true)
    const warnings = version>=4 ? metadata & 0xf000 : metadata
    if(version>=4){
      const divider=metadata&0x3ff,verified=!!(metadata&0x400)
      if((metadata&0x800)!==0 || (verified ? ![11,22,44].includes(divider) : divider!==0))throw new Error('잘못된 센서 설정 데이터')
      if(verified)sensor_profile={reference_divider:divider as 11|22|44,output_gain:16,offset:170,sensor_divider:2,verified:true}
    }
    if(version===5){
      if(sensor_profile){
        if(driveInfo===65535 || (driveInfo&~0x061f)!==0)throw new Error('잘못된 센서 구동 정보')
        sensor_profile.drive_current_code=driveInfo&31
      }else if(driveInfo!==65535)throw new Error('확인되지 않은 센서 구동 정보')
    }
    const amplitudeWarning = (warnings & 0x1000) !== 0
    if ((warnings & 0x0fff) !== 0 ||
        (calibration === 2 ? baseline < 1 || baseline > 4095 : baseline !== 65535) ||
        (average !== 65535 && average > 4095) ||
        (percent !== 65535 && (percent > 100 || calibration !== 2 || average === 65535 || (warnings & 0xe000) !== 0)) ||
        (calibration === 1 && (status !== 2 || average !== 65535 || percent !== 65535)) ||
        (status === 0 && warnings !== 0) ||
        (status === 2 && percent !== 65535) ||
        (status === 1 && percent !== 65535 && !amplitudeWarning) ||
        (percent !== 65535 && percent !== Math.floor(Math.max(0, baseline - average) * 100 / baseline))) {
      throw new Error('잘못된 BLE 보정/상대 수분 데이터')
    }
    reference = { calibration: (['uncalibrated', 'calibrating', 'ready', 'failed'] as const)[calibration],
      baseline: baseline === 65535 ? null : baseline, average: average === 65535 ? null : average,
      percent: percent === 65535 ? null : percent, amplitudeWarning, warning_flags: warnings, ...(version===5?{amplitude_direction:!amplitudeWarning?'none':(driveInfo&0x600)===0x200?'low':(driveInfo&0x600)===0x400?'high':(driveInfo&0x600)===0x600?'both':'unknown'} as const:{}) }
  }
  return { protocol_version: version as 1 | 2 | 3 | 4 | 5, ...(sensor_profile ? {sensor_profile}:{}), ...(reference ? { reference } : {}), source: flags ? 'ble_simulation' : 'ble_sensor',
    status: (['valid', 'sensor_error', 'not_ready'] as const)[status],
    raw_value: status === 0 ? raw : null, unit: 'fdc2112_count',
    sequence: data.getUint16(6, true), device_uptime_ms: data.getUint32(8, true), received_at: now.toISOString() }
}

export function sensorReadiness(value: Measurement): string | null {
  if(value.source!=='ble_sensor')return '실제 측정기를 연결해 주세요.'
  if(value.protocol_version!==4&&value.protocol_version!==5)return `측정기 연결됨 · 이전 데이터 형식(v${value.protocol_version}). 새 moisture_sensor.ino 업로드 후 USB를 재연결해 주세요.`
  if(!value.sensor_profile)return value.status==='sensor_error'
    ? '아두이노 연결됨 · 센서 설정 확인 실패. 센서 전원과 I2C 연결을 확인해 주세요.'
    : '아두이노 연결됨 · 센서 초기화와 설정 확인 중…'
  return null
}

// Project telemetry v2–v4 into the unchanged raw-only v1 API schema.
export function rawSubmission(value: Measurement) {
  return { protocol_version: 1 as const, source: value.source, status: value.status,
    raw_value: value.raw_value, unit: value.unit, sequence: value.sequence,
    device_uptime_ms: value.device_uptime_ms, received_at: value.received_at }
}
