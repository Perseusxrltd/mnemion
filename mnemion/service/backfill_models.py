"""Separate approval and observable progress for publishing older native memory."""

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from .contracts import ResponseModel
from .models import Command


class BackfillStartInput(Command):
    expected_version: int = Field(ge=1)
    publish_existing_memories: Literal[True]
    acknowledge_retained_git_history: Literal[True]
    resume_run: UUID | None = None

    @field_validator("publish_existing_memories", "acknowledge_retained_git_history", mode="before")
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError(
                "Explicit existing-memory publication and retained-history consent are required"
            )
        return value


class BackfillControlInput(Command):
    expected_version: int = Field(ge=1)
    run_id: UUID
    action: Literal["pause", "cancel"]


class BackfillError(ResponseModel):
    memory_id: str
    version: int
    code: str


class BackfillRun(ResponseModel):
    id: str
    policy_version: int
    state: Literal["running", "paused", "blocked", "completed", "cancelled"]
    cutoff_at: str
    total_at_start: int
    examined: int
    queued: int
    already_journaled: int
    excluded: int
    rejected: int
    content_bytes: int
    errors: list[BackfillError]
    last_error: str | None
    started_at: str
    updated_at: str
    finished_at: str | None


class BackfillStatus(ResponseModel):
    policy_version: int
    eligible_memories: int
    eligible_content_bytes: int
    waiting_reason: str | None
    run: BackfillRun | None
