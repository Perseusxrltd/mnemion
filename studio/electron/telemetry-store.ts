/** No network or implicit choice: share Python's private SQLite store. */
import { lstatSync, readFileSync, type Stats } from 'node:fs'
import { isAbsolute, join } from 'node:path'
import { pathToFileURL } from 'node:url'
import type { DatabaseSync } from 'node:sqlite'
import type { TelemetryConnectionMode, TelemetryDisclosure, TelemetryStamp } from '../shared/product-telemetry.js'
import { TelemetryCatalog, type MeasurementCatalog } from './telemetry-catalog.js'
import { windowsTelemetryPrivateStore } from './telemetry-private-store.js'

export type NativeTelemetryDisclosure = TelemetryDisclosure & { metric_groups: string[] }
type Preference = { revision: number; enabled: number; disclosure_version: number; store_generation: string; connection_mode: TelemetryConnectionMode }
type Company = { enabled: boolean; groups: string[] }
const failure = () => new Error('telemetry_storage_unavailable')
const integer = (value: unknown, maximum: number, minimum = 0): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= minimum && value <= maximum
const generation = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{32}$/.test(value)
const stampValid = (value: TelemetryStamp) => value && integer(value.revision, 2147483646) && generation(value.store_generation)
const sameFile = (left: Stats, right: Stats) => left.dev === right.dev && left.ino === right.ino &&
  left.mtimeMs === right.mtimeMs && left.ctimeMs === right.ctimeMs && left.size === right.size

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

  private saturationFile() {
    // This is only a negative sampling hint. Number precision can at worst
    // suppress an extra sample until expiry; it never authorizes a write.
    return lstatSync(join(this.root, 'product-telemetry.sqlite3'))
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
    const directory = lstatSync(this.root), path = join(this.root, 'product-telemetry.sqlite3'), file = lstatSync(path)
    if (!directory.isDirectory() || directory.isSymbolicLink() || !file.isFile() || file.isSymbolicLink() || file.nlink !== 1 || file.size > 96 * 1024) throw failure()
    if (process.platform !== 'win32' && [directory, file].some(item => item.uid !== process.getuid!() || (item.mode & 0o077))) throw failure()
    return path
  }

  protected company(): Company {
    try {
      const info = lstatSync(this.companyFile)
      if (!info.isFile() || info.isSymbolicLink() || info.size > 8192) throw failure()
      const raw = readFileSync(this.companyFile)
      if (raw.length > 8192) throw failure()
      const value = JSON.parse(raw.toString('utf8'))
      if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).sort().join() !== 'enabled,metric_groups,schema_version' ||
          value.schema_version !== 1 || typeof value.enabled !== 'boolean' || !Array.isArray(value.metric_groups) ||
          value.metric_groups.length > this.disclosure.metric_groups.length || new Set(value.metric_groups).size !== value.metric_groups.length ||
          value.metric_groups.some((group: unknown) => typeof group !== 'string' || !this.disclosure.metric_groups.includes(group))) throw failure()
      return { enabled: value.enabled, groups: value.metric_groups }
    } catch (error) {
      return (error as NodeJS.ErrnoException)?.code === 'ENOENT'
        ? { enabled: true, groups: [...this.disclosure.metric_groups] } : { enabled: false, groups: [] }
    }
  }

  protected async open(write = false): Promise<DatabaseSync> {
    const path = this.safe()
    if (process.platform === 'win32') {
      // At most one short native ACL helper, including concurrent UI reads.
      this.permissionCheck ??= windowsTelemetryPrivateStore(this.root, path).finally(() => { this.permissionCheck = undefined })
      if (!await this.permissionCheck) throw failure()
    }
    // Load SQLite only for an active disclosed measurement, never merely for
    // loading the app or an unavailable telemetry build.
    this.sqlite ??= import('node:sqlite')
    const { DatabaseSync } = await this.sqlite
    const url = pathToFileURL(path)
    url.search = write ? '?mode=rw' : '?mode=ro'
    const database = new DatabaseSync(url.href, { readOnly: !write, allowExtension: false })
    try {
      database.exec('PRAGMA busy_timeout=0; PRAGMA trusted_schema=OFF; PRAGMA cache_size=-128; PRAGMA mmap_size=0;')
      if (write) database.exec('PRAGMA secure_delete=ON; PRAGMA synchronous=FULL; PRAGMA max_page_count=24;')
      return database
    } catch (error) { database.close(); throw error }
  }

  protected preferences(database: DatabaseSync): Preference {
    const version = Number(database.prepare('PRAGMA user_version').get()?.user_version)
    if (database.prepare('PRAGMA application_id').get()?.application_id !== 0x4D4E5450 ||
        ![3, 4, 5].includes(version) ||
        database.prepare('PRAGMA journal_mode').get()?.journal_mode !== 'delete') throw failure()
    const row = database.prepare('SELECT revision, enabled, disclosure_version, store_generation FROM preferences WHERE singleton=1').get()
    if (!row || !integer(row.revision, 2147483647) || ![0, 1].includes(row.enabled as number) ||
        !integer(row.disclosure_version, this.disclosure.version) || !generation(row.store_generation) || row.revision === 2147483647) throw failure()
    const mode = version >= 5 ? database.prepare('SELECT connection_mode FROM preferences WHERE singleton=1').get()?.connection_mode : 'auto'
    if (!['auto', 'unmetered', 'metered'].includes(mode as string)) throw failure()
    return { ...row, connection_mode: mode } as Preference
  }

  snapshot(workflow?: string, surface?: string): Promise<TelemetryStamp | null> | null {
    if (!this.available) return null
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
    finally { try { database?.close() } catch { /* Optional observation never breaks the caller. */ } }
  }

  record(input: unknown, stamp: TelemetryStamp, day = Math.floor(Date.now() / 86400000)): Promise<boolean> {
    return this.recordMany([input], stamp, day)
  }

  async recordMany(inputs: unknown[], stamp: TelemetryStamp, day = Math.floor(Date.now() / 86400000)): Promise<boolean> {
    if (!this.available || !stampValid(stamp) || !integer(day, 1000000)) return false
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
      if (preference.enabled !== 1 || preference.disclosure_version !== this.disclosure.version || !company.enabled || !company.groups.length) {
        this.saturated = undefined
        database.exec('DELETE FROM pending; DELETE FROM producer_budget; COMMIT;')
        if (preference.enabled !== 1) this.rememberExhausted([], day, true)
        return false
      }
      database.prepare('DELETE FROM pending WHERE window_day < ? OR window_day > ?').run(day - 1, day)
      database.prepare('DELETE FROM producer_budget WHERE window_day != ?').run(day)
      const rows = database.prepare('SELECT cell, count, window_day FROM pending LIMIT 513').all()
      if (rows.length > 512) throw failure()
      const occupied = new Set<number>()
      const remove = database.prepare('DELETE FROM pending WHERE cell=?')
      for (const row of rows) {
        if (!integer(row.cell, 65535) || !integer(row.count, 255, 1) || !integer(row.window_day, 1000000)) throw failure()
        if (!company.groups.includes(this.catalog.describe(row.cell).group)) remove.run(row.cell)
        else occupied.add(row.cell)
      }
      // Reuse this transaction's statements and capacity snapshot for the pair.
      // No connection, statements or settings survive the policy transaction.
      const budget = database.prepare('SELECT count FROM producer_budget WHERE scope=?')
      const contribute = database.prepare('INSERT INTO producer_budget VALUES (?, 1, ?) ON CONFLICT(scope) DO UPDATE SET count=count+1, window_day=excluded.window_day')
      const update = database.prepare('INSERT INTO pending VALUES (?, 1, ?) ON CONFLICT(cell) DO UPDATE SET count=CASE WHEN pending.window_day=excluded.window_day THEN min(pending.count+1, 255) ELSE 1 END, window_day=excluded.window_day')
      let recorded = false
      const exhausted: number[] = []
      for (const { scope, cells } of observations) {
        const permitted = cells.filter(cell => company.groups.includes(this.catalog.describe(cell).group))
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
    finally { try { database?.close() } catch { /* Optional observation never breaks the caller. */ } }
  }
}
