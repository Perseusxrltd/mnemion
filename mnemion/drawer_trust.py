#!/usr/bin/env python3
"""
drawer_trust.py — Memory Trust Layer for Mnemion
====================================================

Every drawer (memory) has a lifecycle:
    current → superseded | contested → historical

Trust records live in a sidecar SQLite DB (same file as knowledge_graph.sqlite3).
Pre-computation at save time keeps fetch paths fast.

Tables:
  drawer_trust         — one row per drawer, bitemporal status + confidence
  drawer_conflicts     — pairwise conflict records, resolved or pending
  drawer_trust_history — append-only audit trail of every state change
"""

import sqlite3
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger("mnemion.trust")

# ── Status constants ──────────────────────────────────────────────────────────
STATUS_CURRENT = "current"
STATUS_SUPERSEDED = "superseded"
STATUS_CONTESTED = "contested"
STATUS_HISTORICAL = "historical"  # soft-deleted: never hard-removed

CONFLICT_DIRECT = "direct_contradiction"
CONFLICT_TEMPORAL = "temporal_update"
CONFLICT_PARTIAL = "partial_overlap"

SCHEMA = """
-- Primary trust record per drawer
CREATE TABLE IF NOT EXISTS drawer_trust (
    drawer_id       TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'current',       -- current|superseded|contested|historical
    confidence      REAL NOT NULL DEFAULT 1.0,            -- 0.0–1.0
    valid_from      TEXT,                                  -- ISO date when fact became true
    valid_to        TEXT,                                  -- ISO date when fact stopped being true (NULL = still valid)
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    superseded_by   TEXT,                                  -- drawer_id that replaces this one
    verifications   INTEGER NOT NULL DEFAULT 0,           -- times AI has confirmed this fact
    challenges      INTEGER NOT NULL DEFAULT 0,           -- times AI has challenged this fact
    wing            TEXT,
    room            TEXT,
    FOREIGN KEY(superseded_by) REFERENCES drawer_trust(drawer_id)
);

-- Pairwise conflict records
CREATE TABLE IF NOT EXISTS drawer_conflicts (
    conflict_id     TEXT PRIMARY KEY,
    drawer_id_a     TEXT NOT NULL,
    drawer_id_b     TEXT NOT NULL,
    conflict_type   TEXT NOT NULL,                        -- direct_contradiction|temporal_update|partial_overlap
    confidence      REAL NOT NULL DEFAULT 0.0,           -- LLM confidence the conflict is real
    resolved        INTEGER NOT NULL DEFAULT 0,          -- 0=pending, 1=resolved
    resolved_by     TEXT,                                -- drawer_id that resolved it, or 'manual'
    resolution_note TEXT,
    created_at      TEXT NOT NULL,
    resolved_at     TEXT,
    FOREIGN KEY(drawer_id_a) REFERENCES drawer_trust(drawer_id),
    FOREIGN KEY(drawer_id_b) REFERENCES drawer_trust(drawer_id)
);

-- Append-only audit trail
CREATE TABLE IF NOT EXISTS drawer_trust_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    drawer_id       TEXT NOT NULL,
    old_status      TEXT,
    new_status      TEXT NOT NULL,
    old_confidence  REAL,
    new_confidence  REAL,
    reason          TEXT,
    changed_by      TEXT NOT NULL DEFAULT 'system',      -- 'system'|'mcp'|'llm'|'user'
    changed_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trust_status    ON drawer_trust(status);
CREATE INDEX IF NOT EXISTS idx_trust_wing_room ON drawer_trust(wing, room);
CREATE INDEX IF NOT EXISTS idx_conflicts_a     ON drawer_conflicts(drawer_id_a);
CREATE INDEX IF NOT EXISTS idx_conflicts_b     ON drawer_conflicts(drawer_id_b);
CREATE INDEX IF NOT EXISTS idx_conflicts_res   ON drawer_conflicts(resolved);
CREATE INDEX IF NOT EXISTS idx_history_drawer  ON drawer_trust_history(drawer_id);
"""


class DrawerTrust:
    """
    Manages trust lifecycle for drawers.
    Same SQLite file as the knowledge_graph to keep I/O simple.
    """

    def __init__(self, db_path: Optional[str] = None):
        from .config import MempalaceConfig

        cfg = MempalaceConfig()
        anaktoron_parent = Path(cfg.palace_path).parent
        self.db_path = db_path or str(anaktoron_parent / "knowledge_graph.sqlite3")
        self._init_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self):
        conn = self._connect()
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── Core CRUD ─────────────────────────────────────────────────────────────

    def create(
        self,
        drawer_id: str,
        wing: str,
        room: str,
        confidence: float = 1.0,
        valid_from: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a trust record for a new drawer. Called at add_drawer time."""
        now = self._now()
        conn = self._connect()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO drawer_trust
                   (drawer_id, status, confidence, valid_from, created_at, updated_at, wing, room)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (drawer_id, STATUS_CURRENT, confidence, valid_from, now, now, wing, room),
            )
            self._log_history(
                conn, drawer_id, None, STATUS_CURRENT, None, confidence, "created", "system"
            )
            conn.commit()
            return {"drawer_id": drawer_id, "status": STATUS_CURRENT, "confidence": confidence}
        finally:
            conn.close()

    def get(self, drawer_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM drawer_trust WHERE drawer_id = ?", (drawer_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_status(
        self,
        drawer_id: str,
        new_status: str,
        confidence: Optional[float] = None,
        superseded_by: Optional[str] = None,
        valid_to: Optional[str] = None,
        reason: str = "",
        changed_by: str = "system",
    ) -> Dict[str, Any]:
        """Transition a drawer's status. Always logs to history."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT status, confidence FROM drawer_trust WHERE drawer_id = ?", (drawer_id,)
            ).fetchone()
            if not row:
                return {"error": f"drawer_id not found: {drawer_id}"}

            old_status = row["status"]
            old_confidence = row["confidence"]
            new_conf = confidence if confidence is not None else old_confidence
            now = self._now()

            conn.execute(
                """UPDATE drawer_trust
                   SET status=?, confidence=?, superseded_by=COALESCE(?, superseded_by),
                       valid_to=COALESCE(?, valid_to), updated_at=?
                   WHERE drawer_id=?""",
                (new_status, new_conf, superseded_by, valid_to, now, drawer_id),
            )
            self._log_history(
                conn,
                drawer_id,
                old_status,
                new_status,
                old_confidence,
                new_conf,
                reason,
                changed_by,
            )
            conn.commit()
            return {
                "drawer_id": drawer_id,
                "old_status": old_status,
                "new_status": new_status,
                "confidence": new_conf,
            }
        finally:
            conn.close()

    def verify(self, drawer_id: str) -> Dict[str, Any]:
        """Increment verification count and bump confidence."""
        conn = self._connect()
        try:
            conn.execute(
                """UPDATE drawer_trust
                   SET verifications = verifications + 1,
                       confidence = MIN(1.0, confidence + 0.05),
                       updated_at = ?
                   WHERE drawer_id = ?""",
                (self._now(), drawer_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT verifications, confidence FROM drawer_trust WHERE drawer_id = ?",
                (drawer_id,),
            ).fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def challenge(self, drawer_id: str) -> Dict[str, Any]:
        """Increment challenge count and lower confidence."""
        conn = self._connect()
        try:
            conn.execute(
                """UPDATE drawer_trust
                   SET challenges = challenges + 1,
                       confidence = MAX(0.1, confidence - 0.1),
                       updated_at = ?
                   WHERE drawer_id = ?""",
                (self._now(), drawer_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT challenges, confidence FROM drawer_trust WHERE drawer_id = ?",
                (drawer_id,),
            ).fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    # ── Conflict management ───────────────────────────────────────────────────

    def record_conflict(
        self,
        drawer_id_a: str,
        drawer_id_b: str,
        conflict_type: str,
        confidence: float,
    ) -> str:
        """Record a detected conflict between two drawers. Returns conflict_id."""
        raw = f"{drawer_id_a}:{drawer_id_b}:{conflict_type}"
        conflict_id = "cf_" + hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest()[:16]
        conn = self._connect()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO drawer_conflicts
                   (conflict_id, drawer_id_a, drawer_id_b, conflict_type, confidence, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (conflict_id, drawer_id_a, drawer_id_b, conflict_type, confidence, self._now()),
            )
            conn.commit()
            return conflict_id
        finally:
            conn.close()

    def resolve_conflict(
        self,
        conflict_id: str,
        resolved_by: str,
        resolution_note: str = "",
    ) -> Dict[str, Any]:
        now = self._now()
        conn = self._connect()
        try:
            conn.execute(
                """UPDATE drawer_conflicts
                   SET resolved=1, resolved_by=?, resolution_note=?, resolved_at=?
                   WHERE conflict_id=?""",
                (resolved_by, resolution_note, now, conflict_id),
            )
            conn.commit()
            return {"conflict_id": conflict_id, "resolved_at": now, "resolved_by": resolved_by}
        finally:
            conn.close()

    def get_pending_conflicts(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM drawer_conflicts
                   WHERE resolved = 0
                   ORDER BY confidence DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Batch / query helpers ─────────────────────────────────────────────────

    def get_contested(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return contested drawers for review."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM drawer_trust
                   WHERE status = 'contested'
                   ORDER BY confidence ASC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def bulk_create_default(self, drawer_ids: List[tuple]) -> int:
        """
        Backfill trust records for existing drawers.
        drawer_ids: list of (drawer_id, wing, room) tuples
        Returns count of rows inserted.
        """
        now = self._now()
        inserted = 0
        conn = self._connect()
        try:
            for drawer_id, wing, room in drawer_ids:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO drawer_trust
                       (drawer_id, status, confidence, created_at, updated_at, wing, room)
                       VALUES (?, 'current', 1.0, ?, ?, ?, ?)""",
                    (drawer_id, now, now, wing, room),
                )
                inserted += cur.rowcount
            conn.commit()
            return inserted
        finally:
            conn.close()

    def stats(self) -> Dict[str, Any]:
        conn = self._connect()
        try:
            counts = dict(
                conn.execute("SELECT status, COUNT(*) FROM drawer_trust GROUP BY status").fetchall()
            )
            conflicts = conn.execute(
                "SELECT resolved, COUNT(*) FROM drawer_conflicts GROUP BY resolved"
            ).fetchall()
            conflict_counts = {
                f"conflicts_{'resolved' if r else 'pending'}": c for r, c in conflicts
            }
            avg_conf = conn.execute(
                "SELECT AVG(confidence) FROM drawer_trust WHERE status='current'"
            ).fetchone()[0]
            return {
                "trust_counts": counts,
                "avg_confidence_current": round(avg_conf or 0, 3),
                **conflict_counts,
            }
        finally:
            conn.close()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _log_history(
        self,
        conn: sqlite3.Connection,
        drawer_id: str,
        old_status: Optional[str],
        new_status: str,
        old_confidence: Optional[float],
        new_confidence: float,
        reason: str,
        changed_by: str,
    ):
        conn.execute(
            """INSERT INTO drawer_trust_history
               (drawer_id, old_status, new_status, old_confidence, new_confidence, reason, changed_by, changed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                drawer_id,
                old_status,
                new_status,
                old_confidence,
                new_confidence,
                reason,
                changed_by,
                self._now(),
            ),
        )
