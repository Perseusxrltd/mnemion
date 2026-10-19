/** Complete native journal recovery creates no source principals or permissions. */
export interface JournalRecoveryInput {
  identity_mode?: 'original' | 'copy'
  catalog: string
  files: { path: string; text: string }[]
  withdrawn_ids: string[]
  reject_personal_data?: boolean
}
export interface JournalRecoveryApply extends JournalRecoveryInput {
  preview_sha256: string
  reviewed_complete_inventory: true
  reviewed_withdrawals: true
  acknowledge_source_only: true
}
export interface JournalRecoveryItem {
  original_id: string; memory_id: string; source_version?: number | null
  version?: number | null; code?: string | null
  action: 'create' | 'already_restored' | 'preserved_changes' | 'stale_source' | 'withdraw' | 'deny' | 'withdrawn' | 'hold' | 'quarantine' | 'held' | 'release' | 'update' | 'conflict' | 'rejected'
}
export interface JournalRecoveryReceipt {
  identity_mode: 'original' | 'copy'
  namespace: string; space_id: string; preview_sha256: string
  counts: Partial<Record<JournalRecoveryItem['action'], number>>
  items: JournalRecoveryItem[]
  source_only: true; remote_delivery_verified: false
}
export interface JournalRecoveryPreview extends JournalRecoveryReceipt {
  input_sha256: string; can_restore: boolean; records: number; duplicates: number; bytes: number
}
export function supportsJournalRecovery(version?: string | null): boolean {
  const parts = version?.match(/^(\d{1,5})\.(\d{1,5})\.(\d{1,5})$/)?.slice(1).map(Number)
  const major = parts?.[0] ?? 0, minor = parts?.[1] ?? 0
  return major > 4 || (major === 4 && minor >= 26)
}
