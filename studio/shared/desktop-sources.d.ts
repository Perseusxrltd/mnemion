import type { CapturePolicy } from '../../packages/client/dist/capture.js'
export type { CapturePolicy } from '../../packages/client/dist/capture.js'

export type DesktopSource = {
  id: string; endpoint: string; tenant_id: string; connector_id: string; principal_id: string;
  name: string; provider: 'filesystem' | 'conversations' | 'slack' | 'gdrive'; path?: string; members: string[];
  capture_mode?: 'complete' | 'messages';
  capture_policy?: CapturePolicy;
  custody?: { source_id: string; grant_id: string; keep_accepted: true; pending_limit_mib: number;
    history_limit_events?: number; database_limit_mib?: number };
  scope_id?: string;
  slack?: { team_id: string; channels: string[]; include_threads: boolean };
  gdrive?: { folder_ids: string[]; file_ids: string[]; recursive: boolean };
  publish_to_mapped_members: true; poll_seconds: number; memory_limit_mib: number; max_files: number; enabled: boolean;
}
export type SourceReport = {
  completed: boolean; timestamp: string; duration_seconds: number; changed: number; removed: number;
  unchanged: number; conflicts: number; remote_sync_available: boolean;
  capture?: CaptureReport;
}
export type CaptureReason = 'capture_authorization_revoked' | 'capture_binding_mismatch' | 'capture_binding_invalid' |
  'capture_delivery_unavailable' | 'capture_delivery_pending' | 'capture_capacity_blocked' | 'capture_fence_capacity' | 'capture_scan_pending' | 'capture_disk_full' |
  'capture_enrollment_missing' | 'capture_integrity_failed' | 'capture_inbox_missing' |
  'capture_key_unavailable' | 'capture_not_initialized' | 'capture_policy_change_requires_migration' | 'capture_recovery_pending' |
  'capture_server_upgrade_required' | 'capture_settings_changed' | 'capture_source_changed' |
  'capture_source_unavailable' | 'capture_storage_not_private' | 'capture_storage_unavailable' |
  'capture_event_invalid' | 'capture_event_conflict' | 'capture_checkpoint_invalid' | 'capture_retire_required' | 'capture_retirement_credentials' |
  'capture_prefix_changed' | 'source_changed_during_read' | 'conversation_scan_deadline' |
  'conversation_record_limit' | 'conversation_file_limit' | 'conversation_event_conflict' | 'conversation_field_selection_limit';
export type CaptureReport = {
  locally_accepted: number; pending_events: number; pending_bytes: number;
  remote_committed_events: number; stored_events: number; forgotten_events: number;
  newly_stored_events?: number | null;
  unknown_pages: number; database_bytes: number; over_limit: boolean;
  capture_complete: boolean; delivery_complete: boolean;
  device_pending_bytes: number; device_database_bytes: number; reason_code?: CaptureReason | null;
  coverage?: CaptureCoverage | null;
  storage?: CaptureStorage | null;
  history?: CaptureHistory | null;
}
export type CaptureHistory = {
  format: 'mnemion-capture-history-v1'; events: number; producer_events: number; fragments: number;
  scopes: number; delivery_pages: number; denials: number; event_limit: number; scope_limit: number;
  database_bytes: number; database_limit_bytes: number; fence_history_blocked: boolean; over_limit: boolean;
}
export type CaptureStorage = {
  format: 'mnemion-capture-storage-v1'; state: 'idle' | 'reclaimed' | 'deferred' | 'failed';
  database_bytes: number; reclaimable_bytes: number; reclaimed_bytes: number;
  reason: 'time_budget' | 'byte_budget' | 'disk_reserve' | 'pending_legacy' | 'sqlite_failure' | null;
}
export type CaptureCoverage = {
  format: 'mnemion-capture-coverage-v1'; catalog: 'unobserved' | 'available' | 'unavailable';
  capture_mode: 'complete' | 'messages';
  tracked_scopes: number; checking_scopes: number; failed_scopes: number; missing_scopes: number;
  uncertain_scopes: number; unknown_prefix_scopes: number; uncertain_intervals: number;
  observed_bytes: number; examined_prefix_bytes: number; unaccepted_observed_bytes: number;
  unresolved_previous_bytes: number;
  records: { lines: number; selected: number; omitted: number; unsupported: number };
  tracked_from: string | null; observed_at: string | null; complete_prefix_at: string | null;
  last_contact_at: string | null; last_acknowledged_at: string | null; queue_nonempty_since: string | null;
  history_before_tracking: 'unknown';
  index?: CaptureIndexProgress;
}
export type CaptureIndexCounts = {
  events: number; lexical_indexed: number; vector_indexed: number; waiting: number;
  failed: number; withheld: number; forgotten: number; unknown: number;
}
export type CaptureIndexSweep = {
  generation_id: string; inference_paused: boolean; started_at: string; observed_at: string;
  pages: number; counts: CaptureIndexCounts; next_cursor: string | null;
}
export type CaptureIndexProgress = {
  status: 'unobserved' | 'available' | 'unavailable' | 'unsupported';
  last_attempt_at: string | null; active: CaptureIndexSweep | null; completed: CaptureIndexSweep | null;
}
export type SourceReason = CaptureReason | 'history_reset' | 'partial' | 'interrupted' | 'source_cancelled' | 'source_timeout' |
  'source_preview_required' | 'capture_backup_unavailable' |
  'source_unavailable' | 'source_helper_unavailable' | 'source_invalid_response' |
  'source_identity_mismatch' | 'source_connection_unavailable' | 'source_scope_ambiguous' |
  'source_scope_mismatch' | 'source_conversation_identity_required' | 'source_conversation_copy_unverified' |
  'source_conversation_incomplete_copy' | 'source_settings_changed' | 'source_memory_limit' |
  'source_provider_credentials' | 'provider_access_lost' | 'slack_access_lost' | 'slack_workspace_mismatch' |
  'provider_rate_limited' | 'provider_unavailable' | 'invalid_drive_identity' | 'private_location' |
  'unsafe_location' | 'damaged_state' | 'storage_locked' | 'source_credentials_unavailable' |
  'source_status_invalid' | 'source_status_unconfirmed' | 'source_status_unavailable' | 'source_status_changed'
export type SourceActivity = {
  phase: 'waiting' | 'scanning' | 'paused' | 'backfill' | 'complete' | 'attention';
  message?: string; report?: SourceReport; next_scan_at?: string;
  durability?: 'saved' | 'unavailable' | 'unknown'; reason_code?: SourceReason;
  started_at?: string; finished_at?: string; last_success_report?: SourceReport;
  last_failure?: { observed_at: string; reason_code: SourceReason };
  repair_token?: string;
}
export type DesktopSourceView = {
  revision: string; secure_storage: boolean; running: boolean; memory_bytes: number;
  sources: Array<DesktopSource & { activity: SourceActivity }>;
}
export type SourceConfigure = {
  expected_revision: string; source: Omit<DesktopSource, 'id'> & { id?: string }; credential?: string;
  provider_credential?: string;
  preview_hash?: string;
}
export type SourcePreviewSelection = {
  path: string; capture_mode: 'messages' | 'complete'; capture_policy?: CapturePolicy | null;
  keep_accepted: boolean; memory_limit_mib: number; max_files: number; pending_limit_mib: number;
  history_limit_events?: number; database_limit_mib?: number;
}
export type CapturePreviewFile = {
  path: string; status: 'sampled' | 'unreadable' | 'changed' | 'too_large' | 'record_too_large' | 'private_control' | 'invalid_jsonl' | 'field_selection_limit';
  file_bytes: number; read_bytes: number; prefix_bytes: number;
  records: { lines: number; selected: number; omitted: number; unsupported: number };
}
export type CapturePreview = {
  format: 'mnemion-capture-preview-v1'; configuration_hash: string; policy_revision: string | null;
  observed_at: string; capture_mode: 'messages' | 'complete'; catalog: 'complete' | 'limited' | 'unavailable';
  visited_entries: number; read_bytes: number; files: CapturePreviewFile[];
  records: CapturePreviewFile['records']; file_limit: 8; byte_limit: 1048576;
  attachment_binaries: 'not_read'; external_links: 'not_followed'; hidden_reasoning: 'unavailable';
  field_redaction: 'not_supported' | 'disabled' | 'json_field_names'; automatic_expiry: 'not_enabled' | 'server_scheduled'; retention_days?: number; content_saved: false;
}
export type SourceControl = { expected_revision: string; id: string; enabled?: boolean; confirm?: boolean; repair_token?: string; discard_local_inbox?: boolean; retirement_credential?: string }
export type CaptureArchiveInfo = {
  format: 'mnemion-capture-archive-v1'; created_at: string; name: string;
  binding: { tenant_id: string; connector_id: string; source_id: string; grant_id: string;
    namespace: string; capture_mode: 'messages' | 'complete'; capture_policy?: CapturePolicy };
  database_bytes: number; archive_sha256: string; authenticated: true;
  workspace_credentials_included: false; source_enrolled: false;
  status: { format: 'mnemion-selected-inbox-v1'; pending_events: number; pending_bytes: number;
    database_bytes: number; over_limit: boolean; stored_events: number; forgotten_events: number;
    unknown_pages: number; coverage: CaptureCoverage; history?: CaptureHistory };
}
export type CaptureBackupInput = { expected_revision: string; id: string; file: string; recovery_key: string; confirm: true }
export type CaptureInspectInput = { file: string; recovery_key: string }
export type CaptureRestoreInput = CaptureInspectInput & {
  expected_revision: string; archive_sha256: string; source: SourceConfigure['source'];
  credential: string; retirement_credential: string; preview_hash: string; confirm: true;
  policy_change?: true; replace_id?: string;
}
export type CaptureRecovery = { id: string; name: string; endpoint: string; archive_sha256: string; created_at: string; copy_available: boolean; policy_change?: true; previous_grant_revoked?: boolean }
export type CaptureRecoveries = { format: 'mnemion-capture-recoveries-v1'; items: CaptureRecovery[] }
export type CaptureRestoreControl = { id: string; expected_revision: string; confirm: true; file?: string; recovery_key?: string; retirement_credential?: string }
export type CaptureRestored = {
  format: 'mnemion-capture-restored-v1'; id: string; archive_sha256: string;
  previous_grant_id: string; grant_id: string; previous_grant_revoked: true;
  source_enrolled: true; source_enabled: boolean; status: CaptureArchiveInfo['status'];
  policy_change?: true; replaced_source_id?: string;
}
export type CaptureRestoreResult = { view: DesktopSourceView; recovery: CaptureRestored }
export type CaptureDrainInput = { id: string; expected_revision: string; confirm: true }
export type CaptureDrained = { format: 'mnemion-capture-drained-v1'; id: string; source_enabled: false;
  remote_committed_events: number; delivery_complete: boolean; status: CaptureArchiveInfo['status'] }
