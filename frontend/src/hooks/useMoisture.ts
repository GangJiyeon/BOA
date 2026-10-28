import { useEffect, useRef, useState } from 'react'
import { BleMoistureAdapter, MockMoistureAdapter, type Bluetooth, type ConnectionState, type MoistureAdapter } from '../moisture/adapters'
import type { Measurement } from '../moisture/protocol'

export function useMoisture() {
  const [state, setState] = useState<ConnectionState>('disconnected')
  const [measurement, setMeasurement] = useState<Measurement | null>(null)
  const [error, setError] = useState('')
  const adapter = useRef<MoistureAdapter | null>(null)
  const mounted = useRef(false)
  const epoch = useRef(0)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; ++epoch.current; adapter.current?.disconnect() } }, [])
  const disconnect = () => { ++epoch.current; adapter.current?.disconnect(); adapter.current = null; setState('disconnected'); setMeasurement(null) }
  const connect = (mock = false) => {
    if (state === 'connecting' || state === 'connected') return
    disconnect(); setError('')
    const current = epoch.current
    const live = () => mounted.current && current === epoch.current
    const observer = {
      state: (value: ConnectionState) => { if (live()) { setState(value); if (value !== 'connected') setMeasurement(null) } },
      measurement: (value: Measurement) => { if (live()) { setMeasurement(value); setError('') } },
      error: (message: string) => { if (live()) { setError(message); setMeasurement(null) } },
    }
    adapter.current = mock ? new MockMoistureAdapter(observer, import.meta.env.DEV)
      : new BleMoistureAdapter(observer, (navigator as Navigator & { bluetooth?: Bluetooth }).bluetooth, window.isSecureContext)
    void adapter.current.connect().catch(e => observer.error(String(e)))
  }
  const calibrate = async () => {
    if (!adapter.current?.calibrate) throw new Error('이 연결은 보정을 지원하지 않습니다.')
    await adapter.current.calibrate()
  }
  return { state, measurement, error, connect, disconnect, calibrate }
}
