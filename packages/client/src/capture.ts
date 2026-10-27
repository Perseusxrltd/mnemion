/** Reviewed capture policies and device permissions; no producer file contents. */
export type CapturePolicy = {
  format: 'mnemion-capture-policy-v1' | 'mnemion-capture-policy-v2' | 'mnemion-capture-policy-v3'; preset: 'selected' | 'conversation' | 'detailed';
  capture_mode: 'messages' | 'complete'; include: string[]; exclude: string[];
  retention: 'source_mirror' | 'until_deleted' | 'expire_after'; max_file_bytes: number; max_record_bytes: number;
  retention_days?: number; expiry_scope?: 'captured_fragment_family';
  exclude_fields?: string[];
}

export interface CaptureSource {
  version: number; policy_version: number; source_id: string; connector_id: string;
  space_id: string; namespace: string; name: string; members: string[];
  capture_mode: 'messages' | 'complete'; capture_policy: CapturePolicy | null;
  keep_accepted: true; revoked_at: string | null; has_capture_history: boolean;
}

export interface CapturePolicyVersion {
  source_id: string; policy_version: number; capture_mode: 'messages' | 'complete';
  capture_policy: CapturePolicy | null; created_at: string; transition_id: string | null;
  previous_grants: 'retain' | 'revoke' | null; affected_grants: number | null;
  approved_by: string | null;
}

export interface CapturePolicyChange {
  expected_version: number; review_token: string; capture_policy: CapturePolicy;
  previous_grants: 'retain' | 'revoke'; confirm: true;
}

export interface CapturePolicyChanged {
  source: CaptureSource; transition: CapturePolicyVersion;
}

export interface CaptureGrant {
  grant_id: string; source_id: string; connector_id: string; space_id: string;
  tenant_id: string; device_key_id: string; namespace: string;
  capture_mode: 'messages' | 'complete'; capture_policy: CapturePolicy | null;
  policy_version: number; revoked_at: string | null; source_revoked_at: string | null;
  active: boolean;
}
