import { decodeMeasurement, MEASUREMENT_UUID, SERVICE_UUID, type Measurement } from './protocol'
export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error'
export type Observer = { state: (s: ConnectionState) => void; measurement: (m: Measurement) => void; error: (message: string) => void }
export interface MoistureAdapter { connect(): Promise<void>; disconnect(): void }
// Minimal structural declarations for the Web Bluetooth subset we use.
export interface Characteristic extends EventTarget {
  value?: DataView
  startNotifications(): Promise<Characteristic>
  stopNotifications(): Promise<Characteristic>
}
export interface Device extends EventTarget {
  gatt?: { connected: boolean; connect(): Promise<{ getPrimaryService(uuid: string): Promise<{ getCharacteristic(uuid: string): Promise<Characteristic> }> }>; disconnect(): void }
}
export interface Bluetooth { requestDevice(options: { filters: { services: string[] }[] }): Promise<Device> }
export class BleMoistureAdapter implements MoistureAdapter {
  private device?: Device
  private characteristic?: Characteristic
  private generation = 0
  private busy = false
  private observer: Observer
  private bluetooth?: Bluetooth
  private secure: boolean
  constructor(observer: Observer, bluetooth?: Bluetooth, secure = true) { this.observer = observer; this.bluetooth = bluetooth; this.secure = secure }
  private notification = () => {
    try {
      const value = this.characteristic?.value
      if (!value) throw new Error('빈 BLE 데이터')
      this.observer.measurement(decodeMeasurement(value))
    } catch (e) { this.observer.error(e instanceof Error ? e.message : 'BLE 데이터 오류') }
  }
  private lost = () => this.disconnect()
  async connect() {
    if (this.busy || this.device?.gatt?.connected) return
    const generation = ++this.generation
    this.busy = true
    this.observer.state('connecting')
    let device: Device | undefined
    let characteristic: Characteristic | undefined
    try {
      if (!this.secure || !this.bluetooth) throw new Error('HTTPS 또는 localhost의 Chrome/Edge와 Bluetooth 지원이 필요합니다')
      device = await this.bluetooth.requestDevice({ filters: [{ services: [SERVICE_UUID] }] })
      if (generation !== this.generation) return
      this.device = device
      device.addEventListener('gattserverdisconnected', this.lost)
      if (!device.gatt) throw new Error('GATT를 사용할 수 없습니다')
      const server = await device.gatt.connect()
      if (generation !== this.generation) { device.gatt.disconnect(); return }
      const service = await server.getPrimaryService(SERVICE_UUID)
      characteristic = await service.getCharacteristic(MEASUREMENT_UUID)
      if (generation !== this.generation) { device.gatt.disconnect(); return }
      this.characteristic = characteristic
      characteristic.addEventListener('characteristicvaluechanged', this.notification)
      await characteristic.startNotifications()
      if (generation !== this.generation) {
        characteristic.removeEventListener('characteristicvaluechanged', this.notification)
        void characteristic.stopNotifications().catch(() => {})
        device.gatt.disconnect(); return
      }
      this.observer.state('connected')
    } catch (e) {
      if (generation !== this.generation) return
      this.disconnect()
      this.observer.state('error')
      this.observer.error(e instanceof Error ? e.message : 'BLE 연결 실패. 전원·권한을 확인하고 다시 연결하세요.')
    } finally { if (generation === this.generation) this.busy = false }
  }
  disconnect() {
    ++this.generation; this.busy = false
    const characteristic = this.characteristic, device = this.device
    this.characteristic = undefined; this.device = undefined
    characteristic?.removeEventListener('characteristicvaluechanged', this.notification)
    if (device?.gatt?.connected) void characteristic?.stopNotifications().catch(() => {})
    device?.removeEventListener('gattserverdisconnected', this.lost)
    device?.gatt?.disconnect()
    this.observer.state('disconnected')
  }
}
export class MockMoistureAdapter implements MoistureAdapter {
  private timer?: ReturnType<typeof setInterval>
  private observer: Observer
  private enabled: boolean
  constructor(observer: Observer, enabled: boolean) { this.observer = observer; this.enabled = enabled }
  async connect() {
    if (!this.enabled) throw new Error('Mock은 개발 환경에서만 사용할 수 있습니다')
    if (this.timer) return
    this.observer.state('connecting')
    let sequence = 0
    this.observer.state('connected')
    const emit = () => this.observer.measurement({ protocol_version: 1, source: 'mock', status: 'valid',
      raw_value: 1100 + sequence % 40, unit: 'fdc2112_count', sequence: sequence++ % 65536,
      device_uptime_ms: (sequence * 500) >>> 0, received_at: new Date().toISOString() })
    emit(); this.timer = setInterval(emit, 500)
  }
  disconnect() { clearInterval(this.timer); this.timer = undefined; this.observer.state('disconnected') }
}
