import { isDeepStrictEqual } from 'node:util'
import type { ModelDefinition, ModelKind, ModelsAccess, ModelsChange, SavedModelProvider } from '../shared/local-models.js'

const revision = /^(?:not-configured|[a-f0-9-]{36}|[a-f0-9]{64})$/
const id = /^[a-z][a-z0-9-]{0,63}$/
const requestFields = ['workspace_id', 'expected_revision']
const common = ['id', 'label', 'protocol', 'endpoint', 'model', 'revision', 'response_model', 'api_key_header', 'timeout_seconds',
  'api_key_env', 'ca_bundle_env', 'tokenizer', 'max_response_bytes', 'keep_alive_seconds', 'server_threads']
const embedding = ['dimensions', 'send_dimensions', 'query_prefix', 'document_prefix', 'chunk_tokens', 'overlap_tokens',
  'max_input_tokens', 'max_query_tokens', 'batch_size', 'max_document_bytes', 'document_timeout_seconds', 'max_queued']
const librarian = ['context_budget', 'chat_overhead_reserve', 'max_output_tokens', 'output_token_parameter', 'json_mode', 'temperature', 'thinking']

function object(input: unknown, fields: readonly string[]): Record<string, unknown> {
  if (!input || typeof input !== 'object' || Array.isArray(input) || Object.keys(input).some(key => !fields.includes(key))) throw new Error('Check the model settings and supported fields.')
  return input as Record<string, unknown>
}
function label(value: unknown, maximum: number): boolean {
  return typeof value === 'string' && value.length > 0 && value.length <= maximum && !!value.trim() && !/[\x00-\x1f\x7f]/.test(value)
}
function endpoint(value: unknown): boolean {
  if (typeof value !== 'string' || !value || value.length > 2000 || /[\s\\]/.test(value)) throw new Error('Use the complete HTTPS model endpoint, or HTTP on localhost, without URL credentials.')
  try {
    const url = new URL(value)
    const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || (url.protocol === 'http:' && !local) ||
        url.username || url.password || url.hash || !url.pathname || url.pathname.endsWith('/') ||
        (url.port && Number(url.port) < 1) || [...url.searchParams.keys()].some(key => key !== 'api-version') || [...url.searchParams].length > 1) throw new Error()
    return !local
  } catch { throw new Error('Use the complete HTTPS model endpoint, or HTTP on localhost, without URL credentials.') }
}
function number(value: Record<string, unknown>, key: string, minimum: number, maximum: number, required = false) {
  if (value[key] === undefined && !required) return
  if (!Number.isInteger(value[key]) || Number(value[key]) < minimum || Number(value[key]) > maximum) throw new Error(`Check the model limit: ${key.replaceAll('_', ' ')}.`)
}
export function modelDefinition(input: unknown): ModelDefinition {
  const value = object(input, ['kind', 'profile'])
  if (!['embedding', 'librarian'].includes(String(value.kind))) throw new Error('Choose embedding or librarian.')
  const kind = value.kind as ModelKind
  const p = object(value.profile, [...common, ...(kind === 'embedding' ? embedding : librarian)])
  if (typeof p.id !== 'string' || !id.test(p.id) || !label(p.label, 200) || !label(p.model, 300) || !label(p.revision, 300) ||
      !['openai', 'ollama'].includes(String(p.protocol)) || (p.response_model != null && !label(p.response_model, 300)) ||
      (p.api_key_header !== undefined && !['Authorization', 'api-key'].includes(String(p.api_key_header))) ||
      p.api_key_env != null || p.ca_bundle_env != null) throw new Error('Check the model identity, protocol and private credential fields.')
  endpoint(p.endpoint)
  if (p.tokenizer !== undefined) {
    const tokenizer = object(p.tokenizer, ['kind', 'repository', 'revision', 'sha256', 'file_env'])
    if (tokenizer.kind !== 'utf8' || Object.entries(tokenizer).some(([key, value]) => key !== 'kind' && value !== null)) throw new Error('Desktop setup uses conservative UTF-8 budgets.')
  }
  number(p, 'timeout_seconds', 1, kind === 'embedding' ? 120 : 90)
  number(p, 'max_response_bytes', 4096, kind === 'embedding' ? 8388608 : 1048576)
  number(p, 'keep_alive_seconds', 0, kind === 'embedding' ? 600 : 60)
  number(p, 'server_threads', 1, kind === 'embedding' ? 32 : 8)
  if (kind === 'embedding') {
    if (['e5-small', 'bge-small-en'].includes(p.id)) throw new Error('Keep the built-in model identifiers; choose a different profile ID.')
    for (const [key, min, max] of [['dimensions', 1, 4096], ['chunk_tokens', 32, 8192], ['overlap_tokens', 0, 4096],
      ['max_input_tokens', 64, 32768], ['max_query_tokens', 32, 32768], ['batch_size', 1, 32], ['max_document_bytes', 1024, 1048576],
      ['document_timeout_seconds', 1, 600], ['max_queued', 0, 64]] as const) number(p, key, min, max, key === 'dimensions')
    if ((p.send_dimensions !== undefined && typeof p.send_dimensions !== 'boolean') || ['query_prefix', 'document_prefix'].some(key => p[key] !== undefined && (typeof p[key] !== 'string' || String(p[key]).length > 2000)) ||
        Number(p.overlap_tokens ?? 64) > Number(p.chunk_tokens ?? 512) / 2 ||
        Number(p.max_input_tokens ?? 4096) < Math.max(Number(p.chunk_tokens ?? 512), Number(p.max_query_tokens ?? 2048)) ||
        Number(p.document_timeout_seconds ?? 120) < Number(p.timeout_seconds ?? 30)) throw new Error('Check embedding prefixes, chunk overlap, input limits and request deadlines.')
  } else {
    for (const [key, min, max] of [['context_budget', 2048, 32768], ['chat_overhead_reserve', 128, 2048], ['max_output_tokens', 256, 8192]] as const) number(p, key, min, max)
    if ((p.output_token_parameter !== undefined && !['max_tokens', 'max_completion_tokens'].includes(String(p.output_token_parameter))) ||
        (p.json_mode !== undefined && typeof p.json_mode !== 'boolean') || (p.thinking != null && typeof p.thinking !== 'boolean') ||
        (p.temperature != null && (typeof p.temperature !== 'number' || !Number.isFinite(p.temperature) || p.temperature < 0 || p.temperature > 1)) ||
        Number(p.max_output_tokens ?? 1024) + Number(p.chat_overhead_reserve ?? 512) + 1024 > Number(p.context_budget ?? 8192)) throw new Error('Check the librarian context, output and structured response settings.')
  }
  return structuredClone(value) as ModelDefinition
}
export function modelsOptions(input: unknown): ModelsChange {
  const value = object(input, [...requestFields, 'action', 'provider', 'kind', 'profile_id', 'api_key', 'clear_api_key', 'ca_pem'])
  if (typeof value.workspace_id !== 'string' || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(value.workspace_id) ||
      typeof value.expected_revision !== 'string' || !revision.test(value.expected_revision)) throw new Error('Refresh the current workspace and model settings before continuing.')
  if (Buffer.byteLength(JSON.stringify(value), 'utf8') > 15360) throw new Error('Model settings exceed the private request size limit. Reduce the profile, certificate or key size.')
  if (value.action === 'save') {
    if (value.kind !== undefined || value.profile_id !== undefined ||
        (value.api_key != null && (typeof value.api_key !== 'string' || !/^[\x21-\x7e]{1,4096}$/.test(value.api_key))) ||
        (value.clear_api_key !== undefined && typeof value.clear_api_key !== 'boolean') || (value.api_key != null && value.clear_api_key) ||
        (value.ca_pem != null && (typeof value.ca_pem !== 'string' || value.ca_pem.length > 8192 || !value.ca_pem.includes('-----BEGIN CERTIFICATE-----') || value.ca_pem.includes('PRIVATE KEY')))) throw new Error('Check the private API key or PEM certificate. Choose replacement or removal of the key.')
    return { ...value, provider: modelDefinition(value.provider) } as ModelsChange
  }
  if (Object.keys(value).some(key => ![...requestFields, 'action', 'kind', 'profile_id'].includes(key))) throw new Error('Choose a model removal or damaged-settings reset.')
  if (value.action === 'remove' && ['embedding', 'librarian'].includes(String(value.kind)) && typeof value.profile_id === 'string' && id.test(value.profile_id)) return structuredClone(value) as ModelsChange
  if (value.action === 'reset' && value.kind === undefined && value.profile_id === undefined) return structuredClone(value) as ModelsChange
  throw new Error('Choose a model settings operation.')
}
export function modelsSnapshot(input: unknown): ModelsAccess {
  const value = object(input, ['revision', 'repairable', 'state', 'message', 'providers'])
  if (typeof value.revision !== 'string' || !(revision.test(value.revision) || value.revision === 'unreadable') ||
      typeof value.repairable !== 'boolean' || !label(value.message, 512) ||
      !['not_configured', 'configured', 'configuration_error', 'external'].includes(String(value.state)) || !Array.isArray(value.providers) || value.providers.length > 16) throw new Error('Invalid local model settings status.')
  const providers = value.providers.map(input => {
    const item = object(input, ['kind', 'profile', 'has_api_key', 'has_custom_ca', 'network_egress', 'fingerprint'])
    const provider = modelDefinition({ kind: item.kind, profile: item.profile })
    if (typeof item.has_api_key !== 'boolean' || typeof item.has_custom_ca !== 'boolean' || item.network_egress !== endpoint(provider.profile.endpoint) || typeof item.fingerprint !== 'string' || !/^[a-f0-9]{64}$/.test(item.fingerprint)) throw new Error('Invalid private model status.')
    return { ...item, ...provider } as SavedModelProvider
  })
  if (new Set(providers.map(p => p.kind + '/' + p.profile.id)).size !== providers.length || ['embedding', 'librarian'].some(kind => providers.filter(p => p.kind === kind).length > 8)) throw new Error('Model profiles must have distinct identifiers, up to eight of each kind.')
  return { ...value, providers } as ModelsAccess
}
export function modelsSaved(snapshot: ModelsAccess | undefined, change: ModelsChange): boolean {
  if (!snapshot || ['configuration_error', 'external'].includes(snapshot.state) || snapshot.revision === change.expected_revision) return false
  if (change.action === 'reset') return snapshot.providers.length === 0
  const kind = change.action === 'save' ? change.provider.kind : change.kind
  const id = change.action === 'save' ? change.provider.profile.id : change.profile_id
  const saved = snapshot.providers.find(p => p.kind === kind && p.profile.id === id)
  if (change.action === 'remove') return !saved
  const profile = { ...change.provider.profile }
  if (profile.tokenizer) profile.tokenizer = { repository: null, revision: null, sha256: null, file_env: null, ...profile.tokenizer }
  return !!saved && Object.entries(profile).every(([key, value]) => isDeepStrictEqual(saved.profile[key as keyof typeof saved.profile], value)) &&
    (!change.api_key || saved.has_api_key) && (!change.clear_api_key || !saved.has_api_key) &&
    (!Object.hasOwn(change, 'ca_pem') || saved.has_custom_ca === !!change.ca_pem)
}
