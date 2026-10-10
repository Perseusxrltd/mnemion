"""Bounded librarian commands, model output and review contracts."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from .contracts import ResponseModel
from .models import Command

Mode = Literal["organize", "review"]
ProposalKind = Literal["organize", "duplicate", "contradiction", "stale", "link"]
RunState = Literal["queued", "running", "completed", "failed", "cancelled"]
ProposalState = Literal["pending", "accepted", "rejected", "undone", "invalidated"]
Tag = Annotated[str, Field(min_length=1, max_length=60)]
PIPELINE_VERSION = "mnemion-librarian-1"


class OrganizationChanges(Command):
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    tags: list[Tag] | None = Field(default=None, max_length=16)
    summary: str | None = Field(default=None, min_length=1, max_length=1500)

    @model_validator(mode="after")
    def meaningful(self):
        if not (self.subject or self.tags or self.summary):
            raise ValueError("An organization proposal needs a change")
        if any(
            not value.strip()
            for value in [self.subject or "-", self.summary or "-", *(self.tags or [])]
        ):
            raise ValueError("Organization changes must contain text")
        if self.tags and len({tag.casefold() for tag in self.tags}) != len(self.tags):
            raise ValueError("Tags must be distinct")
        return self


class EvidenceQuote(Command):
    memory_id: UUID
    quote: str = Field(min_length=1, max_length=1000)


class LibrarianSuggestion(Command):
    kind: ProposalKind
    memory_id: UUID
    related_ids: list[UUID] = Field(default_factory=list, max_length=11)
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: Literal["low", "medium", "high"]
    evidence: list[EvidenceQuote] = Field(min_length=1, max_length=12)
    changes: OrganizationChanges | None = None

    @model_validator(mode="after")
    def coherent(self):
        if (
            len(set(self.related_ids)) != len(self.related_ids)
            or self.memory_id in self.related_ids
        ):
            raise ValueError("Related memories must be distinct from the target")
        if self.kind == "organize":
            if self.changes is None or self.related_ids:
                raise ValueError("Organization changes use only the target's own evidence")
        elif self.changes is not None:
            raise ValueError("Findings cannot modify canonical memories")
        if self.kind in {"duplicate", "contradiction", "link"} and not self.related_ids:
            raise ValueError("This finding needs related memories")
        if not self.rationale.strip():
            raise ValueError("A proposal needs a rationale")
        return self


class LibrarianOutput(Command):
    proposals: list[LibrarianSuggestion] = Field(max_length=12)


class LibrarianSettingsInput(Command):
    expected_version: StrictInt = Field(ge=0)
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    enabled: StrictBool = True
    approve_network_egress: StrictBool = False
    mode: Mode = "organize"
    max_memories: StrictInt = Field(default=4, ge=1, le=12)
    max_calls_per_day: StrictInt = Field(default=24, ge=1, le=1000)
    interval_minutes: StrictInt | None = Field(default=None, ge=60, le=10080)


class LibrarianRunInput(Command):
    mode: Mode = "organize"
    memory_ids: list[UUID] = Field(default_factory=list, max_length=12)

    @field_validator("memory_ids")
    @classmethod
    def unique_memories(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Select distinct memories")
        return value


class LibrarianDecision(Command):
    expected_version: StrictInt = Field(ge=1)
    action: Literal["accept", "reject", "undo"]


class LibrarianChoice(ResponseModel):
    id: str
    label: str
    model: str
    revision: str
    fingerprint: str
    protocol: Literal["openai", "ollama"]
    endpoint_origin: str
    network_egress: bool
    context_budget: int
    token_count_unit: Literal["model_tokens", "utf8_bytes"]
    max_output_tokens: int
    timeout_seconds: int


class LibrarianSettings(ResponseModel):
    space_id: str
    version: int
    profile_id: str | None
    profile_fingerprint: str | None
    profile_available: bool
    enabled: bool
    network_egress_approved: bool
    mode: Mode
    max_memories: int
    max_calls_per_day: int
    interval_minutes: int | None
    next_run_at: str | None
    calls_reserved_today: int
    pending_proposals: int
    updated_at: str | None


class LibrarianRun(ResponseModel):
    id: str
    space_id: str
    profile_id: str
    profile_fingerprint: str
    mode: Mode
    state: RunState
    configuration: dict
    selected: int
    processed: int
    skipped: int
    proposal_count: int
    calls_reserved: int
    calls_completed: int
    input_units: int
    output_tokens: int | None
    request_bytes: int
    response_bytes: int
    latency_ms: float
    error_code: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


class LibrarianReference(ResponseModel):
    memory_id: str
    revision_id: str
    memory_version: int


class LibrarianRunItem(LibrarianReference):
    position: int
    state: Literal["pending", "completed", "skipped"]
    reason: str | None


class LibrarianProposal(ResponseModel):
    id: str
    run_id: str
    memory_id: str
    state: ProposalState
    version: int
    suggestion: LibrarianSuggestion | None
    references: list[LibrarianReference]
    before: dict | None
    applicable: bool
    unavailable_reason: str | None
    applied_revision_id: str | None
    created_at: str
    decided_at: str | None


class LibrarianDecisionReceipt(ResponseModel):
    proposal_id: str
    state: ProposalState
    version: int
    applied_revision_id: str | None
