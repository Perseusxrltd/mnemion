"""Typed model-selection contracts shared by the service and thin clients."""

from typing import Literal

from pydantic import Field, StrictBool, StrictInt

from .contracts import ResponseModel
from .models import Command


class ReindexInput(Command):
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    expected_version: StrictInt = Field(ge=0)
    approve_network_egress: StrictBool = False


class ReindexControl(Command):
    expected_version: StrictInt = Field(ge=0)
    approve_network_egress: StrictBool = False


class EmbeddingProfile(ResponseModel):
    id: str
    label: str
    model: str
    generation_id: str
    dimensions: int
    execution: str
    network_egress: bool
    endpoint_origin: str | None
    token_count_unit: Literal["model_tokens", "utf8_bytes"]
    configuration: dict
    registered: bool


class CandidateIndex(ResponseModel):
    id: str
    generation_id: str
    state: Literal["running", "paused"]
    scan_complete: bool
    revisions: int
    indexed_revisions: int
    jobs: list[dict]
    ready_to_activate: bool
    network_egress_approved: bool
    created_at: str
    updated_at: str


class EmbeddingSettings(ResponseModel):
    space_id: str
    version: int
    active_generation_id: str
    inference_paused: bool = False
    previous_generation_id: str | None
    candidate: CandidateIndex | None
    profiles: list[EmbeddingProfile]


class EmbeddingChoice(ResponseModel):
    generation_id: str
    state: Literal["active", "candidate"]
    label: str
    available: bool
    token_count_unit: Literal["model_tokens", "utf8_bytes"] | None
