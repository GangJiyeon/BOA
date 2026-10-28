import { decodeMeasurement, MEASUREMENT_UUID, REFERENCE_UUID, FRESH_UUID, PROFILED_UUID, DRIVEN_UUID, COMMAND_UUID, SERVICE_UUID, type Measurement } from './protocol'
export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error'
export type Observer = { state: (s: ConnectionState) => void; measurement: (m: Measurement) => void; error: (message: string) => void }
export interface MoistureAdapter { connect(): Promise<void>; disconnect(): void; calibrate?(): Promise<void> }
// Minimal structural declarations for the Web Bluetooth subset we use.
export interface Characteristic extends EventTarget {
  uuid?: string
  value?: DataView
  readValue?(): Promise<DataView>
  writeValueWithResponse?(value: Uint8Array): Promise<void>
  startNotifications(): Promise<Characteristic>
  stopNotifications(): Promise<Characteristic>
}
export interface Service {
  getCharacteristic(uuid:string):Promise<Characteristic>
  getCharacteristics?():Promise<Characteristic[]>
}
export interface Device extends EventTarget {
  gatt?: { connected: boolean; connect(): Promise<{ getPrimaryService(uuid: string): Promise<Service> }>; disconnect(): void }
}
export interface Bluetooth { requestDevice(options: { filters: { services: string[] }[] }): Promise<Device> }
export class BleMoistureAdapter implements MoistureAdapter {
  private device?: Device
  private characteristic?: Characteristic
  private command?: Characteristic
  private generation = 0
  private busy = false
  private observer: Observer
  private bluetooth?: Bluetooth
  private secure: boolean
  private selectedProtocol?: number
  constructor(observer: Observer, bluetooth?: Bluetooth, secure = true) { this.observer = observer; this.bluetooth = bluetooth; this.secure = secure }
  private notification = () => {
    try {
      const value = this.characteristic?.value
      if (!value) throw new Error('빈 BLE 데이터')
      this.deliver(value)
    } catch (e) { this.observer.error(e instanceof Error ? e.message : 'BLE 데이터 오류') }
  }
  private deliver(value:DataView) {
    const measurement=decodeMeasurement(value)
    if(this.selectedProtocol && measurement.protocol_version!==this.selectedProtocol)
      throw new Error('선택한 BLE 항목과 데이터 버전이 다릅니다. USB 재연결 후 측정기를 다시 선택해 주세요.')
    this.observer.measurement(measurement)
  }
  private lost = () => this.disconnect()
  async connect() {
    if (this.busy || this.device?.gatt?.connected) return
    const generation = ++this.generation
    this.busy = true
    this.observer.state('connecting')
    let device: Device | undefined
    let characteristic: Characteristic | undefined
    let command: Characteristic | undefined
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
      const choices=[DRIVEN_UUID,PROFILED_UUID,FRESH_UUID,REFERENCE_UUID,MEASUREMENT_UUID]
      // Enumerate the actual GATT table first where supported. Keep the direct
      // lookup fallback for older browsers/adapters; never guess a sensor profile.
      const available=await service.getCharacteristics?.()
      if(generation!==this.generation){device.gatt.disconnect();return}
      for(const uuid of choices){
        if(available){characteristic=available.find(c=>c.uuid?.toLowerCase()===uuid);if(!characteristic)continue}
        else {
          try {characteristic=await service.getCharacteristic(uuid)}
          catch(e){if(!(e instanceof Error)||e.name!=='NotFoundError')throw e;continue}
        }
        this.selectedProtocol=uuid===DRIVEN_UUID?5:uuid===PROFILED_UUID?4:uuid===FRESH_UUID?3:uuid===REFERENCE_UUID?2:1
        break
      }
      if(!characteristic)throw new Error('측정 데이터 항목을 찾지 못했습니다. 새 펌웨어 업로드 후 USB를 재연결해 주세요.')
      if (generation !== this.generation) { device.gatt.disconnect(); return }
      try { command = await service.getCharacteristic(COMMAND_UUID) }
      catch (e) { if (!(e instanceof Error) || e.name !== 'NotFoundError') throw e }
      if (generation !== this.generation) { device.gatt.disconnect(); return }
      this.command = command
      this.characteristic = characteristic
      characteristic.addEventListener('characteristicvaluechanged', this.notification)
      await characteristic.startNotifications()
      if (generation !== this.generation) {
        characteristic.removeEventListener('characteristicvaluechanged', this.notification)
        void characteristic.stopNotifications().catch(() => {})
        device.gatt.disconnect(); return
      }
      this.observer.state('connected')
      // A readable initial value avoids waiting for a notification to discover
      // whether this is a legacy firmware or a not-yet-initialized sensor.
      if(characteristic.readValue){
        let initial:DataView|undefined
        try{initial=await characteristic.readValue()}catch{/* Notifications remain active if this optional initial read fails. */}
        if(initial&&generation===this.generation){
          try{this.deliver(initial)}catch(e){this.observer.error(e instanceof Error?e.message:'BLE 데이터 오류')}
        }
      }
    } catch (e) {
      if (generation !== this.generation) return
      this.disconnect()
      this.observer.state('error')
      this.observer.error(e instanceof Error ? e.message : 'BLE 연결 실패. 전원·권한을 확인하고 다시 연결하세요.')
    } finally { if (generation === this.generation) this.busy = false }
  }
  async calibrate() {
    if (!this.device?.gatt?.connected || !this.command?.writeValueWithResponse)
      throw new Error('보정 버튼을 사용하려면 v6 펌웨어로 업데이트하고 재연결하세요.')
    await this.command.writeValueWithResponse(new Uint8Array([1]))
  }
  disconnect() {
    this.selectedProtocol = undefined
    this.command = undefined
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
