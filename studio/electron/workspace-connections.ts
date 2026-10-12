/** Volatile credentials stay in the main process; renderer handles are origin-bound. */
import { randomBytes } from 'node:crypto'
import { WorkspaceStore, workspaceEndpoint, workspaceIdentity, type WorkspaceIdentity, type WorkspaceBookmark } from './workspace-store.js'

export interface WorkspaceSession {
  endpoint: string
  sessionToken: string
  me: WorkspaceIdentity
  remembered: boolean
  bookmarkId?: string
}

type Active = WorkspaceSession & { credential: string }
type VerifyIdentity = (endpoint: string, credential: string) => Promise<WorkspaceIdentity>
const PREFIX = 'mnm_session_'
export const isWorkspaceSession = (header: string): boolean => header.startsWith('Bearer ' + PREFIX)

export class WorkspaceConnections {
  private active: Active | null = null
  private generation = 0
  private queue: Promise<void> = Promise.resolve()
  private resuming: Promise<WorkspaceSession | null> | null = null

  constructor(private readonly store: WorkspaceStore, private readonly verify: VerifyIdentity) {}

  private publicSession(): WorkspaceSession | null {
    if (!this.active) return null
    const { credential: _credential, ...session } = this.active
    return structuredClone(session)
  }

  private serial<T>(operation: () => Promise<T>): Promise<T> {
    const pending = this.queue.then(operation)
    this.queue = pending.then(() => {}, () => {})
    return pending
  }

  async status() {
    await this.queue
    return { secureStorage: await this.store.available(), ...await this.store.status(), active: this.publicSession() }
  }

  async inspect(id: string) {
    await this.queue
    return this.store.inspect(id)
  }

  private async activate(endpoint: string, credential: string, remember: boolean, generation: number, expected?: WorkspaceBookmark): Promise<WorkspaceSession> {
    endpoint = workspaceEndpoint(endpoint)
    if (typeof credential !== 'string' || !/^[A-Za-z0-9_.~+/=-]{16,1024}$/.test(credential)) throw new Error('Enter a valid workspace key.')
    const me = workspaceIdentity(await this.verify(endpoint, credential))
    if (JSON.stringify(me).includes(credential)) throw new Error('The workspace returned an invalid identity.')
    if (expected && (expected.tenantId !== me.tenant_id || expected.principalId !== me.principal_id)) {
      throw new Error('This key now identifies a different workspace or person. Connect again to review its access.')
    }
    return this.serial(async () => {
      if (generation !== this.generation) throw new Error('A newer connection was selected.')
      const bookmark = remember ? await this.store.save(endpoint, credential, me) : undefined
      if (!remember) await this.store.select(null)
      if (generation !== this.generation) throw new Error('A newer connection was selected.')
      this.active = { endpoint, credential, me, remembered: !!bookmark, bookmarkId: bookmark?.id, sessionToken: PREFIX + randomBytes(32).toString('base64url') }
      return this.publicSession()!
    })
  }

  connect(endpoint: string, credential: string, remember: boolean): Promise<WorkspaceSession> {
    return this.activate(endpoint, credential, remember, ++this.generation)
  }

  async restore(id: string): Promise<WorkspaceSession> {
    const generation = ++this.generation
    const { bookmark, credential } = await this.store.credential(id)
    if (generation !== this.generation) throw new Error('A newer connection was selected.')
    return this.activate(bookmark.endpoint, credential, true, generation, bookmark)
  }

  async resume(): Promise<WorkspaceSession | null> {
    if (this.active) return this.publicSession()
    if (this.resuming) return this.resuming
    const generation = this.generation
    const pending = (async () => {
      await this.queue
      if (generation !== this.generation) throw new Error('A newer connection was selected.')
      const { activeId } = await this.store.status()
      if (generation !== this.generation) throw new Error('A newer connection was selected.')
      return activeId ? this.restore(activeId) : null
    })()
    this.resuming = pending
    try { return await pending } finally { if (this.resuming === pending) this.resuming = null }
  }

  /** Clear process memory on exit while retaining the chosen saved workspace. */
  lock(): void {
    ++this.generation
    this.active = null
  }

  disconnect(): Promise<void> {
    this.lock()
    return this.serial(() => this.store.select(null))
  }

  async forget(id: string): Promise<void> {
    ++this.generation
    if (this.active?.bookmarkId === id) this.active = null
    await this.serial(() => this.store.remove(id))
  }

  reset(): Promise<void> {
    this.lock()
    return this.serial(() => this.store.reset())
  }

  authorization(url: URL, header: string): string {
    if (!isWorkspaceSession(header)) return header
    if (!this.active || header !== 'Bearer ' + this.active.sessionToken) throw new Error('Reconnect to your workspace before continuing.')
    const endpoint = new URL(this.active.endpoint)
    const prefix = endpoint.pathname.replace(/\/+$/, '')
    if (url.origin !== endpoint.origin || url.username || url.password || url.hash ||
        !(url.pathname.startsWith(prefix + '/v1/') || [prefix + '/health/live', prefix + '/health/ready'].includes(url.pathname))) {
      throw new Error('A saved connection can only access its own workspace API.')
    }
    return 'Bearer ' + this.active.credential
  }
}
