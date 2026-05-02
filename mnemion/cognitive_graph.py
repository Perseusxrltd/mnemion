"""Structured cognitive memory graph over raw Anaktoron drawers."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class CognitiveUnit:
    unit_id: str
    drawer_id: str
    unit_type: str
    text: str
    cues: tuple[str, ...]
    source_file: str = ""
    timestamp: str = ""
    trust_status: str = "current"


@dataclass(frozen=True)
class CognitiveEdge:
    edge_id: str
    drawer_id: str
    edge_type: str
    source_text: str
    target_text: str


_TOKEN_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b")
_STOP = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "was",
    "were",
    "are",
    "uses",
    "use",
    "all",
    "always",
    "never",
    "must",
    "should",
    "why",
    "did",
    "what",
    "when",
    "where",
    "how",
    "old",
    "current",
    "fact",
}
_HIDDEN_TRUST_STATUSES = {"superseded", "historical", "quarantined"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS cognitive_units (
    unit_id      TEXT PRIMARY KEY,
    drawer_id    TEXT NOT NULL,
    unit_type    TEXT NOT NULL,
    text         TEXT NOT NULL,
    cues         TEXT NOT NULL,
    source_file  TEXT,
    timestamp    TEXT,
    trust_status TEXT NOT NULL DEFAULT 'current',
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cognitive_edges (
    edge_id     TEXT PRIMARY KEY,
    drawer_id   TEXT NOT NULL,
    edge_type   TEXT NOT NULL,
    source_text TEXT NOT NULL,
    target_text TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cognitive_consolidated_drawers (
    drawer_id       TEXT PRIMARY KEY,
    consolidated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cognitive_units_drawer ON cognitive_units(drawer_id);
CREATE INDEX IF NOT EXISTS idx_cognitive_units_type ON cognitive_units(unit_type);
CREATE INDEX IF NOT EXISTS idx_cognitive_units_trust ON cognitive_units(trust_status);
"""


def _cues(text: str) -> tuple[str, ...]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    seen = []
    for token in tokens:
        if token in _STOP or token in seen:
            continue
        seen.append(token)
    return tuple(seen[:12])


def _unit_id(drawer_id: str, unit_type: str, text: str) -> str:
    digest = hashlib.sha1(f"{drawer_id}:{unit_type}:{text}".encode()).hexdigest()[:16]
    return f"cog_{digest}"


def _edge_id(drawer_id: str, edge_type: str, source: str, target: str) -> str:
    digest = hashlib.sha1(f"{drawer_id}:{edge_type}:{source}:{target}".encode()).hexdigest()[:16]
    return f"edge_{digest}"


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def extract_cognitive_units(
    drawer_id: str,
    text: str,
    metadata: dict[str, Any] | None = None,
    trust_status: str = "current",
) -> tuple[list[CognitiveUnit], list[CognitiveEdge]]:
    """Extract lightweight proposition/prescription/event units and causal edges."""
    metadata = metadata or {}
    source_file = str(metadata.get("source_file", ""))
    timestamp = str(metadata.get("timestamp") or metadata.get("filed_at") or "")
    units: list[CognitiveUnit] = []
    edges: list[CognitiveEdge] = []

    for sentence in _sentences(text):
        lower = sentence.lower()
        unit_type = "proposition"
        if " because " in lower or " caused " in lower:
            unit_type = "cause"
            if " because " in lower:
                source, target = re.split(r"\bbecause\b", sentence, maxsplit=1, flags=re.I)
            else:
                source, target = re.split(r"\bcaused\b", sentence, maxsplit=1, flags=re.I)
            edges.append(
                CognitiveEdge(
                    edge_id=_edge_id(drawer_id, "cause", source.strip(), target.strip()),
                    drawer_id=drawer_id,
                    edge_type="cause",
                    source_text=source.strip(),
                    target_text=target.strip().rstrip("."),
                )
            )
        elif re.match(r"^(always|never|must|should|do not|don't)\b", lower):
            unit_type = "prescription"
        elif " prefers " in lower or " preference" in lower:
            unit_type = "preference"
        elif lower.startswith("goal:") or lower.startswith("objective:") or " goal " in lower:
            unit_type = "objective"
        elif re.search(r"\b(moved|switched|decided|started|ended|launched)\b", lower):
            unit_type = "event"

        units.append(
            CognitiveUnit(
                unit_id=_unit_id(drawer_id, unit_type, sentence),
                drawer_id=drawer_id,
                unit_type=unit_type,
                text=sentence,
                cues=_cues(sentence),
                source_file=source_file,
                timestamp=timestamp,
                trust_status=trust_status,
            )
        )

    return units, edges


class CognitiveGraph:
    """SQLite-backed structured memory layer linked to raw drawer IDs."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def upsert_drawer_units(
        self,
        drawer_id: str,
        units: list[CognitiveUnit],
        edges: list[CognitiveEdge],
    ) -> dict[str, int]:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            before_units = conn.total_changes
            conn.executemany(
                """INSERT OR IGNORE INTO cognitive_units
                   (unit_id, drawer_id, unit_type, text, cues, source_file, timestamp, trust_status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        unit.unit_id,
                        drawer_id,
                        unit.unit_type,
                        unit.text,
                        " ".join(unit.cues),
                        unit.source_file,
                        unit.timestamp,
                        unit.trust_status,
                        now,
                    )
                    for unit in units
                ],
            )
            units_inserted = conn.total_changes - before_units
            before_edges = conn.total_changes
            conn.executemany(
                """INSERT OR IGNORE INTO cognitive_edges
                   (edge_id, drawer_id, edge_type, source_text, target_text, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (
                        edge.edge_id,
                        drawer_id,
                        edge.edge_type,
                        edge.source_text,
                        edge.target_text,
                        now,
                    )
                    for edge in edges
                ],
            )
            edges_inserted = conn.total_changes - before_edges
            conn.commit()
        return {"units_inserted": units_inserted, "edges_inserted": edges_inserted}

    def _is_consolidated(self, conn: sqlite3.Connection, drawer_id: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM cognitive_consolidated_drawers WHERE drawer_id = ?",
            (drawer_id,),
        ).fetchone()
        return row is not None

    def _mark_consolidated(self, conn: sqlite3.Connection, drawer_id: str) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO cognitive_consolidated_drawers VALUES (?, ?)",
            (drawer_id, datetime.now(timezone.utc).isoformat()),
        )

    def consolidate_collection(
        self,
        collection,
        trust=None,
        limit: int = 100,
        dry_run: bool = False,
    ) -> dict[str, int]:
        result = {"drawers_consolidated": 0, "units_inserted": 0, "edges_inserted": 0}
        if limit <= 0:
            return {"would_consolidate": 0, **result} if dry_run else result

        pending = []
        count_fn = getattr(collection, "count", None)
        total = count_fn() if callable(count_fn) else None
        offset = 0
        batch_size = min(max(limit, 100), 5000)

        with self._connect() as conn:
            while len(pending) < limit and (total is None or offset < total):
                page_limit = batch_size if total is None else min(batch_size, total - offset)
                docs = collection.get(
                    limit=page_limit,
                    offset=offset,
                    include=["documents", "metadatas"],
                )
                ids = docs.get("ids") or []
                documents = docs.get("documents") or []
                metadatas = docs.get("metadatas") or []
                if not ids:
                    break
                for drawer_id, doc, meta in zip(ids, documents, metadatas):
                    if not self._is_consolidated(conn, drawer_id):
                        pending.append((drawer_id, doc, meta or {}))
                        if len(pending) >= limit:
                            break
                offset += len(ids)
                if total is None and len(ids) < page_limit:
                    break

        if dry_run:
            return {"would_consolidate": len(pending), **result}

        for drawer_id, doc, meta in pending:
            trust_record = trust.get(drawer_id) if trust else None
            trust_status = (trust_record or {}).get("status", "current")
            units, edges = extract_cognitive_units(drawer_id, doc, meta, trust_status)
            inserted = self.upsert_drawer_units(drawer_id, units, edges)
            result["drawers_consolidated"] += 1
            result["units_inserted"] += inserted["units_inserted"]
            result["edges_inserted"] += inserted["edges_inserted"]
            with self._connect() as conn:
                self._mark_consolidated(conn, drawer_id)
                conn.commit()
        return result

    def units_for_drawer(self, drawer_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM cognitive_units WHERE drawer_id = ? ORDER BY unit_id",
                (drawer_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def edges_for_drawer(self, drawer_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM cognitive_edges WHERE drawer_id = ? ORDER BY edge_id",
                (drawer_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def search_units(
        self,
        query: str,
        budget: int = 10,
        include_hidden: bool = False,
    ) -> list[dict[str, Any]]:
        query_cues = set(_cues(query))
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM cognitive_units").fetchall()
        scored = []
        for row in rows:
            unit = dict(row)
            if not include_hidden and unit["trust_status"] in _HIDDEN_TRUST_STATUSES:
                continue
            cues = set((unit.get("cues") or "").split())
            matched = sorted(query_cues & cues)
            if not matched:
                continue
            unit["score"] = len(matched)
            unit["matched_cues"] = matched
            scored.append(unit)
        scored.sort(key=lambda item: (-item["score"], item["unit_type"], item["drawer_id"]))
        return scored[: max(1, budget)]

    def topic_tunnels(
        self,
        min_count: int = 2,
        include_hidden: bool = False,
    ) -> list[dict[str, Any]]:
        """Return recurring cue paths that connect multiple current drawers."""
        min_count = max(2, int(min_count))
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM cognitive_units").fetchall()

        by_cue: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for row in rows:
            unit = dict(row)
            if not include_hidden and unit["trust_status"] in _HIDDEN_TRUST_STATUSES:
                continue
            for cue in sorted(set((unit.get("cues") or "").split())):
                by_cue.setdefault(cue, {}).setdefault(unit["drawer_id"], []).append(unit)

        tunnels: list[dict[str, Any]] = []
        for cue, drawer_units in by_cue.items():
            if len(drawer_units) < min_count:
                continue
            units = [
                {
                    "unit_id": unit["unit_id"],
                    "drawer_id": unit["drawer_id"],
                    "unit_type": unit["unit_type"],
                    "text": unit["text"],
                    "trust_status": unit["trust_status"],
                }
                for drawer_id in sorted(drawer_units)
                for unit in sorted(drawer_units[drawer_id], key=lambda item: item["unit_id"])
            ]
            tunnels.append(
                {
                    "cue": cue,
                    "drawer_count": len(drawer_units),
                    "unit_count": len(units),
                    "drawer_ids": sorted(drawer_units),
                    "units": units,
                }
            )

        tunnels.sort(key=lambda item: (-item["drawer_count"], -item["unit_count"], item["cue"]))
        return tunnels

    def tunnels_for_query(
        self,
        query: str,
        min_count: int = 2,
        include_hidden: bool = False,
    ) -> list[dict[str, Any]]:
        """Return topic tunnels whose cue appears in the query intent."""
        query_cues = set(_cues(query))
        return [
            tunnel
            for tunnel in self.topic_tunnels(min_count=min_count, include_hidden=include_hidden)
            if tunnel["cue"] in query_cues
        ]
