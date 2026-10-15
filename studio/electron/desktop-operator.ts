/** Same-account native control. No TCP listener, browser route, or memory credential. */
import { createServer, type Server, type Socket } from 'node:net'
import { chmod, mkdtemp, realpath, rm, unlink } from 'node:fs/promises'
import { basename, isAbsolute, join } from 'node:path'
import { createHash, randomBytes, randomUUID, timingSafeEqual } from 'node:crypto'
import { readBackupDocument } from './local-backups.js'

const MAX_REQUEST = 16 * 1024, MAX_RESPONSE = 256 * 1024
const UUID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/
export type DesktopRequest = {
  request_id: string; action: string; expected_workspace_id?: string | null; input: Record<string, unknown>
}
type Endpoint = { format: 1; session_id: string; version: string; pid: number; address: string; credential: string }
type Reply = { protocol: 1; session_id: string; request_id: string; ok: boolean; result?: unknown; error?: string; message?: string }
type Options = {
  directory: string; version: string;
  publish: (value: { directory: string; endpoint: Endpoint }) => Promise<void>;
  execute: (request: DesktopRequest, signal: AbortSignal) => Promise<unknown>;
}
type Cached = { hash: string; at: number; bytes: Buffer }

function privateMessage(error: unknown, input: unknown, credential: string): string {
  let result = error instanceof Error && error.message.length <= 32768 ? error.message : 'The desktop operation could not finish. Refresh status before retrying.'
  const values = [credential]
  function visit(value: unknown, depth: number): void {
    if (depth > 5 || !value || typeof value !== 'object') return
    for (const [key, child] of Object.entries(value)) {
      if (/key|token|secret|password|credential/i.test(key) && typeof child === 'string' && child.length > 3) values.push(child)
      else if (typeof child === 'object') visit(child, depth + 1)
    }
  }
  visit(input, 0)
  for (const value of values) result = result.split(value).join('[private]')
  return result.replace(/mnm_bk_[A-Za-z0-9_-]+/g, '[private]').replace(/postgres(?:ql)?:\/\/\S+/gi, '[private database]').replace(/[\x00-\x1f\x7f]/g, ' ').slice(0, 1000)
}

export class DesktopOperator {
  private server?: Server
  private folder?: string
  private endpoint?: Endpoint
  private sockets = new Set<Socket>()
  private controllers = new Set<AbortController>()
  private pending = new Set<string>()
  private cache = new Map<string, Cached>()
  private cachedBytes = 0
  private closing = false
  constructor(private options: Options) {}
  get active(): boolean { return this.controllers.size > 0 }
  get ready(): boolean { return !!this.endpoint && !this.closing }
  cancel(): void { for (const controller of this.controllers) controller.abort() }

  async start(): Promise<void> {
    if (this.server || this.closing) throw new Error('Desktop control is already starting or closing.')
    if (!isAbsolute(this.options.directory) || basename(this.options.directory) !== 'mnemion-desktop-control') throw new Error('Use the private desktop control directory.')
    const session_id = randomUUID()
    let address: string
    if (process.platform === 'win32') address = `\\\\.\\pipe\\mnemion-operator-${session_id}-${randomBytes(16).toString('hex')}`
    else {
      // A short private directory avoids Unix socket limits with long profile paths.
      this.folder = await mkdtemp(join(await realpath('/tmp'), 'mnemion-operator-'))
      await chmod(this.folder, 0o700)
      address = join(this.folder, 'control.sock')
    }
    const endpoint: Endpoint = { format: 1, session_id, version: this.options.version, pid: process.pid,
      address, credential: randomBytes(32).toString('hex') }
    this.server = createServer(socket => this.accept(socket, endpoint))
    this.server.maxConnections = 16
    try {
      await new Promise<void>((resolve, reject) => {
        this.server!.once('error', reject)
        this.server!.listen(address, () => { this.server!.off('error', reject); resolve() })
      })
      this.server.on('error', () => { void this.close() })
      if (process.platform !== 'win32') await chmod(address, 0o600)
      await this.options.publish({ directory: this.options.directory, endpoint })
      this.endpoint = endpoint
    } catch (error) { await this.close(); throw error }
  }

  private accept(socket: Socket, endpoint: Endpoint): void {
    if (this.closing || this.sockets.size >= 16) { socket.destroy(); return }
    this.sockets.add(socket)
    let bytes = Buffer.alloc(0), received = false
    const controller = new AbortController()
    const handshake = setTimeout(() => socket.destroy(), 5000)
    handshake.unref()
    socket.setTimeout(5000, () => socket.destroy())
    socket.on('error', () => {})
    socket.once('close', () => { clearTimeout(handshake); controller.abort(); this.sockets.delete(socket) })
    socket.on('data', chunk => {
      if (received || bytes.length + chunk.length > MAX_REQUEST + 4) { socket.destroy(); return }
      bytes = Buffer.concat([bytes, chunk])
      if (bytes.length < 4) return
      const length = bytes.readUInt32BE(0)
      if (!length || length > MAX_REQUEST || bytes.length > length + 4) { socket.destroy(); return }
      if (bytes.length !== length + 4) return
      received = true
      clearTimeout(handshake)
      socket.setTimeout(0)
      const body = bytes.subarray(4)
      void this.process(socket, endpoint, body, controller).catch(() => socket.destroy())
      bytes = Buffer.alloc(0)
    })
  }

  private async process(socket: Socket, endpoint: Endpoint, bytes: Buffer, controller: AbortController): Promise<void> {
    let input: any
    try { input = JSON.parse(bytes.toString('utf8')) } catch { socket.destroy(); return }
    if (!input || typeof input !== 'object' || Array.isArray(input) || input.protocol !== 1 ||
        input.session_id !== endpoint.session_id || typeof input.credential !== 'string' ||
        !/^[a-f0-9]{64}$/.test(input.credential) ||
        !timingSafeEqual(Buffer.from(input.credential, 'hex'), Buffer.from(endpoint.credential, 'hex'))) { socket.destroy(); return }
    if (Object.keys(input).some(key => !['protocol', 'session_id', 'credential', 'request_id', 'action', 'expected_workspace_id', 'input'].includes(key)) ||
        typeof input.request_id !== 'string' || !UUID.test(input.request_id) || typeof input.action !== 'string' ||
        !/^[a-z][a-z.-]{0,63}$/.test(input.action) || !input.input || typeof input.input !== 'object' || Array.isArray(input.input) ||
        (input.expected_workspace_id !== undefined && input.expected_workspace_id !== null &&
          (typeof input.expected_workspace_id !== 'string' || !UUID.test(input.expected_workspace_id)))) { socket.destroy(); return }
    const request: DesktopRequest = { request_id: input.request_id, action: input.action, input: input.input,
      ...('expected_workspace_id' in input ? { expected_workspace_id: input.expected_workspace_id } : {}) }
    const reply = (value: Omit<Reply, 'protocol' | 'session_id' | 'request_id'>): Reply => ({ protocol: 1,
      session_id: endpoint.session_id, request_id: request.request_id, ...value })
    this.expire()
    const hash = createHash('sha256').update(JSON.stringify(request)).digest('hex'), cached = this.cache.get(request.request_id)
    if (cached) {
      this.send(socket, cached.hash === hash ? cached.bytes : this.encode(reply({ ok: false, error: 'request_changed', message: 'This request ID was already used for different input. Refresh status and use a new ID.' })))
      return
    }
    if (this.pending.has(request.request_id) || this.controllers.size >= 8) {
      this.send(socket, this.encode(reply({ ok: false, error: 'request_in_progress', message: 'An operation is still running. Read status before retrying a change.' })))
      return
    }
    this.pending.add(request.request_id)
    this.controllers.add(controller)
    const timer = setTimeout(() => { controller.abort(); socket.destroy() }, 4 * 60 * 60 * 1000)
    timer.unref()
    let result: Reply
    try {
      controller.signal.throwIfAborted()
      const value = request.action === 'ping' ? { version: this.options.version, pid: process.pid } : await this.options.execute(request, controller.signal)
      result = reply({ ok: true, result: value ?? null })
    } catch (error) {
      result = reply({ ok: false, error: controller.signal.aborted ? 'cancelled' : 'operation_failed',
        message: privateMessage(error, request.input, endpoint.credential) })
    } finally { clearTimeout(timer); this.controllers.delete(controller); this.pending.delete(request.request_id) }
    let encoded: Buffer
    try { encoded = this.encode(result) } catch {
      encoded = this.encode(reply({ ok: false, error: 'response_limit', message: 'The result exceeds the desktop control limit. Use a smaller selection or the app.' }))
    }
    this.cache.set(request.request_id, { hash, at: Date.now(), bytes: encoded })
    this.cachedBytes += encoded.length
    this.expire()
    this.send(socket, encoded)
  }

  private expire(): void {
    for (const [id, value] of this.cache) {
      if (this.cache.size <= 64 && this.cachedBytes <= 2 * 1024 * 1024 && Date.now() - value.at < 10 * 60_000) break
      this.cache.delete(id); this.cachedBytes -= value.bytes.length
    }
  }
  private encode(value: Reply): Buffer {
    const bytes = Buffer.from(JSON.stringify(value))
    if (bytes.length > MAX_RESPONSE) throw new Error('Desktop response limit')
    const header = Buffer.alloc(4); header.writeUInt32BE(bytes.length)
    return Buffer.concat([header, bytes])
  }
  private send(socket: Socket, bytes: Buffer): void { if (!socket.destroyed) socket.end(bytes) }
  async close(): Promise<void> {
    if (this.closing) return
    this.closing = true
    this.cancel()
    for (const socket of this.sockets) socket.destroy()
    if (this.server?.listening) await new Promise<void>(resolve => this.server!.close(() => resolve()))
    if (this.endpoint) {
      const path = join(this.options.directory, 'endpoint.json')
      try { if ((await readBackupDocument(path))?.session_id === this.endpoint.session_id) await unlink(path) } catch { /* A stale private endpoint grants no access after shutdown. */ }
    }
    if (this.folder) await rm(this.folder, { recursive: true, force: true }).catch(() => {})
    this.endpoint = undefined
    this.cache.clear(); this.cachedBytes = 0
  }
}
