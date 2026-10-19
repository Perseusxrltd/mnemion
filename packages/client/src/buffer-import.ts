/** Reviewed source recovery never infers original permissions or remote delivery. */
export interface BufferPreviewInput {
  namespace: string
  jsonl: string
  withdrawn_ids: string[]
  reject_personal_data?: boolean
}
export interface BufferImportInput extends BufferPreviewInput {
  preview_sha256: string
  reviewed_withdrawals: true
  acknowledge_source_only: true
}
export interface BufferPlanItem {
  legacy_id: string; memory_id: string; version?: number | null; code?: string | null
  action: 'create' | 'already_imported' | 'preserved_changes' | 'withdrawn' | 'withdraw' | 'deny' | 'conflict' | 'rejected'
}
export interface BufferImported {
  namespace: string; space_id: string; preview_sha256: string
  counts: Partial<Record<BufferPlanItem['action'], number>>; items: BufferPlanItem[]
  source_only: true; remote_delivery_verified: false
}
export interface BufferPreview extends BufferImported {
  input_sha256: string; can_import: boolean; duplicates: number; writers: string[]
}
export function supportsBufferImport(version?: string | null): boolean {
  const parts = version?.match(/^(\d{1,5})\.(\d{1,5})\.(\d{1,5})$/)?.slice(1).map(Number)
  const major = parts?.[0] ?? 0, minor = parts?.[1] ?? 0
  return major > 4 || (major === 4 && minor >= 25)
}
