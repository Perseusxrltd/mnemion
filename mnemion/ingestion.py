"""Recoverable writes for legacy local stores.

The SQLite journal is committed before touching Chroma. A successful call means
the vector record, lexical row and trust record have all been persisted. Pending
work can be replayed after an interruption. The v4 service uses its own canonical
PostgreSQL transaction; this adapter protects existing installations and imports.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .knowledge_graph import KnowledgeGraph
from .legacy_freeze import require_writable
from .trust_lifecycle import DrawerTrust


SCHEMA = """
CREATE TABLE IF NOT EXISTS drawer_ingest_jobs (
    write_id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id TEXT NOT NULL,
    drawer_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'ready')),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_drawer_ingest_pending
    ON drawer_ingest_jobs(collection_id, state, write_id);
CREATE TABLE IF NOT EXISTS drawer_deletions (
    collection_id TEXT NOT NULL,
    drawer_id TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (collection_id, drawer_id)
);
"""


class LegacyMemoryWriter:
    def __init__(self, collection, db_path: str | Path):
        self.collection = collection
        self.db_path = str(db_path)
        identifier = getattr(collection, "id", None) or getattr(
            collection, "name", "mnemion_drawers"
        )
        self.collection_id = str(identifier)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        KnowledgeGraph(self.db_path)
        DrawerTrust(self.db_path)
        with closing(self._connect()) as conn, conn:
            conn.executescript(SCHEMA)

    def _connect(self):
        require_writable(Path(self.db_path).parent)
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def save(self, drawer_id: str, content: str, metadata: dict[str, Any], embedding=None) -> dict:
        if not drawer_id or not content.strip():
            raise ValueError("Memory ID and content are required")
        payload = {"content": content, "metadata": metadata}
        if embedding is not None:
            payload["embedding"] = embedding.tolist() if hasattr(embedding, "tolist") else embedding
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute(
                "SELECT 1 FROM drawer_deletions WHERE collection_id=? AND drawer_id=?",
                (self.collection_id, drawer_id),
            ).fetchone():
                raise ValueError("This memory ID was deleted and cannot be replayed")
            cursor = conn.execute(
                "INSERT INTO drawer_ingest_jobs (collection_id, drawer_id, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (self.collection_id, drawer_id, json.dumps(payload, ensure_ascii=False), now),
            )
            write_id = cursor.lastrowid
        applied = self.recover(through=write_id)
        return {"write_id": write_id, "state": "ready", "applied_jobs": applied}

    def delete(self, drawer_id: str) -> dict:
        """Durably deny replay, cancel pending saves, then remove projections."""
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT OR IGNORE INTO drawer_deletions(collection_id, drawer_id, requested_at) VALUES (?, ?, ?)",
                (self.collection_id, drawer_id, now),
            )
            conn.execute(
                """UPDATE drawer_ingest_jobs SET state='ready', payload_json='{}',
                   completed_at=?, error='cancelled_by_deletion'
                   WHERE collection_id=? AND drawer_id=? AND state='pending'""",
                (now, self.collection_id, drawer_id),
            )
            cursor = conn.execute(
                "INSERT INTO drawer_ingest_jobs(collection_id, drawer_id, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (self.collection_id, drawer_id, '{"operation":"delete"}', now),
            )
            write_id = cursor.lastrowid
        applied = self.recover(through=write_id)
        return {
            "drawer_id": drawer_id,
            "state": "ready",
            "write_id": write_id,
            "applied_jobs": applied,
        }

    def import_records(self, records) -> dict:
        """Journal a fully validated legacy export before applying any vectors.

        Flat drawer exports have no reliable lifecycle record. New identities
        enter review; existing trust and permanent deletion denials prevail.
        """
        now = datetime.now(timezone.utc).isoformat()
        accepted = skipped = 0
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            for row in records:
                if conn.execute(
                    "SELECT 1 FROM drawer_deletions WHERE collection_id=? AND drawer_id=?",
                    (self.collection_id, row["id"]),
                ).fetchone():
                    skipped += 1
                    continue
                payload = {
                    "content": row["content"],
                    "metadata": {"wing": "unknown", "room": "notes", **row["metadata"]},
                    "quarantine_new": True,
                }
                conn.execute(
                    "INSERT INTO drawer_ingest_jobs(collection_id,drawer_id,payload_json,created_at) VALUES(?,?,?,?)",
                    (
                        self.collection_id,
                        row["id"],
                        json.dumps(payload, ensure_ascii=False, allow_nan=False),
                        now,
                    ),
                )
                accepted += 1
        applied = self.recover()
        return {
            "state": "ready",
            "imported_records": accepted,
            "skipped_deleted": skipped,
            "applied_jobs": applied,
        }

    def is_deleted(self, drawer_id: str) -> bool:
        with closing(self._connect()) as conn:
            return bool(
                conn.execute(
                    "SELECT 1 FROM drawer_deletions WHERE collection_id=? AND drawer_id=?",
                    (self.collection_id, drawer_id),
                ).fetchone()
            )

    def _delete_indexes(self, conn, drawer_id, now):
        conn.execute("DELETE FROM drawers_fts WHERE drawer_id=?", (drawer_id,))
        for table in (
            "cognitive_units",
            "cognitive_edges",
            "cognitive_consolidated_drawers",
            "memory_guard_findings",
        ):
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone():
                conn.execute(f"DELETE FROM {table} WHERE drawer_id=?", (drawer_id,))
        conn.execute("DELETE FROM triples WHERE source_closet=?", (drawer_id,))
        changed = conn.execute(
            "UPDATE drawer_trust SET status='historical', confidence=0, updated_at=? WHERE drawer_id=? AND status<>'historical'",
            (now, drawer_id),
        ).rowcount
        if changed:
            conn.execute(
                """INSERT INTO drawer_trust_history(drawer_id, new_status, new_confidence, reason, changed_by, changed_at)
                   VALUES (?, 'historical', 0, 'drawer deleted', 'ingestion', ?)""",
                (drawer_id, now),
            )
        conn.execute(
            "UPDATE drawer_deletions SET completed_at=? WHERE collection_id=? AND drawer_id=?",
            (now, self.collection_id, drawer_id),
        )

    def reconcile(self, batch_size: int = 200) -> dict:
        """Repair sidecars for older writer paths; never revive a deletion."""
        self.recover()
        offset, repaired = 0, 0
        while True:
            result = self.collection.get(
                limit=batch_size, offset=offset, include=["documents", "metadatas"]
            )
            ids = result.get("ids") or []
            if not ids:
                break
            with closing(self._connect()) as conn, conn:
                conn.execute("BEGIN IMMEDIATE")
                for drawer_id, content, metadata in zip(
                    ids, result["documents"], result["metadatas"]
                ):
                    if conn.execute(
                        "SELECT 1 FROM drawer_deletions WHERE collection_id=? AND drawer_id=?",
                        (self.collection_id, drawer_id),
                    ).fetchone():
                        continue
                    self._write_indexes(
                        conn,
                        drawer_id,
                        content or "",
                        metadata or {},
                        datetime.now(timezone.utc).isoformat(),
                    )
                    repaired += 1
            offset += len(ids)
        return {"state": "ready", "reconciled_records": repaired}

    def _write_indexes(self, conn, drawer_id, content, metadata, now, quarantine_new=False):
        previous = conn.execute(
            "SELECT content FROM drawers_fts WHERE drawer_id = ? LIMIT 1", (drawer_id,)
        ).fetchone()
        conn.execute("DELETE FROM drawers_fts WHERE drawer_id = ?", (drawer_id,))
        conn.execute(
            "INSERT INTO drawers_fts (drawer_id, content, wing, room) VALUES (?, ?, ?, ?)",
            (drawer_id, content, metadata.get("wing", "unknown"), metadata.get("room", "notes")),
        )
        status, confidence = ("quarantined", 0.5) if quarantine_new else ("current", 1.0)
        created = conn.execute(
            """INSERT OR IGNORE INTO drawer_trust
               (drawer_id, status, confidence, created_at, updated_at, wing, room)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                drawer_id,
                status,
                confidence,
                now,
                now,
                metadata.get("wing", "unknown"),
                metadata.get("room", "notes"),
            ),
        ).rowcount
        if created:
            conn.execute(
                """INSERT INTO drawer_trust_history
                   (drawer_id, new_status, new_confidence, reason, changed_by, changed_at)
                   VALUES (?, ?, ?, ?, 'ingestion', ?)""",
                (
                    drawer_id,
                    status,
                    confidence,
                    "drawer-only import requires review" if quarantine_new else "created",
                    now,
                ),
            )
        if previous and previous["content"] != content:
            # Evidence derived from an older text must be rebuilt before reuse.
            for table in ("cognitive_units", "cognitive_edges", "cognitive_consolidated_drawers"):
                if conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone():
                    conn.execute(f"DELETE FROM {table} WHERE drawer_id = ?", (drawer_id,))
            conn.execute(
                "UPDATE triples SET valid_to = ? WHERE source_closet = ? AND valid_to IS NULL",
                (now, drawer_id),
            )

    def recover(self, through: int | None = None) -> int:
        """Replay pending jobs in order, including writes from a previous process.

        Serialize the local projection transaction across processes. Chroma is a
        separate database, so a crash can require replay; no pending job is lost.
        SQLite WAL readers remain available while a legacy vector write runs.
        """
        applied = 0
        while True:
            conn = self._connect()
            job = None
            try:
                conn.execute("BEGIN IMMEDIATE")
                sql = "SELECT * FROM drawer_ingest_jobs WHERE collection_id=? AND state='pending'"
                params = [self.collection_id]
                if through is not None:
                    sql += " AND write_id <= ?"
                    params.append(through)
                job = conn.execute(sql + " ORDER BY write_id LIMIT 1", params).fetchone()
                if job is None:
                    conn.commit()
                    return applied
                payload = json.loads(job["payload_json"])
                now = datetime.now(timezone.utc).isoformat()
                if payload.get("operation") == "delete":
                    self.collection.delete(ids=[job["drawer_id"]])
                    self._delete_indexes(conn, job["drawer_id"], now)
                elif not conn.execute(
                    "SELECT 1 FROM drawer_deletions WHERE collection_id=? AND drawer_id=?",
                    (self.collection_id, job["drawer_id"]),
                ).fetchone():
                    kwargs = {
                        "ids": [job["drawer_id"]],
                        "documents": [payload["content"]],
                        "metadatas": [payload["metadata"]],
                    }
                    if "embedding" in payload:
                        kwargs["embeddings"] = [payload["embedding"]]
                    self.collection.upsert(**kwargs)
                    self._write_indexes(
                        conn,
                        job["drawer_id"],
                        payload["content"],
                        payload["metadata"],
                        now,
                        payload.get("quarantine_new", False),
                    )
                conn.execute(
                    "UPDATE drawer_ingest_jobs SET state='ready', payload_json='{}', completed_at=?, error=NULL WHERE write_id=?",
                    (now, job["write_id"]),
                )
                conn.commit()
                applied += 1
            except Exception as exc:
                conn.rollback()
                if job is not None:
                    # Keep the payload durable; never turn a projection failure
                    # into an acknowledged write merely because its vector exists.
                    try:
                        conn.execute(
                            "UPDATE drawer_ingest_jobs SET error=? WHERE write_id=?",
                            (type(exc).__name__, job["write_id"]),
                        )
                        conn.commit()
                    except sqlite3.Error:
                        conn.rollback()
                raise
            finally:
                conn.close()
