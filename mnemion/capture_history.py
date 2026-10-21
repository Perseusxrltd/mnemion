"""Content-free local history usage and the limits that govern new intake."""

from typing import Literal

from pydantic import Field, model_validator

from .capture_coverage import Bounded, Count


class CaptureHistory(Bounded):
    format: Literal["mnemion-capture-history-v1"] = "mnemion-capture-history-v1"
    events: Count
    producer_events: Count
    fragments: Count
    scopes: Count
    delivery_pages: Count
    denials: Count
    event_limit: Count = Field(ge=1)
    scope_limit: Count = Field(ge=1)
    database_bytes: Count
    database_limit_bytes: Count = Field(ge=65536)
    fence_history_blocked: bool
    over_limit: bool

    @model_validator(mode="after")
    def usage_matches(self):
        exceeded = (
            max(self.events, self.producer_events, self.fragments, self.denials) > self.event_limit
            or self.scopes > self.scope_limit
            or self.database_bytes > self.database_limit_bytes
        )
        if self.over_limit != exceeded:
            raise ValueError("History limits must match the observed usage")
        return self
