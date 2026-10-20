export type ModelKind = 'embedding' | 'librarian'
export type ModelCommonSettings = {
  id: string; label: string; protocol: 'openai' | 'ollama'; endpoint: string; model: string; revision: string;
  response_model?: string | null; api_key_header?: 'Authorization' | 'api-key'; timeout_seconds?: number;
  api_key_env?: null; ca_bundle_env?: null;
  tokenizer?: { kind: 'utf8'; repository?: null; revision?: null; sha256?: null; file_env?: null };
  max_response_bytes?: number; keep_alive_seconds?: number; server_threads?: number;
}
export type EmbeddingProviderSettings = ModelCommonSettings & {
  dimensions: number; send_dimensions?: boolean; query_prefix?: string; document_prefix?: string;
  chunk_tokens?: number; overlap_tokens?: number; max_input_tokens?: number; max_query_tokens?: number;
  batch_size?: number; max_document_bytes?: number; document_timeout_seconds?: number; max_queued?: number;
}
export type LibrarianProviderSettings = ModelCommonSettings & {
  context_budget?: number; chat_overhead_reserve?: number; max_output_tokens?: number;
  output_token_parameter?: 'max_tokens' | 'max_completion_tokens'; json_mode?: boolean;
  temperature?: number | null; thinking?: boolean | null;
}
export type ModelDefinition = { kind: 'embedding'; profile: EmbeddingProviderSettings } | { kind: 'librarian'; profile: LibrarianProviderSettings }
export type SavedModelProvider = ModelDefinition & { has_api_key: boolean; has_custom_ca: boolean; network_egress: boolean; fingerprint: string }
export type ModelsChange = { workspace_id: string; expected_revision: string } & (
  { action: 'save'; provider: ModelDefinition; api_key?: string | null; clear_api_key?: boolean; ca_pem?: string | null } |
  { action: 'remove'; kind: ModelKind; profile_id: string } | { action: 'reset' }
)
export type ModelsAccess = {
  revision: string; repairable: boolean; state: 'not_configured' | 'configured' | 'configuration_error' | 'external';
  message: string; providers: SavedModelProvider[];
}
