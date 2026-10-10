/** Evidence-linked suggestions; model findings never grant access or verify facts. */
export type LibrarianMode = 'organize' | 'review'
export type LibrarianProposalState = 'pending' | 'accepted' | 'rejected' | 'undone' | 'invalidated'
export interface LibrarianChoice {
  id: string; label: string; model: string; revision: string; fingerprint: string
  protocol: 'openai' | 'ollama'; endpoint_origin: string; network_egress: boolean
  context_budget: number; token_count_unit: 'model_tokens' | 'utf8_bytes'
  max_output_tokens: number; timeout_seconds: number
}
export interface LibrarianSettings {
  space_id: string; version: number; profile_id: string | null; profile_fingerprint: string | null
  profile_available: boolean; enabled: boolean; network_egress_approved: boolean
  mode: LibrarianMode; max_memories: number; max_calls_per_day: number
  interval_minutes: number | null; next_run_at: string | null; calls_reserved_today: number
  pending_proposals: number; updated_at: string | null
}
export interface LibrarianSettingsInput {
  expected_version: number; profile_id: string; enabled?: boolean; approve_network_egress?: boolean
  mode?: LibrarianMode; max_memories?: number; max_calls_per_day?: number; interval_minutes?: number | null
}
export interface LibrarianRun {
  id: string; space_id: string; profile_id: string; profile_fingerprint: string; mode: LibrarianMode
  state: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  configuration: Record<string, unknown>; selected: number; processed: number; skipped: number
  proposal_count: number; calls_reserved: number; calls_completed: number; input_units: number
  output_tokens: number | null; request_bytes: number; response_bytes: number; latency_ms: number
  error_code: string | null; created_at: string; started_at: string | null; finished_at: string | null
}
export interface LibrarianSuggestion {
  kind: 'organize' | 'duplicate' | 'contradiction' | 'stale' | 'link'
  memory_id: string; related_ids: string[]; rationale: string; confidence: 'low' | 'medium' | 'high'
  evidence: { memory_id: string; quote: string }[]
  changes: { subject?: string | null; tags?: string[] | null; summary?: string | null } | null
}
export interface LibrarianReference {
  memory_id: string; revision_id: string; memory_version: number
}
export interface LibrarianRunItem extends LibrarianReference {
  position: number; state: 'pending' | 'completed' | 'skipped'; reason: string | null
}
export interface LibrarianProposal {
  id: string; run_id: string; memory_id: string; state: LibrarianProposalState; version: number
  suggestion: LibrarianSuggestion | null; before: Record<string, unknown> | null
  references: LibrarianReference[]
  applicable: boolean; unavailable_reason: string | null; applied_revision_id: string | null
  created_at: string; decided_at: string | null
}
export interface LibrarianDecisionReceipt {
  proposal_id: string; state: LibrarianProposalState; version: number; applied_revision_id: string | null
}
