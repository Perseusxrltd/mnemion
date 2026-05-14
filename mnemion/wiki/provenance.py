"""Live provenance checks for compiled wiki pages.

Generated markdown can drift from the SQLite truth layer after a source trust or
privacy review. This module centralizes the live DB lookup so lint, export,
context packs, and MCP fetch all make the same default-deny decisions.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..sources.store import SourceStore
from .renderer import parse_frontmatter

CLAIM_SOURCE_RE = re.compile(r"\bsource:(?P<source_id>src_[A-Za-z0-9_-]+)")
SOURCE_ID_LINE_RE = re.compile(r"Source ID:\s*`(?P<source_id>src_[A-Za-z0-9_-]+)`")


def _safe_frontmatter(markdown: str) -> dict[str, Any]:
    try:
        return parse_frontmatter(markdown)
    except Exception:
        return {}


@dataclass(frozen=True)
class WikiPageProvenance:
    path: str
    page_id: str
    frontmatter: dict[str, Any]
    source_ids: list[str]
    sources: list[dict[str, Any]] = field(default_factory=list)
    missing_source_ids: list[str] = field(default_factory=list)
    stale_source_hash_ids: list[str] = field(default_factory=list)
    stale_source_trust_ids: list[str] = field(default_factory=list)
    quarantined_source_ids: list[str] = field(default_factory=list)
    contested_source_ids: list[str] = field(default_factory=list)
    sensitive_source_ids: list[str] = field(default_factory=list)
    effective_trust_status: str = "current"
    effective_privacy_class: str = "private"
    warnings: list[str] = field(default_factory=list)

    @property
    def has_quarantined_evidence(self) -> bool:
        return bool(self.quarantined_source_ids)

    @property
    def has_sensitive_evidence(self) -> bool:
        return bool(self.sensitive_source_ids)

    @property
    def has_contested_evidence(self) -> bool:
        return bool(self.contested_source_ids)


def _normalize_source_ids(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return []
    seen: set[str] = set()
    ids: list[str] = []
    for raw in values:
        source_id = str(raw).strip()
        if source_id.startswith("src_") and source_id not in seen:
            ids.append(source_id)
            seen.add(source_id)
    return ids


def extract_source_ids(markdown: str, db_path: str | Path | None = None) -> list[str]:
    """Extract source IDs from frontmatter, claim comments, and claim rows."""

    fm = _safe_frontmatter(markdown)
    source_ids: list[str] = []
    seen: set[str] = set()

    for source_id in _normalize_source_ids(fm.get("source_id")) + _normalize_source_ids(
        fm.get("source_ids")
    ):
        if source_id not in seen:
            source_ids.append(source_id)
            seen.add(source_id)

    for regex in (CLAIM_SOURCE_RE, SOURCE_ID_LINE_RE):
        for match in regex.finditer(markdown):
            source_id = match.group("source_id")
            if source_id not in seen:
                source_ids.append(source_id)
                seen.add(source_id)

    page_id = str(fm.get("mnemion_page_id") or "")
    if db_path is not None and page_id:
        try:
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    """SELECT DISTINCT source_id
                       FROM wiki_claims
                       WHERE page_id = ? AND source_id IS NOT NULL AND source_id != ''""",
                    (page_id,),
                ).fetchall()
            finally:
                conn.close()
            for (source_id,) in rows:
                if source_id and source_id not in seen:
                    source_ids.append(source_id)
                    seen.add(source_id)
        except sqlite3.Error:
            pass

    return source_ids


def resolve_page_provenance(
    markdown: str,
    path: str,
    db_path: str | Path | None = None,
) -> WikiPageProvenance:
    fm = _safe_frontmatter(markdown)
    page_id = str(fm.get("mnemion_page_id") or "")
    source_ids = extract_source_ids(markdown, db_path=db_path)
    source_hashes = {str(value) for value in (fm.get("source_hashes") or [])}
    frontmatter_trust = str(fm.get("trust_status", "current") or "current")

    sources: list[dict[str, Any]] = []
    missing: list[str] = []
    stale_hash: list[str] = []
    stale_trust: list[str] = []
    quarantined: list[str] = []
    contested: list[str] = []
    sensitive: list[str] = []
    warnings: list[str] = []

    if db_path is not None and source_ids:
        store = SourceStore(db_path=db_path)
        for source_id in source_ids:
            try:
                source = store.get_source(source_id)
            except KeyError:
                missing.append(source_id)
                warnings.append(f"missing source registry row: {source_id}")
                continue
            sources.append(source)
            trust_status = str(source.get("trust_status") or "current")
            privacy_class = str(source.get("privacy_class") or "private")
            content_hash = str(source.get("content_hash") or "")
            if source_hashes and content_hash not in source_hashes:
                stale_hash.append(source_id)
                warnings.append(f"source hash differs from compiled frontmatter: {source_id}")
            if trust_status != frontmatter_trust:
                stale_trust.append(source_id)
                warnings.append(f"source trust differs from compiled frontmatter: {source_id}")
            if trust_status == "quarantined":
                quarantined.append(source_id)
                warnings.append(f"quarantined source evidence visible: {source_id}")
            elif trust_status == "contested":
                contested.append(source_id)
                warnings.append(f"contested source evidence visible: {source_id}")
            if privacy_class == "sensitive":
                sensitive.append(source_id)
                warnings.append(f"sensitive source evidence visible: {source_id}")

    trust_order = ["quarantined", "contested", "superseded", "historical", "current"]
    effective_trust = frontmatter_trust
    source_trusts = [str(source.get("trust_status") or "current") for source in sources]
    for status in trust_order:
        if status in source_trusts or frontmatter_trust == status:
            effective_trust = status
            break

    privacy_order = ["sensitive", "private", "internal", "public"]
    frontmatter_privacy = str(fm.get("privacy_class", "private") or "private")
    effective_privacy = frontmatter_privacy
    source_privacy = [str(source.get("privacy_class") or "private") for source in sources]
    for privacy in privacy_order:
        if privacy in source_privacy or frontmatter_privacy == privacy:
            effective_privacy = privacy
            break

    return WikiPageProvenance(
        path=path,
        page_id=page_id,
        frontmatter=fm,
        source_ids=source_ids,
        sources=sources,
        missing_source_ids=missing,
        stale_source_hash_ids=stale_hash,
        stale_source_trust_ids=stale_trust,
        quarantined_source_ids=quarantined,
        contested_source_ids=contested,
        sensitive_source_ids=sensitive,
        effective_trust_status=effective_trust,
        effective_privacy_class=effective_privacy,
        warnings=warnings,
    )
