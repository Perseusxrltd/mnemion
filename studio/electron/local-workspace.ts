import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { existsSync } from 'node:fs'
import { StringDecoder } from 'node:string_decoder'
import type { LocalOptions, LocalInfo, LocalStatus, MemoryChange, MemorySnapshot, MemoryPolicy } from '../shared/local-workspace.js'
type Connection = { endpoint: string; credential: string; workspaceId: string; version: string }
type Options = { executable: string; database: string; root: string; version: string; environment: NodeJS.ProcessEnv; desktopMemory?: () => number }

export function memoryOptions(input: unknown, revision = false): MemoryChange {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Choose automatic memory management or a RAM budget of at least 256 MiB.')
  const value = input as MemoryChange
  const allowed = revision ? ['mode', 'limit_mib', 'expected_revision'] : ['mode', 'limit_mib']
  if (Object.keys(value).some(key => !allowed.includes(key)) ||
      (value.mode !== 'auto' && value.mode !== 'manual') ||
      (value.mode === 'auto' ? value.limit_mib !== null : (!Number.isInteger(value.limit_mib) || value.limit_mib < 256 || value.limit_mib > 1048576)) ||
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

export class LocalWorkspace {
  private child?: ChildProcessWithoutNullStreams
  private connection?: Connection
  private info?: LocalInfo
  private operation?: Promise<LocalInfo>
  private memoryChange?: Promise<LocalStatus>
  private stopping?: Promise<boolean>
  private closing?: Promise<boolean>
  private controls = new Set<ChildProcessWithoutNullStreams>()
  private intentionalStop = false
  private statusValue: LocalStatus
  private disposed = false

  constructor(private options: Options, private changed: (status: LocalStatus) => void) {
    this.statusValue = { available: existsSync(options.executable) && existsSync(options.database), state: 'new',
      message: 'Create a private memory workspace on this computer.' }
  }

  get status(): LocalStatus { return { ...this.statusValue, info: this.info } }
  get active(): boolean { return !!this.child || this.controls.size > 0 || !!this.operation || !!this.memoryChange }
  get busy(): boolean { return !!this.operation || !!this.memoryChange || this.controls.size > 0 || !!this.stopping || !!this.closing || ['starting', 'stopping'].includes(this.statusValue.state) }

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

  async inspect(): Promise<LocalInfo> {
    this.assertOpen()
    if (!this.status.available) throw new Error('The complete local runtime is missing. Reinstall Mnemion Studio to create a workspace on this computer.')
    if (this.operation) return this.operation
    this.operation = new Promise((resolve, reject) => {
      const child = this.control('status')
      child.stdin.end()
      let body = ''
      let failed = false
      const timer = setTimeout(() => { failed = true; child.kill(); reject(new Error('The local runtime check timed out. Try again.')) }, 20_000)
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
          if (code !== 0 || value.event !== 'status') throw new Error(value.event === 'error' ? value.message : 'The local runtime could not read its settings.')
          if (value.engine_version !== this.options.version || typeof value.configured !== 'boolean' || value.data_directory !== this.options.root ||
              !value.resources || typeof value.resources.memory_bytes !== 'number' || typeof value.resources.available_disk_bytes !== 'number') {
            throw new Error('The local runtime does not match this app. Reinstall the complete app.')
          }
          const { configured, data_directory, engine_version, resources, settings, last_verification, memory_policy, memory } = value
          const info = { configured, data_directory, engine_version, resources, settings, last_verification, memory_policy, memory }
          this.info = info
          this.changed(this.status)
          resolve(info)
        } catch (error) { reject(error instanceof Error ? error : new Error('The local runtime returned an invalid status.')) }
      })
    })
    try { return await this.operation } finally { this.operation = undefined }
  }

  async start(input?: unknown): Promise<LocalStatus> {
    this.assertOpen()
    if (this.child) return this.status
    const options = input === undefined ? undefined : localOptions(input)
    const info = await this.inspect()
    this.assertOpen()
    if (this.child) return this.status
    if (!options && !info.configured) throw new Error('Choose the workspace settings before starting.')
    this.intentionalStop = false
    this.connection = undefined
    this.set({ state: 'starting', stage: 'starting', message: info.configured ? 'Opening your local workspace…' : 'Creating your local workspace…', errorCode: undefined })
    const child = spawn(this.options.executable, this.command(options ? 'initialize' : 'run'), {
      env: this.options.environment, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
    })
    this.child = child
    const decoder = new StringDecoder('utf8')
    let pending = ''
    const invalid = () => {
      this.set({ state: 'error', errorCode: 'invalid_runtime_response', message: 'The local runtime returned an invalid response. Your saved data has been retained.' })
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
            if (memory.revision !== this.info?.memory_policy?.revision) void this.inspect().catch(() => {})
          } else if (value.event === 'progress' && typeof value.stage === 'string' && value.stage.length <= 64 && typeof value.message === 'string' && value.message.length <= 1000) {
            this.set({ stage: value.stage, message: value.message })
          } else if (value.event === 'ready') {
            const endpoint = new URL(value.endpoint)
            if (endpoint.protocol !== 'http:' || endpoint.hostname !== '127.0.0.1' || !endpoint.port || endpoint.pathname !== '/' || endpoint.username || endpoint.password || endpoint.search || endpoint.hash ||
                typeof value.credential !== 'string' || !/^mnm_[A-Za-z0-9_-]{40,100}$/.test(value.credential) ||
                typeof value.workspace_id !== 'string' || !/^[a-f0-9-]{36}$/.test(value.workspace_id) || value.engine_version !== this.options.version) throw new Error('Invalid private connection')
            if (this.intentionalStop) { child.stdin.end('{"action":"stop"}\n'); continue }
            this.connection = { endpoint: endpoint.origin, credential: value.credential, workspaceId: value.workspace_id, version: value.engine_version }
            this.set({ state: 'running', stage: 'ready', message: 'Your local workspace is ready.' })
            void this.inspect().catch(() => {})
          } else if (value.event === 'error' && typeof value.code === 'string' && value.code.length <= 64 && typeof value.message === 'string' && value.message.length <= 1000) {
            this.set({ state: 'error', errorCode: value.code, message: value.message })
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
      this.set({ state: 'error', errorCode: 'engine_start', message: 'The local runtime could not start. Reinstall the complete app; your saved data will remain in its separate folder.' })
    })
    child.on('close', code => {
      clearInterval(memoryTimer)
      if (this.child !== child) return
      this.child = undefined
      this.connection = undefined
      if (this.intentionalStop) this.set({ state: 'stopped', stage: undefined, message: 'Local workspace paused. Your memories remain on this computer.', errorCode: undefined })
      else if (this.statusValue.state !== 'error') this.set({ state: 'error', errorCode: 'engine_stopped', message: code === 0 ? 'The local workspace stopped. Start it again to reconnect.' : 'The local workspace stopped unexpectedly. Retry to resume it; saved data has been retained.' })
      this.set({ memory: undefined })
      if (!this.disposed) void this.inspect().catch(() => {})
    })
    if (options) child.stdin.write(JSON.stringify(options) + '\n')
    reportDesktop()
    return this.status
  }

  async changeMemory(input: unknown): Promise<LocalStatus> {
    this.assertOpen()
    if (this.memoryChange) throw new Error('The RAM budget is already being saved. Wait for it to finish.')
    const change = memoryOptions(input, true)
    this.memoryChange = this.saveMemory(change)
    try { return await this.memoryChange } finally { this.memoryChange = undefined }
  }

  private async saveMemory(change: MemoryChange): Promise<LocalStatus> {
    const info = await this.inspect()
    this.assertOpen()
    if (!info.configured) throw new Error('Create a local workspace first.')
    const policy = await new Promise<MemoryPolicy>((resolve, reject) => {
      const child = this.control('memory')
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
    this.info = { ...info, memory_policy: policy }
    this.changed(this.status)
    return this.status
  }

  privateConnection(): Connection {
    if (!this.connection || this.statusValue.state !== 'running') throw new Error('Wait for the local workspace checks to finish before opening it.')
    return { ...this.connection }
  }

  async stop(): Promise<boolean> {
    if (this.stopping) return this.stopping
    this.stopping = this.finishStop()
    try { return await this.stopping } finally { this.stopping = undefined }
  }

  private async finishStop(): Promise<boolean> {
    // A writer must finish before an updater replaces its executable. Starts
    // waiting on inspection recheck the stop/close guard before spawning.
    await Promise.allSettled([this.operation, this.memoryChange])
    if (this.controls.size > 0) return false
    const child = this.child
    if (!child) return true
    this.intentionalStop = true
    this.set({ state: 'stopping', message: 'Finishing local work and safely closing the database…' })
    return new Promise(resolve => {
      const closed = () => { clearTimeout(timer); resolve(true) }
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
