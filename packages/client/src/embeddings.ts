/** Approved model choices and an independent candidate index for each space. */
export interface EmbeddingProfile {
  id: string; label: string; model: string; generation_id: string; dimensions: number;
  execution: string; network_egress: boolean; endpoint_origin: string | null;
  token_count_unit: 'model_tokens' | 'utf8_bytes'; configuration: Record<string, unknown>; registered: boolean;
}
export interface CandidateIndex {
  id: string; generation_id: string; state: 'running' | 'paused'; scan_complete: boolean;
  revisions: number; indexed_revisions: number; jobs: { state: string; count: number }[];
  ready_to_activate: boolean; network_egress_approved: boolean; created_at: string; updated_at: string;
}
export interface EmbeddingSettings {
  space_id: string; version: number; active_generation_id: string; previous_generation_id: string | null;
  candidate: CandidateIndex | null; profiles: EmbeddingProfile[];
  inference_paused?: boolean;
}
export interface ReindexInput { profile_id: string; expected_version: number; approve_network_egress?: boolean }
export type ReindexAction = 'pause' | 'resume' | 'retry' | 'cancel' | 'activate';
export interface EmbeddingChoice {
  generation_id: string; state: 'active' | 'candidate'; label: string; available: boolean;
  token_count_unit: 'model_tokens' | 'utf8_bytes' | null;
}
