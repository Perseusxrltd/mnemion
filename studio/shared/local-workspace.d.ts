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
}
export type LocalStatus = {
  available: boolean; state: 'new' | 'starting' | 'running' | 'stopping' | 'stopped' | 'error';
  stage?: string; message: string; info?: LocalInfo; errorCode?: string; memory?: MemorySnapshot;
  preferences?: { selected: boolean; startWithApp: boolean };
  diagnostic?: LocalDiagnostic;
}
export type LocalDiagnostic = {
  category: 'unexpected' | 'memory' | 'dependency' | 'operating_system' | 'timeout' | 'database';
  errno?: number; winerror?: number; sqlstate?: string;
  locations: Array<{ module: string; function: string; line: number }>;
}
