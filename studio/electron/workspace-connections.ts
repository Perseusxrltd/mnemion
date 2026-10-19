/** Volatile credentials stay in the main process; renderer handles are origin-bound. */
import { randomBytes } from 'node:crypto'
import { WorkspaceStore, workspaceEndpoint, workspaceIdentity, type WorkspaceIdentity, type WorkspaceBookmark } from './workspace-store.js'
import { WorkspacePasswordAuth, type PasswordTokens, type PasswordSession, type InvitationPreview } from './workspace-auth.js'
import { recoveryRecord, type RecoveryDirectoryRecord } from './workspace-recovery.js'
import { WorkspaceCompanyAuth } from './workspace-company-auth.js'

export interface WorkspaceSession {
  endpoint: string
  sessionToken: string
  me: WorkspaceIdentity
  remembered: boolean
  bookmarkId?: string
  authentication?: 'password' | 'company'
}
type Active = WorkspaceSession & { credential: string; password?: PasswordTokens }
export type ExpectedWorkspaceIdentity = Pick<WorkspaceBookmark, 'tenantId' | 'principalId'>
type VerifyIdentity = (endpoint: string, credential: string) => Promise<WorkspaceIdentity>
const PREFIX = 'mnm_session_'
export const isWorkspaceSession = (header: string): boolean => header.startsWith('Bearer ' + PREFIX)
const sessionMetadata = (tokens: PasswordTokens): PasswordSession => ({
  sessionId: tokens.sessionId, expiresAt: tokens.expiresAt, refreshPending: false,
  ...(tokens.authentication ? { authentication: tokens.authentication } : {}),
})

export class WorkspaceConnections {
  private active: Active | null = null
  private generation = 0
  private queue: Promise<void> = Promise.resolve()
  private resuming: Promise<WorkspaceSession | null> | null = null
  private refreshing: Promise<void> | null = null

  constructor(private readonly store: WorkspaceStore, private readonly verify: VerifyIdentity,
    private readonly passwords?: WorkspacePasswordAuth,
    private readonly beforeRestore?: (bookmark: WorkspaceBookmark) => Promise<void>,
    private readonly closed?: (sessionToken: string) => void,
    private readonly readRecovery?: (endpoint: string, credential: string) => Promise<unknown>,
    private readonly company?: WorkspaceCompanyAuth) {}

  private async directory(endpoint: string, credential: string, me: WorkspaceIdentity): Promise<RecoveryDirectoryRecord | null | undefined> {
    if (!me.administrator) return null
    if (!this.readRecovery) return undefined
    const value = await this.readRecovery(endpoint, credential)
    if (value === null || value === undefined) return value
    const record = recoveryRecord(value, me.tenant_id)
    if (JSON.stringify(record).includes(credential)) throw new Error('Invalid recovery references.')
    return record
  }

  async refreshRecovery(sessionToken: string) {
    const active = this.active
    if (!active || active.sessionToken !== sessionToken || !active.bookmarkId || !active.me.administrator) throw new Error('Use the remembered administrator connection to refresh recovery details.')
    const credential = await this.authorization(new URL(active.endpoint + '/v1/recovery-directory'), 'Bearer ' + sessionToken)
    const directory = await this.directory(active.endpoint, credential.replace(/^Bearer /, ''), active.me)
    if (directory === undefined) throw new Error('Recovery details could not be refreshed. The last saved copy is preserved.')
    return this.serial(async () => {
      if (this.active?.sessionToken !== sessionToken) throw new Error('The active connection changed.')
      await this.store.cacheRecovery(active.bookmarkId!, active.me, active.endpoint, directory)
      if (directory === null) throw new Error('This connection no longer has access to the recovery directory. Sign in with a current administrator account.')
      return this.store.inspect(active.bookmarkId!)
    })
  }

  private passwordAuth(): WorkspacePasswordAuth {
    if (!this.passwords) throw new Error('This installation does not support individual sign-in.')
    return this.passwords
  }

  private publicSession(): WorkspaceSession | null {
    if (!this.active) return null
    const { endpoint, sessionToken, me, remembered, bookmarkId, authentication } = this.active
    // Explicit allowlist: neither access nor refresh secrets cross into the renderer.
    return structuredClone({ endpoint, sessionToken, me, remembered, bookmarkId, ...(authentication ? { authentication } : {}) })
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

  async identify(endpoint: string, credential: string): Promise<{ endpoint: string; me: WorkspaceIdentity }> {
    endpoint = workspaceEndpoint(endpoint)
    if (typeof credential !== 'string' || !/^[A-Za-z0-9_.~+/=-]{16,1024}$/.test(credential)) throw new Error('Enter a valid workspace key.')
    const me = workspaceIdentity(await this.verify(endpoint, credential))
    if (JSON.stringify(me).includes(credential)) throw new Error('The workspace returned an invalid identity.')
    return { endpoint, me }
  }

  private async activate(endpoint: string, credential: string, remember: boolean, generation: number,
    expected?: ExpectedWorkspaceIdentity, password?: PasswordTokens): Promise<WorkspaceSession> {
    const identified = await this.identify(endpoint, credential)
    endpoint = identified.endpoint
    const me = identified.me
    if (password && JSON.stringify(me).includes(password.refreshToken)) throw new Error('The workspace returned an invalid identity.')
    if ((expected && (expected.tenantId !== me.tenant_id || expected.principalId !== me.principal_id)) ||
        (password && (password.tenantId !== me.tenant_id || password.principalId !== me.principal_id))) {
      throw new Error('This credential now identifies a different workspace or person. Connect again to review its access.')
    }
    return this.serial(async () => {
      if (generation !== this.generation) throw new Error('A newer connection was selected.')
      let directory: RecoveryDirectoryRecord | null | undefined
      if (remember) {
        try { directory = await this.directory(endpoint, credential, me) } catch { /* Optional recovery metadata must not prevent a verified connection. */ }
      }
      if (generation !== this.generation) throw new Error('A newer connection was selected.')
      const bookmark = remember ? await this.store.save(endpoint, password?.refreshToken ?? credential, me,
        password ? sessionMetadata(password) : undefined, directory) : undefined
      if (!remember) await this.store.select(null)
      if (generation !== this.generation) throw new Error('A newer connection was selected.')
      this.active = { endpoint, credential, me, remembered: !!bookmark, bookmarkId: bookmark?.id,
        sessionToken: PREFIX + randomBytes(32).toString('base64url'),
        ...(password ? { authentication: password.authentication ?? 'password' as const, password } : {}) }
      return this.publicSession()!
    })
  }

  connect(endpoint: string, credential: string, remember: boolean, expected?: ExpectedWorkspaceIdentity): Promise<WorkspaceSession> {
    return this.activate(endpoint, credential, remember, ++this.generation, expected)
  }

  async previewInvitation(endpoint: string, invitation: unknown): Promise<InvitationPreview> {
    return this.passwordAuth().preview(endpoint, invitation)
  }

  private async activatePassword(endpoint: string, tokens: PasswordTokens, remember: boolean, generation: number,
    expected?: WorkspaceBookmark): Promise<WorkspaceSession> {
    try {
      return await this.activate(endpoint, tokens.accessToken, remember, generation, expected, tokens)
    } catch (error) {
      await this.passwordAuth().signOut(endpoint, tokens.refreshToken, sessionMetadata(tokens), tokens.tenantId).catch(() => {})
      throw error
    }
  }

  async signIn(endpoint: string, input: unknown, remember: boolean): Promise<WorkspaceSession> {
    const generation = ++this.generation
    endpoint = workspaceEndpoint(endpoint)
    const tokens = await this.passwordAuth().signIn(endpoint, input)
    return this.activatePassword(endpoint, tokens, remember, generation)
  }

  async companyConfiguration(endpoint: string, workspaceId: unknown) {
    if (!this.company) throw new Error('Update this app to use company sign-in.')
    return this.company.configuration(endpoint, workspaceId)
  }

  cancelCompanySignIn(): void { ++this.generation; this.company?.cancel() }

  async companySignIn(endpoint: string, input: unknown, remember: boolean): Promise<WorkspaceSession> {
    if (!this.company) throw new Error('Update this app to use company sign-in.')
    const generation = ++this.generation
    endpoint = workspaceEndpoint(endpoint)
    const tokens = await this.company.signIn(endpoint, input)
    return this.activatePassword(endpoint, tokens, remember, generation)
  }

  async acceptInvitation(endpoint: string, input: unknown, remember: boolean): Promise<WorkspaceSession> {
    const generation = ++this.generation
    endpoint = workspaceEndpoint(endpoint)
    const invitation = input && typeof input === 'object' ? (input as { invitation?: unknown }).invitation : undefined
    const preview = await this.passwordAuth().preview(endpoint, invitation)
    const tokens = await this.passwordAuth().accept(endpoint, input, preview)
    return this.activatePassword(endpoint, tokens, remember, generation)
  }

  async restore(id: string): Promise<WorkspaceSession> {
    const generation = ++this.generation
    const { bookmark, credential, session } = await this.store.credential(id)
    await this.beforeRestore?.(bookmark)
    if (generation !== this.generation) throw new Error('A newer connection was selected.')
    if (!session) return this.activate(bookmark.endpoint, credential, true, generation, bookmark)
    await this.serial(async () => {
      if (generation !== this.generation) throw new Error('A newer connection was selected.')
      await this.store.markRefreshPending(id)
    })
    const tokens = await this.passwordAuth().refresh(bookmark.endpoint, credential, session, bookmark)
    return this.activatePassword(bookmark.endpoint, tokens, true, generation, bookmark)
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
    this.company?.cancel()
    ++this.generation
    this.active = null
  }

  async disconnect(): Promise<void> {
    const previous = this.active
    this.lock()
    await this.serial(async () => {
      await this.store.select(null)
      if (previous?.password && previous.bookmarkId) await this.store.remove(previous.bookmarkId)
    })
    if (previous?.password) {
      try {
        await this.passwordAuth().signOut(previous.endpoint, previous.password.refreshToken,
          sessionMetadata(previous.password), previous.me.tenant_id)
      } catch {
        throw new Error('Signed out on this device. The workspace could not confirm revocation; revoke this device in Account & sessions when it is reachable.')
      }
    }
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

  private sessionEnded(active: Active): void {
    // Do not cancel a newer connection whose identity check is still running.
    // Explicit disconnect/lock has that authority; a late server denial does not.
    this.active = null
    try { this.closed?.(active.sessionToken) } catch { /* A closing renderer must not prevent credential cleanup. */ }
  }

  /** A final server rejection must still belong to this exact native login. */
  async rejectedAuthorization(header: string, rejected: string): Promise<void> {
    // A request sent before rotation can finish after it. Wait for an existing
    // rotation, then compare the actual rejected credential before closing.
    await this.refreshing?.catch(() => {})
    await this.serial(async () => {
      const active = this.active
      if (this.refreshing || !active?.password || header !== 'Bearer ' + active.sessionToken ||
          rejected !== 'Bearer ' + active.credential) return
      this.sessionEnded(active)
      if (active.bookmarkId) await this.store.remove(active.bookmarkId)
      else await this.store.select(null)
    })
  }

  private async refreshActive(): Promise<void> {
    if (this.refreshing) return this.refreshing
    const active = this.active
    if (!active?.password) return
    const generation = this.generation
    const pending = (async () => {
      let advanced: PasswordTokens | undefined
      try {
        if (active.remembered && active.bookmarkId) {
          await this.serial(async () => {
            if (generation !== this.generation) throw new Error('A newer connection was selected.')
            await this.store.markRefreshPending(active.bookmarkId!)
          })
        }
        advanced = await this.passwordAuth().refresh(active.endpoint, active.password!.refreshToken,
          sessionMetadata(active.password!), { tenantId: active.me.tenant_id, principalId: active.me.principal_id })
        const me = workspaceIdentity(await this.verify(active.endpoint, advanced.accessToken))
        if (me.tenant_id !== active.me.tenant_id || me.principal_id !== active.me.principal_id ||
            JSON.stringify(me).includes(advanced.accessToken) || JSON.stringify(me).includes(advanced.refreshToken)) {
          throw new Error('The refreshed login identified a different account. Sign in again.')
        }
        await this.serial(async () => {
          if (generation !== this.generation || this.active !== active) throw new Error('A newer connection was selected.')
          if (active.remembered) await this.store.save(active.endpoint, advanced!.refreshToken, me, sessionMetadata(advanced!))
          if (generation !== this.generation || this.active !== active) throw new Error('A newer connection was selected.')
          this.active = { ...active, me, credential: advanced!.accessToken, password: advanced }
        })
      } catch (error) {
        if (this.active === active) {
          this.sessionEnded(active)
        }
        if (advanced) await this.passwordAuth().signOut(active.endpoint, advanced.refreshToken,
          sessionMetadata(advanced), active.me.tenant_id).catch(() => {})
        throw error
      }
    })()
    this.refreshing = pending
    try { await pending } finally { if (this.refreshing === pending) this.refreshing = null }
  }

  async authorization(url: URL, header: string): Promise<string> {
    if (!isWorkspaceSession(header)) return header
    if (!this.active || header !== 'Bearer ' + this.active.sessionToken) throw new Error('Reconnect to your workspace before continuing.')
    const endpoint = new URL(this.active.endpoint)
    const prefix = endpoint.pathname.replace(/\/+$/, '')
    if (url.origin !== endpoint.origin || url.username || url.password || url.hash ||
        !(url.pathname.startsWith(prefix + '/v1/') || [prefix + '/health/live', prefix + '/health/ready'].includes(url.pathname))) {
      throw new Error('A saved connection can only access its own workspace API.')
    }
    if (this.active.password && Date.parse(this.active.password.accessExpiresAt) <= Date.now() + 60_000) await this.refreshActive()
    if (!this.active || header !== 'Bearer ' + this.active.sessionToken) throw new Error('Reconnect to your workspace before continuing.')
    return 'Bearer ' + this.active.credential
  }
}
