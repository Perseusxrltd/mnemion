#!/usr/bin/env python3
"""
Mnemion MCP Server — read/write Anaktoron access for AI agents
================================================================
Install: claude mcp add mnemion -- python -m mnemion.mcp_server [--anaktoron /path/to/anaktoron]

Tools (read):
  mnemion_status          — total drawers, wing/room breakdown
  mnemion_list_wings      — all wings with drawer counts
  mnemion_list_rooms      — rooms within a wing
  mnemion_get_taxonomy    — full wing → room → count tree
  mnemion_search          — hybrid search (vector + lexical)
  mnemion_reconstruct     — cognitive graph reconstruction with evidence trails
  mnemion_get_evidence_trail — structured units and edges for one drawer
  mnemion_check_duplicate — check if content already exists before filing

Tools (write):
  mnemion_add_drawer      — file verbatim content into a wing/room
  mnemion_consolidate     — extract cognitive graph units from drawers
  mnemion_memory_guard_scan — scan/quarantine memory-injection risks
  mnemion_delete_drawer   — remove a drawer by ID
"""

# Issue #225: save real stdout BEFORE any other import so chatter from
# chromadb/posthog/etc cannot corrupt the JSON-RPC wire on stdout.
import sys

_real_stdout = sys.stdout
sys.stdout = sys.stderr

import argparse  # noqa: E402
import os  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import hashlib  # noqa: E402
import sqlite3  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

from .config import MnemionConfig  # noqa: E402
from .version import __version__  # noqa: E402
from .anaktoron_graph import traverse, find_tunnels, graph_stats  # noqa: E402
from .knowledge_graph import KnowledgeGraph  # noqa: E402
from .hybrid_searcher import HybridSearcher  # noqa: E402
from .trust_lifecycle import DrawerTrust  # noqa: E402
from .backends.registry import get_backend  # noqa: E402
from .query_sanitizer import sanitize_query  # noqa: E402
from . import contradiction_detector as _cd  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
logger = logging.getLogger("mnemion_mcp")


def _parse_args():
    parser = argparse.ArgumentParser(description="Mnemion MCP Server")
    parser.add_argument(
        "--anaktoron",
        metavar="PATH",
        help="Path to the Anaktoron directory (overrides config file and env var)",
    )
    args, _ = parser.parse_known_args()
    return args


_args = _parse_args()

if _args.anaktoron:
    os.environ["MNEMION_ANAKTORON_PATH"] = os.path.abspath(_args.anaktoron)

_config = MnemionConfig()

# Hybrid Searcher and sidecar DB initialization follow the resolved Anaktoron path,
# regardless of whether it came from --anaktoron, env vars, or config.json.
kg_path = os.path.join(os.path.dirname(_config.anaktoron_path), "knowledge_graph.sqlite3")
_kg = KnowledgeGraph(db_path=kg_path)
_hybrid = HybridSearcher(anaktoron_path=_config.anaktoron_path, kg_path=kg_path)
_trust = DrawerTrust(db_path=kg_path)


_client_cache = None
_collection_cache = None


def _get_collection(create=False):
    """Return the ChromaDB collection, caching the client between calls."""
    global _client_cache, _collection_cache
    try:
        if _client_cache is None:
            _client_cache = get_backend(anaktoron_path=_config.anaktoron_path)
        if create:
            _collection_cache = _client_cache.get_collection(_config.collection_name, create=True)
        elif _collection_cache is None:
            _collection_cache = _client_cache.get_collection(_config.collection_name)
        return _collection_cache
    except Exception as e:
        logger.error(f"Caught exception: {e}")
        return None


def _no_anaktoron():
    return {
        "error": "No Anaktoron found",
        "hint": "Run: mnemion init <dir> && mnemion mine <dir>",
    }


# ==================== READ TOOLS ====================


def _iter_all_metadatas(col, where=None):
    """Yield every drawer's metadata, paginating so Anaktorons with >10k drawers
    don't silently truncate. Logs and re-raises on error so callers never
    receive partial data presented as a full result. Issue #171."""
    PAGE, offset = 10000, 0
    try:
        while True:
            kwargs = {"include": ["metadatas"], "limit": PAGE, "offset": offset}
            if where:
                kwargs["where"] = where
            metas = col.get(**kwargs).get("metadatas") or []
            yield from (m for m in metas if m is not None)
            if len(metas) < PAGE:
                return
            offset += PAGE
    except Exception as e:
        logger.error("metadata iteration failed at offset %d: %s", offset, e)
        raise


def tool_status():
    col = _get_collection()
    if not col:
        return _no_anaktoron()
    count = col.count()
    wings = {}
    rooms = {}
    for m in _iter_all_metadatas(col):
        w = m.get("wing", "unknown")
        r = m.get("room", "unknown")
        wings[w] = wings.get(w, 0) + 1
        rooms[r] = rooms.get(r, 0) + 1
    return {
        "version": __version__,
        "total_drawers": count,
        "wings": wings,
        "rooms": rooms,
        "anaktoron_path": _config.anaktoron_path,
        "protocol": ANAKTORON_PROTOCOL,
        "aaak_dialect": AAAK_SPEC,
    }


# ── AAAK Dialect Spec ─────────────────────────────────────────────────────────
# Included in status response so the AI learns it on first wake-up call.
# Also available via mnemion_get_aaak_spec tool.

ANAKTORON_PROTOCOL = """IMPORTANT — Mnemion Memory Protocol:
1. ON WAKE-UP: Call mnemion_status to load Anaktoron overview + AAAK spec.
2. BEFORE RESPONDING about any person, project, or past event: call mnemion_kg_query or mnemion_search FIRST. Never guess — verify.
3. IF UNSURE about a fact (name, gender, age, relationship): say "let me check" and query the Anaktoron. Wrong is worse than slow.
4. AFTER EACH SESSION: call mnemion_diary_write to record what happened, what you learned, what matters.
5. WHEN FACTS CHANGE: call mnemion_kg_invalidate on the old fact, mnemion_kg_add for the new one.

This protocol ensures the AI KNOWS before it speaks. Storage is not memory — but storage + this protocol = memory."""

AAAK_SPEC = """AAAK is a compressed memory dialect that Mnemion uses for efficient storage.
It is designed to be readable by both humans and LLMs without decoding.

FORMAT:
  ENTITIES: 3-letter uppercase codes. ALC=Alice, JOR=Jordan, RIL=Riley, MAX=Max, BEN=Ben.
  EMOTIONS: *action markers* before/during text. *warm*=joy, *fierce*=determined, *raw*=vulnerable, *bloom*=tenderness.
  STRUCTURE: Pipe-separated fields. FAM: family | PROJ: projects | ⚠: warnings/reminders.
  DATES: ISO format (2026-03-31). COUNTS: Nx = N mentions (e.g., 570x).
  IMPORTANCE: ★ to ★★★★★ (1-5 scale).
  HALLS: hall_facts, hall_events, hall_discoveries, hall_preferences, hall_advice.
  WINGS: wing_user, wing_agent, wing_team, wing_code, wing_myproject, wing_hardware, wing_ue5, wing_ai_research.
  ROOMS: Hyphenated slugs representing named ideas (e.g., chromadb-setup, gpu-pricing).

EXAMPLE:
  FAM: ALC→♡JOR | 2D(kids): RIL(18,sports) MAX(11,chess+swimming) | BEN(contributor)

Read AAAK naturally — expand codes mentally, treat *markers* as emotional context.
When WRITING AAAK: use entity codes, mark emotions, keep structure tight."""


def tool_list_wings():
    col = _get_collection()
    if not col:
        return _no_anaktoron()
    wings = {}
    for m in _iter_all_metadatas(col):
        w = m.get("wing", "unknown")
        wings[w] = wings.get(w, 0) + 1
    return {"wings": wings}


def tool_list_rooms(wing: str = None):
    col = _get_collection()
    if not col:
        return _no_anaktoron()
    rooms = {}
    for m in _iter_all_metadatas(col, where={"wing": wing} if wing else None):
        r = m.get("room", "unknown")
        rooms[r] = rooms.get(r, 0) + 1
    return {"wing": wing or "all", "rooms": rooms}


def tool_get_taxonomy():
    col = _get_collection()
    if not col:
        return _no_anaktoron()
    taxonomy = {}
    for m in _iter_all_metadatas(col):
        w = m.get("wing", "unknown")
        r = m.get("room", "unknown")
        if w not in taxonomy:
            taxonomy[w] = {}
        taxonomy[w][r] = taxonomy[w].get(r, 0) + 1
    return {"taxonomy": taxonomy}


def tool_search(
    query: str, limit: int = 5, wing: str = None, room: str = None, min_similarity: float = 0.0
):
    """Hybrid search tool handler."""
    from . import predictor

    sanitized = sanitize_query(query)
    clean_query = sanitized["clean_query"]
    limit = max(1, min(limit, 50))
    hits = _hybrid.search(
        clean_query, wing=wing, room=room, n_results=limit, min_similarity=min_similarity
    )

    # Log activity for predictive context
    for hit in hits:
        predictor.record_activity(hit["id"], hit.get("embedding"))

    response = {
        "query": query,
        "filters": {"wing": wing, "room": room},
        "results": hits,
    }
    if sanitized["was_sanitized"]:
        response["sanitized_query"] = clean_query
        response["sanitizer"] = {
            "method": sanitized["method"],
            "original_length": sanitized["original_length"],
            "clean_length": sanitized["clean_length"],
        }
    return response


def tool_reconstruct(query: str, budget: int = 10):
    """Active reconstruction search over cognitive graph evidence."""
    from .reconstruction import reconstruct_query

    return reconstruct_query(
        query=query,
        anaktoron_path=_config.anaktoron_path,
        kg_path=os.path.join(os.path.dirname(_config.anaktoron_path), "knowledge_graph.sqlite3"),
        budget=max(1, min(int(budget), 50)),
    )


def tool_consolidate(limit: int = 100, dry_run: bool = False):
    """Consolidate raw drawers into cognitive graph units."""
    from .cognitive_graph import CognitiveGraph

    col = _get_collection()
    if not col:
        return _no_anaktoron()
    kg_path = os.path.join(os.path.dirname(_config.anaktoron_path), "knowledge_graph.sqlite3")
    return CognitiveGraph(kg_path).consolidate_collection(
        col,
        trust=_trust,
        limit=max(1, min(int(limit), 1000)),
        dry_run=bool(dry_run),
    )


def tool_memory_guard_scan(quarantine: bool = False):
    """Scan drawers for memory-injection and privacy risks."""
    from .memory_guard import MemoryGuard

    col = _get_collection()
    if not col:
        return _no_anaktoron()
    kg_path = os.path.join(os.path.dirname(_config.anaktoron_path), "knowledge_graph.sqlite3")
    return MemoryGuard(kg_path).scan_collection(col, trust=_trust, quarantine=bool(quarantine))


def tool_get_evidence_trail(drawer_id: str):
    """Return cognitive graph evidence units and edges for one drawer."""
    from .cognitive_graph import CognitiveGraph

    kg_path = os.path.join(os.path.dirname(_config.anaktoron_path), "knowledge_graph.sqlite3")
    graph = CognitiveGraph(kg_path)
    return {
        "drawer_id": drawer_id,
        "units": graph.units_for_drawer(drawer_id),
        "edges": graph.edges_for_drawer(drawer_id),
    }


def tool_predict_next():
    """Predict the next relevant context based on session history."""
    from . import predictor

    if not predictor.SESSION_FILE.exists():
        return {"prediction": None, "note": "No session history yet."}

    try:
        with open(predictor.SESSION_FILE, "r") as f:
            history = json.load(f)
    except Exception as e:
        logger.error(f"Caught exception: {e}")
        return {"error": "Failed to read session history"}

    embeddings = [h["embedding"] for h in history if "embedding" in h and h["embedding"]]
    if not embeddings:
        return {"prediction": None, "note": "No embeddings in history."}

    pred_vector = predictor.predict_next_context(embeddings)

    col = _get_collection()
    if not col or not pred_vector:
        return {"prediction": None, "note": "No active Anaktoron or prediction failed."}

    try:
        results = col.query(
            query_embeddings=[pred_vector],
            n_results=3,
        )
        docs = results.get("documents", [[]])[0]
        meta = results.get("metadatas", [[]])[0]

        prefetches = []
        for d, m in zip(docs, meta):
            prefetches.append(
                {"content": d, "room": m.get("room", "general"), "wing": m.get("wing", "general")}
            )

        return {
            "predicted_latent_state": "computed",
            "recent_history_count": len(embeddings),
            "note": "Live JEPA RNN model prediction active - Context Prefetched",
            "proactive_context": prefetches,
        }
    except Exception as e:
        logger.error(f"JEPA prefetch failure: {e}")
        return {"prediction": None, "error": str(e)}


def tool_check_duplicate(content: str, threshold: float = 0.9):
    col = _get_collection()
    if not col:
        return _no_anaktoron()
    try:
        results = col.query(
            query_texts=[content],
            n_results=5,
            include=["metadatas", "documents", "distances"],
        )
        duplicates = []
        if results["ids"] and results["ids"][0]:
            for i, drawer_id in enumerate(results["ids"][0]):
                dist = results["distances"][0][i]
                similarity = round(1 - dist, 3)
                if similarity >= threshold:
                    meta = results["metadatas"][0][i]
                    doc = results["documents"][0][i]
                    duplicates.append(
                        {
                            "id": drawer_id,
                            "wing": meta.get("wing", "?"),
                            "room": meta.get("room", "?"),
                            "similarity": similarity,
                            "content": doc[:200] + "..." if len(doc) > 200 else doc,
                        }
                    )
        return {
            "is_duplicate": len(duplicates) > 0,
            "matches": duplicates,
        }
    except Exception as e:
        logger.error(f"Caught exception: {e}")
        logger.exception("check_duplicate failed")
        return {"error": "Duplicate check failed"}


def tool_get_aaak_spec():
    """Return the AAAK dialect specification."""
    return {"aaak_spec": AAAK_SPEC}


def tool_traverse_graph(start_room: str, max_hops: int = 2):
    """Walk the Anaktoron graph from a room. Find connected ideas across wings."""
    max_hops = max(1, min(max_hops, 10))
    col = _get_collection()
    if not col:
        return _no_anaktoron()
    return traverse(start_room, col=col, max_hops=max_hops)


def tool_find_tunnels(wing_a: str = None, wing_b: str = None):
    """Find rooms that bridge two wings — the hallways connecting domains."""
    col = _get_collection()
    if not col:
        return _no_anaktoron()
    return find_tunnels(wing_a, wing_b, col=col)


def tool_graph_stats():
    """Anaktoron graph overview: nodes, tunnels, edges, connectivity."""
    col = _get_collection()
    if not col:
        return _no_anaktoron()
    return graph_stats(col=col)


# ==================== WRITE TOOLS ====================


def tool_add_drawer(
    wing: str, room: str, content: str, source_file: str = None, added_by: str = "mcp"
):
    """File verbatim content into a wing/room. Checks for duplicates and indexes in both stores."""
    col = _get_collection(create=True)
    if not col:
        return _no_anaktoron()

    drawer_id = f"drawer_{wing}_{room}_{hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()[:16]}"

    # Idempotency: if the deterministic ID already exists, return success as a no-op.
    try:
        existing = col.get(ids=[drawer_id])
        if existing and existing["ids"]:
            return {"success": True, "reason": "already_exists", "drawer_id": drawer_id}
    except Exception as e:
        logger.error(f"Suppressed error in execution: {e}")

    try:
        # 1. Add to ChromaDB (Semantic) using upsert for idempotency
        col.upsert(
            ids=[drawer_id],
            documents=[content],
            metadatas=[
                {
                    "wing": wing,
                    "room": room,
                    "source_file": source_file or "",
                    "chunk_index": 0,
                    "added_by": added_by,
                    "filed_at": datetime.now().isoformat(),
                }
            ],
        )

        # 2. Add to SQLite FTS5 (Lexical Mirror)
        KnowledgeGraph(db_path=_hybrid.kg_path)  # Ensure schema exists
        conn = sqlite3.connect(_hybrid.kg_path)
        conn.execute(
            "INSERT OR REPLACE INTO drawers_fts (drawer_id, content, wing, room) VALUES (?, ?, ?, ?)",
            (drawer_id, content, wing, room),
        )
        conn.commit()
        conn.close()

        logger.info(f"Filed drawer: {drawer_id} → {wing}/{room}")

        # Create trust record (idempotent — same drawer_id = same trust row)
        _trust.create(drawer_id, wing=wing, room=room)

        # Spawn background contradiction detection (daemon thread — never blocks)
        _cd.spawn_detection(drawer_id, content, wing, room, _trust, _hybrid)

        return {"success": True, "drawer_id": drawer_id, "wing": wing, "room": room}
    except Exception as e:
        logger.error(f"Caught exception: {e}")
        logger.exception("add_drawer failed")
        return {"success": False, "error": "Failed to add drawer"}


def tool_source_add(
    path: str,
    source_type: str = None,
    title: str = None,
    author: str = None,
    privacy_class: str = "private",
    compile_wiki: bool = False,
):
    """Add an immutable raw source to the source vault."""
    from .sources.store import SourceStore

    result = SourceStore(db_path=_hybrid.kg_path, anaktoron_path=_config.anaktoron_path).add_path(
        path,
        source_type=source_type,
        title=title,
        author=author,
        privacy_class=privacy_class,
    )
    if compile_wiki and result.get("source_id"):
        from .wiki.compiler import WikiCompiler

        result["wiki"] = WikiCompiler(db_path=_hybrid.kg_path).compile_source(
            result["source_id"], apply=True
        )
    return result


def tool_source_list(source_type: str = None, privacy_class: str = None, limit: int = 20):
    from .sources.store import SourceStore

    return {
        "sources": SourceStore(db_path=_hybrid.kg_path).list_sources(
            source_type=source_type,
            privacy_class=privacy_class,
            limit=max(1, min(int(limit), 200)),
        )
    }


def tool_source_read(source_id: str, chunks: bool = False):
    from .sources.store import SourceStore

    return SourceStore(db_path=_hybrid.kg_path).read_source(source_id, include_chunks=chunks)


def tool_source_search(query: str, limit: int = 10, privacy_class: str = None):
    from .sources.store import SourceStore

    return {
        "query": query,
        "results": SourceStore(db_path=_hybrid.kg_path).search(
            query,
            limit=max(1, min(int(limit), 50)),
            privacy_class=privacy_class,
        ),
    }


def tool_wiki_compile(
    all: bool = False,
    source_id: str = None,
    apply: bool = False,
    review: bool = True,
):
    from .wiki.compiler import WikiCompiler

    compiler = WikiCompiler(db_path=_hybrid.kg_path)
    if source_id:
        return compiler.compile_source(source_id, apply=apply, review=review and not apply)
    return compiler.compile_all(apply=apply, review=review and not apply)


def tool_wiki_lint(json_output: bool = True, page: str = None):
    from .wiki.linter import WikiLinter

    result = WikiLinter(db_path=_hybrid.kg_path).lint(page=page)
    return result.to_dict()


def tool_wiki_context_pack(query: str, mode: str = "answer_question", token_budget: int = 6000):
    from .wiki.context_pack import build_context_pack

    return build_context_pack(
        query,
        mode=mode,
        token_budget=max(1000, min(int(token_budget), 24000)),
        db_path=_hybrid.kg_path,
        anaktoron_path=_config.anaktoron_path,
    )


def tool_wiki_blast_radius(source_id: str = None, drawer_id: str = None, topic: str = None):
    from .wiki.compiler import WikiCompiler

    return WikiCompiler(db_path=_hybrid.kg_path).blast_radius(
        source_id=source_id,
        drawer_id=drawer_id,
        topic=topic,
    )


def tool_wiki_page_get(id_or_path: str):
    from pathlib import Path
    from .wiki.compiler import WikiCompiler
    from .wiki.provenance import resolve_page_provenance

    compiler = WikiCompiler(db_path=_hybrid.kg_path)
    target = Path(id_or_path)
    if not target.suffix:
        target = target.with_suffix(".md")
    page = compiler.wiki_path / target
    if not page.exists():
        # Try resolving a page id through SQLite.
        conn = sqlite3.connect(_hybrid.kg_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT path FROM wiki_pages WHERE id = ?", (id_or_path,)).fetchone()
        finally:
            conn.close()
        if row:
            page = compiler.wiki_path / row["path"]
    if not page.exists():
        return {"error": f"wiki page not found: {id_or_path}"}
    text = page.read_text(encoding="utf-8", errors="replace")
    rel = str(page.relative_to(compiler.wiki_path)).replace("\\", "/")
    provenance = resolve_page_provenance(text, rel, db_path=_hybrid.kg_path)
    if provenance.quarantined_source_ids:
        return {"error": f"wiki page references quarantined evidence: {id_or_path}"}
    warnings = _trust_warning(provenance.effective_trust_status, id_or_path)
    warnings.extend(provenance.warnings)
    return {"path": str(page), "content": text, "warnings": warnings}


def tool_wiki_export_obsidian(path: str = None, include_sensitive: bool = False):
    from pathlib import Path
    from .wiki.compiler import WikiCompiler
    from .wiki.obsidian_export import export_compiled_wiki_to_obsidian

    compiler = WikiCompiler(db_path=_hybrid.kg_path)
    target = path or str(Path(_config.obsidian_vault_path))
    return export_compiled_wiki_to_obsidian(
        compiler.wiki_path,
        target,
        include_sensitive=include_sensitive,
        db_path=_hybrid.kg_path,
    )


def _is_quarantined_trust(status=None) -> bool:
    return (status or "current") == "quarantined"


def _trust_warning(status, identifier):
    if status == "contested":
        return [f"contested evidence: {identifier}"]
    if status in {"superseded", "historical"}:
        return [f"{status} evidence: {identifier}"]
    return []


def tool_openbrain_capture_thought(
    content: str,
    tags: list = None,
    source: str = None,
    metadata: dict = None,
    wing: str = None,
    room: str = None,
    privacy_class: str = "private",
    compile_wiki: bool = False,
):
    from .capture.cli_capture import capture_text

    duplicate = tool_check_duplicate(content)
    if duplicate.get("is_duplicate"):
        match = duplicate["matches"][0]
        return {
            "id": match["id"],
            "status": "duplicate",
            "message": "Thought already exists in Mnemion",
            "wing": match.get("wing", wing or "thoughts"),
            "room": match.get("room", room or "general"),
            "trust_status": "current",
        }
    result = capture_text(
        content,
        tags=tags or [],
        source=source,
        metadata=metadata or {},
        wing=wing,
        room=room,
        privacy_class=privacy_class,
        added_by="mcp_openbrain_compat",
        anaktoron_path=_config.anaktoron_path,
    )
    if compile_wiki and result.get("status") == "created":
        from .wiki.compiler import WikiCompiler

        result["wiki"] = WikiCompiler(db_path=_hybrid.kg_path).compile_all(apply=True)
    return result


def tool_openbrain_search_thoughts(
    query: str,
    limit: int = 10,
    min_similarity: float = 0.0,
    include_contested: bool = True,
    include_superseded: bool = False,
    wing: str = None,
    room: str = None,
):
    from .mcp.compat.openbrain import thought_result

    hits = _hybrid.search(
        query,
        wing=wing,
        room=room,
        n_results=max(1, min(int(limit), 50)),
        include_superseded=bool(include_superseded),
        min_similarity=float(min_similarity),
    )
    hits = [hit for hit in hits if hit.get("trust_status", "current") != "quarantined"]
    if not include_contested:
        hits = [hit for hit in hits if hit.get("trust_status") != "contested"]
    if not include_superseded:
        hits = [hit for hit in hits if hit.get("trust_status") != "superseded"]
    return {
        "results": [
            thought_result(hit) for hit in hits if not str(hit.get("id", "")).startswith("kg_")
        ]
    }


def tool_openbrain_list_thoughts(
    limit: int = 20,
    offset: int = 0,
    wing: str = None,
    room: str = None,
    since: str = None,
    trust_status: str = None,
):
    col = _get_collection()
    if not col:
        return _no_anaktoron()
    where = {}
    if wing:
        where["wing"] = wing
    if room:
        where["room"] = room
    kwargs = {
        "include": ["documents", "metadatas"],
        "limit": max(1, min(int(limit), 200)),
        "offset": max(0, int(offset)),
    }
    if len(where) == 1:
        kwargs["where"] = where
    elif len(where) > 1:
        kwargs["where"] = {"$and": [{key: value} for key, value in where.items()]}
    result = col.get(**kwargs)
    thoughts = []
    for drawer_id, doc, meta in zip(
        result.get("ids") or [],
        result.get("documents") or [],
        result.get("metadatas") or [],
    ):
        meta = meta or {}
        filed_at = meta.get("filed_at") or meta.get("timestamp") or ""
        if since and filed_at and filed_at < since:
            continue
        trust = _trust.get(drawer_id) or {"status": "current"}
        if trust.get("status", "current") == "quarantined" and trust_status != "quarantined":
            continue
        if trust_status and trust.get("status") != trust_status:
            continue
        thoughts.append(
            {
                "id": drawer_id,
                "content": doc,
                "wing": meta.get("wing", "unknown"),
                "room": meta.get("room", "unknown"),
                "created_at": filed_at,
                "trust_status": trust.get("status", "current"),
            }
        )
    return {"thoughts": thoughts, "limit": limit, "offset": offset}


def tool_openbrain_thought_stats():
    from .sources.store import SourceStore
    from .wiki.compiler import WikiCompiler

    status = tool_status()
    return {
        "drawers": status.get("total_drawers", 0),
        "wings": status.get("wings", {}),
        "rooms": status.get("rooms", {}),
        "trust": _trust.stats(),
        "sources": SourceStore(db_path=_hybrid.kg_path).stats(),
        "wiki": WikiCompiler(db_path=_hybrid.kg_path).status(),
    }


def tool_openbrain_search(query: str):
    from .mcp.compat.openbrain import connector_search_result
    from .sources.store import SourceStore
    from .wiki.context_pack import build_context_pack

    results = []
    for hit in _hybrid.search(query, n_results=5):
        trust_status = hit.get("trust_status", "current")
        if str(hit.get("id", "")).startswith("kg_") or trust_status == "quarantined":
            continue
        results.append(
            connector_search_result(
                "drawer",
                hit["id"],
                f"{hit.get('wing', '')}/{hit.get('room', '')}",
                hit.get("text", ""),
                hit.get("score", 0),
            )
        )
    source_store = SourceStore(db_path=_hybrid.kg_path)
    for hit in source_store.search(query, limit=5):
        results.append(
            connector_search_result(
                "chunk", hit["id"], hit.get("title", hit["source_id"]), hit["text"], 0.8
            )
        )
    pack = build_context_pack(query, db_path=_hybrid.kg_path, anaktoron_path=_config.anaktoron_path)
    for page in pack.get("wiki_pages", [])[:5]:
        results.append(
            connector_search_result(
                "wiki",
                page["path"],
                page.get("title", page["path"]),
                page.get("text", ""),
                page.get("relevance", 0.5),
            )
        )
    return {"query": query, "results": results[:15]}


def tool_openbrain_fetch(id: str):
    from pathlib import Path
    from .sources.store import SourceStore
    from .wiki.compiler import WikiCompiler

    if ":" not in id:
        return {"error": "id must be typed as drawer:<id>, source:<id>, chunk:<id>, or wiki:<path>"}
    kind, identifier = id.split(":", 1)
    if kind == "drawer":
        col = _get_collection()
        if not col:
            return _no_anaktoron()
        result = col.get(ids=[identifier], include=["documents", "metadatas"])
        if not result.get("ids"):
            return {"error": f"drawer not found: {identifier}"}
        trust = _trust.get(identifier) or {"status": "current"}
        if _is_quarantined_trust(trust.get("status")):
            return {"error": f"drawer is quarantined: {identifier}"}
        meta = result["metadatas"][0] or {}
        return {
            "id": id,
            "content": result["documents"][0] or "",
            "metadata": meta,
            "trust": trust,
            "warnings": _trust_warning(trust.get("status"), identifier),
        }
    source_store = SourceStore(db_path=_hybrid.kg_path)
    if kind == "source":
        source = source_store.get_source(identifier)
        if _is_quarantined_trust(source.get("trust_status")):
            return {"error": f"source is quarantined: {identifier}"}
        payload = source_store.read_source(identifier, include_chunks=False)
        payload["warnings"] = _trust_warning(source.get("trust_status"), identifier)
        return {"id": id, **payload}
    if kind == "chunk":
        chunk = source_store.get_chunk(identifier)
        source = source_store.get_source(chunk["source_id"])
        if _is_quarantined_trust(source.get("trust_status")):
            return {"error": f"source chunk is quarantined: {identifier}"}
        return {
            "id": id,
            "chunk": chunk,
            "warnings": _trust_warning(source.get("trust_status"), chunk["source_id"]),
        }
    if kind == "wiki":
        from .wiki.provenance import resolve_page_provenance

        compiler = WikiCompiler(db_path=_hybrid.kg_path)
        page = compiler.wiki_path / identifier
        if not page.suffix:
            page = page.with_suffix(".md")
        if not page.exists():
            return {"error": f"wiki page not found: {identifier}"}
        text = page.read_text(encoding="utf-8", errors="replace")
        rel = str(page.relative_to(compiler.wiki_path)).replace("\\", "/")
        provenance = resolve_page_provenance(text, rel, db_path=_hybrid.kg_path)
        if _is_quarantined_trust(provenance.effective_trust_status):
            return {"error": f"wiki page is quarantined: {identifier}"}
        warnings = _trust_warning(provenance.effective_trust_status, identifier)
        warnings.extend(provenance.warnings)
        return {
            "id": id,
            "path": str(Path(identifier)),
            "content": text,
            "warnings": warnings,
        }
    return {"error": f"unsupported id kind: {kind}"}


def tool_delete_drawer(drawer_id: str):
    """Delete a single drawer by ID from both stores."""
    col = _get_collection()
    if not col:
        return _no_anaktoron()
    existing = col.get(ids=[drawer_id])
    if not existing["ids"]:
        return {"success": False, "error": f"Drawer not found: {drawer_id}"}
    try:
        # 1. Delete from Chroma
        col.delete(ids=[drawer_id])

        # 2. Delete from FTS5
        conn = sqlite3.connect(_hybrid.kg_path)
        conn.execute("DELETE FROM drawers_fts WHERE drawer_id = ?", (drawer_id,))
        conn.commit()
        conn.close()

        # 3. Soft-delete from trust layer (mark historical instead of hard-removing)
        trust_rec = _trust.get(drawer_id)
        if trust_rec:
            _trust.update_status(drawer_id, "historical", reason="drawer deleted", changed_by="mcp")

        logger.info(f"Deleted drawer: {drawer_id}")
        return {"success": True, "drawer_id": drawer_id}
    except Exception as e:
        logger.error(f"Caught exception: {e}")
        logger.exception("delete_drawer failed")
        return {"success": False, "error": "Failed to delete drawer"}


# ==================== TRUST TOOLS ====================


def tool_trust_stats():
    """Return trust layer statistics."""
    return _trust.stats()


def tool_verify_drawer(drawer_id: str):
    """Mark a drawer as verified — bumps confidence by 0.05, max 1.0."""
    rec = _trust.get(drawer_id)
    if rec is None:
        return {"error": f"No trust record for {drawer_id}"}
    return _trust.verify(drawer_id)


def tool_challenge_drawer(drawer_id: str, reason: str = ""):
    """Challenge a drawer's accuracy — lowers confidence by 0.1, min 0.1."""
    rec = _trust.get(drawer_id)
    if rec is None:
        return {"error": f"No trust record for {drawer_id}"}
    result = _trust.challenge(drawer_id)
    if reason:
        _trust.update_status(drawer_id, "contested", reason=reason, changed_by="mcp")
    return result


def tool_get_contested():
    """Return contested drawers — memories with unresolved conflicts. Review these."""
    return {"contested": _trust.get_contested(limit=20)}


def tool_resolve_contest(drawer_id: str, winner_id: str, resolution_note: str = ""):
    """
    Manually resolve a contested memory.
    drawer_id: one of the two conflicting drawers (the contested one).
    winner_id: the drawer_id that wins (the correct/current version).
    The other one is marked superseded.
    """
    # Determine the loser — it's whichever of the pair is NOT the winner.
    # Both drawer_id and winner_id must be valid trust records.
    if drawer_id == winner_id:
        return {"error": "drawer_id and winner_id must be different drawers"}

    for did in [drawer_id, winner_id]:
        if _trust.get(did) is None:
            return {"error": f"No trust record for {did}"}

    loser_id = drawer_id if winner_id != drawer_id else winner_id

    _trust.update_status(
        loser_id,
        "superseded",
        superseded_by=winner_id,
        reason=f"manual resolution: {resolution_note}",
        changed_by="user",
    )
    _trust.update_status(
        winner_id,
        "current",
        reason=f"manual resolution winner: {resolution_note}",
        changed_by="user",
    )

    # Mark any pending conflicts involving these two as resolved
    pending = _trust.get_pending_conflicts()
    for c in pending:
        if {c["drawer_id_a"], c["drawer_id_b"]} == {drawer_id, winner_id}:
            _trust.resolve_conflict(c["conflict_id"], winner_id, resolution_note)

    return {
        "success": True,
        "winner": winner_id,
        "loser": loser_id,
        "resolved_note": resolution_note,
    }


# ==================== KNOWLEDGE GRAPH ====================


def tool_kg_query(entity: str, as_of: str = None, direction: str = "both"):
    """Query the knowledge graph for an entity's relationships."""
    results = _kg.query_entity(entity, as_of=as_of, direction=direction)
    return {"entity": entity, "as_of": as_of, "facts": results, "count": len(results)}


def tool_kg_add(
    subject: str, predicate: str, object: str, valid_from: str = None, source_closet: str = None
):
    """Add a relationship to the knowledge graph."""
    triple_id = _kg.add_triple(
        subject, predicate, object, valid_from=valid_from, source_closet=source_closet
    )
    return {"success": True, "triple_id": triple_id, "fact": f"{subject} → {predicate} → {object}"}


def tool_kg_invalidate(subject: str, predicate: str, object: str, ended: str = None):
    """Mark a fact as no longer true (set end date)."""
    _kg.invalidate(subject, predicate, object, ended=ended)
    return {
        "success": True,
        "fact": f"{subject} → {predicate} → {object}",
        "ended": ended or "today",
    }


def tool_kg_timeline(entity: str = None):
    """Get chronological timeline of facts, optionally for one entity."""
    results = _kg.timeline(entity)
    return {"entity": entity or "all", "timeline": results, "count": len(results)}


def tool_kg_stats():
    """Knowledge graph overview: entities, triples, relationship types."""
    return _kg.stats()


# ==================== AGENT DIARY ====================


def tool_diary_write(agent_name: str, entry: str, topic: str = "general"):
    """
    Write a diary entry for this agent. Each agent gets its own wing
    with a diary room. Entries are timestamped and accumulate over time.

    This is the agent's personal journal — observations, thoughts,
    what it worked on, what it noticed, what it thinks matters.
    """
    wing = f"wing_{agent_name.lower().replace(' ', '_')}"
    room = "diary"
    col = _get_collection(create=True)
    if not col:
        return _no_anaktoron()

    now = datetime.now()
    entry_id = f"diary_{wing}_{now.strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(entry[:50].encode()).hexdigest()[:8]}"

    try:
        col.add(
            ids=[entry_id],
            documents=[entry],
            metadatas=[
                {
                    "wing": wing,
                    "room": room,
                    "hall": "hall_diary",
                    "topic": topic,
                    "type": "diary_entry",
                    "agent": agent_name,
                    "filed_at": now.isoformat(),
                    "date": now.strftime("%Y-%m-%d"),
                }
            ],
        )

        # 2. Add to SQLite FTS5 (Lexical Mirror)
        import sqlite3

        KnowledgeGraph(db_path=_hybrid.kg_path)  # Ensure schema exists
        conn = sqlite3.connect(_hybrid.kg_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO drawers_fts (drawer_id, content, wing, room) VALUES (?, ?, ?, ?)",
                (entry_id, entry, wing, room),
            )
            conn.commit()
        finally:
            conn.close()

        # 3. Create trust record (idempotent)
        _trust.create(entry_id, wing=wing, room=room)

        logger.info(f"Diary entry: {entry_id} → {wing}/diary/{topic}")
        return {
            "success": True,
            "entry_id": entry_id,
            "agent": agent_name,
            "topic": topic,
            "timestamp": now.isoformat(),
        }
    except Exception as e:
        logger.error(f"Caught exception: {e}")
        logger.exception("diary_write failed")
        return {"success": False, "error": "Failed to write diary entry"}


def tool_diary_read(agent_name: str, last_n: int = 10):
    """
    Read an agent's recent diary entries. Returns the last N entries
    in chronological order — the agent's personal journal.
    """
    last_n = max(1, min(last_n, 100))
    wing = f"wing_{agent_name.lower().replace(' ', '_')}"
    col = _get_collection()
    if not col:
        return _no_anaktoron()

    try:
        results = col.get(
            where={"$and": [{"wing": wing}, {"room": "diary"}]},
            include=["documents", "metadatas"],
            limit=10000,
        )

        if not results["ids"]:
            return {"agent": agent_name, "entries": [], "message": "No diary entries yet."}

        # Combine and sort by timestamp
        entries = []
        for doc, meta in zip(results["documents"], results["metadatas"]):
            entries.append(
                {
                    "date": meta.get("date", ""),
                    "timestamp": meta.get("filed_at", ""),
                    "topic": meta.get("topic", ""),
                    "content": doc,
                }
            )

        entries.sort(key=lambda x: x["timestamp"], reverse=True)
        entries = entries[:last_n]

        return {
            "agent": agent_name,
            "entries": entries,
            "total": len(results["ids"]),
            "showing": len(entries),
        }
    except Exception as e:
        logger.error(f"Caught exception: {e}")
        logger.exception("diary_read failed")
        return {"error": "Failed to read diary entries"}


# ==================== MCP PROTOCOL ====================

TOOLS = {
    "mnemion_status": {
        "description": "CALL THIS FIRST at every session start. Returns your behavioral protocol, AAAK memory dialect spec, and Anaktoron overview (wings, rooms, drawer counts). Required for correct operation — the protocol tells you when and how to use all other tools.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_status,
    },
    "mnemion_list_wings": {
        "description": "List all wings with drawer counts",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_list_wings,
    },
    "mnemion_list_rooms": {
        "description": "List rooms within a wing (or all rooms if no wing given)",
        "input_schema": {
            "type": "object",
            "properties": {
                "wing": {"type": "string", "description": "Wing to list rooms for (optional)"},
            },
        },
        "handler": tool_list_rooms,
    },
    "mnemion_get_taxonomy": {
        "description": "Full taxonomy: wing → room → drawer count",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_get_taxonomy,
    },
    "mnemion_get_aaak_spec": {
        "description": "Get the AAAK dialect specification — the compressed memory format Mnemion uses. Call this if you need to read or write AAAK-compressed memories.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_get_aaak_spec,
    },
    "mnemion_kg_query": {
        "description": "Query the knowledge graph for an entity's relationships. Use BEFORE answering questions about specific people, projects, or things — get typed facts with temporal validity. E.g. 'Max' → child_of Alice, loves chess. Filter by date with as_of to see what was true at a point in time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "Entity to query (e.g. 'Max', 'MyProject', 'Alice')",
                },
                "as_of": {
                    "type": "string",
                    "description": "Date filter — only facts valid at this date (YYYY-MM-DD, optional)",
                },
                "direction": {
                    "type": "string",
                    "description": "outgoing (entity→?), incoming (?→entity), or both (default: both)",
                },
            },
            "required": ["entity"],
        },
        "handler": tool_kg_query,
    },
    "mnemion_kg_add": {
        "description": "Add a fact to the knowledge graph. Subject → predicate → object with optional time window. E.g. ('Max', 'started_school', 'Year 7', valid_from='2026-09-01').",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "The entity doing/being something"},
                "predicate": {
                    "type": "string",
                    "description": "The relationship type (e.g. 'loves', 'works_on', 'daughter_of')",
                },
                "object": {"type": "string", "description": "The entity being connected to"},
                "valid_from": {
                    "type": "string",
                    "description": "When this became true (YYYY-MM-DD, optional)",
                },
                "source_closet": {
                    "type": "string",
                    "description": "Closet ID where this fact appears (optional)",
                },
            },
            "required": ["subject", "predicate", "object"],
        },
        "handler": tool_kg_add,
    },
    "mnemion_kg_invalidate": {
        "description": "Mark a fact as no longer true. E.g. ankle injury resolved, job ended, moved house.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Entity"},
                "predicate": {"type": "string", "description": "Relationship"},
                "object": {"type": "string", "description": "Connected entity"},
                "ended": {
                    "type": "string",
                    "description": "When it stopped being true (YYYY-MM-DD, default: today)",
                },
            },
            "required": ["subject", "predicate", "object"],
        },
        "handler": tool_kg_invalidate,
    },
    "mnemion_kg_timeline": {
        "description": "Chronological timeline of facts. Shows the story of an entity (or everything) in order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "Entity to get timeline for (optional — omit for full timeline)",
                },
            },
        },
        "handler": tool_kg_timeline,
    },
    "mnemion_kg_stats": {
        "description": "Knowledge graph overview: entities, triples, current vs expired facts, relationship types.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_kg_stats,
    },
    "mnemion_traverse": {
        "description": "Walk the Anaktoron graph from a room. Shows connected ideas across wings — the tunnels. Like following a thread through the Anaktoron: start at 'chromadb-setup' in wing_code, discover it connects to wing_myproject (planning) and wing_user (feelings about it).",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_room": {
                    "type": "string",
                    "description": "Room to start from (e.g. 'chromadb-setup', 'riley-school')",
                },
                "max_hops": {
                    "type": "integer",
                    "description": "How many connections to follow (default: 2)",
                },
            },
            "required": ["start_room"],
        },
        "handler": tool_traverse_graph,
    },
    "mnemion_find_tunnels": {
        "description": "Find rooms that bridge two wings — the hallways connecting different domains. E.g. what topics connect wing_code to wing_team?",
        "input_schema": {
            "type": "object",
            "properties": {
                "wing_a": {"type": "string", "description": "First wing (optional)"},
                "wing_b": {"type": "string", "description": "Second wing (optional)"},
            },
        },
        "handler": tool_find_tunnels,
    },
    "mnemion_graph_stats": {
        "description": "Anaktoron graph overview: total rooms, tunnel connections, edges between wings.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_graph_stats,
    },
    "mnemion_search": {
        "description": "Hybrid search (vector + lexical) across all memories. Use BEFORE answering any question about past events, people, projects, or facts — verify from the Anaktoron, don't guess. Returns verbatim drawer content with similarity scores.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for"},
                "limit": {"type": "integer", "description": "Max results (default 5)"},
                "wing": {"type": "string", "description": "Filter by wing (optional)"},
                "room": {"type": "string", "description": "Filter by room (optional)"},
                "min_similarity": {
                    "type": "number",
                    "description": "Minimum similarity threshold 0-1 (default 0.0, discards negative scores). Raise to 0.1+ for stricter filtering.",
                },
            },
            "required": ["query"],
        },
        "handler": tool_search,
    },
    "mnemion_reconstruct": {
        "description": "Active reconstruction search. Uses cognitive graph evidence before hydrating raw drawers, returning an evidence trail.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Question or search intent"},
                "budget": {
                    "type": "integer",
                    "description": "Max cognitive units to traverse (default 10)",
                },
            },
            "required": ["query"],
        },
        "handler": tool_reconstruct,
    },
    "mnemion_consolidate": {
        "description": "Extract structured cognitive units and causal edges from raw drawers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max drawers to consolidate"},
                "dry_run": {"type": "boolean", "description": "Preview without writing"},
            },
        },
        "handler": tool_consolidate,
    },
    "mnemion_memory_guard_scan": {
        "description": "Scan memories for instruction-injection or privacy-exfiltration risks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "quarantine": {
                    "type": "boolean",
                    "description": "Mark flagged drawers quarantined",
                },
            },
        },
        "handler": tool_memory_guard_scan,
    },
    "mnemion_get_evidence_trail": {
        "description": "Return cognitive graph units and causal edges linked to a drawer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "drawer_id": {"type": "string", "description": "Drawer ID"},
            },
            "required": ["drawer_id"],
        },
        "handler": tool_get_evidence_trail,
    },
    "mnemion_predict_next": {
        "description": "Imagine the next relevant context based on current session history. Returns a prediction of which room or topic the user will likely need next.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_predict_next,
    },
    "mnemion_check_duplicate": {
        "description": "Check if content already exists in the Anaktoron before filing",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Content to check"},
                "threshold": {
                    "type": "number",
                    "description": "Similarity threshold 0-1 (default 0.9)",
                },
            },
            "required": ["content"],
        },
        "handler": tool_check_duplicate,
    },
    "mnemion_add_drawer": {
        "description": "Save a new memory to the Anaktoron. Call when you learn a new fact, the user shares something important, or something changes. Content is stored verbatim — never summarize, preserve exact words. Checks for duplicates automatically.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wing": {"type": "string", "description": "Wing (project name)"},
                "room": {
                    "type": "string",
                    "description": "Room (aspect: backend, decisions, meetings...)",
                },
                "content": {
                    "type": "string",
                    "description": "Verbatim content to store — exact words, never summarized",
                },
                "source_file": {"type": "string", "description": "Where this came from (optional)"},
            },
            "required": ["wing", "room", "content"],
        },
        "handler": tool_add_drawer,
    },
    "mnemion_source_add": {
        "description": "Add an immutable raw source file to Mnemion's source vault.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "source_type": {"type": "string"},
                "title": {"type": "string"},
                "author": {"type": "string"},
                "privacy_class": {"type": "string", "default": "private"},
                "compile_wiki": {"type": "boolean", "default": False},
            },
            "required": ["path"],
        },
        "handler": tool_source_add,
    },
    "mnemion_source_list": {
        "description": "List raw sources in the source vault.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_type": {"type": "string"},
                "privacy_class": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
        },
        "handler": tool_source_list,
    },
    "mnemion_source_read": {
        "description": "Read a raw source and optionally its chunks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string"},
                "chunks": {"type": "boolean", "default": False},
            },
            "required": ["source_id"],
        },
        "handler": tool_source_read,
    },
    "mnemion_source_search": {
        "description": "Search immutable raw source chunks with SQLite FTS5.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
                "privacy_class": {"type": "string"},
            },
            "required": ["query"],
        },
        "handler": tool_source_search,
    },
    "mnemion_wiki_compile": {
        "description": "Compile source-backed Markdown wiki pages. Defaults to review mode unless apply=true.",
        "input_schema": {
            "type": "object",
            "properties": {
                "all": {"type": "boolean", "default": False},
                "source_id": {"type": "string"},
                "apply": {"type": "boolean", "default": False},
                "review": {"type": "boolean", "default": True},
            },
        },
        "handler": tool_wiki_compile,
    },
    "mnemion_wiki_page_get": {
        "description": "Fetch a compiled wiki page by path or page id.",
        "input_schema": {
            "type": "object",
            "properties": {"id_or_path": {"type": "string"}},
            "required": ["id_or_path"],
        },
        "handler": tool_wiki_page_get,
    },
    "mnemion_wiki_lint": {
        "description": "Lint compiled wiki pages for frontmatter, generated markers, and provenance issues.",
        "input_schema": {
            "type": "object",
            "properties": {
                "json_output": {"type": "boolean", "default": True},
                "page": {"type": "string"},
            },
        },
        "handler": tool_wiki_lint,
    },
    "mnemion_wiki_context_pack": {
        "description": "Build a query-focused context pack from wiki pages, source chunks, drawers, and trust state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "mode": {"type": "string", "default": "answer_question"},
                "token_budget": {"type": "integer", "default": 6000},
            },
            "required": ["query"],
        },
        "handler": tool_wiki_context_pack,
    },
    "mnemion_wiki_blast_radius": {
        "description": "Estimate affected wiki pages for a source, drawer, or topic update.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string"},
                "drawer_id": {"type": "string"},
                "topic": {"type": "string"},
            },
        },
        "handler": tool_wiki_blast_radius,
    },
    "mnemion_wiki_export_obsidian": {
        "description": "Export compiled wiki pages into a managed Obsidian subfolder.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "include_sensitive": {"type": "boolean", "default": False},
            },
        },
        "handler": tool_wiki_export_obsidian,
    },
    "capture_thought": {
        "description": "Open Brain-compatible alias: capture text into Mnemion as a normal drawer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "source": {"type": "string"},
                "metadata": {"type": "object"},
                "wing": {"type": "string"},
                "room": {"type": "string"},
                "privacy_class": {"type": "string"},
                "compile_wiki": {"type": "boolean", "default": False},
            },
            "required": ["content"],
        },
        "handler": tool_openbrain_capture_thought,
    },
    "search_thoughts": {
        "description": "Open Brain-compatible alias: search Mnemion drawers through native hybrid retrieval.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
                "min_similarity": {"type": "number", "default": 0.0},
                "include_contested": {"type": "boolean", "default": True},
                "include_superseded": {"type": "boolean", "default": False},
                "wing": {"type": "string"},
                "room": {"type": "string"},
            },
            "required": ["query"],
        },
        "handler": tool_openbrain_search_thoughts,
    },
    "list_thoughts": {
        "description": "Open Brain-compatible alias: list recent Mnemion drawers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
                "offset": {"type": "integer", "default": 0},
                "wing": {"type": "string"},
                "room": {"type": "string"},
                "since": {"type": "string"},
                "trust_status": {"type": "string"},
            },
        },
        "handler": tool_openbrain_list_thoughts,
    },
    "thought_stats": {
        "description": "Open Brain-compatible alias: return Mnemion drawer, trust, source, and wiki stats.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_openbrain_thought_stats,
    },
    "search": {
        "description": "OpenAI/ChatGPT connector-compatible search over Mnemion drawers, source chunks, and wiki pages.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "handler": tool_openbrain_search,
    },
    "fetch": {
        "description": "OpenAI/ChatGPT connector-compatible fetch for typed IDs returned by search.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
        "handler": tool_openbrain_fetch,
    },
    "mnemion_delete_drawer": {
        "description": "Delete a drawer by ID from both stores. Trust record is soft-deleted (marked historical).",
        "input_schema": {
            "type": "object",
            "properties": {
                "drawer_id": {"type": "string", "description": "ID of the drawer to delete"},
            },
            "required": ["drawer_id"],
        },
        "handler": tool_delete_drawer,
    },
    "mnemion_trust_stats": {
        "description": "Trust layer overview — counts by status (current/superseded/contested/historical), avg confidence, pending conflicts.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_trust_stats,
    },
    "mnemion_verify": {
        "description": "Verify a drawer as accurate — confirms the memory, bumps confidence.",
        "input_schema": {
            "type": "object",
            "properties": {
                "drawer_id": {"type": "string", "description": "Drawer ID to verify"},
            },
            "required": ["drawer_id"],
        },
        "handler": tool_verify_drawer,
    },
    "mnemion_challenge": {
        "description": "Challenge a drawer's accuracy. Lowers confidence and marks it contested for review.",
        "input_schema": {
            "type": "object",
            "properties": {
                "drawer_id": {"type": "string", "description": "Drawer ID to challenge"},
                "reason": {
                    "type": "string",
                    "description": "Why you think this is wrong (optional)",
                },
            },
            "required": ["drawer_id"],
        },
        "handler": tool_challenge_drawer,
    },
    "mnemion_get_contested": {
        "description": "Return contested memories — drawers with unresolved conflicts that need review.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_get_contested,
    },
    "mnemion_resolve_contest": {
        "description": "Manually resolve a contested memory by picking the winner. The loser is marked superseded.",
        "input_schema": {
            "type": "object",
            "properties": {
                "drawer_id": {"type": "string", "description": "Drawer ID that is contested"},
                "winner_id": {
                    "type": "string",
                    "description": "Drawer ID of the correct/current version",
                },
                "resolution_note": {
                    "type": "string",
                    "description": "Why this one wins (optional)",
                },
            },
            "required": ["drawer_id", "winner_id"],
        },
        "handler": tool_resolve_contest,
    },
    "mnemion_diary_write": {
        "description": "Write to your agent diary. Call AT END OF EVERY SESSION with your name and a summary of what happened, what you learned, what matters. Each agent has their own diary wing. Write in AAAK format for compression — e.g. 'SESSION:2026-04-04|built.anaktoron.graph+diary.tools|★★★'. Use entity codes from the AAAK spec.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Your name — each agent gets their own diary wing",
                },
                "entry": {
                    "type": "string",
                    "description": "Your diary entry in AAAK format — compressed, entity-coded, emotion-marked",
                },
                "topic": {
                    "type": "string",
                    "description": "Topic tag (optional, default: general)",
                },
            },
            "required": ["agent_name", "entry"],
        },
        "handler": tool_diary_write,
    },
    "mnemion_diary_read": {
        "description": "Read your recent diary entries (in AAAK). See what past versions of yourself recorded — your journal across sessions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Your name — each agent gets their own diary wing",
                },
                "last_n": {
                    "type": "integer",
                    "description": "Number of recent entries to read (default: 10)",
                },
            },
            "required": ["agent_name"],
        },
        "handler": tool_diary_read,
    },
}


def handle_request(request):
    method = request.get("method", "")
    params = request.get("params", {})
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "prompts": {}},
                "serverInfo": {"name": "mnemion", "version": __version__},
            },
        }
    elif method == "notifications/initialized":
        return None
    elif method == "prompts/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "prompts": [
                    {
                        "name": "mnemion_protocol",
                        "description": "The Mnemion memory protocol — behavioral rules for any AI using this Anaktoron. Request this at session start if you did not call mnemion_status yet.",
                    }
                ]
            },
        }
    elif method == "prompts/get":
        prompt_name = params.get("name", "")
        if prompt_name == "mnemion_protocol":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "description": "Mnemion behavioral protocol",
                    "messages": [
                        {
                            "role": "user",
                            "content": {
                                "type": "text",
                                "text": ANAKTORON_PROTOCOL + "\n\n" + AAAK_SPEC,
                            },
                        }
                    ],
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32602, "message": f"Unknown prompt: {prompt_name}"},
        }
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {"name": n, "description": t["description"], "inputSchema": t["input_schema"]}
                    for n, t in TOOLS.items()
                ]
            },
        }
    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        if tool_name not in TOOLS:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }
        # Whitelist arguments to declared schema properties only.
        # Prevents callers from injecting internal params (added_by, source_file, etc.)
        # that could spoof the audit trail.
        schema_props = TOOLS[tool_name]["input_schema"].get("properties", {})
        tool_args = {k: v for k, v in tool_args.items() if k in schema_props}
        # Coerce argument types based on input_schema.
        # MCP JSON transport may deliver integers as floats or strings;
        # ChromaDB and Python slicing require native int.
        for key, value in list(tool_args.items()):
            prop_schema = schema_props.get(key, {})
            declared_type = prop_schema.get("type")
            if declared_type == "integer" and not isinstance(value, int):
                tool_args[key] = int(value)
            elif declared_type == "number" and not isinstance(value, (int, float)):
                tool_args[key] = float(value)
        try:
            tool_args.pop("wait_for_previous", None)
            result = TOOLS[tool_name]["handler"](**tool_args)
            _write_heartbeat(tool_name)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
            }
        except Exception as e:
            logger.error(f"Caught exception: {e}")
            logger.exception(f"Tool error in {tool_name}")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": "Internal tool error"},
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def _write_heartbeat(tool_name: str = ""):
    """Write / update a heartbeat file for Studio agent status panel."""
    try:
        import os as _os

        hb_dir = _os.path.expanduser("~/.mnemion/heartbeats")
        _os.makedirs(hb_dir, exist_ok=True)
        pid = _os.getpid()
        hb_path = _os.path.join(hb_dir, f"{pid}.json")
        now_iso = datetime.now(timezone.utc).isoformat()

        existing = {}
        try:
            with open(hb_path) as f:
                existing = json.load(f)
        except Exception:
            pass

        existing.update(
            {
                "agent_id": existing.get(
                    "agent_id", _os.environ.get("MNEMION_AGENT_ID", f"mcp-{pid}")
                ),
                "pid": pid,
                "started_at": existing.get("started_at", now_iso),
                "last_call": now_iso,
                "last_tool": tool_name,
                "call_count": existing.get("call_count", 0) + 1,
            }
        )
        with open(hb_path, "w") as f:
            json.dump(existing, f)
    except Exception:
        pass  # heartbeat is best-effort — never break MCP calls


def main():
    logger.info("Mnemion MCP Server starting...")
    _write_heartbeat("startup")
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            request = json.loads(line)
            response = handle_request(request)
            if response is not None:
                _real_stdout.write(json.dumps(response) + "\n")
                _real_stdout.flush()
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Server error: {e}")


if __name__ == "__main__":
    main()
