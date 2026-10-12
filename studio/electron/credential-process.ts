/** Private, bounded pipes to one OS-credential process; never renderer IPC. */
import type { ChildProcessWithoutNullStreams } from 'node:child_process'
import type { Readable, Writable } from 'node:stream'

export interface ProcessStorage {
  available(): Promise<boolean>
  encrypt(value: string): Promise<Buffer>
  decrypt(value: Buffer): Promise<string>
}

const FAILURE = 'The operating system secure store is unavailable. Unlock it and retry.'
const MAX_FRAME = 32768
const MAX_VALUE = 16384

function frames(input: Readable, receive: (value: Record<string, unknown>) => void, failed: () => void): () => void {
  let buffered = Buffer.alloc(0)
  let ended = false
  const fail = () => { if (!ended) { ended = true; buffered = Buffer.alloc(0); failed() } }
  const data = (chunk: Buffer) => {
    if (ended) return
    let offset = 0
    while (offset < chunk.length && !ended) {
      const newline = chunk.indexOf(10, offset)
      const end = newline < 0 ? chunk.length : newline
      if (buffered.length + end - offset > MAX_FRAME) { fail(); return }
      buffered = Buffer.concat([buffered, chunk.subarray(offset, end)])
      offset = end + 1
      if (newline < 0) break
      try {
        const value = JSON.parse(buffered.toString('utf8'))
        buffered = Buffer.alloc(0)
        if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(FAILURE)
        receive(value)
      } catch { fail() }
    }
  }
  input.on('data', data).on('error', fail).on('end', fail).on('close', fail)
  return () => {
    ended = true; buffered = Buffer.alloc(0)
    input.off('data', data).off('error', fail).off('end', fail).off('close', fail)
  }
}

function encoded(value: unknown): Buffer {
  if (typeof value !== 'string' || !value.length || value.length > 21848 || !/^[A-Za-z0-9+/]+={0,2}$/.test(value)) throw new Error(FAILURE)
  const bytes = Buffer.from(value, 'base64')
  if (bytes.length > MAX_VALUE || bytes.toString('base64') !== value) throw new Error(FAILURE)
  return bytes
}

function plaintext(value: unknown): string {
  if (typeof value !== 'string' || Buffer.byteLength(value) > MAX_VALUE) throw new Error(FAILURE)
  return value
}

export class CredentialProcess implements ProcessStorage {
  private child: ChildProcessWithoutNullStreams | undefined
  private pending: { id: number; resolve(value: unknown): void; reject(error: Error): void } | undefined
  private nextId = 0
  private stopped = false
  private unlisten: (() => void) | undefined
  private observedMemory = 0

  constructor(private readonly launch: () => ChildProcessWithoutNullStreams) {}

  // Reserve a conservative startup footprint until the helper reports metrics.
  get memoryBytes(): number { return this.child ? Math.max(96 * 1024 * 1024, this.observedMemory) : 0 }

  private terminate(): void {
    const child = this.child
    this.child = undefined
    this.unlisten?.(); this.unlisten = undefined
    this.pending?.reject(new Error(FAILURE)); this.pending = undefined
    this.observedMemory = 0
    if (child) {
      // Only this disposable process can be stuck inside OS consent. It never
      // owns a workspace, database, update transaction or saved-connection file.
      if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL')
      child.stdin.destroy(); child.stdout.destroy(); child.stderr.destroy()
    }
  }

  /** Called at final will-quit, after cancellable database/update drains. */
  close(): void { this.stopped = true; this.terminate() }

  private start(): void {
    if (this.child) return
    const child = this.launch()
    this.child = child
    const failed = () => { if (this.child === child) this.terminate() }
    child.on('error', failed).on('exit', failed)
    child.stdin.on('error', failed)
    // Discard native diagnostics rather than retaining paths/provider errors.
    child.stderr.on('error', failed).resume()
    this.unlisten = frames(child.stdout, message => {
      if (message.type === 'metrics') {
        const memory = message.memoryBytes
        if (Object.keys(message).sort().join(',') !== 'memoryBytes,type' ||
            !Number.isSafeInteger(memory) || (memory as number) < 0 || (memory as number) > 16 * 1024 ** 3) throw new Error(FAILURE)
        this.observedMemory = memory as number
        return
      }
      if (message.type !== 'result' || !this.pending || message.id !== this.pending.id || typeof message.ok !== 'boolean' ||
          Object.keys(message).some(key => !['type', 'id', 'ok', 'value'].includes(key))) throw new Error(FAILURE)
      const pending = this.pending
      this.pending = undefined
      if (message.ok) pending.resolve(message.value)
      else pending.reject(new Error(FAILURE))
    }, failed)
  }

  private request(operation: 'available' | 'encrypt' | 'decrypt', value?: string): Promise<unknown> {
    if (this.stopped || this.pending) return Promise.reject(new Error(FAILURE))
    try { this.start() } catch { this.terminate(); return Promise.reject(new Error(FAILURE)) }
    const id = ++this.nextId
    const frame = JSON.stringify({ id, operation, ...(value === undefined ? {} : { value }) }) + '\n'
    if (Buffer.byteLength(frame) > MAX_FRAME) return Promise.reject(new Error(FAILURE))
    return new Promise((resolve, reject) => {
      this.pending = { id, resolve, reject }
      const child = this.child!
      child.stdin.write(frame, error => { if (error && this.child === child) this.terminate() })
    })
  }

  async available(): Promise<boolean> {
    const available = await this.request('available') === true
    // Some native providers cache a denied/locked result for their lifetime.
    // A later explicit retry must be able to consult the unlocked OS afresh.
    if (!available) this.terminate()
    return available
  }
  async encrypt(value: string): Promise<Buffer> { return encoded(await this.request('encrypt', plaintext(value))) }
  async decrypt(value: Buffer): Promise<string> {
    if (!Buffer.isBuffer(value) || !value.length || value.length > MAX_VALUE) throw new Error(FAILURE)
    return plaintext(await this.request('decrypt', value.toString('base64')))
  }
}

/** Fixed helper protocol, shared with subprocess tests; no filesystem access. */
export function serveCredentialRequests(storage: ProcessStorage, input: Readable, output: Writable, memory: () => number, abort: () => void): void {
  let working = false
  let ended = false
  let blocked = false
  const stop = () => { if (!ended) { ended = true; clearInterval(timer); abort() } }
  const send = (value: Record<string, unknown>) => {
    if (ended) return
    const frame = JSON.stringify(value) + '\n'
    if (Buffer.byteLength(frame) > MAX_FRAME || blocked) { stop(); return }
    blocked = !output.write(frame)
  }
  const metrics = () => send({ type: 'metrics', memoryBytes: memory() })
  const timer = setInterval(metrics, 5000)
  timer.unref()
  output.on('error', stop).on('drain', () => { blocked = false })
  frames(input, request => {
    const { id, operation, value } = request
    if (working || !Number.isSafeInteger(id) || (id as number) < 1 ||
        !['available', 'encrypt', 'decrypt'].includes(operation as string) ||
        Object.keys(request).sort().join(',') !== (operation === 'available' ? 'id,operation' : 'id,operation,value')) throw new Error(FAILURE)
    working = true
    void (async () => {
      try {
        let result: boolean | string
        if (operation === 'available') result = await storage.available() === true
        else if (operation === 'encrypt') {
          const encrypted = await storage.encrypt(plaintext(value))
          if (!Buffer.isBuffer(encrypted) || !encrypted.length || encrypted.length > MAX_VALUE) throw new Error(FAILURE)
          result = encrypted.toString('base64')
        } else result = plaintext(await storage.decrypt(encoded(value)))
        send({ type: 'result', id, ok: true, value: result })
      } catch { send({ type: 'result', id, ok: false }) }
      finally { working = false }
    })()
  }, stop)
  metrics()
}
