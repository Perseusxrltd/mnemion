"""Explicit custody consent and bounded, immutable selected-evidence pages."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from ..capture_identity import canonical_capture_json
from ..capture_policy import CapturePolicy
from .connector_models import ConnectorItemInput, ExternalID
from .contracts import ResponseModel
from ..capture_coverage import Cursor, Generation, IndexCounts, utc_timestamp
from .models import Command

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
ProducerScope = Annotated[str, Field(pattern=r"^conversation:[a-f0-9]{64}$")]


class CaptureSourceInput(Command):
    expected_version: int = Field(default=0, ge=0)
    namespace: str = Field(min_length=1, max_length=400)
    name: str = Field(min_length=1, max_length=200)
    members: list[ExternalID] = Field(max_length=128)
    capture_mode: Literal["messages", "complete"]
    keep_accepted: Literal[True]
    capture_policy: CapturePolicy | None = None

    @model_validator(mode="after")
    def distinct_members(self):
        if self.capture_policy is not None and (
            self.capture_policy.capture_mode != self.capture_mode
            or not self.capture_policy.keeps_accepted
        ):
            raise ValueError("Capture custody requires its approved content and retention policy")
        if len(set(self.members)) != len(self.members):
            raise ValueError("Choose distinct mapped members")
        return self


class CaptureGrantInput(Command):
    device_key_id: UUID
    previous_grant_id: UUID | None = None
    confirm_previous_policy: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def reviewed_recovery(self):
        if bool(self.previous_grant_id) != self.confirm_previous_policy:
            raise ValueError("Explicitly approve the previous device's original capture policy")
        return self


class CapturePolicyChange(Command):
    expected_version: int = Field(ge=1, strict=True)
    review_token: Digest
    capture_policy: CapturePolicy
    previous_grants: Literal["retain", "revoke"]
    confirm: bool = Field(strict=True)

    @model_validator(mode="after")
    def consent(self):
        if not self.confirm or not self.capture_policy.keeps_accepted:
            raise ValueError("Approve retained capture and the treatment of existing device grants")
        return self


class CaptureEvent(Command):
    event_id: Digest
    producer_scope: ProducerScope
    item: ConnectorItemInput

    @model_validator(mode="after")
    def evidence_only(self):
        if self.item.action != "upsert":
            raise ValueError("Capture pages contain only selected evidence upserts")
        return self


class CapturePageInput(Command):
    page_id: UUID
    events: list[CaptureEvent] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def bounded_unique(self):
        if len({event.event_id for event in self.events}) != len(self.events):
            raise ValueError("A capture page cannot repeat an event")
        if len(canonical_capture_json(self.model_dump(mode="json"))) > 1_500_000:
            raise ValueError("A capture page exceeds the 1.5 MB limit")
        return self


class CaptureSource(ResponseModel):
    version: int
    policy_version: int = 1
    source_id: str
    connector_id: str
    space_id: str
    namespace: str
    name: str
    members: list[str]
    capture_mode: Literal["messages", "complete"]
    capture_policy: CapturePolicy | None = None
    keep_accepted: Literal[True] = True
    revoked_at: str | None
    has_capture_history: bool = False


class CaptureGrant(ResponseModel):
    grant_id: str
    source_id: str
    connector_id: str
    space_id: str
    tenant_id: str
    device_key_id: str
    namespace: str
    capture_mode: Literal["messages", "complete"]
    capture_policy: CapturePolicy | None = None
    policy_version: int = 1
    revoked_at: str | None
    source_revoked_at: str | None
    active: bool


class CaptureSourcePage(ResponseModel):
    items: list[CaptureSource]
    next_cursor: str | None


class CaptureDeviceSummary(ResponseModel):
    grant_id: str
    device_key_id: str
    device_name: str
    policy_version: int
    created_at: str
    active: bool


class CapturePolicyReview(ResponseModel):
    source: CaptureSource
    review_token: str
    unrevoked_grants: int
    active_grants: int
    devices: list[CaptureDeviceSummary]
    next_cursor: str | None


class CapturePolicyVersion(ResponseModel):
    source_id: str
    policy_version: int
    capture_mode: Literal["messages", "complete"]
    capture_policy: CapturePolicy | None
    created_at: str
    transition_id: str | None = None
    previous_grants: Literal["retain", "revoke"] | None = None
    affected_grants: int | None = None
    approved_by: str | None = None


class CaptureRetentionStatus(ResponseModel):
    source_id: str
    observed_at: str
    families: int
    pending_families: int
    due_families: int
    expired_families: int
    failed_families: int
    purges_pending: int
    next_deadline: str | None
    last_cleanup_at: str | None
    error_code: str | None
    semantics: Literal["scheduled_cleanup"]
    backup_erasure: Literal["not_included"]


class CapturePolicyVersionPage(ResponseModel):
    items: list[CapturePolicyVersion]
    next_cursor: int | None


class CapturePolicyChanged(ResponseModel):
    source: CaptureSource
    transition: CapturePolicyVersion


class CaptureEventReceipt(ResponseModel):
    event_id: str
    lineage_id: str
    memory_id: str | None
    operation_id: str | None
    outcome: Literal["stored", "forgotten"]


class CapturePageReceipt(ResponseModel):
    page_id: str
    grant_id: str
    source_id: str
    durable: Literal[True] = True
    items: list[CaptureEventReceipt]


class CaptureFence(ResponseModel):
    lineage_id: str
    forgotten_at: str


class CaptureFencePage(ResponseModel):
    items: list[CaptureFence]
    next_cursor: str | None


class CaptureIndexPage(ResponseModel):
    source_id: str
    grant_id: str
    generation_id: Generation
    inference_paused: bool
    observed_at: str
    after: Cursor | None
    counts: IndexCounts
    next_cursor: Cursor | None

    _timestamp = field_validator("observed_at")(utc_timestamp)

    @model_validator(mode="after")
    def advancing(self):
        if (
            self.counts.events > 1000
            or self.next_cursor
            and (not self.counts.events or self.after and self.next_cursor <= self.after)
        ):
            raise ValueError("Use a bounded, advancing index observation page")
        return self
