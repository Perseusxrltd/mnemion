import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { existsSync } from 'node:fs'
import { StringDecoder } from 'node:string_decoder'
import { localDiagnostic, processExitDiagnostic } from './local-diagnostics.js'
export { localDiagnostic } from './local-diagnostics.js'
import { backupResult } from './local-backup-protocol.js'
import { companyOptions, companyDiscoveryOptions, companyDiscoveryResult, companySnapshot } from './local-company-protocol.js'
import { vaultKeyId, vaultKeyResult, vaultOptions, vaultRequest, vaultSnapshot } from './local-vault-protocol.js'
import { journalOptions, journalSnapshot } from './local-journal-protocol.js'
import { modelsOptions, modelsSaved, modelsSnapshot } from './local-models-protocol.js'
import type { ModelsChange } from '../shared/local-models.js'
import type { JournalChange } from '../shared/local-workspace.js'
import type { VaultChange, VaultKey } from '../shared/local-workspace.js'
import type { CompanyChange, CompanyDiscoveryResult } from '../shared/local-workspace.js'
import type { BackupAction, BackupOperationResult } from '../shared/local-workspace.js'
import type { LocalOptions, LocalInfo, LocalStatus, MemoryChange, MemoryWrite, MemorySnapshot, MemoryPolicy, PortChange, LocalDiagnostic, RemoteChange, RemoteAccess, RemoteCheck } from '../shared/local-workspace.js'
type Connection = { endpoint: string; credential: string; workspaceId: string; tenantId: string; version: string }
type Options = { executable: string; database: string; root: string; version: string; environment: NodeJS.ProcessEnv; desktopMemory?: () => number }

export function memoryOptions(input: unknown, revision = false): MemoryChange & { repair_token?: string } {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Choose automatic memory management or a RAM budget of at least 256 MiB.')
  const value = input as MemoryChange & { repair_token?: string }
  const allowed = revision ? ['mode', 'limit_mib', 'expected_revision', 'repair_token'] : ['mode', 'limit_mib']
  if (Object.keys(value).some(key => !allowed.includes(key)) ||
      (value.mode !== 'auto' && value.mode !== 'manual') ||
      (value.mode === 'auto' ? value.limit_mib !== null : (!Number.isInteger(value.limit_mib) || value.limit_mib < 256 || value.limit_mib > 1048576)) ||
      (value.repair_token !== undefined && (typeof value.repair_token !== 'string' || !/^[a-f0-9]{64}$/.test(value.repair_token) || value.expected_revision !== undefined)) ||
      (value.expected_revision !== undefined && (typeof value.expected_revision !== 'string' || !/^[a-z0-9-]{1,64}$/.test(value.expected_revision)))) {
    throw new Error('Choose automatic memory management or a RAM budget of at least 256 MiB.')
  }
  return { ...value }
}

function memorySnapshot(input: unknown): MemorySnapshot {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid RAM status')
  const value = input as MemorySnapshot
  if (value.enforcement !== 'cooperative' || value.scope !== 'local_engine_database_and_reported_desktop' ||
      !['normal', 'constrained', 'paused'].includes(value.state) || typeof value.revision !== 'string' || value.revision.length > 64 ||
      !['target_bytes', 'used_bytes', 'engine_bytes', 'database_bytes', 'desktop_bytes', 'effective_hardware_bytes', 'available_hardware_bytes'].every(key =>
        typeof value[key as keyof MemorySnapshot] === 'number' && Number.isFinite(value[key as keyof MemorySnapshot]) && Number(value[key as keyof MemorySnapshot]) >= 0)) throw new Error('Invalid RAM status')
  return value
}

export function localOptions(input: unknown): LocalOptions {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Check the workspace settings.')
  const value = input as LocalOptions
  if (Object.keys(value).some(key => !['workspace_name', 'owner_name', 'embedding_profile', 'threads', 'port', 'memory'].includes(key)) ||
      !['workspace_name', 'owner_name'].every(key => typeof value[key as keyof LocalOptions] === 'string' &&
        (value[key as keyof LocalOptions] as string).trim().length > 0 && (value[key as keyof LocalOptions] as string).length <= 200 &&
        !/[\x00-\x1f\x7f]/.test(value[key as keyof LocalOptions] as string)) ||
      !['e5-small', 'bge-small-en'].includes(value.embedding_profile) ||
      !Number.isInteger(value.threads) || value.threads < 1 || value.threads > 8 ||
      !Number.isInteger(value.port) || value.port < 1024 || value.port > 65535) throw new Error('Check the workspace names, model and resource settings.')
  return { workspace_name: value.workspace_name.trim(), owner_name: value.owner_name.trim(),
    embedding_profile: value.embedding_profile, threads: value.threads, port: value.port,
    memory: memoryOptions(value.memory ?? { mode: 'auto', limit_mib: null }) }
}

export function localEnvironment(source: NodeJS.ProcessEnv, root: string): NodeJS.ProcessEnv {
  const allowed = new Set(['path', 'home', 'userprofile', 'appdata', 'localappdata', 'systemroot', 'windir', 'comspec',
    'temp', 'tmp', 'tmpdir', 'lang', 'lc_all', 'lc_ctype', 'ssl_cert_file', 'ssl_cert_dir', 'requests_ca_bundle',
    'curl_ca_bundle', 'http_proxy', 'https_proxy', 'no_proxy', 'all_proxy', '__cf_user_text_encoding'])
  const environment = Object.fromEntries(Object.entries(source).filter(([key, value]) => value !== undefined && allowed.has(key.toLowerCase())))
  return { ...environment, HF_HOME: root + '/model-download-cache', HF_HUB_DISABLE_TELEMETRY: '1', HF_HUB_DISABLE_PROGRESS_BARS: '1' }
}

export function portOptions(input: unknown): PortChange {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Choose a valid local address.')
  const value = input as PortChange
  const validPort = (port: unknown) => Number.isInteger(port) && Number(port) >= 1024 && Number(port) <= 65535
  if (Object.keys(value).some(key => !['workspace_id', 'expected_port', 'port'].includes(key)) ||
      typeof value.workspace_id !== 'string' || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(value.workspace_id) ||
      !validPort(value.expected_port) || (value.port !== null && !validPort(value.port))) throw new Error('Choose a valid local address.')
  return { workspace_id: value.workspace_id, expected_port: value.expected_port, port: value.port }
}

const remoteRevision = /^(?:not-configured|[a-f0-9-]{36}|[a-f0-9]{64})$/

function remoteOrigin(input: unknown): string {
  try {
    if (typeof input !== 'string' || input.length > 2048 || /[\s\\]/.test(input)) throw new Error()
    const url = new URL(input)
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash ||
        !['/', '/mcp', '/mcp/'].includes(url.pathname)) throw new Error()
    return url.origin
  } catch { throw new Error('Enter an HTTPS origin without credentials, a query or a path.') }
}

export function remoteOptions(input: unknown): RemoteChange {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Check the remote access settings.')
  const value = input as RemoteChange
  if (Object.keys(value).some(key => !['workspace_id', 'expected_revision', 'mode', 'public_url', 'personal_sign_in', 'ngrok_authtoken'].includes(key)) ||
      typeof value.workspace_id !== 'string' || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(value.workspace_id) ||
      typeof value.expected_revision !== 'string' || !remoteRevision.test(value.expected_revision) ||
      !['disabled', 'ngrok', 'proxy'].includes(value.mode) || typeof value.personal_sign_in !== 'boolean' ||
      (value.ngrok_authtoken != null && (typeof value.ngrok_authtoken !== 'string' || !/^[\x21-\x7e]{16,256}$/.test(value.ngrok_authtoken)))) {
    throw new Error('Check the remote access settings and refresh their current revision.')
  }
  const public_url = value.mode === 'disabled' ? null : remoteOrigin(value.public_url)
  if (value.mode === 'ngrok' && new URL(public_url!).port) throw new Error('Use your ngrok HTTPS domain without a port.')
  return { ...value, workspace_id: value.workspace_id.toLowerCase(), public_url,
    ngrok_authtoken: value.mode === 'ngrok' ? value.ngrok_authtoken ?? null : null }
}

export function remoteSnapshot(input: unknown): RemoteAccess {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid remote access status')
  const value = input as RemoteAccess
  if (Object.keys(value).some(key => !['mode', 'public_url', 'personal_sign_in', 'has_ngrok_authtoken', 'revision', 'repairable', 'state', 'message', 'checked_at', 'verified_at', 'provider_code'].includes(key)) ||
      !['disabled', 'ngrok', 'proxy'].includes(value.mode) || typeof value.personal_sign_in !== 'boolean' ||
      typeof value.has_ngrok_authtoken !== 'boolean' || typeof value.repairable !== 'boolean' ||
      typeof value.revision !== 'string' || !(remoteRevision.test(value.revision) || value.revision === 'unreadable') ||
      !['disabled', 'unchecked', 'stopped', 'configuration_error', 'connecting', 'online', 'unavailable'].includes(value.state) ||
      typeof value.message !== 'string' || value.message.length > 512 ||
      (value.public_url !== null && remoteOrigin(value.public_url) !== value.public_url) ||
      [value.checked_at, value.verified_at].some(stamp => stamp != null && (typeof stamp !== 'string' || stamp.length > 40 || !Number.isFinite(Date.parse(stamp)))) ||
      (value.provider_code != null && (typeof value.provider_code !== 'string' || !/^ERR_NGROK_[0-9]{1,8}$/.test(value.provider_code)))) {
    throw new Error('Invalid remote access status')
  }
  return structuredClone(value)
}

export class LocalWorkspace {
  private child?: ChildProcessWithoutNullStreams
  private connection?: Connection
  private info?: LocalInfo
  private operation?: Promise<LocalInfo>
  private memoryChange?: Promise<LocalStatus>
  private configurationChange?: Promise<LocalStatus>
  private backupWork?: Promise<BackupOperationResult>
  private shutdownFailed = false
  private backupChild?: ChildProcessWithoutNullStreams
  private stopping?: Promise<boolean>
  private closing?: Promise<boolean>
  private controls = new Set<ChildProcessWithoutNullStreams>()
  private intentionalStop = false
  private updateResumeRequested = false
  private cancelledUpdateStop = false
  private statusValue: LocalStatus
  private disposed = false

  constructor(private options: Options, private changed: (status: LocalStatus) => void) {
    this.statusValue = { available: existsSync(options.executable) && existsSync(options.database), state: 'new',
      message: 'Create a private memory workspace on this computer.' }
  }

  get status(): LocalStatus { return { ...this.statusValue, info: this.info } }
  get dataDirectory(): string { return this.options.root }
  get backupActive(): boolean { return !!this.backupWork }
  async waitForInspection(): Promise<void> { await this.operation }
  get active(): boolean { return !!this.child || this.controls.size > 0 || !!this.operation || !!this.memoryChange || !!this.configurationChange || !!this.backupWork }
  get busy(): boolean { return !!this.operation || !!this.memoryChange || !!this.configurationChange || !!this.backupWork || this.controls.size > 0 || !!this.stopping || !!this.closing || ['starting', 'stopping'].includes(this.statusValue.state) }

  private assertOpen() {
    if (this.disposed || this.closing) throw new Error('The app is closing.')
    if (this.stopping) throw new Error('The local workspace is stopping. Wait for it to finish before trying again.')
  }

  private control(action: string): ChildProcessWithoutNullStreams {
    const child = spawn(this.options.executable, this.command(action), { env: this.options.environment, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] })
    this.controls.add(child)
    child.once('close', () => this.controls.delete(child))
    child.stdin.on('error', () => { /* Command failures are reported by error/close. */ })
    return child
  }

  private set(value: Partial<LocalStatus>) {
    this.statusValue = { ...this.statusValue, ...value }
    this.changed(this.status)
  }

  private command(action: string): string[] {
    return ['local', action, '--root', this.options.root, '--database-runtime', this.options.database]
  }

  async runBackup(action: BackupAction, input: Record<string, unknown>, signal?: AbortSignal): Promise<BackupOperationResult> {
    // A read-only status refresh must not make a just-opened recovery form fail.
    // Recheck mutation/stop guards after that refresh has actually drained.
    if (this.operation) await this.waitForInspection()
    signal?.throwIfAborted()
    this.assertOpen()
    if (!['backup', 'backup-ledger', 'backup-inspect', 'backup-restore', 'backup-inventory', 'backup-prune'].includes(action)) throw new Error('Choose a supported backup operation.')
    if (!this.status.available) throw new Error('Install the complete desktop app to use local backups and recovery.')
    if (this.backupWork || this.configurationChange || this.memoryChange || this.operation) throw new Error('Another local operation is finishing. Try again when it completes.')
    if (['backup', 'backup-ledger'].includes(action) && this.status.state !== 'running') throw new Error('Start the local workspace before backing it up.')
    const body = JSON.stringify({ ...input, watch_parent: true }) + '\n'
    if (Buffer.byteLength(body) > 16384) throw new Error('The backup request is too large.')
    const started_at = new Date().toISOString()
    this.set({ backup: { action, state: 'running', stage: 'starting', message: 'Preparing the recovery operation…', started_at } })
    const pending = new Promise<BackupOperationResult>((resolve, reject) => {
      const child = this.control(action)
      this.backupChild = child
      const abort = () => { if (this.backupChild === child) this.cancelBackup() }
      signal?.addEventListener('abort', abort, { once: true })
      const decoder = new StringDecoder('utf8')
      let line = '', total = 0, failure: Error | undefined, result: unknown, cancelled = false
      let diagnostic: LocalDiagnostic | undefined
      const timer = setTimeout(() => {
        failure = new Error('The recovery operation exceeded its time limit and is stopping safely.')
        this.cancelBackup()
      }, 4 * 60 * 60 * 1000)
      const accept = (text: string) => {
        if (!text.trim() || failure) return
        try {
          const value = JSON.parse(text)
          if (value.event === 'backup_progress') {
            if (typeof value.stage !== 'string' || !/^[a-z_]{1,64}$/.test(value.stage) ||
                typeof value.message !== 'string' || value.message.length > 1000) throw new Error()
            this.set({ backup: { action, state: this.statusValue.backup?.state === 'cancelling' ? 'cancelling' : 'running', stage: value.stage, message: value.message, started_at } })
          } else if (value.event === 'error') {
            diagnostic = localDiagnostic(value.diagnostic)
            failure = new Error(typeof value.message === 'string' && value.message.length <= 1000 ? value.message : 'The recovery operation could not finish.')
          } else if (value.event === 'cancelled') {
            cancelled = true
          } else {
            const event = action === 'backup-inspect' ? 'backup_inspection' : action === 'backup-restore' ? 'recovery' : action === 'backup-inventory' ? 'backup_inventory' : action === 'backup-prune' ? 'backup_retention' : 'backup'
            if (result !== undefined || value.event !== event || value.engine_version !== this.options.version) throw new Error()
            result = backupResult(action, action === 'backup-inspect' ? value.inspection : value.receipt, String(input.workspace_id ?? ''))
          }
        } catch {
          failure = new Error('The native runtime returned an invalid recovery result. Review the saved backup inventory before retrying.')
          this.cancelBackup()
        }
      }
      child.stdout.on('data', (chunk: Buffer) => {
        total += chunk.length
        if (total > 1024 * 1024) {
          failure ??= new Error('The recovery inventory is too large for this view. Existing data was retained.')
          this.cancelBackup()
          return
        }
        line += decoder.write(chunk)
        let boundary: number
        while ((boundary = line.indexOf('\n')) !== -1) {
          accept(line.slice(0, boundary)); line = line.slice(boundary + 1)
        }
      })
      child.stderr.resume()
      child.once('error', () => { failure = new Error('The native recovery runtime could not start. Reinstall the complete app.') })
      child.once('close', code => {
        signal?.removeEventListener('abort', abort)
        clearTimeout(timer)
        if (this.backupChild === child) this.backupChild = undefined
        accept(line + decoder.end())
        const finished_at = new Date().toISOString()
        if (code === 0 && result !== undefined && !failure) {
          this.set({ backup: { action, state: 'complete', stage: 'complete', message: 'Recovery operation verified and complete.', started_at, finished_at } })
          resolve(result as BackupOperationResult)
        } else {
          const message = cancelled ? 'Operation cancelled. Verified recovery points remain available; review the inventory for any completed cleanup removals.' : failure?.message ?? 'The recovery operation could not finish. Existing workspace data was retained.'
          this.set({ backup: { action, state: cancelled ? 'cancelled' : 'error', stage: cancelled ? 'cancelled' : 'error', message, started_at, finished_at,
            ...(!cancelled && diagnostic ? { diagnostic } : {}) } })
          reject(new Error(message))
        }
      })
      child.stdin.write(body)
    })
    this.backupWork = pending
    try { return await pending } finally { if (this.backupWork === pending) this.backupWork = undefined }
  }

  cancelBackup(): LocalStatus {
    const child = this.backupChild
    if (child && !child.stdin.destroyed && !child.stdin.writableEnded) {
      child.stdin.write('{"action":"cancel"}\n')
      if (this.statusValue.backup) this.set({ backup: { ...this.statusValue.backup, state: 'cancelling', message: 'Stopping safely and cleaning private temporary files…' } })
    }
    return this.status
  }

  async inspect(): Promise<LocalInfo> {
    this.assertOpen()
    if (!this.status.available) throw new Error('The complete local runtime is missing. Reinstall Mnemion Studio to create a workspace on this computer.')
    // A concurrent status read must not publish pre-save settings after the
    // address writer has confirmed its replacement. Refresh even after an
    // unconfirmed write so callers can recover from a partial completion.
    if (this.configurationChange) {
      await this.configurationChange.catch(() => undefined)
      this.assertOpen()
    }
    if (this.operation) return this.operation
    this.operation = this.readInfo('status')
    try { return await this.operation } finally { this.operation = undefined }
  }

  private readInfo(action: 'status' | 'port' | 'remote' | 'remote-check' | 'company' | 'vault' | 'journal' | 'models', input?: PortChange | RemoteChange | RemoteCheck | CompanyChange | VaultChange | JournalChange | ModelsChange): Promise<LocalInfo> {
    return new Promise((resolve, reject) => {
      const child = this.control(action)
      child.stdin.end(input === undefined ? undefined : JSON.stringify(input) + '\n')
      let body = ''
      let failed = false
      const timer = setTimeout(() => { failed = true; child.kill(); reject(new Error(action !== 'status'
        ? 'The host settings change could not be confirmed. Refresh its status before retrying.'
        : 'The local runtime check timed out. Try again.')) }, 20_000)
      child.stdout.on('data', (chunk: Buffer) => {
        body += chunk.toString('utf8')
        if (body.length > 256 * 1024) { failed = true; child.kill(); reject(new Error('The local runtime returned an invalid status.')) }
      })
      child.stderr.resume()
      child.on('error', () => { failed = true; reject(new Error('The local runtime could not start. Reinstall the complete app.')) })
      child.on('close', code => {
        clearTimeout(timer)
        if (failed) return
        try {
          const value = JSON.parse(body)
          if (code !== 0 || value.event !== 'status') throw new Error(value.event === 'error' && typeof value.message === 'string' && value.message.length <= 1000 ? value.message : 'The local runtime could not read its settings.')
          if (value.engine_version !== this.options.version || typeof value.configured !== 'boolean' || value.data_directory !== this.options.root ||
              !value.resources || typeof value.resources.memory_bytes !== 'number' || typeof value.resources.available_disk_bytes !== 'number') {
            throw new Error('The local runtime does not match this app. Reinstall the complete app.')
          }
          const { configured, data_directory, engine_version, resources, settings, last_verification, memory_policy, memory_recovery, memory } = value
          const remote_access = value.remote_access === undefined ? undefined : remoteSnapshot(value.remote_access)
          const company_access = value.company_access === undefined ? undefined : companySnapshot(value.company_access)
          const vault_access = value.vault_access === undefined ? undefined : vaultSnapshot(value.vault_access)
          const journal_access = value.journal_access === undefined ? undefined : journalSnapshot(value.journal_access)
          const model_access = value.model_access === undefined ? undefined : modelsSnapshot(value.model_access)
          const address = input as PortChange
          if (action === 'port' && (!configured || !settings || settings.workspace_id !== input!.workspace_id.toLowerCase() ||
              !Number.isInteger(settings.port) || settings.port < 1024 || settings.port > 65535 || settings.port === settings.database_port ||
              (address.port !== null && settings.port !== address.port))) throw new Error('The saved local address could not be confirmed. Refresh before retrying.')
          const sharing = input as RemoteChange
          if (action === 'remote' && (!configured || !settings || settings.workspace_id !== sharing.workspace_id ||
              !remote_access || remote_access.state === 'configuration_error' || remote_access.revision === sharing.expected_revision ||
              remote_access.mode !== sharing.mode || remote_access.public_url !== sharing.public_url ||
              remote_access.personal_sign_in !== sharing.personal_sign_in ||
              (sharing.mode === 'ngrok' && !remote_access.has_ngrok_authtoken))) throw new Error('The saved remote settings could not be confirmed. Refresh before retrying.')
          if (action === 'company') {
            const change = input as CompanyChange
            const provider = company_access?.providers.find(item => item.id === (change.action === 'save' ? change.provider.id : change.action === 'remove' ? change.provider_id : ''))
            if (!configured || settings?.workspace_id !== change.workspace_id || !company_access || company_access.state === 'configuration_error' ||
                company_access.revision === change.expected_revision || remote_access?.revision !== change.expected_remote_revision ||
                (change.action === 'remove' && provider) || (change.action === 'reset' && company_access.providers.length) ||
                (change.action === 'save' && (!provider || Object.entries(change.provider).some(([key, value]) => provider[key as keyof typeof provider] !== value) ||
                  (change.client_secret && !provider.has_client_secret) || (change.clear_client_secret && provider.has_client_secret) ||
                  (Object.hasOwn(change, 'ca_pem') && company_access.has_custom_ca !== !!change.ca_pem)))) throw new Error('The saved company settings could not be confirmed. Refresh before retrying.')
          }
          if (action === 'vault') {
            const change = input as VaultChange
            if (!configured || settings?.workspace_id !== change.workspace_id || !vault_access ||
                vault_access.state === 'configuration_error' || vault_access.revision === change.expected_revision ||
                vault_access.enabled !== change.enabled || vault_access.mcp_enabled !== change.mcp_enabled ||
                (change.recovery_key && vault_access.key_id !== vaultKeyId(change.recovery_key))) throw new Error('The saved vault settings could not be confirmed. Refresh before retrying.')
          }
          if (action === 'journal') {
            const change = input as JournalChange
            const destination = journal_access?.destinations.find(item => item.space_id === (change.action === 'save' ? change.destination.space_id : change.action === 'remove' ? change.space_id : ''))
            if (!configured || settings?.workspace_id !== change.workspace_id || !journal_access ||
                ['configuration_error', 'external'].includes(journal_access.state) || journal_access.revision === change.expected_revision ||
                (change.action === 'remove' && destination) || (change.action === 'reset' && journal_access.destinations.length) ||
                (change.action === 'save' && (!destination || Object.entries(change.destination).some(([key, value]) => destination[key as keyof typeof destination] !== value)))) throw new Error('The saved journal destination could not be confirmed. Refresh before retrying.')
          }
          if (action === 'models' && (!configured || settings?.workspace_id !== input!.workspace_id || !modelsSaved(model_access, input as ModelsChange))) throw new Error('The saved model settings could not be confirmed. Refresh before retrying.')
          if (memory_recovery && (!['memory_policy_missing', 'memory_policy_damaged', 'memory_policy_inaccessible'].includes(memory_recovery.code) ||
              typeof memory_recovery.message !== 'string' || memory_recovery.message.length > 1000 ||
              (memory_recovery.repair_token !== null && !/^[a-f0-9]{64}$/.test(memory_recovery.repair_token)))) throw new Error('Invalid RAM recovery status')
          const info = { configured, data_directory, engine_version, resources, settings, last_verification, memory_policy, memory_recovery, memory, remote_access, company_access, vault_access, journal_access, model_access }
          this.info = info
          this.changed(this.status)
          resolve(info)
        } catch (error) { reject(error instanceof Error ? error : new Error('The local runtime returned an invalid status.')) }
      })
    })
  }

  async start(input?: unknown): Promise<LocalStatus> {
    this.assertOpen()
    if (this.backupWork) throw new Error('Finish or cancel the recovery operation before starting the workspace.')
    if (this.configurationChange) throw new Error('The local address is being saved. Wait for it to finish.')
    if (this.child) return this.status
    const options = input === undefined ? undefined : localOptions(input)
    const info = await this.inspect()
    this.assertOpen()
    if (this.configurationChange) throw new Error('The local address is being saved. Wait for it to finish.')
    if (this.child) return this.status
    if (!options && !info.configured) throw new Error('Choose the workspace settings before starting.')
    return this.launch(info, options)
  }

  private launch(info: LocalInfo, options?: LocalOptions): LocalStatus {
    if (info.memory_recovery) throw new Error('Repair the saved RAM budget before resuming this workspace.')
    this.intentionalStop = false
    this.shutdownFailed = false
    this.connection = undefined
    this.set({ state: 'starting', stage: 'starting', message: info.configured ? 'Opening your local workspace…' : 'Creating your local workspace…', errorCode: undefined, diagnostic: undefined })
    const child = spawn(this.options.executable, this.command(options ? 'initialize' : 'run'), {
      env: this.options.environment, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
    })
    this.child = child
    const decoder = new StringDecoder('utf8')
    let pending = ''
    const invalid = () => {
      this.set({ state: 'stopping', errorCode: 'invalid_runtime_response', message: 'The local runtime returned an invalid response. Your saved data has been retained.' })
      child.stdin.end('{"action":"stop"}\n')
    }
    child.stdout.on('data', (chunk: Buffer) => {
      pending += decoder.write(chunk)
      if (pending.length > 256 * 1024) { invalid(); pending = ''; return }
      let end: number
      while ((end = pending.indexOf('\n')) !== -1) {
        const line = pending.slice(0, end); pending = pending.slice(end + 1)
        if (line.length > 32768) { invalid(); return }
        try {
          const value = JSON.parse(line)
          if (value.event === 'resources') {
            const memory = memorySnapshot(value.memory)
            this.set({ memory })
            if ((memory.reason === 'policy_unavailable') !== !!this.info?.memory_recovery ||
                (memory.reason !== 'policy_unavailable' && memory.revision !== this.info?.memory_policy?.revision)) void this.inspect().catch(() => {})
          } else if (value.event === 'remote_access' && this.info) {
            this.info = { ...this.info, remote_access: remoteSnapshot(value.remote_access) }
            this.changed(this.status)
          } else if (value.event === 'progress' && typeof value.stage === 'string' && value.stage.length <= 64 && typeof value.message === 'string' && value.message.length <= 1000) {
            this.set({ stage: value.stage, message: value.message })
          } else if (value.event === 'ready') {
            const endpoint = new URL(value.endpoint)
            if (endpoint.protocol !== 'http:' || endpoint.hostname !== '127.0.0.1' || !endpoint.port || endpoint.pathname !== '/' || endpoint.username || endpoint.password || endpoint.search || endpoint.hash ||
                typeof value.credential !== 'string' || !/^mnm_[A-Za-z0-9_-]{40,100}$/.test(value.credential) ||
                typeof value.workspace_id !== 'string' || !/^[a-f0-9-]{36}$/.test(value.workspace_id) ||
                typeof value.tenant_id !== 'string' || !/^[a-f0-9-]{36}$/.test(value.tenant_id) || value.engine_version !== this.options.version) throw new Error('Invalid private connection')
            if (this.intentionalStop) { child.stdin.end('{"action":"stop"}\n'); continue }
            this.connection = { endpoint: endpoint.origin, credential: value.credential, workspaceId: value.workspace_id, tenantId: value.tenant_id, version: value.engine_version }
            this.set({ state: 'running', stage: 'ready', message: 'Your local workspace is ready.' })
            void this.inspect().catch(() => {})
          } else if (value.event === 'error' && typeof value.code === 'string' && value.code.length <= 64 && typeof value.message === 'string' && value.message.length <= 1000) {
            // The error can arrive before Python has closed its process/pipes.
            // Keep repairs and Resume disabled until the host actually exits.
            this.set({ state: 'stopping', errorCode: value.code, message: value.message, diagnostic: localDiagnostic(value.diagnostic) })
          } else if (value.event !== 'stopped') {
            invalid()
          }
        } catch { invalid() }
      }
    })
    child.stdin.on('error', () => { /* Process closure is handled once below. */ })
    const reportDesktop = () => {
      if (this.child !== child || child.stdin.destroyed || child.stdin.writableEnded) return
      try {
        const bytes = this.options.desktopMemory?.() ?? 0
        if (Number.isSafeInteger(bytes) && bytes >= 0) child.stdin.write(JSON.stringify({ action: 'desktop_usage', resident_bytes: bytes }) + '\n')
      } catch { /* A missing desktop sample cannot interrupt canonical storage. */ }
    }
    const memoryTimer = setInterval(reportDesktop, 2000)
    memoryTimer.unref()
    child.stderr.resume() // Raw Python/provider diagnostics can include private local paths.
    child.on('error', () => {
      this.set({ state: 'stopping', errorCode: 'engine_start', message: 'The local runtime could not start. Reinstall the complete app; your saved data will remain in its separate folder.' })
    })
    child.on('close', (code, signal) => {
      clearInterval(memoryTimer)
      if (this.child !== child) return
      this.child = undefined
      this.connection = undefined
      this.shutdownFailed = code !== 0 || !!this.statusValue.errorCode
      if (this.intentionalStop && !this.shutdownFailed) this.set({ state: 'stopped', stage: undefined, message: 'Local workspace paused. Your memories remain on this computer.', errorCode: undefined, diagnostic: undefined })
      else {
        const diagnostic = processExitDiagnostic(code, signal ?? null, this.statusValue.diagnostic)
        if (this.statusValue.errorCode) this.set({ state: 'error', diagnostic })
        else if (this.statusValue.state !== 'error') this.set({ state: 'error', errorCode: 'engine_stopped', diagnostic, message: code === 0 ? 'The local workspace stopped. Start it again to reconnect.' : 'The local workspace stopped unexpectedly. Retry to resume it; saved data has been retained.' })
      }
      this.set({ memory: undefined })
      if (this.cancelledUpdateStop && this.updateResumeRequested) {
        // Let the stop promise finish before reopening after a slow shutdown.
        setImmediate(() => {
          if (!this.disposed && !this.closing) void this.cancelUpdateStop().catch(() => {
            this.set({ state: 'stopped', message: 'The update was cancelled. Resume your local workspace when ready.' })
          })
        })
      }
      if (!this.disposed) void this.inspect().catch(() => {})
    })
    if (options) child.stdin.write(JSON.stringify(options) + '\n')
    reportDesktop()
    return this.status
  }

  async changeMemory(input: unknown): Promise<LocalStatus> {
    this.assertOpen()
    if (this.configurationChange) throw new Error('The local address is being saved. Wait for it to finish.')
    if (this.memoryChange) throw new Error('The RAM budget is already being saved. Wait for it to finish.')
    const change = memoryOptions(input, true)
    this.memoryChange = this.saveMemory(change)
    try { return await this.memoryChange } finally { this.memoryChange = undefined }
  }

  private async saveMemory(change: MemoryWrite): Promise<LocalStatus> {
    const info = await this.inspect()
    this.assertOpen()
    if (!info.configured) throw new Error('Create a local workspace first.')
    const policy = await new Promise<MemoryPolicy>((resolve, reject) => {
      const child = this.control('repair_token' in change ? 'memory-repair' : 'memory')
      let body = '', failed = false
      const timer = setTimeout(() => { failed = true; child.kill(); reject(new Error('The RAM policy could not be saved in time. Refresh its status before retrying.')) }, 20_000)
      child.stdout.on('data', (chunk: Buffer) => {
        body += chunk.toString('utf8')
        if (body.length > 16384) { failed = true; child.kill(); reject(new Error('The local runtime returned an invalid RAM policy.')) }
      })
      child.stderr.resume()
      child.stdin.on('error', () => {})
      child.on('error', () => { failed = true; reject(new Error('The local operator could not start.')) })
      child.on('close', code => {
        clearTimeout(timer)
        if (failed) return
        try {
          const value = JSON.parse(body)
          if (code !== 0 || value.event !== 'memory_policy') throw new Error(value.event === 'error' && typeof value.message === 'string' ? value.message : 'The RAM policy could not be saved.')
          memoryOptions(value.policy?.settings)
          if (typeof value.policy?.revision !== 'string') throw new Error('The RAM policy could not be verified.')
          resolve(value.policy)
        } catch (error) { reject(error instanceof Error ? error : new Error('The RAM policy could not be saved.')) }
      })
      child.stdin.end(JSON.stringify(change) + '\n')
    })
    this.info = { ...info, memory_policy: policy, memory_recovery: null }
    if (this.statusValue.state === 'error' && this.statusValue.errorCode?.startsWith('memory_policy_')) {
      this.set({ state: 'stopped', errorCode: undefined, stage: undefined, message: 'RAM budget repaired. Resume your local workspace when ready.' })
    } else this.changed(this.status)
    return this.status
  }

  async changePort(input: unknown): Promise<LocalStatus> {
    this.assertOpen()
    if (!this.status.available) throw new Error('The complete local runtime is missing. Reinstall Mnemion Studio.')
    if (this.child || this.busy) throw new Error('Pause the local workspace and wait for other changes to finish before changing its address.')
    const change = portOptions(input)
    this.configurationChange = this.savePort(change)
    try { return await this.configurationChange } finally { this.configurationChange = undefined }
  }

  private async savePort(change: PortChange): Promise<LocalStatus> {
    await this.readInfo('port', change)
    if (this.statusValue.state !== 'error' || this.statusValue.errorCode === 'port_in_use') {
      this.set({ state: 'stopped', errorCode: undefined, stage: undefined, message: 'Local address saved. Resume your workspace when ready.' })
    }
    return this.status
  }

  async changeRemote(input: unknown): Promise<LocalStatus> {
    this.assertOpen()
    if (!this.status.available) throw new Error('The complete local runtime is missing. Reinstall Mnemion Studio.')
    if (this.busy) throw new Error('Wait for the current local operation before changing remote access.')
    const change = remoteOptions(input)
    this.configurationChange = this.saveHostConfiguration('remote', change)
    try { return await this.configurationChange } finally { this.configurationChange = undefined }
  }

  async checkRemote(input: unknown): Promise<LocalStatus> {
    this.assertOpen()
    if (!this.child || this.statusValue.state !== 'running' || this.busy) throw new Error('Wait for the local host to be running before checking remote access.')
    if (!input || typeof input !== 'object' || Array.isArray(input) || Object.keys(input).sort().join(',') !== 'expected_revision,workspace_id') throw new Error('Choose the current remote access settings.')
    const change = input as RemoteCheck
    if (change.workspace_id !== this.info?.settings?.workspace_id || change.expected_revision !== this.info?.remote_access?.revision) throw new Error('Remote settings changed. Refresh before checking them.')
    await this.readInfo('remote-check', change)
    return this.status
  }

  async changeCompany(input: unknown): Promise<LocalStatus> {
    this.assertOpen()
    if (this.operation) { await this.operation; this.assertOpen() }
    if (!this.status.available) throw new Error('The complete local runtime is missing. Reinstall Mnemion Studio.')
    if (this.busy) throw new Error('Wait for the current local operation before changing company access.')
    const change = companyOptions(input)
    this.configurationChange = this.saveHostConfiguration('company', change)
    try { return await this.configurationChange } finally { this.configurationChange = undefined }
  }

  async discoverCompany(input: unknown): Promise<CompanyDiscoveryResult> {
    this.assertOpen()
    if (this.operation) { await this.operation; this.assertOpen() }
    if (!this.status.available || this.busy) throw new Error('Wait for the current local operation before checking the company provider.')
    const request = companyDiscoveryOptions(input)
    return new Promise((resolve, reject) => {
      const child = this.control('company-discover')
      child.stdin.end(JSON.stringify(request) + '\n')
      let body = '', failed = false
      const timer = setTimeout(() => { failed = true; child.kill(); reject(new Error('Company provider discovery timed out. Check its address and connection.')) }, 20_000)
      child.stdout.on('data', (chunk: Buffer) => {
        body += chunk.toString('utf8')
        if (body.length > 16 * 1024) { failed = true; child.kill(); reject(new Error('The local runtime returned an invalid provider response.')) }
      })
      child.stderr.resume()
      child.on('error', () => { failed = true; reject(new Error('The local runtime could not check the provider.')) })
      child.on('close', code => {
        clearTimeout(timer)
        if (failed) return
        try {
          const value = JSON.parse(body)
          if (code !== 0 || value.event !== 'company_discovery' || value.engine_version !== this.options.version) throw new Error(value.event === 'error' && typeof value.message === 'string' && value.message.length <= 1000 ? value.message : 'The local runtime could not check the provider.')
          resolve(companyDiscoveryResult(value.discovery, request))
        } catch (error) { reject(error instanceof Error ? error : new Error('Invalid company provider response.')) }
      })
    })
  }

  async changeVault(input: unknown): Promise<LocalStatus> {
    this.assertOpen()
    if (this.operation) { await this.operation; this.assertOpen() }
    if (!this.status.available || this.busy) throw new Error('Wait for the current local operation before changing vault settings.')
    const change = vaultOptions(input)
    this.configurationChange = this.saveHostConfiguration('vault', change)
    try { return await this.configurationChange } finally { this.configurationChange = undefined }
  }

  async revealVaultKey(input: unknown): Promise<VaultKey> {
    this.assertOpen()
    if (this.operation) { await this.operation; this.assertOpen() }
    if (!this.status.available || this.busy) throw new Error('Wait for the current local operation before reading its recovery key.')
    const request = vaultRequest(input)
    return new Promise((resolve, reject) => {
      const child = this.control('vault-key')
      child.stdin.end(JSON.stringify(request) + '\n')
      let body = '', failed = false
      const timer = setTimeout(() => { failed = true; child.kill(); reject(new Error('The vault key request timed out. Refresh before retrying.')) }, 10_000)
      child.stdout.on('data', (chunk: Buffer) => {
        body += chunk.toString('utf8')
        if (body.length > 4096) { failed = true; child.kill(); reject(new Error('Invalid private vault key response.')) }
      })
      child.stderr.resume()
      child.on('error', () => { failed = true; reject(new Error('The local runtime could not read the vault key.')) })
      child.on('close', code => {
        clearTimeout(timer)
        if (failed) return
        try {
          const value = JSON.parse(body)
          if (code !== 0 || value.event !== 'vault_key' || value.engine_version !== this.options.version) throw new Error('The vault key could not be read. Refresh the current workspace settings.')
          resolve(vaultKeyResult(value.key, request))
        } catch { reject(new Error('The vault key response could not be verified.')) }
        finally { body = '' }
      })
    })
  }

  async changeJournal(input: unknown): Promise<LocalStatus> {
    this.assertOpen()
    if (this.operation) { await this.operation; this.assertOpen() }
    if (!this.status.available || this.busy) throw new Error('Wait for the current local operation before changing journal registrations.')
    const change = journalOptions(input)
    this.configurationChange = this.saveHostConfiguration('journal', change)
    try { return await this.configurationChange } finally { this.configurationChange = undefined }
  }

  async changeModels(input: unknown): Promise<LocalStatus> {
    this.assertOpen()
    if (this.operation) { await this.operation; this.assertOpen() }
    if (!this.status.available || this.busy) throw new Error('Wait for the current local operation before changing model settings.')
    const change = modelsOptions(input)
    this.configurationChange = this.saveHostConfiguration('models', change)
    try { return await this.configurationChange } finally { this.configurationChange = undefined }
  }

  private async saveHostConfiguration(action: 'remote' | 'company' | 'vault' | 'journal' | 'models', change: RemoteChange | CompanyChange | VaultChange | JournalChange | ModelsChange): Promise<LocalStatus> {
    const before = await this.readInfo('status')
    const section = ({ remote: 'remote_access', company: 'company_access', vault: 'vault_access', journal: 'journal_access', models: 'model_access' } as const)[action]
    if (before.settings?.workspace_id !== change.workspace_id || before[section]?.revision !== change.expected_revision ||
        (action === 'company' && before.remote_access?.revision !== (change as CompanyChange).expected_remote_revision)) {
      throw new Error('Host settings changed. Refresh before saving them again.')
    }
    const resume = !!this.child
    // Own the entire drain/write/reopen operation. External stop/close waits
    // for it and prevents the reopen; it cannot race the private state write.
    if (resume && !await this.stopChild()) throw new Error('The local workspace is still stopping. Refresh before retrying.')
    try {
      const updated = await this.readInfo(action, change)
      this.set({ state: 'stopped', stage: undefined, errorCode: undefined, message: action === 'remote' ? 'Remote settings saved.' : action === 'company' ? 'Company settings saved.' : action === 'journal' ? 'Journal destination saved.' : action === 'models' ? 'Model settings saved.' : 'Vault settings saved.' })
      if (resume && !this.stopping && !this.closing && !this.disposed) return this.launch(updated)
      return this.status
    } catch (error) {
      if (resume && !this.child && !this.stopping && !this.closing && !this.disposed && !this.controls.size) {
        try { this.launch(await this.readInfo('status')) } catch { /* Saved settings remain available for an explicit resume. */ }
      }
      throw error
    }
  }

  privateConnection(): Connection {
    if (!this.connection || this.statusValue.state !== 'running') throw new Error('Wait for the local workspace checks to finish before opening it.')
    return { ...this.connection }
  }

  /** Never consume a saved refresh token while its own managed host is booting. */
  async prepareSavedConnection(endpoint: string, tenantId: string, startWithApp: boolean): Promise<void> {
    const url = new URL(endpoint)
    if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || url.pathname !== '/' || !this.status.available) return
    const info = await this.inspect()
    if (!info.configured || info.settings?.port !== Number(url.port)) return
    if (this.status.state !== 'running') {
      if (!startWithApp) throw new Error('This local workspace is paused. Resume it in Setup before reopening your login.')
      await this.start()
    }
    const deadline = performance.now() + 180000
    while (this.status.state !== 'running') {
      this.assertOpen()
      if (this.status.state !== 'starting') throw new Error(this.status.message)
      if (performance.now() >= deadline) throw new Error('The local workspace is still starting. Reopen the saved login when Setup reports it is ready.')
      await new Promise(resolve => setTimeout(resolve, 100))
    }
    const ready = this.privateConnection()
    if (ready.endpoint !== endpoint || ready.tenantId !== tenantId) {
      throw new Error('The saved login belongs to another workspace. Choose its original address or sign in to the current workspace.')
    }
  }

  async stopForUpdate(): Promise<boolean> {
    const resume = this.updateResumeRequested || !!this.child
    const stopping = this.stop()
    this.updateResumeRequested = resume
    return stopping
  }

  async cancelUpdateStop(): Promise<void> {
    if (!this.updateResumeRequested) return
    if (this.child && this.statusValue.state === 'stopping') {
      this.cancelledUpdateStop = true
      return
    }
    this.updateResumeRequested = false
    this.cancelledUpdateStop = false
    if (!this.child) await this.start()
  }

  async stop(): Promise<boolean> {
    this.updateResumeRequested = false
    this.cancelledUpdateStop = false
    if (this.stopping) return this.stopping
    this.stopping = this.finishStop()
    try { return await this.stopping } finally { this.stopping = undefined }
  }

  private async finishStop(): Promise<boolean> {
    // A writer must finish before an updater replaces its executable. Starts
    // waiting on inspection recheck the stop/close guard before spawning.
    await Promise.allSettled([this.operation, this.memoryChange, this.configurationChange])
    if (this.backupWork) {
      this.cancelBackup()
      const stopped = await new Promise<boolean>(resolve => {
        const timer = setTimeout(() => resolve(false), 90_000)
        const done = () => { clearTimeout(timer); resolve(true) }
        void this.backupWork!.then(done, done)
      })
      if (!stopped) return false
    }
    if (this.controls.size > 0) {
      this.set({ message: 'Finishing local operations before closing the database…' })
      const drained = await new Promise<boolean>(resolve => {
        const pending = [...this.controls]
        const finish = (complete: boolean) => {
          clearTimeout(timer)
          for (const child of pending) child.removeListener('close', closed)
          resolve(complete)
        }
        const closed = () => { if (pending.every(child => !this.controls.has(child))) finish(true) }
        const timer = setTimeout(() => finish(false), 90_000)
        for (const child of pending) child.once('close', closed)
        closed()
      })
      if (!drained) {
        this.set({ message: 'Local operations are still finishing. Wait a moment and try again.' })
        return false
      }
    }
    return this.stopChild()
  }

  private async stopChild(): Promise<boolean> {
    const child = this.child
    if (!child) return !this.shutdownFailed
    this.intentionalStop = true
    this.set({ state: 'stopping', message: 'Finishing local work and safely closing the database…' })
    return new Promise(resolve => {
      const closed = () => { clearTimeout(timer); resolve(!this.shutdownFailed) }
      const timer = setTimeout(() => {
        child.removeListener('close', closed)
        this.set({ message: 'Local work is still finishing. Wait a moment and try again.' })
        resolve(false)
      }, 90_000)
      child.once('close', closed)
      if (!child.stdin.destroyed && !child.stdin.writableEnded) child.stdin.end('{"action":"stop"}\n')
    })
  }

  async close(): Promise<boolean> {
    if (this.closing) return this.closing
    this.closing = this.stop()
    try {
      const stopped = await this.closing
      if (stopped) this.disposed = true
      return stopped
    } finally { this.closing = undefined }
  }
}
