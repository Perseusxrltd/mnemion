"""Lightweight diagnostics response contracts shared by SDKs and the service."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .contracts import ResponseModel


class Count(ResponseModel):
    label: str
    count: int


class MemoryHealth(ResponseModel):
    active: int
    ordinary: int
    quarantined: int
    eligible: int
    indexed: int
    expired: int
    future: int
    content_bytes: int
    duplicate_copies: int
    deleted: int
    revisions: int
    revision_bytes: int
    sources: int
    source_revisions: int
    source_bytes: int
    attachment_bytes: int
    distributions: dict[str, list[Count]]


class QueueRow(ResponseModel):
    state: str
    count: int
    retried: int
    oldest_at: str | None
    oldest_age_seconds: float | None


class QueueWork(QueueRow):
    kind: Literal["embed", "purge"]
    due: int
    input_bytes: int
    largest_input_bytes: int


class GenerationRow(ResponseModel):
    id: str
    model: str
    dimensions: int
    chunks: int
    revisions: int
    vector_bytes: int
    active: bool


class SourceHealth(ResponseModel):
    managed: bool
    operator_details_available: bool
    provider: str | None = None
    connector_id: str | None = None
    observed_at: str | None = None
    access_valid_until: str | None = None
    completed_at: str | None = None
    operator_paused: bool | None = None
    items: list[Count]
    runs: list[Count]


class ChangePoint(ResponseModel):
    at: str
    action: str
    count: int


class QueueLatency(ResponseModel):
    completed_operations: int
    p50_seconds: float | None
    p95_seconds: float | None
    max_seconds: float | None


class MetricValues(ResponseModel):
    calls: int
    failures: int
    duration_ms: float
    mean_ms: float | None
    max_ms: float | None
    p50_upper_ms: float | None
    p95_upper_ms: float | None
    p99_upper_ms: float | None
    latency_histogram: list[int]
    input_bytes: int
    output_bytes: int
    input_tokens: int
    output_tokens: int
    records: int
    chunks: int
    empty_results: int
    fallbacks: int
    incomplete_index: int


class MetricGroup(MetricValues):
    stage: str
    mode: str
    origin: str
    generation_id: str


class MetricPoint(MetricValues):
    at: str
    stage: str


class MetricsWindow(ResponseModel):
    since: str
    until: str
    bucket_seconds: int
    retention_days: int
    origin: str
    histogram_upper_bounds_ms: list[int | None]
    groups: list[MetricGroup]
    series: list[MetricPoint]
    truncated: bool
    recorded_calls: int
    first_sample_at: str | None
    last_sample_at: str | None


class Insights(ResponseModel):
    space_id: str
    observed_at: str
    snapshot_at: str
    snapshot_cache_seconds: int
    generation_id: str
    memory: MemoryHealth
    queue: list[QueueRow]
    queue_work: list[QueueWork] | None = None
    generations: list[GenerationRow]
    source: SourceHealth
    changes: list[ChangePoint]
    queue_latency: QueueLatency
    metrics: MetricsWindow
    notices: list[str]


class MemoryBudgetSnapshot(ResponseModel):
    mode: Literal["auto", "manual"]
    requested_limit_mib: int | None
    revision: str
    target_bytes: int
    used_bytes: int
    engine_bytes: int
    database_bytes: int
    desktop_bytes: int
    effective_hardware_bytes: int
    available_hardware_bytes: int
    system_reserve_bytes: int
    os_memory_limit_bytes: int | None
    measurement_complete: bool
    measurement: Literal["sum_of_process_resident_sets"]
    scope: Literal["local_engine_database_and_reported_desktop"]
    enforcement: Literal["cooperative"]
    state: Literal["normal", "constrained", "paused"]
    reason: (
        Literal[
            "policy_unavailable",
            "measurement_unavailable",
            "system_pressure",
            "working_set_over_budget",
            "model_exceeds_budget",
        ]
        | None
    )
    background_paused: bool
    indexing_paused: bool
    minimum_model_budget_bytes: int
    batch_size: int
    rejected_inferences: int
    model_evictions: int


class ModelCacheSnapshot(ResponseModel):
    scope: Literal["this_process"]
    local_model_owner: Literal["this_process", "worker"] = "this_process"
    idle_seconds: int = Field(ge=0, le=86400)
    idle_cleanup_enabled: bool
    idle_cleanup_running: bool
    idle_model_evictions: int = Field(ge=0)
    cleanup_failures: int = Field(ge=0)
    loaded_local_models: int = Field(ge=0)


class SharedModelWorkerSnapshot(ResponseModel):
    scope: Literal["indexing_worker"]
    available: bool
    model_cache: ModelCacheSnapshot | None = None
    resources: dict = Field(default_factory=dict)
    inference: dict | None = None


class RuntimeInsights(ResponseModel):
    observed_at: str
    scope: Literal["this_api_process"]
    telemetry: dict
    inference: dict | None
    model_loaded: bool | None
    model: str
    generation_id: str
    dimensions: int
    configuration: dict
    models: list[dict] = Field(default_factory=list)
    pool: dict
    resources: dict
    memory_budget: MemoryBudgetSnapshot | None = None
    shared_model_worker: SharedModelWorkerSnapshot | None = None
    model_cache: ModelCacheSnapshot | None = None
    notices: list[str] = Field(default_factory=list)
