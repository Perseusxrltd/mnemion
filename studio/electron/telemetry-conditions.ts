/** Local current gauges, never report fields, network identifiers or a timer. */
import { cpus } from 'node:os'
import { setTimeout as delay } from 'node:timers/promises'
import type { TelemetryConditions } from './telemetry-activity.js'
import { NativeNetworkConditions } from './telemetry-network.js'

type CpuSample = { at: number; idle: number; total: number; count: number }

export class DesktopTelemetryConditions {
  private previous?: CpuSample
  private sampledAt = -Infinity
  private cpuConstrained = true
  constructor(private readonly platform: {
    online: () => boolean
    thermal: () => string
    metering?: () => TelemetryConditions['network']
  }, private readonly network = new NativeNetworkConditions()) {}

  async prepare(stop: AbortSignal): Promise<boolean> {
    if (stop.aborted || !this.platform.online() || !await this.network.start(stop)) return false
    this.read()
    // A first/stale CPU sample needs a real delta, inside this awake attempt.
    if (this.cpuConstrained) {
      try { await delay(250, undefined, { signal: stop, ref: false }) }
      catch { return false }
      this.read()
    }
    return !stop.aborted
  }
  close(): void { this.network.close() }

  read(): TelemetryConditions {
    try {
      const now = performance.now()
      // Reuse a sub-second CPU delta during the existing attempt's policy
      // checks. There is no sampling task or wake while the app is idle.
      if (now - this.sampledAt >= 250) {
        const cores = cpus()
        const current = { at: now, idle: 0, total: 0, count: cores.length }
        for (const { times } of cores) {
          current.idle += times.idle
          current.total += times.user + times.nice + times.sys + times.idle + times.irq
        }
        const prior = this.previous
        this.cpuConstrained = !prior || !cores.length || prior.count !== current.count ||
          now - prior.at > 120000 || current.total <= prior.total || current.idle < prior.idle ||
          (current.idle - prior.idle) / (current.total - prior.total) < 0.2
        this.previous = current
        this.sampledAt = now
      }
      const available = process.availableMemory(), thermal = this.platform.thermal()
      const network = this.network.read()
      const metering = network.network === 'metered' ? 'metered' : this.platform.metering?.() ?? network.network
      return { network: metering, constrained: network.constrained ||
        !this.platform.online() || this.cpuConstrained || !Number.isFinite(available) || available < 128 * 1024 * 1024 ||
        ['serious', 'critical'].includes(thermal) }
    } catch { return { network: 'unknown', constrained: true } }
  }
}
