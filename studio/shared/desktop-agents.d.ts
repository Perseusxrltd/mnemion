export type AgentSetup = {
  id?: string; client: string; server_name: string; config_path?: string;
  endpoint: string; tenant_id: string; principal_id: string; legacy_space?: string | null;
};
export type AgentPreview = {
  setup: AgentSetup & { id: string; config_path: string }; configuration_hash: string | null;
  replacing: boolean; snippet: string; credential_storage: 'private_os_account_file';
  command: { command: string; args: string[] };
};
export type AgentInstallation = AgentPreview['setup'] & {
  created_at: string; configuration_hash: string | null;
  state: 'installed' | 'key_missing' | 'replaced' | 'removed' | 'unverified';
  private_key_file_exists: boolean; agent_restart_required: boolean;
};
export type AgentSetupStatus = {
  profiles: { client: string; config_path: string | null; exists: boolean; custom_path_required: boolean }[];
  installations: AgentInstallation[]; credential_storage: 'private_os_account_file'; max_installations: number;
  runtime_version?: string | null; runtime_attention?: string | null;
};
export type AgentInstall = {
  setup: AgentPreview['setup']; configuration_hash: string | null;
  credential: string; confirm: true; replace_existing: boolean;
};
export type AgentRemove = { id: string; configuration_hash: string | null; confirm: true };
export type AgentSetupResult = { installation: AgentInstallation; backup: string | null; changed: boolean; server_key_revoked?: false };
