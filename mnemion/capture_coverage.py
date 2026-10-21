"""Bounded counters for observed file prefixes, distinct from memory delivery."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Count = Annotated[int, Field(ge=0, le=2**53 - 1, strict=True)]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Bounded(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SelectionCounts(Bounded):
    lines: Count = 0
    selected: Count = 0
    omitted: Count = 0
    unsupported: Count = 0

    @model_validator(mode="after")
    def partition(self):
        if self.lines != self.selected + self.omitted + self.unsupported:
            raise ValueError(
                "Selected, omitted and unsupported lines must cover the examined prefix"
            )
        return self


class CaptureCoverage(Bounded):
    format: Literal["mnemion-capture-coverage-v1"] = "mnemion-capture-coverage-v1"
    capture_mode: Literal["complete", "messages"]
    catalog: Literal["unobserved", "available", "unavailable"] = "unobserved"
    tracked_scopes: Count = 0
    checking_scopes: Count = 0
    failed_scopes: Count = 0
    missing_scopes: Count = 0
    uncertain_scopes: Count = 0
    unknown_prefix_scopes: Count = 0
    uncertain_intervals: Count = 0
    observed_bytes: Count = 0
    examined_prefix_bytes: Count = 0
    unaccepted_observed_bytes: Count = 0
    unresolved_previous_bytes: Count = 0
    records: SelectionCounts = Field(default_factory=SelectionCounts)
    tracked_from: str | None = None
    observed_at: str | None = None
    complete_prefix_at: str | None = None
    last_contact_at: str | None = None
    last_acknowledged_at: str | None = None
    queue_nonempty_since: str | None = None
    history_before_tracking: Literal["unknown"] = "unknown"

    @field_validator(
        "tracked_from",
        "observed_at",
        "complete_prefix_at",
        "last_contact_at",
        "last_acknowledged_at",
        "queue_nonempty_since",
    )
    @classmethod
    def timestamp(cls, value):
        if value is not None:
            if len(value) > 40:
                raise ValueError("Use a bounded UTC timestamp")
            parsed = datetime.fromisoformat(value)
            if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
                raise ValueError("Use a UTC timestamp")
        return value

    @model_validator(mode="after")
    def consistent(self):
        if (
            self.checking_scopes + self.failed_scopes + self.missing_scopes > self.tracked_scopes
            or self.uncertain_scopes > self.tracked_scopes
            or self.unknown_prefix_scopes > self.tracked_scopes
            or self.examined_prefix_bytes + self.unaccepted_observed_bytes != self.observed_bytes
        ):
            raise ValueError("Capture coverage counters are inconsistent")
        return self


class PrefixObservation(Bounded):
    outcome: Literal["checking", "accepted", "failed", "missing"] = "checking"
    generation: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")] | None = None
    observed_bytes: Count = 0
    examined_bytes: Count = 0
    unresolved_bytes: Count = 0
    uncertain: bool = False
    records: SelectionCounts | None = None

    @model_validator(mode="after")
    def prefix(self):
        if self.examined_bytes > self.observed_bytes:
            raise ValueError("An accepted prefix cannot exceed the observed file")
        return self
