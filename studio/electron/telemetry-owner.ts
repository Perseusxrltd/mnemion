/** An existing awake app may offer work; this owner never schedules a wake. */
import type { TelemetryStamp } from '../shared/product-telemetry'

type Port<Report> = {
  available: () => boolean
  reserve: (stamp: TelemetryStamp, stop: AbortSignal) => Promise<Report | null>
  send: (report: Report, stop: AbortSignal) => Promise<unknown>
  cancel: (report: Report) => Promise<void>
  cleanup?: () => void
}

export class TelemetryActivity<Report> {
  private active?: { stop: AbortController; done: Promise<void> }
  private readonly pauses = new Set<string>()
  private closed = false
  private nextCheck = 0
  constructor(private readonly port: Port<Report>, private readonly now = () => performance.now()) {}
  private available(): boolean { try { return this.port.available() === true } catch { return false } }

  /** At most one in-flight operation and one eligibility probe per awake minute.
   * No inputs, results or missed opportunities are retained for a later retry. */
  offer(stamp: TelemetryStamp): void {
    if (this.closed || this.pauses.size || this.active || !this.available()) return
    const now = this.now()
    if (!Number.isFinite(now) || now < this.nextCheck) return
    this.nextCheck = now + 60000
    const expected = { revision: stamp.revision, store_generation: stamp.store_generation }
    const state = { stop: new AbortController(), done: Promise.resolve() }
    this.active = state
    state.done = Promise.resolve().then(async () => {
      let report: Report | null = null
      try {
        if (state.stop.signal.aborted || !this.available()) return
        report = await this.port.reserve(expected, state.stop.signal)
        if (report !== null && !state.stop.signal.aborted && this.available()) {
          await this.port.send(report, state.stop.signal)
        }
      } catch { /* Optional delivery never changes memory work or forwards errors. */ }
      finally {
        if (report !== null) { try { await this.port.cancel(report) } catch { /* Spent budget remains. */ } }
        try { this.port.cleanup?.() } catch { /* Optional gauges cannot prevent shutdown. */ }
        if (this.active === state) this.active = undefined
      }
    })
  }

  pause(reason = 'lifecycle'): void { this.pauses.add(reason); this.active?.stop.abort() }
  resume(reason = 'lifecycle'): void { if (!this.closed) { this.pauses.delete(reason); this.nextCheck = 0 } }
  close(): void { this.closed = true; this.pause() }
  /** Lifecycle owners/tests may await cleanup; no shutdown report is created. */
  settled(): Promise<void> { return this.active?.done ?? Promise.resolve() }
}
