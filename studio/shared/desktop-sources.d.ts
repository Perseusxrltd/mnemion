export type DesktopSource = {
  id: string; endpoint: string; tenant_id: string; connector_id: string; principal_id: string;
  name: string; provider: 'filesystem' | 'conversations' | 'slack' | 'gdrive'; path?: string; members: string[];
  capture_mode?: 'complete' | 'messages';
  custody?: { source_id: string; grant_id: string; keep_accepted: true; pending_limit_mib: number };
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
  'capture_delivery_unavailable' | 'capture_capacity_blocked' | 'capture_disk_full' |
  'capture_enrollment_missing' | 'capture_integrity_failed' | 'capture_inbox_missing' |
  'capture_key_unavailable' | 'capture_not_initialized' | 'capture_policy_change_requires_migration' |
  'capture_server_upgrade_required' | 'capture_settings_changed' | 'capture_source_changed' |
  'capture_source_unavailable' | 'capture_storage_not_private' | 'capture_storage_unavailable' |
  'capture_event_invalid' | 'capture_event_conflict' | 'capture_checkpoint_invalid' | 'capture_retire_required' | 'capture_retirement_credentials' |
  'capture_prefix_changed' | 'source_changed_during_read' | 'conversation_scan_deadline' |
  'conversation_record_limit' | 'conversation_file_limit' | 'conversation_event_conflict';
export type CaptureReport = {
  locally_accepted: number; pending_events: number; pending_bytes: number;
  remote_committed_events: number; stored_events: number; forgotten_events: number;
  unknown_pages: number; database_bytes: number; over_limit: boolean;
  capture_complete: boolean; delivery_complete: boolean;
  device_pending_bytes: number; device_database_bytes: number; reason_code?: CaptureReason | null;
  coverage?: CaptureCoverage | null;
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
}
export type SourceReason = CaptureReason | 'history_reset' | 'partial' | 'interrupted' | 'source_cancelled' | 'source_timeout' |
  'source_unavailable' | 'source_helper_unavailable' | 'source_invalid_response' |
  'source_identity_mismatch' | 'source_connection_unavailable' | 'source_scope_ambiguous' |
  'source_scope_mismatch' | 'source_conversation_identity_required' | 'source_conversation_copy_unverified' |
  'source_conversation_incomplete_copy' | 'source_settings_changed' | 'source_memory_limit' |
  'source_provider_credentials' | 'provider_access_lost' | 'slack_access_lost' | 'slack_workspace_mismatch' |
  'provider_rate_limited' | 'provider_unavailable' | 'invalid_drive_identity' | 'private_location' |
  'unsafe_location' | 'damaged_state' | 'storage_locked' | 'source_credentials_unavailable' |
  'source_status_invalid' | 'source_status_unconfirmed' | 'source_status_unavailable' | 'source_status_changed'
export type SourceActivity = {
  phase: 'waiting' | 'scanning' | 'paused' | 'complete' | 'attention';
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
}
export type SourceControl = { expected_revision: string; id: string; enabled?: boolean; confirm?: boolean; repair_token?: string; discard_local_inbox?: boolean; retirement_credential?: string }
