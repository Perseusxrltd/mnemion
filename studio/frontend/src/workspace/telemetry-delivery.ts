/** Origin-wide reservations. No sender, idle timer, network request or identity. */
import specification from '../../../../mnemion/product_telemetry/wire-v1.json'
import type { TelemetryStamp, TelemetryStatus } from '../../../shared/product-telemetry'
import { TelemetryWire, secureRandomBelow } from '../../../electron/telemetry-wire'
import { pendingState, telemetryCatalog } from './telemetry-aggregate'
import { budgetKey, budgetState, choiceKey, queueKey, reserveBudget, serializeBudget,
  budgetView, clockValid, generationValid, DAY, DEADLINE, JITTER, MAX_CLOCK } from './telemetry-budget'
import { checkReview, checkReviewMetadata, clearReview, type ReviewContext, type ReviewMetadata, type ReviewReport, type ReviewState } from '../../../electron/telemetry-review'
import type { ReviewClock } from '../../../electron/telemetry-review-lifetime'
import { browserReviewContext } from './telemetry-review'

type Port = { storage: () => Storage; status: () => TelemetryStatus; reconcile: () => void; fail: () => void
  reviewClock?: () => ReviewClock | null; ensureReviewClock?: (epoch: string) => Promise<ReviewClock | null> }
export type BrowserDeliveryEnvironment = {
  locks: () => LockManager | null; now: () => number; monotonic: () => number
  events: () => Window | null
  conditions?: () => Network
}
type Network = { network: 'unknown' | 'metered' | 'unmetered'; constrained: boolean }

/** The private lease survives the one-use handoff until completion or abort. */
export class PreparedBrowserTelemetryReport {
  #body: Uint8Array
  #ticket: string
  #used = false
  #closed = false
  #claimed = false
  #transportClaimed = false
  #policyClaimed = false
  #review: ReviewMetadata | null
  constructor(body: Uint8Array, ticket: string, readonly stamp: Readonly<TelemetryStamp>,
    readonly deadline: number, readonly monotonicDeadline: number, readonly group: string, reviewed?: ReviewReport | null) {
    this.#body = new Uint8Array(body)
    this.#ticket = ticket
    this.stamp = Object.freeze({ ...stamp })
    this.#review = reviewed ? { stamp: { ...reviewed.stamp }, groups: [...reviewed.groups], binding: { ...reviewed.binding },
      lifetime: { ...reviewed.lifetime, clock: { ...reviewed.lifetime.clock } } } : null
  }
  get used(): boolean { return this.#used }
  get closed(): boolean { return this.#closed }
  get ticket(): string { return this.#ticket }
  body(): Uint8Array { return new Uint8Array(this.#body) }
  claimTransport(): boolean {
    if (this.#transportClaimed || this.#claimed || this.#used || this.#closed) return false
    this.#transportClaimed = true
    return true
  }
  claimHandoff(): boolean {
    if (this.#claimed || this.#used || this.#closed) return false
    this.#claimed = true
    return true
  }
  claimPolicyRead(): boolean {
    if (this.#policyClaimed || this.#claimed || this.#used || this.#closed) return false
    this.#policyClaimed = true
    return true
  }
  burn(): void { this.#used = true }
  eraseBody(): void { this.#body.fill(0) }
  get reviewed(): boolean { return this.#review !== null }
  reviewCurrent(context: ReviewContext, now: number, clock: ReviewClock | null): boolean {
    if (!this.#review) return true
    const checked = checkReviewMetadata(this.#review, context, now, clock)
    if (!checked) return false
    this.#review = checked
    return true
  }
  clear(): void { this.eraseBody(); this.#ticket = ''; this.#used = true; this.#closed = true; this.#review = null }
}

export class BrowserTelemetryDelivery {
  private encoder?: TelemetryWire
  private readonly owned = new Set<PreparedBrowserTelemetryReport>()
  private readonly cancellations = new WeakMap<PreparedBrowserTelemetryReport, Promise<void>>()
  private readonly invalidators = new Set<() => void>()
  private readonly environment: BrowserDeliveryEnvironment
  private localOperation: Promise<void> = Promise.resolve()
  private pendingOperations = 0
  constructor(private readonly port: Port, environment: Partial<BrowserDeliveryEnvironment> = {}) {
    this.environment = {
      locks: () => typeof navigator === 'undefined' ? null : navigator.locks ?? null,
      now: () => Date.now(), monotonic: () => performance.now(),
      events: () => typeof window === 'undefined' ? null : window, ...environment,
    }
  }

  private wire(): TelemetryWire { return this.encoder ??= new TelemetryWire(specification, telemetryCatalog) }

  formatExample() { return this.wire().formatExample() }
  packetPreview(packet: Uint8Array) { return this.wire().preview(packet) }
  prepareInspection(cells: number[][], groups: string[]): Uint8Array { return this.wire().prepare(cells, groups) }

  checkedReview(state: ReviewState, status: TelemetryStatus, now: number): ReviewState {
    if (!state.report) return state
    const checked = checkReview(state, status.effective_enabled ? browserReviewContext(status) : null, now, this.port.reviewClock?.() ?? null)
    if (checked.report) {
      try {
        const view = this.wire().decode(new Uint8Array(checked.report.packet)).view
        if (!status.company_policy.metric_groups.includes(this.wire().specification.views[view].group)) return clearReview(checked)
      } catch { return clearReview(checked) }
    }
    return checked
  }

  private async prepareReviewClock(stamp: TelemetryStamp): Promise<void> {
    const status = this.port.status()
    if (!status.effective_enabled || status.revision !== stamp.revision || status.store_generation !== stamp.store_generation) return
    const raw = this.port.storage().getItem(budgetKey)
    if (raw === null) return
    const budget = budgetState(raw)
    if (budget.review.outcome === 'approved' && budget.review.report && budgetView(budget, this.environment.now()).state === 'ready')
      await this.port.ensureReviewClock?.(budget.review.report.lifetime.clock.epoch)
  }

  /** Read-only preflight, including the report hold, before resource gauges. */
  async eligible(stamp: TelemetryStamp): Promise<boolean> {
    if (!stamp || !clockValid(stamp.revision, 2147483646) || !generationValid(stamp.store_generation)) return false
    try {
      await this.prepareReviewClock(stamp)
      return await this.locked(() => {
        const status = this.port.status(), now = this.environment.now()
        if (!status.effective_enabled || status.connection_mode === 'metered' ||
            status.revision !== stamp.revision || status.store_generation !== stamp.store_generation) return false
        const raw = this.port.storage().getItem(budgetKey)
        if (raw === null) return false
        const budget = budgetState(raw), view = budgetView(budget, now)
        if (budget.clear !== 'none' || budget.generation !== stamp.store_generation || view.state !== 'ready' || view.attempts_in_rolling_week! >= 7) return false
        const review = this.checkedReview(budget.review, status, now)
        if (review.mode === 'review') return review.outcome === 'approved' && review.report !== null
        const day = Math.floor(now / DAY)
        return pendingState(this.port.storage().getItem(queueKey)).entries.some(row => row.window_day >= day - 1 && row.window_day <= day &&
          status.company_policy.metric_groups.includes(telemetryCatalog.describe(row.cell).group))
      }, false)
    } catch { return false }
  }

  private async locked<T>(run: () => T, fallback: T): Promise<T> {
    // Serialize only this owner's short lock operations. A privacy watcher
    // must not compete with its own policy/report handoff after Web Locks
    // releases asynchronously. Other tabs still use nonwaiting ifAvailable.
    if (this.pendingOperations >= 4) return fallback
    this.pendingOperations++
    const preceding = this.localOperation
    let release = () => {}
    this.localOperation = new Promise<void>(resolve => { release = resolve })
    try {
      await preceding
      const locks = this.environment.locks()
      return locks ? await locks.request(choiceKey, { ifAvailable: true }, lock => lock ? run() : fallback) : fallback
    } catch { return fallback }
    finally { this.pendingOperations--; release() }
  }

  /** Called synchronously by the same tab's explicit privacy-choice mutation. */
  invalidate(): void {
    // cancel erases the handle synchronously and retains its ticket only in
    // the bounded cleanup closure. A later owner/finally must await that same
    // cleanup, including company restrictions without a configure() write.
    for (const report of [...this.owned]) void this.cancel(report)
    for (const stop of [...this.invalidators]) stop()
  }

  async reserve(stamp: TelemetryStamp, network: Network = { network: 'unknown', constrained: true },
    cohorts: unknown = {}): Promise<PreparedBrowserTelemetryReport | null> {
    if (!stamp || !clockValid(stamp.revision, 2147483646) || !generationValid(stamp.store_generation) ||
      !['unknown', 'unmetered'].includes(network.network) || network.constrained !== false) return null
    const expected = { revision: stamp.revision, store_generation: stamp.store_generation }
    try { await this.prepareReviewClock(expected) } catch { return null }
    const started = this.environment.monotonic()
    return this.locked(() => {
      let body: Uint8Array | undefined
      try {
        // Reconcile a crash between the write-ahead intent and queue cleanup.
        this.port.reconcile()
        const now = this.environment.now(), status = this.port.status()
        const observed = this.environment.conditions?.() ?? network
        if (!['unknown', 'unmetered'].includes(observed.network) || observed.constrained !== false) return null
        if (status.connection_mode === 'metered' ||
            (observed.network === 'unknown' && status.connection_mode !== 'unmetered')) return null
        if (!clockValid(now, MAX_CLOCK - DAY - JITTER) || !status.effective_enabled ||
          status.revision !== expected.revision || status.store_generation !== expected.store_generation ||
          this.environment.monotonic() - started >= DEADLINE) return null
        const raw = this.port.storage().getItem(budgetKey)
        if (raw === null) return null
        const budget = budgetState(raw), day = Math.floor(now / DAY)
        if (budget.generation !== expected.store_generation) return null
        const review = this.checkedReview(budget.review, status, now)
        let cells: number[][] = [], reviewed: ReviewReport | null = null
        if (review.mode === 'review') {
          if (review.outcome !== 'approved' || !review.report) {
            this.port.storage().setItem(budgetKey, serializeBudget({ ...budget, review }))
            return null
          }
          reviewed = review.report
          body = new Uint8Array(reviewed.packet)
        } else {
          const pending = pendingState(this.port.storage().getItem(queueKey))
          cells = pending.entries.filter(row => row.window_day >= day - 1 && row.window_day <= day &&
            status.company_policy.metric_groups.includes(telemetryCatalog.describe(row.cell).group))
            .map(row => [row.cell, row.count])
          if (!cells.length) return null
        }
        const ticket = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('')
        let next = reserveBudget(budget, now, ticket, secureRandomBelow(JITTER / 1000 + 1) * 1000)
        if (!next) return null
        if (reviewed) next = { ...next, clear: 'none', review: clearReview(review, 'consumed') }
        else body = this.wire().prepare(cells, status.company_policy.metric_groups, cohorts)
        if (!body) return null
        if (this.environment.monotonic() - started >= DEADLINE) return null
        // No refund on failure, crash, opt-out or reload. Contributions remain.
        this.port.storage().setItem(budgetKey, serializeBudget(next))
        this.port.reconcile()
        if (this.environment.monotonic() - started >= DEADLINE) return null
        const group = this.wire().specification.views[this.wire().decode(body).view].group
        const report = new PreparedBrowserTelemetryReport(body, ticket, expected, now + DEADLINE, started + DEADLINE, group, reviewed)
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
    if (this.environment.conditions) {
      const observed = this.environment.conditions()
      if (observed.constrained !== false || !['unknown', 'unmetered'].includes(observed.network) ||
          (observed.network === 'unknown' && status.connection_mode !== 'unmetered')) return false
    }
    const raw = this.port.storage().getItem(budgetKey)
    if (raw === null) return false
    const budget = budgetState(raw)
    if (report.reviewed && !report.reviewCurrent(browserReviewContext(status), now, this.port.reviewClock?.() ?? null)) return false
    return clockValid(now) && this.environment.monotonic() < report.monotonicDeadline &&
      budget.clear === 'none' && budget.clock_ms <= now && now < report.deadline &&
      budget.lease?.deadline_ms === report.deadline && budget.lease.token === report.ticket &&
      budget.generation === report.stamp.store_generation && status.effective_enabled && status.connection_mode !== 'metered' &&
      status.revision === report.stamp.revision && status.store_generation === report.stamp.store_generation &&
      status.company_policy.metric_groups.includes(report.group)
  }

  async current(report: PreparedBrowserTelemetryReport): Promise<boolean> {
    const valid = await this.locked(() => this.permitted(report), false)
    if (!valid) await this.cancel(report)
    return valid
  }

  async cancel(report: PreparedBrowserTelemetryReport): Promise<void> {
    const pending = this.cancellations.get(report)
    if (pending) return pending
    if (!this.owned.has(report)) return
    const ticket = report.ticket
    report.clear(); this.owned.delete(report)
    const cleanup = this.locked(() => {
      const raw = this.port.storage().getItem(budgetKey)
      if (raw === null) return
      const budget = budgetState(raw)
      if (budget.lease?.token === ticket) this.port.storage().setItem(budgetKey, serializeBudget({ ...budget, lease: null }))
    }, undefined)
    this.cancellations.set(report, cleanup)
    await cleanup
  }

  /** The single same-origin policy request has no measurement body and must
   * pass the same current choice, pressure, lease and budget checks. */
  async guardedPolicyRead(report: PreparedBrowserTelemetryReport, start: () => boolean): Promise<boolean> {
    if (!this.owned.has(report) || typeof start !== 'function' || !report.claimPolicyRead()) return false
    if (start.constructor?.name === 'AsyncFunction') { await this.cancel(report); return false }
    const started = await this.locked(() => this.permitted(report) && start() === true, false)
    if (!started) await this.cancel(report)
    return started
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
  async watch(report: PreparedBrowserTelemetryReport, abort: () => void, stop: AbortSignal, handoff?: Promise<void>): Promise<void> {
    let timer: ReturnType<typeof setTimeout> | undefined, checking = false, done = false
    let armed = handoff === undefined
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
      if (done || checking || !armed) return
      if (timer !== undefined) clearTimeout(timer)
      checking = true
      const valid = await this.current(report)
      checking = false
      if (!done) { if (!valid) finish(true); else timer = setTimeout(check, 25) }
    }
    const changed = (event: StorageEvent) => {
      if (event.key === null || [choiceKey, budgetKey].includes(event.key)) {
        if (armed) void check(); else invalidate()
      }
    }
    this.invalidators.add(invalidate)
    events?.addEventListener('storage', changed)
    events?.addEventListener('pagehide', invalidate)
    stop.addEventListener('abort', stopped, { once: true })
    // Install cancellation listeners before Fetch can start, but let its
    // privacy lock finish before this same attempt polls that lock again.
    if (stop.aborted) stopped()
    else if (handoff) void handoff.then(() => { armed = true; void check() }, invalidate)
    else void check()
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
