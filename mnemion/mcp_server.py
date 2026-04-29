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
  mnemion_check_duplicate — check if content already exists before filing

Tools (write):
  mnemion_add_drawer      — file verbatim content into a wing/room
  mnemion_delete_drawer   — remove a drawer by ID
"""

# Save real stdout before any heavy import, then redirect fd 1 to stderr so
# native/library writes cannot corrupt the JSON-RPC wire on stdout.
import os
import sys

_real_stdout_fd = os.dup(1)
_real_stdout = os.fdopen(_real_stdout_fd, "w", buffering=1, encoding=sys.stdout.encoding or "utf-8")
os.dup2(2, 1)
sys.stdout = sys.stderr

import argparse  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import hashlib  # noqa: E402
import sqlite3  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

from .config import (  # noqa: E402
    DRAWER_HNSW_METADATA,
    MnemionConfig,
    sanitize_content,
    sanitize_kg_value,
    sanitize_name,
)
from .version import __version__  # noqa: E402
from .anaktoron_graph import (  # noqa: E402
    create_tunnel,
    delete_tunnel,
    find_tunnels,
    follow_tunnels,
    graph_stats,
    list_explicit_tunnels,
    traverse,
)
from .chroma_compat import (  # noqa: E402
    close_chroma_handles,
    db_stat,
    hnsw_capacity_status,
    make_persistent_client,
    pin_hnsw_threads,
    sqlite_metadata_summary,
)
from .knowledge_graph import KnowledgeGraph  # noqa: E402
from .hybrid_searcher import HybridSearcher  # noqa: E402
from .trust_lifecycle import DrawerTrust  # noqa: E402
from . import contradiction_detector as _cd  # noqa: E402
from .query_sanitizer import sanitize_query  # noqa: E402

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

_kg_path = os.path.join(os.path.dirname(_config.anaktoron_path), "knowledge_graph.sqlite3")
_vector_health = hnsw_capacity_status(_config.anaktoron_path, _config.collection_name)
_vector_disabled = bool(_vector_health.get("diverged"))

_kg = KnowledgeGraph(db_path=_kg_path) if _args.anaktoron else KnowledgeGraph()
_trust = DrawerTrust(db_path=_kg_path) if _args.anaktoron else DrawerTrust()
_hybrid = HybridSearcher(
    anaktoron_path=_config.anaktoron_path,
    kg_path=_kg_path,
    vector_disabled=_vector_disabled,
    vector_disabled_reason=_vector_health.get("message", ""),
)


_client_cache = None
_collection_cache = None
_client_cache_stat = (0, 0.0)


def _refresh_vector_disabled_flag():
    global _vector_health, _vector_disabled, _hybrid
    _vector_health = hnsw_capacity_status(_config.anaktoron_path, _config.collection_name)
    _vector_disabled = bool(_vector_health.get("diverged"))
    _hybrid = HybridSearcher(
        anaktoron_path=_config.anaktoron_path,
        kg_path=_kg_path,
        vector_disabled=_vector_disabled,
        vector_disabled_reason=_vector_health.get("message", ""),
    )
    return _vector_health


def _get_collection(create=False):
    """Return the ChromaDB collection, caching the client between calls."""
    global _client_cache, _collection_cache, _client_cache_stat
    try:
        if _vector_disabled:
            return None
        current_stat = db_stat(_config.anaktoron_path)
        if _client_cache is None or (
            _client_cache_stat != (0, 0.0)
            and current_stat != (0, 0.0)
            and abs(current_stat[1] - _client_cache_stat[1]) > 0.01
        ):
            _client_cache = make_persistent_client(
                _config.anaktoron_path,
                vector_safe=True,
                collection_name=_config.collection_name,
            )
            _collection_cache = None
            _client_cache_stat = db_stat(_config.anaktoron_path)
        if create:
            # Issue #218: cosine required so similarity = 1 - distance is meaningful.
            _collection_cache = _client_cache.get_or_create_collection(
                _config.collection_name, metadata=DRAWER_HNSW_METADATA
            )
            pin_hnsw_threads(_collection_cache)
        elif _collection_cache is None:
            _collection_cache = _client_cache.get_collection(_config.collection_name)
            pin_hnsw_threads(_collection_cache)
        return _collection_cache
    except Exception as e:
        logger.error(f"Caught exception: {e}")
        return None


def _no_anaktoron():
    if _vector_disabled:
        return {
            "error": "Vector search disabled",
            "hint": "Run: mnemion repair --mode status, then mnemion repair --mode rebuild if divergence is confirmed",
            "health": _vector_health,
        }
    return {
        "error": "No Anaktoron found",
        "hint": "Run: mnemion init <dir> && mnemion mine <dir>",
    }


_WAL_REDACT_KEYS = {
    "content",
    "text",
    "query",
    "entry",
    "object",
    "label",
    "reason",
    "resolution_note",
    "note",
    "description",
    "source_file",
    "file_path",
    "path",
}


def _wal_redacted_value(value):
    raw = "" if value is None else str(value)
    return {
        "redacted": True,
        "type": type(value).__name__,
        "length": len(raw),
        "sha256": hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16],
    }


def _redact_for_wal(value):
    if isinstance(value, dict):
        return {
            key: (_wal_redacted_value(val) if key in _WAL_REDACT_KEYS else _redact_for_wal(val))
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_redact_for_wal(item) for item in value]
    return value


def _write_wal(tool_name: str, args: dict) -> None:
    try:
        wal_dir = os.path.expanduser("~/.mnemion/wal")
        os.makedirs(wal_dir, exist_ok=True)
        record = {
            "tool": tool_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "args": _redact_for_wal(args),
        }
        with open(os.path.join(wal_dir, "write_log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
    except Exception:
        logger.debug("WAL write failed", exc_info=True)


def _sync_fts(drawer_id: str, content: str, wing: str, room: str) -> None:
    KnowledgeGraph(db_path=_hybrid.kg_path)  # Ensure schema exists
    with sqlite3.connect(_hybrid.kg_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO drawers_fts (drawer_id, content, wing, room) VALUES (?, ?, ?, ?)",
            (drawer_id, content, wing, room),
        )
        conn.commit()


def _delete_fts(drawer_id: str) -> None:
    with sqlite3.connect(_hybrid.kg_path) as conn:
        conn.execute("DELETE FROM drawers_fts WHERE drawer_id = ?", (drawer_id,))
        conn.commit()


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
    if _vector_disabled:
        summary = sqlite_metadata_summary(
            _config.anaktoron_path, _config.collection_name, kg_path=_kg_path
        )
        return {
            "version": __version__,
            "total_drawers": summary["total_drawers"] or _vector_health.get("sqlite_count") or 0,
            "wing_count": summary["wing_count"],
            "room_count": summary["room_count"],
            "wings": summary["wings"],
            "rooms": summary["rooms"],
            "metadata_unavailable": summary["metadata_unavailable"],
            "metadata_message": summary["metadata_message"],
            "anaktoron_path": _config.anaktoron_path,
            "protocol": ANAKTORON_PROTOCOL,
            "aaak_dialect": AAAK_SPEC,
            "health": _vector_health,
            "vector_disabled": True,
        }
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
        "health": _vector_health,
        "vector_disabled": _vector_disabled,
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

    query_info = sanitize_query(query)
    clean_query = query_info["clean_query"]
    limit = max(1, min(limit, 50))
    hits = _hybrid.search(
        clean_query, wing=wing, room=room, n_results=limit, min_similarity=min_similarity
    )

    # Log activity for predictive context
    for hit in hits:
        predictor.record_activity(hit["id"], hit.get("embedding"))

    return {
        "query": clean_query,
        "query_sanitizer": query_info,
        "filters": {"wing": wing, "room": room},
        "results": hits,
        "vector_disabled": _vector_disabled,
        "health": _vector_health if _vector_disabled else None,
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
    if _vector_disabled:
        return {
            "is_duplicate": None,
            "matches": [],
            "warning": "Vector duplicate detection is disabled because the HNSW index is diverged. Run `mnemion repair --mode status`.",
            "health": _vector_health,
        }
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


def tool_get_drawer(drawer_id: str):
    col = _get_collection()
    if not col:
        return _no_anaktoron()
    data = col.get(ids=[drawer_id], include=["documents", "metadatas"])
    if not data.get("ids"):
        return {"error": f"Drawer not found: {drawer_id}"}
    return {
        "drawer_id": drawer_id,
        "content": data.get("documents", [""])[0],
        "metadata": data.get("metadatas", [{}])[0] or {},
        "trust": _trust.get(drawer_id),
    }


def tool_list_drawers(wing: str = None, room: str = None, limit: int = 50, offset: int = 0):
    col = _get_collection()
    if not col:
        return _no_anaktoron()
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    where = None
    if wing and room:
        where = {"$and": [{"wing": wing}, {"room": room}]}
    elif wing:
        where = {"wing": wing}
    elif room:
        where = {"room": room}
    data = col.get(
        include=["documents", "metadatas"],
        where=where,
        limit=limit,
        offset=offset,
    )
    drawers = []
    for drawer_id, content, meta in zip(
        data.get("ids", []), data.get("documents", []), data.get("metadatas", [])
    ):
        drawers.append(
            {
                "drawer_id": drawer_id,
                "content": content,
                "metadata": meta or {},
                "trust": _trust.get(drawer_id),
            }
        )
    return {"drawers": drawers, "limit": limit, "offset": offset}


def tool_update_drawer(
    drawer_id: str,
    content: str = None,
    wing: str = None,
    room: str = None,
):
    _write_wal(
        "mnemion_update_drawer",
        {"drawer_id": drawer_id, "content": content, "wing": wing, "room": room},
    )
    col = _get_collection(create=True)
    if not col:
        return _no_anaktoron()
    existing = col.get(ids=[drawer_id], include=["documents", "metadatas"])
    if not existing.get("ids"):
        return {"success": False, "error": f"Drawer not found: {drawer_id}"}
    old_content = existing["documents"][0]
    old_meta = existing["metadatas"][0] or {}
    new_wing = sanitize_name(wing or old_meta.get("wing", "general"), "wing")
    new_room = sanitize_name(room or old_meta.get("room", "general"), "room")

    if content is not None and content.strip() != old_content:
        new_content = sanitize_content(content)
        new_id = f"drawer_{new_wing}_{new_room}_{hashlib.md5(new_content.encode(), usedforsecurity=False).hexdigest()[:16]}"
        meta = dict(old_meta)
        meta.update(
            {
                "wing": new_wing,
                "room": new_room,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "supersedes": drawer_id,
                "added_by": "mcp",
            }
        )
        inserted_chroma = False
        synced_fts = False
        created_trust = False
        rollback_errors = []
        try:
            col.upsert(ids=[new_id], documents=[new_content], metadatas=[meta])
            inserted_chroma = True
            _sync_fts(new_id, new_content, new_wing, new_room)
            synced_fts = True
            _trust.create(new_id, wing=new_wing, room=new_room)
            created_trust = True
            trust_result = _trust.update_status(
                drawer_id,
                "superseded",
                superseded_by=new_id,
                reason="drawer content updated",
                changed_by="mcp",
            )
            if isinstance(trust_result, dict) and trust_result.get("error"):
                raise RuntimeError(trust_result["error"])
        except Exception as exc:
            if inserted_chroma:
                try:
                    col.delete(ids=[new_id])
                except Exception as rollback_exc:
                    rollback_errors.append(f"chroma: {rollback_exc}")
            if synced_fts:
                try:
                    _delete_fts(new_id)
                except Exception as rollback_exc:
                    rollback_errors.append(f"fts: {rollback_exc}")
            if created_trust:
                try:
                    _trust.update_status(
                        new_id,
                        "historical",
                        reason="rollback after failed drawer update",
                        changed_by="mcp",
                    )
                except Exception as rollback_exc:
                    rollback_errors.append(f"trust: {rollback_exc}")
            return {
                "success": False,
                "error": f"Failed to update drawer safely: {exc}",
                "rollback_errors": rollback_errors,
            }
        _cd.spawn_detection(new_id, new_content, new_wing, new_room, _trust, _hybrid)
        return {
            "success": True,
            "drawer_id": new_id,
            "superseded": drawer_id,
            "wing": new_wing,
            "room": new_room,
        }

    meta = dict(old_meta)
    meta.update(
        {
            "wing": new_wing,
            "room": new_room,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    col.upsert(ids=[drawer_id], documents=[old_content], metadatas=[meta])
    _sync_fts(drawer_id, old_content, new_wing, new_room)
    try:
        with sqlite3.connect(_trust.db_path) as conn:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE drawer_trust SET wing=?, room=?, updated_at=? WHERE drawer_id=?",
                (new_wing, new_room, now, drawer_id),
            )
            conn.execute(
                """INSERT INTO drawer_trust_history
                   (drawer_id, old_status, new_status, old_confidence, new_confidence, reason, changed_by, changed_at)
                   SELECT drawer_id, status, status, confidence, confidence, ?, 'mcp', ?
                   FROM drawer_trust WHERE drawer_id=?""",
                ("drawer metadata updated", now, drawer_id),
            )
            conn.commit()
    except Exception:
        logger.debug("Trust location update failed for %s", drawer_id, exc_info=True)
    return {"success": True, "drawer_id": drawer_id, "wing": new_wing, "room": new_room}


def tool_create_tunnel(
    source_wing: str,
    source_room: str,
    target_wing: str,
    target_room: str,
    label: str = "",
    source_drawer_id: str = "",
    target_drawer_id: str = "",
):
    _write_wal(
        "mnemion_create_tunnel",
        {
            "source_wing": source_wing,
            "source_room": source_room,
            "target_wing": target_wing,
            "target_room": target_room,
            "label": label,
        },
    )
    tunnel = create_tunnel(
        sanitize_name(source_wing, "source_wing"),
        sanitize_name(source_room, "source_room"),
        sanitize_name(target_wing, "target_wing"),
        sanitize_name(target_room, "target_room"),
        label=sanitize_kg_value(label, "label") if label else "",
        source_drawer_id=source_drawer_id or "",
        target_drawer_id=target_drawer_id or "",
        config=_config,
    )
    return {"success": True, "tunnel": tunnel}


def tool_list_tunnels(wing: str = None):
    return {
        "tunnels": list_explicit_tunnels(
            sanitize_name(wing, "wing") if wing else None, config=_config
        )
    }


def tool_delete_tunnel(tunnel_id: str):
    _write_wal("mnemion_delete_tunnel", {"tunnel_id": tunnel_id})
    return delete_tunnel(sanitize_name(tunnel_id, "tunnel_id"), config=_config)


def tool_follow_tunnels(wing: str, room: str):
    return follow_tunnels(sanitize_name(wing, "wing"), sanitize_name(room, "room"), config=_config)


def tool_reconnect():
    global _client_cache, _collection_cache, _client_cache_stat, _kg, _trust
    close_chroma_handles()
    _client_cache = None
    _collection_cache = None
    _client_cache_stat = (0, 0.0)
    _kg = KnowledgeGraph(db_path=_kg_path)
    _trust = DrawerTrust(db_path=_kg_path)
    health = _refresh_vector_disabled_flag()
    return {"success": True, "health": health, "vector_disabled": _vector_disabled}


def tool_hook_settings(silent_save: bool = None, desktop_toast: bool = None):
    changed = {}
    if silent_save is not None:
        changed.update(_config.set_hook_setting("hook_silent_save", bool(silent_save)))
    if desktop_toast is not None:
        changed.update(_config.set_hook_setting("hook_desktop_toast", bool(desktop_toast)))
    return {
        "success": True,
        "changed": changed,
        "settings": {
            "silent_save": _config.hook_silent_save,
            "desktop_toast": _config.hook_desktop_toast,
        },
    }


def tool_memories_filed_away():
    state_dir = os.path.expanduser("~/.mnemion/hook_state")
    checkpoint = os.path.join(state_dir, "last_checkpoint")
    exists = os.path.exists(checkpoint)
    return {
        "checkpoint_exists": exists,
        "checkpoint_path": checkpoint,
        "modified_at": datetime.fromtimestamp(
            os.path.getmtime(checkpoint), timezone.utc
        ).isoformat()
        if exists
        else None,
    }


def tool_repair_status():
    from .repair import status

    return status(_config.anaktoron_path, _config.collection_name)


# ==================== WRITE TOOLS ====================


def tool_add_drawer(
    wing: str, room: str, content: str, source_file: str = None, added_by: str = "mcp"
):
    """File verbatim content into a wing/room. Checks for duplicates and indexes in both stores."""
    wing = sanitize_name(wing, "wing")
    room = sanitize_name(room, "room")
    content = sanitize_content(content)
    _write_wal("mnemion_add_drawer", {"wing": wing, "room": room, "content": content})
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
        _sync_fts(drawer_id, content, wing, room)

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


def tool_delete_drawer(drawer_id: str):
    """Delete a single drawer by ID from both stores."""
    _write_wal("mnemion_delete_drawer", {"drawer_id": drawer_id})
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
        _delete_fts(drawer_id)

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
    _write_wal("mnemion_verify", {"drawer_id": drawer_id})
    rec = _trust.get(drawer_id)
    if rec is None:
        return {"error": f"No trust record for {drawer_id}"}
    return _trust.verify(drawer_id)


def tool_challenge_drawer(drawer_id: str, reason: str = ""):
    """Challenge a drawer's accuracy — lowers confidence by 0.1, min 0.1."""
    _write_wal("mnemion_challenge", {"drawer_id": drawer_id, "reason": reason})
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
    _write_wal(
        "mnemion_resolve_contest",
        {"drawer_id": drawer_id, "winner_id": winner_id, "resolution_note": resolution_note},
    )
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
    subject = sanitize_kg_value(subject, "subject")
    predicate = sanitize_name(predicate, "predicate")
    object = sanitize_kg_value(object, "object")
    _write_wal(
        "mnemion_kg_add",
        {"subject": subject, "predicate": predicate, "object": object},
    )
    triple_id = _kg.add_triple(
        subject, predicate, object, valid_from=valid_from, source_closet=source_closet
    )
    return {"success": True, "triple_id": triple_id, "fact": f"{subject} → {predicate} → {object}"}


def tool_kg_invalidate(subject: str, predicate: str, object: str, ended: str = None):
    """Mark a fact as no longer true (set end date)."""
    subject = sanitize_kg_value(subject, "subject")
    predicate = sanitize_name(predicate, "predicate")
    object = sanitize_kg_value(object, "object")
    _write_wal(
        "mnemion_kg_invalidate",
        {"subject": subject, "predicate": predicate, "object": object, "ended": ended},
    )
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
    display_agent_name = sanitize_name(agent_name, "agent_name")
    agent_name = display_agent_name.lower().replace(" ", "_")
    topic = sanitize_name(topic, "topic")
    entry = sanitize_content(entry, "entry")
    _write_wal("mnemion_diary_write", {"agent_name": agent_name, "entry": entry, "topic": topic})
    wing = f"wing_{agent_name}"
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
                    "agent": display_agent_name,
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
            "agent": display_agent_name,
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
    "mnemion_get_drawer": {
        "description": "Fetch one drawer by ID, including verbatim content, metadata, and trust record.",
        "input_schema": {
            "type": "object",
            "properties": {"drawer_id": {"type": "string", "description": "Drawer ID"}},
            "required": ["drawer_id"],
        },
        "handler": tool_get_drawer,
    },
    "mnemion_list_drawers": {
        "description": "List drawers with optional wing/room filters and pagination.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wing": {"type": "string", "description": "Filter by wing"},
                "room": {"type": "string", "description": "Filter by room"},
                "limit": {"type": "integer", "description": "Max rows, default 50"},
                "offset": {"type": "integer", "description": "Pagination offset"},
            },
        },
        "handler": tool_list_drawers,
    },
    "mnemion_update_drawer": {
        "description": "Update a drawer. Content changes create a superseding drawer; metadata-only moves update Chroma, FTS, and trust location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "drawer_id": {"type": "string", "description": "Drawer ID to update"},
                "content": {"type": "string", "description": "Replacement content, optional"},
                "wing": {"type": "string", "description": "New wing, optional"},
                "room": {"type": "string", "description": "New room, optional"},
            },
            "required": ["drawer_id"],
        },
        "handler": tool_update_drawer,
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
    "mnemion_create_tunnel": {
        "description": "Create an explicit tunnel between two Anaktoron wing/room locations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_wing": {"type": "string"},
                "source_room": {"type": "string"},
                "target_wing": {"type": "string"},
                "target_room": {"type": "string"},
                "label": {"type": "string"},
                "source_drawer_id": {"type": "string"},
                "target_drawer_id": {"type": "string"},
            },
            "required": ["source_wing", "source_room", "target_wing", "target_room"],
        },
        "handler": tool_create_tunnel,
    },
    "mnemion_list_tunnels": {
        "description": "List explicit tunnels, optionally filtered by wing.",
        "input_schema": {
            "type": "object",
            "properties": {"wing": {"type": "string", "description": "Optional wing filter"}},
        },
        "handler": tool_list_tunnels,
    },
    "mnemion_delete_tunnel": {
        "description": "Delete an explicit tunnel by ID.",
        "input_schema": {
            "type": "object",
            "properties": {"tunnel_id": {"type": "string"}},
            "required": ["tunnel_id"],
        },
        "handler": tool_delete_tunnel,
    },
    "mnemion_follow_tunnels": {
        "description": "Follow explicit tunnels from a wing/room location.",
        "input_schema": {
            "type": "object",
            "properties": {"wing": {"type": "string"}, "room": {"type": "string"}},
            "required": ["wing", "room"],
        },
        "handler": tool_follow_tunnels,
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
    "mnemion_reconnect": {
        "description": "Clear cached Chroma clients/collections after external CLI, Studio, or sync writes.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_reconnect,
    },
    "mnemion_hook_settings": {
        "description": "Read or update Mnemion hook settings for silent save and desktop toast behavior.",
        "input_schema": {
            "type": "object",
            "properties": {
                "silent_save": {"type": "boolean"},
                "desktop_toast": {"type": "boolean"},
            },
        },
        "handler": tool_hook_settings,
    },
    "mnemion_memories_filed_away": {
        "description": "Return latest hook checkpoint status so agents can verify save hooks persisted memory.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_memories_filed_away,
    },
    "mnemion_repair_status": {
        "description": "Read-only Anaktoron repair/health status without loading the vector segment.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_repair_status,
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
