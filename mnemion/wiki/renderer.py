"""Markdown rendering helpers for the compiled wiki."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import yaml

BEGIN_RE = re.compile(r"<!-- MNEMION:BEGIN generated section=([a-zA-Z0-9_-]+) -->")
GENERATED_BLOCK_RE = re.compile(
    r"\n?<!-- MNEMION:BEGIN generated section=[^>]+ -->.*?<!-- MNEMION:END -->\n?",
    re.S,
)
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify_wikilink(value: str, fallback: str = "page") -> str:
    raw = value.strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw)
    raw = re.sub(r"-+", "-", raw).strip("-")
    return raw or fallback


def wiki_link(path_without_ext: str, label: str | None = None) -> str:
    safe_label = (label or path_without_ext).replace("|", "/").replace("[", "(").replace("]", ")")
    return f"[[{path_without_ext}|{safe_label}]]"


def frontmatter(data: dict[str, Any]) -> str:
    clean = {key: value for key, value in data.items() if value not in (None, "")}
    return "---\n" + yaml.safe_dump(clean, sort_keys=False, allow_unicode=True).strip() + "\n---\n"


def parse_frontmatter(markdown: str) -> dict[str, Any]:
    match = FRONTMATTER_RE.match(markdown)
    if not match:
        return {}
    data = yaml.safe_load(match.group(1))
    return data if isinstance(data, dict) else {}


def strip_frontmatter(markdown: str) -> str:
    return FRONTMATTER_RE.sub("", markdown, count=1)


def render_page(
    page_id: str,
    page_type: str,
    title: str,
    body: str = "",
    generated_sections: dict[str, str] | None = None,
    source_hashes: list[str] | None = None,
    drawer_ids: list[str] | None = None,
    claim_ids: list[str] | None = None,
    trust_status: str = "current",
    citation_coverage: float = 1.0,
    stale_claims: int = 0,
    contested_claims: int = 0,
    metadata: dict[str, Any] | None = None,
) -> str:
    source_hashes = source_hashes or []
    drawer_ids = drawer_ids or []
    claim_ids = claim_ids or []
    generated_sections = generated_sections or {}
    meta = metadata or {}
    fm = frontmatter(
        {
            "mnemion_page_id": page_id,
            "page_type": page_type,
            "title": title,
            "generated_by": "mnemion-wiki-compiler",
            "last_compiled": now_iso(),
            "source_hashes": source_hashes,
            "drawer_ids": drawer_ids,
            "claim_ids": claim_ids,
            "trust_status": trust_status,
            "citation_coverage": round(float(citation_coverage), 3),
            "stale_claims": stale_claims,
            "contested_claims": contested_claims,
            **meta,
        }
    )
    lines = [fm, f"# {title}", ""]
    if stale_claims:
        lines.extend(
            [
                "> WARNING: This page may be stale. One or more source hashes changed since last compile.",
                "",
            ]
        )
    if contested_claims:
        lines.extend(["> WARNING: Contested memory is present in this page.", ""])
    for section, content in generated_sections.items():
        lines.extend(
            [
                f"<!-- MNEMION:BEGIN generated section={section} -->",
                content.rstrip(),
                "<!-- MNEMION:END -->",
                "",
            ]
        )
    if body:
        lines.extend([body.rstrip(), ""])
    return "\n".join(lines).rstrip() + "\n"


def _manual_content(markdown: str) -> str:
    body = strip_frontmatter(markdown)
    body = GENERATED_BLOCK_RE.sub("\n", body)
    lines = []
    for line in body.splitlines():
        if line.startswith("# "):
            continue
        lines.append(line)
    manual = "\n".join(lines).strip()
    return manual


def merge_generated_page(existing: str | None, generated: str) -> str:
    if not existing:
        return generated
    manual = _manual_content(existing)
    if not manual:
        return generated
    if manual in generated:
        return generated
    return generated.rstrip() + "\n\n" + manual.rstrip() + "\n"


def generated_markers_balanced(markdown: str) -> bool:
    return markdown.count("<!-- MNEMION:BEGIN") == markdown.count("<!-- MNEMION:END -->")
