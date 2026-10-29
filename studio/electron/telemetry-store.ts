/** No network or implicit choice: share Python's private SQLite store. */
import { lstatSync, readFileSync, type Stats } from 'node:fs'
import { dirname, isAbsolute, join } from 'node:path'
import { pathToFileURL } from 'node:url'
import type { DatabaseSync, StatementSync } from 'node:sqlite'
import type { TelemetryConnectionMode, TelemetryDisclosure, TelemetryStamp } from '../shared/product-telemetry.js'
import { TelemetryCatalog, type MeasurementCatalog } from './telemetry-catalog.js'
import { windowsTelemetryPrivateStore } from './telemetry-private-store.js'
import { clearReview, loadReview, salvageStaleReview, serializeReview } from './telemetry-review.js'
import { checkReviewLifetime } from './telemetry-review-lifetime.js'
import { readReviewClock } from './telemetry-review-clock.js'

export type NativeTelemetryDisclosure = TelemetryDisclosure & { metric_groups: string[] }
type Preference = { revision: number; enabled: number; disclosure_version: number; store_generation: string; connection_mode: TelemetryConnectionMode; schema_version: number }
type Company = { enabled: boolean; groups: string[] }
const failure = () => new Error('telemetry_storage_unavailable')
const integer = (value: unknown, maximum: number, minimum = 0): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= minimum && value <= maximum
const generation = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{32}$/.test(value)
const stampValid = (value: TelemetryStamp) => value && integer(value.revision, 2147483646) && generation(value.store_generation)
const sameFile = (left: Stats, right: Stats) => left.dev === right.dev && left.ino === right.ino &&
  left.mtimeMs === right.mtimeMs && left.ctimeMs === right.ctimeMs && left.size === right.size
const PREFERENCES_CURRENT = `SELECT revision, enabled, disclosure_version, store_generation, connection_mode,
  (SELECT user_version FROM pragma_user_version()),
  (SELECT application_id FROM pragma_application_id()),
  (SELECT journal_mode FROM pragma_journal_mode()) FROM preferences WHERE singleton=1`
const PREFERENCES_LEGACY = `SELECT revision, enabled, disclosure_version, store_generation, 'auto',
  (SELECT user_version FROM pragma_user_version()),
  (SELECT application_id FROM pragma_application_id()),
  (SELECT journal_mode FROM pragma_journal_mode()) FROM preferences WHERE singleton=1`

// One OS-account telemetry store is shared by every desktop owner. Acquire
// before the first await: otherwise concurrent callers can all open SQLite
// before any caller resumes to close its transaction. There is no wait queue.
let storageOwner: { database?: DatabaseSync } | undefined

export function nativeTelemetryDefinitions(): { disclosure: NativeTelemetryDisclosure; catalog: MeasurementCatalog } {
  return {
    disclosure: JSON.parse(readFileSync(new URL('./telemetry-disclosure.json', import.meta.url), 'utf8')),
    catalog: JSON.parse(readFileSync(new URL('./telemetry-catalog.json', import.meta.url), 'utf8')),
  }
}

export function nativeCompanyPolicyPath(): string {
  if (process.platform === 'win32') return join(process.env.PROGRAMDATA || 'C:\\ProgramData', 'Mnemion', 'telemetry-policy.json')
  if (process.platform === 'darwin') return '/Library/Application Support/Mnemion/telemetry-policy.json'
  return '/etc/mnemion/telemetry-policy.json'
}

export class NativeTelemetryStore {
  readonly catalog: TelemetryCatalog
  private sqlite?: Promise<typeof import('node:sqlite')>
  private permissionCheck?: Promise<boolean>
  private databasePath?: string
  private databaseUris?: { read: string; write: string }
  private saturated?: {
    bits: Uint8Array; day: number; until: number; checkedUntil: number; userDisabled: boolean
    file: Stats
  }
  constructor(
    private readonly root: string,
    readonly disclosure: NativeTelemetryDisclosure,
    catalog: MeasurementCatalog,
    private readonly companyFile = nativeCompanyPolicyPath(),
  ) { this.catalog = new TelemetryCatalog(catalog) }

  get available(): boolean { return this.disclosure.collection_available && Boolean(this.disclosure.destination) }

  /** A local control reply may only deny optional sampling, never authorize it.
   * Preserve its original monotonic expiry, including delayed owner creation.
   * The existing negative cache still notices file changes and day rollover. */
  noteUserDisabled(until: number): void {
    const now = performance.now()
    if (!this.available || !Number.isFinite(until) || !Number.isFinite(now) ||
        until <= now || until > now + 60000) return
    this.rememberExhausted([], Math.floor(Date.now() / 86400000), true)
    const saved = this.saturated
    if (saved?.userDisabled) {
      saved.until = Math.min(saved.until, until)
      saved.checkedUntil = Math.min(saved.checkedUntil, saved.until)
    }
  }

  private path(): string { return this.databasePath ??= join(this.root, 'product-telemetry.sqlite3') }

  private saturationFile() {
    // This is only a negative sampling hint. Number precision can at worst
    // suppress an extra sample until expiry; it never authorizes a write.
    return lstatSync(this.path())
  }

  /** A short negative cache can only drop disabled/exhausted measurements.
   * It never grants consent, skips a write fence or holds a database connection.
   * Work can reuse a file observation for at most 250 ms. Day/expiry changes
   * clear it immediately. There is no idle polling or positive cache. */
  private exhausted(scopes: number | number[], day: number): boolean {
    const saved = this.saturated
    if (!saved) return false
    const now = performance.now()
    if (day !== saved.day || !Number.isFinite(now) || now >= saved.until || now < saved.until - 60000) {
      this.saturated = undefined; return false
    }
    const denied = saved.userDisabled || (typeof scopes === 'number'
      ? scopes >= 0 && Boolean(saved.bits[scopes >> 3] & (1 << (scopes & 7)))
      : scopes.length > 0 && scopes.every(scope => Boolean(saved.bits[scope >> 3] & (1 << (scope & 7)))))
    if (!denied) return false
    // This quiet interval only suppresses optional samples, including briefly
    // after re-enabling. It is never used by a write, reservation or handoff.
    if (now < saved.checkedUntil) return true
    try {
      const current = this.saturationFile(), prior = saved.file
      if (!sameFile(current, prior)) {
        this.saturated = undefined; return false
      }
      saved.checkedUntil = Math.min(saved.until, now + 250)
      return true
    } catch { this.saturated = undefined; return false }
  }

  private rememberExhausted(scopes: number[], day: number, userDisabled = false): void {
    if (!scopes.length && !userDisabled) return
    try {
      // Multiple exhausted scopes may share a verified file version. Never
      // carry old scope bits across a change, a new day or the bounded expiry.
      const file = this.saturationFile(), now = performance.now(), prior = this.saturated
      const bits = prior && prior.day === day && now < prior.until && now >= prior.until - 60000 && sameFile(file, prior.file)
        ? prior.bits : new Uint8Array(65)
      const until = bits === prior?.bits ? prior.until : now + 60000
      this.saturated = { bits, day, until, checkedUntil: Math.min(until, now + 250), file, userDisabled }
      for (const scope of scopes) this.saturated.bits[scope >> 3] |= 1 << (scope & 7)
    } catch { this.saturated = undefined }
  }

  private safe(): string {
    if (!isAbsolute(this.root)) throw failure()
    const directory = lstatSync(this.root), path = this.path(), file = lstatSync(path)
    if (!directory.isDirectory() || directory.isSymbolicLink() || !file.isFile() || file.isSymbolicLink() || file.nlink !== 1 || file.size > 96 * 1024) throw failure()
    if (process.platform !== 'win32' && [directory, file].some(item => item.uid !== process.getuid!() || (item.mode & 0o077))) throw failure()
    return path
  }

  private absentCompanyParent(): boolean {
    // Windows also reports ENOENT when a parent is a regular file. Verify the
    // nearest existing ancestor before treating the optional path as absent.
    let path = dirname(this.companyFile)
    for (let depth = 0; depth < 32; depth++) {
      const info = lstatSync(path, { throwIfNoEntry: false })
      if (info) return info.isDirectory() && !info.isSymbolicLink()
      const parent = dirname(path)
      if (parent === path) return false
      path = parent
    }
    return false
  }

  protected company(): Company {
    try {
      // An absent optional file is common. Avoid allocating an ENOENT error
      // on every fresh read; other filesystem errors still deny below.
      const info = lstatSync(this.companyFile, { throwIfNoEntry: false })
      if (!info) return this.absentCompanyParent()
        ? { enabled: true, groups: [...this.disclosure.metric_groups] } : { enabled: false, groups: [] }
      if (!info.isFile() || info.isSymbolicLink() || info.size > 8192) throw failure()
      const raw = readFileSync(this.companyFile)
      if (raw.length > 8192) throw failure()
      const value = JSON.parse(raw.toString('utf8'))
      if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).sort().join() !== 'enabled,metric_groups,schema_version' ||
          value.schema_version !== 1 || typeof value.enabled !== 'boolean' || !Array.isArray(value.metric_groups) ||
          value.metric_groups.length > this.disclosure.metric_groups.length || new Set(value.metric_groups).size !== value.metric_groups.length ||
          value.metric_groups.some((group: unknown) => typeof group !== 'string' || !this.disclosure.metric_groups.includes(group))) throw failure()
      return { enabled: value.enabled, groups: value.metric_groups }
    } catch {
      // Once a file was observed, disappearance or any failed read is
      // uncertainty. A later fresh check can establish genuine absence.
      return { enabled: false, groups: [] }
    }
  }

  protected async open(write = false): Promise<DatabaseSync> {
    if (storageOwner) throw failure()
    const owner: { database?: DatabaseSync } = {}
    storageOwner = owner
    let database: DatabaseSync | undefined
    try {
      const path = this.safe()
      if (process.platform === 'win32') {
        this.permissionCheck ??= windowsTelemetryPrivateStore(this.root, path).finally(() => { this.permissionCheck = undefined })
        if (!await this.permissionCheck) throw failure()
      }
      // Load SQLite only for an active disclosed measurement, never merely for
      // loading the app or an unavailable telemetry build.
      this.sqlite ??= import('node:sqlite')
      const { DatabaseSync } = await this.sqlite
      // Cache only the spelling of this immutable location. Filesystem/ACL
      // checks above and SQLite authority reads remain fresh on every open.
      if (!this.databaseUris) {
        const url = pathToFileURL(path)
        url.search = '?mode=ro'
        const read = url.href
        url.search = '?mode=rw'
        this.databaseUris = { read, write: url.href }
      }
      database = new DatabaseSync(write ? this.databaseUris.write : this.databaseUris.read,
        { readOnly: !write, allowExtension: false })
      owner.database = database
      database.exec('PRAGMA busy_timeout=0; PRAGMA trusted_schema=OFF; PRAGMA cache_size=-128; PRAGMA mmap_size=0;')
      if (write) database.exec('PRAGMA secure_delete=ON; PRAGMA synchronous=FULL; PRAGMA max_page_count=24;')
      return database
    } catch (error) {
      if (database) this.closeDatabase(database)
      else if (storageOwner === owner) storageOwner = undefined
      throw error
    }
  }

  /** Release reclaimable SQLite allocations before closing each transaction's
   * connection, without retaining a handle, statements or positive policy cache. */
  protected closeDatabase(database?: DatabaseSync): void {
    if (!database) return
    try { database.exec('PRAGMA shrink_memory') } catch { /* Closing still owns rollback and cleanup. */ }
    let closed = false
    try { database.close(); closed = true }
    catch {
      // A failed close cannot grant another handle. If the connection is still
      // open (or its state is unknown), keep telemetry unavailable in this
      // process until cleanup succeeds or the process exits.
      try { closed = database.isOpen === false } catch { /* Retain ownership. */ }
    }
    if (closed && storageOwner?.database === database) storageOwner = undefined
  }

  protected preferences(database: DatabaseSync): Preference {
    // The current format needs one coherent read, with no column-name objects
    // or separate version statement. Nothing survives this transaction's close.
    let statement: StatementSync, legacy = false
    try { statement = database.prepare(PREFERENCES_CURRENT) }
    catch (error) {
      // Schema 3/4 has no connection_mode column. Only a SQL compilation error
      // can select the fixed legacy query; busy/corrupt/IO failures are not retried.
      const sqlite = error as { code?: unknown; errcode?: unknown } | null
      if (sqlite?.code !== 'ERR_SQLITE_ERROR' || sqlite.errcode !== 1) throw failure()
      statement = database.prepare(PREFERENCES_LEGACY)
      legacy = true
    }
    statement.setReturnArrays(true)
    const row = statement.get() as unknown as unknown[] | undefined
    if (!row) throw failure()
    const [revision, enabled, disclosure_version, store_generation, mode, version, application, journal] = row
    if (!integer(version, 6, 3) || (legacy && version >= 5) ||
        application !== 0x4D4E5450 || journal !== 'delete' ||
        !integer(revision, 2147483646) || ![0, 1].includes(enabled as number) ||
        !integer(disclosure_version, this.disclosure.version) || !generation(store_generation)) throw failure()
    // Legacy versions never interpret an extra connection_mode column as a
    // setting, even if a damaged or partially upgraded file happens to have one.
    const connection_mode = version < 5 ? 'auto' : mode
    if (!['auto', 'unmetered', 'metered'].includes(connection_mode as string)) throw failure()
    return { revision, enabled, disclosure_version, store_generation, connection_mode, schema_version: version } as Preference
  }

  private maintainReview(database: DatabaseSync, preference: Preference, company: Company): void {
    if (preference.schema_version !== 6) return
    const raw = database.prepare('SELECT state FROM report_review WHERE singleton=1').get()?.state
    let state
    try { state = loadReview(raw) }
    catch { return }
    if (salvageStaleReview(raw) && !state.report) {
      database.prepare('UPDATE report_review SET state=? WHERE singleton=1').run(serializeReview(state))
      return
    }
    const report = state.report
    if (!report) return
    const permitted = preference.enabled === 1 && preference.disclosure_version === this.disclosure.version && company.enabled &&
      report.stamp.revision === preference.revision && report.stamp.store_generation === preference.store_generation &&
      report.binding.disclosure_version === this.disclosure.version && report.binding.catalog_version === this.catalog.specification.version &&
      report.binding.destination === this.disclosure.destination &&
      [...report.groups].sort().join() === [...company.groups].sort().join()
    const expired = permitted && !checkReviewLifetime(report.lifetime, Date.now(), readReviewClock())
    if (!permitted || expired) database.prepare('UPDATE report_review SET state=? WHERE singleton=1')
      .run(serializeReview(clearReview(state, expired ? 'expired' : 'invalidated')))
  }

  snapshot(workflow?: string, surface?: string): Promise<TelemetryStamp | null> | null {
    if (!this.available || storageOwner) return null
    let scope = -1
    const day = Math.floor(Date.now() / 86400000)
    if (workflow !== undefined || surface !== undefined) {
      const index = this.catalog.workflows.indexOf(workflow!), origin = this.catalog.specification.surfaces.indexOf(surface!)
      if (index < 0 || origin < 0) return null
      scope = index * 4 + origin
    }
    if (this.exhausted(scope, day)) return null
    return this.readStamp(day)
  }

  private async readStamp(day: number): Promise<TelemetryStamp | null> {
    let database: DatabaseSync | undefined
    try {
      database = await this.open()
      database.exec('BEGIN')
      const preference = this.preferences(database), company = this.company()
      if (preference.enabled !== 1 || preference.disclosure_version !== this.disclosure.version || !company.enabled || !company.groups.length) {
        this.saturated = undefined
        if (preference.enabled !== 1) this.rememberExhausted([], day, true)
        return null
      }
      return { revision: preference.revision, store_generation: preference.store_generation }
    } catch { return null }
    finally { this.closeDatabase(database) }
  }

  record(input: unknown, stamp: TelemetryStamp, day = Math.floor(Date.now() / 86400000)): Promise<boolean> {
    return this.recordMany([input], stamp, day)
  }

  async recordMany(inputs: unknown[], stamp: TelemetryStamp, day = Math.floor(Date.now() / 86400000)): Promise<boolean> {
    if (!this.available || storageOwner || !stampValid(stamp) || !integer(day, 1000000)) return false
    const expected = { revision: stamp.revision, store_generation: stamp.store_generation }
    let database: DatabaseSync | undefined
    try {
      // Encode before the async boundary. The queue never retains a caller's
      // object, private arguments, exact numeric values or exception text.
      if (!Array.isArray(inputs) || inputs.length < 1 || inputs.length > 2) return false
      const observations = inputs.map(input => this.catalog.observation(input))
      if (this.exhausted(observations.map(value => value.scope), day)) return false
      database = await this.open(true)
      database.exec('BEGIN IMMEDIATE')
      const preference = this.preferences(database)
      if (preference.revision !== expected.revision || preference.store_generation !== expected.store_generation) return false
      const company = this.company()
      this.maintainReview(database, preference, company)
      if (preference.enabled !== 1 || preference.disclosure_version !== this.disclosure.version || !company.enabled || !company.groups.length) {
        this.saturated = undefined
        database.exec('DELETE FROM pending; DELETE FROM producer_budget; COMMIT;')
        if (preference.enabled !== 1) this.rememberExhausted([], day, true)
        return false
      }
      database.prepare('DELETE FROM pending WHERE window_day < ? OR window_day > ?').run(day - 1, day)
      database.prepare('DELETE FROM producer_budget WHERE window_day != ?').run(day)
      const pending = database.prepare('SELECT cell, count, window_day FROM pending LIMIT 513')
      pending.setReturnArrays(true)
      // Snapshot before deleting rows; iterating a mutating table can miss one.
      const rows = pending.all() as unknown as [unknown, unknown, unknown][]
      if (rows.length > 512) throw failure()
      const occupied = new Set<number>()
      const remove = database.prepare('DELETE FROM pending WHERE cell=?')
      for (const [cell, count, windowDay] of rows) {
        if (!integer(cell, 65535) || !integer(count, 255, 1) || !integer(windowDay, 1000000)) throw failure()
        if (!company.groups.includes(this.catalog.group(cell))) remove.run(cell)
        else occupied.add(cell)
      }
      // Reuse this transaction's statements and capacity snapshot for the pair.
      // No connection, statements or settings survive the policy transaction.
      const budget = database.prepare('SELECT count FROM producer_budget WHERE scope=?')
      const contribute = database.prepare('INSERT INTO producer_budget VALUES (?, 1, ?) ON CONFLICT(scope) DO UPDATE SET count=count+1, window_day=excluded.window_day')
      const update = database.prepare('INSERT INTO pending VALUES (?, 1, ?) ON CONFLICT(cell) DO UPDATE SET count=CASE WHEN pending.window_day=excluded.window_day THEN min(pending.count+1, 255) ELSE 1 END, window_day=excluded.window_day')
      let recorded = false
      const exhausted: number[] = []
      for (const { scope, cells } of observations) {
        const permitted = cells.filter(cell => company.groups.includes(this.catalog.group(cell)))
        const prior = budget.get(scope)
        const limit = scope >= 512 ? this.catalog.specification.limits.resource_observations_per_day : this.catalog.specification.limits.observations_per_workflow_day
        if (prior && !integer(prior.count, 64, 1)) throw failure()
        if (prior && Number(prior.count) >= limit) exhausted.push(scope)
        if (!permitted.length || (prior && Number(prior.count) >= limit) || occupied.size + permitted.filter(cell => !occupied.has(cell)).length > 512) continue
        contribute.run(scope, day)
        if (Number(prior?.count ?? 0) + 1 >= limit) exhausted.push(scope)
        for (const cell of permitted) { update.run(cell, day); occupied.add(cell) }
        recorded = true
      }
      database.exec('COMMIT')
      this.rememberExhausted(exhausted, day)
      return recorded
    } catch { return false }
    finally { this.closeDatabase(database) }
  }
}
