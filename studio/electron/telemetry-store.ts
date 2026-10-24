/** No network or implicit choice: share Python's private SQLite store. */
import { lstatSync, readFileSync } from 'node:fs'
import { isAbsolute, join } from 'node:path'
import { pathToFileURL } from 'node:url'
import type { DatabaseSync } from 'node:sqlite'
import type { TelemetryDisclosure, TelemetryStamp } from '../shared/product-telemetry.js'
import { TelemetryCatalog, type MeasurementCatalog } from './telemetry-catalog.js'
import { windowsTelemetryPrivateStore } from './telemetry-private-store.js'

export type NativeTelemetryDisclosure = TelemetryDisclosure & { metric_groups: string[] }
type Preference = { revision: number; enabled: number; disclosure_version: number; store_generation: string }
type Company = { enabled: boolean; groups: string[] }
const failure = () => new Error('telemetry_storage_unavailable')
const integer = (value: unknown, maximum: number, minimum = 0): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= minimum && value <= maximum
const generation = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{32}$/.test(value)
const stampValid = (value: TelemetryStamp) => value && integer(value.revision, 2147483646) && generation(value.store_generation)

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
  constructor(
    private readonly root: string,
    readonly disclosure: NativeTelemetryDisclosure,
    catalog: MeasurementCatalog,
    private readonly companyFile = nativeCompanyPolicyPath(),
  ) { this.catalog = new TelemetryCatalog(catalog) }

  get available(): boolean { return this.disclosure.collection_available && Boolean(this.disclosure.destination) }

  private safe(): string {
    if (!isAbsolute(this.root)) throw failure()
    const directory = lstatSync(this.root), path = join(this.root, 'product-telemetry.sqlite3'), file = lstatSync(path)
    if (!directory.isDirectory() || directory.isSymbolicLink() || !file.isFile() || file.isSymbolicLink() || file.nlink !== 1 || file.size > 96 * 1024) throw failure()
    if (process.platform !== 'win32' && [directory, file].some(item => item.uid !== process.getuid!() || (item.mode & 0o077))) throw failure()
    return path
  }

  private company(): Company {
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

  private async open(write = false): Promise<DatabaseSync> {
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

  private preferences(database: DatabaseSync): Preference {
    if (database.prepare('PRAGMA application_id').get()?.application_id !== 0x4D4E5450 ||
        database.prepare('PRAGMA user_version').get()?.user_version !== 3 ||
        database.prepare('PRAGMA journal_mode').get()?.journal_mode !== 'delete') throw failure()
    const row = database.prepare('SELECT revision, enabled, disclosure_version, store_generation FROM preferences WHERE singleton=1').get()
    if (!row || !integer(row.revision, 2147483647) || ![0, 1].includes(row.enabled as number) ||
        !integer(row.disclosure_version, this.disclosure.version) || !generation(row.store_generation) || row.revision === 2147483647) throw failure()
    return row as Preference
  }

  async snapshot(): Promise<TelemetryStamp | null> {
    if (!this.available) return null
    let database: DatabaseSync | undefined
    try {
      database = await this.open()
      database.exec('BEGIN')
      const preference = this.preferences(database), company = this.company()
      return preference.enabled === 1 && preference.disclosure_version === this.disclosure.version && company.enabled && company.groups.length
        ? { revision: preference.revision, store_generation: preference.store_generation } : null
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
      database = await this.open(true)
      database.exec('BEGIN IMMEDIATE')
      const preference = this.preferences(database)
      if (preference.revision !== expected.revision || preference.store_generation !== expected.store_generation) return false
      const company = this.company()
      if (preference.enabled !== 1 || preference.disclosure_version !== this.disclosure.version || !company.enabled || !company.groups.length) {
        database.exec('DELETE FROM pending; DELETE FROM producer_budget; COMMIT;')
        return false
      }
      database.prepare('DELETE FROM pending WHERE window_day < ? OR window_day > ?').run(day - 1, day)
      database.prepare('DELETE FROM producer_budget WHERE window_day != ?').run(day)
      const rows = database.prepare('SELECT cell, count, window_day FROM pending LIMIT 513').all()
      if (rows.length > 512) throw failure()
      for (const row of rows) {
        if (!integer(row.cell, 65535) || !integer(row.count, 255, 1) || !integer(row.window_day, 1000000)) throw failure()
        if (!company.groups.includes(this.catalog.describe(row.cell).group)) database.prepare('DELETE FROM pending WHERE cell=?').run(row.cell)
      }
      let recorded = false
      for (const { scope, cells } of observations) {
        const permitted = cells.filter(cell => company.groups.includes(this.catalog.describe(cell).group))
        const prior = database.prepare('SELECT count FROM producer_budget WHERE scope=?').get(scope)
        const limit = scope >= 512 ? this.catalog.specification.limits.resource_observations_per_day : this.catalog.specification.limits.observations_per_workflow_day
        const occupied = new Set(database.prepare('SELECT cell FROM pending LIMIT 513').all().map(row => row.cell))
        if (prior && !integer(prior.count, 64, 1)) throw failure()
        if (!permitted.length || (prior && Number(prior.count) >= limit) || new Set([...occupied, ...permitted]).size > 512) continue
        database.prepare('INSERT INTO producer_budget VALUES (?, 1, ?) ON CONFLICT(scope) DO UPDATE SET count=count+1, window_day=excluded.window_day').run(scope, day)
        const update = database.prepare('INSERT INTO pending VALUES (?, 1, ?) ON CONFLICT(cell) DO UPDATE SET count=CASE WHEN pending.window_day=excluded.window_day THEN min(pending.count+1, 255) ELSE 1 END, window_day=excluded.window_day')
        for (const cell of permitted) update.run(cell, day)
        recorded = true
      }
      database.exec('COMMIT')
      return recorded
    } catch { return false }
    finally { try { database?.close() } catch { /* Optional observation never breaks the caller. */ } }
  }
}
