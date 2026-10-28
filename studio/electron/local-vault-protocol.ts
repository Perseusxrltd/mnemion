import { createHash } from 'node:crypto'
import type { VaultAccess, VaultChange, VaultKey, VaultRequest } from '../shared/local-workspace.js'

const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/
const revision = /^(?:not-configured|[a-f0-9-]{36}|[a-f0-9]{64})$/
const keyId = /^[a-f0-9]{32}$/
function object(input: unknown, fields: string[]): Record<string, unknown> {
  if (!input || typeof input !== 'object' || Array.isArray(input) || Object.keys(input).some(key => !fields.includes(key))) throw new Error('Invalid vault settings fields.')
  return input as Record<string, unknown>
}
export function vaultKeyId(input: unknown): string {
  if (typeof input !== 'string' || !/^mnv_[A-Za-z0-9_-]{43}$/.test(input)) throw new Error('Use a generated Mnemion vault key.')
  const key = Buffer.from(input.slice(4), 'base64url')
  if (key.length !== 32 || key.toString('base64url') !== input.slice(4)) throw new Error('Use a generated Mnemion vault key.')
  return createHash('sha256').update('mnemion-vault-key-v1\0').update(key).digest('hex').slice(0, 32)
}
export function vaultRequest(input: unknown): VaultRequest {
  const value = object(input, ['workspace_id', 'expected_revision'])
  if (typeof value.workspace_id !== 'string' || !uuid.test(value.workspace_id) || typeof value.expected_revision !== 'string' || !revision.test(value.expected_revision)) throw new Error('Refresh the current workspace and vault settings before continuing.')
  return { workspace_id: value.workspace_id, expected_revision: value.expected_revision }
}
export function vaultOptions(input: unknown): VaultChange {
  const value = object(input, ['workspace_id', 'expected_revision', 'action', 'enabled', 'mcp_enabled', 'mcp_metadata_enabled', 'recovery_key', 'key_saved'])
  const base = vaultRequest({ workspace_id: value.workspace_id, expected_revision: value.expected_revision })
  if (!['configure', 'restore'].includes(String(value.action)) || typeof value.enabled !== 'boolean' || typeof value.mcp_enabled !== 'boolean' || (value.key_saved !== undefined && typeof value.key_saved !== 'boolean')) throw new Error('Choose the vault access and key recovery settings.')
  if (value.mcp_metadata_enabled !== undefined && typeof value.mcp_metadata_enabled !== 'boolean') throw new Error('Choose whether agents can inspect vault metadata.')
  if (value.recovery_key !== undefined) vaultKeyId(value.recovery_key)
  if ((value.action === 'restore' || base.expected_revision === 'not-configured') && (!value.recovery_key || value.key_saved !== true)) throw new Error('Save an independent copy of the vault key before enabling it.')
  return structuredClone(value) as VaultChange
}
export function vaultSnapshot(input: unknown): VaultAccess {
  const value = object(input, ['revision', 'repairable', 'state', 'enabled', 'mcp_enabled', 'mcp_metadata_enabled', 'key_id', 'message'])
  if (typeof value.revision !== 'string' || (!revision.test(value.revision) && value.revision !== 'unreadable') ||
      typeof value.repairable !== 'boolean' || typeof value.enabled !== 'boolean' || typeof value.mcp_enabled !== 'boolean' ||
      (value.mcp_metadata_enabled !== undefined && typeof value.mcp_metadata_enabled !== 'boolean') ||
      !['not_configured', 'configured', 'disabled', 'configuration_error', 'external'].includes(String(value.state)) ||
      (value.key_id !== null && (typeof value.key_id !== 'string' || !keyId.test(value.key_id))) ||
      typeof value.message !== 'string' || !value.message || value.message.length > 512) throw new Error('Invalid public vault status.')
  return structuredClone(value) as VaultAccess
}
export function vaultKeyResult(input: unknown, request: VaultRequest): VaultKey {
  const value = object(input, ['workspace_id', 'revision', 'key_id', 'recovery_key'])
  if (value.workspace_id !== request.workspace_id || value.revision !== request.expected_revision ||
      value.key_id !== vaultKeyId(value.recovery_key)) throw new Error('The vault key does not match the current workspace settings.')
  return structuredClone(value) as VaultKey
}
