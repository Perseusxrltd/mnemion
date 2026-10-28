from typing import Literal

from pydantic import Field

from .connector_models import ConnectorItemInput, SourceFileError
from .contracts import ResponseModel


class Connector(ResponseModel):
    id: str
    name: str
    provider: str
    principal_id: str
    access_mode: Literal["provider", "published"]
    disabled_at: str | None
    created_at: str


class Binding(ResponseModel):
    external_id: str
    principal_id: str
    role: Literal["reader", "reviewer"]


class SyncStatus(ResponseModel):
    connector_id: str
    requested_generation: int
    completed_generation: int
    requested_at: str | None
    completed_at: str | None
    pending: bool
    last_attempt_at: str | None
    last_successful: bool | None
    last_duration_seconds: float | None
    last_changed: int
    last_removed: int
    last_unchanged: int
    last_error_code: str | None
    scanned_commit: str | None = None
    scanned_at: str | None = None
    scanned_space_id: str | None = None


class BindingResult(Binding):
    connector_id: str
    removed: bool


class InventoryStatus(ResponseModel):
    incomplete_inventory: bool = False
    skipped_documents: int = 0
    file_errors: list[SourceFileError] = Field(default_factory=list)


class SourceDiagnostic(ResponseModel):
    space_id: str
    connector_id: str
    operator_id: str
    provider: Literal["filesystem", "git", "conversations", "gdrive", "slack", "rclone", "other"]
    operator_paused: bool
    skipped_documents: int
    reasons: list[
        Literal[
            "connector_disabled",
            "connector_identity_disabled",
            "connector_identity_not_dedicated",
            "operator_paused",
            "permissions_expired",
            "source_access_lost",
            "provider_unavailable",
            "permissions_recheck_required",
            "inventory_incomplete",
        ]
    ]
    recovery: Literal[
        "restore_connector_identity",
        "enable_connector",
        "resume_source",
        "request_source_sync",
        "repair_source_files",
    ]
    can_resume: bool
    can_request_sync: bool


class SourceDiagnostics(ResponseModel):
    visibility: Literal["tenant", "owned", "unavailable"]
    items: list[SourceDiagnostic]
    next_cursor: str | None


class SourceHealth(ResponseModel):
    unavailable_scopes: int
    incomplete_scopes: int
    skipped_documents: int
    attention: list[str]
    observed_at: str
    diagnostics: SourceDiagnostics | None = None


class ConnectorScope(ResponseModel):
    space_id: str
    connector_id: str
    external_id: str
    name: str | None = None
    operator_paused: bool
    observed_at: str
    access_valid_until: str
    suspended_at: str | None
    suspension_reason: str | None
    checkpoint: str | None
    completed_at: str | None
    access_current: bool
    inventory: InventoryStatus | None = None


class ScopePage(ResponseModel):
    items: list[ConnectorScope]
    next_cursor: str | None


class SuspendedScope(ResponseModel):
    space_id: str
    suspended: bool
    reason: str


class ConnectorRun(ResponseModel):
    id: str
    space_id: str
    mode: Literal["snapshot", "incremental"]
    state: Literal["running", "finalizing", "completed", "aborted"]
    next_sequence: int
    checkpoint: str | None
    lease_until: str
    created_at: str
    finished_at: str | None


class ItemResult(ResponseModel):
    external_id: str
    memory_id: str | None
    outcome: Literal["created", "revised", "unchanged", "deleted", "deletion_preserved", "conflict"]


class PageResult(ResponseModel):
    run_id: str
    sequence: int
    next_sequence: int
    items: list[ItemResult]


class SyncResult(InventoryStatus):
    run_id: str
    space_id: str
    state: Literal["finalizing", "completed"]
    pages: int
    removed: int
    checkpoint_committed: bool


class Proposal(ResponseModel):
    memory_id: str
    proposal_hash: str
    payload: ConnectorItemInput
    created_at: str
    version: int


class ProposalResult(ResponseModel):
    memory_id: str
    resolution: Literal["accept", "keep_local"]
