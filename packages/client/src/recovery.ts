/** Administrative references only. Entries do not grant host or memory access. */
export interface RecoveryHost {
  id: string; name: string; role: 'primary' | 'recovery' | 'ingestion';
  platform: 'windows' | 'macos' | 'linux' | 'managed' | 'other';
  workspace_url: string | null; operator_url: string | null; operator: string; notes: string;
}
export interface RecoveryMaterial {
  id: string; name: string; kind: 'database_backup' | 'recovery_ledger' | 'source_mirror';
  location: string; access_url: string | null; reported_verified_at: string | null; notes: string;
}
export interface RecoveryContact { id: string; name: string; channel: string; responsibility: string }
export interface RecoveryDirectory {
  instructions: string; independent_url: string | null;
  hosts: RecoveryHost[]; materials: RecoveryMaterial[]; contacts: RecoveryContact[];
}
export interface RecoveryDirectoryRecord {
  tenant_id: string; revision: number; updated_at: string | null; updated_by: string | null;
  directory: RecoveryDirectory;
}
