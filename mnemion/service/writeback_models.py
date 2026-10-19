"""Consent, status and explicit controls for a host-approved Git destination."""

from typing import Literal
from pydantic import Field, StrictBool, field_validator
from .models import Command
from .contracts import ResponseModel


class WritebackPolicyInput(Command):
    expected_version: int = Field(ge=0)
    destination_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    publish_to_repository: Literal[True]
    acknowledge_retained_git_history: Literal[True]
    paused: StrictBool = False
    interval_seconds: int = Field(default=300, ge=30, le=86400)
    repair_publisher: StrictBool = False
    fold_enabled: StrictBool | None = None
    fold_after_hours: int | None = Field(default=None, ge=24, le=8760)
    fold_interval_seconds: int | None = Field(default=None, ge=60, le=86400)

    @field_validator("publish_to_repository", "acknowledge_retained_git_history", mode="before")
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError("Explicit publication and retained-history consent are required")
        return value


class WritebackPushInput(Command):
    expected_version: int = Field(ge=1)


class DestinationInfo(ResponseModel):
    id: str
    label: str
    repository: str
    branch: str
    prefix: str
    personal_data_scan: bool
    custom_scanner: bool


class WritebackStatus(ResponseModel):
    configured: bool
    can_configure: bool
    destination: DestinationInfo | None
    version: int
    state: Literal[
        "not_configured", "ready", "paused", "publisher_unavailable", "destination_changed"
    ]
    pending_entries: int
    pending_content_bytes: int
    external_history_retained: Literal[True]
    existing_memories_backfilled: Literal[False]
    paused: bool | None = None
    interval_seconds: int | None = None
    publisher_id: str | None = None
    last_push_at: str | None = None
    last_commit: str | None = None
    last_error: str | None = None
    last_entries: int = 0
    last_bytes: int = 0
    can_organize: bool = False
    notes_prefix: str | None = None
    fold_enabled: bool = False
    fold_after_hours: int | None = None
    fold_interval_seconds: int | None = None
    next_fold_at: str | None = None
    last_fold_at: str | None = None
    last_fold_commit: str | None = None
    last_fold_error: str | None = None
    last_fold_notes: int = 0
    last_fold_archived_files: int = 0
    last_fold_pending_notes: int = 0
    last_fold_pending_files: int = 0
    last_fold_read_bytes: int = 0
    last_fold_written_bytes: int = 0
