"""Bounded transport and durable progress for complete native journal recovery."""

from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, StrictBool

from .journal_recovery_models import JournalRecoveryItem
from .models import Command

UPLOAD_BYTES = 2 * 1024**3
UPLOAD_RECORDS = 1_000_000
UPLOAD_IDENTITIES = 100_000
UPLOAD_FILES = 8192
CHUNK_BYTES = 256 * 1024
REVIEW_IDENTITIES = 64
REVIEW_BYTES = 2 * 1024**2


class JournalUploadFileInput(Command):
    path: str = Field(min_length=1, max_length=120)
    bytes: int = Field(ge=0, le=UPLOAD_BYTES)


class JournalUploadInput(Command):
    identity_mode: Literal["original", "copy"] = "original"
    catalog: SecretStr = Field(max_length=4096)
    files: list[JournalUploadFileInput] = Field(max_length=UPLOAD_FILES)
    withdrawn_ids: list[UUID] = Field(max_length=10_000)
    reject_personal_data: StrictBool = True


class JournalUploadChunk(Command):
    offset: int = Field(ge=0, le=UPLOAD_BYTES)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    data: SecretStr = Field(max_length=((CHUNK_BYTES + 2) // 3) * 4)


class JournalUploadAdvance(Command):
    expected_version: int = Field(ge=1)
    action: Literal["finish_upload", "review", "restart_review", "authorize", "restore", "cancel"]
    preview_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    reviewed_complete_inventory: StrictBool = False
    reviewed_withdrawals: StrictBool = False
    acknowledge_source_only: StrictBool = False
    acknowledge_resumable_batches: StrictBool = False


class JournalUploadFile(Command):
    index: int
    path: str
    bytes: int
    received: int
    transport_sha256: str
    complete: bool


class JournalUploadStatus(Command):
    id: UUID
    space_id: UUID
    version: int
    state: Literal["uploading", "reviewing", "reviewed", "restoring", "completed", "cancelled"]
    identity_mode: Literal["original", "copy"]
    namespace: str
    reject_personal_data: bool
    input_sha256: str
    preview_sha256: str | None
    can_restore: bool
    bytes: int
    received: int
    files: int
    completed_files: int
    records: int
    expected_records: int
    physical_records: int
    duplicates: int
    identities: int
    reviewed_identities: int
    processed_identities: int
    reviewed_batches: int
    applied_batches: int
    counts: dict[str, int]
    applied_counts: dict[str, int]
    created_at: str
    updated_at: str
    expires_at: str
    chunk_bytes: int = CHUNK_BYTES
    source_only: Literal[True] = True
    remote_delivery_verified: Literal[False] = False


class JournalUploadList(Command):
    items: list[JournalUploadStatus]


class JournalUploadFiles(Command):
    items: list[JournalUploadFile]
    next_cursor: int | None


class JournalUploadDecisions(Command):
    items: list[JournalRecoveryItem]
    next_cursor: int | None


class JournalUploadChunkReceipt(Command):
    upload: JournalUploadStatus
    file: JournalUploadFile
    repeated: bool
