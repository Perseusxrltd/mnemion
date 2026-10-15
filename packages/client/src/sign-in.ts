import type { Role } from './index.js'

export interface PasswordAccount {
  username: string
  reset_required: boolean
  changed_at: string
}
export interface DeviceSession {
  id: string
  principal_id: string
  device_name: string
  transport: 'native' | 'browser'
  created_at: string
  last_refreshed_at: string
  expires_at: string
  revoked_at: string | null
  current: boolean
  authentication?: 'password' | 'company'
}
export interface CompanyProvider { id: string; name: string; issuer: string; session_seconds: number }
export interface CompanyConfiguration { providers: CompanyProvider[]; callback_uri: string | null }
export interface CompanyLink {
  id: string; principal_id: string; provider_id: string; issuer: string; client_id: string; subject: string
  created_at: string; changed_at: string; last_authenticated_at: string | null; revoked_at: string | null
}
export interface OAuthConnection {
  session_id: string
  principal_id: string
  client_id: string
  issuer: string
  resource: string
  scopes: string[]
  device_name: string
  created_at: string
  last_refreshed_at: string
  expires_at: string
  revoked_at: string | null
}
export interface OAuthConfiguration {
  mode: 'disabled' | 'personal' | 'external'
  mcp_enabled: boolean
  resource: string | null
  issuer: string | null
}
export interface SignInInvitation {
  id: string
  principal_id: string
  issued_by: string
  purpose: 'enroll' | 'reset'
  permissions: { administrator: boolean; spaces: { space_id: string; role: Role }[] }
  created_at: string
  expires_at: string
  consumed_at: string | null
  revoked_at: string | null
}
export interface InvitationReceipt {
  id: string
  workspace_id: string
  purpose: 'enroll' | 'reset'
  expires_at: string
  invitation_token: string
  invitation_url: string | null
  sign_in_url: string | null
  preview: InvitationPreview
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
  spaces: { space_id: string; name: string; role: Role }[]
}
export interface SignInCredentials { workspace_id: string; username: string; password: string; device_name: string }
export interface InvitationCredentials { invitation: string; username: string; password: string; device_name: string }
