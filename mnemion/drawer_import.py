"""Strict, preflighted compatibility import for old drawer-only JSON exports."""

from __future__ import annotations

import json
import math
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def iter_drawers(path: str | Path, *, read_size: int = 65536):
    decoder = json.JSONDecoder(parse_constant=_reject_constant)
    buffer, eof = "", False
    with Path(path).open("r", encoding="utf-8") as source:

        def refill():
            nonlocal buffer, eof
            chunk = source.read(read_size)
            buffer += chunk
            eof = not chunk
            if len(buffer) > 32 * 1024**2:
                raise ValueError("A legacy drawer exceeds the 32 MiB import limit")

        def whitespace():
            nonlocal buffer
            buffer = buffer.lstrip(" \r\n\t")
            while not buffer and not eof:
                refill()
                buffer = buffer.lstrip(" \r\n\t")

        whitespace()
        if not buffer.startswith("["):
            raise ValueError("A drawer export must be a complete JSON array")
        buffer = buffer[1:]
        whitespace()
        if not buffer.startswith("]"):
            while True:
                while True:
                    try:
                        row, end = decoder.raw_decode(buffer)
                        break
                    except json.JSONDecodeError as exc:
                        if eof:
                            raise ValueError("Malformed or truncated drawer export") from exc
                        refill()
                if (
                    not isinstance(row, dict)
                    or not isinstance(row.get("id"), str)
                    or not row["id"]
                    or "\0" in row["id"]
                ):
                    raise ValueError("Every drawer requires a nonempty text ID")
                if (
                    not isinstance(row.get("content"), str)
                    or not row["content"].strip()
                    or "\0" in row["content"]
                ):
                    raise ValueError("Every drawer requires nonempty text content")
                metadata = row.get("meta") if row.get("meta") is not None else {}
                if not isinstance(metadata, dict) or any(
                    not isinstance(key, str)
                    or not key
                    or "\0" in key
                    or not isinstance(value, (str, int, float, bool))
                    or (isinstance(value, str) and "\0" in value)
                    or (isinstance(value, float) and not math.isfinite(value))
                    or (isinstance(value, int) and not -(2**63) <= value < 2**63)
                    for key, value in metadata.items()
                ):
                    raise ValueError("Drawer metadata must contain valid Chroma scalar values")
                yield {"id": row["id"], "content": row["content"], "meta": metadata}
                buffer = buffer[end:]
                whitespace()
                if buffer.startswith("]"):
                    break
                if not buffer.startswith(","):
                    raise ValueError("Expected a comma or the end of the drawer array")
                buffer = buffer[1:]
                whitespace()
                if buffer.startswith("]"):
                    raise ValueError("A JSON array cannot have a trailing comma")
        if not buffer.startswith("]"):
            raise ValueError("Truncated drawer export")
        buffer = buffer[1:]
        whitespace()
        if buffer:
            raise ValueError("Unexpected data after the drawer array")


@contextmanager
def preflight(path: str | Path):
    """Finish parsing and deduplicating on disk before opening a live backend."""
    with tempfile.TemporaryDirectory(prefix="mnemion-drawer-import-") as directory:
        with sqlite3.connect(Path(directory) / "validated.sqlite3") as conn:
            conn.execute("CREATE TABLE records (id TEXT PRIMARY KEY, content TEXT, metadata TEXT)")
            count = 0
            try:
                for row in iter_drawers(path):
                    conn.execute(
                        "INSERT INTO records VALUES (?,?,?)",
                        (
                            row["id"],
                            row["content"],
                            json.dumps(row["meta"], ensure_ascii=False, allow_nan=False),
                        ),
                    )
                    count += 1
            except sqlite3.IntegrityError as exc:
                raise ValueError("A drawer ID occurs more than once in the export") from exc
            conn.commit()
            yield conn, count


def restore_drawers(
    path: str | Path,
    palace: str | Path,
    collection_name: str,
    *,
    merge: bool = False,
    backend_factory=None,
) -> dict:
    from .ingestion import LegacyMemoryWriter

    with preflight(path) as (validated, count):
        if backend_factory is None:
            from .backends.registry import get_backend

            backend_factory = get_backend
        backend = backend_factory(anaktoron_path=str(palace))
        collection = backend.get_collection(collection_name, create=True)
        if collection.count() and not merge:
            raise ValueError(
                "The destination already contains drawers; use --merge or restore a complete backup into a new profile"
            )
        writer = LegacyMemoryWriter(collection, Path(palace).parent / "knowledge_graph.sqlite3")
        records = (
            {"id": identity, "content": content, "metadata": json.loads(metadata)}
            for identity, content, metadata in validated.execute(
                "SELECT id,content,metadata FROM records ORDER BY id"
            )
        )
        result = writer.import_records(records)
    return {
        **result,
        "validated_records": count,
        "new_records_require_review": True,
        "format": "legacy_drawer_json_only",
    }
