/** Shared private reservations and final-write fences. No sender or scheduler. */
import { randomBytes, randomInt } from 'node:crypto'
import { readFileSync } from 'node:fs'
import type { DatabaseSync } from 'node:sqlite'
import { setTimeout as delay } from 'node:timers/promises'
import type { TelemetryStamp } from '../shared/product-telemetry.js'
import { TelemetryWireV3 } from './telemetry-wire-v3.js'
import { cohortOperatingSystem, reviewedDesktopOperatingSystem, reviewedDesktopRelease } from './telemetry-cohorts.js'
import { telemetryWireResource } from './telemetry-resources.js'
import { NativeTelemetryStore, nativeCompanyPolicyPath, type NativeTelemetryDisclosure } from './telemetry-store.js'
import type { MeasurementCatalog } from './telemetry-catalog.js'
import { checkReview, checkReviewMetadata, clearReview, loadReview, reviewContext, serializeReview,
  type ReviewContext, type ReviewMetadata, type ReviewReport, type ReviewState } from './telemetry-review.js'
import { readReviewClock } from './telemetry-review-clock.js'
import type { ReviewClock } from './telemetry-review-lifetime.js'
import { nativeTelemetryRoute } from './telemetry-route.js'

const DAY = 86400000, WEEK = 7 * DAY, DEADLINE = 5000, JITTER = 3600000
const MAX_CLOCK = 86400000000000, COST = 65536, DAILY_BYTES = 256 * 1024
const integer = (value: unknown, max = MAX_CLOCK): value is number =>
  typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 && value <= max
const token = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{32}$/.test(value)
const invalid = () => new Error('telemetry_delivery_unavailable')
type State = { clock_ms: number; next_ms: number; lease_token: string | null; lease_deadline_ms: number }
type Spent = { slot: number; at_ms: number; reserved_bytes: number }
type Network = { network: 'unknown' | 'metered' | 'unmetered'; constrained: boolean }

function state(database: DatabaseSync, version = database.prepare('PRAGMA user_version').get()?.user_version): { current: State; spent: Spent[] } {
  if (version !== 6) throw invalid()
  const row = database.prepare('SELECT clock_ms, next_ms, lease_token, lease_deadline_ms FROM delivery_state WHERE singleton=1').get()
  if (!row || !integer(row.clock_ms) || !integer(row.next_ms) || !integer(row.lease_deadline_ms) ||
      (row.lease_token !== null && !token(row.lease_token)) ||
      (row.lease_token === null) !== (row.lease_deadline_ms === 0) || row.next_ms < row.clock_ms) throw invalid()
  const highWater = row.clock_ms
  const spent = database.prepare('SELECT slot, at_ms, reserved_bytes FROM delivery_attempts ORDER BY slot LIMIT 8').all()
  if (spent.length > 7 || spent.some(item => !integer(item.slot, 6) || !integer(item.at_ms) ||
      item.at_ms > highWater || item.reserved_bytes !== COST)) throw invalid()
  if (spent.length) {
    if (Math.max(...spent.map(item => Number(item.at_ms))) !== highWater || row.next_ms < highWater + DAY ||
        row.next_ms > highWater + DAY + JITTER || (row.lease_token !== null && row.lease_deadline_ms !== highWater + DEADLINE)) throw invalid()
  } else if (highWater !== 0 || row.next_ms !== 0 || row.lease_token !== null || row.lease_deadline_ms !== 0) throw invalid()
  return { current: row as State, spent: spent as Spent[] }
}

/** Lease identity stays in this process and the private database, never the body. */
export class PreparedTelemetryReport {
  #body: Uint8Array
  #token: string
  #used = false
  #closed = false
  #groups: readonly string[]
  #claimed = false
  #transportClaimed = false
  #review: ReviewMetadata | null
  constructor(body: Uint8Array, ticket: string, readonly stamp: Readonly<TelemetryStamp>, readonly deadline: number,
    readonly monotonicDeadline: number, groups: readonly string[], reviewed?: ReviewReport | null) {
    this.#body = new Uint8Array(body)
    this.#token = ticket
    this.#groups = Object.freeze([...groups])
    this.stamp = Object.freeze({ ...stamp })
    this.#review = reviewed ? { stamp: { ...reviewed.stamp }, groups: [...reviewed.groups], binding: { ...reviewed.binding },
      lifetime: { ...reviewed.lifetime, clock: { ...reviewed.lifetime.clock } } } : null
  }
  get used(): boolean { return this.#used }
  get closed(): boolean { return this.#closed }
  get groups(): readonly string[] { return this.#groups }
  permits(current: readonly string[]): boolean {
    return this.#groups.length > 0 && this.#groups.every(group => current.includes(group))
  }
  get ticket(): string { return this.#token }
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
  clear(): void { this.eraseBody(); this.#token = ''; this.#used = true; this.#closed = true; this.#review = null }
}

export class NativeTelemetryDelivery extends NativeTelemetryStore {
  private encoder?: TelemetryWireV3
  private routeAddress: string | null | undefined
  constructor(root: string, disclosure: NativeTelemetryDisclosure, catalog: MeasurementCatalog,
    companyFile = nativeCompanyPolicyPath(), private readonly now = () => Date.now(),
    private readonly monotonic = () => performance.now(), private readonly environment?: () => Network) {
    super(root, disclosure, catalog, companyFile)
  }

  private wire(): TelemetryWireV3 {
    this.encoder ??= new TelemetryWireV3(JSON.parse(readFileSync(new URL(`./${telemetryWireResource}`, import.meta.url), 'utf8')), this.catalog)
    return this.encoder
  }

  private reviewContext(stamp: TelemetryStamp, groups: string[]): ReviewContext {
    if (this.routeAddress === undefined) {
      // This is immutable release input, shared by every inspection/lease check.
      this.routeAddress = nativeTelemetryRoute()?.address ?? null
    }
    return reviewContext({ stamp, groups, binding: { disclosure_version: this.disclosure.version,
      wire_version: this.wire().specification.version, catalog_version: this.catalog.specification.version,
      destination: this.disclosure.destination, route_address: this.routeAddress } })
  }

  private reviewState(database: DatabaseSync, stamp: TelemetryStamp, groups: string[], now: number): ReviewState {
    const state = loadReview(database.prepare('SELECT state FROM report_review WHERE singleton=1').get()?.state)
    if (!state.report) return state
    const checked = checkReview(state, this.reviewContext(stamp, groups), now, readReviewClock())
    if (checked.report && !this.wire().matchesGroups(new Uint8Array(checked.report.packet), checked.report.groups)) {
      return clearReview(checked)
    }
    return checked
  }

  /** Read-only preflight before any OS gauge; final reservation rechecks it. */
  async eligible(stamp: TelemetryStamp): Promise<boolean> {
    if (!this.available || !stamp || !integer(stamp.revision, 2147483646) || !token(stamp.store_generation)) return false
    let database: DatabaseSync | undefined
    try {
      database = await this.open()
      database.exec('BEGIN')
      const preference = this.preferences(database), company = this.company(), now = this.now()
      const { current, spent } = state(database, preference.schema_version)
      const permitted = integer(now, MAX_CLOCK - DAY - JITTER) && preference.enabled === 1 &&
        preference.disclosure_version === this.disclosure.version && preference.connection_mode !== 'metered' &&
        preference.revision === stamp.revision && preference.store_generation === stamp.store_generation &&
        company.enabled && company.groups.length > 0 && now >= current.clock_ms && now >= current.next_ms &&
        !(current.lease_token && now < current.lease_deadline_ms) && spent.filter(item => item.at_ms > now - WEEK).length < 7
      if (!permitted) return false
      const review = this.reviewState(database, stamp, company.groups, now)
      return review.mode === 'review' ? review.outcome === 'approved' && review.report !== null
        : Boolean(database.prepare('SELECT 1 FROM pending WHERE window_day >= ? AND window_day <= ? LIMIT 1')
          .get(Math.floor(now / DAY) - 1, Math.floor(now / DAY)))
    } catch { return false }
    finally { this.closeDatabase(database) }
  }

  async reserve(stamp: TelemetryStamp, network: Network = { network: 'unknown', constrained: true }, cohorts: unknown = {}): Promise<PreparedTelemetryReport | null> {
    if (!this.available || !stamp || !integer(stamp.revision, 2147483646) || !token(stamp.store_generation)) return null
    const expected = { ...stamp }
    const started = this.monotonic()
    let database: DatabaseSync | undefined
    try {
      const observed = this.environment ? this.environment() : network
      if (!['unknown', 'unmetered'].includes(observed.network) || observed.constrained !== false) return null
      const now = this.now()
      if (!integer(now, MAX_CLOCK - DAY - JITTER)) return null
      database = await this.open(true)
      database.exec('BEGIN IMMEDIATE')
      const preference = this.preferences(database), company = this.company()
      if (preference.connection_mode === 'metered' ||
          (observed.network === 'unknown' && preference.connection_mode !== 'unmetered')) return null
      if (preference.revision !== expected.revision || preference.store_generation !== expected.store_generation ||
          preference.enabled !== 1 || preference.disclosure_version !== this.disclosure.version || !company.enabled || !company.groups.length) return null
      const { current, spent } = state(database, preference.schema_version)
      if (now < current.clock_ms || now < current.next_ms || (current.lease_token && now < current.lease_deadline_ms)) return null
      const recent = spent.filter(item => item.at_ms > now - WEEK)
      if (recent.length >= 7 || recent.filter(item => item.at_ms > now - DAY).reduce((sum, item) => sum + item.reserved_bytes, 0) + COST > DAILY_BYTES) return null
      const review = this.reviewState(database, expected, company.groups, now)
      let body: Uint8Array, reviewed: ReviewReport | null = null
      if (review.mode === 'review') {
        if (review.outcome !== 'approved' || !review.report) {
          database.prepare('UPDATE report_review SET state=? WHERE singleton=1').run(serializeReview(review))
          database.exec('COMMIT')
          return null
        }
        reviewed = review.report
        body = new Uint8Array(reviewed.packet)
      } else {
        const day = Math.floor(now / DAY)
        database.prepare('DELETE FROM pending WHERE window_day < ? OR window_day > ?').run(day - 1, day)
        database.prepare('DELETE FROM producer_budget WHERE window_day != ?').run(day)
        const pending = database.prepare('SELECT cell, count FROM pending LIMIT 513')
        pending.setReturnArrays(true)
        // Keep a complete bounded snapshot while removing disallowed groups.
        const rows = pending.all() as unknown as [unknown, unknown][]
        if (rows.length > 512) throw invalid()
        const remove = database.prepare('DELETE FROM pending WHERE cell=?'), cells: [number, number][] = []
        for (const row of rows) {
          const [cell, count] = row
          if (!integer(cell, 65535) || !integer(count, 255) || count < 1) throw invalid()
          if (company.groups.includes(this.catalog.group(cell))) cells.push(row as [number, number])
          else remove.run(cell)
        }
        if (!cells.length) return null
        const release = reviewedDesktopRelease()
        const operatingSystem = cohortOperatingSystem(cohorts) ?? reviewedDesktopOperatingSystem()
        if (!release) return null
        body = this.wire().prepare(cells, company.groups, release, operatingSystem)
      }
      const covered = reviewed ? reviewed.groups : company.groups
      if (!this.wire().matchesGroups(body, covered)) return null
      const ticket = randomBytes(16).toString('hex'), jitter = randomInt(JITTER + 1)
      if (this.monotonic() - started >= DEADLINE) return null
      database.prepare('DELETE FROM delivery_attempts WHERE at_ms <= ?').run(now - WEEK)
      const slot = Array.from({ length: 7 }, (_, index) => index).find(index => !recent.some(item => item.slot === index))!
      database.prepare('INSERT INTO delivery_attempts VALUES (?, ?, ?)').run(slot, now, COST)
      database.prepare('UPDATE delivery_state SET clock_ms=?, next_ms=?, lease_token=?, lease_deadline_ms=? WHERE singleton=1')
        .run(now, now + DAY + jitter, ticket, now + DEADLINE)
      if (reviewed) database.prepare('UPDATE report_review SET state=? WHERE singleton=1').run(serializeReview(clearReview(review, 'consumed')))
      else database.exec('DELETE FROM pending')
      database.exec('COMMIT')
      return new PreparedTelemetryReport(body, ticket, expected, now + DEADLINE, started + DEADLINE, covered, reviewed)
    } catch { return null }
    finally { this.closeDatabase(database) }
  }

  private permitted(database: DatabaseSync, report: PreparedTelemetryReport): boolean {
    if (!(report instanceof PreparedTelemetryReport) || report.closed || !this.available) return false
    const now = this.now(), preference = this.preferences(database), company = this.company()
    const { current } = state(database, preference.schema_version)
    if (report.reviewed && !report.reviewCurrent(this.reviewContext({ revision: preference.revision,
      store_generation: preference.store_generation }, company.groups), now, readReviewClock())) return false
    if (this.environment) {
      const observed = this.environment()
      if (observed.constrained !== false || !['unknown', 'unmetered'].includes(observed.network) ||
          (observed.network === 'unknown' && preference.connection_mode !== 'unmetered')) return false
    }
    return integer(now) && this.monotonic() < report.monotonicDeadline && current.clock_ms <= now && now < current.lease_deadline_ms &&
      current.lease_deadline_ms === report.deadline && current.lease_token === report.ticket &&
      preference.revision === report.stamp.revision && preference.store_generation === report.stamp.store_generation &&
      preference.enabled === 1 && preference.connection_mode !== 'metered' && preference.disclosure_version === this.disclosure.version && company.enabled &&
      report.permits(company.groups)
  }

  async current(report: PreparedTelemetryReport): Promise<boolean> {
    let database: DatabaseSync | undefined, valid = false
    try {
      if (this.available) {
        database = await this.open()
        database.exec('BEGIN')
        valid = this.permitted(database, report)
      }
    } catch { /* Fail closed on unreadable, busy or damaged settings. */ }
    finally { this.closeDatabase(database) }
    if (!valid && report instanceof PreparedTelemetryReport) await this.cancel(report)
    return valid
  }

  async cancel(report: PreparedTelemetryReport): Promise<void> {
    if (!(report instanceof PreparedTelemetryReport)) return
    const ticket = report.ticket
    report.clear()
    if (!token(ticket)) return
    let database: DatabaseSync | undefined
    try {
      database = await this.open(true)
      database.exec('BEGIN IMMEDIATE')
      state(database)
      database.prepare('UPDATE delivery_state SET lease_token=NULL, lease_deadline_ms=0 WHERE singleton=1 AND lease_token=?').run(ticket)
      database.exec('COMMIT')
    } catch { /* Spending remains consumed; an orphaned lease expires. */ }
    finally { this.closeDatabase(database) }
  }

  /** Only a reviewed synchronous nonblocking socket handoff belongs here.
   * A successful handoff remains cancellable; its owner must finish with cancel(). */
  async guardedWrite(report: PreparedTelemetryReport, write: (body: Uint8Array) => boolean): Promise<boolean> {
    if (!(report instanceof PreparedTelemetryReport) || typeof write !== 'function' || !report.claimHandoff()) return false
    if (write.constructor?.name === 'AsyncFunction') { await this.cancel(report); return false }
    let database: DatabaseSync | undefined, result = false, owned = false
    try {
      database = await this.open(true)
      database.exec('BEGIN IMMEDIATE')
      if (report.used) return false
      owned = true
      if (!this.permitted(database, report)) return false
      report.burn()
      const body = report.body()
      try { result = write(body) === true } catch { result = false }
      finally { body.fill(0); report.eraseBody() }
      database.exec('COMMIT')
    } catch { result = false }
    finally {
      this.closeDatabase(database)
      if (owned || !report.used) {
        report.eraseBody()
        if (!result) await this.cancel(report)
      }
    }
    return result
  }

  /** Caller owns an existing attempt and abort signal; this never wakes an idle app.
   * A transport may drain observation before its fresh handoff fence, retaining
   * the lease only on that deliberate stop and owning final cancellation itself. */
  async watch(report: PreparedTelemetryReport, abort: () => void, stop: AbortSignal, cancelOnStop = true): Promise<void> {
    const cancelTransport = () => { try { abort() } catch { /* No retry or exception forwarding. */ } }
    try {
      while (!stop.aborted && await this.current(report)) await delay(25, undefined, { signal: stop, ref: false })
      if (!stop.aborted) cancelTransport()
    } catch { if (!stop.aborted) cancelTransport() }
    finally { if (cancelOnStop || !stop.aborted) await this.cancel(report) }
  }
}
