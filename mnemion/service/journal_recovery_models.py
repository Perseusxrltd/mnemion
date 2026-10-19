"""A complete, bounded native journal is reviewed before any native write."""

from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, StrictBool

from .models import Command

MAX_RECOVERY_BYTES = 1024**2
MAX_RECOVERY_IDENTITIES = 1000


class JournalRecoveryFile(Command):
    path: str = Field(min_length=1, max_length=120)
    text: SecretStr = Field(max_length=MAX_RECOVERY_BYTES)


class JournalRecoveryInput(Command):
    identity_mode: Literal["original", "copy"] = "original"
    catalog: SecretStr = Field(max_length=4096)
    files: list[JournalRecoveryFile] = Field(max_length=256)
    withdrawn_ids: list[UUID] = Field(
        max_length=MAX_RECOVERY_IDENTITIES,
        description="Known original memory IDs withdrawn after this snapshot, including IDs absent from it. Review before supplying an empty list.",
    )
    reject_personal_data: StrictBool = True


class JournalRecoveryApply(JournalRecoveryInput):
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewed_complete_inventory: Literal[True]
    reviewed_withdrawals: Literal[True]
    acknowledge_source_only: Literal[True]


class JournalRecoveryItem(Command):
    original_id: UUID
    memory_id: UUID
    source_version: int | None = None
    version: int | None = None
    action: Literal[
        "create",
        "already_restored",
        "preserved_changes",
        "stale_source",
        "withdraw",
        "deny",
        "withdrawn",
        "hold",
        "quarantine",
        "held",
        "release",
        "update",
        "conflict",
        "rejected",
    ]
    code: str | None = None


class JournalRecoveryReceipt(Command):
    identity_mode: Literal["original", "copy"]
    namespace: str
    space_id: UUID
    preview_sha256: str
    counts: dict[str, int]
    items: list[JournalRecoveryItem]
    source_only: Literal[True] = True
    remote_delivery_verified: Literal[False] = False


class JournalRecoveryPreview(JournalRecoveryReceipt):
    input_sha256: str
    can_restore: bool
    records: int
    duplicates: int
    bytes: int
