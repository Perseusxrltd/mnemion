/** Native backup preferences, protected keys and one coalesced background job. */
import { constants, type Stats } from 'node:fs'
import { lstat, mkdir, open, realpath, unlink } from 'node:fs/promises'
import { dirname, isAbsolute, join } from 'node:path'
import { createHash, randomBytes, randomUUID } from 'node:crypto'
import type { CredentialCipher } from './workspace-store.js'
import type { LocalWorkspace } from './local-workspace.js'
import type { BackupFile, BackupReceipt, BackupConfiguration, BackupView, BackupSettings, BackupInventory, BackupRetentionResult } from '../shared/local-workspace.js'
import { backupResult, retentionPolicy, retentionResult } from './local-backup-protocol.js'
import { replaceFile } from './atomic-file.js'
import { BackupStateError, type BackupStateDiagnostic } from './backup-state-diagnostics.js'

type Stored = Omit<BackupConfiguration, 'protected_key'> & { format: 1; sealed_key: string | null }
type SchedulingRecords = {
  last_snapshot?: BackupReceipt
  last_ledger?: BackupReceipt
  failure?: { message: string; retry_at: string }
  snapshot_availability: BackupView['snapshot_availability']
  ledger_availability: BackupView['ledger_availability']
}

export function recoveryKey(value: unknown): string {
  if (typeof value !== 'string' || !/^mnm_bk_[A-Za-z0-9_-]{43}$/.test(value) ||
      Buffer.from(value.slice(7), 'base64url').toString('base64url') !== value.slice(7)) throw new Error('Enter the complete recovery key.')
  return value
}
export function createRecoveryKey(): string { return 'mnm_bk_' + randomBytes(32).toString('base64url') }
export function recoveryKeyId(value: string): string {
  return createHash('sha256').update('mnemion-backup-key-v1\0').update(Buffer.from(recoveryKey(value).slice(7), 'base64url')).digest('hex').slice(0, 24)
}

function privateBackupFile(info: Stats, allowUnlinked = false): boolean {
  return info.isFile() && !info.isSymbolicLink() && (info.nlink === 1 || (allowUnlinked && info.nlink === 0)) &&
    info.size <= 256 * 1024 &&
    (process.platform === 'win32' || ((info.mode & 0o077) === 0 && info.uid === process.getuid?.()))
}

function sameBackupVersion(before: Stats, after: Stats): boolean {
  return before.dev === after.dev && before.ino === after.ino && before.size === after.size &&
    before.mtimeMs === after.mtimeMs && before.ctimeMs === after.ctimeMs
}

export async function readBackupDocument(path: string): Promise<any | undefined> {
  // Writers replace these documents atomically. Refresh once if that happens
  // while reading, and validate the new descriptor independently before use.
  for (let attempt = 0; attempt < 2; attempt++) {
    let before
    try { before = await lstat(path) } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return undefined
      throw new BackupStateError(path, 'path', error)
    }
    if (!privateBackupFile(before)) throw new BackupStateError(path, 'path_private')
    let file
    let stage: BackupStateDiagnostic['stage'] = 'open'
    try {
      file = await open(path, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0))
      stage = 'descriptor'
      const actual = await file.stat()
      if (!privateBackupFile(actual, true)) throw new BackupStateError(path, 'descriptor_private')
      if (actual.dev !== before.dev || actual.ino !== before.ino || actual.nlink === 0) {
        if (attempt === 0) continue
        throw new BackupStateError(path, 'replacement_limit')
      }
      if (!sameBackupVersion(before, actual)) throw new BackupStateError(path, 'metadata_before_read')
      stage = 'read'
      const bytes = Buffer.alloc(256 * 1024 + 1)
      let length = 0
      while (length < bytes.length) {
        const read = await file.read(bytes, length, bytes.length - length)
        if (!read.bytesRead) break
        length += read.bytesRead
      }
      stage = 'metadata_after_read'
      const after = await file.stat()
      if (!privateBackupFile(after, true)) throw new BackupStateError(path, 'descriptor_private')
      if (after.nlink === 0) {
        if (attempt === 0) continue
        throw new BackupStateError(path, 'replacement_limit')
      }
      if (!sameBackupVersion(actual, after) || length !== actual.size || length > 256 * 1024) throw new BackupStateError(path, stage)
      stage = 'json'
      return JSON.parse(bytes.subarray(0, length).toString('utf8'))
    } catch (error) {
      throw error instanceof BackupStateError ? error : new BackupStateError(path, stage, error)
    } finally {
      await file?.close().catch(error => { throw new BackupStateError(path, 'close', error) })
    }
  }
  throw new BackupStateError(path, 'replacement_limit')
}

async function writeDocument(path: string, value: unknown, signal?: AbortSignal): Promise<void> {
  await mkdir(dirname(path), { recursive: true, mode: 0o700 })
  const temporary = path + '.' + randomUUID() + '.tmp'
  const file = await open(temporary, 'wx', 0o600)
  try {
    await file.writeFile(JSON.stringify(value) + '\n', 'utf8')
    await file.sync()
    await file.close()
    await replaceFile(temporary, path, signal)
  } finally {
    await file.close().catch(() => {})
    await unlink(temporary).catch(error => { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error })
  }
}

function decode(value: any, workspaceId: string): Stored {
  if (!value || typeof value !== 'object' || Array.isArray(value) || value.format !== 1 ||
      Object.keys(value).some(key => !['format', 'revision', 'workspace_id', 'destination', 'key_id', 'enabled', 'snapshot_hours', 'ledger_minutes', 'sealed_key', 'retention'].includes(key)) ||
      value.workspace_id !== workspaceId || !/^[a-f0-9-]{36}$/.test(value.revision) ||
      typeof value.destination !== 'string' || !isAbsolute(value.destination) || value.destination.length > 4096 ||
      /[\x00-\x1f\x7f]/.test(value.destination) || !/^[a-f0-9]{24}$/.test(value.key_id) ||
      typeof value.enabled !== 'boolean' || ![6, 12, 24, 168].includes(value.snapshot_hours) ||
      ![15, 30, 60, 240].includes(value.ledger_minutes) ||
      !(value.sealed_key === null || typeof value.sealed_key === 'string' && /^[A-Za-z0-9+/]+={0,2}$/.test(value.sealed_key) && value.sealed_key.length <= 16384) ||
      (value.enabled && !value.sealed_key)) throw new BackupStateError('backup-policy.json', 'policy')
  return { ...value, retention: retentionPolicy(value.retention) } as Stored
}

export class LocalBackups {
  private changing = false
  private running = false
  private checking = false
  private timer?: ReturnType<typeof setInterval>
  private retryAt = 0
  private error?: string
  private closed = false
  private generation = 0
  constructor(private host: LocalWorkspace, private cipher: CredentialCipher, private changed: () => void = () => {}) {}

  get busy(): boolean { return this.changing || this.running }
  private get file(): string { return join(this.host.dataDirectory, 'backup-policy.json') }
  private get failureFile(): string { return join(this.host.dataDirectory, 'backup-failure.json') }
  private workspaceId(): string {
    const id = this.host.status.info?.settings?.workspace_id
    if (!id) throw new Error('Create or open the local workspace before configuring its backups.')
    return id
  }
  private async configuration(): Promise<Stored | undefined> {
    const raw = await readBackupDocument(this.file)
    return raw === undefined ? undefined : decode(raw, this.workspaceId())
  }
  private async receipt(name: string, configuration?: Stored): Promise<BackupReceipt | undefined> {
    if (!configuration) return undefined
    const value = await readBackupDocument(join(this.host.dataDirectory, name))
    if (!value) return undefined
    const record = backupResult(name === 'last-backup.json' ? 'backup' : 'backup-ledger', value, configuration.workspace_id) as BackupReceipt
    const expected = join(configuration.destination, 'Mnemion backups', configuration.workspace_id)
    const same = (file: BackupFile) => {
      const path = dirname(file.file)
      return (process.platform === 'win32' ? path.toLowerCase() === expected.toLowerCase() : path === expected) && file.key_id === configuration.key_id
    }
    return same(record.ledger) && (!record.snapshot || same(record.snapshot)) ? record : undefined
  }
  private async availability(file?: BackupFile): Promise<BackupView['snapshot_availability']> {
    if (!file) return undefined
    try {
      const details = await lstat(file.file)
      return details.isFile() && !details.isSymbolicLink() && details.size === file.bytes ? 'present' : 'changed'
    } catch (error) { return (error as NodeJS.ErrnoException).code === 'ENOENT' ? 'missing' : 'unavailable' }
  }
  private async lastRetention(configuration?: Stored): Promise<BackupRetentionResult | undefined> {
    if (!configuration) return undefined
    const raw = await readBackupDocument(join(this.host.dataDirectory, 'last-retention.json'))
    if (!raw || raw.workspace_id !== configuration.workspace_id || raw.key_id !== configuration.key_id) return undefined
    const result = retentionResult(raw, configuration.workspace_id)
    const expected = join(configuration.destination, 'Mnemion backups', configuration.workspace_id)
    const normalize = (value: string) => process.platform === 'win32' ? value.toLowerCase() : value
    return normalize(result.folder) === normalize(expected) ? result : undefined
  }
  private async previousFailure(configuration?: Stored): Promise<{ message: string; retry_at: string } | undefined> {
    if (!configuration) return undefined
    const value = await readBackupDocument(this.failureFile)
    if (!value || value.workspace_id !== configuration.workspace_id || value.revision !== configuration.revision) return undefined
    if (value.format !== 1 || typeof value.message !== 'string' || value.message.length > 1000 ||
        typeof value.retry_at !== 'string' || value.retry_at.length > 40 || !Number.isFinite(Date.parse(value.retry_at))) throw new BackupStateError(this.failureFile, 'failure_record')
    return { message: value.message, retry_at: value.retry_at }
  }
  private due(last: string | undefined, interval: number): number {
    const now = Date.now(), previous = last ? Date.parse(last) : NaN
    return Number.isFinite(previous) && previous <= now + 300_000 ? previous + interval : now
  }
  private async schedulingRecords(configuration?: Stored): Promise<SchedulingRecords> {
    const [last_snapshot, last_ledger, failure] = await Promise.all([
      this.receipt('last-backup.json', configuration), this.receipt('last-ledger.json', configuration), this.previousFailure(configuration),
    ])
    const [snapshot_availability, ledger_availability] = await Promise.all([
      this.availability(last_snapshot?.snapshot), this.availability(last_ledger?.ledger),
    ])
    return { last_snapshot, last_ledger, failure, snapshot_availability, ledger_availability }
  }
  private scheduleTimes(configuration: Stored, records: SchedulingRecords): { snapshot: number; ledger: number } {
    return {
      snapshot: this.due(records.snapshot_availability === 'present' ? records.last_snapshot?.verified_at : undefined, configuration.snapshot_hours * 3600_000),
      ledger: this.due(records.ledger_availability === 'present' ? records.last_ledger?.verified_at : undefined, configuration.ledger_minutes * 60_000),
    }
  }
  async status(): Promise<BackupView> {
    const configuration = await this.configuration()
    const [secure_storage, records, last_retention] = await Promise.all([
      this.cipher.available(), this.schedulingRecords(configuration), this.lastRetention(configuration),
    ])
    const result: BackupView = { secure_storage: secure_storage === true, last_snapshot: records.last_snapshot, last_ledger: records.last_ledger, last_retention,
      last_error: this.error ?? records.failure?.message, retry_at: records.failure?.retry_at,
      snapshot_availability: records.snapshot_availability, ledger_availability: records.ledger_availability }
    if (configuration) {
      const { sealed_key, format: _, ...publicConfiguration } = configuration
      result.configuration = { ...publicConfiguration, protected_key: sealed_key !== null }
      if (configuration.enabled) {
        const times = this.scheduleTimes(configuration, records)
        result.next_snapshot_at = new Date(times.snapshot).toISOString()
        result.next_ledger_at = new Date(times.ledger).toISOString()
      }
    }
    return result
  }
  async configure(input: BackupSettings, signal?: AbortSignal): Promise<BackupView> {
    signal?.throwIfAborted()
    if (this.closed || this.busy) throw new Error('Another local operation is finishing. Try again when it completes.')
    if (!input || typeof input !== 'object' || typeof input.enabled !== 'boolean' || typeof input.key_saved !== 'boolean' ||
        ![6, 12, 24, 168].includes(input.snapshot_hours) || ![15, 30, 60, 240].includes(input.ledger_minutes) ||
        typeof input.destination !== 'string' || !isAbsolute(input.destination) || input.destination.length > 4096) throw new Error('Check the backup folder and schedule.')
    this.changing = true
    ++this.generation
    try {
      await this.host.waitForInspection()
      signal?.throwIfAborted()
      if (this.closed || this.host.busy) throw new Error('Another local operation is finishing. Try again when it completes.')
      const previous = await this.configuration()
      if ((previous?.revision ?? null) !== input.expected_revision) throw new Error('Backup settings changed. Refresh them before saving.')
      const destination = await realpath(input.destination)
      if (!(await lstat(destination)).isDirectory()) throw new Error('Choose an existing backup folder.')
      const relative = await realpath(this.host.dataDirectory)
      const prefix = (value: string) => process.platform === 'win32' ? value.toLowerCase() : value
      if (prefix(destination) === prefix(relative) || prefix(destination).startsWith(prefix(relative) + (process.platform === 'win32' ? '\\' : '/'))) throw new Error('Choose a backup folder outside the local workspace data.')
      let sealed_key = previous?.sealed_key ?? null, key_id = previous?.key_id
      if (input.recovery_key !== undefined) {
        if (!input.key_saved) throw new Error('Save the recovery key separately before enabling backups.')
        const key = recoveryKey(input.recovery_key)
        key_id = recoveryKeyId(key)
        if (input.enabled && !await this.cipher.available()) throw new Error('Unlock the OS secure store for scheduled backups, or choose manual backups without remembering the key.')
        const sealed = input.enabled ? await this.cipher.encrypt(JSON.stringify({ workspace_id: this.workspaceId(), key })) : null
        if (sealed && (!Buffer.isBuffer(sealed) || !sealed.length || sealed.length > 16384)) throw new Error('The OS secure store did not protect this recovery key.')
        sealed_key = sealed ? sealed.toString('base64') : null
      }
      if (!key_id) throw new Error('Generate or provide a recovery key before saving.')
      if (input.enabled && !sealed_key) throw new Error('Enter the recovery key and unlock the OS secure store to enable scheduled backups. Manual backups can use a key for one run.')
      const configuration: Stored = { format: 1, revision: randomUUID(), workspace_id: this.workspaceId(), destination,
        enabled: input.enabled, snapshot_hours: input.snapshot_hours, ledger_minutes: input.ledger_minutes, key_id, sealed_key,
        retention: retentionPolicy(input.retention === undefined ? previous?.retention : input.retention) }
      if (this.closed || ((await this.configuration())?.revision ?? null) !== input.expected_revision) throw new Error('Backup settings changed before the save finished. Refresh and retry.')
      signal?.throwIfAborted()
      await writeDocument(this.file, configuration, signal)
      this.error = undefined
      this.retryAt = 0
      return await this.status()
    } finally { this.changing = false; this.changed() }
  }
  private async key(configuration: Stored, supplied?: string): Promise<string> {
    if (supplied !== undefined) {
      const value = recoveryKey(supplied)
      if (recoveryKeyId(value) !== configuration.key_id) throw new Error('This key does not match the configured backups. Update the key in backup settings to rotate it.')
      return value
    }
    if (!configuration.sealed_key) throw new Error('Enter the recovery key for this manual backup.')
    if (!await this.cipher.available()) throw new Error('Unlock the OS secure store or enter the recovery key for this run.')
    let clear
    try { clear = JSON.parse(await this.cipher.decrypt(Buffer.from(configuration.sealed_key, 'base64'))) }
    catch { throw new Error('The OS secure store could not open the recovery key. Unlock it or enter the key for this run.') }
    if (clear.workspace_id !== configuration.workspace_id || recoveryKeyId(clear.key) !== configuration.key_id) throw new Error('The protected recovery key does not match this workspace.')
    return clear.key
  }
  async run(ledgerOnly = false, suppliedKey?: string, signal?: AbortSignal): Promise<BackupReceipt> {
    signal?.throwIfAborted()
    if (this.closed || this.busy) throw new Error('Another local operation is finishing. Try again when it completes.')
    this.running = true
    const generation = ++this.generation
    let configuration: Stored | undefined
    try {
      await this.host.waitForInspection()
      signal?.throwIfAborted()
      if (this.closed || this.host.busy || generation !== this.generation) throw new Error('Another local operation is finishing. Try again when it completes.')
      configuration = await this.configuration()
      if (!configuration) throw new Error('Choose the backup folder and recovery key first.')
      const key = await this.key(configuration, suppliedKey)
      signal?.throwIfAborted()
      if (this.closed || generation !== this.generation) throw new Error('Backup cancelled. Existing recovery files were retained.')
      const result = await this.host.runBackup(ledgerOnly ? 'backup-ledger' : 'backup', {
        workspace_id: configuration.workspace_id, destination: configuration.destination, recovery_key: key, retention: configuration.retention,
      }, signal) as BackupReceipt
      this.error = undefined; this.retryAt = 0
      await unlink(this.failureFile).catch(error => {
        if ((error as NodeJS.ErrnoException).code !== 'ENOENT') this.error = 'Backup verified, but its previous failure notice could not be cleared.'
      })
      return result
    } catch (error) {
      this.error = error instanceof Error ? error.message : 'The backup could not finish. Existing backups were retained.'
      this.retryAt = Date.now() + 15 * 60_000
      if (configuration) await writeDocument(this.failureFile, { format: 1, workspace_id: configuration.workspace_id,
        revision: configuration.revision, message: this.error.slice(0, 1000), retry_at: new Date(this.retryAt).toISOString() }).catch(() => {})
      throw error
    } finally { this.running = false; this.changed() }
  }
  private async retentionAction(input?: { expected_revision: string; plan_token: string; confirm: boolean }, signal?: AbortSignal): Promise<BackupInventory | BackupRetentionResult> {
    signal?.throwIfAborted()
    if (this.closed || this.busy) throw new Error('Another local operation is finishing. Try again when it completes.')
    this.running = true
    const generation = ++this.generation
    try {
      await this.host.waitForInspection()
      signal?.throwIfAborted()
      if (this.closed || this.host.busy || generation !== this.generation) throw new Error('Another local operation is finishing. Try again when it completes.')
      const configuration = await this.configuration()
      if (!configuration) throw new Error('Choose the backup folder and recovery key first.')
      if (input && (input.confirm !== true || !/^[a-f0-9]{64}$/.test(input.plan_token) ||
          input.expected_revision !== configuration.revision || configuration.retention.mode !== 'limited')) throw new Error('Review the current inventory and confirm the configured cleanup plan.')
      return await this.host.runBackup(input ? 'backup-prune' : 'backup-inventory', {
        workspace_id: configuration.workspace_id, destination: configuration.destination, key_id: configuration.key_id,
        policy: configuration.retention, ...(input ? { plan_token: input.plan_token, confirm: true } : {}),
      }, signal) as BackupInventory | BackupRetentionResult
    } finally { this.running = false; this.changed() }
  }
  async inventory(signal?: AbortSignal): Promise<BackupInventory> {
    return this.retentionAction(undefined, signal) as Promise<BackupInventory>
  }
  async prune(input: { expected_revision: string; plan_token: string; confirm: boolean }, signal?: AbortSignal): Promise<BackupRetentionResult> {
    if (!input || typeof input !== 'object') throw new Error('Review and confirm the current cleanup plan.')
    return this.retentionAction(input, signal) as Promise<BackupRetentionResult>
  }
  start(): void {
    if (this.timer || this.closed) return
    this.timer = setInterval(() => { void this.tick() }, 60_000)
    this.timer.unref()
    void this.tick()
  }
  // Idle ticks stop at the policy. Enabled ticks share the due calculation with status(),
  // without asking whether the secure store is available or loading retention display.
  private async scheduledAction(): Promise<{ snapshot: boolean } | undefined> {
    const configuration = await this.configuration()
    if (!configuration?.enabled) return undefined
    const records = await this.schedulingRecords(configuration)
    if (records.failure?.retry_at && Date.parse(records.failure.retry_at) > Date.now()) return undefined
    const times = this.scheduleTimes(configuration, records), now = Date.now()
    const snapshot = times.snapshot <= now
    if (!snapshot && times.ledger > now) return undefined
    return { snapshot }
  }
  private async tick(): Promise<void> {
    if (this.closed || this.checking || this.busy || this.host.busy || this.host.status.state !== 'running' || Date.now() < this.retryAt) return
    this.checking = true
    const generation = this.generation
    try {
      const action = await this.scheduledAction()
      if (!action || this.closed || this.busy || this.host.busy || generation !== this.generation) return
      await this.run(!action.snapshot)
    } catch (error) {
      this.error = error instanceof Error ? error.message : 'Scheduled backup needs attention.'
      this.retryAt = Date.now() + 15 * 60_000
      this.changed()
    } finally { this.checking = false }
  }
  close(): void {
    this.closed = true
    if (this.timer) clearInterval(this.timer)
    this.timer = undefined
    this.cancel()
  }
  cancel(): void { ++this.generation; this.host.cancelBackup() }
}
