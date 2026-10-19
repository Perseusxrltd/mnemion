"""Bounded, reviewed recovery of the external prototype's JSONL records."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, SecretStr, StrictBool, field_validator

from .models import Command, Content


class LegacyBufferRecord(Command):
    id: UUID
    ts: AwareDatetime
    desk: str = Field(min_length=1, max_length=120)
    kind: Literal["memory", "action"]
    text: Content
    subject: str | None = Field(default=None, max_length=500)
    important: StrictBool = False
    journal: str | None = Field(default=None, max_length=1024)

    @field_validator("ts", mode="before")
    @classmethod
    def original_timestamp(cls, value):
        if not isinstance(value, str):
            raise ValueError("Use the original ISO timestamp with its time zone")
        return value


class BufferPreviewInput(Command):
    namespace: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    jsonl: SecretStr = Field(
        max_length=1048576,
        description="Complete UTF-8 JSONL records, at most 1 MiB and 100 unique records. Never send encrypted bytes as text.",
    )
    withdrawn_ids: list[UUID] = Field(
        max_length=1000,
        description="Explicitly reconciled withdrawals, including IDs absent from this batch. The prototype has no trustworthy built-in deletion ledger.",
    )
    reject_personal_data: StrictBool = True


class BufferImportInput(BufferPreviewInput):
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewed_withdrawals: Literal[True]
    acknowledge_source_only: Literal[True]


class BufferPlanItem(Command):
    legacy_id: UUID
    memory_id: UUID
    action: Literal[
        "create",
        "already_imported",
        "preserved_changes",
        "withdrawn",
        "withdraw",
        "deny",
        "conflict",
        "rejected",
    ]
    version: int | None = None
    code: str | None = None


class BufferPreview(Command):
    namespace: str
    space_id: UUID
    preview_sha256: str
    input_sha256: str
    can_import: bool
    duplicates: int
    writers: list[str]
    items: list[BufferPlanItem]
    counts: dict[str, int]
    source_only: Literal[True] = True
    remote_delivery_verified: Literal[False] = False


class BufferImported(Command):
    namespace: str
    space_id: UUID
    preview_sha256: str
    counts: dict[str, int]
    items: list[BufferPlanItem]
    source_only: Literal[True] = True
    remote_delivery_verified: Literal[False] = False
