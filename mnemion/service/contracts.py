"""Versioned response contract shared by HTTP, the Python SDK, and MCP.

Additional response fields are forward compatible; command fields are strict.
Identifiers and timestamps remain strings in clients, exactly as on the wire.
"""

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from .models import ClaimStatus, MemoryKind, RankingPolicy, Role

OperationState = Literal["accepted", "indexing", "ready", "failed", "cancelled"]
ReviewState = Literal["ordinary", "quarantined"]
T = TypeVar("T")


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Page(ResponseModel, Generic[T]):
    items: list[T]


class ErrorDetail(ResponseModel):
    code: str
    message: str


class ErrorResponse(ResponseModel):
    error: ErrorDetail
    request_id: str


class LiveStatus(ResponseModel):
    status: Literal["alive"]
    api_version: Literal["v1"]
    service_version: str | None = None


class ReadyStatus(ResponseModel):
    status: Literal["ready"]
    generation_id: str
    service_version: str | None = None


class Receipt(ResponseModel):
    operation_id: str
    memory_id: str
    revision_id: str | None = None
    space_id: str
    state: OperationState
    version: int | None = None
    lexical_ready: bool = False
    semantic_ready: bool = False
    generation_id: str | None = None
    deleted: bool = False


class Evidence(ResponseModel):
    source_id: str
    source_revision_id: str
    title: str
    uri: str | None = None
    media_type: str
    content_hash: str
    start: int
    end: int
    offset_unit: Literal["unicode_codepoints"]
    excerpt: str
    excerpt_truncated: bool = False


class MemoryMetadata(ResponseModel):
    memory_id: str
    revision_id: str
    space_id: str
    version: int
    revision_version: int
    content_hash: str
    subject: str | None = None
    kind: MemoryKind
    metadata: dict[str, Any] = Field(default_factory=dict)
    claim_status: ClaimStatus
    review_state: ReviewState
    recorded_at: str
    valid_from: str | None = None
    valid_to: str | None = None
    created_at: str
    updated_at: str
    created_by: str
    evidence: Evidence


class Memory(MemoryMetadata):
    content: str
    can_forget: bool | None = Field(
        default=None,
        description="Current withdrawal permission for a fetched memory. Missing/null on older services or views without a permission observation; the write rechecks authorization.",
    )


class MemoryPage(Page[Memory]):
    next_cursor: str | None


class Span(ResponseModel):
    start: int
    end: int
    offset_unit: Literal["unicode_codepoints"]


class IdentifierRanking(ResponseModel):
    rank: int = Field(ge=1)
    label_rank: int | None = Field(default=None, ge=1)
    matched: int = Field(ge=1, le=8)
    requested: int = Field(ge=1, le=8)
    label_matches: int = Field(ge=0, le=8)
    weight: float = Field(gt=0)
    label_weight: float = Field(gt=0)


class RankingAdjustment(ResponseModel):
    score: float = Field(ge=0, le=1)
    date: str
    age_days: float = Field(ge=0)
    recency_factor: float = Field(ge=0, le=1)
    archive_factor: float = Field(ge=0, le=1)
    archive_segment: str | None = None


class KeywordRanking(ResponseModel):
    rank: int = Field(ge=1)
    matched: int = Field(ge=1, le=24)
    requested: int = Field(ge=2, le=24)
    terms: list[str]
    weight: float = Field(gt=0, le=1)


class Ranking(ResponseModel):
    ranks: dict[Literal["lexical", "semantic"], int]
    rrf: float
    lexical_rank: float | None
    cosine_similarity: float | None
    identifier: IdentifierRanking | None = None
    adjustment: RankingAdjustment | None = None
    keywords: KeywordRanking | None = None


class RecallHit(MemoryMetadata):
    text: str
    text_truncated: bool
    memory_span: Span
    relevance_score: float
    score_method: Literal["normalized_rrf_k60"]
    ranking: Ranking


class IndexState(ResponseModel):
    generation_id: str | None
    generation_ids: list[str] = Field(default_factory=list)
    space_generations: dict[str, str] = Field(default_factory=dict)
    eligible_records: int
    indexed_records: int
    pending_records: int
    observed_at: str


class SourceGrouping(ResponseModel):
    max_per_source: int = Field(ge=0, le=50)
    grouped_candidates: int = Field(ge=0)
    scope: Literal["candidate_window"] = "candidate_window"


class Recall(ResponseModel):
    request_id: str
    query: str
    hits: list[RecallHit]
    warnings: list[str]
    index: IndexState
    timing_ms: float
    score_description: str
    match_status: Literal["matched", "semantic_only", "empty"] = "matched"
    filtered_candidates: int = Field(default=0, ge=0)
    ranking_policy: RankingPolicy | None = None
    ranking_reference_time: str | None = None
    source_grouping: SourceGrouping | None = None


class Citation(ResponseModel):
    number: int
    memory_id: str
    revision_id: str
    space_id: str
    source_revision_id: str
    source_start: int
    source_end: int
    memory_span: Span


class IncludedBlock(ResponseModel):
    space_id: str
    key: str
    version: int


class ContextPack(ResponseModel):
    source_grouping: SourceGrouping | None = None
    request_id: str
    text: str
    citations: list[Citation]
    core_blocks: list[IncludedBlock]
    token_count: int
    token_budget: int
    tokenizer: str
    tokenizer_generation: str
    token_count_unit: Literal["model_tokens", "utf8_bytes"] = "model_tokens"
    omitted_items: int
    warnings: list[str]
    index: IndexState


class IdentityInfo(ResponseModel):
    principal_id: str
    tenant_id: str
    name: str
    tenant_name: str
    kind: Literal["human", "application"]
    administrator: bool
    service_version: str | None = Field(
        default=None,
        description="Version of the authenticated workspace service, independent of the client app.",
    )


class Space(ResponseModel):
    id: str
    name: str
    description: str
    role: Role | None
    created_at: str


class Principal(ResponseModel):
    id: str
    name: str
    kind: Literal["human", "application"]
    administrator: bool
    disabled_at: str | None
    created_at: str


class DisabledPrincipal(ResponseModel):
    id: str
    disabled_at: str


class ApiKey(ResponseModel):
    id: str
    principal_id: str
    name: str
    prefix: str
    expires_at: str | None
    revoked_at: str | None
    created_at: str


class CreatedKey(ApiKey):
    api_key: str


class RevokedKey(ResponseModel):
    id: str
    revoked_at: str


class Grant(ResponseModel):
    principal_id: str
    name: str
    kind: Literal["human", "application"]
    role: Role
    created_at: str


class GrantResult(ResponseModel):
    space_id: str
    principal_id: str
    role: Role


class RevokedGrant(ResponseModel):
    space_id: str
    principal_id: str
    revoked: Literal[True]


class ReviewResult(ResponseModel):
    memory_id: str
    version: int
    review_state: ReviewState


class Attachment(ResponseModel):
    attachment_id: str
    name: str
    media_type: str
    content_hash: str
    size_bytes: int


class Source(ResponseModel):
    source_revision_id: str
    source_id: str
    space_id: str
    content: str
    content_hash: str
    media_type: str
    recorded_at: str
    title: str
    uri: str | None
    attachments: list[Attachment] = Field(default_factory=list)


class Operation(ResponseModel):
    operation_id: str
    memory_id: str | None
    revision_id: str | None
    space_id: str
    kind: Literal["ingest", "revise", "delete", "reindex"]
    state: OperationState
    error_code: str | None
    created_at: str
    updated_at: str
    memory_deleted: bool = False


class AuditEvent(ResponseModel):
    id: str
    space_id: str | None
    principal_id: str
    action: str
    resource_id: str
    details: dict[str, Any]
    reason: str | None
    created_at: str


class RetryResult(ResponseModel):
    operation_id: str
    state: Literal["accepted"]


class CoreBlock(ResponseModel):
    key: str
    content: str
    version: int
    updated_at: str
    updated_by: str


class BlockResult(ResponseModel):
    space_id: str
    key: str
    content: str
    version: int


class QueueState(ResponseModel):
    state: OperationState
    count: int
    oldest: str | None


class SpaceStatus(ResponseModel):
    space_id: str
    memories: int
    operations: list[QueueState]
    generation_id: str
