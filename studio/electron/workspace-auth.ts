/** Password credentials stay in the main process and its protected vault. */
import { workspaceEndpoint } from './workspace-store.js'

export interface PasswordSession {
  sessionId: string
  expiresAt: string
  refreshPending: boolean
}
export interface PasswordTokens {
  sessionId: string
  tenantId: string
  principalId: string
  accessToken: string
  refreshToken: string
  accessExpiresAt: string
  expiresAt: string
}
export interface InvitationPreview {
  id: string
  workspace_id: string
  workspace_name: string
  principal_id: string
  person_name: string
  administrator: boolean
  purpose: 'enroll' | 'reset'
  expires_at: string
  suggested_login: string | null
  spaces: { space_id: string; name: string; role: string }[]
}
export type SignInRequest = (endpoint: string, operation: 'login' | 'refresh' | 'logout' | 'invitations/preview' | 'invitations/accept', input: Record<string, unknown>) => Promise<unknown>
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const ACCESS = /^mnm_s_[A-Za-z0-9_-]{43}$/
const REFRESH = /^mnm_r_[A-Za-z0-9_-]{43}$/
const INVITATION = /^mnm_i_[A-Za-z0-9_-]{43}$/

export function passwordSession(value: unknown): PasswordSession {
  const data = object(value)
  if (!uuid(data.sessionId) || typeof data.expiresAt !== 'string' || !Number.isFinite(Date.parse(data.expiresAt)) ||
      typeof data.refreshPending !== 'boolean' || Object.keys(data).some(key => !['sessionId', 'expiresAt', 'refreshPending'].includes(key))) {
    throw new Error('This saved login is invalid. Sign in again.')
  }
  return { sessionId: data.sessionId, expiresAt: data.expiresAt, refreshPending: data.refreshPending }
}
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid sign-in response.')
  return value as Record<string, unknown>
}
function uuid(value: unknown): value is string { return typeof value === 'string' && UUID.test(value) }
function label(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= 256 && !/[\u0000-\u001f\u007f]/.test(value)
}
function tokens(value: unknown): PasswordTokens {
  const data = object(value)
  if (!uuid(data.session_id) || !uuid(data.tenant_id) || !uuid(data.principal_id) ||
      typeof data.access_token !== 'string' || !ACCESS.test(data.access_token) ||
      typeof data.refresh_token !== 'string' || !REFRESH.test(data.refresh_token) ||
      typeof data.access_expires_at !== 'string' || typeof data.expires_at !== 'string' ||
      data.persistence !== 'native' || data.csrf_token != null) throw new Error('The workspace returned an invalid login.')
  const access = Date.parse(data.access_expires_at), expires = Date.parse(data.expires_at), now = Date.now()
  if (!Number.isFinite(access) || !Number.isFinite(expires) || access <= now || expires < access ||
      access > now + 20 * 60_000 || expires > now + 31 * 86400_000) {
    throw new Error('The login has expired or the device clock is incorrect. Check the time and sign in again.')
  }
  return { sessionId: data.session_id, tenantId: data.tenant_id, principalId: data.principal_id,
    accessToken: data.access_token, refreshToken: data.refresh_token,
    accessExpiresAt: data.access_expires_at, expiresAt: data.expires_at }
}
function credentials(input: unknown, invitation: boolean): Record<string, unknown> {
  const value = object(input)
  const allowed = invitation ? ['invitation', 'username', 'password', 'device_name'] : ['workspace_id', 'username', 'password', 'device_name']
  if (Object.keys(value).some(key => !allowed.includes(key)) ||
      typeof value.username !== 'string' || value.username.length < 3 || value.username.length > 128 ||
      typeof value.password !== 'string' || !value.password || value.password.length > 256 || Buffer.byteLength(value.password) > 512 ||
      typeof value.device_name !== 'string' || value.device_name.length > 100 || !label(value.device_name) ||
      (invitation ? typeof value.invitation !== 'string' || !INVITATION.test(value.invitation) : !uuid(value.workspace_id))) {
    throw new Error('Check the workspace, login, password and device name.')
  }
  return { ...value, transport: 'native' }
}

export class WorkspacePasswordAuth {
  constructor(private readonly request: SignInRequest) {}

  async signIn(endpoint: string, input: unknown): Promise<PasswordTokens> {
    const command = credentials(input, false)
    const result = tokens(await this.request(workspaceEndpoint(endpoint), 'login', command))
    if (result.tenantId !== command.workspace_id) throw new Error('The login identified another workspace. Sign in again.')
    return result
  }

  async accept(endpoint: string, input: unknown, expected: InvitationPreview): Promise<PasswordTokens> {
    const result = tokens(await this.request(workspaceEndpoint(endpoint), 'invitations/accept', credentials(input, true)))
    if (result.tenantId !== expected.workspace_id || result.principalId !== expected.principal_id) {
      throw new Error('The invitation identified another workspace or person. Ask for a new invitation.')
    }
    return result
  }

  async preview(endpoint: string, secret: unknown): Promise<InvitationPreview> {
    if (typeof secret !== 'string' || !INVITATION.test(secret)) throw new Error('Paste a complete invitation from your administrator.')
    const data = object(await this.request(workspaceEndpoint(endpoint), 'invitations/preview', { invitation: secret }))
    if (!uuid(data.id) || !uuid(data.workspace_id) || !uuid(data.principal_id) ||
        !label(data.workspace_name) || !label(data.person_name) || typeof data.administrator !== 'boolean' ||
        !['enroll', 'reset'].includes(String(data.purpose)) || typeof data.expires_at !== 'string' ||
        !Number.isFinite(Date.parse(data.expires_at)) || !(data.suggested_login === null || label(data.suggested_login)) ||
        !Array.isArray(data.spaces) || data.spaces.length > 1000 || JSON.stringify(data).includes(secret)) {
      throw new Error('The workspace returned an invalid invitation.')
    }
    const spaces = data.spaces.map(value => {
      const space = object(value)
      if (!uuid(space.space_id) || !label(space.name) || !['reader', 'contributor', 'reviewer', 'administrator'].includes(String(space.role))) {
        throw new Error('The invitation returned invalid permissions.')
      }
      return { space_id: space.space_id, name: space.name, role: String(space.role) }
    })
    return { id: data.id, workspace_id: data.workspace_id, workspace_name: data.workspace_name,
      principal_id: data.principal_id, person_name: data.person_name, administrator: data.administrator,
      purpose: data.purpose as 'enroll' | 'reset', expires_at: data.expires_at, suggested_login: data.suggested_login as string | null, spaces }
  }

  async refresh(endpoint: string, refresh: string, session: PasswordSession, expected: { tenantId: string; principalId: string }): Promise<PasswordTokens> {
    if (session.refreshPending) throw new Error('The previous login refresh was interrupted. Sign in again to keep your account safe.')
    if (Date.parse(session.expiresAt) <= Date.now()) throw new Error('This saved login has expired. Sign in again.')
    if (!REFRESH.test(refresh)) throw new Error('This saved login is invalid. Sign in again.')
    const result = tokens(await this.request(workspaceEndpoint(endpoint), 'refresh', {
      workspace_id: expected.tenantId, session_id: session.sessionId, transport: 'native', refresh_token: refresh,
    }))
    if (result.sessionId !== session.sessionId || result.tenantId !== expected.tenantId || result.principalId !== expected.principalId ||
        Date.parse(result.expiresAt) !== Date.parse(session.expiresAt)) {
      throw new Error('The refreshed login no longer identifies the saved account. Sign in again.')
    }
    return result
  }

  async signOut(endpoint: string, refresh: string, session: PasswordSession, tenantId: string): Promise<void> {
    await this.request(workspaceEndpoint(endpoint), 'logout', {
      workspace_id: tenantId, session_id: session.sessionId, transport: 'native', refresh_token: refresh,
    })
  }
}
