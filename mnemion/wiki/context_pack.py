"""Context pack builder for large compiled wiki and source vaults."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..sources.store import SourceStore
from .provenance import resolve_page_provenance
from .renderer import parse_frontmatter


def _snippet(text: str, budget_chars: int) -> str:
    return text[:budget_chars].rstrip()


def _wiki_hits(
    query: str,
    wiki_path: Path,
    limit: int,
    budget_chars: int,
    db_path=None,
    warnings: list[str] | None = None,
    contested: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    tokens = [token.lower() for token in query.split() if token.strip()]
    hits = []
    for path in sorted(wiki_path.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        lower = text.lower()
        score = sum(1 for token in tokens if token in lower)
        if score <= 0:
            continue
        rel = str(path.relative_to(wiki_path)).replace("\\", "/")
        fm = parse_frontmatter(text)
        provenance = resolve_page_provenance(text, rel, db_path=db_path) if db_path else None
        if fm.get("trust_status") == "quarantined" or (
            provenance and provenance.quarantined_source_ids
        ):
            if warnings is not None:
                warnings.append(f"quarantined wiki page excluded: {rel}")
            continue
        hit = {
            "path": rel,
            "title": fm.get("title") or path.stem,
            "relevance": round(score / max(1, len(tokens)), 3),
            "why": "matched query terms in compiled wiki page",
            "text": _snippet(text, budget_chars),
            "trust_status": (
                provenance.effective_trust_status
                if provenance is not None
                else fm.get("trust_status", "current")
            ),
            "privacy_class": (
                provenance.effective_privacy_class
                if provenance is not None
                else fm.get("privacy_class", "private")
            ),
        }
        if provenance and provenance.contested_source_ids:
            hit["warnings"] = [
                f"contested source evidence: {source_id}"
                for source_id in provenance.contested_source_ids
            ]
            if warnings is not None:
                warnings.extend(hit["warnings"])
            if contested is not None:
                contested.append(hit)
        hits.append(hit)
    hits.sort(key=lambda item: item["relevance"], reverse=True)
    return hits[:limit]


def build_context_pack(
    query: str,
    mode: str = "answer_question",
    token_budget: int = 6000,
    db_path=None,
    wiki_path=None,
    anaktoron_path: str | None = None,
) -> dict[str, Any]:
    if wiki_path is None:
        from ..config import MnemionConfig

        wiki_path = MnemionConfig().wiki_path
    wiki_root = Path(wiki_path).expanduser()
    char_budget = max(400, int(token_budget) * 4)
    source_store = SourceStore(db_path=db_path, anaktoron_path=anaktoron_path)
    source_hits = source_store.search(query, limit=8)
    source_chunks = []
    warnings = []
    contested = []
    remaining = char_budget // 2
    for hit in source_hits:
        if remaining <= 0:
            break
        trust_status = hit["trust_status"]
        if trust_status == "quarantined":
            continue
        text = _snippet(hit["text"], min(remaining, 1200))
        remaining -= len(text)
        chunk_payload = {
            "source_id": hit["source_id"],
            "chunk_id": hit["id"],
            "title": hit["title"],
            "text": text,
            "trust_status": trust_status,
            "privacy_class": hit["privacy_class"],
            "untrusted_source_content": True,
        }
        source_chunks.append(chunk_payload)
        if trust_status == "contested":
            contested.append(chunk_payload)
            warnings.append(f"contested source evidence included: {hit['source_id']}")
    wiki_pages = (
        _wiki_hits(
            query,
            wiki_root,
            limit=8,
            budget_chars=max(400, char_budget // 6),
            db_path=source_store.db_path,
            warnings=warnings,
            contested=contested,
        )
        if wiki_root.exists()
        else []
    )

    drawers = []
    try:
        from ..hybrid_searcher import HybridSearcher

        for hit in HybridSearcher(
            anaktoron_path=anaktoron_path, kg_path=str(source_store.db_path)
        ).search(query, n_results=5):
            trust_status = hit.get("trust_status", "current")
            if str(hit.get("id", "")).startswith("kg_") or trust_status == "quarantined":
                continue
            drawer_payload = {
                "drawer_id": hit["id"],
                "wing": hit.get("wing", ""),
                "room": hit.get("room", ""),
                "text": _snippet(hit.get("text", ""), 1000),
                "trust_status": trust_status,
            }
            drawers.append(drawer_payload)
            if trust_status == "contested":
                contested.append(drawer_payload)
                warnings.append(f"contested drawer evidence included: {hit['id']}")
    except Exception:
        drawers = []

    return {
        "query": query,
        "mode": mode,
        "token_budget": token_budget,
        "warnings": warnings,
        "wiki_pages": wiki_pages,
        "source_chunks": source_chunks,
        "drawers": drawers,
        "kg_facts": [],
        "contested": contested,
        "recommended_reading_order": [page["path"] for page in wiki_pages]
        + [chunk["chunk_id"] for chunk in source_chunks],
    }
