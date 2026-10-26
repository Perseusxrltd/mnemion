/** Local current gauges, never report fields, network identifiers or a timer. */
import { setTimeout as delay } from 'node:timers/promises'
import type { TelemetryConditions } from './telemetry-activity.js'
import { NativeNetworkConditions } from './telemetry-network.js'
import { readCpuTotals, type CpuTotals } from './telemetry-cpu.js'

type CpuSample = CpuTotals & { at: number }

export class DesktopTelemetryConditions {
  private previous?: CpuSample
  private sampledAt = -Infinity
  private cpuConstrained = true
  constructor(private readonly platform: {
    online: () => boolean
    thermal: () => string
    metering?: () => TelemetryConditions['network']
  }, private readonly network = new NativeNetworkConditions(),
  private readonly cpu = readCpuTotals, private readonly clock = () => performance.now()) {}

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
      const now = this.clock()
      if (!Number.isFinite(now) || now < this.sampledAt) {
        this.previous = undefined; this.sampledAt = -Infinity; this.cpuConstrained = true
        return { network: 'unknown', constrained: true }
      }
      // Reuse a sub-second CPU delta during the existing attempt's policy
      // checks. There is no sampling task or wake while the app is idle.
      if (now - this.sampledAt >= 250) {
        const totals = this.cpu()
        const current = totals ? { ...totals, at: now } : undefined
        const prior = this.previous
        // Counter units can differ by provider. Hotplug, fallback transitions,
        // resets and unknown samples always need two new comparable readings.
        this.cpuConstrained = !prior || !current || prior.source !== current.source || prior.count !== current.count ||
          now - prior.at > 120000 || current.total <= prior.total || current.idle < prior.idle ||
          current.idle - prior.idle > current.total - prior.total ||
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
    } catch {
      this.previous = undefined; this.sampledAt = -Infinity; this.cpuConstrained = true
      return { network: 'unknown', constrained: true }
    }
  }
}
