export type HostConnection = {
  host_id: string; operator_id: string; hostname: string; port: number; username: string;
  host_key_algorithm: string; host_key_fingerprint: string; operator_key_fingerprint: string;
}
export type HostRequest = {
  protocol: 1; host_id: string; request_id: string; action: string;
  issued_at?: string; valid_until?: string; [key: string]: unknown;
}
export type HostReceipt = {
  protocol: 1; host_id: string; operator_id: string; request_id: string; ok: boolean;
  result: Record<string, any> | null; error: { code: string; message: string } | null;
}
export type HostProfile = {
  id: string; name: string; public_key: string; fingerprint: string; created_at: string;
  connection: HostConnection | null;
  last_operation: { request: HostRequest; phase: string; at: string } | null;
}
export type HostProfilesStatus = { secure_storage: boolean; profiles: HostProfile[] }
export type HostInspection = { status: HostReceipt; history: HostReceipt | null; operation: HostReceipt | null }
export type HostBackup = {
  backup_id: string; key_id: string; service_version: string | null;
  snapshot_at: string; ledger_at: string; verified_at: string; last_verified_at: string;
  bytes: number; files: Record<'bundle' | 'ledger', { bytes: number; sha256: string }>;
  remote_readback_verified: true; controller_authority_included: false;
}
export type HostBackupsStatus = {
  configured: boolean; inspection_required?: boolean; key_id?: string | null;
  configuration_sha256?: string | null; maximum_bytes?: number | null;
  last_verified_at?: string | null; retained_verified_backups?: number; items?: HostBackup[];
}
