/** Pure validation shared by the renderer and main process; keep this module Node-free. */
import type { CompanyProvider, CompanyConfiguration, CompanyCredentials, CompanyStart } from '../shared/company-sign-in.js'

export const companyUUID = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
const object = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid company sign-in response.')
  return value as Record<string, unknown>
}
const https = (value: unknown): value is string => {
  if (typeof value !== 'string' || value.length > 8192) return false
  try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password && !url.hash } catch { return false }
}
const provider = (value: unknown): CompanyProvider => {
  const p = object(value)
  if (typeof p.id !== 'string' || !/^[a-z][a-z0-9-]{0,63}$/.test(p.id) ||
      typeof p.name !== 'string' || !p.name.trim() || p.name.length > 100 || /[\u0000-\u001f\u007f]/.test(p.name) ||
      !https(p.issuer) || typeof p.session_seconds !== 'number' || !Number.isInteger(p.session_seconds) || p.session_seconds < 900 || p.session_seconds > 86400) throw new Error('Invalid company sign-in provider.')
  return { id: p.id, name: p.name, issuer: p.issuer, session_seconds: p.session_seconds }
}
export function companyConfiguration(value: unknown, endpoint: string): CompanyConfiguration {
  const data = object(value)
  if (!Array.isArray(data.providers) || data.providers.length > 32 ||
      !(data.callback_uri === null || data.callback_uri === endpoint.replace(/\/$/, '') + '/company/callback')) throw new Error('The workspace returned an invalid company callback.')
  const providers = data.providers.map(provider)
  if (new Set(providers.map(p => p.id)).size !== providers.length) throw new Error('The workspace returned duplicate company providers.')
  return { providers, callback_uri: data.callback_uri }
}
export function companyCredentials(value: unknown): CompanyCredentials {
  const c = object(value)
  if (Object.keys(c).some(key => !['workspace_id', 'provider_id', 'device_name', 'invitation'].includes(key)) ||
      !companyUUID(c.workspace_id) || typeof c.provider_id !== 'string' || !/^[a-z][a-z0-9-]{0,63}$/.test(c.provider_id) ||
      typeof c.device_name !== 'string' || !c.device_name.trim() || c.device_name.length > 100 || /[\u0000-\u001f\u007f]/.test(c.device_name) ||
      !(c.invitation === undefined || typeof c.invitation === 'string' && /^mnm_i_[A-Za-z0-9_-]{43}$/.test(c.invitation))) throw new Error('Check the workspace, company provider and device name.')
  return { workspace_id: c.workspace_id, provider_id: c.provider_id, device_name: c.device_name,
    ...(c.invitation ? { invitation: c.invitation } : {}) }
}
export function companyStart(value: unknown, selected: string): CompanyStart {
  const s = object(value), chosen = provider(s.provider)
  if (typeof s.state !== 'string' || !/^mnm_o_[A-Za-z0-9_-]{43}$/.test(s.state) ||
      typeof s.code_verifier !== 'string' || !/^[A-Za-z0-9._~-]{43,128}$/.test(s.code_verifier) ||
      typeof s.expires_in !== 'number' || !Number.isInteger(s.expires_in) || s.expires_in < 1 || s.expires_in > 300 ||
      !https(s.authorization_url) || chosen.id !== selected) throw new Error('The workspace returned an invalid company login.')
  return { state: s.state, code_verifier: s.code_verifier, expires_in: s.expires_in, authorization_url: s.authorization_url, provider: chosen }
}
