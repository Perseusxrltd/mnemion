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
            or self.capture_policy.retention != "until_deleted"
        ):
            raise ValueError("Capture custody requires its approved content and retention policy")
        if len(set(self.members)) != len(self.members):
            raise ValueError("Choose distinct mapped members")
        return self


class CaptureGrantInput(Command):
    device_key_id: UUID


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
    revoked_at: str | None
    source_revoked_at: str | None
    active: bool


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
