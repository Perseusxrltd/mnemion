/** A journal exports future native writes to an explicitly approved Git repository. */
export interface JournalDelivery {
  event_id: string
  durability: 'local_journal' | 'remote_git'
  remote_pending: boolean
  external_history_retained: true
}
export interface JournalDestination {
  id: string; label: string; repository: string; branch: string; prefix: string
  personal_data_scan: boolean; custom_scanner: boolean
}
export interface JournalStatus {
  configured: boolean; can_configure: boolean; destination: JournalDestination | null
  version: number
  state: 'not_configured' | 'ready' | 'paused' | 'publisher_unavailable' | 'destination_changed'
  pending_entries: number; pending_content_bytes: number
  external_history_retained: true; existing_memories_backfilled: false
  paused?: boolean | null; interval_seconds?: number | null; publisher_id?: string | null
  last_push_at?: string | null; last_commit?: string | null; last_error?: string | null
  last_entries: number; last_bytes: number
}
export interface JournalPolicyInput {
  expected_version: number; destination_id: string
  publish_to_repository: true; acknowledge_retained_git_history: true
  paused?: boolean; interval_seconds?: number; repair_publisher?: boolean
}

export function supportsJournal(version?: string | null): boolean {
  const parts = version?.match(/^(\d{1,5})\.(\d{1,5})\.(\d{1,5})$/)?.slice(1).map(Number)
  const major = parts?.[0] ?? 0, minor = parts?.[1] ?? 0
  return major > 4 || (major === 4 && minor >= 15)
}
