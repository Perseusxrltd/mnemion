/** Vault values require explicit reads; never place them in memory/query caches. */
export interface VaultEntry {
  id: string; name: string; version: number; access_version: number; created_at: string; updated_at: string;
  permissions: { read: boolean; write: boolean; manage: boolean };
}
export interface VaultStatus {
  configured: boolean; enabled: boolean; mcp_enabled: boolean; available: boolean; error_code: string | null;
  mcp_metadata_enabled?: boolean; metadata_available?: boolean; audit_access?: boolean;
  key_id: string | null; required_key_ids: string[]; current_key_id: string; current_person_id: string | null; administrator: boolean;
}
export interface VaultPage<T> { items: T[]; next_offset: number | null }
export interface VaultGrant { subject_kind: 'person' | 'key'; subject_id: string; name: string; read: boolean; write: boolean; active: boolean }
export interface VaultGrants { entry_id: string; access_version: number; items: VaultGrant[] }
export interface VaultGrantInput { expected_access_version: number; subject_kind: 'person' | 'key'; subject_id: string; read?: boolean; write?: boolean; remove?: boolean }
export interface VaultPutInput { expected_version: number; name: string; value: string }
export interface VaultEnvelope { format: 'mnemion-vault-export'; version: 1; key_id: string; nonce: string; ciphertext: string }
export interface VaultAuditEvent { id: string; principal_id: string; key_id: string; entry_id: string | null; target_key_id?: string | null; action: string; outcome: string; occurred_at: string }
export interface VaultAuditor { key_id: string; principal_id: string; name: string; version: number; enabled: boolean; expires_at: string | null; active: boolean; created_at: string; updated_at: string }
export interface VaultAuditorInput { expected_version: number; enabled: boolean; expires_at?: string | null }
export interface KeepassPreviewInput { file: string; password?: string | null; key_file?: string | null; namespace?: string; mask_names?: boolean }
export interface KeepassImportInput extends KeepassPreviewInput { expected_plan: string; import_current_values: true }
export interface KeepassPreview {
  plan: string; entries: number; credentials: number; empty_fields: number; names: string[]; mask_names: boolean;
  omitted: { history_entries: number; attachments: number; recycled_entries: number };
  name_conflicts: number; can_import: boolean; already_imported: boolean;
}
export interface KeepassImported { items: VaultEntry[]; already_imported: boolean }
export interface KeepassExported { format: 'kdbx'; version: '4.1'; file: string; sha256: string; credentials: number; entries: number }
export function supportsKeePass(version?: string | null): boolean {
  const parts = /^(\d+)\.(\d+)\.(\d+)(?:$|[-+])/.exec(version ?? '');
  return !!parts && (Number(parts[1]) > 4 || Number(parts[1]) === 4 && Number(parts[2]) >= 23);
}
