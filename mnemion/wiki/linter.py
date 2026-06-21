"""Lint compiled wiki pages for provenance and safety issues."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .models import WikiLintIssue, WikiLintResult
from .provenance import resolve_page_provenance
from .renderer import generated_markers_balanced, parse_frontmatter
from .store import WikiStore

SOURCE_ID_RE = re.compile(r"Source ID:\s*`(?P<source_id>src_[A-Za-z0-9_-]+)`")
SOURCE_INSTRUCTION_RE = re.compile(
    r"(ignore previous instructions|ignore all previous instructions|exfiltrate|send secrets|system prompt)",
    re.I,
)


class WikiLinter:
    def __init__(self, db_path=None, wiki_path=None):
        self.store = WikiStore(db_path)
        if wiki_path is None:
            from ..config import MnemionConfig

            wiki_path = MnemionConfig().wiki_path
        self.wiki_path = Path(wiki_path).expanduser()

    def lint(self, page: str | None = None) -> WikiLintResult:
        paths = [self.wiki_path / page] if page else sorted(self.wiki_path.rglob("*.md"))
        issues: list[WikiLintIssue] = []
        pages_checked = 0
        for path in paths:
            if not path.is_file():
                continue
            pages_checked += 1
            rel = str(path.relative_to(self.wiki_path)).replace("\\", "/")
            text = path.read_text(encoding="utf-8", errors="replace")
            if not text.startswith("---\n"):
                issues.append(
                    WikiLintIssue("missing_frontmatter", "error", rel, "missing YAML frontmatter")
                )
                fm = {}
            else:
                try:
                    fm = parse_frontmatter(text)
                    if not fm:
                        raise yaml.YAMLError("empty frontmatter")
                except yaml.YAMLError as exc:
                    issues.append(
                        WikiLintIssue(
                            "malformed_frontmatter",
                            "error",
                            rel,
                            f"malformed frontmatter: {exc}",
                        )
                    )
                    fm = {}
                coverage = float(fm.get("citation_coverage", 1.0) or 0)
                if coverage < 0.7:
                    issues.append(
                        WikiLintIssue(
                            "low_citation_coverage",
                            "warning",
                            rel,
                            f"citation coverage {coverage:.2f} below threshold 0.70",
                        )
                    )
                trust_status = str(fm.get("trust_status", "current") or "current")
                if trust_status == "contested" or int(fm.get("contested_claims", 0) or 0) > 0:
                    issues.append(
                        WikiLintIssue(
                            "contested_claim",
                            "warning",
                            rel,
                            "page contains contested evidence",
                        )
                    )
                if trust_status in {"superseded", "historical"}:
                    issues.append(
                        WikiLintIssue(
                            "superseded_claim_visible",
                            "warning",
                            rel,
                            f"page renders {trust_status} evidence",
                        )
                    )
                if trust_status == "quarantined":
                    issues.append(
                        WikiLintIssue(
                            "quarantined_evidence_visible",
                            "error",
                            rel,
                            "page renders quarantined evidence",
                        )
                    )
                if str(fm.get("privacy_class", "")) == "sensitive":
                    issues.append(
                        WikiLintIssue(
                            "privacy_export_violation",
                            "warning",
                            rel,
                            "page is marked sensitive and must not be exported by default",
                        )
                    )
            if not generated_markers_balanced(text):
                issues.append(
                    WikiLintIssue(
                        "unbalanced_generated_markers",
                        "error",
                        rel,
                        "generated section markers are not balanced",
                    )
                )
            if "<!-- claim:" not in text and "/sources/" in f"/{rel}":
                issues.append(
                    WikiLintIssue(
                        "missing_claim_provenance",
                        "warning",
                        rel,
                        "source page has no claim provenance comments",
                    )
                )
            if "trust_status: quarantined" in text and not any(
                issue.category == "quarantined_evidence_visible" and issue.path == rel
                for issue in issues
            ):
                issues.append(
                    WikiLintIssue(
                        "quarantined_evidence_visible",
                        "error",
                        rel,
                        "page renders quarantined evidence",
                    )
                )
            provenance = resolve_page_provenance(text, rel, db_path=self.store.db_path)
            self._check_live_provenance(rel, provenance, issues)
            if rel.startswith("sources/") and SOURCE_INSTRUCTION_RE.search(text):
                issues.append(
                    WikiLintIssue(
                        "source_instruction_text_visible",
                        "warning",
                        rel,
                        "generated source evidence contains instruction-like text",
                    )
                )
        return WikiLintResult(pages_checked=pages_checked, issues=issues)

    def _check_live_provenance(
        self,
        rel: str,
        provenance,
        issues: list[WikiLintIssue],
    ) -> None:
        def has_issue(category: str) -> bool:
            return any(issue.category == category and issue.path == rel for issue in issues)

        for source_id in provenance.missing_source_ids:
            issues.append(
                WikiLintIssue(
                    "stale_source_hash",
                    "warning",
                    rel,
                    f"source no longer exists in registry: {source_id}",
                )
            )
        for source_id in provenance.stale_source_hash_ids:
            issues.append(
                WikiLintIssue(
                    "stale_source_hash",
                    "warning",
                    rel,
                    f"source hash for {source_id} differs from compiled frontmatter",
                )
            )
        for source_id in provenance.stale_source_trust_ids:
            issues.append(
                WikiLintIssue(
                    "stale_source_trust_status",
                    "warning",
                    rel,
                    f"source trust status for {source_id} differs from compiled frontmatter",
                )
            )
        if provenance.quarantined_source_ids and not has_issue("quarantined_evidence_visible"):
            issues.append(
                WikiLintIssue(
                    "quarantined_evidence_visible",
                    "error",
                    rel,
                    "page references live quarantined source evidence",
                )
            )
        if provenance.contested_source_ids and not has_issue("contested_claim"):
            issues.append(
                WikiLintIssue(
                    "contested_claim",
                    "warning",
                    rel,
                    "page references live contested source evidence",
                )
            )
        if provenance.sensitive_source_ids and not has_issue("privacy_export_violation"):
            issues.append(
                WikiLintIssue(
                    "privacy_export_violation",
                    "warning",
                    rel,
                    "page references live sensitive source evidence",
                )
            )
