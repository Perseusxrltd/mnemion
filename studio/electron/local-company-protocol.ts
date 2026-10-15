import type { CompanyAccess, CompanyChange, CompanyDiscoveryRequest, CompanyDiscoveryResult, CompanyProviderSettings, CompanyRequest } from '../shared/local-workspace.js'

const revision = /^(?:not-configured|[a-f0-9-]{36}|[a-f0-9]{64})$/
const providerId = /^[a-z][a-z0-9-]{0,63}$/
const providerFields = ['id', 'name', 'issuer', 'authorization_url', 'token_url', 'jwks_url', 'client_id', 'session_seconds']
const requestFields = ['workspace_id', 'expected_revision', 'expected_remote_revision']
const endpointFields = ['issuer', 'authorization_url', 'token_url', 'jwks_url']

function object(input: unknown, fields: readonly string[]): Record<string, unknown> {
  if (!input || typeof input !== 'object' || Array.isArray(input) || Object.keys(input).some(key => !fields.includes(key))) throw new Error('Check the company settings and supported fields.')
  return input as Record<string, unknown>
}
function label(value: unknown, maximum: number) {
  return typeof value === 'string' && value.length > 0 && value.length <= maximum && !!value.trim() && !/[\x00-\x1f\x7f]/.test(value)
}
function url(value: unknown, maximum = 2048) {
  if (typeof value !== 'string' || !value || value.length > maximum || /[^\x21-\x7e]|[\\"<>*]/.test(value)) throw new Error('Use a fixed HTTPS provider address without credentials or a query.')
  try {
    const parsed = new URL(value)
    if (parsed.protocol !== 'https:' || !parsed.hostname || parsed.username || parsed.password || parsed.search || parsed.hash || (parsed.port && Number(parsed.port) < 1)) throw new Error()
  } catch { throw new Error('Use a fixed HTTPS provider address without credentials or a query.') }
  return value
}
function request(value: Record<string, unknown>): CompanyRequest {
  if (typeof value.workspace_id !== 'string' || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(value.workspace_id) ||
      typeof value.expected_revision !== 'string' || !revision.test(value.expected_revision) ||
      typeof value.expected_remote_revision !== 'string' || !revision.test(value.expected_remote_revision)) throw new Error('Refresh the current workspace, company and remote settings before continuing.')
  return { workspace_id: value.workspace_id, expected_revision: value.expected_revision, expected_remote_revision: value.expected_remote_revision }
}
function ca(value: unknown) {
  if (value !== undefined && value !== null && (typeof value !== 'string' || !value || value.length > 8192 || value.includes('PRIVATE KEY') || !value.includes('-----BEGIN CERTIFICATE-----'))) throw new Error('Use PEM certificates without a private key, up to 8 KiB.')
}
function bounded(input: unknown) {
  if (Buffer.byteLength(JSON.stringify(input), 'utf8') > 15360) throw new Error('Company settings exceed the private request size limit.')
}
export function companyProvider(input: unknown, saved = false): CompanyProviderSettings & { has_client_secret?: boolean } {
  const value = object(input, saved ? [...providerFields, 'has_client_secret'] : providerFields)
  if (typeof value.id !== 'string' || !providerId.test(value.id) || !label(value.name, 100) || !label(value.client_id, 512) ||
      !Number.isInteger(value.session_seconds) || Number(value.session_seconds) < 900 || Number(value.session_seconds) > 86400 ||
      (saved && typeof value.has_client_secret !== 'boolean')) throw new Error('Check the provider name, client ID and session duration (15 minutes to 24 hours).')
  for (const field of endpointFields) url(value[field])
  return structuredClone(value) as CompanyProviderSettings
}
export function companyOptions(input: unknown): CompanyChange {
  const value = object(input, [...requestFields, 'action', 'provider', 'provider_id', 'client_secret', 'clear_client_secret', 'ca_pem'])
  const base = request(value)
  bounded(value)
  if (value.action === 'save') {
    if (value.provider_id !== undefined || (value.client_secret != null && !label(value.client_secret, 2048)) ||
        (value.clear_client_secret !== undefined && typeof value.clear_client_secret !== 'boolean') ||
        (value.client_secret != null && value.clear_client_secret)) throw new Error('Choose whether to retain, replace or remove the client secret.')
    ca(value.ca_pem)
    return { ...value, ...base, action: 'save', provider: companyProvider(value.provider) } as CompanyChange
  }
  if (Object.keys(value).some(key => ![...requestFields, 'action', 'provider_id'].includes(key))) throw new Error('Choose a provider removal or damaged-settings reset.')
  if (value.action === 'remove' && typeof value.provider_id === 'string' && providerId.test(value.provider_id)) return { ...base, action: 'remove', provider_id: value.provider_id }
  if (value.action === 'reset' && value.provider_id === undefined) return { ...base, action: 'reset' }
  throw new Error('Choose a company settings operation.')
}
export function companyDiscoveryOptions(input: unknown): CompanyDiscoveryRequest {
  const value = object(input, [...requestFields, 'issuer', 'ca_pem'])
  const base = request(value)
  ca(value.ca_pem)
  bounded(value)
  return { ...value, ...base, issuer: url(value.issuer) } as CompanyDiscoveryRequest
}
export function companyDiscoveryResult(input: unknown, expected: CompanyDiscoveryRequest): CompanyDiscoveryResult {
  const value = object(input, [...requestFields, ...endpointFields])
  const base = request(value)
  if (base.workspace_id !== expected.workspace_id || base.expected_revision !== expected.expected_revision || base.expected_remote_revision !== expected.expected_remote_revision || value.issuer !== expected.issuer) throw new Error('Provider discovery does not match the current request.')
  for (const field of endpointFields) url(value[field])
  return structuredClone(value) as CompanyDiscoveryResult
}
export function companySnapshot(input: unknown): CompanyAccess {
  const value = object(input, ['revision', 'repairable', 'state', 'message', 'callback_uri', 'has_custom_ca', 'providers'])
  if (typeof value.revision !== 'string' || !(revision.test(value.revision) || value.revision === 'unreadable') ||
      typeof value.repairable !== 'boolean' || typeof value.has_custom_ca !== 'boolean' ||
      !['disabled', 'configured', 'needs_remote', 'configuration_error', 'external'].includes(String(value.state)) || !label(value.message, 512) ||
      !Array.isArray(value.providers) || value.providers.length > 32) throw new Error('Invalid local company settings status.')
  if (value.callback_uri !== null) url(value.callback_uri, 4096)
  const providers = value.providers.map(item => companyProvider(item, true))
  if (new Set(providers.map(item => item.id)).size !== providers.length) throw new Error('Company provider identifiers must be distinct.')
  return { ...value, providers } as CompanyAccess
}
