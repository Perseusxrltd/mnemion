"""Transport-neutral validated commands. Identity always comes from credentials."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

Role = Literal["reader", "contributor", "reviewer", "administrator"]
ClaimStatus = Literal["observed", "verified", "contested", "superseded", "retracted"]
MemoryKind = Literal["fact", "event", "preference", "procedure", "note"]
Content = Annotated[str, Field(min_length=1, max_length=65536)]


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def reject_nul(cls, value: Any) -> Any:
        if isinstance(value, str) and "\0" in value:
            raise ValueError("Null characters are not supported")
        return value


class SourceInput(Command):
    title: str = Field(default="Captured evidence", min_length=1, max_length=300)
    uri: str | None = Field(default=None, max_length=4096)
    content: str | None = Field(default=None, min_length=1, max_length=1_000_000)
    media_type: Literal["text/plain", "text/markdown"] = "text/plain"
    start: int = Field(default=0, ge=0)
    end: int | None = Field(default=None, ge=0)


class MemoryInput(Command):
    content: Content
    kind: MemoryKind = "fact"
    subject: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: SourceInput | None = None
    claim_status: ClaimStatus = "observed"
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None

    @field_validator("content")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Memory content must contain text")
        return value

    @field_validator("metadata")
    @classmethod
    def small_json(cls, value: dict) -> dict:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > 16384 or "\\u0000" in encoded:
            raise ValueError("Metadata must be valid JSON smaller than 16 KiB, without null bytes")
        return value

    @model_validator(mode="after")
    def evidence_and_time(self) -> MemoryInput:
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must follow valid_from")
        if self.source and self.source.content is not None:
            end = self.source.end if self.source.end is not None else len(self.source.content)
            if not self.source.start < end <= len(self.source.content):
                raise ValueError("Source offsets must identify a nonempty Unicode character span")
        elif self.source and (self.source.start or self.source.end is not None):
            raise ValueError("Explicit source offsets require source content")
        return self


class RevisionInput(MemoryInput):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class ReviewInput(Command):
    expected_version: int = Field(ge=1)
    state: Literal["ordinary", "quarantined"]
    reason: str = Field(min_length=1, max_length=1000)


class SpaceSelection(Command):
    space_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    all_accessible: bool = False

    @model_validator(mode="after")
    def explicit_selection(self):
        if bool(self.space_ids) == self.all_accessible:
            raise ValueError("Select explicit spaces or all_accessible, but not both")
        self.space_ids = list(dict.fromkeys(self.space_ids))
        return self


class RecallInput(SpaceSelection):
    query: str = Field(min_length=1, max_length=4000)
    subject: str | None = Field(default=None, max_length=500)
    kinds: list[MemoryKind] | None = Field(default=None, max_length=5)
    limit: int = Field(default=10, ge=1, le=50)
    mode: Literal["hybrid", "lexical", "semantic"] = "hybrid"
    valid_at: AwareDatetime | None = None
    known_at: AwareDatetime | None = None
    include_contested: bool = True
    metadata_filter: dict[str, str | int | bool] = Field(default_factory=dict, max_length=10)
    embedding_generation: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @field_validator("metadata_filter")
    @classmethod
    def bounded_filter(cls, value: dict) -> dict:
        return MemoryInput.small_json(value)

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Query must contain text")
        return value

    @field_validator("space_ids")
    @classmethod
    def distinct_spaces(cls, value: list[UUID]) -> list[UUID]:
        return list(dict.fromkeys(value))


class ContextInput(RecallInput):
    token_budget: int = Field(default=2048, ge=64, le=32768)


class ExportInput(SpaceSelection):
    review: bool = False


class SpaceInput(Command):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class PrincipalInput(Command):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["human", "application"] = "application"
    administrator: bool = False


class KeyInput(Command):
    name: str = Field(min_length=1, max_length=200)
    expires_at: AwareDatetime | None = None


class GrantInput(Command):
    role: Role


class BlockInput(Command):
    content: str = Field(max_length=16000)
    expected_version: int = Field(ge=0)


def json_value(value: Any) -> Any:
    """JSON-safe values for receipts persisted before returning to a transport."""
    return json.loads(
        json.dumps(value, default=lambda x: x.isoformat() if isinstance(x, datetime) else str(x))
    )
