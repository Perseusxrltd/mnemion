import { isAbsolute } from 'node:path'
import type { BackupAction, BackupFile, BackupInspectionData, BackupReceipt, RecoveryReceipt } from '../shared/local-workspace.js'

const uuid = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i
const digest = /^[a-f0-9]{64}$/
function object(value: unknown): Record<string, any> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid backup result')
  return value as Record<string, any>
}
function text(value: unknown, max = 4096): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= max && !/[\x00-\x1f\x7f]/.test(value)
}
function count(value: unknown, max = Number.MAX_SAFE_INTEGER): value is number {
  return Number.isSafeInteger(value) && Number(value) >= 0 && Number(value) <= max
}
function date(value: unknown): value is string {
  return text(value, 40) && Number.isFinite(Date.parse(value))
}
function identity(value: unknown): value is string { return typeof value === 'string' && uuid.test(value) }
function checksum(value: unknown): value is string { return typeof value === 'string' && digest.test(value) }
function version(value: unknown): value is string { return typeof value === 'string' && /^[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}$/.test(value) }
function keyId(value: unknown): value is string { return typeof value === 'string' && /^[a-f0-9]{24}$/.test(value) }
function file(input: unknown): BackupFile {
  const value = object(input)
  if (!text(value.file) || !isAbsolute(value.file) || !count(value.bytes, 50 * 1024 ** 3 + 2048) ||
      !checksum(value.sha256) || !keyId(value.key_id) || value.authenticated !== true) throw new Error('Invalid backup file receipt')
  return { file: value.file, bytes: value.bytes, sha256: value.sha256, key_id: value.key_id, authenticated: true }
}

/** Project explicit fields only: extra native output never reaches the UI. */
export function backupResult(action: BackupAction, input: unknown, workspaceId?: string): BackupReceipt | BackupInspectionData | RecoveryReceipt {
  const value = object(input)
  if (action === 'backup' || action === 'backup-ledger') {
    if (value.format !== 1 || !/^[a-f0-9]{32}$/.test(value.operation_id) || !identity(value.workspace_id) ||
        value.workspace_id !== workspaceId || value.scope !== 'complete_local_database' || !count(value.tenant_count) ||
        !date(value.ledger_at) || !version(value.application_version) || !date(value.verified_at)) throw new Error('Invalid backup receipt')
    const result: BackupReceipt = { format: 1, operation_id: value.operation_id, workspace_id: value.workspace_id,
      scope: value.scope, tenant_count: value.tenant_count, ledger_at: value.ledger_at,
      application_version: value.application_version, verified_at: value.verified_at, ledger: file(value.ledger) }
    if (action === 'backup') {
      const snapshot = object(value.snapshot)
      if (!identity(snapshot.backup_id) || !date(snapshot.snapshot_at) || !count(snapshot.memory_count)) throw new Error('Invalid snapshot receipt')
      result.snapshot = { ...file(snapshot), backup_id: snapshot.backup_id, snapshot_at: snapshot.snapshot_at, memory_count: snapshot.memory_count }
    }
    return result
  }
  if (action === 'backup-inspect') {
    if (!['snapshot', 'ledger'].includes(value.kind) || value.authenticated !== true || !keyId(value.key_id) ||
        !count(value.encrypted_bytes, 50 * 1024 ** 3 + 2048) || !checksum(value.sha256) ||
        !date(value.ledger_at) || !count(value.tenant_count)) throw new Error('Invalid backup inspection')
    const result: BackupInspectionData = { kind: value.kind, authenticated: true, key_id: value.key_id,
      encrypted_bytes: value.encrypted_bytes, sha256: value.sha256, ledger_at: value.ledger_at, tenant_count: value.tenant_count }
    if (value.kind === 'ledger') {
      if (!count(value.deletion_count)) throw new Error('Invalid ledger inspection')
      result.deletion_count = value.deletion_count
    } else {
      if (value.archive_verified !== true || !identity(value.backup_id) || !date(value.snapshot_at) ||
          !count(value.memory_count) || !version(value.application_version) || !count(value.server_version) ||
          !Array.isArray(value.tenant_ids) || value.tenant_ids.length !== value.tenant_count || value.tenant_ids.some(id => !identity(id))) throw new Error('Invalid snapshot inspection')
      Object.assign(result, { archive_verified: true, backup_id: value.backup_id, snapshot_at: value.snapshot_at,
        memory_count: value.memory_count, application_version: value.application_version, server_version: value.server_version,
        tenant_ids: [...value.tenant_ids] })
      const context = value.context?.local_workspace
      if (context !== undefined) {
        const hints = object(context)
        if (!identity(hints.workspace_id) || !identity(hints.primary_tenant_id) || !text(hints.workspace_name, 200) ||
            !text(hints.owner_name, 200) || !['e5-small', 'bge-small-en'].includes(hints.embedding_profile) ||
            !count(hints.threads, 8) || hints.threads < 1 || !version(hints.application_version)) throw new Error('Invalid snapshot context')
        result.context = { local_workspace: { workspace_id: hints.workspace_id, primary_tenant_id: hints.primary_tenant_id,
          workspace_name: hints.workspace_name, owner_name: hints.owner_name, embedding_profile: hints.embedding_profile,
          threads: hints.threads, application_version: hints.application_version } }
      }
    }
    return result
  }
  if (value.format !== 1 || value.state !== 'restored' || !date(value.started_at) || !date(value.restored_at) ||
      !identity(value.workspace_id) || !(value.source_workspace_id === null || identity(value.source_workspace_id)) ||
      !identity(value.backup_id) || !identity(value.tenant_id) || !checksum(value.snapshot_sha256) ||
      !checksum(value.ledger_sha256) || !text(value.data_directory) || !isAbsolute(value.data_directory) ||
      !count(value.tenant_count) || value.keys_rotated !== true || !count(value.verified_tables) ||
      !count(value.deletions_reconciled) || !date(value.ledger_at) || value.external_connections_require_review !== true) throw new Error('Invalid recovery receipt')
  return { format: 1, state: 'restored', started_at: value.started_at, restored_at: value.restored_at,
    workspace_id: value.workspace_id, source_workspace_id: value.source_workspace_id, backup_id: value.backup_id,
    snapshot_sha256: value.snapshot_sha256, ledger_sha256: value.ledger_sha256, data_directory: value.data_directory,
    tenant_id: value.tenant_id, tenant_count: value.tenant_count, keys_rotated: true, verified_tables: value.verified_tables,
    deletions_reconciled: value.deletions_reconciled, ledger_at: value.ledger_at, external_connections_require_review: true }
}
