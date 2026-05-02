"""Message-granular JSONL ingestion for Claude/Codex transcripts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .backends.registry import get_backend
from .config import MnemionConfig


def _flatten_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                block_type = item.get("type")
                if block_type == "text":
                    parts.append(str(item.get("text", "")))
                elif block_type == "tool_use":
                    parts.append(f"tool_use: {item.get('name', 'unknown')} {json.dumps(item.get('input', {}), sort_keys=True)}")
                elif block_type == "tool_result":
                    parts.append(f"tool_result: {_flatten_content(item.get('content'))}")
                else:
                    parts.append(json.dumps(item, sort_keys=True))
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        if "text" in value:
            return str(value["text"])
        return json.dumps(value, sort_keys=True)
    return str(value)


def _normalise_row(data: dict[str, Any], path: Path, line_number: int) -> dict[str, Any] | None:
    message = data.get("message") if isinstance(data.get("message"), dict) else data
    role = message.get("role") or data.get("role")
    content = _flatten_content(message.get("content") if "content" in message else data.get("content"))
    if not role or not content.strip():
        return None

    session_id = (
        data.get("session_id")
        or data.get("sessionId")
        or message.get("session_id")
        or data.get("conversation_id")
        or path.stem
    )
    uuid = (
        data.get("uuid")
        or data.get("id")
        or message.get("uuid")
        or message.get("id")
        or hashlib.sha1(f"{path}:{line_number}:{role}:{content}".encode()).hexdigest()[:16]
    )
    timestamp = (
        data.get("timestamp")
        or data.get("created_at")
        or message.get("timestamp")
        or message.get("created_at")
        or ""
    )
    return {
        "session_id": str(session_id),
        "uuid": str(uuid),
        "timestamp": str(timestamp),
        "role": str(role),
        "content": content.strip(),
        "source_file": str(path),
    }


def parse_jsonl(path: str | Path, stats: dict[str, int] | None = None) -> Iterable[dict[str, Any]]:
    source = Path(path)
    with source.open(encoding="utf-8", errors="replace") as f:
        for line_number, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                if stats is not None:
                    stats["skipped_invalid"] = stats.get("skipped_invalid", 0) + 1
                continue
            if isinstance(data, dict):
                row = _normalise_row(data, source, line_number)
                if row:
                    yield row
                elif stats is not None:
                    stats["skipped_unsupported"] = stats.get("skipped_unsupported", 0) + 1
            elif stats is not None:
                stats["skipped_unsupported"] = stats.get("skipped_unsupported", 0) + 1


def _iter_jsonl(source: str | Path) -> list[Path]:
    path = Path(source).expanduser().resolve()
    if path.is_dir():
        return sorted(path.rglob("*.jsonl"))
    return [path]


def _cursor_path(anaktoron_path: str) -> Path:
    return Path(anaktoron_path).expanduser().resolve() / ".mnemion" / "sweep_cursor.json"


def _load_cursors(anaktoron_path: str) -> dict[str, str]:
    path = _cursor_path(anaktoron_path)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cursors(anaktoron_path: str, cursors: dict[str, str]) -> None:
    path = _cursor_path(anaktoron_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cursors, indent=2, sort_keys=True))


def _doc_id(row: dict[str, Any]) -> str:
    session = row["session_id"].replace("/", "_").replace("\\", "_")
    uuid = row["uuid"].replace("/", "_").replace("\\", "_")
    return f"sweep_{session}_{uuid}"


def sweep(
    jsonl_or_dir: str,
    anaktoron_path: str | None = None,
    source_label: str | None = None,
    collection_name: str | None = None,
    batch_size: int = 64,
) -> dict[str, int]:
    cfg = MnemionConfig()
    target = anaktoron_path or cfg.anaktoron_path
    collection = get_backend(anaktoron_path=target).get_collection(
        collection_name or cfg.collection_name,
        create=True,
    )
    cursors = _load_cursors(target)
    stats = {
        "files": 0,
        "seen": 0,
        "filed": 0,
        "skipped_existing": 0,
        "skipped_cursor": 0,
        "skipped_invalid": 0,
        "skipped_unsupported": 0,
    }

    def flush(batch: list[dict[str, Any]]) -> None:
        if not batch:
            return
        ids = [_doc_id(row) for row in batch]
        existing = set(collection.get(ids=ids).ids)
        new_rows = [row for row, doc_id in zip(batch, ids) if doc_id not in existing]
        stats["skipped_existing"] += len(batch) - len(new_rows)
        if not new_rows:
            return
        now = datetime.now(timezone.utc).isoformat()
        collection.upsert(
            ids=[_doc_id(row) for row in new_rows],
            documents=[row["content"] for row in new_rows],
            metadatas=[
                {
                    "wing": source_label or "sweeps",
                    "room": row["role"],
                    "source_file": row["source_file"],
                    "session_id": row["session_id"],
                    "timestamp": row["timestamp"],
                    "message_uuid": row["uuid"],
                    "role": row["role"],
                    "filed_at": now,
                    "ingest_mode": "sweep",
                }
                for row in new_rows
            ],
        )
        stats["filed"] += len(new_rows)

    for path in _iter_jsonl(jsonl_or_dir):
        stats["files"] += 1
        cursor_key = str(path)
        cursor_ts = cursors.get(cursor_key)
        max_ts = cursor_ts or ""
        batch: list[dict[str, Any]] = []
        for row in parse_jsonl(path, stats=stats):
            stats["seen"] += 1
            if cursor_ts and row["timestamp"] and row["timestamp"] < cursor_ts:
                stats["skipped_cursor"] += 1
                stats["skipped_existing"] += 1
                continue
            batch.append(row)
            if row["timestamp"] and row["timestamp"] > max_ts:
                max_ts = row["timestamp"]
            if len(batch) >= batch_size:
                flush(batch)
                batch = []
        flush(batch)
        if max_ts:
            cursors[cursor_key] = max_ts

    _save_cursors(target, cursors)
    return stats
