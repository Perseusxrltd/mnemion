/** Vault values require explicit reads; never place them in memory/query caches. */
export interface VaultEntry {
  id: string; name: string; version: number; access_version: number; created_at: string; updated_at: string;
  permissions: { read: boolean; write: boolean; manage: boolean };
}
export interface VaultStatus {
  configured: boolean; enabled: boolean; mcp_enabled: boolean; available: boolean; error_code: string | null;
  key_id: string | null; required_key_ids: string[]; current_key_id: string; current_person_id: string | null; administrator: boolean;
}
export interface VaultPage<T> { items: T[]; next_offset: number | null }
export interface VaultGrant { subject_kind: 'person' | 'key'; subject_id: string; name: string; read: boolean; write: boolean; active: boolean }
export interface VaultGrants { entry_id: string; access_version: number; items: VaultGrant[] }
export interface VaultGrantInput { expected_access_version: number; subject_kind: 'person' | 'key'; subject_id: string; read?: boolean; write?: boolean; remove?: boolean }
export interface VaultPutInput { expected_version: number; name: string; value: string }
export interface VaultEnvelope { format: 'mnemion-vault-export'; version: 1; key_id: string; nonce: string; ciphertext: string }
export interface VaultAuditEvent { id: string; principal_id: string; key_id: string; entry_id: string | null; action: string; outcome: string; occurred_at: string }
