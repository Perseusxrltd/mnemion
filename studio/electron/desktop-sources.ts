/** One bounded source scan at a time, independent of the selected workspace. */
import { randomUUID } from 'node:crypto'
import type { CredentialCipher } from './workspace-store.js'
import type { DesktopSource, DesktopSourceView, SourceActivity, SourceConfigure, SourceControl, SourceReport } from '../shared/desktop-sources.js'

type SavedSource = DesktopSource & { sealed_key: string }
type Document = { format: 1; revision: string; sources: SavedSource[] }
export type SourceCall = (request: Record<string, unknown>, signal?: AbortSignal,
  resources?: (bytes: number) => void) => Promise<Record<string, unknown>>
type Options = { call: SourceCall; cipher: CredentialCipher; changed?: () => void; now?: () => number }
const UUID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/

function publicSource(source: SavedSource): DesktopSource {
  const { sealed_key: _private, ...value } = source
  return value
}

export class DesktopSources {
  private document?: Document
  private loading?: Promise<void>
  private controlling = false
  private controlWork?: Promise<unknown>
  private timer?: ReturnType<typeof setInterval>
  private startRequested = false
  private suspended = false
  private closed = false
  private active?: { id: string; abort: AbortController; work: Promise<void> }
  private pending = new Set<string>()
  private next = new Map<string, number>()
  private activities = new Map<string, SourceActivity>()
  private rss = 0
  constructor(private readonly options: Options) {}
  get busy(): boolean { return this.controlling || !!this.active || !!this.loading }
  get memoryBytes(): number { return this.rss }
  private now(): number { return this.options.now?.() ?? Date.now() }
  private changed() { this.options.changed?.() }

  private async ensure(): Promise<void> {
    if (this.document) return
    if (!this.loading) this.loading = (async () => {
      const result = await this.options.call({ operation: 'load' })
      if (result.format !== 1 || typeof result.revision !== 'string' || !Array.isArray(result.sources) || result.sources.length > 16) throw new Error('Saved source settings could not be read. The existing file has been retained.')
      // The native helper validates every field before returning its private file.
      this.document = result as Document
    })().finally(() => { this.loading = undefined })
    return this.loading
  }

  async status(): Promise<DesktopSourceView> {
    await this.ensure()
    return { revision: this.document!.revision, secure_storage: await this.options.cipher.available(),
      running: !!this.timer && !this.suspended && !this.closed, memory_bytes: this.rss,
      sources: this.document!.sources.map(source => ({ ...publicSource(source), activity: source.enabled ? {
        ...(this.activities.get(source.id) ?? { phase: 'waiting' }),
        ...(this.next.has(source.id) ? { next_scan_at: new Date(this.next.get(source.id)!).toISOString() } : {}),
      } : { phase: 'paused', report: this.activities.get(source.id)?.report } })) }
  }

  async start(): Promise<void> {
    this.startRequested = true
    if (this.closed) return
    await this.ensure()
    if (!this.timer) { this.timer = setInterval(() => { void this.tick() }, 2000); this.timer.unref() }
    void this.tick()
  }

  private async mutate<T>(expected: string, work: () => Promise<T>): Promise<T> {
    await this.ensure()
    if (this.closed || this.suspended || this.controlling) throw new Error('Source controls are busy. Wait for the current operation or app update to finish.')
    if (expected !== this.document!.revision) throw new Error('Source settings changed. Refresh before retrying.')
    this.controlling = true
    const pending = work()
    this.controlWork = pending
    try { return await pending } finally { this.controlWork = undefined; this.controlling = false; this.changed(); void this.tick() }
  }

  private async save(sources: SavedSource[]) {
    try {
      const result = await this.options.call({ operation: 'store', expected_revision: this.document!.revision, sources })
      if (result.format !== 1 || typeof result.revision !== 'string' || !Array.isArray(result.sources)) throw new Error('Source settings could not be confirmed. Refresh before retrying.')
      this.document = result as Document
    } catch (error) {
      // A lost reply may follow a completed write. Reload before any retry;
      // never replay an ambiguous mutation against the previous revision.
      this.document = undefined
      throw error
    }
  }

  async configure(input: SourceConfigure, signal?: AbortSignal): Promise<DesktopSourceView> {
    if (!input || !input.source || Object.keys(input).some(k => !['expected_revision', 'source', 'credential'].includes(k))) throw new Error('Review the source settings and its dedicated application key.')
    await this.mutate(input.expected_revision, async () => {
      signal?.throwIfAborted()
      if (!await this.options.cipher.available()) throw new Error('Unlock OS credential storage before remembering a background source.')
      const id = input.source.id ?? randomUUID()
      if (!UUID.test(id)) throw new Error('Choose a source from current desktop status.')
      const before = this.document!.sources.find(item => item.id === id)
      if (!before && this.document!.sources.length >= 16) throw new Error('This app can host up to 16 sources. Pause or remove an unused source first.')
      if (this.active?.id === id) throw new Error('Pause this source before changing its settings.')
      const source = { ...input.source, id }
      if (before && ['endpoint', 'tenant_id', 'connector_id', 'principal_id', 'provider', 'path'].some(key => source[key as keyof DesktopSource] !== before[key as keyof DesktopSource])) throw new Error('Use a new connection for a different source folder or workspace.')
      if (this.document!.sources.some(item => item.id !== id && item.endpoint === source.endpoint && item.connector_id === source.connector_id)) throw new Error('This connection already runs on this computer.')
      const credential = input.credential ?? (before ? await this.options.cipher.decrypt(Buffer.from(before.sealed_key, 'base64')) : '')
      const verified = await this.options.call({ operation: 'verify', source, credential }, signal) as DesktopSource
      signal?.throwIfAborted()
      const sealed_key = (await this.options.cipher.encrypt(credential)).toString('base64')
      signal?.throwIfAborted()
      await this.save([...this.document!.sources.filter(item => item.id !== id), { ...verified, sealed_key }])
      this.next.set(id, this.now())
    })
    if (this.startRequested && !this.timer) await this.start()
    return this.status()
  }

  async control(action: 'pause' | 'sync' | 'remove', input: SourceControl): Promise<DesktopSourceView> {
    if (!input || !UUID.test(input.id) || Object.keys(input).some(k => !['expected_revision', 'id', 'enabled', 'confirm'].includes(k))) throw new Error('Choose a source from current desktop status.')
    await this.mutate(input.expected_revision, async () => {
      const source = this.document!.sources.find(item => item.id === input.id)
      if (!source) throw new Error('This source is no longer configured on this computer.')
      if (action === 'sync') {
        if (!source.enabled) throw new Error('Resume this source before requesting a scan.')
        this.pending.add(source.id)
        return
      }
      if (action === 'pause' && typeof input.enabled !== 'boolean') throw new Error('Choose whether to run this source.')
      if (action === 'remove' && input.confirm !== true) throw new Error('Confirm removal of this computer’s source settings. Existing memories are retained.')
      const next = action === 'remove' ? this.document!.sources.filter(item => item.id !== input.id) :
        this.document!.sources.map(item => item.id === input.id ? { ...item, enabled: input.enabled! } : item)
      // Persist a pause before stopping work. A failed settings save must not
      // misleadingly claim that a source will stay paused after restart.
      await this.save(next)
      if (action === 'remove' || !input.enabled) {
        this.pending.delete(input.id)
        if (this.active?.id === input.id) { this.active.abort.abort(); await this.active.work }
      } else this.next.set(input.id, this.now())
      if (action === 'remove') { this.activities.delete(input.id); this.next.delete(input.id) }
    })
    return this.status()
  }

  async tick(): Promise<void> {
    if (!this.document || this.busy || this.suspended || this.closed || !this.timer) return
    // Serve older due work first so repeated requests for one connector cannot
    // starve other workspaces' sources on this device.
    const source = this.document.sources.filter(item => item.enabled && (this.pending.has(item.id) || (this.next.get(item.id) ?? 0) <= this.now()))
      .sort((a, b) => (this.next.get(a.id) ?? 0) - (this.next.get(b.id) ?? 0))[0]
    if (!source) return
    this.pending.delete(source.id)
    const abort = new AbortController()
    const activity = { id: source.id, abort, work: Promise.resolve() }
    this.active = activity
    this.activities.set(source.id, { phase: 'scanning', report: this.activities.get(source.id)?.report })
    this.changed()
    activity.work = (async () => {
      try {
        if (!await this.options.cipher.available()) throw new Error('Unlock OS credential storage to resume this source.')
        const credential = await this.options.cipher.decrypt(Buffer.from(source.sealed_key, 'base64'))
        abort.signal.throwIfAborted()
        const report = await this.options.call({ operation: 'scan', source: publicSource(source), credential }, abort.signal,
          bytes => { this.rss = bytes }) as SourceReport
        this.activities.set(source.id, { phase: report.completed ? 'complete' : 'attention', report,
          ...(report.completed ? {} : { message: 'The scan was partial. Earlier good memories are retained; check Source status.' }) })
      } catch (error) {
        this.activities.set(source.id, { phase: 'attention', report: this.activities.get(source.id)?.report,
          message: abort.signal.aborted ? 'The scan stopped. Its next run will reconcile saved progress.' :
            error instanceof Error ? error.message : 'The source could not be scanned. Check its folder, key and connection.' })
      } finally {
        this.next.set(source.id, this.now() + source.poll_seconds * 1000)
        this.rss = 0
        if (this.active === activity) this.active = undefined
        this.changed()
      }
    })()
    await activity.work
  }

  pauseForUpdate(): boolean {
    if (this.busy) return false
    this.suspended = true
    return true
  }
  resumeAfterUpdate(): void { this.suspended = false; void this.tick() }
  async close(): Promise<void> {
    this.closed = true
    if (this.timer) clearInterval(this.timer)
    this.timer = undefined
    this.active?.abort.abort()
    if (this.active) await this.active.work
    if (this.controlWork) await this.controlWork.catch(() => {})
  }
}
