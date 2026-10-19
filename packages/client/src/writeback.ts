/** Future native writes are captured by policy; older memories need separate backfill approval. */
export type JournalDestinationKind = 'local_repository' | 'https_repository' | 'ssh_repository'
export interface JournalDelivery {
  event_id: string
  durability: 'local_journal' | 'remote_git'
  remote_pending: boolean
  /** Missing on older receipts. remote_git acknowledges this destination, not every replica. */
  destination_kind?: JournalDestinationKind | null
  external_history_retained: true
}
export interface JournalDestination {
  id: string; label: string; repository: string; branch: string; prefix: string
  personal_data_scan: boolean; custom_scanner: boolean
  destination_kind?: JournalDestinationKind
}
export interface JournalStatus {
  configured: boolean; can_configure: boolean; destination: JournalDestination | null
  version: number
  state: 'not_configured' | 'ready' | 'paused' | 'publisher_unavailable' | 'destination_changed'
  pending_entries: number; pending_content_bytes: number
  external_history_retained: true
  /** Legacy enablement flag: enabling the journal alone never backfills. Use journalBackfillStatus for coverage. */
  existing_memories_backfilled: false
  paused?: boolean | null; interval_seconds?: number | null; publisher_id?: string | null
  last_push_at?: string | null; last_commit?: string | null; last_error?: string | null
  last_entries: number; last_bytes: number
  can_organize?: boolean; notes_prefix?: string | null; fold_enabled?: boolean
  fold_after_hours?: number | null; fold_interval_seconds?: number | null
  next_fold_at?: string | null; last_fold_at?: string | null; last_fold_commit?: string | null
  last_fold_error?: string | null; last_fold_notes?: number; last_fold_archived_files?: number
  last_fold_pending_notes?: number; last_fold_pending_files?: number
  last_fold_read_bytes?: number; last_fold_written_bytes?: number
}
export interface JournalPolicyInput {
  expected_version: number; destination_id: string
  publish_to_repository: true; acknowledge_retained_git_history: true
  paused?: boolean; interval_seconds?: number; repair_publisher?: boolean
  fold_enabled?: boolean; fold_after_hours?: number; fold_interval_seconds?: number
}

export interface JournalBackfillRun {
  id: string; policy_version: number
  state: 'running' | 'paused' | 'blocked' | 'completed' | 'cancelled'
  cutoff_at: string; total_at_start: number; examined: number; queued: number
  already_journaled: number; excluded: number; rejected: number; content_bytes: number
  errors: { memory_id: string; version: number; code: string }[]
  last_error: string | null; started_at: string; updated_at: string; finished_at: string | null
}
export interface JournalBackfillStatus {
  policy_version: number; eligible_memories: number; eligible_content_bytes: number
  waiting_reason: string | null; run: JournalBackfillRun | null
}
export interface JournalBackfillStart {
  expected_version: number; publish_existing_memories: true
  acknowledge_retained_git_history: true; resume_run?: string | null
}
export interface JournalBackfillControl {
  expected_version: number; run_id: string; action: 'pause' | 'cancel'
}

export function supportsJournal(version?: string | null): boolean {
  const parts = version?.match(/^(\d{1,5})\.(\d{1,5})\.(\d{1,5})$/)?.slice(1).map(Number)
  const major = parts?.[0] ?? 0, minor = parts?.[1] ?? 0
  return major > 4 || (major === 4 && minor >= 15)
}

export function supportsJournalFolding(version?: string | null): boolean {
  const parts = version?.match(/^(\d{1,5})\.(\d{1,5})\.(\d{1,5})$/)?.slice(1).map(Number)
  const major = parts?.[0] ?? 0, minor = parts?.[1] ?? 0
  return major > 4 || (major === 4 && minor >= 16)
}

export function supportsJournalBackfill(version?: string | null): boolean {
  const parts = version?.match(/^(\d{1,5})\.(\d{1,5})\.(\d{1,5})$/)?.slice(1).map(Number)
  const major = parts?.[0] ?? 0, minor = parts?.[1] ?? 0
  return major > 4 || (major === 4 && minor >= 22)
}
