export type MemoryOptions = { mode: 'auto'; limit_mib: null } | { mode: 'manual'; limit_mib: number }
export type MemoryChange = MemoryOptions & { expected_revision?: string }
export type MemoryRepair = MemoryOptions & { repair_token: string }
export type MemoryWrite = MemoryChange | MemoryRepair
export type PortChange = { workspace_id: string; expected_port: number; port: number | null }
export type RemoteMode = 'disabled' | 'ngrok' | 'proxy'
export type RemoteChange = {
  workspace_id: string; expected_revision: string; mode: RemoteMode; public_url: string | null;
  personal_sign_in: boolean; ngrok_authtoken?: string | null;
}
export type RemoteCheck = Pick<RemoteChange, 'workspace_id' | 'expected_revision'>
export type RemoteAccess = {
  mode: RemoteMode; public_url: string | null; personal_sign_in: boolean; has_ngrok_authtoken: boolean;
  revision: string; repairable: boolean;
  state: 'disabled' | 'unchecked' | 'stopped' | 'configuration_error' | 'connecting' | 'online' | 'unavailable';
  message: string; checked_at?: string | null; verified_at?: string | null; provider_code?: string | null;
}
export type CompanyProviderSettings = {
  id: string; name: string; issuer: string; authorization_url: string; token_url: string;
  jwks_url: string; client_id: string; session_seconds: number;
}
export type CompanyRequest = { workspace_id: string; expected_revision: string; expected_remote_revision: string }
export type CompanyChange = CompanyRequest & (
  { action: 'save'; provider: CompanyProviderSettings; client_secret?: string | null; clear_client_secret?: boolean; ca_pem?: string | null } |
  { action: 'remove'; provider_id: string } | { action: 'reset' }
)
export type CompanyDiscoveryRequest = CompanyRequest & { issuer: string; ca_pem?: string | null }
export type CompanyDiscoveryResult = CompanyRequest & Pick<CompanyProviderSettings, 'issuer' | 'authorization_url' | 'token_url' | 'jwks_url'>
export type CompanyAccess = {
  revision: string; repairable: boolean; state: 'disabled' | 'configured' | 'needs_remote' | 'configuration_error' | 'external';
  message: string; callback_uri: string | null; has_custom_ca: boolean;
  providers: Array<CompanyProviderSettings & { has_client_secret: boolean }>;
}
export type VaultRequest = { workspace_id: string; expected_revision: string }
export type VaultChange = VaultRequest & { action: 'configure' | 'restore'; enabled: boolean; mcp_enabled: boolean; recovery_key?: string; key_saved?: boolean }
export type VaultAccess = { revision: string; repairable: boolean; state: 'not_configured' | 'configured' | 'disabled' | 'configuration_error' | 'external'; enabled: boolean; mcp_enabled: boolean; key_id: string | null; message: string }
export type VaultKey = { workspace_id: string; revision: string; key_id: string; recovery_key: string }
export type MemoryRecovery = { code: 'memory_policy_missing' | 'memory_policy_damaged' | 'memory_policy_inaccessible'; message: string; repair_token: string | null }
export type MemorySnapshot = {
  mode: 'auto' | 'manual'; requested_limit_mib: number | null; revision: string;
  target_bytes: number; used_bytes: number; engine_bytes: number; database_bytes: number; desktop_bytes: number;
  effective_hardware_bytes: number; available_hardware_bytes: number; system_reserve_bytes: number;
  os_memory_limit_bytes: number | null; measurement_complete: boolean;
  measurement: 'sum_of_process_resident_sets'; scope: 'local_engine_database_and_reported_desktop';
  enforcement: 'cooperative'; state: 'normal' | 'constrained' | 'paused'; reason: string | null;
  background_paused: boolean; indexing_paused: boolean; minimum_model_budget_bytes: number;
  batch_size: number; rejected_inferences: number; model_evictions: number;
}
export type LocalOptions = {
  workspace_name: string; owner_name: string; embedding_profile: 'e5-small' | 'bge-small-en';
  threads: number; port: number; memory: MemoryOptions;
}
export type LocalResources = {
  memory_bytes: number; available_memory_bytes: number; available_disk_bytes: number;
  effective_memory_bytes: number; effective_available_memory_bytes: number;
  recommended_budget_bytes: number; system_reserve_bytes: number; recommended_profile: LocalOptions['embedding_profile'];
  cpu_threads: number; platform: string; architecture: string; desktop_architecture?: string; gpu_required: boolean;
  minimum_free_disk_bytes: number;
  remote_access?: { ngrok_sdk: string; existing_https_proxy: boolean };
  profiles: Array<{ id: string; label: string; languages: string; minimum_available_memory_bytes: number }>;
}
export type MemoryPolicy = { format: 1; revision: string; updated_at?: string; settings: MemoryOptions }
export type LocalInfo = {
  configured: boolean; data_directory: string; engine_version: string; resources: LocalResources;
  settings?: LocalOptions & { workspace_id: string; created_at: string; database_port: number };
  last_verification?: { verified_at: string; generation_id: string; engine_version: string; semantic_index: boolean };
  memory_policy?: MemoryPolicy | null; memory_recovery?: MemoryRecovery | null; memory?: MemorySnapshot | null;
  remote_access?: RemoteAccess;
  company_access?: CompanyAccess;
  vault_access?: VaultAccess;
}
export type LocalStatus = {
  available: boolean; state: 'new' | 'starting' | 'running' | 'stopping' | 'stopped' | 'error';
  stage?: string; message: string; info?: LocalInfo; errorCode?: string; memory?: MemorySnapshot;
  preferences?: { selected: boolean; startWithApp: boolean; recoveryRoot?: string; originalAvailable?: boolean };
  diagnostic?: LocalDiagnostic;
  backup?: BackupActivity;
  operator?: DesktopOperatorStatus;
}
export type DesktopOperatorStatus = {
  state: 'starting' | 'ready' | 'unavailable'; message: string; control_directory: string;
  command: { executable: string; arguments: string[] };
}
export type BackupAction = 'backup' | 'backup-ledger' | 'backup-inspect' | 'backup-restore' | 'backup-inventory' | 'backup-prune';
export type BackupActivity = {
  action: BackupAction; state: 'running' | 'cancelling' | 'complete' | 'cancelled' | 'error';
  stage: string; message: string; started_at: string; finished_at?: string;
}
export type BackupFile = { file: string; bytes: number; sha256: string; key_id: string; authenticated: true };
export type BackupReceipt = {
  format: 1; operation_id: string; workspace_id: string; scope: 'complete_local_database';
  tenant_count: number; ledger_at: string; application_version: string; verified_at: string;
  snapshot?: BackupFile & { backup_id: string; snapshot_at: string; memory_count: number };
  ledger: BackupFile;
  retention?: BackupRetentionResult; retention_warning?: string;
}
export type BackupRetentionPolicy = { mode: 'keep_all' | 'limited'; snapshots: number; ledgers: number };
export type BackupInventory = {
  format: 1; workspace_id: string; key_id: string; folder: string; policy: BackupRetentionPolicy;
  state: 'keep_all' | 'untracked' | 'ready' | 'insufficient_recovery'; message: string; plan_token: string;
  tracked_snapshots: number; tracked_ledgers: number; tracked_bytes: number; other_key_files: number;
  candidate_files: number; candidate_bytes: number; batch_files: number; batch_bytes: number; recent_limit: number;
  recent: Array<{ name: string; kind: 'snapshot' | 'ledger'; key_id: string; bytes: number; verified_at: string;
    availability: 'present' | 'missing' | 'changed' | 'unavailable'; protected: boolean }>;
};
export type BackupRetentionResult = {
  format: 1; workspace_id: string; key_id: string; folder: string; policy: BackupRetentionPolicy;
  state: 'complete' | 'partial' | 'blocked' | 'cancelled'; message: string; completed_at: string;
  deleted_files: number; deleted_bytes: number; skipped_files: number; remaining_candidates: number;
};
export type BackupOperationResult = BackupReceipt | BackupInspectionData | RecoveryReceipt | BackupInventory | BackupRetentionResult;
export type BackupInspectionData = {
  kind: 'snapshot' | 'ledger'; key_id: string; encrypted_bytes: number; sha256: string;
  authenticated: true; ledger_at: string; tenant_count: number; deletion_count?: number;
  backup_id?: string; snapshot_at?: string; memory_count?: number; application_version?: string;
  server_version?: number; archive_verified?: true; tenant_ids?: string[];
  context?: { local_workspace?: { workspace_id: string; primary_tenant_id: string; workspace_name: string; owner_name: string; embedding_profile: string; threads: number; application_version: string } };
}
export type RecoveryReceipt = {
  format: 1; state: 'restored'; started_at: string; restored_at: string; workspace_id: string;
  source_workspace_id: string | null; backup_id: string; snapshot_sha256: string; ledger_sha256: string;
  data_directory: string; tenant_id: string; tenant_count: number; keys_rotated: true;
  verified_tables: number; deletions_reconciled: number; ledger_at: string;
  external_connections_require_review: true;
}
export type BackupConfiguration = {
  revision: string; workspace_id: string; destination: string; key_id: string;
  enabled: boolean; snapshot_hours: number; ledger_minutes: number; protected_key: boolean; retention: BackupRetentionPolicy;
}
export type BackupView = {
  configuration?: BackupConfiguration; secure_storage: boolean; last_snapshot?: BackupReceipt; last_ledger?: BackupReceipt;
  last_error?: string; retry_at?: string; next_snapshot_at?: string; next_ledger_at?: string;
  snapshot_availability?: 'present' | 'missing' | 'changed' | 'unavailable';
  ledger_availability?: 'present' | 'missing' | 'changed' | 'unavailable';
  last_retention?: BackupRetentionResult;
}
export type BackupSettings = {
  expected_revision: string | null; destination: string; enabled: boolean;
  snapshot_hours: number; ledger_minutes: number; recovery_key?: string; key_saved: boolean; retention?: BackupRetentionPolicy;
}
export type BackupSettingsInput = Omit<BackupSettings, 'destination'> & { destination_selection: string | null };
export type BackupRestoreInput = {
  snapshot_selection: string; ledger_selection: string; recovery_key: string; ledger_key?: string | null;
  snapshot_sha256: string; ledger_sha256: string; primary_tenant_id: string; trusted_backup_confirmed: boolean;
}
export type LocalDiagnostic = {
  category: 'unexpected' | 'memory' | 'dependency' | 'operating_system' | 'timeout' | 'database';
  errno?: number; winerror?: number; sqlstate?: string;
  locations: Array<{ module: string; function: string; line: number }>;
}
