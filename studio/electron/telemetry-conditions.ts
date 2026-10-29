/** Local current gauges, never report fields, network identifiers or a timer. */
import { setTimeout as delay } from 'node:timers/promises'
import type { TelemetryConditions } from './telemetry-activity.js'
import { NativeNetworkConditions } from './telemetry-network.js'
import { readCpuTotals, type CpuTotals } from './telemetry-cpu.js'

type CpuSample = CpuTotals & { at: number }

const guardNetworks = ['unknown', 'metered', 'unmetered'] as const
const guardReasons = ['allowed', 'clock', 'network_not_allowed', 'network_constrained', 'offline',
  'cpu_busy', 'cpu_unobserved', 'memory', 'thermal', 'read_failed'] as const

/** Fixed fields from one opted-in admission read. Not a report, a cohort, or a delivery input. */
export type AdmissionGuard = {
  schema_version: 1
  network: (typeof guardNetworks)[number]
  constrained: boolean
  reason: (typeof guardReasons)[number]
}

export function copyAdmissionGuard(value: unknown): AdmissionGuard | null {
  if (!value || typeof value !== 'object') return null
  const record = value as Partial<AdmissionGuard>
  if (record.schema_version !== 1 || typeof record.constrained !== 'boolean') return null
  if (!guardNetworks.includes(record.network as AdmissionGuard['network'])) return null
  if (!guardReasons.includes(record.reason as AdmissionGuard['reason'])) return null
  return { schema_version: 1, network: record.network as AdmissionGuard['network'],
    constrained: record.constrained, reason: record.reason as AdmissionGuard['reason'] }
}

export class DesktopTelemetryConditions {
  private previous?: CpuSample
  private sampledAt = -Infinity
  private cpuConstrained = true
  /** Class of the CPU sample taken while tracing, so a reuse inside 250 ms stays the same class. */
  private cpuAdmission?: 'unobserved' | 'busy' | 'clear'
  /** Present only after a traced read. Ordinary reads do not allocate one. */
  admissionGuard?: AdmissionGuard
  /** Off unless the owned attribution wrapper sets it before read(). */
  traceAdmission = false
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
    const trace = this.traceAdmission
    try {
      const now = this.clock()
      if (!Number.isFinite(now) || now < this.sampledAt) {
        this.previous = undefined; this.sampledAt = -Infinity; this.cpuConstrained = true
        this.cpuAdmission = undefined
        if (trace) this.admissionGuard = { schema_version: 1, network: 'unknown', constrained: true, reason: 'clock' }
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
        const incomparable = !prior || !current || prior.source !== current.source || prior.count !== current.count ||
          now - prior.at > 120000 || current.total <= prior.total || current.idle < prior.idle ||
          current.idle - prior.idle > current.total - prior.total
        const busy = !incomparable && current !== undefined && prior !== undefined &&
          (current.idle - prior.idle) / (current.total - prior.total) < 0.2
        this.cpuConstrained = incomparable || busy
        this.cpuAdmission = trace ? (incomparable ? 'unobserved' : busy ? 'busy' : 'clear') : undefined
        this.previous = current
        this.sampledAt = now
      }
      const available = process.availableMemory(), thermal = this.platform.thermal()
      const network = this.network.read()
      const metering = network.network === 'metered' ? 'metered' : this.platform.metering?.() ?? network.network
      // online() stays in this short-circuit: it runs only when the network is not already constrained.
      let online = false
      let constrained = network.constrained
      if (!constrained) {
        online = this.platform.online()
        constrained = !online || this.cpuConstrained || !Number.isFinite(available) || available < 128 * 1024 * 1024 ||
          ['serious', 'critical'].includes(thermal)
      }
      if (trace) {
        const reason: AdmissionGuard['reason'] = metering === 'metered' ? 'network_not_allowed'
          : network.constrained ? 'network_constrained'
          : !online ? 'offline'
          : this.cpuConstrained ? (this.cpuAdmission === 'busy' ? 'cpu_busy' : 'cpu_unobserved')
          : !Number.isFinite(available) || available < 128 * 1024 * 1024 ? 'memory'
          : ['serious', 'critical'].includes(thermal) ? 'thermal'
          : 'allowed'
        this.admissionGuard = { schema_version: 1, network: metering, constrained, reason }
      }
      return { network: metering, constrained }
    } catch {
      this.previous = undefined; this.sampledAt = -Infinity; this.cpuConstrained = true
      this.cpuAdmission = undefined
      if (trace) this.admissionGuard = { schema_version: 1, network: 'unknown', constrained: true, reason: 'read_failed' }
      return { network: 'unknown', constrained: true }
    }
  }
}
