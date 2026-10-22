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
