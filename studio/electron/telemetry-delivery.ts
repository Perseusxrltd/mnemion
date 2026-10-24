/** Shared private reservations and final-write fences. No sender or scheduler. */
import { randomBytes, randomInt } from 'node:crypto'
import { readFileSync } from 'node:fs'
import type { DatabaseSync } from 'node:sqlite'
import { setTimeout as delay } from 'node:timers/promises'
import type { TelemetryStamp } from '../shared/product-telemetry.js'
import { TelemetryWire } from './telemetry-wire.js'
import { NativeTelemetryStore, nativeCompanyPolicyPath, type NativeTelemetryDisclosure } from './telemetry-store.js'
import type { MeasurementCatalog } from './telemetry-catalog.js'

const DAY = 86400000, WEEK = 7 * DAY, DEADLINE = 5000, JITTER = 3600000
const MAX_CLOCK = 86400000000000, COST = 65536, DAILY_BYTES = 256 * 1024
const integer = (value: unknown, max = MAX_CLOCK): value is number =>
  typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 && value <= max
const token = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{32}$/.test(value)
const invalid = () => new Error('telemetry_delivery_unavailable')
type State = { clock_ms: number; next_ms: number; lease_token: string | null; lease_deadline_ms: number }
type Spent = { slot: number; at_ms: number; reserved_bytes: number }
type Network = { network: 'unknown' | 'metered' | 'unmetered'; constrained: boolean }

function state(database: DatabaseSync): { current: State; spent: Spent[] } {
  if (database.prepare('PRAGMA user_version').get()?.user_version !== 4) throw invalid()
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
  #group: string
  #claimed = false
  #transportClaimed = false
  constructor(body: Uint8Array, ticket: string, readonly stamp: Readonly<TelemetryStamp>, readonly deadline: number,
    readonly monotonicDeadline: number, group: string) {
    this.#body = new Uint8Array(body)
    this.#token = ticket
    this.#group = group
    this.stamp = Object.freeze({ ...stamp })
  }
  get used(): boolean { return this.#used }
  get closed(): boolean { return this.#closed }
  get group(): string { return this.#group }
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
  clear(): void { this.eraseBody(); this.#token = ''; this.#used = true; this.#closed = true }
}

export class NativeTelemetryDelivery extends NativeTelemetryStore {
  private encoder?: TelemetryWire
  constructor(root: string, disclosure: NativeTelemetryDisclosure, catalog: MeasurementCatalog,
    companyFile = nativeCompanyPolicyPath(), private readonly now = () => Date.now(),
    private readonly monotonic = () => performance.now()) {
    super(root, disclosure, catalog, companyFile)
  }

  private wire(): TelemetryWire {
    this.encoder ??= new TelemetryWire(JSON.parse(readFileSync(new URL('./telemetry-wire-v1.json', import.meta.url), 'utf8')), this.catalog)
    return this.encoder
  }

  async reserve(stamp: TelemetryStamp, network: Network = { network: 'unknown', constrained: true }, cohorts: unknown = {}): Promise<PreparedTelemetryReport | null> {
    if (!this.available || !stamp || !integer(stamp.revision, 2147483646) || !token(stamp.store_generation) ||
        network.network !== 'unmetered' || network.constrained !== false) return null
    const expected = { ...stamp }
    const started = this.monotonic()
    let database: DatabaseSync | undefined
    try {
      const now = this.now()
      if (!integer(now, MAX_CLOCK - DAY - JITTER)) return null
      database = await this.open(true)
      database.exec('BEGIN IMMEDIATE')
      const preference = this.preferences(database), company = this.company()
      if (preference.revision !== expected.revision || preference.store_generation !== expected.store_generation ||
          preference.enabled !== 1 || preference.disclosure_version !== this.disclosure.version || !company.enabled || !company.groups.length) return null
      const { current, spent } = state(database)
      if (now < current.clock_ms || now < current.next_ms || (current.lease_token && now < current.lease_deadline_ms)) return null
      const recent = spent.filter(item => item.at_ms > now - WEEK)
      if (recent.length >= 7 || recent.filter(item => item.at_ms > now - DAY).reduce((sum, item) => sum + item.reserved_bytes, 0) + COST > DAILY_BYTES) return null
      const day = Math.floor(now / DAY)
      database.prepare('DELETE FROM pending WHERE window_day < ? OR window_day > ?').run(day - 1, day)
      database.prepare('DELETE FROM producer_budget WHERE window_day != ?').run(day)
      const rows = database.prepare('SELECT cell, count FROM pending LIMIT 513').all()
      if (rows.length > 512) throw invalid()
      const remove = database.prepare('DELETE FROM pending WHERE cell=?'), cells: [number, number][] = []
      for (const row of rows) {
        if (!integer(row.cell, 65535) || !integer(row.count, 255) || row.count < 1) throw invalid()
        if (company.groups.includes(this.catalog.describe(row.cell).group)) cells.push([row.cell, row.count])
        else remove.run(row.cell)
      }
      if (!cells.length) return null
      const body = this.wire().prepare(cells, company.groups, cohorts)
      const ticket = randomBytes(16).toString('hex'), jitter = randomInt(JITTER + 1)
      if (this.monotonic() - started >= DEADLINE) return null
      database.prepare('DELETE FROM delivery_attempts WHERE at_ms <= ?').run(now - WEEK)
      const slot = Array.from({ length: 7 }, (_, index) => index).find(index => !recent.some(item => item.slot === index))!
      database.prepare('INSERT INTO delivery_attempts VALUES (?, ?, ?)').run(slot, now, COST)
      database.prepare('UPDATE delivery_state SET clock_ms=?, next_ms=?, lease_token=?, lease_deadline_ms=? WHERE singleton=1')
        .run(now, now + DAY + jitter, ticket, now + DEADLINE)
      database.exec('DELETE FROM pending; COMMIT;')
      return new PreparedTelemetryReport(body, ticket, expected, now + DEADLINE, started + DEADLINE,
        this.wire().specification.views[this.wire().decode(body).view].group)
    } catch { return null }
    finally { try { database?.close() } catch { /* Optional delivery cannot fail memory work. */ } }
  }

  private permitted(database: DatabaseSync, report: PreparedTelemetryReport): boolean {
    if (!(report instanceof PreparedTelemetryReport) || report.closed || !this.available) return false
    const now = this.now(), { current } = state(database)
    const preference = this.preferences(database), company = this.company()
    return integer(now) && this.monotonic() < report.monotonicDeadline && current.clock_ms <= now && now < current.lease_deadline_ms &&
      current.lease_deadline_ms === report.deadline && current.lease_token === report.ticket &&
      preference.revision === report.stamp.revision && preference.store_generation === report.stamp.store_generation &&
      preference.enabled === 1 && preference.disclosure_version === this.disclosure.version && company.enabled &&
      company.groups.includes(report.group)
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
    finally { try { database?.close() } catch { /* No retry or diagnostics. */ } }
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
    finally { try { database?.close() } catch { /* No retry or diagnostics. */ } }
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
      try { database?.close() } catch { /* No retry or diagnostics. */ }
      if (owned || !report.used) {
        report.eraseBody()
        if (!result) await this.cancel(report)
      }
    }
    return result
  }

  /** Caller owns an existing attempt and abort signal; this never wakes an idle app. */
  async watch(report: PreparedTelemetryReport, abort: () => void, stop: AbortSignal): Promise<void> {
    const cancelTransport = () => { try { abort() } catch { /* No retry or exception forwarding. */ } }
    try {
      while (!stop.aborted && await this.current(report)) await delay(25, undefined, { signal: stop, ref: false })
      if (!stop.aborted) cancelTransport()
    } catch { if (!stop.aborted) cancelTransport() }
    finally { await this.cancel(report) }
  }
}
