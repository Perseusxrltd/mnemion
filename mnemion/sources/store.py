"""SQLite-backed immutable raw source store."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .chunking import chunk_text, sha256_hex
from .extractors import extract_text
from .privacy import normalize_privacy_class

SOURCE_CHROMA_COLLECTION = "mnemion_source_chunks"

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_sources (
    id TEXT PRIMARY KEY,
    uri TEXT,
    file_path TEXT,
    source_type TEXT NOT NULL,
    title TEXT,
    author TEXT,
    captured_at TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    raw_text_path TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    trust_status TEXT NOT NULL DEFAULT 'current',
    privacy_class TEXT NOT NULL DEFAULT 'private',
    extraction_status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_sources_hash ON raw_sources(content_hash);
CREATE INDEX IF NOT EXISTS idx_raw_sources_type ON raw_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_raw_sources_trust ON raw_sources(trust_status);
CREATE INDEX IF NOT EXISTS idx_raw_sources_privacy ON raw_sources(privacy_class);

CREATE TABLE IF NOT EXISTS source_chunks (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES raw_sources(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    start_offset INTEGER,
    end_offset INTEGER,
    token_estimate INTEGER,
    content_hash TEXT NOT NULL,
    embedding_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_chunks_source ON source_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_source_chunks_hash ON source_chunks(content_hash);

CREATE VIRTUAL TABLE IF NOT EXISTS source_chunks_fts USING fts5(
    id UNINDEXED,
    source_id UNINDEXED,
    text,
    tokenize='porter'
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_db_path() -> Path:
    from ..config import MnemionConfig

    return Path(MnemionConfig().anaktoron_path).expanduser().parent / "knowledge_graph.sqlite3"


def _default_source_path() -> Path:
    from ..config import MnemionConfig

    return Path(MnemionConfig().source_path).expanduser()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


class SourceStore:
    """Owns raw source metadata, extracted text, chunks, and source FTS."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        source_path: str | Path | None = None,
        anaktoron_path: str | None = None,
    ):
        self.db_path = Path(db_path) if db_path is not None else _default_db_path()
        self.source_path = Path(source_path) if source_path is not None else _default_source_path()
        self.anaktoron_path = anaktoron_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.source_path.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _source_id(self, content_hash: str) -> str:
        digest = content_hash.split(":", 1)[-1]
        return f"src_{digest[:12]}"

    def _chunk_id(self, source_id: str, chunk_index: int) -> str:
        return f"sch_{source_id.removeprefix('src_')}_{chunk_index:04d}"

    def add_path(
        self,
        path: str | Path,
        source_type: str | None = None,
        title: str | None = None,
        author: str | None = None,
        privacy_class: str | None = None,
        dry_run: bool = False,
        index_embeddings: bool = False,
    ) -> dict[str, Any]:
        source_path = Path(path).expanduser().resolve()
        raw_bytes = source_path.read_bytes()
        content_hash = sha256_hex(raw_bytes)
        existing = self.get_source_by_hash(content_hash)
        if existing:
            if not self.list_chunks(existing["id"], limit=1):
                extracted = extract_text(source_path, source_type=source_type)
                if not dry_run:
                    self._insert_chunks(existing["id"], extracted.text, {}, index_embeddings)
            return {"status": "existing", "source_id": existing["id"], "content_hash": content_hash}

        extracted = extract_text(source_path, source_type=source_type)
        source_id = self._source_id(content_hash)
        detected_type = extracted.source_type
        privacy = normalize_privacy_class(privacy_class)
        now = now_iso()
        display_title = title or source_path.stem
        text_path = self.source_path / "text" / f"{source_id}.txt"
        raw_dir = self.source_path / "raw"
        raw_copy = raw_dir / f"{source_id}{source_path.suffix or '.txt'}"
        metadata = dict(extracted.metadata)
        metadata["untrusted_source_content"] = True

        if dry_run:
            chunks = chunk_text(extracted.text)
            return {
                "status": "dry_run",
                "source_id": source_id,
                "content_hash": content_hash,
                "chunks": len(chunks),
            }

        raw_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, raw_copy)
        atomic_write_text(text_path, extracted.text)

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO raw_sources
                   (id, uri, file_path, source_type, title, author, captured_at, content_hash,
                    raw_text_path, metadata_json, trust_status, privacy_class, extraction_status,
                    error, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source_id,
                    str(source_path),
                    str(raw_copy),
                    detected_type,
                    display_title,
                    author or "",
                    now,
                    content_hash,
                    str(text_path),
                    json.dumps(metadata, sort_keys=True),
                    "current",
                    privacy,
                    "extracted",
                    "",
                    now,
                    now,
                ),
            )
            conn.commit()

        chunk_count = self._insert_chunks(source_id, extracted.text, metadata, index_embeddings)
        return {
            "status": "created",
            "source_id": source_id,
            "content_hash": content_hash,
            "chunks": chunk_count,
        }

    def _insert_chunks(
        self,
        source_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        index_embeddings: bool = False,
    ) -> int:
        chunks = chunk_text(text)
        now = now_iso()
        rows = []
        fts_rows = []
        for chunk in chunks:
            chunk_id = self._chunk_id(source_id, chunk.chunk_index)
            rows.append(
                (
                    chunk_id,
                    source_id,
                    chunk.chunk_index,
                    chunk.text,
                    chunk.start_offset,
                    chunk.end_offset,
                    chunk.token_estimate,
                    chunk.content_hash,
                    chunk_id,
                    json.dumps(metadata or {}, sort_keys=True),
                    now,
                )
            )
            fts_rows.append((chunk_id, source_id, chunk.text))

        with self._connect() as conn:
            conn.execute("DELETE FROM source_chunks WHERE source_id = ?", (source_id,))
            conn.execute("DELETE FROM source_chunks_fts WHERE source_id = ?", (source_id,))
            conn.executemany(
                """INSERT INTO source_chunks
                   (id, source_id, chunk_index, text, start_offset, end_offset, token_estimate,
                    content_hash, embedding_id, metadata_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            conn.executemany(
                "INSERT INTO source_chunks_fts (id, source_id, text) VALUES (?, ?, ?)",
                fts_rows,
            )
            conn.commit()

        if index_embeddings and rows:
            self._index_chroma(source_id)
        return len(rows)

    def _index_chroma(self, source_id: str) -> None:
        try:
            from ..backends.registry import get_backend

            source = self.get_source(source_id)
            chunks = self.list_chunks(source_id)
            backend = get_backend(anaktoron_path=self.anaktoron_path)
            collection = backend.get_collection(SOURCE_CHROMA_COLLECTION, create=True)
            collection.upsert(
                ids=[chunk["id"] for chunk in chunks],
                documents=[chunk["text"] for chunk in chunks],
                metadatas=[
                    {
                        "kind": "source_chunk",
                        "source_id": source_id,
                        "chunk_id": chunk["id"],
                        "source_type": source["source_type"],
                        "title": source["title"],
                        "content_hash": chunk["content_hash"],
                        "privacy_class": source["privacy_class"],
                        "trust_status": source["trust_status"],
                    }
                    for chunk in chunks
                ],
            )
        except Exception:
            return

    def get_source_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM raw_sources WHERE content_hash = ?", (content_hash,)
            ).fetchone()
        return self._decode_source(row) if row else None

    def get_source(self, source_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM raw_sources WHERE id = ?", (source_id,)).fetchone()
        if not row:
            raise KeyError(f"source not found: {source_id}")
        return self._decode_source(row)

    def list_sources(
        self,
        source_type: str | None = None,
        privacy_class: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM raw_sources"
        clauses = []
        params: list[Any] = []
        if source_type:
            clauses.append("source_type = ?")
            params.append(source_type)
        if privacy_class:
            clauses.append("privacy_class = ?")
            params.append(privacy_class)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY captured_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._decode_source(row) for row in rows]

    def list_chunks(self, source_id: str, limit: int = 1000) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM source_chunks
                   WHERE source_id = ?
                   ORDER BY chunk_index
                   LIMIT ?""",
                (source_id, max(1, int(limit))),
            ).fetchall()
        return [self._decode_chunk(row) for row in rows]

    def read_source(self, source_id: str, include_chunks: bool = False) -> dict[str, Any]:
        source = self.get_source(source_id)
        text = ""
        if source.get("raw_text_path"):
            path = Path(source["raw_text_path"])
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
        payload: dict[str, Any] = {"source": source, "text": text}
        if include_chunks:
            payload["chunks"] = self.list_chunks(source_id)
        return payload

    def get_chunk(self, chunk_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM source_chunks WHERE id = ?", (chunk_id,)).fetchone()
        if not row:
            raise KeyError(f"chunk not found: {chunk_id}")
        return self._decode_chunk(row)

    def search(
        self,
        query: str,
        limit: int = 10,
        privacy_class: str | None = None,
        trust_status: str | None = None,
        include_quarantined: bool = False,
    ) -> list[dict[str, Any]]:
        tokens = re.findall(r"\b[A-Za-z0-9_]{2,}\b", query)
        if not tokens:
            return []
        matches = [" ".join(tokens)]
        if len(tokens) > 1:
            matches.append(" OR ".join(tokens))

        def _run_match(match: str) -> list[sqlite3.Row]:
            sql = """
            SELECT c.*, s.title, s.source_type, s.privacy_class, s.trust_status,
                   bm25(source_chunks_fts) AS rank
            FROM source_chunks_fts f
            JOIN source_chunks c ON c.id = f.id
            JOIN raw_sources s ON s.id = c.source_id
            WHERE source_chunks_fts MATCH ?
            """
            params: list[Any] = [match]
            if privacy_class:
                sql += " AND s.privacy_class = ?"
                params.append(privacy_class)
            if trust_status:
                sql += " AND s.trust_status = ?"
                params.append(trust_status)
            elif not include_quarantined:
                sql += " AND s.trust_status != 'quarantined'"
            sql += " ORDER BY rank LIMIT ?"
            params.append(max(1, int(limit)))
            with self._connect() as conn:
                return conn.execute(sql, params).fetchall()

        rows = []
        for match in matches:
            rows = _run_match(match)
            if rows:
                break
        return [self._decode_search_row(row) for row in rows]

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            sources = conn.execute("SELECT COUNT(*) FROM raw_sources").fetchone()[0]
            chunks = conn.execute("SELECT COUNT(*) FROM source_chunks").fetchone()[0]
            by_privacy = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT privacy_class, COUNT(*) FROM raw_sources GROUP BY privacy_class"
                ).fetchall()
            }
            by_type = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT source_type, COUNT(*) FROM raw_sources GROUP BY source_type"
                ).fetchall()
            }
        return {
            "sources": sources,
            "chunks": chunks,
            "by_privacy": by_privacy,
            "by_type": by_type,
            "source_path": str(self.source_path),
            "db_path": str(self.db_path),
        }

    def _decode_source(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data

    def _decode_chunk(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data

    def _decode_search_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = self._decode_chunk(row)
        data.update(
            {
                "title": row["title"],
                "source_type": row["source_type"],
                "privacy_class": row["privacy_class"],
                "trust_status": row["trust_status"],
            }
        )
        return data
