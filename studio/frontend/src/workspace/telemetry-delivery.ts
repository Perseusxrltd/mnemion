/** Origin-wide reservations. No sender, idle timer, network request or identity. */
import specification from '../../../../mnemion/product_telemetry/wire-v1.json'
import type { TelemetryStamp, TelemetryStatus } from '../../../shared/product-telemetry'
import { TelemetryWire, secureRandomBelow } from '../../../electron/telemetry-wire'
import { pendingState, telemetryCatalog } from './telemetry-aggregate'
import { budgetKey, budgetState, choiceKey, queueKey, reserveBudget, serializeBudget,
  clockValid, generationValid, DAY, DEADLINE, JITTER, MAX_CLOCK } from './telemetry-budget'

type Port = { storage: () => Storage; status: () => TelemetryStatus; reconcile: () => void; fail: () => void }
export type BrowserDeliveryEnvironment = {
  locks: () => LockManager | null; now: () => number; monotonic: () => number
  events: () => Window | null
}
type Network = { network: 'unknown' | 'metered' | 'unmetered'; constrained: boolean }

/** The private lease survives the one-use handoff until completion or abort. */
export class PreparedBrowserTelemetryReport {
  #body: Uint8Array
  #ticket: string
  #used = false
  #closed = false
  #claimed = false
  constructor(body: Uint8Array, ticket: string, readonly stamp: Readonly<TelemetryStamp>,
    readonly deadline: number, readonly monotonicDeadline: number, readonly group: string) {
    this.#body = new Uint8Array(body)
    this.#ticket = ticket
    this.stamp = Object.freeze({ ...stamp })
  }
  get used(): boolean { return this.#used }
  get closed(): boolean { return this.#closed }
  get ticket(): string { return this.#ticket }
  body(): Uint8Array { return new Uint8Array(this.#body) }
  claimHandoff(): boolean {
    if (this.#claimed || this.#used || this.#closed) return false
    this.#claimed = true
    return true
  }
  burn(): void { this.#used = true }
  eraseBody(): void { this.#body.fill(0) }
  clear(): void { this.eraseBody(); this.#ticket = ''; this.#used = true; this.#closed = true }
}

export class BrowserTelemetryDelivery {
  private encoder?: TelemetryWire
  private readonly owned = new Set<PreparedBrowserTelemetryReport>()
  private readonly invalidators = new Set<() => void>()
  private readonly environment: BrowserDeliveryEnvironment
  constructor(private readonly port: Port, environment: Partial<BrowserDeliveryEnvironment> = {}) {
    this.environment = {
      locks: () => typeof navigator === 'undefined' ? null : navigator.locks ?? null,
      now: () => Date.now(), monotonic: () => performance.now(),
      events: () => typeof window === 'undefined' ? null : window, ...environment,
    }
  }

  private wire(): TelemetryWire { return this.encoder ??= new TelemetryWire(specification, telemetryCatalog) }

  private async locked<T>(run: () => T, fallback: T): Promise<T> {
    try {
      const locks = this.environment.locks()
      return locks ? await locks.request(choiceKey, { ifAvailable: true }, lock => lock ? run() : fallback) : fallback
    } catch { return fallback }
  }

  /** Called synchronously by the same tab's explicit privacy-choice mutation. */
  invalidate(): void {
    for (const report of this.owned) report.clear()
    this.owned.clear()
    for (const stop of [...this.invalidators]) stop()
  }

  async reserve(stamp: TelemetryStamp, network: Network = { network: 'unknown', constrained: true },
    cohorts: unknown = {}): Promise<PreparedBrowserTelemetryReport | null> {
    if (!stamp || !clockValid(stamp.revision, 2147483646) || !generationValid(stamp.store_generation) ||
      network.network !== 'unmetered' || network.constrained !== false) return null
    const expected = { revision: stamp.revision, store_generation: stamp.store_generation }
    const started = this.environment.monotonic()
    return this.locked(() => {
      let body: Uint8Array | undefined
      try {
        // Reconcile a crash between the write-ahead intent and queue cleanup.
        this.port.reconcile()
        const now = this.environment.now(), status = this.port.status()
        if (!clockValid(now, MAX_CLOCK - DAY - JITTER) || !status.effective_enabled ||
          status.revision !== expected.revision || status.store_generation !== expected.store_generation ||
          this.environment.monotonic() - started >= DEADLINE) return null
        const raw = this.port.storage().getItem(budgetKey)
        if (raw === null) return null
        const budget = budgetState(raw), day = Math.floor(now / DAY)
        if (budget.generation !== expected.store_generation) return null
        const pending = pendingState(this.port.storage().getItem(queueKey))
        const cells = pending.entries.filter(row => row.window_day >= day - 1 && row.window_day <= day &&
          status.company_policy.metric_groups.includes(telemetryCatalog.describe(row.cell).group))
          .map(row => [row.cell, row.count])
        if (!cells.length) return null
        const ticket = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('')
        const next = reserveBudget(budget, now, ticket, secureRandomBelow(JITTER / 1000 + 1) * 1000)
        if (!next) return null
        body = this.wire().prepare(cells, status.company_policy.metric_groups, cohorts)
        if (this.environment.monotonic() - started >= DEADLINE) return null
        // No refund on failure, crash, opt-out or reload. Contributions remain.
        this.port.storage().setItem(budgetKey, serializeBudget(next))
        this.port.reconcile()
        if (this.environment.monotonic() - started >= DEADLINE) return null
        const group = this.wire().specification.views[this.wire().decode(body).view].group
        const report = new PreparedBrowserTelemetryReport(body, ticket, expected, now + DEADLINE, started + DEADLINE, group)
        // An abandoned expired handle must not accumulate over later days.
        this.invalidate()
        this.owned.add(report)
        return report
      } catch { this.port.fail(); return null }
      finally { body?.fill(0) }
    }, null)
  }

  private permitted(report: PreparedBrowserTelemetryReport): boolean {
    if (!this.owned.has(report) || report.closed) return false
    const now = this.environment.now(), status = this.port.status()
    const raw = this.port.storage().getItem(budgetKey)
    if (raw === null) return false
    const budget = budgetState(raw)
    return clockValid(now) && this.environment.monotonic() < report.monotonicDeadline &&
      budget.clear === 'none' && budget.clock_ms <= now && now < report.deadline &&
      budget.lease?.deadline_ms === report.deadline && budget.lease.token === report.ticket &&
      budget.generation === report.stamp.store_generation && status.effective_enabled &&
      status.revision === report.stamp.revision && status.store_generation === report.stamp.store_generation &&
      status.company_policy.metric_groups.includes(report.group)
  }

  async current(report: PreparedBrowserTelemetryReport): Promise<boolean> {
    const valid = await this.locked(() => this.permitted(report), false)
    if (!valid) await this.cancel(report)
    return valid
  }

  async cancel(report: PreparedBrowserTelemetryReport): Promise<void> {
    if (!this.owned.has(report)) return
    const ticket = report.ticket
    report.clear(); this.owned.delete(report)
    await this.locked(() => {
      const raw = this.port.storage().getItem(budgetKey)
      if (raw === null) return
      const budget = budgetState(raw)
      if (budget.lease?.token === ticket) this.port.storage().setItem(budgetKey, serializeBudget({ ...budget, lease: null }))
    }, undefined)
  }

  /** Only a synchronous nonblocking transport handoff may run inside this lock.
   * A successful handoff stays cancellable; its owner must finish with cancel(). */
  async guardedWrite(report: PreparedBrowserTelemetryReport, write: (body: Uint8Array) => boolean): Promise<boolean> {
    if (!this.owned.has(report) || typeof write !== 'function' || !report.claimHandoff()) return false
    if (write.constructor?.name === 'AsyncFunction') { await this.cancel(report); return false }
    let owned = false
    const written = await this.locked(() => {
      if (report.used) return false
      owned = true
      if (!this.permitted(report)) return false
      report.burn()
      const body = report.body()
      try { return write(body) === true }
      finally { body.fill(0); report.eraseBody() }
    }, false)
    if (!written && (owned || !report.used)) await this.cancel(report)
    return written
  }

  /** Listeners and bounded polling exist only during an owned active attempt. */
  async watch(report: PreparedBrowserTelemetryReport, abort: () => void, stop: AbortSignal): Promise<void> {
    let timer: ReturnType<typeof setTimeout> | undefined, checking = false, done = false
    let finish = (_cancel: boolean) => {}
    const events = this.environment.events()
    const ended = new Promise<void>(resolve => {
      finish = cancel => {
        if (done) return
        done = true
        if (timer !== undefined) clearTimeout(timer)
        if (cancel) { try { abort() } catch { /* No exception forwarding or retry. */ } }
        resolve()
      }
    })
    const invalidate = () => finish(true), stopped = () => finish(false)
    const check = async () => {
      if (done || checking) return
      if (timer !== undefined) clearTimeout(timer)
      checking = true
      const valid = await this.current(report)
      checking = false
      if (!done) { if (!valid) finish(true); else timer = setTimeout(check, 25) }
    }
    const changed = (event: StorageEvent) => {
      if (event.key === null || [choiceKey, budgetKey].includes(event.key)) void check()
    }
    this.invalidators.add(invalidate)
    events?.addEventListener('storage', changed)
    events?.addEventListener('pagehide', invalidate)
    stop.addEventListener('abort', stopped, { once: true })
    if (stop.aborted) stopped(); else void check()
    try { await ended }
    finally {
      if (timer !== undefined) clearTimeout(timer)
      this.invalidators.delete(invalidate)
      events?.removeEventListener('storage', changed)
      events?.removeEventListener('pagehide', invalidate)
      stop.removeEventListener('abort', stopped)
      await this.cancel(report)
    }
  }
}
