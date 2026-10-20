import type { ContextPack, RecallHit, IndexState, RankingPolicy, SourceGrouping } from './index.js'

export type MetricOrigin = 'all' | 'interactive' | 'background' | 'evaluation'
export interface NamedCount { label: string; count: number }
export interface MetricValues {
  calls: number; failures: number; duration_ms: number; mean_ms: number | null; max_ms: number | null
  p50_upper_ms: number | null; p95_upper_ms: number | null; p99_upper_ms: number | null
  latency_histogram: number[]; input_bytes: number; output_bytes: number
  input_tokens: number; output_tokens: number; records: number; chunks: number
  empty_results: number; fallbacks: number; incomplete_index: number
}
export interface MetricGroup extends MetricValues { stage: string; mode: string; origin: string; generation_id: string }
export interface MetricPoint extends MetricValues { at: string; stage: string }
export interface QueueWork {
  kind: 'embed' | 'purge'; state: string; count: number; retried: number
  oldest_at: string | null; oldest_age_seconds: number | null
  due: number; input_bytes: number; largest_input_bytes: number
}
export interface Insights {
  space_id: string; observed_at: string; snapshot_at: string; snapshot_cache_seconds: number; generation_id: string
  memory: {
    active: number; ordinary: number; quarantined: number; eligible: number; indexed: number
    expired: number; future: number; content_bytes: number; duplicate_copies: number; deleted: number
    revisions: number; revision_bytes: number; sources: number; source_revisions: number
    source_bytes: number; attachment_bytes: number; distributions: Record<string, NamedCount[]>
  }
  queue: { state: string; count: number; retried: number; oldest_at: string | null; oldest_age_seconds: number | null }[]
  queue_work?: QueueWork[] | null
  generations: { id: string; model: string; dimensions: number; chunks: number; revisions: number; vector_bytes: number; active: boolean }[]
  source: {
    managed: boolean; operator_details_available: boolean; provider: string | null; connector_id: string | null
    observed_at: string | null; access_valid_until: string | null; completed_at: string | null
    operator_paused: boolean | null; items: NamedCount[]; runs: NamedCount[]
  }
  changes: { at: string; action: string; count: number }[]
  queue_latency: { completed_operations: number; p50_seconds: number | null; p95_seconds: number | null; max_seconds: number | null }
  metrics: {
    since: string; until: string; bucket_seconds: number; retention_days: number; origin: MetricOrigin
    histogram_upper_bounds_ms: (number | null)[]; groups: MetricGroup[]; series: MetricPoint[]
    truncated: boolean; recorded_calls: number; first_sample_at: string | null; last_sample_at: string | null
  }
  notices: string[]
}
export interface MemoryBudgetSnapshot {
  mode: 'auto' | 'manual'; requested_limit_mib: number | null; revision: string
  target_bytes: number; used_bytes: number; engine_bytes: number; database_bytes: number; desktop_bytes: number
  effective_hardware_bytes: number; available_hardware_bytes: number; system_reserve_bytes: number
  os_memory_limit_bytes: number | null; measurement_complete: boolean
  measurement: 'sum_of_process_resident_sets'; scope: 'local_engine_database_and_reported_desktop'; enforcement: 'cooperative'
  state: 'normal' | 'constrained' | 'paused'
  reason: 'policy_unavailable' | 'measurement_unavailable' | 'system_pressure' | 'working_set_over_budget' | 'model_exceeds_budget' | null
  background_paused: boolean; indexing_paused: boolean; minimum_model_budget_bytes: number
  batch_size: number; rejected_inferences: number; model_evictions: number
}
export interface ModelCacheSnapshot {
  scope: 'this_process'; local_model_owner?: 'this_process' | 'worker'; idle_seconds: number; idle_cleanup_enabled: boolean;
  idle_cleanup_running: boolean; idle_model_evictions: number; cleanup_failures: number; loaded_local_models: number
}
export interface RuntimeInsights {
  memory_budget?: MemoryBudgetSnapshot | null
  model_cache?: ModelCacheSnapshot | null
  shared_model_worker?: { scope: 'indexing_worker'; available: boolean; model_cache?: ModelCacheSnapshot | null;
    resources: RuntimeInsights['resources']; inference?: RuntimeInsights['inference'] } | null
  models?: { generation_id: string; model: string; model_loaded: boolean | null; configuration: Record<string, unknown>;
    provider: { requests: number; failed_requests: number; request_bytes: number; response_bytes: number; token_count_unit: string } | null }[]
  observed_at: string; scope: 'this_api_process'; model: string; generation_id: string; dimensions: number
  configuration: Record<string, unknown>; model_loaded: boolean | null; pool: Record<string, number>; notices: string[]
  telemetry: { started_at: string; buffered_series: number; series_capacity: number; dropped_samples: number
    persisted_samples: number; last_flush_at: string | null; flush_interval_seconds: number; retention_days: number }
  inference: { concurrency: number; queue_capacity: number; active: number; queued: number; completed: number
    failed: number; rejected: number; wait_ms: number; execution_ms: number } | null
  resources: { available: boolean; reason?: string; platform?: string; architecture?: string; rss_bytes?: number
    virtual_bytes?: number; cpu_seconds?: number; uptime_seconds?: number; threads?: number; logical_cpus?: number
    memory_limit_bytes?: number | null; cpu_limit_cores?: number | null; memory_current_bytes?: number | null; swap_limit_bytes?: number | null }
}
export type EvaluationMode = 'lexical' | 'semantic' | 'hybrid'
export type EvaluationSplit = 'development' | 'held_out'
export interface EvaluationCase {
  id: string; query: string; category?: string; split?: EvaluationSplit; unanswerable?: boolean
  references?: { memory_id: string; revision_id?: string | null; grade?: number }[]
  known_at?: string | null; valid_at?: string | null
}
export interface EvaluationDatasetInput { name: string; description?: string; cases: EvaluationCase[] }
export interface EvaluationDataset {
  id: string; name: string; description: string; version: number; content_hash: string
  state: 'active' | 'invalidated' | 'deleted'; case_count: number; development_count: number; held_out_count: number
  created_at: string; cases: EvaluationCase[] | null
}
export interface EvaluationInput {
  dataset_id: string; split?: EvaluationSplit; modes?: EvaluationMode[]; cutoffs?: number[]; context?: boolean
  token_budget?: number; max_seconds?: number; interval_seconds?: number
  embedding_generation?: string | null
  keyword_fallback?: boolean; ranking_policy?: RankingPolicy; max_per_source?: number
  sort?: 'relevance' | 'recent'
}
export interface EvaluationScores { recall: number | null; precision: number | null; ndcg: number | null; mrr: number | null; complete: boolean | null }
export interface EvaluationScoreSummary extends Omit<EvaluationScores, 'complete'> {
  n: number; complete: number; complete_rate: number | null; complete_wilson95: number[] | null; recall_bootstrap95: number[] | null
}
export interface EvaluationModeSummary {
  cases: number; successful: number; failed: number; answerable: number; unanswerable: number
  metrics: Record<string, EvaluationScoreSummary>; context_recall: number | null; context_complete: number; context_cases: number
  citations_checked: number; citations_invalid: number; citation_validity: number | null
  latency_p50_ms: number | null; latency_p95_ms: number | null; context_tokens: number; empty_results: number
}
export interface EvaluationSummary {
  scorer_version: string; modes: Partial<Record<EvaluationMode, EvaluationModeSummary>>
  categories: (EvaluationModeSummary & { mode: EvaluationMode; category: string })[]
  uncertainty: { bootstrap_resamples: number; seed: number; method: string; note: string }
  definitions: Record<string, string>; answer_quality: string
}
export interface EvaluationRun {
  id: string; space_id: string; dataset_id: string; generation_id: string
  state: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'invalidated'; progress: number; total: number
  configuration: Required<Omit<EvaluationInput, 'keyword_fallback' | 'ranking_policy' | 'max_per_source' | 'sort'>> & Pick<EvaluationInput, 'keyword_fallback' | 'ranking_policy' | 'max_per_source' | 'sort'>; summary: EvaluationSummary | null; error_code: string | null
  created_at: string; started_at: string | null; finished_at: string | null
  manifest: {
    version: number; scorer_version: string; dataset_hash: string; dataset_version: number; queued_service_version?: string
    generation: { id: string; model: string; dimensions: number; configuration: Record<string, unknown> }
    retrieval: string; selected_cases?: string[]; configuration: EvaluationInput
    corpus_start: string | null; corpus_end: string | null; corpus_changed: boolean | null; index_changed?: boolean
    index_start?: { sha256: string; records: number; indexed_records: number }
    index_end?: { sha256: string; records: number; indexed_records: number }
    frozen_manifest_hash?: string; execution: Record<string, unknown>
  }
}
export type AssessmentLabel = 'useful' | 'partially_useful' | 'not_useful' | 'correct_abstention' | 'incorrect_abstention'
export interface AssessmentInput { expected_recorded_at: string; expected_assessment_version?: number; label: AssessmentLabel; note?: string }
export interface EvaluationResult {
  position: number; case_id: string; mode: EvaluationMode; assessment_version: number
  human_assessment: { label: AssessmentLabel; note: string } | null; assessed_by: string | null; assessed_at: string | null; recorded_at: string
  result: { case_id: string; mode: EvaluationMode; category: string; unanswerable: boolean; status: 'completed' | 'failed'; error_code: string | null
    metrics: Record<string, EvaluationScores>; recall_ms?: number; context_ms?: number | null
    ranking?: (Pick<RecallHit, 'memory_id' | 'revision_id' | 'relevance_score' | 'ranking' | 'memory_span'> & { source_revision_id: string })[]
    ranking_reference_time?: string | null
    source_grouping?: SourceGrouping | null
    retrieval_service_version?: string
    context_recall?: number | null; context_complete?: boolean | null; context_tokens?: number
    context_citations?: ContextPack['citations']; citations_checked?: number; citations_invalid?: number
    index?: IndexState; warnings?: string[] }
}
export interface EvaluationResultPage { items: EvaluationResult[]; next_cursor: number | null }
export interface EvaluationComparison {
  baseline: EvaluationRun; candidate: EvaluationRun; comparable: boolean; reasons: string[]
  deltas: { mode: EvaluationMode; cutoff: number; metric: string; paired_cases: number; delta: number | null; paired_bootstrap95: number[] | null }[]
}
