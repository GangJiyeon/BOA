import { useEffect, useRef, useState } from 'react'
import { AutoMeasurement, type CompletedMeasurement } from '../moisture/autoMeasurement'
import { CheekAudit } from '../moisture/cheekAudit'
import type { Measurement } from '../moisture/protocol'

export function useAutoMoisture(value: Measurement | null, connected: boolean, context: number | null, onComplete: (r: CompletedMeasurement) => void, initialResult: CompletedMeasurement | null = null) {
  const machineRef = useRef<AutoMeasurement | null>(null)
  if (!machineRef.current) {
    machineRef.current = new AutoMeasurement()
    if (initialResult) machineRef.current.restoreCompleted(initialResult)
  }
  const machine = machineRef as { current: AutoMeasurement }
  const audit = useRef<CheekAudit | null>(null)
  audit.current ??= new CheekAudit()
  const completedAt = useRef<number | null>(initialResult ? performance.now() : null)
  const callback = useRef(onComplete)
  callback.current = onComplete
  const [view, setView] = useState(() => machine.current.view())
  const [result, setResult] = useState<CompletedMeasurement | null>(initialResult)
  const priorContext=useRef(context)
  useEffect(() => {
    const before=priorContext.current;priorContext.current=context
    audit.current!.event('analysis_context_changed',performance.now())
    // Binding the first photo analysis ID must not restart a running 3s capture.
    if(machine.current.isTerminal()||before===null||before===context)return
    machine.current.reset();setView(machine.current.view());setResult(null)
  }, [context])
  useEffect(() => {
    audit.current!.event(connected ? 'connected' : 'disconnected', performance.now())
    if (!connected && !machine.current.isTerminal()) { machine.current.reset(); setView(machine.current.view()); setResult(null) }
  }, [connected])
  useEffect(() => {
    if (!connected || !value) return
    if (machine.current.isTerminal()) {
      return
    }
    const completed = machine.current.push(value, performance.now())
    audit.current!.sample(value, machine.current.view(), performance.now())
    setView(machine.current.view())
    if (machine.current.view().phase === 'rejected') {
      completedAt.current = performance.now(); audit.current!.event('measurement_rejected',performance.now(),machine.current.lastRejected() ?? undefined)
    }
    if (value.reference?.calibration === 'calibrating') setResult(null)
    if (completed) { completedAt.current = performance.now(); audit.current!.event('completed', performance.now(), completed); setResult(completed); callback.current(completed) }
  }, [value, connected])
  useEffect(() => {
    const timer = setInterval(() => {
      const was=machine.current.view().phase
      const next=machine.current.tick(performance.now())
      if(was==='collecting'||next.phase!==was)setView(next)
      if(was!=='rejected'&&next.phase==='rejected'){completedAt.current=performance.now();audit.current!.event('measurement_rejected',performance.now())}
      const done=machine.current.takeCompleted()
      if(done){completedAt.current=performance.now();audit.current!.event('completed',performance.now(),done);setResult(done);callback.current(done)}
    }, 25)
    return () => clearInterval(timer)
  }, [])
  const reset = () => { completedAt.current = null; audit.current!.event('calibration_requested', performance.now()); machine.current.requestCalibration(); setView(machine.current.view()); setResult(null) }
  return { view, result, reset, exportAudit: () => audit.current!.export() }
}
