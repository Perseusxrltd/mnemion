/** Web delivery is owned by the already-active page, never a service worker. */
import { TelemetryActivity } from '../../../electron/telemetry-owner'
import { BrowserConditions } from './telemetry-conditions'
import { reviewedBrowserCohorts } from './telemetry-cohorts'
import type { BrowserTelemetry } from './telemetry-policy'
import type { TelemetryStamp } from '../../../shared/product-telemetry'
import { networkKindAllows, type PreparedBrowserTelemetryReport } from './telemetry-delivery'

export class BrowserTelemetryActivity {
  readonly conditions = new BrowserConditions()
  private readonly activity: TelemetryActivity<PreparedBrowserTelemetryReport>
  private cleanup?: () => void
  private stop?: AbortController
  private hidden = false
  constructor(private readonly client: BrowserTelemetry) {
    this.activity = new TelemetryActivity({
      available: () => !this.hidden && this.client.status().effective_enabled && document.visibilityState === 'visible',
      reserve: async (stamp, ownerStop) => {
        if (ownerStop.aborted) return null
        const status = this.client.status()
        if (status.connection_mode === 'metered' || status.delivery_budget?.state !== 'ready') return null
        // Eligibility can wait on origin-wide coordination. A choice change
        // or page exit during that wait must not start new sensor work.
        if (!await this.client.delivery.eligible(stamp) || ownerStop.aborted) return null
        if (!networkKindAllows(this.client.status().connection_mode, this.conditions.read().network)) return null
        const stop = this.stop = new AbortController()
        const paused = () => stop.abort()
        const hidden = () => { if (document.visibilityState !== 'visible') paused() }
        const connection = this.conditions.connection()
        window.addEventListener('pagehide', paused)
        window.addEventListener('offline', paused)
        document.addEventListener('visibilitychange', hidden)
        connection?.addEventListener('change', paused)
        this.cleanup = () => {
          ownerStop.removeEventListener('abort', paused)
          window.removeEventListener('pagehide', paused); window.removeEventListener('offline', paused)
          document.removeEventListener('visibilitychange', hidden); connection?.removeEventListener('change', paused)
          this.conditions.close(); stop.abort(); this.stop = undefined
        }
        ownerStop.addEventListener('abort', paused, { once: true })
        if (ownerStop.aborted) paused()
        let report: PreparedBrowserTelemetryReport | null = null
        try {
          if (stop.signal.aborted || !await this.conditions.start(stop.signal) || stop.signal.aborted) return null
          report = await this.client.delivery.reserve(stamp, this.conditions.read(), reviewedBrowserCohorts())
          return report
        } finally {
          // Keep observations only while a real prepared report has an owner.
          if (report === null) this.release()
        }
      },
      send: async (report, stop) => {
        const abort = () => this.stop?.abort()
        stop.addEventListener('abort', abort, { once: true })
        try {
          if (stop.aborted) abort()
          const { sendBrowserTelemetry } = await import('./telemetry-transport')
          if (!this.stop || this.stop.signal.aborted) return
          await sendBrowserTelemetry(this.client, report, this.stop.signal)
        } finally { stop.removeEventListener('abort', abort) }
      },
      cancel: async report => { try { await this.client.delivery.cancel(report) } finally { this.release() } },
    })
    // Capture pagehide even between recording and the deferred dispatch. These
    // page-owned listeners do not run a task or wake a dormant browser.
    if (typeof window !== 'undefined') {
      window.addEventListener('pagehide', () => {
        this.hidden = true; this.client.reviewClock.close(); this.stop?.abort(); this.activity.pause('page')
      })
      window.addEventListener('pageshow', () => { this.hidden = false; this.activity.resume('page') })
    }
  }
  offer(stamp: TelemetryStamp): void { this.activity.offer(stamp) }
  awake(): void { this.activity.awake() }
  offerApproved(stamp: TelemetryStamp): void { this.activity.offer(stamp, true) }
  invalidate(): void { this.stop?.abort(); this.activity.pause('choice'); this.activity.resume('choice') }
  private release(): void { this.cleanup?.(); this.cleanup = undefined }
}
