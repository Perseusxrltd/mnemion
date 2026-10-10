"""Versioned connector protocol. Provider credentials never enter these commands."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .models import Command, MemoryInput

ExternalID = Annotated[str, Field(min_length=1, max_length=512, pattern=r"^[^\x00-\x1f]+$")]


class ConnectorInput(Command):
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    principal_id: UUID
    access_mode: Literal["provider", "published"] = "provider"


class BindingInput(Command):
    external_id: ExternalID
    principal_id: UUID
    role: Literal["reader", "reviewer"] = "reader"


class SyncRequestInput(Command):
    expected_generation: int = Field(ge=0, le=9007199254740991)


class SyncReportInput(Command):
    generation: int = Field(ge=0, le=9007199254740991)
    successful: bool
    duration_seconds: float = Field(ge=0, le=604800, allow_inf_nan=False)
    changed: int = Field(default=0, ge=0, le=9007199254740991)
    removed: int = Field(default=0, ge=0, le=9007199254740991)
    unchanged: int = Field(default=0, ge=0, le=9007199254740991)
    error_code: (
        Literal[
            "incomplete_inventory", "provider_unavailable", "service_unavailable", "connector_busy"
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def valid_result(self):
        if self.successful != (self.error_code is None):
            raise ValueError("Failed scans require a bounded error code; successful scans omit it")
        return self


class ScopeInput(Command):
    external_id: ExternalID
    name: str = Field(min_length=1, max_length=200)
    members: list[ExternalID] = Field(max_length=10000)
    observed_at: AwareDatetime
    lease_seconds: int = Field(default=900, ge=60, le=86400)


class SuspensionInput(Command):
    reason: Literal["access_lost", "provider_unavailable", "operator_paused"]


class RunInput(Command):
    run_id: UUID
    mode: Literal["snapshot", "incremental"] = "snapshot"


class ConnectorItemInput(Command):
    external_id: ExternalID
    revision: str = Field(min_length=1, max_length=512)
    action: Literal["upsert", "delete"] = "upsert"
    memory: MemoryInput | None = None

    @model_validator(mode="after")
    def valid_item(self):
        if (self.action == "upsert") != (self.memory is not None):
            raise ValueError("Upserts require evidence; deletion events must omit content")
        if self.memory and self.memory.claim_status != "observed":
            raise ValueError("Connectors cannot verify their own source claims")
        return self


class BatchInput(Command):
    sequence: int = Field(ge=0)
    items: list[ConnectorItemInput] = Field(max_length=50)
    # Opaque cursors stay scoped to the connector operator. Never store tokens here.
    checkpoint: str | None = Field(default=None, max_length=8192)

    @model_validator(mode="after")
    def distinct_items(self):
        identifiers = [item.external_id for item in self.items]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("A page cannot contain the same source identity twice")
        return self


class FinishInput(Command):
    complete_inventory: bool = False


class ResolveInput(Command):
    expected_version: int = Field(ge=1)
    proposal_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    resolution: Literal["accept", "keep_local"]
    reason: str = Field(min_length=1, max_length=1000)


def utc_now() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc)
