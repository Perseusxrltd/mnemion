"""Repair helpers for Chroma-backed Anaktorons."""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import DEFAULT_COLLECTION_NAME

MAX_SEQ_ID_SANITY_THRESHOLD = 1 << 53


@dataclass(frozen=True)
class MaxSeqIdIssue:
    rowid: int
    segment_id: str | None
    current: int
    replacement: int | None
    source: str


def _db_path(anaktoron_path: str) -> Path:
    return Path(anaktoron_path).expanduser().resolve() / "chroma.sqlite3"


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.OperationalError:
        return set()


def _seq_id_to_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, bytes):
        return int.from_bytes(value, byteorder="big")
    return None


def _load_sidecar(anaktoron_path: str) -> dict[str, int]:
    candidates = [
        Path(anaktoron_path) / ".mnemion" / "max_seq_id.json",
        Path(anaktoron_path) / "max_seq_id.json",
        Path(anaktoron_path) / "chroma.sqlite3.max_seq_id.json",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        values = data.get("max_seq_id", data) if isinstance(data, dict) else {}
        if isinstance(values, dict):
            return {str(k): int(v) for k, v in values.items() if isinstance(v, (int, float, str))}
    return {}


def _heuristic_replacement(
    conn: sqlite3.Connection,
    segment_id: str | None,
    threshold: int,
) -> int | None:
    cols = _table_columns(conn, "embeddings")
    if "seq_id" not in cols:
        return None
    sql = "SELECT MAX(seq_id) FROM embeddings WHERE typeof(seq_id) = 'integer' AND seq_id <= ?"
    params: list[Any] = [threshold]
    if segment_id and "segment_id" in cols:
        sql += " AND segment_id = ?"
        params.append(segment_id)
    value = conn.execute(sql, params).fetchone()[0]
    return int(value) if value is not None else None


def scan_max_seq_id(
    anaktoron_path: str,
    threshold: int = MAX_SEQ_ID_SANITY_THRESHOLD,
) -> list[MaxSeqIdIssue]:
    """Find poisoned max_seq_id rows and determine a safe replacement."""
    db = _db_path(anaktoron_path)
    if not db.is_file():
        return []
    sidecar = _load_sidecar(anaktoron_path)
    issues: list[MaxSeqIdIssue] = []
    with sqlite3.connect(db) as conn:
        cols = _table_columns(conn, "max_seq_id")
        if "seq_id" not in cols:
            return []
        select_cols = "rowid, seq_id"
        if "segment_id" in cols:
            select_cols += ", segment_id"
        for row in conn.execute(f"SELECT {select_cols} FROM max_seq_id").fetchall():
            rowid, raw_current = row[0], row[1]
            segment_id = row[2] if len(row) > 2 else None
            current = _seq_id_to_int(raw_current)
            if current is None or current <= threshold:
                continue
            replacement = None
            source = "unresolved"
            if segment_id and str(segment_id) in sidecar:
                replacement = sidecar[str(segment_id)]
                source = "sidecar"
            else:
                replacement = _heuristic_replacement(conn, segment_id, threshold)
                if replacement is not None:
                    source = "embeddings"
            issues.append(
                MaxSeqIdIssue(
                    rowid=rowid,
                    segment_id=str(segment_id) if segment_id is not None else None,
                    current=current,
                    replacement=replacement,
                    source=source,
                )
            )
    return issues


def repair_max_seq_id(
    anaktoron_path: str,
    dry_run: bool = False,
    backup: bool = True,
    threshold: int = MAX_SEQ_ID_SANITY_THRESHOLD,
) -> dict[str, Any]:
    """Repair poisoned max_seq_id rows using sidecar or embeddings heuristics."""
    issues = scan_max_seq_id(anaktoron_path, threshold=threshold)
    actionable = [issue for issue in issues if issue.replacement is not None]
    if dry_run or not actionable:
        return {
            "issues": [asdict(issue) for issue in issues],
            "would_update": len(actionable),
            "updated": 0,
            "backup_path": None,
        }

    db = _db_path(anaktoron_path)
    backup_path = None
    if backup:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = str(db.with_suffix(f".sqlite3.bak.{stamp}"))
        shutil.copy2(db, backup_path)

    with sqlite3.connect(db) as conn:
        conn.executemany(
            "UPDATE max_seq_id SET seq_id = ? WHERE rowid = ?",
            [(issue.replacement, issue.rowid) for issue in actionable],
        )
        conn.commit()

    return {
        "issues": [asdict(issue) for issue in issues],
        "would_update": len(actionable),
        "updated": len(actionable),
        "backup_path": backup_path,
    }


def check_extraction_safety(extracted_count: int, sqlite_count: int | None) -> None:
    """Abort rebuilds that look like truncated Chroma extraction."""
    if sqlite_count is not None and extracted_count < sqlite_count:
        raise RuntimeError(
            f"Refusing unsafe repair: extracted {extracted_count} drawers from {sqlite_count}"
        )
    if sqlite_count is None and extracted_count == 10_000:
        raise RuntimeError("Refusing unsafe repair: extraction stopped at Chroma's 10,000 default")


def status(
    anaktoron_path: str,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> dict[str, Any]:
    from .backends.chroma import hnsw_capacity_status, scan_stale_hnsw

    db = _db_path(anaktoron_path)
    return {
        "anaktoron_path": str(Path(anaktoron_path).expanduser()),
        "sqlite_exists": db.is_file(),
        "max_seq_id_issues": [asdict(issue) for issue in scan_max_seq_id(anaktoron_path)],
        "hnsw_status": hnsw_capacity_status(anaktoron_path, collection_name),
        "stale_hnsw_segments": scan_stale_hnsw(anaktoron_path),
    }


def scan(
    anaktoron_path: str,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> dict[str, Any]:
    """Read-only repair scan for HNSW and max_seq_id storage issues."""
    data = status(anaktoron_path, collection_name=collection_name)
    stale = data.get("stale_hnsw_segments", [])
    data["dry_run"] = True
    data["would_quarantine_count"] = sum(1 for item in stale if item.get("would_quarantine"))
    return data


def prune(anaktoron_path: str, dry_run: bool = True) -> dict[str, Any]:
    """Placeholder-safe prune hook for the public repair mode.

    Prune remains non-mutating until a dedicated confirm flag exists. It
    reports stale HNSW candidates so operators can choose a rebuild path.
    """
    from .backends.chroma import scan_stale_hnsw

    hnsw_dirs = [p for p in Path(anaktoron_path).glob("*/") if p.is_dir()]
    stale = scan_stale_hnsw(anaktoron_path)
    return {
        "dry_run": True,
        "requested_dry_run": dry_run,
        "candidate_dirs": [str(p) for p in hnsw_dirs],
        "stale_hnsw_segments": stale,
        "would_quarantine_count": sum(1 for item in stale if item.get("would_quarantine")),
        "removed": 0,
    }
