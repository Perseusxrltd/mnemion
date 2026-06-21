"""Models for compiled wiki pages, claims, and lint issues."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WikiPagePlan:
    path: str
    page_type: str
    title: str
    generated_sections: dict[str, str]
    source_hashes: list[str] = field(default_factory=list)
    drawer_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WikiClaim:
    id: str
    page_id: str
    claim_text: str
    source_id: str = ""
    source_chunk_id: str = ""
    drawer_id: str = ""
    kg_fact_id: str = ""
    evidence_span_start: int | None = None
    evidence_span_end: int | None = None
    confidence: float = 0.5
    trust_status: str = "current"
    content_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WikiLintIssue:
    category: str
    severity: str
    path: str
    message: str


@dataclass(frozen=True)
class WikiLintResult:
    pages_checked: int
    issues: list[WikiLintIssue]

    @property
    def errors(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    def to_dict(self) -> dict[str, Any]:
        return {
            "pages_checked": self.pages_checked,
            "errors": self.errors,
            "warnings": self.warnings,
            "issues": [issue.__dict__ for issue in self.issues],
        }
