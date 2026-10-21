import type { CaptureCoverage, CaptureIndexCounts, CaptureIndexProgress, CaptureIndexSweep, CaptureReason } from '../shared/desktop-sources.js'

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
