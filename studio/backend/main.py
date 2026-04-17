"""
Mnemion Studio — FastAPI backend
=================================
Imports mnemion.* directly — no MCP overhead.

Usage:
    cd mnemion
    python -m studio.backend.main
    # or
    uvicorn studio.backend.main:app --reload --port 7891
"""

import io
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional

# Suppress chromadb/posthog stdout noise before importing
_saved_stdout = sys.stdout
sys.stdout = io.StringIO()
import chromadb  # noqa: E402
sys.stdout = _saved_stdout

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from mnemion.config import DRAWER_HNSW_METADATA, MnemionConfig  # noqa: E402
from mnemion.hybrid_searcher import HybridSearcher  # noqa: E402
from mnemion.knowledge_graph import KnowledgeGraph  # noqa: E402
from mnemion.trust_lifecycle import DrawerTrust  # noqa: E402
from mnemion.version import __version__  # noqa: E402
from . import connectors as _connectors  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger("studio")

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Mnemion Studio", version=__version__, docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(http://(localhost|127\.0\.0\.1)(:\d+)?|file://.*)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mnemion singletons ────────────────────────────────────────────────────────

_config = MnemionConfig()
_kg = KnowledgeGraph()
_hybrid = HybridSearcher()
_trust = DrawerTrust()

_chroma_client: Optional[chromadb.PersistentClient] = None
_collection: Optional[chromadb.Collection] = None


def _get_collection() -> chromadb.Collection:
    global _chroma_client, _collection
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=_config.anaktoron_path)
    if _collection is None:
        try:
            _collection = _chroma_client.get_collection(_config.collection_name)
        except Exception:
            _collection = _chroma_client.get_or_create_collection(
                _config.collection_name, metadata=DRAWER_HNSW_METADATA
            )
    return _collection


def _iter_metadatas(col, where=None, limit=None):
    """Paginated metadata iteration — handles 35k+ drawer anaktorons."""
    PAGE, offset = 5000, 0
    fetched = 0
    while True:
        batch_limit = PAGE if limit is None else min(PAGE, limit - fetched)
        if batch_limit <= 0:
            break
        kwargs = {"include": ["metadatas"], "limit": batch_limit, "offset": offset}
        if where:
            kwargs["where"] = where
        metas = col.get(**kwargs).get("metadatas") or []
        for m in metas:
            if m is not None:
                yield m
                fetched += 1
                if limit and fetched >= limit:
                    return
        if len(metas) < batch_limit:
            break
        offset += PAGE


# ── Pydantic models ───────────────────────────────────────────────────────────

class DrawerCreate(BaseModel):
    wing: str
    room: str
    content: str
    source_file: str = ""


class LLMConfig(BaseModel):
    backend: str
    url: str = ""
    model: str = ""
    api_key: str = ""


# ── Status & taxonomy ─────────────────────────────────────────────────────────

@app.get("/api/status")
def get_status():
    col = _get_collection()
    wings: dict = {}
    rooms: dict = {}
    for m in _iter_metadatas(col):
        w = m.get("wing", "unknown")
        r = m.get("room", "unknown")
        wings[w] = wings.get(w, 0) + 1
        rooms[r] = rooms.get(r, 0) + 1
    return {
        "version": __version__,
        "total_drawers": col.count(),
        "wing_count": len(wings),
        "room_count": len(rooms),
        "wings": wings,
        "rooms": rooms,
        "anaktoron_path": _config.anaktoron_path,
        "collection_name": _config.collection_name,
    }


@app.get("/api/taxonomy")
def get_taxonomy():
    """Full wing → room → count tree. Used for sidebar navigation."""
    col = _get_collection()
    taxonomy: dict = {}
    for m in _iter_metadatas(col):
        w = m.get("wing", "unknown")
        r = m.get("room", "unknown")
        taxonomy.setdefault(w, {})
        taxonomy[w][r] = taxonomy[w].get(r, 0) + 1
    return {"taxonomy": taxonomy}


# ── Drawers ───────────────────────────────────────────────────────────────────

@app.get("/api/drawers")
def list_drawers(
    wing: Optional[str] = None,
    room: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    col = _get_collection()
    where: dict = {}
    if wing:
        where["wing"] = wing
    if room:
        where["room"] = room

    kwargs: dict = {
        "include": ["documents", "metadatas"],
        "limit": limit,
        "offset": offset,
    }
    if where:
        kwargs["where"] = (
            where if len(where) == 1 else {"$and": [{k: v} for k, v in where.items()]}
        )

    result = col.get(**kwargs)
    drawers = []
    for i, did in enumerate(result.get("ids") or []):
        meta = (result.get("metadatas") or [])[i] or {}
        doc = (result.get("documents") or [])[i] or ""
        trust = _trust.get(did)
        drawers.append(
            {
                "id": did,
                "wing": meta.get("wing", "unknown"),
                "room": meta.get("room", "unknown"),
                "source": meta.get("source_file", ""),
                "added_by": meta.get("added_by", ""),
                "timestamp": meta.get("filed_at") or meta.get("timestamp", ""),
                "preview": doc[:280] + ("…" if len(doc) > 280 else ""),
                "char_count": len(doc),
                "trust": _trust_summary(trust),
            }
        )
    return {"drawers": drawers, "wing": wing, "room": room, "offset": offset, "limit": limit}


@app.get("/api/drawer/{drawer_id:path}")
def get_drawer(drawer_id: str):
    col = _get_collection()
    result = col.get(ids=[drawer_id], include=["documents", "metadatas"])
    if not result.get("ids"):
        raise HTTPException(404, "Drawer not found")
    meta = result["metadatas"][0] or {}
    doc = result["documents"][0] or ""
    trust_history = _trust_history(drawer_id)

    # Related drawers via hybrid search (exclude self)
    try:
        related_hits = _hybrid.search(doc[:400], n_results=6)
        related = [
            {
                "id": h["id"],
                "wing": h.get("wing", "unknown"),
                "room": h.get("room", "unknown"),
                "content": h.get("text", ""),
                "similarity": round(h.get("score", 0), 4),
            }
            for h in related_hits
            if h["id"] != drawer_id
        ][:5]
    except Exception:
        related = []

    return {
        "id": drawer_id,
        "wing": meta.get("wing", "unknown"),
        "room": meta.get("room", "unknown"),
        "source": meta.get("source_file", ""),
        "added_by": meta.get("added_by", ""),
        "timestamp": meta.get("filed_at") or meta.get("timestamp", ""),
        "content": doc,
        "char_count": len(doc),
        "trust": _trust.get(drawer_id),
        "trust_history": trust_history,
        "related": related,
    }


@app.delete("/api/drawer/{drawer_id:path}")
def delete_drawer(drawer_id: str):
    col = _get_collection()
    if not col.get(ids=[drawer_id]).get("ids"):
        raise HTTPException(404, "Drawer not found")
    col.delete(ids=[drawer_id])
    try:
        conn = sqlite3.connect(_hybrid.kg_path)
        conn.execute("DELETE FROM drawers_fts WHERE drawer_id = ?", (drawer_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass
    trust_rec = _trust.get(drawer_id)
    if trust_rec:
        _trust.update_status(drawer_id, "historical", reason="deleted via Studio", changed_by="studio")
    return {"success": True, "drawer_id": drawer_id}


@app.post("/api/drawer")
def create_drawer(body: DrawerCreate):
    from mnemion.mcp_server import tool_add_drawer
    result = tool_add_drawer(
        wing=body.wing,
        room=body.room,
        content=body.content,
        source_file=body.source_file or None,
        added_by="studio",
    )
    return result


# ── Search ────────────────────────────────────────────────────────────────────

@app.get("/api/drawers/recent")
def get_recent_drawers(limit: int = Query(7, ge=1, le=20)):
    """Return the most recently added drawers, sorted by timestamp desc."""
    col = _get_collection()
    total = col.count()
    if total == 0:
        return {"drawers": []}
    # Sample last batch (ChromaDB insertion order ≈ chronological)
    sample_size = min(500, total)
    offset = max(0, total - sample_size)
    result = col.get(
        include=["metadatas", "documents"],
        limit=sample_size,
        offset=offset,
    )
    items = []
    for did, meta, doc in zip(
        result.get("ids") or [],
        result.get("metadatas") or [],
        result.get("documents") or [],
    ):
        m = meta or {}
        items.append({
            "id": did,
            "wing": m.get("wing", "unknown"),
            "room": m.get("room", "unknown"),
            "timestamp": m.get("filed_at") or m.get("timestamp", ""),
            "added_by": m.get("added_by", ""),
            "preview": (doc or "")[:120],
        })
    items.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    return {"drawers": items[:limit]}


@app.get("/api/search")
def search(
    q: str = Query(..., min_length=1),
    wing: Optional[str] = None,
    room: Optional[str] = None,
    limit: int = Query(20, ge=1, le=50),
    min_similarity: float = Query(0.0, ge=0.0, le=1.0),
):
    hits = _hybrid.search(q, wing=wing, room=room, n_results=limit, min_similarity=min_similarity)
    # Transform for frontend: rename 'text'→'content', add similarity alias
    results = [
        {
            "id": h["id"],
            "wing": h.get("wing", "unknown"),
            "room": h.get("room", "unknown"),
            "content": h.get("text", ""),
            "score": h.get("score", 0),
            "similarity": round(h.get("score", 0), 4),
            "trust_status": h.get("trust_status"),
        }
        for h in hits
    ]
    return {"query": q, "count": len(results), "results": results}


# ── Knowledge graph ───────────────────────────────────────────────────────────

@app.get("/api/kg/graph")
def get_kg_graph(limit_nodes: int = Query(1500, ge=10, le=5000)):
    """All KG entities + triples. Used for the graph view."""
    conn = sqlite3.connect(_kg.db_path)
    conn.row_factory = sqlite3.Row
    try:
        entities = conn.execute(
            "SELECT id, name, type FROM entities LIMIT ?", (limit_nodes,)
        ).fetchall()
        entity_ids = {e["id"] for e in entities}
        triples = conn.execute(
            "SELECT id, subject, predicate, object, valid_from, valid_to, confidence FROM triples LIMIT 5000"
        ).fetchall()
    finally:
        conn.close()

    nodes = [
        {"id": e["id"], "label": e["name"], "type": e["type"] or "entity"}
        for e in entities
    ]
    edges = []
    for t in triples:
        if t["subject"] in entity_ids and t["object"] in entity_ids:
            edges.append({
                "id": t["id"],
                "source": t["subject"],
                "target": t["object"],
                "label": t["predicate"],
                "valid_from": t["valid_from"],
                "confidence": t["confidence"],
            })

    return {"nodes": nodes, "edges": edges}


@app.get("/api/kg/entity/{name}")
def get_entity(name: str):
    facts = _kg.query_entity(name, direction="both")
    return facts


@app.get("/api/kg/entities")
def list_entities(limit: int = Query(200, ge=1, le=2000)):
    conn = sqlite3.connect(_kg.db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, name, type, created_at FROM entities ORDER BY name LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    return {"entities": [dict(r) for r in rows]}


# ── Trust ─────────────────────────────────────────────────────────────────────

@app.get("/api/trust/stats")
def get_trust_stats():
    return _trust.stats()


@app.get("/api/trust/contested")
def get_contested():
    return {"contested": _trust.get_contested(limit=30)}


@app.post("/api/trust/{drawer_id}/verify")
def verify_drawer(drawer_id: str):
    rec = _trust.get(drawer_id)
    if not rec:
        raise HTTPException(404, f"No trust record for {drawer_id}")
    return _trust.verify(drawer_id)


@app.post("/api/trust/{drawer_id}/challenge")
def challenge_drawer(drawer_id: str, reason: str = ""):
    rec = _trust.get(drawer_id)
    if not rec:
        raise HTTPException(404, f"No trust record for {drawer_id}")
    result = _trust.challenge(drawer_id)
    if reason:
        _trust.update_status(drawer_id, "contested", reason=reason, changed_by="studio")
    return result


# ── Agents ────────────────────────────────────────────────────────────────────

@app.get("/api/agents")
def get_agents():
    heartbeat_dir = Path(os.path.expanduser("~/.mnemion/heartbeats"))
    beats = []
    if heartbeat_dir.exists():
        for f in sorted(heartbeat_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                beats.append(json.loads(f.read_text()))
            except Exception:
                pass

    # Pull last-seen times from sessions wing metadatas
    col = _get_collection()
    last_seen: dict = {}
    call_counts: dict = {}
    try:
        for m in _iter_metadatas(col, where={"wing": "sessions"}):
            by = m.get("added_by") or "unknown"
            ts = m.get("filed_at") or m.get("timestamp") or ""
            call_counts[by] = call_counts.get(by, 0) + 1
            if ts > last_seen.get(by, ""):
                last_seen[by] = ts
    except Exception:
        pass

    activity = [
        {"agent": k, "last_seen": v, "session_entries": call_counts.get(k, 0)}
        for k, v in sorted(last_seen.items(), key=lambda x: x[1], reverse=True)
    ]
    return {"heartbeats": beats, "activity": activity}


# ── Config ────────────────────────────────────────────────────────────────────

@app.get("/api/config")
def get_config():
    return {
        "anaktoron_path": _config.anaktoron_path,
        "collection_name": _config.collection_name,
        "llm": _config.llm,
        "topic_wings": _config.topic_wings,
    }


@app.put("/api/config/llm")
def update_llm_config(body: LLMConfig):
    _config.save_llm_config(
        backend=body.backend,
        url=body.url,
        model=body.model,
        api_key=body.api_key,
    )
    return {"success": True, "llm": _config.llm}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trust_summary(rec):
    if not rec:
        return None
    return {
        "status": rec.get("status", "unknown"),
        "confidence": rec.get("confidence", 1.0),
        "verifications": rec.get("verifications", 0),
        "challenges": rec.get("challenges", 0),
    }


def _trust_history(drawer_id: str):
    try:
        conn = sqlite3.connect(_kg.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT status, changed_by, reason, changed_at FROM drawer_trust_history WHERE drawer_id = ? ORDER BY changed_at DESC LIMIT 20",
            (drawer_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ── Agent connectors ──────────────────────────────────────────────────────────

@app.get("/api/connectors")
def list_connectors():
    """Detect installed MCP-capable AI clients and whether Mnemion is wired in."""
    return {
        "connectors": _connectors.detect_all(),
        "python_cmd": _connectors.PYTHON_CMD,
        "python_args": _connectors.PYTHON_ARGS,
    }


@app.get("/api/connectors/{conn_id}")
def get_connector(conn_id: str):
    c = _connectors.get(conn_id)
    if not c:
        raise HTTPException(404, f"Unknown connector: {conn_id}")
    return {**_connectors.detect(c), "snippet": _connectors.snippet(c)}


@app.post("/api/connectors/{conn_id}/install")
def install_connector(conn_id: str):
    c = _connectors.get(conn_id)
    if not c:
        raise HTTPException(404, f"Unknown connector: {conn_id}")
    result = _connectors.install(c)
    if not result.get("success"):
        raise HTTPException(500, result.get("error", "install failed"))
    return result


@app.post("/api/connectors/{conn_id}/uninstall")
def uninstall_connector(conn_id: str):
    c = _connectors.get(conn_id)
    if not c:
        raise HTTPException(404, f"Unknown connector: {conn_id}")
    result = _connectors.uninstall(c)
    if not result.get("success"):
        raise HTTPException(500, result.get("error", "uninstall failed"))
    return result


# ── Vault export (Obsidian-compatible) ───────────────────────────────────────

@app.get("/api/export/vault")
def export_vault(wing: Optional[str] = Query(None)):
    """Export drawers as Obsidian-compatible Markdown files in a streamed ZIP archive."""
    import tempfile
    import zipfile
    import re
    import os as _os
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    # Write to a temp file (not BytesIO) so large vaults don't blow up memory.
    # The temp file is unlinked after the response finishes streaming.
    tmp = tempfile.NamedTemporaryFile(
        prefix="mnemion_vault_", suffix=".zip", delete=False
    )
    tmp_path = tmp.name
    tmp.close()

    try:
        col = _get_collection()
        PAGE = 500
        offset = 0
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            while True:
                try:
                    res = col.get(
                        limit=PAGE,
                        offset=offset,
                        where={"wing": wing} if wing else None,
                        include=["metadatas", "documents"],
                    )
                except Exception:
                    break
                if not res or not res.get("ids"):
                    break
                ids = res["ids"]
                metas = res.get("metadatas") or [{}] * len(ids)
                docs = res.get("documents") or [""] * len(ids)
                for did, meta, doc in zip(ids, metas, docs):
                    meta = meta or {}
                    w = meta.get("wing", "unknown")
                    r = meta.get("room", "misc")
                    fm_lines = ["---"]
                    fm_lines.append(f'id: "{did}"')
                    fm_lines.append(f'wing: "{w}"')
                    fm_lines.append(f'room: "{r}"')
                    for k in ("agent", "session_id", "trust_status", "created_at", "filed_at"):
                        if meta.get(k):
                            fm_lines.append(f'{k}: "{meta[k]}"')
                    if meta.get("confidence") is not None:
                        fm_lines.append(f'confidence: {meta["confidence"]}')
                    fm_lines.append("---")
                    fm_lines.append("")
                    fm_lines.append(doc or "")
                    content = "\n".join(fm_lines)
                    safe_id = re.sub(r'[^\w\-]', '_', did[:32])
                    path = f"{w}/{r}/{safe_id}.md"
                    zf.writestr(path, content)
                if len(ids) < PAGE:
                    break
                offset += PAGE

        fname = f"mnemion_vault{'_' + wing if wing else ''}.zip"

        def _cleanup(path: str):
            try:
                _os.unlink(path)
            except OSError:
                pass

        return FileResponse(
            tmp_path,
            media_type="application/zip",
            filename=fname,
            background=BackgroundTask(_cleanup, tmp_path),
        )
    except Exception as exc:
        try:
            _os.unlink(tmp_path)
        except OSError:
            pass
        raise HTTPException(500, str(exc))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("studio.backend.main:app", host="127.0.0.1", port=7891, reload=True)
