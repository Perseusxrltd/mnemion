import type { JournalRecoveryItem } from './journal-recovery.js'

export const JOURNAL_CHUNK_BYTES = 256 * 1024
export interface JournalUploadInput {
  catalog: string; files: { path: string; bytes: number }[]; withdrawn_ids: string[]
  identity_mode?: 'original' | 'copy'; reject_personal_data?: boolean
}
export interface JournalUploadStatus {
  id: string; space_id: string; version: number
  state: 'uploading' | 'reviewing' | 'reviewed' | 'restoring' | 'completed' | 'cancelled'
  identity_mode: 'original' | 'copy'; namespace: string; reject_personal_data: boolean
  input_sha256: string; preview_sha256: string | null; can_restore: boolean
  bytes: number; received: number; files: number; completed_files: number
  records: number; expected_records: number; physical_records: number; duplicates: number
  identities: number; reviewed_identities: number; processed_identities: number
  reviewed_batches: number; applied_batches: number
  counts: Partial<Record<JournalRecoveryItem['action'], number>>
  applied_counts: Partial<Record<JournalRecoveryItem['action'], number>>
  created_at: string; updated_at: string; expires_at: string; chunk_bytes: number
  source_only: true; remote_delivery_verified: false
}
export interface JournalUploadFile {
  index: number; path: string; bytes: number; received: number; transport_sha256: string; complete: boolean
}
export interface JournalUploadFiles { items: JournalUploadFile[]; next_cursor: number | null }
export interface JournalUploadDecisions { items: JournalRecoveryItem[]; next_cursor: number | null }
export interface JournalUploadChunk { offset: number; sha256: string; data: string }
export interface JournalUploadChunkReceipt { upload: JournalUploadStatus; file: JournalUploadFile; repeated: boolean }
export interface JournalUploadAdvance {
  expected_version: number; action: 'finish_upload' | 'review' | 'restart_review' | 'authorize' | 'restore' | 'cancel'
  preview_sha256?: string | null; reviewed_complete_inventory?: boolean; reviewed_withdrawals?: boolean
  acknowledge_source_only?: boolean; acknowledge_resumable_batches?: boolean
}
export function supportsJournalUploads(version?: string | null): boolean {
  const parts = version?.match(/^(\d{1,5})\.(\d{1,5})\.(\d{1,5})$/)?.slice(1).map(Number)
  const major = parts?.[0] ?? 0, minor = parts?.[1] ?? 0
  return major > 4 || (major === 4 && minor >= 29)
}

const hex = (data: ArrayBuffer) => Array.from(new Uint8Array(data), byte => byte.toString(16).padStart(2, '0')).join('')
export async function journalChunk(data: ArrayBuffer, offset: number): Promise<JournalUploadChunk> {
  if (!Number.isSafeInteger(offset) || offset < 0 || data.byteLength < 1 || data.byteLength > JOURNAL_CHUNK_BYTES) throw new Error('Use one bounded journal chunk.')
  // Avoid spreading a large typed array onto the JavaScript call stack.
  const bytes = new Uint8Array(data)
  let binary = ''
  for (let start = 0; start < bytes.length; start += 8192) binary += String.fromCharCode(...bytes.subarray(start, start + 8192))
  return { offset, sha256: hex(await crypto.subtle.digest('SHA-256', data)), data: btoa(binary) }
}
export async function journalTransportDigest(previous: string, offset: number, data: ArrayBuffer): Promise<string> {
  if (!/^[a-f0-9]{64}$/.test(previous) || !Number.isSafeInteger(offset) || offset < 0 || data.byteLength > JOURNAL_CHUNK_BYTES) throw new Error('Invalid journal transport receipt.')
  const combined = new Uint8Array(80), view = new DataView(combined.buffer)
  for (let i = 0; i < 32; i++) combined[i] = Number.parseInt(previous.slice(i * 2, i * 2 + 2), 16)
  view.setBigUint64(32, BigInt(offset)); view.setBigUint64(40, BigInt(data.byteLength))
  combined.set(new Uint8Array(await crypto.subtle.digest('SHA-256', data)), 48)
  return hex(await crypto.subtle.digest('SHA-256', combined))
}

/** Verify the original prefix locally before appending any bytes after a pause. */
export async function verifyJournalPrefix(source: Blob, receipt: JournalUploadFile, cancelled: () => boolean = () => false): Promise<boolean> {
  if (source.size !== receipt.bytes || receipt.received > source.size || receipt.received < 0) throw new Error('The selected journal file length changed. Select the original folder.')
  let chain = '0'.repeat(64)
  for (let offset = 0; offset < receipt.received; offset += JOURNAL_CHUNK_BYTES) {
    if (cancelled()) return false
    chain = await journalTransportDigest(chain, offset, await source.slice(offset, Math.min(offset + JOURNAL_CHUNK_BYTES, receipt.received)).arrayBuffer())
  }
  if (chain !== receipt.transport_sha256) throw new Error('This file differs from the accepted upload. Select the original folder or start a new recovery.')
  return !cancelled()
}
