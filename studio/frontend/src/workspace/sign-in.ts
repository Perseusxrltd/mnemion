import { MnemionClient, MnemionError, type InvitationCredentials, type InvitationPreview, type SignInCredentials } from '@mnemion/client'
import type { Connection } from './connection-types'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const TOKEN = (prefix: string, value: unknown): value is string => typeof value === 'string' && new RegExp('^' + prefix + '[A-Za-z0-9_-]{43}$').test(value)
const BOOKMARKS = 'mnemion_sign_in_bookmarks_v1'
export type JoinLink = { endpoint: string; workspaceId?: string; invitation?: string }
export type BrowserBookmark = {
  endpoint: string; workspaceId: string; principalId: string; sessionId: string
  name: string; workspaceName: string; expiresAt: string; refreshPending: boolean
}
type Tokens = {
  tenant_id: string; principal_id: string; session_id: string; access_token: string
  refresh_token: string | null; csrf_token: string; access_expires_at: string; expires_at: string
  persistence: 'cookie' | 'memory'; rotation: number
}

export function joinLink(value: string): JoinLink {
  if (value.length > 4096) throw new Error('The workspace address is too long.')
  let url: URL
  try { url = new URL(value.trim()) } catch { throw new Error('Enter a complete workspace address or invitation link.') }
  if (url.username || url.password || (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)))) {
    throw new Error('Use HTTPS for a remote workspace. Local workspaces may use loopback HTTP.')
  }
  const workspace = url.searchParams.get('workspace') ?? undefined
  if ([...url.searchParams.keys()].some(key => key !== 'workspace') || url.searchParams.getAll('workspace').length > 1 || (workspace && !UUID.test(workspace))) {
    throw new Error('Use the sign-in link supplied by your workspace administrator.')
  }
  const fragment = new URLSearchParams(url.hash.slice(1))
  const invitation = fragment.get('invitation') ?? undefined
  if (url.hash && ([...fragment.keys()].some(key => key !== 'invitation') || fragment.getAll('invitation').length !== 1 || !TOKEN('mnm_i_', invitation))) {
    throw new Error('Paste the complete invitation link from your administrator.')
  }
  url.hash = ''; url.search = ''
  url.pathname = url.pathname.replace(/\/(?:v1|mcp|workspace)\/?$/, '')
  return { endpoint: url.href.replace(/\/+$/, ''), workspaceId: workspace?.toLowerCase(), invitation }
}

export function initialJoinLink(): JoinLink | null {
  if (location.protocol === 'file:') return null
  try {
    const value = joinLink(location.href)
    if (value.invitation) history.replaceState(history.state, '', location.pathname + location.search)
    return value.workspaceId || value.invitation ? value : null
  } catch { return null }
}

export function canRememberBrowser(): boolean {
  return location.protocol === 'https:' && !!navigator.locks && typeof BroadcastChannel !== 'undefined'
}
function failed(message = 'Sign in to this workspace again.'): MnemionError {
  return new MnemionError(401, 'sign_in_required', message)
}
async function browserLock<T>(workspaceId: string, action: () => Promise<T>): Promise<T> {
  try { return await navigator.locks.request('mnemion-sign-in:' + workspaceId, { signal: AbortSignal.timeout(25_000) }, action) }
  catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') throw failed('Another tab is finishing sign-in. Close that tab or try again shortly.')
    throw error
  }
}
function ownOrigin(endpoint: string): void {
  if (new URL(endpoint).origin !== location.origin) throw new Error('Open the workspace’s own website to sign in, or use the desktop app.')
}
export function browserBookmarks(): BrowserBookmark[] {
  try {
    const raw = localStorage.getItem(BOOKMARKS)
    if (!raw || raw.length > 32768) return []
    const data: unknown = JSON.parse(raw)
    if (!Array.isArray(data) || data.length > 32) return []
    return data.filter((value): value is BrowserBookmark => {
      if (!value || typeof value !== 'object') return false
      const b = value as BrowserBookmark
      return typeof b.endpoint === 'string' && b.endpoint.length <= 4096 && joinLink(b.endpoint).endpoint === b.endpoint &&
        new URL(b.endpoint).origin === location.origin && [b.workspaceId, b.principalId, b.sessionId].every(id => typeof id === 'string' && UUID.test(id)) &&
        [b.name, b.workspaceName].every(label => typeof label === 'string' && label.length <= 256) &&
        typeof b.expiresAt === 'string' && Number.isFinite(Date.parse(b.expiresAt)) && typeof b.refreshPending === 'boolean'
    }).map(b => ({ endpoint: b.endpoint, workspaceId: b.workspaceId, principalId: b.principalId, sessionId: b.sessionId,
      name: b.name, workspaceName: b.workspaceName, expiresAt: b.expiresAt, refreshPending: b.refreshPending }))
  } catch { return [] }
}
function saveBookmark(bookmark: BrowserBookmark): void {
  const others = browserBookmarks().filter(b => b.endpoint !== bookmark.endpoint || b.workspaceId !== bookmark.workspaceId)
  if (others.length >= 32) throw failed('Remove an old browser login before remembering another workspace.')
  try { localStorage.setItem(BOOKMARKS, JSON.stringify([...others, bookmark])) }
  catch { throw failed('This browser cannot remember the login. Sign in without remembering this device.') }
}
export function forgetBrowserBookmark(bookmark: BrowserBookmark): void {
  try { localStorage.setItem(BOOKMARKS, JSON.stringify(browserBookmarks().filter(b => b.sessionId !== bookmark.sessionId))) }
  catch { /* Sign-out still clears the in-memory session and attempts server revocation. */ }
}

async function request(endpoint: string, operation: string, input: unknown, csrf?: string): Promise<unknown> {
  ownOrigin(endpoint)
  let response: Response
  try {
    response = await fetch(endpoint + '/v1/sign-in/' + operation, {
      method: 'POST', body: JSON.stringify(input), redirect: 'error', cache: 'no-store', credentials: 'same-origin',
      signal: AbortSignal.timeout(20_000), headers: { 'Content-Type': 'application/json', Accept: 'application/json',
        'ngrok-skip-browser-warning': 'mnemion', ...(csrf ? { 'X-Mnemion-CSRF': csrf } : {}) },
    })
  } catch { throw failed('The workspace could not confirm this request. Check the connection and sign in again.') }
  if (!response.ok) {
    await response.body?.cancel()
    if (response.status === 404) throw failed('Update this workspace server to use individual sign-in. You can still connect with a workspace key.')
    if (response.status === 429) throw failed('Too many attempts. Wait a few minutes and try again.')
    if (response.status === 409) throw failed('The account or server configuration changed. Check your login or ask your administrator for a new invitation.')
    if (response.status === 422) throw failed('Check the fields. Use a unique password of at least 15 characters, such as several unrelated words.')
    throw failed('Sign-in could not be completed. Check your login or request a new invitation.')
  }
  const reader = response.body?.getReader()
  if (!reader) throw failed('The workspace returned an empty sign-in response.')
  const chunks: Uint8Array[] = []
  let size = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      size += value.byteLength
      if (size > 128 * 1024) { await reader.cancel(); throw failed('The sign-in response was too large.') }
      chunks.push(value)
    }
    const bytes = new Uint8Array(size)
    let offset = 0
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length }
    return JSON.parse(new TextDecoder().decode(bytes))
  } catch (error) {
    if (error instanceof MnemionError) throw error
    throw failed('The workspace returned an invalid sign-in response.')
  } finally { reader.releaseLock() }
}

function readTokens(value: unknown): Tokens {
  if (!value || typeof value !== 'object') throw failed('The workspace returned an invalid login.')
  const t = value as Tokens
  if (![t.tenant_id, t.principal_id, t.session_id].every(id => typeof id === 'string' && UUID.test(id)) ||
      !TOKEN('mnm_s_', t.access_token) || !TOKEN('mnm_c_', t.csrf_token) ||
      !Number.isInteger(t.rotation) || t.rotation < 0 || t.rotation > 4096 ||
      !(t.persistence === 'cookie' && t.refresh_token === null || t.persistence === 'memory' && TOKEN('mnm_r_', t.refresh_token))) throw failed('The workspace returned an invalid login.')
  const access = Date.parse(t.access_expires_at), expires = Date.parse(t.expires_at), now = Date.now()
  if (!Number.isFinite(access) || !Number.isFinite(expires) || access <= now || access > now + 20 * 60_000 || expires < access || expires > now + 31 * 86400_000) {
    throw failed('The login expired or the device clock is incorrect. Check the time and sign in again.')
  }
  return { tenant_id: t.tenant_id, principal_id: t.principal_id, session_id: t.session_id,
    access_token: t.access_token, refresh_token: t.refresh_token, csrf_token: t.csrf_token,
    access_expires_at: t.access_expires_at, expires_at: t.expires_at, persistence: t.persistence, rotation: t.rotation }
}
export async function previewBrowserInvitation(endpoint: string, invitation: string): Promise<InvitationPreview> {
  const value = await request(endpoint, 'invitations/preview', { invitation })
  if (!value || typeof value !== 'object') throw failed('Invalid invitation.')
  const p = value as InvitationPreview
  if (![p.id, p.workspace_id, p.principal_id].every(id => typeof id === 'string' && UUID.test(id)) ||
      ![p.workspace_name, p.person_name].every(label => typeof label === 'string' && label.length <= 256) ||
      typeof p.administrator !== 'boolean' || !['enroll', 'reset'].includes(p.purpose) ||
      typeof p.expires_at !== 'string' || !Number.isFinite(Date.parse(p.expires_at)) || Date.parse(p.expires_at) <= Date.now() ||
      !(p.suggested_login === null || typeof p.suggested_login === 'string' && p.suggested_login.length <= 128) ||
      !Array.isArray(p.spaces) || p.spaces.length > 1000 ||
      !p.spaces.every(s => s && typeof s === 'object' && typeof s.space_id === 'string' && UUID.test(s.space_id) && typeof s.name === 'string' && s.name.length <= 256 && ['reader', 'contributor', 'reviewer', 'administrator'].includes(s.role)) ||
      JSON.stringify(p).includes(invitation)) throw failed('The workspace returned an invalid invitation.')
  return { id: p.id, workspace_id: p.workspace_id, workspace_name: p.workspace_name,
    principal_id: p.principal_id, person_name: p.person_name, administrator: p.administrator,
    purpose: p.purpose, expires_at: p.expires_at, suggested_login: p.suggested_login,
    spaces: p.spaces.map(s => ({ space_id: s.space_id, name: s.name, role: s.role })) }
}

export class BrowserSignIn {
  readonly client: MnemionClient
  #tokens: Tokens | null
  #bookmark: BrowserBookmark
  #cookie: boolean
  #closed = false
  #pending: Promise<void> | null = null
  #channel?: BroadcastChannel
  #listeners = new Set<() => void>()

  private constructor(readonly endpoint: string, bookmark: BrowserBookmark, tokens: Tokens | null) {
    ownOrigin(endpoint)
    this.#tokens = tokens; this.#bookmark = bookmark; this.#cookie = !tokens || tokens.persistence === 'cookie'
    if (this.#cookie) {
      if (!canRememberBrowser()) throw failed('This browser cannot safely restore a remembered login. Sign in without remembering this device.')
      this.#channel = new BroadcastChannel('mnemion-sign-in:' + bookmark.workspaceId + ':' + bookmark.sessionId)
      this.#channel.onmessage = ({ data }) => {
        if (data?.kind === 'request' && this.#tokens && !this.#closed && Date.parse(this.#tokens.access_expires_at) > Date.now() + 60_000) this.#publish()
        if (data?.kind === 'closed') this.#close()
        if (data?.kind === 'access' && !this.#closed) {
          try {
            const candidate = readTokens(data.tokens)
            this.#checkPin(candidate)
            if (candidate.persistence !== 'cookie') return
            if (!this.#tokens || candidate.rotation > this.#tokens.rotation) this.#tokens = candidate
            for (const done of this.#listeners) done()
          } catch { /* Ignore malformed or different-account tab messages. */ }
        }
      }
    }
    this.client = new MnemionClient({ baseUrl: endpoint, apiKey: () => this.accessToken() })
  }
  #checkPin(tokens: Tokens): void {
    const b = this.#bookmark
    if (tokens.tenant_id !== b.workspaceId || tokens.principal_id !== b.principalId || tokens.session_id !== b.sessionId ||
        Date.parse(tokens.expires_at) !== Date.parse(b.expiresAt)) throw failed('This login identifies a different account. Sign in again.')
  }
  #publish(): void { if (this.#cookie && this.#tokens) this.#channel?.postMessage({ kind: 'access', tokens: this.#tokens }) }
  #close(): void {
    this.#closed = true; this.#tokens = null
    for (const done of this.#listeners) done()
    this.#channel?.close()
    this.#channel = undefined
  }
  async #lock<T>(action: () => Promise<T>): Promise<T> {
    return this.#cookie ? browserLock(this.#bookmark.workspaceId, action) : action()
  }
  async #borrow(): Promise<void> {
    if (!this.#channel) return
    await new Promise<void>(resolve => {
      const done = () => { clearTimeout(timer); this.#listeners.delete(done); resolve() }
      const timer = setTimeout(done, 150)
      this.#listeners.add(done)
      this.#channel!.postMessage({ kind: 'request' })
    })
  }
  #csrf(): string {
    if (!this.#cookie) return this.#tokens?.csrf_token ?? ''
    const name = '__Host-mnemion-csrf-' + this.#bookmark.workspaceId.replaceAll('-', '')
    const values = document.cookie.split(';').map(part => part.trim()).filter(part => part.startsWith(name + '='))
    const value = values.length === 1 ? values[0].slice(name.length + 1) : ''
    if (!TOKEN('mnm_c_', value)) throw failed('This browser login expired. Sign in again.')
    return value
  }
  async accessToken(): Promise<string> {
    if (this.#closed) throw failed()
    if (this.#tokens && Date.parse(this.#tokens.access_expires_at) > Date.now() + 60_000) return this.#tokens.access_token
    if (!this.#pending) {
      const operation = this.#lock(async () => {
        if (this.#closed) throw failed()
        if (this.#cookie) {
          const current = browserBookmarks().find(b => b.endpoint === this.endpoint && b.workspaceId === this.#bookmark.workspaceId)
          if (!current || current.sessionId !== this.#bookmark.sessionId || current.refreshPending) throw failed('This saved login changed or its refresh was interrupted. Sign in again.')
          await this.#borrow()
          if (this.#tokens && Date.parse(this.#tokens.access_expires_at) > Date.now() + 60_000) return
          saveBookmark({ ...this.#bookmark, refreshPending: true })
        }
        const tokens = readTokens(await request(this.endpoint, 'refresh', {
          workspace_id: this.#bookmark.workspaceId, session_id: this.#bookmark.sessionId, transport: 'browser',
          ...(this.#cookie ? {} : { refresh_token: this.#tokens?.refresh_token }),
        }, this.#csrf()))
        this.#checkPin(tokens)
        if (this.#closed) throw failed()
        if (this.#cookie) saveBookmark(this.#bookmark)
        this.#tokens = tokens
        this.#publish()
      })
      this.#pending = operation
      try { await operation } catch (error) {
        this.#channel?.postMessage({ kind: 'closed' }); this.#close(); throw error
      } finally { if (this.#pending === operation) this.#pending = null }
    } else await this.#pending
    if (this.#closed || !this.#tokens) throw failed()
    return this.#tokens.access_token
  }
  async #connection(): Promise<Connection> {
    const me = await this.client.me()
    if (me.tenant_id !== this.#bookmark.workspaceId || me.principal_id !== this.#bookmark.principalId) throw failed('The workspace returned another account. Sign in again.')
    if ([me.name, me.tenant_name].some(value => typeof value !== 'string' || value.length > 256)) throw failed('Invalid workspace identity.')
    this.#bookmark = { ...this.#bookmark, name: me.name, workspaceName: me.tenant_name }
    if (this.#cookie) saveBookmark(this.#bookmark)
    return { client: this.client, me, endpoint: this.endpoint, authentication: 'password', signOut: () => this.signOut(), close: () => this.#close() }
  }
  static async signIn(endpoint: string, input: SignInCredentials | InvitationCredentials, remember: boolean, preview?: InvitationPreview): Promise<Connection> {
    ownOrigin(endpoint)
    const workspaceId = preview?.workspace_id ?? (input as SignInCredentials).workspace_id
    if (!UUID.test(workspaceId)) throw failed('Use your administrator’s workspace sign-in link.')
    const start = async () => {
      const previous = browserBookmarks().find(b => b.endpoint === endpoint && b.workspaceId === workspaceId)
      if (previous) {
        // The same workspace lock covers both logout and cookie replacement.
        if (canRememberBrowser()) await new BrowserSignIn(endpoint, previous, null).#end()
        else forgetBrowserBookmark(previous)
      }
      const tokens = readTokens(await request(endpoint, preview ? 'invitations/accept' : 'login', {
        ...input, transport: 'browser', remember: remember && canRememberBrowser(),
      }))
      if (tokens.tenant_id !== workspaceId || (preview && tokens.principal_id !== preview.principal_id)) throw failed('The sign-in identified another workspace or person.')
      const session = new BrowserSignIn(endpoint, { endpoint, workspaceId: tokens.tenant_id, principalId: tokens.principal_id,
        sessionId: tokens.session_id, expiresAt: tokens.expires_at, name: '', workspaceName: '', refreshPending: false }, tokens)
      try { const connection = await session.#connection(); session.#publish(); return connection }
      catch (error) { await session.#end().catch(() => {}); throw error }
    }
    return canRememberBrowser() ? browserLock(workspaceId, start) : start()
  }
  static async resume(bookmark: BrowserBookmark): Promise<Connection> {
    if (bookmark.refreshPending || Date.parse(bookmark.expiresAt) <= Date.now()) throw failed('The saved login expired or its refresh was interrupted. Sign in again.')
    const session = new BrowserSignIn(bookmark.endpoint, bookmark, null)
    try { return await session.#connection() } catch (error) { session.#close(); throw error }
  }
  async #end(): Promise<void> {
    let error: unknown
    try {
      await request(this.endpoint, 'logout', {
          workspace_id: this.#bookmark.workspaceId, session_id: this.#bookmark.sessionId, transport: 'browser',
          ...(this.#cookie ? {} : { refresh_token: this.#tokens?.refresh_token }),
      }, this.#csrf())
    } catch { error = failed('Signed out in this window. The workspace could not confirm revocation; revoke this device in Account & sessions when it is reachable.') }
    finally {
      forgetBrowserBookmark(this.#bookmark)
      this.#channel?.postMessage({ kind: 'closed' }); this.#close()
    }
    if (error) throw error
  }
  async signOut(): Promise<void> {
    try { await this.#lock(() => this.#end()) }
    finally {
      forgetBrowserBookmark(this.#bookmark)
      this.#channel?.postMessage({ kind: 'closed' }); this.#close()
    }
  }
}
