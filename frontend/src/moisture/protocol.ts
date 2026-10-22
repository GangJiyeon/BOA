export const SERVICE_UUID = '98b10000-e8f2-537e-4f6c-d104768a1214'
export const MEASUREMENT_UUID = '98b10001-e8f2-537e-4f6c-d104768a1214'
export type Measurement = {
  protocol_version: 1
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
  if (data.byteLength !== 12 || data.getUint8(0) !== 1) throw new Error('지원하지 않는 BLE 패킷 길이/버전')
  const flags = data.getUint8(1), status = data.getUint8(2)
  const raw = data.getUint16(4, true)
  if (flags > 1 || status > 2 || data.getUint8(3) !== 0 || (status === 0 ? raw > 4095 : raw !== 65535)) {
    throw new Error('잘못된 BLE 측정 데이터')
  }
  return { protocol_version: 1, source: flags ? 'ble_simulation' : 'ble_sensor',
    status: (['valid', 'sensor_error', 'not_ready'] as const)[status],
    raw_value: status === 0 ? raw : null, unit: 'fdc2112_count',
    sequence: data.getUint16(6, true), device_uptime_ms: data.getUint32(8, true), received_at: now.toISOString() }
}
