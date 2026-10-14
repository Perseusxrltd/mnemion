"""Bounded evaluation commands and reviewable public contracts."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    field_validator,
    model_validator,
)

from .contracts import ResponseModel
from .models import Command, RankingPolicy

Mode = Literal["lexical", "semantic", "hybrid"]
Split = Literal["development", "held_out"]
RunState = Literal["queued", "running", "completed", "failed", "cancelled", "invalidated"]


class Reference(Command):
    memory_id: UUID
    revision_id: UUID | None = None
    grade: StrictInt = Field(default=1, ge=1, le=3)


class EvaluationCase(Command):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    query: str = Field(min_length=1, max_length=4000)
    category: str = Field(default="general", min_length=1, max_length=80)
    split: Split = "development"
    unanswerable: StrictBool = False
    references: list[Reference] = Field(default_factory=list, max_length=50)
    known_at: AwareDatetime | None = None
    valid_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def labels(self):
        if not self.query.strip() or not self.category.strip():
            raise ValueError("Queries and categories must contain text")
        if self.unanswerable == bool(self.references):
            raise ValueError("Answerable cases need references; unanswerable cases must have none")
        keys = [(r.memory_id, r.revision_id) for r in self.references]
        if len(keys) != len(set(keys)):
            raise ValueError("Reference labels must be unique")
        return self


class DatasetInput(Command):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    cases: list[EvaluationCase] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_cases(self):
        if not self.name.strip() or len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Use a nonblank name and unique case IDs")
        if len(self.model_dump_json().encode("utf-8")) > 1_500_000:
            raise ValueError("A dataset version must fit within 1.5 MB")
        return self


class EvaluationInput(Command):
    dataset_id: UUID
    embedding_generation: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    split: Split = "development"
    modes: list[Mode] = Field(default_factory=lambda: ["hybrid"], min_length=1, max_length=3)
    cutoffs: list[StrictInt] = Field(
        default_factory=lambda: [5, 10, 20], min_length=1, max_length=5
    )
    context: StrictBool = True
    keyword_fallback: StrictBool = True
    ranking_policy: RankingPolicy = Field(default_factory=RankingPolicy)
    token_budget: StrictInt = Field(default=2048, ge=128, le=16000)
    max_seconds: StrictInt = Field(default=300, ge=10, le=3600)
    interval_seconds: StrictFloat = Field(default=1, ge=0.25, le=60, allow_inf_nan=False)

    @field_validator("modes", "cutoffs")
    @classmethod
    def unique_options(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Duplicate run options are not allowed")
        return value

    @field_validator("cutoffs")
    @classmethod
    def valid_cutoffs(cls, value):
        if any(isinstance(k, bool) or not 1 <= k <= 50 for k in value):
            raise ValueError("Retrieval cutoffs must be integers from 1 to 50")
        return sorted(value)


class AssessmentInput(Command):
    expected_recorded_at: AwareDatetime
    expected_assessment_version: StrictInt = Field(default=0, ge=0)
    label: Literal[
        "useful", "partially_useful", "not_useful", "correct_abstention", "incorrect_abstention"
    ]
    note: str = Field(default="", max_length=2000)


class Dataset(ResponseModel):
    id: str
    name: str
    description: str
    version: int
    content_hash: str
    state: Literal["active", "invalidated", "deleted"]
    case_count: int
    development_count: int
    held_out_count: int
    created_at: str
    cases: list[EvaluationCase] | None = None


class EvaluationRun(ResponseModel):
    id: str
    space_id: str
    dataset_id: str
    generation_id: str
    state: RunState
    progress: int
    total: int
    configuration: dict
    manifest: dict
    summary: dict | None
    error_code: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


class EvaluationResult(ResponseModel):
    position: int
    case_id: str
    mode: Mode
    result: dict
    human_assessment: dict | None
    assessed_by: str | None
    assessed_at: str | None
    assessment_version: int
    recorded_at: str


class EvaluationPage(ResponseModel):
    items: list[EvaluationResult]
    next_cursor: int | None


class RunComparison(Command):
    baseline_id: UUID
    candidate_id: UUID


class Comparison(ResponseModel):
    baseline: EvaluationRun
    candidate: EvaluationRun
    comparable: bool
    reasons: list[str]
    deltas: list[dict]
