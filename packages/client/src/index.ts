import type { Insights, RuntimeInsights, MetricOrigin, EvaluationDataset, EvaluationDatasetInput,
  EvaluationInput, EvaluationRun, EvaluationResultPage, EvaluationResult, AssessmentInput, EvaluationComparison } from './insights.js'
export * from './insights.js'
import type { EmbeddingSettings, EmbeddingChoice, ReindexInput, ReindexAction } from './embeddings.js'
export * from './embeddings.js'
import type { LibrarianChoice, LibrarianSettings, LibrarianSettingsInput, LibrarianRun, LibrarianRunItem,
  LibrarianMode, LibrarianProposal, LibrarianProposalState, LibrarianDecisionReceipt } from './librarian.js'
export * from './librarian.js'
import type { PasswordAccount, DeviceSession, OAuthConfiguration, OAuthConnection, SignInInvitation, InvitationReceipt, CompanyConfiguration, CompanyLink } from './sign-in.js'
export * from './sign-in.js'
import type { RecoveryDirectory, RecoveryDirectoryRecord } from './recovery.js'
export * from './recovery.js'
import type { KeepassExported, KeepassImported, KeepassImportInput, KeepassPreview, KeepassPreviewInput, VaultAuditEvent, VaultEntry, VaultEnvelope, VaultGrantInput, VaultGrants, VaultPage, VaultPutInput, VaultStatus } from './vault.js'
export * from './vault.js'
import type { JournalBackfillControl, JournalBackfillStart, JournalBackfillStatus, JournalDelivery, JournalPolicyInput, JournalStatus } from './writeback.js'
export * from './writeback.js'
export * from './conversations.js'
import type { BufferPreviewInput, BufferImportInput, BufferPreview, BufferImported } from './buffer-import.js'
export * from './buffer-import.js'
import type { JournalRecoveryInput, JournalRecoveryApply, JournalRecoveryPreview, JournalRecoveryReceipt } from './journal-recovery.js'
export * from './journal-recovery.js'

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json }
export type Kind = 'fact' | 'event' | 'preference' | 'procedure' | 'note'
export type ClaimStatus = 'observed' | 'verified' | 'contested' | 'superseded' | 'retracted'
export type Role = 'reader' | 'contributor' | 'reviewer' | 'administrator'
export type OperationState = 'accepted' | 'indexing' | 'ready' | 'failed' | 'cancelled'

export interface SourceInput {
  title?: string; uri?: string | null; content?: string | null
  media_type?: 'text/plain' | 'text/markdown'; start?: number; end?: number | null
}
export interface MemoryInput {
  content: string; kind?: Kind; subject?: string | null; metadata?: Record<string, Json>
  source?: SourceInput | null; claim_status?: ClaimStatus
  valid_from?: string | null; valid_to?: string | null
}
export interface RevisionInput extends MemoryInput { expected_version: number; reason: string }
export interface Receipt {
  operation_id: string; memory_id: string; revision_id: string | null; space_id: string
  state: OperationState; version?: number; lexical_ready: boolean; semantic_ready: boolean
  generation_id: string | null; deleted?: boolean
  writeback?: JournalDelivery | null
}
export interface Operation {
  operation_id: string; memory_id: string | null; revision_id: string | null; space_id: string
  kind: 'ingest' | 'revise' | 'delete' | 'reindex'; state: OperationState
  error_code: string | null; created_at: string; updated_at: string; memory_deleted?: boolean
}
export interface AuditEvent {
  id: string; space_id: string | null; principal_id: string; action: string
  resource_id: string; details: Record<string, Json>; reason: string | null; created_at: string
}
export interface Evidence {
  source_id: string; source_revision_id: string; title: string; uri: string | null
  media_type: string; content_hash: string; start: number; end: number
  offset_unit: 'unicode_codepoints'; excerpt: string; excerpt_truncated?: boolean
}
export interface Attachment { attachment_id: string; name: string; media_type: string; content_hash: string; size_bytes: number }
export interface Source {
  source_revision_id: string; source_id: string; space_id: string; title: string; uri: string | null
  content: string; content_hash: string; media_type: string; recorded_at: string; attachments: Attachment[]
}
export interface Memory {
  memory_id: string; revision_id: string; space_id: string; version: number; revision_version: number
  content: string; content_hash: string; metadata: Record<string, Json>; kind: Kind
  subject: string | null; claim_status: ClaimStatus; review_state: 'ordinary' | 'quarantined'
  valid_from: string | null; valid_to: string | null; recorded_at: string
  created_at: string; updated_at: string; created_by: string; evidence: Evidence
  can_forget?: boolean | null
}
export interface RankingPolicy {
  recency_weight?: number; half_life_days?: number; archive_weight?: number
  archive_path_segments?: string[]
  recent_relevance_ratio?: number
}
export interface RecallInput {
  query: string; space_ids?: string[]; all_accessible?: boolean; subject?: string | null; kinds?: Kind[]
  limit?: number; mode?: 'hybrid' | 'lexical' | 'semantic'; include_contested?: boolean
  valid_at?: string | null; known_at?: string | null; metadata_filter?: Record<string, string | number | boolean>
  embedding_generation?: string | null
  on_inference_busy?: 'error' | 'lexical'
  sort?: 'relevance' | 'recent'; recorded_after?: string | null
  min_score?: number; min_similarity?: number | null
  ranking_policy?: RankingPolicy
  keyword_fallback?: boolean
  max_per_source?: number
}
export interface RecallHit extends Omit<Memory, 'content'> {
  text: string; text_truncated: boolean
  memory_span: { start: number; end: number; offset_unit: 'unicode_codepoints' }
  relevance_score: number; score_method: 'normalized_rrf_k60'
  ranking: {
    ranks: { lexical?: number; semantic?: number }; rrf: number
    lexical_rank: number | null; cosine_similarity: number | null
    identifier?: {
      rank: number; label_rank: number | null; matched: number; requested: number
      label_matches: number; weight: number; label_weight: number
      context_matches?: number
    } | null
    adjustment?: {
      score: number; date: string; age_days: number
      recency_factor: number; archive_factor: number; archive_segment: string | null
      keyword_factor?: number | null
      configured_archive_factor?: number; archive_uncontested?: boolean
    } | null
    archive?: { archive_factor: number; archive_segment: string | null; demoted: boolean } | null
    keywords?: { rank: number; matched: number; requested: number; terms: string[]; weight: number } | null
    recency?: {
      at: string; basis: 'recorded_at' | 'source_modified_at' | 'source_timestamp' | 'source_date'
      span: { start: number; end: number; offset_unit: 'unicode_codepoints' }
      tracked: boolean; matched_terms: number; requested_terms: number; prioritized: boolean | null
      limited?: boolean
      comparison_support?: number
      comparison_basis?: 'passage_coverage' | 'rank_fusion_with_keyword_support' | 'rank_fusion'
    } | null
  }
}
export interface IndexState {
  generation_id: string | null; generation_ids?: string[]; space_generations?: Record<string, string>
  eligible_records: number; indexed_records: number
  pending_records: number; observed_at: string
}
export interface SourceGrouping {
  max_per_source: number; grouped_candidates: number; scope: 'candidate_window'
}
export interface Recall {
  request_id: string; query: string; hits: RecallHit[]; warnings: string[]
  index: IndexState; timing_ms: number; score_description: string
  match_status?: 'matched' | 'semantic_only' | 'empty'; filtered_candidates?: number
  ranking_policy?: RankingPolicy | null; ranking_reference_time?: string | null
  source_grouping?: SourceGrouping | null
}
export interface ContextPack {
  source_grouping?: SourceGrouping | null
  request_id: string; text: string; token_count: number; token_budget: number; tokenizer: string
  tokenizer_generation: string; omitted_items: number; warnings: string[]; index: IndexState
  token_count_unit?: 'model_tokens' | 'utf8_bytes'
  citations: { number: number; memory_id: string; revision_id: string; space_id: string; source_revision_id: string; source_start: number; source_end: number }[]
  core_blocks: { space_id: string; key: string; version: number }[]
}
export interface Space { id: string; name: string; description: string; role: Role | null; created_at: string }
export interface Principal { id: string; name: string; kind: 'human' | 'application'; administrator: boolean; disabled_at: string | null }
export interface ApiKey { id: string; principal_id: string; name: string; prefix: string; expires_at: string | null; revoked_at: string | null }
export interface CoreBlock { key: string; content: string; version: number; updated_at: string; updated_by: string }
export interface Page<T> { items: T[]; next_cursor?: string | null }
export interface Connector { id: string; name: string; provider: string; principal_id: string; access_mode: 'provider' | 'published'; disabled_at: string | null; created_at: string }
export interface ConnectorSyncStatus { connector_id: string; requested_generation: number; completed_generation: number; pending: boolean; requested_at: string | null; completed_at: string | null; last_attempt_at: string | null; last_successful: boolean | null; last_duration_seconds: number | null; last_changed: number; last_removed: number; last_unchanged: number; last_error_code: string | null; scanned_commit?: string | null; scanned_at?: string | null; scanned_space_id?: string | null }
export interface ConnectorBinding { external_id: string; principal_id: string; role: 'reader' | 'reviewer' }
export interface SourceFileError { path: string; path_sha256: string; error_code: 'source_is_not_utf8_text' | 'source_contains_binary_data' | 'source_too_large' }
export interface SourceInventory { incomplete_inventory: boolean; skipped_documents: number; file_errors: SourceFileError[] }
export interface SourceHealth { unavailable_scopes: number; incomplete_scopes: number; skipped_documents: number; attention: string[]; observed_at: string }
export interface ConnectorScope { space_id: string; connector_id: string; external_id: string; name?: string; operator_paused: boolean; access_current: boolean; observed_at: string; access_valid_until: string; suspended_at: string | null; suspension_reason: string | null; completed_at: string | null; checkpoint?: string | null; inventory?: SourceInventory | null }
export interface KnowledgeNode { id: string; kind: 'space' | 'memory' | 'source' | 'entity'; label: string; space_id: string; memory_id?: string }
export interface Knowledge { generated_at: string; fingerprint: string; truncated: boolean; memories: Memory[]; nodes: KnowledgeNode[]; edges: { source: string; target: string; relation: 'in_space' | 'cites' | 'about' }[]; topics: { id: string; title: string; space_id: string; memory_ids: string[] }[]; findings: { kind: 'exact_duplicate' | 'contested' | 'unassigned_subject'; message: string; memory_ids: string[] }[]; markdown: string }
export interface ConnectorItem { external_id: string; revision: string; action: 'upsert' | 'delete' | 'retain'; memory?: MemoryInput | null }
export interface ConnectorProposal { memory_id: string; proposal_hash: string; payload: ConnectorItem; created_at: string; version: number }

export class MnemionError extends Error {
  constructor(public readonly status: number, public readonly code: string, message: string, public readonly requestId?: string, public readonly retryAfterSeconds?: number) {
    super(message); this.name = 'MnemionError'
  }
  get retryable() { return [408, 429, 502, 503, 504].includes(this.status) }
}

function retryAfter(value: string | null): number | undefined {
  if (!value || value.length > 128) return undefined
  const seconds = /^\d+(?:\.\d+)?$/.test(value) ? Number(value) : (Date.parse(value) - Date.now()) / 1000
  return Number.isFinite(seconds) ? Math.max(0, Math.min(30, seconds)) : undefined
}

function waitForRetry(ms: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.reject(signal.reason)
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(signal?.reason) }
    const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve() }, ms)
    signal?.addEventListener('abort', abort, { once: true })
  })
}
export interface ClientOptions {
  baseUrl: string; apiKey: string | (() => Promise<string>); timeoutMs?: number; retries?: number; fetch?: typeof globalThis.fetch
}
interface RequestOptions { body?: unknown; key?: string; signal?: AbortSignal; binary?: boolean }

export class MnemionClient {
  previewJournalRecovery(space: string, input: JournalRecoveryInput) { return this.request<JournalRecoveryPreview>('POST', '/v1/spaces/' + encodeURIComponent(space) + '/journal-recovery/preview', { body: input }) }
  restoreJournal(space: string, input: JournalRecoveryApply, key: string = crypto.randomUUID()) { return this.request<JournalRecoveryReceipt>('POST', '/v1/spaces/' + encodeURIComponent(space) + '/journal-recovery', { body: input, key }) }
  private journalPath(space: string) { return '/v1/spaces/' + encodeURIComponent(space) + '/writeback' }
  journalStatus(space: string) { return this.request<JournalStatus>('GET', this.journalPath(space)) }
  configureJournal(space: string, input: JournalPolicyInput) { return this.request<JournalStatus>('PUT', this.journalPath(space), { body: input }) }
  pushJournal(space: string, expectedVersion: number) { return this.request<JournalStatus>('POST', this.journalPath(space) + '/push', { body: { expected_version: expectedVersion } }) }
  organizeJournal(space: string, expectedVersion: number) { return this.request<JournalStatus>('POST', this.journalPath(space) + '/organize', { body: { expected_version: expectedVersion } }) }
  journalBackfillStatus(space: string) { return this.request<JournalBackfillStatus>('GET', this.journalPath(space) + '/backfill') }
  previewLegacyBuffer(space: string, input: BufferPreviewInput) { return this.request<BufferPreview>('POST', `/v1/spaces/${encodeURIComponent(space)}/buffer-import/preview`, { body: input }) }
  importLegacyBuffer(space: string, input: BufferImportInput, key: string = crypto.randomUUID()) { return this.request<BufferImported>('POST', `/v1/spaces/${encodeURIComponent(space)}/buffer-import`, { body: input, key }) }
  startJournalBackfill(space: string, input: JournalBackfillStart, key: string = crypto.randomUUID()) { return this.request<JournalBackfillStatus>('POST', this.journalPath(space) + '/backfill', { body: input, key }) }
  controlJournalBackfill(space: string, input: JournalBackfillControl) { return this.request<JournalBackfillStatus>('POST', this.journalPath(space) + '/backfill/control', { body: input }) }
  private librarianPath(space: string) { return '/v1/spaces/' + encodeURIComponent(space) + '/librarian' }
  librarianChoices(space: string) { return this.request<Page<LibrarianChoice>>('GET', this.librarianPath(space) + '/models') }
  librarianSettings(space: string) { return this.request<LibrarianSettings>('GET', this.librarianPath(space)) }
  configureLibrarian(space: string, input: LibrarianSettingsInput) { return this.request<LibrarianSettings>('PUT', this.librarianPath(space), { body: input }) }
  librarianRuns(space: string, cursor?: string) {
    const params = new URLSearchParams({ limit: '50' }); if (cursor) params.set('cursor', cursor)
    return this.request<Page<LibrarianRun>>('GET', this.librarianPath(space) + '/runs?' + params)
  }
  startLibrarian(space: string, mode: LibrarianMode = 'organize', memoryIds: string[] = [], key = crypto.randomUUID()) {
    return this.request<LibrarianRun>('POST', this.librarianPath(space) + '/runs', { body: { mode, memory_ids: memoryIds }, key })
  }
  cancelLibrarian(space: string, run: string) { return this.request<LibrarianRun>('POST', this.librarianPath(space) + '/runs/' + encodeURIComponent(run) + '/cancel') }
  librarianRunItems(space: string, run: string) { return this.request<Page<LibrarianRunItem>>('GET', this.librarianPath(space) + '/runs/' + encodeURIComponent(run) + '/items') }
  librarianProposals(space: string, state?: LibrarianProposalState, cursor?: string) {
    const params = new URLSearchParams({ limit: '20' })
    if (state) params.set('state', state); if (cursor) params.set('cursor', cursor)
    return this.request<Page<LibrarianProposal>>('GET', this.librarianPath(space) + '/proposals?' + params)
  }
  decideLibrarian(space: string, proposal: string, action: 'accept' | 'reject' | 'undo', version: number, key = crypto.randomUUID()) {
    return this.request<LibrarianDecisionReceipt>('POST', this.librarianPath(space) + '/proposals/' + encodeURIComponent(proposal) + '/decision',
      { body: { action, expected_version: version }, key })
  }
  embeddingChoices(space: string) { return this.request<Page<EmbeddingChoice>>('GET', `/v1/spaces/${encodeURIComponent(space)}/embedding/choices`) }
  embeddingSettings(space: string) { return this.request<EmbeddingSettings>('GET', `/v1/spaces/${encodeURIComponent(space)}/embedding`) }
  startReindex(space: string, input: ReindexInput, key?: string) { return this.request<EmbeddingSettings>('POST', `/v1/spaces/${encodeURIComponent(space)}/embedding/reindex`, { body: input, key: key ?? globalThis.crypto.randomUUID() }) }
  controlReindex(space: string, run: string, action: ReindexAction, version: number, approveNetworkEgress = false) { return this.request<EmbeddingSettings>('POST', `/v1/spaces/${encodeURIComponent(space)}/embedding/reindex/${encodeURIComponent(run)}/${action}`, { body: { expected_version: version, approve_network_egress: approveNetworkEgress } }) }
  resumeEmbeddingProcessing(space: string, version: number, approveNetworkEgress = false) { return this.request<EmbeddingSettings>('POST', `/v1/spaces/${encodeURIComponent(space)}/embedding/resume`, { body: { expected_version: version, approve_network_egress: approveNetworkEgress } }) }
  readonly baseUrl: string
  #apiKey: string | (() => Promise<string>)
  #fetch: typeof globalThis.fetch
  #timeout: number
  #retries: number
  constructor(options: ClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, '')
    this.#apiKey = options.apiKey
    this.#fetch = (options.fetch ?? globalThis.fetch).bind(globalThis)
    this.#timeout = options.timeoutMs ?? 30000
    this.#retries = options.retries ?? 2
    if (this.#retries < 0 || this.#retries > 5) throw new Error('Retries must be between 0 and 5')
  }

  #credential(signal: AbortSignal): Promise<string> {
    const reason = () => signal.reason ?? new Error('Credential acquisition was cancelled')
    if (signal.aborted) return Promise.reject(reason())
    return new Promise((resolve, reject) => {
      const abort = () => reject(reason())
      signal.addEventListener('abort', abort, { once: true })
      Promise.resolve().then(() => {
        if (signal.aborted) throw reason()
        return typeof this.#apiKey === 'function' ? this.#apiKey() : this.#apiKey
      }).then(value => {
        signal.removeEventListener('abort', abort)
        if (typeof value !== 'string' || !/^[\x21-\x7e]{1,4096}$/.test(value)) {
          reject(new Error('The credential provider returned an invalid credential'))
        } else resolve(value)
      }, error => { signal.removeEventListener('abort', abort); reject(error) })
    })
  }

  async request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
    const safeRetry = method === 'GET' || !!options.key || ['/v1/recall', '/v1/context', '/v1/knowledge'].includes(path)
    let rejectedCredential: { value: string; error: MnemionError } | undefined
    let checkedRotation = false
    for (let attempt = 0; attempt <= this.#retries; attempt++) {
      let retryDelay = Math.min(2000, 200 * 2 ** attempt)
      const timeout = new AbortController()
      const timer = setTimeout(() => timeout.abort(new Error('Mnemion request timed out')), this.#timeout)
      const signal = options.signal ? AbortSignal.any([options.signal, timeout.signal]) : timeout.signal
      let credentialReady = false
      try {
        const apiKey = await this.#credential(signal)
        credentialReady = true
        if (rejectedCredential) {
          if (apiKey === rejectedCredential.value) throw rejectedCredential.error
          rejectedCredential = undefined
        }
        const response = await this.#fetch(this.baseUrl + path, {
          method, signal, redirect: 'error',
          headers: { 'Authorization': `Bearer ${apiKey}`, ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }),
            ...(options.key ? { 'Idempotency-Key': options.key } : {}) },
          body: options.body === undefined ? undefined : JSON.stringify(options.body),
        })
        if (response.headers.get('ngrok-error-code') === 'ERR_NGROK_3200') {
          await response.body?.cancel()
          throw new MnemionError(response.status, 'tunnel_offline',
            'The workspace tunnel is offline. Restart its connection through the host’s operator controls; changing the workspace key will not reconnect the host.')
        }
        if (response.ok) return (response.status === 204 ? undefined : options.binary ? await response.arrayBuffer() : await response.json()) as T
        let payload: { error?: { code?: string; message?: string }; request_id?: string } = {}
        try {
          const parsed = await response.json()
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) payload = parsed
        } catch { /* Non-JSON proxy errors have a stable fallback. */ }
        const retryAfterSeconds = retryAfter(response.headers.get('Retry-After'))
        if (retryAfterSeconds !== undefined) retryDelay = Math.max(retryDelay, retryAfterSeconds * 1000)
        const error = new MnemionError(response.status, payload.error?.code ?? 'http_error',
          payload.error?.message ?? `Mnemion returned HTTP ${response.status}`, payload.request_id ?? response.headers.get('X-Request-ID') ?? undefined, retryAfterSeconds)
        if (response.status === 401 && safeRetry && typeof this.#apiKey === 'function' && !checkedRotation && attempt < this.#retries) {
          // A concurrent request/tab may have rotated this access credential.
          // Retry only after observing a different one; revoked credentials and
          // uncertain refresh failures must never cause a retry loop.
          checkedRotation = true
          rejectedCredential = { value: apiKey, error }
          retryDelay = 0
        } else if (!(safeRetry && [408, 429, 502, 503, 504].includes(response.status) && attempt < this.#retries)) {
          throw error
        }
      } catch (error) {
        if (!credentialReady || error instanceof MnemionError || options.signal?.aborted || !safeRetry || attempt === this.#retries) throw error
      } finally { clearTimeout(timer) }
      await waitForRetry(retryDelay, options.signal)
    }
    throw new Error('Request retry loop exhausted')
  }

  me() { return this.request<{ principal_id: string; tenant_id: string; name: string; tenant_name: string; administrator: boolean; service_version?: string | null }>('GET', '/v1/me') }
  recoveryDirectory() { return this.request<RecoveryDirectoryRecord>('GET', '/v1/recovery-directory') }
  vaultStatus() { return this.request<VaultStatus>('GET', '/v1/vault/status') }
  vaultEntries(offset = 0, limit = 100) { return this.request<VaultPage<VaultEntry>>('GET', `/v1/vault/entries?offset=${offset}&limit=${limit}`) }
  vaultValue(id: string) { return this.request<VaultEntry & { value: string }>('GET', `/v1/vault/entries/${encodeURIComponent(id)}`) }
  putVaultValue(id: string, input: VaultPutInput) { return this.request<VaultEntry>('PUT', `/v1/vault/entries/${encodeURIComponent(id)}`, { body: input }) }
  vaultGrants(id: string) { return this.request<VaultGrants>('GET', `/v1/vault/entries/${encodeURIComponent(id)}/grants`) }
  grantVault(id: string, input: VaultGrantInput) { return this.request<VaultGrants>('PUT', `/v1/vault/entries/${encodeURIComponent(id)}/grants`, { body: input }) }
  deleteVault(id: string, expected_version: number) { return this.request<{ id: string; deleted: true }>('POST', `/v1/vault/entries/${encodeURIComponent(id)}/delete`, { body: { expected_version } }) }
  exportVault(entry_ids: string[], recovery_key: string) { return this.request<VaultEnvelope>('POST', '/v1/vault/export', { body: { entry_ids, recovery_key } }) }
  importVault(archive: VaultEnvelope, recovery_key: string) { return this.request<VaultPage<VaultEntry>>('POST', '/v1/vault/import', { body: { archive, recovery_key } }) }
  previewKeePass(input: KeepassPreviewInput) { return this.request<KeepassPreview>('POST', '/v1/vault/keepass/preview', { body: input }) }
  importKeePass(input: KeepassImportInput) { return this.request<KeepassImported>('POST', '/v1/vault/keepass/import', { body: input }) }
  exportKeePass(entry_ids: string[], password: string) { return this.request<KeepassExported>('POST', '/v1/vault/keepass/export', { body: { entry_ids, password } }) }
  vaultAudit(offset = 0, limit = 100) { return this.request<VaultPage<VaultAuditEvent>>('GET', `/v1/vault/audit?offset=${offset}&limit=${limit}`) }
  configureRecoveryDirectory(expected_revision: number, directory: RecoveryDirectory) {
    return this.request<RecoveryDirectoryRecord>('PUT', '/v1/recovery-directory', { body: { expected_revision, directory } })
  }
  passwordAccount() { return this.request<{ account: PasswordAccount | null; can_use_password: boolean }>('GET', '/v1/sign-in/account') }
  setPassword(input: { username: string; password: string; current_password?: string }) { return this.request<{ changed: boolean; sessions_revoked: boolean }>('PUT', '/v1/sign-in/account', { body: input }) }
  deviceSessions() { return this.request<{ items: DeviceSession[] }>('GET', '/v1/sign-in/sessions') }
  revokeSession(id: string) { return this.request<{ id: string; revoked: boolean }>('DELETE', '/v1/sign-in/sessions/' + encodeURIComponent(id)) }
  oauthConfiguration() { return this.request<OAuthConfiguration>('GET', '/v1/oauth/configuration') }
  signInConfiguration() { return this.request<{ password_sign_in: boolean; public_origin: string | null; browser_sign_in: boolean; remember_browser: boolean; minimum_password_characters: number }>('GET', '/v1/sign-in/configuration') }
  companyConfiguration(workspace: string) { return this.request<CompanyConfiguration>('GET', '/v1/sign-in/company/configuration?workspace_id=' + encodeURIComponent(workspace)) }
  companyLinks() { return this.request<{ items: CompanyLink[] }>('GET', '/v1/sign-in/company/links') }
  linkCompanyIdentity(input: { principal_id: string; provider_id: string; subject: string }) { return this.request<{ id: string; principal_id: string; provider_id: string }>('POST', '/v1/sign-in/company/links', { body: input }) }
  revokeCompanyIdentity(id: string) { return this.request<{ id: string; revoked: boolean }>('DELETE', '/v1/sign-in/company/links/' + encodeURIComponent(id)) }
  oauthConnections() { return this.request<{ connections: OAuthConnection[] }>('GET', '/v1/oauth/connections') }
  revokeOAuthConnection(id: string) { return this.request<{ id: string; revoked: boolean }>('POST', '/v1/oauth/connections/' + encodeURIComponent(id) + '/revoke') }
  signInInvitations() { return this.request<{ items: SignInInvitation[] }>('GET', '/v1/sign-in/invitations') }
  createSignInInvitation(input: { principal_id: string; purpose?: 'enroll' | 'reset'; expires_in_seconds?: number }) { return this.request<InvitationReceipt>('POST', '/v1/sign-in/invitations', { body: input }) }
  revokeSignInInvitation(id: string) { return this.request<{ id: string; revoked: boolean }>('DELETE', '/v1/sign-in/invitations/' + encodeURIComponent(id)) }
  spaces() { return this.request<Page<Space>>('GET', '/v1/spaces') }
  space(id: string) { return this.request<Space>('GET', `/v1/spaces/${encodeURIComponent(id)}`) }
  createSpace(name: string, description = '') { return this.request<Space>('POST', '/v1/spaces', { body: { name, description } }) }
  save(space: string, memory: MemoryInput, key: string = crypto.randomUUID()) { return this.request<Receipt>('POST', `/v1/spaces/${encodeURIComponent(space)}/memories`, { body: memory, key }) }
  fetch(memory: string, options: { revisionId?: string; review?: boolean } = {}) {
    const params = new URLSearchParams({ review: String(options.review ?? false) })
    if (options.revisionId) params.set('revision_id', options.revisionId)
    return this.request<Memory>('GET', `/v1/memories/${encodeURIComponent(memory)}?${params}`)
  }
  list(space: string, options: { limit?: number; cursor?: string; review?: boolean } = {}) {
    const params = new URLSearchParams({ limit: String(options.limit ?? 50), review: String(options.review ?? false) })
    if (options.cursor) params.set('cursor', options.cursor)
    return this.request<Page<Memory>>('GET', `/v1/spaces/${encodeURIComponent(space)}/memories?${params}`)
  }
  history(memory: string, review = false) { return this.request<Page<Memory>>('GET', `/v1/memories/${encodeURIComponent(memory)}/revisions?review=${review}`) }
  source(revision: string, review = false) { return this.request<Source>('GET', `/v1/sources/${encodeURIComponent(revision)}?review=${review}`) }
  resolveAlias(space: string, legacyId: string, review = false) { return this.request<Memory>('GET', `/v1/spaces/${encodeURIComponent(space)}/resolve?${new URLSearchParams({ legacy_id: legacyId, review: String(review) })}`) }
  attachment(revision: string, attachment: string, review = false) { return this.request<ArrayBuffer>('GET', `/v1/sources/${encodeURIComponent(revision)}/attachments/${encodeURIComponent(attachment)}?review=${review}`, { binary: true }) }
  revise(memory: string, revision: RevisionInput, key: string = crypto.randomUUID()) { return this.request<Receipt>('POST', `/v1/memories/${encodeURIComponent(memory)}/revisions`, { body: revision, key }) }
  review(memory: string, state: 'ordinary' | 'quarantined', expectedVersion: number, reason: string) {
    return this.request<{ memory_id: string; version: number; review_state: string }>('PUT', `/v1/memories/${encodeURIComponent(memory)}/review`, { body: { state, expected_version: expectedVersion, reason } })
  }
  forget(memory: string, expectedVersion: number, key: string = crypto.randomUUID()) { return this.request<Receipt>('DELETE', `/v1/memories/${encodeURIComponent(memory)}?expected_version=${expectedVersion}`, { key }) }
  search(input: RecallInput) { return this.request<Recall>('POST', '/v1/recall', { body: input }) }
  context(input: RecallInput & { token_budget?: number }) { return this.request<ContextPack>('POST', '/v1/context', { body: input }) }
  operation(id: string) { return this.request<Operation>('GET', `/v1/operations/${encodeURIComponent(id)}`) }
  operations(space: string, state?: OperationState) { return this.request<Page<Operation>>('GET', `/v1/spaces/${encodeURIComponent(space)}/operations${state ? `?state=${state}` : ''}`) }
  activity(space: string, options: { memoryId?: string; limit?: number } = {}) {
    const params = new URLSearchParams({ limit: String(options.limit ?? 100) })
    if (options.memoryId) params.set('memory_id', options.memoryId)
    return this.request<Page<AuditEvent>>('GET', `/v1/spaces/${encodeURIComponent(space)}/activity?${params}`)
  }
  insights(space: string, options: { hours?: number; origin?: MetricOrigin; signal?: AbortSignal } = {}) {
    return this.request<Insights>('GET', `/v1/spaces/${encodeURIComponent(space)}/insights?${new URLSearchParams({ hours: String(options.hours ?? 24), origin: options.origin ?? 'all' })}`, { signal: options.signal })
  }
  runtimeInsights(signal?: AbortSignal) { return this.request<RuntimeInsights>('GET', '/v1/insights/runtime', { signal }) }
  evaluationDatasets(space: string, options: { cursor?: string; limit?: number } = {}) {
    const params = new URLSearchParams({ limit: String(options.limit ?? 200) })
    if (options.cursor) params.set('cursor', options.cursor)
    return this.request<Page<EvaluationDataset>>('GET', `/v1/spaces/${encodeURIComponent(space)}/evaluations/datasets?${params}`)
  }
  evaluationDataset(space: string, id: string) { return this.request<EvaluationDataset>('GET', `/v1/spaces/${encodeURIComponent(space)}/evaluations/datasets/${encodeURIComponent(id)}`) }
  createEvaluationDataset(space: string, input: EvaluationDatasetInput) { return this.request<EvaluationDataset>('POST', `/v1/spaces/${encodeURIComponent(space)}/evaluations/datasets`, { body: input }) }
  removeEvaluationDataset(space: string, id: string) { return this.request<void>('DELETE', `/v1/spaces/${encodeURIComponent(space)}/evaluations/datasets/${encodeURIComponent(id)}`) }
  evaluationRuns(space: string, options: { cursor?: string; limit?: number } = {}) {
    const params = new URLSearchParams({ limit: String(options.limit ?? 100) })
    if (options.cursor) params.set('cursor', options.cursor)
    return this.request<Page<EvaluationRun>>('GET', `/v1/spaces/${encodeURIComponent(space)}/evaluations/runs?${params}`)
  }
  evaluationRun(space: string, id: string, compact = false) { return this.request<EvaluationRun>('GET', `/v1/spaces/${encodeURIComponent(space)}/evaluations/runs/${encodeURIComponent(id)}?compact=${compact}`) }
  startEvaluation(space: string, input: EvaluationInput, key: string = crypto.randomUUID()) { return this.request<EvaluationRun>('POST', `/v1/spaces/${encodeURIComponent(space)}/evaluations/runs`, { body: input, key }) }
  evaluationResults(space: string, id: string, cursor = 0, limit = 50) { return this.request<EvaluationResultPage>('GET', `/v1/spaces/${encodeURIComponent(space)}/evaluations/runs/${encodeURIComponent(id)}/results?cursor=${cursor}&limit=${limit}`) }
  cancelEvaluation(space: string, id: string) { return this.request<EvaluationRun>('POST', `/v1/spaces/${encodeURIComponent(space)}/evaluations/runs/${encodeURIComponent(id)}/cancel`) }
  assessEvaluation(space: string, id: string, position: number, input: AssessmentInput) { return this.request<EvaluationResult>('PUT', `/v1/spaces/${encodeURIComponent(space)}/evaluations/runs/${encodeURIComponent(id)}/results/${position}/assessment`, { body: input }) }
  compareEvaluations(space: string, baselineId: string, candidateId: string) { return this.request<EvaluationComparison>('POST', `/v1/spaces/${encodeURIComponent(space)}/evaluations/compare`, { body: { baseline_id: baselineId, candidate_id: candidateId } }) }
  exportEvaluation(space: string, id: string, format: 'json' | 'csv' = 'json') { return this.request<ArrayBuffer>('GET', `/v1/spaces/${encodeURIComponent(space)}/evaluations/runs/${encodeURIComponent(id)}/export?format=${format}`, { binary: true }) }
  retryOperation(id: string) { return this.request<{ operation_id: string; state: string }>('POST', `/v1/operations/${encodeURIComponent(id)}/retry`) }
  blocks(space: string) { return this.request<Page<CoreBlock>>('GET', `/v1/spaces/${encodeURIComponent(space)}/blocks`) }
  putBlock(space: string, key: string, content: string, expectedVersion: number) {
    return this.request<Pick<CoreBlock, 'key' | 'content' | 'version'> & { space_id: string }>('PUT', `/v1/spaces/${encodeURIComponent(space)}/blocks/${encodeURIComponent(key)}`, { body: { content, expected_version: expectedVersion } })
  }
  principals() { return this.request<Page<Principal>>('GET', '/v1/principals') }
  createPrincipal(name: string, kind: 'human' | 'application' = 'application', options: { administrator?: boolean } = {}) {
    return this.request<Principal>('POST', '/v1/principals', { body: { name, kind, administrator: options.administrator ?? false } })
  }
  disablePrincipal(principal: string) { return this.request<{ id: string; disabled_at: string }>('POST', `/v1/principals/${encodeURIComponent(principal)}/disable`) }
  keys() { return this.request<Page<ApiKey>>('GET', '/v1/keys') }
  createKey(principal: string, name: string, expires_at?: string) { return this.request<ApiKey & { api_key: string }>('POST', `/v1/principals/${encodeURIComponent(principal)}/keys`, { body: { name, expires_at } }) }
  revokeKey(key: string) { return this.request<{ id: string; revoked_at: string }>('DELETE', `/v1/keys/${encodeURIComponent(key)}`) }
  grant(space: string, principal: string, role: Role) { return this.request('PUT', `/v1/spaces/${encodeURIComponent(space)}/grants/${encodeURIComponent(principal)}`, { body: { role } }) }
  revokeGrant(space: string, principal: string) { return this.request('DELETE', `/v1/spaces/${encodeURIComponent(space)}/grants/${encodeURIComponent(principal)}`) }
  exportObsidian(space_ids: string[] = [], review = false, all_accessible = false) { return this.request<ArrayBuffer>('POST', '/v1/exports', { body: { space_ids, review, all_accessible }, binary: true }) }
  connectors() { return this.request<Page<Connector>>('GET', '/v1/connectors') }
  createConnector(input: Pick<Connector, 'name' | 'provider' | 'principal_id' | 'access_mode'>) { return this.request<Connector>('POST', '/v1/connectors', { body: input }) }
  disableConnector(id: string) { return this.request<Connector>('DELETE', `/v1/connectors/${encodeURIComponent(id)}`) }
  enableConnector(id: string) { return this.request<Connector>('POST', `/v1/connectors/${encodeURIComponent(id)}/enable`) }
  connectorSyncStatus(id: string) { return this.request<ConnectorSyncStatus>('GET', `/v1/connectors/${encodeURIComponent(id)}/sync`) }
  sourceHealth() { return this.request<SourceHealth>('GET', '/v1/health/sources') }
  requestConnectorSync(id: string, expectedGeneration: number) { return this.request<ConnectorSyncStatus>('POST', `/v1/connectors/${encodeURIComponent(id)}/sync`, { body: { expected_generation: expectedGeneration } }) }
  connectorBindings(id: string) { return this.request<Page<ConnectorBinding>>('GET', `/v1/connectors/${encodeURIComponent(id)}/bindings`) }
  putConnectorBinding(id: string, input: ConnectorBinding) { return this.request('PUT', `/v1/connectors/${encodeURIComponent(id)}/bindings`, { body: input }) }
  removeConnectorBinding(id: string, input: ConnectorBinding) { return this.request('DELETE', `/v1/connectors/${encodeURIComponent(id)}/bindings`, { body: input }) }
  connectorScopes(id: string, after?: string) { return this.request<Page<ConnectorScope>>('GET', `/v1/connectors/${encodeURIComponent(id)}/scopes${after ? `?after=${encodeURIComponent(after)}` : ''}`) }
  pauseConnectorScope(space: string) { return this.request('POST', `/v1/connector-scopes/${encodeURIComponent(space)}/suspend`, { body: { reason: 'operator_paused' } }) }
  resumeConnectorScope(space: string) { return this.request('POST', `/v1/connector-scopes/${encodeURIComponent(space)}/resume`) }
  connectorProposals(space: string) { return this.request<Page<ConnectorProposal>>('GET', `/v1/spaces/${encodeURIComponent(space)}/connector-proposals`) }
  knowledge(input: { space_ids?: string[]; all_accessible?: boolean; subject?: string; limit?: number; include_historical?: boolean }) { return this.request<Knowledge>('POST', '/v1/knowledge', { body: input }) }
  resolveConnectorProposal(memory: string, input: { expected_version: number; proposal_hash: string; resolution: 'accept' | 'keep_local'; reason: string }) { return this.request('POST', `/v1/memories/${encodeURIComponent(memory)}/connector-proposal`, { body: input }) }
}
