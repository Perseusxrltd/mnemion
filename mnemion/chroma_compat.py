"""
ChromaDB compatibility and safety helpers for Mnemion.

The functions in this module deliberately keep chromadb imports lazy. Health
checks and SQLite repair probes must be callable before any vector segment is
loaded, because a diverged HNSW segment can crash Chroma on open.
"""

from __future__ import annotations

import gc
import logging
import os
import pickle
import sqlite3
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("mnemion.chroma_compat")

BLOB_FIX_MARKER = ".blob_seq_ids_migrated"
SYSDB10_PREFIX = b"\x11\x11"

HNSW_DIVERGENCE_ABSOLUTE = 2_000
HNSW_DIVERGENCE_FRACTION = 0.10


class VectorStoreUnsafe(RuntimeError):
    """Raised when opening Chroma would load a known-diverged vector segment."""

    def __init__(self, health: dict[str, Any]):
        self.health = health
        super().__init__(health.get("message") or "Vector store is unsafe to open")


def fix_blob_seq_ids(anaktoron_path: str) -> None:
    """Convert legacy BLOB ``embeddings.seq_id`` rows to INTEGER.

    Older Mnemion versions also converted ``max_seq_id.seq_id``. That is
    unsafe with ChromaDB 1.5.x because native sysdb rows may use a
    ``b"\\x11\\x11"``-prefixed BLOB representation; treating those bytes as a
    big-endian integer poisons ``max_seq_id`` and suppresses future writes.

    This migration therefore touches only ``embeddings`` and skips defensive
    sysdb-10-prefixed blobs. A marker avoids reopening SQLite on every startup
    after a database has been checked once.
    """
    anaktoron = Path(anaktoron_path).expanduser()
    db_path = anaktoron / "chroma.sqlite3"
    marker_path = anaktoron / BLOB_FIX_MARKER
    if marker_path.exists() or not db_path.is_file():
        return

    try:
        with sqlite3.connect(db_path) as conn:
            try:
                rows = conn.execute(
                    "SELECT rowid, seq_id FROM embeddings WHERE typeof(seq_id) = 'blob'"
                ).fetchall()
            except sqlite3.OperationalError:
                return

            updates = []
            skipped = 0
            for rowid, blob in rows:
                if not isinstance(blob, (bytes, bytearray, memoryview)):
                    continue
                raw = bytes(blob)
                if raw.startswith(SYSDB10_PREFIX):
                    skipped += 1
                    continue
                updates.append((int.from_bytes(raw, byteorder="big"), rowid))

            if updates:
                conn.executemany("UPDATE embeddings SET seq_id = ? WHERE rowid = ?", updates)
                logger.info("Fixed %d BLOB embeddings.seq_id rows in %s", len(updates), db_path)
            if skipped:
                logger.info("Skipped %d sysdb-prefixed embeddings.seq_id BLOB rows", skipped)
            conn.commit()

        try:
            marker_path.touch(exist_ok=True)
        except OSError:
            logger.debug("Could not write BLOB migration marker at %s", marker_path, exc_info=True)
    except sqlite3.DatabaseError:
        logger.debug("Skipping BLOB seq_id migration for unreadable SQLite DB %s", db_path)
    except Exception:
        logger.exception("Could not fix BLOB seq_ids in %s", db_path)


def prepare_anaktoron_for_chroma(anaktoron_path: str) -> None:
    """Run compatibility checks that must happen before opening Chroma."""
    fix_blob_seq_ids(anaktoron_path)


def make_persistent_client(
    anaktoron_path: str,
    *,
    vector_safe: bool = False,
    collection_name: str = "mnemion_drawers",
):
    """Create a Chroma PersistentClient after storage compatibility checks."""
    prepare_anaktoron_for_chroma(anaktoron_path)
    if vector_safe:
        health = hnsw_capacity_status(anaktoron_path, collection_name)
        if health.get("diverged"):
            raise VectorStoreUnsafe(health)
    import chromadb

    return chromadb.PersistentClient(path=anaktoron_path)


def pin_hnsw_threads(collection) -> None:
    """Best-effort runtime retrofit to keep HNSW writes single-threaded."""
    try:
        from chromadb.api.collection_configuration import (
            UpdateCollectionConfiguration,
            UpdateHNSWConfiguration,
        )

        collection.modify(
            configuration=UpdateCollectionConfiguration(hnsw=UpdateHNSWConfiguration(num_threads=1))
        )
    except Exception:
        logger.debug("Could not retrofit HNSW num_threads=1", exc_info=True)


def db_stat(anaktoron_path: str) -> tuple[int, float]:
    """Return ``(inode, mtime)`` for chroma.sqlite3 or ``(0, 0.0)``."""
    db_path = os.path.join(anaktoron_path, "chroma.sqlite3")
    try:
        st = os.stat(db_path)
        return (getattr(st, "st_ino", 0), st.st_mtime)
    except OSError:
        return (0, 0.0)


def close_chroma_handles() -> None:
    """Drop Chroma singleton caches so SQLite files can be repaired safely."""
    try:
        from chromadb.api.client import SharedSystemClient

        SharedSystemClient.clear_system_cache()
    except Exception:
        pass
    gc.collect()


def verify_hnsw_metadata(collection) -> bool:
    """Return whether a collection exposes Mnemion's required HNSW metadata."""
    try:
        from .config import DRAWER_HNSW_METADATA

        metadata = getattr(collection, "metadata", None) or {}
        return all(metadata.get(key) == value for key, value in DRAWER_HNSW_METADATA.items())
    except Exception:
        return False


def _vector_segment_id(anaktoron_path: str, collection_name: str) -> Optional[str]:
    db_path = os.path.join(anaktoron_path, "chroma.sqlite3")
    if not os.path.isfile(db_path):
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                """
                SELECT s.id
                FROM segments s
                JOIN collections c ON s.collection = c.id
                WHERE c.name = ? AND s.scope = 'VECTOR'
                LIMIT 1
                """,
                (collection_name,),
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def sqlite_embedding_count(anaktoron_path: str, collection_name: str) -> Optional[int]:
    """Count SQLite embeddings for a collection without opening Chroma."""
    db_path = os.path.join(anaktoron_path, "chroma.sqlite3")
    if not os.path.isfile(db_path):
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM embeddings e
                JOIN segments s ON e.segment_id = s.id
                JOIN collections c ON s.collection = c.id
                WHERE c.name = ?
                """,
                (collection_name,),
            ).fetchone()
            return int(row[0]) if row and row[0] is not None else None
        finally:
            conn.close()
    except Exception:
        return None


def _summary_from_counts(
    *,
    total: Optional[int],
    wings: dict[str, int],
    rooms: dict[str, int],
    unavailable: bool,
    message: str,
    source: str,
) -> dict[str, Any]:
    return {
        "total_drawers": int(total or 0),
        "wing_count": len(wings),
        "room_count": len(rooms),
        "wings": wings,
        "rooms": rooms,
        "metadata_unavailable": unavailable,
        "metadata_message": message,
        "metadata_source": source,
    }


def _coerce_meta_value(*values) -> Optional[str]:
    for value in values:
        if value is not None:
            return str(value)
    return None


def _fts_metadata_summary(
    anaktoron_path: str,
    collection_name: str,
    kg_path: Optional[str],
    message: str,
) -> dict[str, Any]:
    kg = (
        Path(kg_path)
        if kg_path
        else Path(anaktoron_path).expanduser().parent / "knowledge_graph.sqlite3"
    )
    if not kg.is_file():
        return _summary_from_counts(
            total=sqlite_embedding_count(anaktoron_path, collection_name),
            wings={},
            rooms={},
            unavailable=True,
            message=message or "Chroma metadata unavailable and FTS mirror not found",
            source="unavailable",
        )
    try:
        conn = sqlite3.connect(f"file:{kg}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT COALESCE(wing, 'unknown'), COALESCE(room, 'unknown'), COUNT(*) "
                "FROM drawers_fts GROUP BY wing, room"
            ).fetchall()
        finally:
            conn.close()
    except Exception as exc:
        return _summary_from_counts(
            total=sqlite_embedding_count(anaktoron_path, collection_name),
            wings={},
            rooms={},
            unavailable=True,
            message=f"{message}; FTS metadata unavailable: {exc}"
            if message
            else f"FTS metadata unavailable: {exc}",
            source="unavailable",
        )

    wings: dict[str, int] = {}
    rooms: dict[str, int] = {}
    total = 0
    for wing, room, count in rows:
        n = int(count)
        wings[str(wing)] = wings.get(str(wing), 0) + n
        rooms[str(room)] = rooms.get(str(room), 0) + n
        total += n
    return _summary_from_counts(
        total=total,
        wings=wings,
        rooms=rooms,
        unavailable=False,
        message="Derived taxonomy from FTS mirror because Chroma metadata was unavailable",
        source="fts",
    )


def sqlite_metadata_summary(
    anaktoron_path: str,
    collection_name: str = "mnemion_drawers",
    *,
    kg_path: Optional[str] = None,
) -> dict[str, Any]:
    """Summarize collection taxonomy without opening Chroma.

    The primary source is Chroma's SQLite metadata tables. If those are not
    readable, fall back to the local FTS mirror. The function never raises.
    """
    db_path = os.path.join(anaktoron_path, "chroma.sqlite3")
    sqlite_count = sqlite_embedding_count(anaktoron_path, collection_name)
    if not os.path.isfile(db_path):
        return _fts_metadata_summary(
            anaktoron_path, collection_name, kg_path, "Chroma SQLite database not found"
        )

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                ).fetchall()
            }
            if not {"collections", "segments", "embeddings", "embedding_metadata"}.issubset(tables):
                raise sqlite3.OperationalError("required Chroma metadata tables missing")

            rows = conn.execute(
                """
                SELECT e.id, m.key, m.string_value, m.int_value, m.float_value, m.bool_value
                FROM embeddings e
                JOIN segments s ON e.segment_id = s.id
                JOIN collections c ON s.collection = c.id
                LEFT JOIN embedding_metadata m
                  ON m.id = e.id AND m.key IN ('wing', 'room')
                WHERE c.name = ?
                """,
                (collection_name,),
            ).fetchall()
        finally:
            conn.close()
    except Exception as exc:
        return _fts_metadata_summary(
            anaktoron_path,
            collection_name,
            kg_path,
            f"Chroma metadata summary unavailable: {exc}",
        )

    by_embedding: dict[Any, dict[str, str]] = {}
    for embedding_id, key, string_value, int_value, float_value, bool_value in rows:
        by_embedding.setdefault(embedding_id, {})
        if key:
            value = _coerce_meta_value(string_value, int_value, float_value, bool_value)
            if value:
                by_embedding[embedding_id][str(key)] = value

    wings: dict[str, int] = {}
    rooms: dict[str, int] = {}
    for meta in by_embedding.values():
        wing = meta.get("wing", "unknown")
        room = meta.get("room", "unknown")
        wings[wing] = wings.get(wing, 0) + 1
        rooms[room] = rooms.get(room, 0) + 1

    if sqlite_count and not by_embedding:
        return _fts_metadata_summary(
            anaktoron_path,
            collection_name,
            kg_path,
            "Chroma metadata rows were empty despite SQLite embeddings",
        )

    return _summary_from_counts(
        total=sqlite_count if sqlite_count is not None else len(by_embedding),
        wings=wings,
        rooms=rooms,
        unavailable=False,
        message="Derived taxonomy from Chroma SQLite metadata",
        source="chroma_sqlite",
    )


class _PersistentDataStub:
    def __init__(self, *args, **kwargs):
        pass

    def __setstate__(self, state):
        if isinstance(state, dict):
            self.__dict__.update(state)
        elif isinstance(state, tuple) and len(state) == 2 and isinstance(state[1], dict):
            self.__dict__.update(state[1])


class _SafePersistentDataUnpickler:
    _ALLOWED = frozenset(
        {
            (
                "chromadb.segment.impl.vector.local_persistent_hnsw",
                "PersistentData",
            ),
        }
    )

    @classmethod
    def load(cls, path: str):
        class _Restricted(pickle.Unpickler):
            def find_class(self, module: str, name: str):
                if (module, name) in cls._ALLOWED:
                    return _PersistentDataStub
                raise pickle.UnpicklingError(f"disallowed class: {module}.{name}")

        with open(path, "rb") as f:
            return _Restricted(f).load()


def _hnsw_element_count(anaktoron_path: str, segment_id: str) -> Optional[int]:
    pickle_path = os.path.join(anaktoron_path, segment_id, "index_metadata.pickle")
    if not os.path.isfile(pickle_path):
        return None
    try:
        persistent_data = _SafePersistentDataUnpickler.load(pickle_path)
        if isinstance(persistent_data, dict):
            id_to_label = persistent_data.get("id_to_label")
        else:
            id_to_label = getattr(persistent_data, "id_to_label", None)
        if isinstance(id_to_label, dict):
            return len(id_to_label)
        return None
    except Exception:
        logger.debug("Could not read HNSW metadata at %s", pickle_path, exc_info=True)
        return None


def hnsw_capacity_status(anaktoron_path: str, collection_name: str = "mnemion_drawers") -> dict:
    """Compare SQLite embedding count with persisted HNSW element count.

    Never opens a Chroma client and never raises.
    """
    out: dict[str, Any] = {
        "segment_id": None,
        "sqlite_count": None,
        "hnsw_count": None,
        "divergence": None,
        "diverged": False,
        "status": "unknown",
        "message": "",
    }

    try:
        segment_id = _vector_segment_id(anaktoron_path, collection_name)
        sqlite_count = sqlite_embedding_count(anaktoron_path, collection_name)
        out["segment_id"] = segment_id
        out["sqlite_count"] = sqlite_count

        if segment_id is None or sqlite_count is None:
            out["message"] = "Anaktoron vector state is unreadable or not initialized"
            return out

        hnsw_count = _hnsw_element_count(anaktoron_path, segment_id)
        out["hnsw_count"] = hnsw_count

        if hnsw_count is None:
            if sqlite_count > HNSW_DIVERGENCE_ABSOLUTE:
                out["status"] = "diverged"
                out["diverged"] = True
                out["divergence"] = sqlite_count
                out["message"] = (
                    f"SQLite has {sqlite_count:,} embeddings but HNSW metadata has not "
                    "flushed; run `mnemion repair --mode rebuild` if vector search is unsafe."
                )
            else:
                out["message"] = "HNSW metadata not flushed yet; status unknown"
            return out

        divergence = sqlite_count - hnsw_count
        out["divergence"] = divergence
        threshold = max(HNSW_DIVERGENCE_ABSOLUTE, int(sqlite_count * HNSW_DIVERGENCE_FRACTION))
        if divergence > threshold:
            pct = 100.0 * divergence / max(sqlite_count, 1)
            out["status"] = "diverged"
            out["diverged"] = True
            out["message"] = (
                f"HNSW holds {hnsw_count:,} elements but SQLite has "
                f"{sqlite_count:,}; {divergence:,} drawers ({pct:.0f}%) may be "
                "invisible to vector search. Run `mnemion repair --mode rebuild`."
            )
        else:
            out["status"] = "ok"
            out["message"] = f"HNSW {hnsw_count:,} / SQLite {sqlite_count:,}"
        return out
    except Exception as exc:
        out["message"] = f"HNSW health probe failed: {exc}"
        return out
