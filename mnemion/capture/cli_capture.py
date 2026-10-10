"""Minimal capture pipeline that writes normal Mnemion drawers."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..backends.registry import get_backend
from ..config import MnemionConfig
from ..trust_lifecycle import DrawerTrust


def _drawer_id(wing: str, room: str, content: str) -> str:
    digest = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()[:16]
    safe_wing = wing.replace("/", "_").replace("\\", "_")
    safe_room = room.replace("/", "_").replace("\\", "_")
    return f"drawer_{safe_wing}_{safe_room}_{digest}"


def capture_text(
    content: str,
    tags: list[str] | None = None,
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
    wing: str | None = None,
    room: str | None = None,
    privacy_class: str | None = None,
    added_by: str = "capture",
    anaktoron_path: str | None = None,
) -> dict[str, Any]:
    text = content.strip()
    if not text:
        return {"status": "failed", "message": "content is empty"}
    tags = tags or []
    cfg = MnemionConfig()
    target = anaktoron_path or cfg.anaktoron_path
    wing = wing or "thoughts"
    room = room or (tags[0] if tags else "general")
    drawer_id = _drawer_id(wing, room, text)
    collection = get_backend(anaktoron_path=target).get_collection(cfg.collection_name, create=True)
    existing = collection.get(ids=[drawer_id])
    duplicate = bool(existing.get("ids"))

    filed_at = datetime.now(timezone.utc).isoformat()
    meta = {
        "wing": wing,
        "room": room,
        "source_file": source or "",
        "chunk_index": 0,
        "added_by": added_by,
        "filed_at": filed_at,
        "tags": ",".join(tags),
        "privacy_class": privacy_class or "private",
    }
    if metadata:
        meta["metadata_json"] = str(metadata)
    from ..ingestion import LegacyMemoryWriter

    kg_path = str(Path(target).expanduser().parent / "knowledge_graph.sqlite3")
    if duplicate:
        meta = existing["metadatas"][0] or meta
    LegacyMemoryWriter(collection, kg_path).save(drawer_id, text, meta)
    trust = DrawerTrust(kg_path).get(drawer_id)
    return {
        "id": drawer_id,
        "status": "duplicate" if duplicate else "created",
        "message": "Thought already exists" if duplicate else "Captured thought",
        "wing": wing,
        "room": room,
        "trust_status": trust["status"],
    }
