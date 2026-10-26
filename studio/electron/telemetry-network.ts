/** Existing awake attempts own OS probes. No timer, identity or Internet call. */
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import type { TelemetryConditions } from './telemetry-activity.js'

type Probe = () => Promise<number>
let binding: { readState: Probe; readCpuTotals?: () => unknown; readReviewClock?: () => unknown;
  initializeReviewClock?: () => unknown } | false | undefined
function nativeBinding() {
  if (binding === undefined) {
    try {
      const path = fileURLToPath(new URL('./telemetry-network.node', import.meta.url))
        .replace(/([\\/])app\.asar([\\/])/, '$1app.asar.unpacked$2')
      const loaded = createRequire(import.meta.url)(path)
      binding = typeof loaded?.readState === 'function' ? loaded : false
    } catch { binding = false }
  }
  return binding
}

async function nativeState(): Promise<number> {
  const loaded = nativeBinding()
  return loaded ? loaded.readState() : 0
}

/** Aggregate counters only. Older/missing binaries retain the Node fallback. */
export function nativeCpuTotals(): unknown {
  const loaded = nativeBinding()
  return loaded && typeof loaded.readCpuTotals === 'function' ? loaded.readCpuTotals() : null
}

/** Only an explicit inspection action may initialize a local epoch marker. */
export function nativeReviewClock(initialize = false): unknown {
  const loaded = nativeBinding()
  if (!loaded) return null
  const read = initialize ? loaded.initializeReviewClock : loaded.readReviewClock
  return typeof read === 'function' ? read() : null
}

export function networkFlags(value: unknown): TelemetryConditions & { observed: boolean } {
  if (![0, 8, 9, 10, 12, 13, 14].includes(value as number)) return { network: 'unknown', constrained: true, observed: false }
  const bits = value as number
  return { network: bits & 2 ? 'metered' : bits & 1 ? 'unmetered' : 'unknown',
    constrained: Boolean(bits & 4), observed: Boolean(bits & 8) }
}

export class NativeNetworkConditions {
  private active = false
  private generation = 0
  private sampledAt = -Infinity
  private attemptedAt = -Infinity
  private value = networkFlags(0)
  private pending?: Promise<void>
  constructor(private readonly probe: Probe = nativeState, private readonly now = () => performance.now()) {}

  private refresh(): Promise<void> {
    if (this.pending || !this.active) return this.pending ?? Promise.resolve()
    const generation = this.generation
    const started = this.now()
    this.attemptedAt = started
    const task = Promise.resolve().then(() => this.active && this.generation === generation ? this.probe() : 0).then(value => {
      if (!this.active || this.generation !== generation) return
      const next = networkFlags(value)
      // A missing capability cannot erase an earlier observed restriction.
      if (next.observed || (!this.value.constrained && this.value.network !== 'metered')) this.value = next
      this.sampledAt = started
    }, () => {
      if (this.active && this.generation === generation) {
        this.value = { ...this.value, constrained: true }; this.sampledAt = started
      }
    }).finally(() => { if (this.pending === task) this.pending = undefined })
    this.pending = task
    return task
  }

  async start(stop: AbortSignal): Promise<boolean> {
    this.active = true; this.generation++; this.sampledAt = -Infinity; this.attemptedAt = -Infinity
    const generation = this.generation
    let timer: ReturnType<typeof setTimeout> | undefined, finish = () => {}
    const ended = new Promise<void>(resolve => { finish = resolve })
    const aborted = () => { this.close(); finish() }
    stop.addEventListener('abort', aborted, { once: true })
    try {
      if (stop.aborted) { aborted(); return false }
      timer = setTimeout(aborted, 1000); timer.unref()
      // An old call may still be returning from the OS after cancellation.
      // Never queue a second call behind it or adopt its stale result.
      if (this.pending) await Promise.race([this.pending, ended])
      if (this.active && this.generation === generation) await Promise.race([this.refresh(), ended])
      return this.active && this.generation === generation && !stop.aborted && Number.isFinite(this.sampledAt)
    } finally { if (timer) clearTimeout(timer); stop.removeEventListener('abort', aborted) }
  }

  read(): TelemetryConditions {
    const now = this.now()
    if (!this.active || !Number.isFinite(now)) return { network: 'unknown', constrained: true }
    if (now - this.attemptedAt >= 250) void this.refresh()
    if (now < this.sampledAt || now - this.sampledAt >= 1000) return { network: this.value.network === 'metered' ? 'metered' : 'unknown', constrained: true }
    return { network: this.value.network, constrained: this.value.constrained }
  }
  close(): void { this.active = false; this.generation++; this.sampledAt = -Infinity }
}
