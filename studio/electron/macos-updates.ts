import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'

export type MacUpdateEvent = {
  state: 'checking' | 'downloading' | 'verifying' | 'ready' | 'installing' | 'installed'
    | 'current' | 'cancelled' | 'error'
  version?: string
  percent?: number
}
const states = new Set(['checking', 'downloading', 'verifying', 'ready', 'installing',
  'installed', 'current', 'cancelled', 'error'])

export function parseMacUpdateEvent(line: string): MacUpdateEvent {
  if (Buffer.byteLength(line) > 2048) throw new Error('Oversized native update event')
  const event = JSON.parse(line)
  if (!event || Array.isArray(event) || !states.has(event.state)) throw new Error('Invalid native update event')
  if (event.version !== undefined && (typeof event.version !== 'string'
    || !/^\d{1,8}\.\d{1,8}\.\d{1,8}$/.test(event.version))) throw new Error('Invalid update version')
  if (event.percent !== undefined && (!Number.isInteger(event.percent)
    || event.percent < 0 || event.percent > 100)) throw new Error('Invalid update progress')
  if (event.state === 'ready' && !event.version) throw new Error('Missing update version')
  // Do not forward provider errors, paths, URLs or arbitrary native fields to the renderer.
  return { state: event.state, ...(event.version ? { version: event.version } : {}),
    ...(event.percent !== undefined ? { percent: event.percent } : {}) }
}

/** One native update cycle, controlled over private inherited pipes. */
export class MacUpdateBridge {
  private child?: ChildProcessWithoutNullStreams
  private pending = ''
  private outputBytes = 0
  private ready = false
  private cancelled = false
  private committed = false
  private reported = false
  private resolveCheck?: () => void
  private closed?: Promise<void>
  private resolveClosed?: () => void
  private timer?: NodeJS.Timeout

  constructor(private executable: string, private notify: (event: MacUpdateEvent) => void,
    private launch: typeof spawn = spawn) {}

  get active() { return !!this.child }
  get installing() { return this.committed }

  async check(): Promise<void> {
    if (this.child) return
    this.ready = false
    this.cancelled = false
    this.committed = false
    this.reported = false
    this.pending = ''
    this.outputBytes = 0
    const completed = new Promise<void>(resolve => { this.resolveCheck = resolve })
    this.closed = new Promise<void>(resolve => { this.resolveClosed = resolve })
    // The updater has no need for service credentials, Electron flags or loader overrides.
    const env: NodeJS.ProcessEnv = { PATH: '/usr/bin:/bin:/usr/sbin:/sbin' }
    for (const name of ['HOME', 'TMPDIR', 'LANG', 'LC_ALL', '__CF_USER_TEXT_ENCODING']) {
      if (process.env[name]) env[name] = process.env[name]
    }
    try {
      const child = this.launch(this.executable, [], { stdio: 'pipe', env }) as ChildProcessWithoutNullStreams
      this.child = child
      child.stdout.setEncoding('utf8')
      child.stdout.on('data', (chunk: string) => this.read(chunk))
      child.stderr.resume() // Sparkle diagnostics may contain private filesystem paths.
      child.stdin.on('error', () => this.fail())
      child.on('error', () => this.fail())
      child.on('close', code => {
        if (this.timer) clearTimeout(this.timer)
        this.timer = undefined
        this.child = undefined
        this.ready = false
        if (this.cancelled && !this.reported) this.notify({ state: 'cancelled' })
        else if (code !== 0 && !this.reported) this.notify({ state: 'error' })
        this.resolveCheck?.()
        this.resolveCheck = undefined
        this.resolveClosed?.()
        this.resolveClosed = undefined
      })
      this.timer = setTimeout(() => this.fail(), 20 * 60_000)
      this.timer.unref()
    } catch {
      this.child = undefined
      this.notify({ state: 'error' })
      this.resolveCheck?.()
      this.resolveCheck = undefined
      this.resolveClosed?.()
      this.resolveClosed = undefined
    }
    return completed
  }

  private read(chunk: string) {
    this.outputBytes += Buffer.byteLength(chunk)
    if (this.outputBytes > 128 * 1024) { this.fail(); return }
    this.pending += chunk
    for (;;) {
      const index = this.pending.indexOf('\n')
      if (index === -1) break
      const line = this.pending.slice(0, index)
      this.pending = this.pending.slice(index + 1)
      let event: MacUpdateEvent
      try { event = parseMacUpdateEvent(line) } catch { this.fail(); return }
      if (this.cancelled) continue
      if (event.state === 'ready') {
        this.ready = true
        if (this.timer) clearTimeout(this.timer)
        this.timer = undefined
        this.resolveCheck?.()
        this.resolveCheck = undefined
      }
      if (event.state === 'error') this.reported = true
      this.notify(event)
    }
    if (Buffer.byteLength(this.pending) > 2048) this.fail()
  }

  private fail() {
    if (!this.reported) {
      this.reported = true
      this.notify({ state: 'error' })
    }
    void this.cancel()
  }

  install(): boolean {
    if (!this.child || !this.ready || this.cancelled || this.committed
      || !this.child.stdin.writable) return false
    this.committed = true
    this.child.stdin.write('install\n')
    return true
  }

  async cancel(): Promise<boolean> {
    if (!this.child || this.committed) return true
    if (!this.cancelled) {
      this.cancelled = true
      this.ready = false
      if (this.child.stdin.writable) this.child.stdin.end('cancel\n')
    }
    // Never kill a staged installer and assume that it is cancelled. Normal app
    // quit waits for the native driver to acknowledge cancellation by exiting.
    let timer: NodeJS.Timeout | undefined
    const deadline = new Promise<boolean>(resolve => { timer = setTimeout(() => resolve(false), 15_000) })
    const stopped = this.closed!.then(() => true)
    const result = await Promise.race([deadline, stopped])
    if (timer) clearTimeout(timer)
    return result
  }
}
