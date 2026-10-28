import type { Measurement } from './protocol'
import type { AutoView, CompletedMeasurement } from './autoMeasurement'

type Entry = { elapsed_ms: number; kind: 'sample'; measurement: Measurement; view: AutoView } |
  { elapsed_ms: number; kind: 'event'; event: string; result?: CompletedMeasurement }

// Records rejected samples too. A completed window alone cannot explain a low result.
// Bounded in-memory capture; no face photo, account id or server upload.
export class CheekAudit {
  private entries: Entry[] = []
  private dropped = 0
  private readonly start: number
  private readonly limit: number
  constructor(start = performance.now(), limit = 3000) { this.start = start; this.limit = limit }
  private append(entry: Entry) {
    this.entries.push(structuredClone(entry))
    if (this.entries.length > this.limit) { this.entries.shift(); this.dropped++ }
  }
  sample(measurement: Measurement, view: AutoView, now: number) {
    this.append({ kind: 'sample', elapsed_ms: now - this.start, measurement, view })
  }
  event(event: string, now: number, result?: CompletedMeasurement) {
    this.append({ kind: 'event', elapsed_ms: now - this.start, event, ...(result ? { result } : {}) })
  }
  export() {
    const completed=this.entries.filter(e=>e.kind==='event'&&e.result).at(-1)
    const latest=this.entries.filter(e=>e.kind==='sample'&&e.measurement.sensor_profile).at(-1)
    return structuredClone({ schema: 'boa-skin-audit-v2', site: 'skin',
      hydration_model: null, interpretation: 'sensor_response_only',
      measurement_window_ms: 3000, normalization_version:completed?.kind==='event'?completed.result?.normalization_version??null:null,
      firmware_configuration:latest?.kind==='sample'?latest.measurement.sensor_profile:'unavailable',
      dropped_entries: this.dropped, entries: this.entries })
  }
}
