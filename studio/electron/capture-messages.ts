import type { CaptureArchiveInfo, CaptureCoverage, CaptureIndexCounts, CaptureIndexProgress, CaptureIndexSweep, CapturePreview, CaptureReason, CaptureRecoveries, CaptureRestored, CaptureStorage } from '../shared/desktop-sources.js'

const coverageCounts = ['tracked_scopes', 'checking_scopes', 'failed_scopes', 'missing_scopes',
  'uncertain_scopes', 'unknown_prefix_scopes', 'uncertain_intervals', 'observed_bytes',
  'examined_prefix_bytes', 'unaccepted_observed_bytes', 'unresolved_previous_bytes'] as const
const coverageTimes = ['tracked_from', 'observed_at', 'complete_prefix_at', 'last_contact_at',
  'last_acknowledged_at', 'queue_nonempty_since'] as const
const coverageKeys = [...coverageCounts, ...coverageTimes, 'format', 'capture_mode', 'catalog', 'records', 'history_before_tracking']
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const count = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 0
const timestamp = (value: unknown) => value === null || typeof value === 'string' &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(value) && Number.isFinite(Date.parse(value))
const keys = (value: unknown, names: string[]): value is Record<string, unknown> => object(value) &&
  Object.keys(value).length === names.length && Object.keys(value).every(key => names.includes(key))
const cursor = (value: unknown) => value === null || typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
const uuid = (value: unknown) => typeof value === 'string' && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(value)
export const validCaptureStorage = (value: unknown): value is CaptureStorage => {
  const counts = ['database_bytes', 'reclaimable_bytes', 'reclaimed_bytes']
  if (!keys(value, ['format', 'state', ...counts, 'reason']) || value.format !== 'mnemion-capture-storage-v1' ||
    !['idle', 'reclaimed', 'deferred', 'failed'].includes(String(value.state)) ||
    counts.some(key => !count(value[key]) || (value[key] as number) > 1e12) ||
    (value.reclaimable_bytes as number) > (value.database_bytes as number)) return false
  const deferred = value.state === 'deferred' || value.state === 'failed'
  return (deferred ? ['time_budget', 'byte_budget', 'disk_reserve', 'pending_legacy', 'sqlite_failure'].includes(String(value.reason)) : value.reason === null) &&
    (value.state === 'failed') === (value.reason === 'sqlite_failure') &&
    (value.state !== 'idle' || value.reclaimed_bytes === 0) &&
    (value.state !== 'reclaimed' || (value.reclaimed_bytes as number) > 0)
}
const indexCounts = ['events', 'lexical_indexed', 'vector_indexed', 'waiting', 'failed', 'withheld', 'forgotten', 'unknown']
const validIndexCounts = (value: unknown): value is CaptureIndexCounts => {
  if (!keys(value, indexCounts) || indexCounts.some(key => !count(value[key]))) return false
  const c = value as CaptureIndexCounts
  return c.events === c.vector_indexed + c.waiting + c.failed + c.withheld + c.forgotten + c.unknown &&
    c.lexical_indexed === c.vector_indexed + c.waiting + c.failed
}
const validIndexSweep = (value: unknown): value is CaptureIndexSweep => keys(value,
  ['generation_id', 'inference_paused', 'started_at', 'observed_at', 'pages', 'counts', 'next_cursor']) &&
  typeof value.generation_id === 'string' && /^[a-zA-Z0-9:._-]{1,128}$/.test(value.generation_id) &&
  typeof value.inference_paused === 'boolean' && count(value.pages) && value.pages > 0 &&
  typeof value.started_at === 'string' && timestamp(value.started_at) &&
  typeof value.observed_at === 'string' && timestamp(value.observed_at) &&
  validIndexCounts(value.counts) && cursor(value.next_cursor)
const validIndexProgress = (value: unknown): value is CaptureIndexProgress => keys(value,
  ['status', 'last_attempt_at', 'active', 'completed']) &&
  ['unobserved', 'available', 'unavailable', 'unsupported'].includes(String(value.status)) && timestamp(value.last_attempt_at) &&
  (value.status === 'unobserved' ? value.last_attempt_at === null && value.active === null && value.completed === null : value.last_attempt_at !== null) &&
  (value.active === null || validIndexSweep(value.active) && value.active.next_cursor !== null) &&
  (value.completed === null || validIndexSweep(value.completed) && value.completed.next_cursor === null)

export function readCapturePreview(value: unknown): CapturePreview {
  const records = (item: unknown) => keys(item, ['lines', 'selected', 'omitted', 'unsupported']) &&
    Object.values(item).every(count) && item.lines === (item.selected as number) + (item.omitted as number) + (item.unsupported as number)
  if (!keys(value, ['format', 'configuration_hash', 'policy_revision', 'observed_at', 'capture_mode', 'catalog',
    'visited_entries', 'read_bytes', 'files', 'records', 'file_limit', 'byte_limit', 'attachment_binaries',
    'external_links', 'hidden_reasoning', 'field_redaction', 'automatic_expiry', 'content_saved']) ||
    value.format !== 'mnemion-capture-preview-v1' || typeof value.configuration_hash !== 'string' || !cursor(value.configuration_hash) ||
    !cursor(value.policy_revision) || typeof value.observed_at !== 'string' || !timestamp(value.observed_at) ||
    !['messages', 'complete'].includes(String(value.capture_mode)) || !['complete', 'limited', 'unavailable'].includes(String(value.catalog)) ||
    !count(value.visited_entries) || value.visited_entries > 10000 || !count(value.read_bytes) || value.read_bytes > 1048576 ||
    !Array.isArray(value.files) || value.files.length > 8 || !records(value.records) || value.file_limit !== 8 || value.byte_limit !== 1048576 ||
    value.attachment_binaries !== 'not_read' || value.external_links !== 'not_followed' || value.hidden_reasoning !== 'unavailable' ||
    value.field_redaction !== 'not_supported' || value.automatic_expiry !== 'not_enabled' || value.content_saved !== false) throw new Error('The capture preview could not be verified.')
  for (const file of value.files) {
    if (!keys(file, ['path', 'status', 'file_bytes', 'read_bytes', 'prefix_bytes', 'records']) || typeof file.path !== 'string' ||
      !file.path || file.path.length > 4096 || file.path.startsWith('/') || file.path.split('/').includes('..') || /[\\\x00-\x1f\x7f]/.test(file.path) ||
      !['sampled', 'unreadable', 'changed', 'too_large', 'record_too_large', 'private_control', 'invalid_jsonl'].includes(String(file.status)) ||
      !count(file.file_bytes) || !count(file.read_bytes) || file.read_bytes > 131072 || !count(file.prefix_bytes) ||
      file.prefix_bytes > file.read_bytes || file.prefix_bytes > file.file_bytes || !records(file.records) ||
      file.status !== 'sampled' && (file.prefix_bytes !== 0 || (file.records as { lines: number }).lines !== 0)) throw new Error('The capture preview contains an invalid file observation.')
  }
  const preview = value as CapturePreview
  if (preview.read_bytes !== preview.files.reduce((sum, file) => sum + file.read_bytes, 0) ||
    (['lines', 'selected', 'omitted', 'unsupported'] as const).some(key => preview.records[key] !== preview.files.reduce((sum, file) => sum + file.records[key], 0))) throw new Error('The capture preview counters could not be verified.')
  return preview
}

export function validCaptureCoverage(value: unknown): value is CaptureCoverage {
  if (!object(value) || Object.keys(value).length !== coverageKeys.length + Number(Object.hasOwn(value, 'index')) ||
    Object.keys(value).some(key => !coverageKeys.includes(key) && key !== 'index') || value.format !== 'mnemion-capture-coverage-v1' ||
    Object.hasOwn(value, 'index') && !validIndexProgress(value.index) ||
    !['complete', 'messages'].includes(String(value.capture_mode)) ||
    !['unobserved', 'available', 'unavailable'].includes(String(value.catalog)) || value.history_before_tracking !== 'unknown' ||
    coverageCounts.some(key => !count(value[key])) || coverageTimes.some(key => !timestamp(value[key])) ||
    !object(value.records) || Object.keys(value.records).length !== 4 ||
    ['lines', 'selected', 'omitted', 'unsupported'].some(key => !count((value.records as Record<string, unknown>)[key]))) return false
  const coverage = value as CaptureCoverage
  return coverage.checking_scopes + coverage.failed_scopes + coverage.missing_scopes <= coverage.tracked_scopes &&
    coverage.uncertain_scopes <= coverage.tracked_scopes && coverage.unknown_prefix_scopes <= coverage.tracked_scopes &&
    coverage.examined_prefix_bytes + coverage.unaccepted_observed_bytes === coverage.observed_bytes &&
    coverage.records.lines === coverage.records.selected + coverage.records.omitted + coverage.records.unsupported
}

export function readCaptureArchive(value: unknown): CaptureArchiveInfo {
  if (!keys(value, ['format', 'created_at', 'name', 'binding', 'database_bytes', 'archive_sha256', 'status', 'authenticated', 'workspace_credentials_included', 'source_enrolled']) ||
    value.format !== 'mnemion-capture-archive-v1' || typeof value.created_at !== 'string' || !timestamp(value.created_at) ||
    typeof value.name !== 'string' || !value.name.length || value.name.length > 200 ||
    !count(value.database_bytes) || value.database_bytes < 65536 || value.database_bytes > 2 * 1024 ** 3 ||
    typeof value.archive_sha256 !== 'string' || !cursor(value.archive_sha256) || value.authenticated !== true ||
    value.workspace_credentials_included !== false || value.source_enrolled !== false) throw new Error('The capture archive report could not be verified.')
  const binding = value.binding, status = value.status
  const bindingFields = ['tenant_id', 'connector_id', 'source_id', 'grant_id', 'namespace', 'capture_mode']
  if (!object(binding) || !keys(binding, [...bindingFields, ...(Object.hasOwn(binding, 'capture_policy') ? ['capture_policy'] : [])]) ||
    bindingFields.slice(0, 4).some(name => !uuid(binding[name])) || typeof binding.namespace !== 'string' ||
    !binding.namespace.length || binding.namespace.length > 512 || !['messages', 'complete'].includes(String(binding.capture_mode))) throw new Error('The archived source identity could not be verified.')
  if (Object.hasOwn(binding, 'capture_policy')) {
    const policy = binding.capture_policy
    const patterns = (v: unknown, required: boolean) => Array.isArray(v) && v.length <= 64 && (!required || v.length > 0) && v.every(p => typeof p === 'string' && p.length > 0 && p.length <= 512)
    if (!keys(policy, ['format', 'preset', 'capture_mode', 'include', 'exclude', 'retention', 'max_file_bytes', 'max_record_bytes']) ||
      policy.format !== 'mnemion-capture-policy-v1' || !['selected', 'conversation', 'detailed'].includes(String(policy.preset)) ||
      policy.capture_mode !== binding.capture_mode || policy.retention !== 'until_deleted' || !patterns(policy.include, true) || !patterns(policy.exclude, false) ||
      !count(policy.max_file_bytes) || policy.max_file_bytes < 1 || policy.max_file_bytes > 1e12 ||
      !count(policy.max_record_bytes) || policy.max_record_bytes < 1 || policy.max_record_bytes > 16e6 || policy.max_record_bytes > policy.max_file_bytes) throw new Error('The archived capture policy could not be verified.')
  }
  if (!validInboxStatus(status) || status.database_bytes !== value.database_bytes ||
    status.coverage.capture_mode !== binding.capture_mode) throw new Error('The archived capture status could not be verified.')
  return value as CaptureArchiveInfo
}

function validInboxStatus(status: unknown): status is CaptureArchiveInfo['status'] {
  const counts = ['pending_events', 'pending_bytes', 'database_bytes', 'stored_events', 'forgotten_events', 'unknown_pages']
  return keys(status, ['format', ...counts, 'over_limit', 'coverage']) && status.format === 'mnemion-selected-inbox-v1' &&
    counts.every(name => count(status[name]) && (status[name] as number) <= 1e12) &&
    (status.database_bytes as number) >= 65536 && (status.database_bytes as number) <= 2 * 1024 ** 3 &&
    typeof status.over_limit === 'boolean' && validCaptureCoverage(status.coverage)
}

export function readCaptureRecoveries(value: unknown): CaptureRecoveries {
  if (!keys(value, ['format', 'items']) || value.format !== 'mnemion-capture-recoveries-v1' ||
    !Array.isArray(value.items) || value.items.length > 16) throw new Error('Pending capture recoveries could not be read.')
  const ids = new Set<string>()
  for (const item of value.items) {
    if (!keys(item, ['id', 'name', 'endpoint', 'archive_sha256', 'created_at', 'copy_available']) || !uuid(item.id) ||
      typeof item.name !== 'string' || !item.name.length || item.name.length > 200 ||
      typeof item.endpoint !== 'string' || item.endpoint.length > 2048 ||
      typeof item.archive_sha256 !== 'string' || !cursor(item.archive_sha256) ||
      typeof item.created_at !== 'string' || !timestamp(item.created_at) || typeof item.copy_available !== 'boolean' || ids.has(item.id as string)) throw new Error('A pending capture recovery could not be verified.')
    ids.add(item.id as string)
  }
  return value as CaptureRecoveries
}

export function readCaptureRestored(value: unknown): CaptureRestored {
  if (!keys(value, ['format', 'id', 'archive_sha256', 'previous_grant_id', 'grant_id', 'previous_grant_revoked', 'source_enrolled', 'source_enabled', 'status']) ||
    value.format !== 'mnemion-capture-restored-v1' || !uuid(value.id) || !uuid(value.previous_grant_id) || !uuid(value.grant_id) ||
    value.previous_grant_id === value.grant_id || typeof value.archive_sha256 !== 'string' || !cursor(value.archive_sha256) ||
    value.previous_grant_revoked !== true || value.source_enrolled !== true || typeof value.source_enabled !== 'boolean' ||
    !validInboxStatus(value.status)) throw new Error('Capture restoration could not be confirmed. Inspect pending recoveries before retrying.')
  return value as CaptureRestored
}

export const captureMessages: Record<CaptureReason, string> = {
  capture_authorization_revoked: 'This capture authorization was revoked. Local evidence is retained; no new evidence is accepted under it.',
  capture_binding_mismatch: 'The saved inbox does not match this source authorization. Its data was retained for recovery.',
  capture_binding_invalid: 'Review the workspace, source and device capture authorization.',
  capture_delivery_unavailable: 'The workspace could not confirm delivery. Locally accepted memories remain queued for a later attempt.',
  capture_capacity_blocked: 'The local inbox reached a configured limit. Accepted memories are retained; new intake waits for capacity.',
  capture_disk_full: 'The device needs more free disk space. Accepted memories are retained.',
  capture_enrollment_missing: 'The protected capture enrollment is missing. Restore its matching settings and inbox; a new inbox was not created.',
  capture_integrity_failed: 'The inbox key or encrypted data could not be verified. Existing data was retained for recovery.',
  capture_inbox_missing: 'An initialized inbox is missing. Restore its matching encrypted backup before resuming.',
  capture_key_unavailable: 'Unlock or restore this inbox’s separate protected key. Capture has stopped.',
  capture_not_initialized: 'The source has not completed its first local inbox initialization.',
  capture_policy_change_requires_migration: 'This change needs a reviewed capture migration. Existing source mirrors, capture selection and inbox identities are retained.',
  capture_server_upgrade_required: 'Update the workspace server to a version supporting retained conversation capture.',
  capture_settings_changed: 'Capture settings changed. Refresh source status before retrying.',
  capture_source_changed: 'The selected folder identity changed. Queued memories remain deliverable; verify the replacement before accepting new data.',
  capture_source_unavailable: 'The selected chat folder is unavailable. Previously accepted memories remain queued and can still be delivered.',
  capture_storage_not_private: 'The inbox storage is not private to this OS account. Its data was retained.',
  capture_storage_unavailable: 'The local inbox could not be read or written. Check storage and restore the matching inbox if needed.',
  capture_event_invalid: 'A selected record failed validation. No unverified evidence was accepted.',
  capture_event_conflict: 'A saved event conflicts with the selected evidence. Review the producer before resuming.',
  capture_checkpoint_invalid: 'The captured file position could not be verified. Earlier accepted evidence was retained.',
  capture_retire_required: 'Pause this source and confirm removal of its local inbox. The server must confirm device-grant revocation before removal can finish.',
  capture_retirement_credentials: 'The saved device key could not confirm removal. Connect as an administrator of this workspace or supply its administrator key in Sources on this computer. Local evidence was retained.',
  capture_prefix_changed: 'The chat file changed during capture. Its last accepted position was retained for the next attempt.',
  source_changed_during_read: 'The chat file changed during capture. Its last accepted position was retained for the next attempt.',
  conversation_scan_deadline: 'The chat scan reached its time allowance. Earlier accepted evidence was retained.',
  conversation_record_limit: 'A chat record exceeds the selected capture limit. Earlier accepted evidence was retained.',
  conversation_file_limit: 'The source exceeds its selected file limit. Narrow the folder or adjust its limits.',
  conversation_event_conflict: 'The producer reused an event identity with different content. Review the source before resuming.',
}
