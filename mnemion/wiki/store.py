"""SQLite schema helpers for wiki projection state."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS wiki_pages (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    page_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content_hash TEXT,
    source_hashes_json TEXT NOT NULL DEFAULT '[]',
    drawer_ids_json TEXT NOT NULL DEFAULT '[]',
    claim_ids_json TEXT NOT NULL DEFAULT '[]',
    trust_status TEXT NOT NULL DEFAULT 'current',
    citation_coverage REAL NOT NULL DEFAULT 0,
    stale_claims INTEGER NOT NULL DEFAULT 0,
    contested_claims INTEGER NOT NULL DEFAULT 0,
    generated_by TEXT NOT NULL DEFAULT 'mnemion-wiki-compiler',
    last_compiled TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS wiki_claims (
    id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
    claim_text TEXT NOT NULL,
    source_id TEXT REFERENCES raw_sources(id),
    source_chunk_id TEXT REFERENCES source_chunks(id),
    drawer_id TEXT,
    kg_fact_id TEXT,
    evidence_span_start INTEGER,
    evidence_span_end INTEGER,
    confidence REAL NOT NULL DEFAULT 0.5,
    trust_status TEXT NOT NULL DEFAULT 'current',
    generated_at TEXT NOT NULL,
    last_verified_at TEXT,
    content_hash TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_wiki_claims_page ON wiki_claims(page_id);
CREATE INDEX IF NOT EXISTS idx_wiki_claims_source ON wiki_claims(source_id);
CREATE INDEX IF NOT EXISTS idx_wiki_claims_drawer ON wiki_claims(drawer_id);
CREATE INDEX IF NOT EXISTS idx_wiki_claims_trust ON wiki_claims(trust_status);

CREATE TABLE IF NOT EXISTS wiki_links (
    id TEXT PRIMARY KEY,
    from_page_id TEXT NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
    to_page_id TEXT REFERENCES wiki_pages(id),
    target_path TEXT,
    link_text TEXT NOT NULL,
    link_type TEXT NOT NULL DEFAULT 'wikilink',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wiki_jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    scope_id TEXT,
    status TEXT NOT NULL,
    affected_pages_json TEXT NOT NULL DEFAULT '[]',
    diff_path TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_db_path() -> Path:
    from ..config import MnemionConfig

    return Path(MnemionConfig().anaktoron_path).expanduser().parent / "knowledge_graph.sqlite3"


class WikiStore:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path is not None else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def upsert_page(
        self,
        page_id: str,
        path: str,
        page_type: str,
        title: str,
        content_hash: str,
        source_hashes: list[str],
        drawer_ids: list[str],
        claim_ids: list[str],
        citation_coverage: float,
        stale_claims: int = 0,
        contested_claims: int = 0,
        trust_status: str = "current",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = now_iso()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM wiki_pages WHERE id = ?", (page_id,)
            ).fetchone()
            conn.execute(
                """INSERT OR REPLACE INTO wiki_pages
                   (id, path, page_type, title, content_hash, source_hashes_json,
                    drawer_ids_json, claim_ids_json, trust_status, citation_coverage,
                    stale_claims, contested_claims, generated_by, last_compiled,
                    created_at, updated_at, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    page_id,
                    path,
                    page_type,
                    title,
                    content_hash,
                    json.dumps(source_hashes),
                    json.dumps(drawer_ids),
                    json.dumps(claim_ids),
                    trust_status,
                    citation_coverage,
                    stale_claims,
                    contested_claims,
                    "mnemion-wiki-compiler",
                    now,
                    existing["created_at"] if existing else now,
                    now,
                    json.dumps(metadata or {}, sort_keys=True),
                ),
            )
            conn.commit()

    def replace_claims(self, page_id: str, claims: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM wiki_claims WHERE page_id = ?", (page_id,))
            conn.executemany(
                """INSERT INTO wiki_claims
                   (id, page_id, claim_text, source_id, source_chunk_id, drawer_id, kg_fact_id,
                    evidence_span_start, evidence_span_end, confidence, trust_status,
                    generated_at, last_verified_at, content_hash, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        claim["id"],
                        page_id,
                        claim["claim_text"],
                        claim.get("source_id") or None,
                        claim.get("source_chunk_id") or None,
                        claim.get("drawer_id") or None,
                        claim.get("kg_fact_id") or None,
                        claim.get("evidence_span_start"),
                        claim.get("evidence_span_end"),
                        claim.get("confidence", 0.5),
                        claim.get("trust_status", "current"),
                        claim.get("generated_at") or now_iso(),
                        claim.get("last_verified_at"),
                        claim["content_hash"],
                        json.dumps(claim.get("metadata") or {}, sort_keys=True),
                    )
                    for claim in claims
                ],
            )
            conn.commit()

    def add_job(
        self,
        job_id: str,
        job_type: str,
        scope_type: str,
        scope_id: str | None,
        status: str,
        affected_pages: list[str],
        diff_path: str = "",
        error: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = now_iso()
        with self.connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO wiki_jobs
                   (id, job_type, scope_type, scope_id, status, affected_pages_json,
                    diff_path, error, created_at, started_at, completed_at, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    job_type,
                    scope_type,
                    scope_id or "",
                    status,
                    json.dumps(affected_pages),
                    diff_path,
                    error,
                    now,
                    now,
                    now if status in {"completed", "failed", "review", "applied"} else "",
                    json.dumps(metadata or {}, sort_keys=True),
                ),
            )
            conn.commit()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM wiki_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["affected_pages"] = json.loads(data.pop("affected_pages_json") or "[]")
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data

    def pages(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM wiki_pages ORDER BY path").fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["source_hashes"] = json.loads(data.pop("source_hashes_json") or "[]")
            data["drawer_ids"] = json.loads(data.pop("drawer_ids_json") or "[]")
            data["claim_ids"] = json.loads(data.pop("claim_ids_json") or "[]")
            data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
            result.append(data)
        return result
