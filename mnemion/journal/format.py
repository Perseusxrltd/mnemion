"""Versioned journal records; source identities never become local permissions."""

from __future__ import annotations

from datetime import timezone
import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, field_validator, model_validator

from ..service.models import Command, Content, MemoryInput, MemoryKind

FORMAT = "mnemion-memory-journal"
MAX_LINE_BYTES = 384 * 1024
MAX_FILE_BYTES = 20_000_000


def journal_candidate(path: str, text: str) -> bool:
    # Even a malformed purported journal must not fall through to raw-text
    # import: an ignored denial could otherwise resurrect its older records.
    return path.lower().endswith(".jsonl") and FORMAT in text[:MAX_LINE_BYTES].split("\n", 1)[0]


class JournalCatalog(Command):
    format: Literal["mnemion-memory-journal-catalog"] = "mnemion-memory-journal-catalog"
    schema_version: Literal[1] = 1
    tenant_id: UUID
    space_id: UUID
    records: int = Field(ge=0, le=1_000_000, strict=True)

    @property
    def namespace(self):
        return f"{self.tenant_id}:{self.space_id}"

    def encoded(self):
        return self.model_dump_json().encode("utf-8") + b"\n"


def parse_catalog(value: bytes):
    if len(value) > 4096:
        raise JournalError("invalid_journal_catalog")
    try:
        raw = json.loads(value.decode("utf-8"), object_pairs_hook=_unique)
        if type(raw.get("schema_version")) is not int:
            raise ValueError
        return JournalCatalog.model_validate(raw)
    except (ValueError, TypeError, AttributeError, RecursionError):
        raise JournalError("invalid_journal_catalog") from None


class JournalError(ValueError):
    """A fixed diagnostic code, never a memory fragment or subprocess output."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class JournalEntry(Command):
    format: Literal["mnemion-memory-journal"] = FORMAT
    schema_version: Literal[1] = 1
    id: UUID
    ts: AwareDatetime
    tenant_id: UUID
    space_id: UUID
    memory_id: UUID
    version: int = Field(ge=1, le=9007199254740991, strict=True)
    writer: UUID
    action: Literal["upsert", "forget", "quarantine"] = "upsert"
    subject: str | None = Field(default=None, max_length=500)
    important: StrictBool = False
    text: Content | None = None
    kind: MemoryKind = "note"
    metadata: dict = Field(default_factory=dict)

    _metadata = field_validator("metadata")(MemoryInput.small_json.__func__)

    @field_validator("schema_version", mode="before")
    @classmethod
    def numeric_schema(cls, value):
        if type(value) is not int:
            raise ValueError("Use an integer schema version")
        return value

    @field_validator("ts")
    @classmethod
    def utc(cls, value):
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def payload(self):
        if self.action == "upsert":
            if self.text is None or not self.text.strip():
                raise ValueError("An upsert requires nonempty text")
        elif self.text is not None or self.subject is not None or self.metadata:
            raise ValueError("A denial cannot carry memory content or metadata")
        return self

    @property
    def origin(self) -> str:
        return f"{self.tenant_id}:{self.space_id}:{self.memory_id}"

    @property
    def relative_path(self) -> str:
        # UUID-only names keep Windows, macOS and Linux paths predictable.
        return f"{self.ts.date().isoformat()}/{self.writer}.jsonl"

    def line(self) -> bytes:
        value = (
            json.dumps(
                self.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )
        if len(value) > MAX_LINE_BYTES:
            raise JournalError("journal_record_too_large")
        return value

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.line()).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise JournalError("journal_duplicate_field")
        result[key] = value
    return result


def parse_line(value: bytes) -> JournalEntry:
    if not value or len(value) > MAX_LINE_BYTES or not value.endswith(b"\n"):
        raise JournalError("journal_incomplete_or_oversized_record")
    try:
        raw = json.loads(value.decode("utf-8"), object_pairs_hook=_unique)
        entry = JournalEntry.model_validate(raw)
        entry.line()
        return entry
    except (ValueError, TypeError, RecursionError):
        raise JournalError("invalid_journal_record") from None


def parse_file(stream, *, maximum: int = MAX_FILE_BYTES):
    """A partial final write is an error, never a silently complete inventory."""
    total = 0
    while value := stream.readline(MAX_LINE_BYTES + 1):
        total += len(value)
        if total > maximum:
            raise JournalError("journal_file_too_large")
        yield parse_line(value)
