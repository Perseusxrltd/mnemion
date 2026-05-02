"""ChromaDB backend with guarded collection creation."""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

import chromadb

from ..chroma_compat import (
    fix_blob_seq_ids,
    fix_legacy_collection_config_json,
    fix_legacy_hnsw_metadata_pickle,
)
from ..config import DRAWER_HNSW_METADATA
from ..embedding import get_embedding_function
from .base import BaseBackend, BaseCollection, GetResult, QueryResult, UnsupportedFilterError

DEFAULT_HNSW_METADATA = dict(DRAWER_HNSW_METADATA)

_CLIENT_CACHE: dict[tuple[str, tuple[int, int, int] | None], Any] = {}
_ALLOWED_OPERATORS = {"$and", "$or", "$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin"}
_HNSW_DIVERGENCE_FALLBACK_FLOOR = 2000
_HNSW_DIVERGENCE_FRACTION = 0.10

logger = logging.getLogger(__name__)


def _path_stamp(path: str) -> tuple[int, int, int] | None:
    target = Path(path) / "chroma.sqlite3"
    if not target.exists():
        target = Path(path)
    try:
        stat = os.stat(target)
        return (getattr(stat, "st_ino", 0), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def validate_where(where: dict | None) -> None:
    """Reject Chroma filters with unsupported operators before they reach storage."""
    if where is None:
        return
    if not isinstance(where, dict):
        raise UnsupportedFilterError("Chroma where filters must be dictionaries")

    for key, value in where.items():
        if key.startswith("$") and key not in _ALLOWED_OPERATORS:
            raise UnsupportedFilterError(f"Unsupported Chroma filter operator: {key}")
        if key in {"$and", "$or"}:
            if not isinstance(value, list):
                raise UnsupportedFilterError(f"{key} filter must be a list")
            for child in value:
                validate_where(child)
        elif isinstance(value, dict):
            for op, op_value in value.items():
                if op.startswith("$") and op not in _ALLOWED_OPERATORS:
                    raise UnsupportedFilterError(f"Unsupported Chroma filter operator: {op}")
                if isinstance(op_value, dict):
                    validate_where(op_value)


def _segment_appears_healthy(seg_dir: str | Path) -> bool:
    """Return True when a Chroma HNSW segment metadata file looks complete."""
    meta_path = Path(seg_dir) / "index_metadata.pickle"
    if not meta_path.is_file():
        return True
    try:
        size = meta_path.stat().st_size
        if size < 16:
            return False
        with open(meta_path, "rb") as f:
            head = f.read(2)
            f.seek(-1, os.SEEK_END)
            tail = f.read(1)
    except OSError:
        return False
    return len(head) == 2 and head[0] == 0x80 and tail == b"\x2e"


def scan_stale_hnsw(anaktoron_path: str, stale_seconds: float = 300.0) -> list[dict[str, Any]]:
    """Read-only scan for stale HNSW segment dirs that look unsafe to load."""
    root = Path(anaktoron_path).expanduser().resolve()
    db_path = root / "chroma.sqlite3"
    if not db_path.is_file():
        return []
    try:
        sqlite_mtime = db_path.stat().st_mtime
        entries = list(root.iterdir())
    except OSError:
        return []

    findings: list[dict[str, Any]] = []
    for seg_dir in entries:
        if (
            not seg_dir.is_dir()
            or "-" not in seg_dir.name
            or seg_dir.name.startswith(".")
            or ".drift-" in seg_dir.name
        ):
            continue
        hnsw_bin = seg_dir / "data_level0.bin"
        if not hnsw_bin.is_file():
            continue
        try:
            hnsw_mtime = hnsw_bin.stat().st_mtime
        except OSError:
            continue
        mtime_gap = sqlite_mtime - hnsw_mtime
        is_stale = mtime_gap >= stale_seconds
        metadata_healthy = _segment_appears_healthy(seg_dir)
        findings.append(
            {
                "path": str(seg_dir),
                "segment_id": seg_dir.name,
                "mtime_gap_seconds": mtime_gap,
                "stale": is_stale,
                "metadata_healthy": metadata_healthy,
                "would_quarantine": is_stale and not metadata_healthy,
            }
        )
    return findings


def quarantine_stale_hnsw(
    anaktoron_path: str,
    stale_seconds: float = 300.0,
    dry_run: bool = False,
) -> list[str]:
    """Rename stale, malformed HNSW segments so Chroma can lazily rebuild them.

    This is intentionally not called during normal client creation. Repair
    commands can opt into it, while status and scan stay read-only.
    """
    moved: list[str] = []
    for finding in scan_stale_hnsw(anaktoron_path, stale_seconds=stale_seconds):
        if not finding["would_quarantine"]:
            continue
        source = Path(finding["path"])
        if dry_run:
            moved.append(str(source))
            continue
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        target = source.with_name(f"{source.name}.drift-{stamp}")
        try:
            source.rename(target)
        except OSError:
            logger.exception("Failed to quarantine corrupt HNSW segment %s", source)
            continue
        logger.warning("Quarantined corrupt HNSW segment %s as %s", source, target)
        moved.append(str(target))
    return moved


def _vector_segment_id(anaktoron_path: str, collection_name: str) -> str | None:
    db_path = Path(anaktoron_path).expanduser().resolve() / "chroma.sqlite3"
    if not db_path.is_file():
        return None
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
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
            return str(row[0]) if row else None
    except sqlite3.Error:
        return None


class _PersistentDataStub:
    def __init__(self, *args, **kwargs):
        pass

    def __setstate__(self, state):
        if isinstance(state, dict):
            self.__dict__.update(state)
        elif isinstance(state, tuple) and len(state) == 2 and isinstance(state[1], dict):
            self.__dict__.update(state[1])


class _SafePersistentDataUnpickler:
    """Whitelist-only unpickler for Chroma ``index_metadata.pickle`` files."""

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
        import pickle

        class _Restricted(pickle.Unpickler):
            def find_class(self, module: str, name: str):
                if (module, name) in cls._ALLOWED:
                    return _PersistentDataStub
                raise pickle.UnpicklingError(f"disallowed class: {module}.{name}")

        with open(path, "rb") as f:
            return _Restricted(f).load()


def _hnsw_element_count(anaktoron_path: str, segment_id: str) -> int | None:
    pickle_path = Path(anaktoron_path).expanduser().resolve() / segment_id / "index_metadata.pickle"
    if not pickle_path.is_file():
        return None
    try:
        payload = _SafePersistentDataUnpickler.load(str(pickle_path))
        if isinstance(payload, dict):
            id_to_label = payload.get("id_to_label")
        else:
            id_to_label = getattr(payload, "id_to_label", None)
        return len(id_to_label) if isinstance(id_to_label, dict) else None
    except Exception:
        logger.debug("_hnsw_element_count failed for %s", pickle_path, exc_info=True)
        return None


def _sqlite_embedding_count(anaktoron_path: str, collection_name: str) -> int | None:
    db_path = Path(anaktoron_path).expanduser().resolve() / "chroma.sqlite3"
    if not db_path.is_file():
        return None
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
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
    except sqlite3.Error:
        return None


def _read_sync_threshold(anaktoron_path: str, collection_name: str) -> int:
    db_path = Path(anaktoron_path).expanduser().resolve() / "chroma.sqlite3"
    if not db_path.is_file():
        return 1000
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            tables = {
                row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "collection_metadata" in tables:
                row = conn.execute(
                    """
                    SELECT cm.int_value
                    FROM collection_metadata cm
                    JOIN collections c ON cm.collection_id = c.id
                    WHERE c.name = ? AND cm.key = 'hnsw:sync_threshold'
                    """,
                    (collection_name,),
                ).fetchone()
                if row and row[0] is not None:
                    return int(row[0])

            columns = {info[1] for info in conn.execute("PRAGMA table_info(collections)")}
            if "config_json_str" in columns:
                row = conn.execute(
                    "SELECT config_json_str FROM collections WHERE name = ?",
                    (collection_name,),
                ).fetchone()
                if row and row[0]:
                    config = json.loads(row[0])
                    hnsw_config = config.get("hnsw_configuration", {})
                    value = hnsw_config.get("sync_threshold") or hnsw_config.get(
                        "hnsw:sync_threshold"
                    )
                    if value is not None:
                        return int(value)
    except Exception:
        logger.debug("_read_sync_threshold failed", exc_info=True)
    return 1000


def hnsw_capacity_status(
    anaktoron_path: str,
    collection_name: str = "mnemion_drawers",
) -> dict[str, Any]:
    """Compare SQLite embedding rows with the persisted HNSW element count."""
    out: dict[str, Any] = {
        "collection_name": collection_name,
        "segment_id": None,
        "sqlite_count": None,
        "hnsw_count": None,
        "sync_threshold": None,
        "divergence": None,
        "divergence_threshold": None,
        "diverged": False,
        "status": "unknown",
        "message": "",
    }

    try:
        segment_id = _vector_segment_id(anaktoron_path, collection_name)
        sqlite_count = _sqlite_embedding_count(anaktoron_path, collection_name)
        sync_threshold = _read_sync_threshold(anaktoron_path, collection_name)
        divergence_floor = max(_HNSW_DIVERGENCE_FALLBACK_FLOOR, 2 * sync_threshold)

        out["segment_id"] = segment_id
        out["sqlite_count"] = sqlite_count
        out["sync_threshold"] = sync_threshold
        out["divergence_threshold"] = divergence_floor

        if segment_id is None or sqlite_count is None:
            out["message"] = "Anaktoron state unreadable; skipping HNSW capacity check"
            return out

        hnsw_count = _hnsw_element_count(anaktoron_path, segment_id)
        out["hnsw_count"] = hnsw_count

        if hnsw_count is None:
            if sqlite_count > divergence_floor:
                out["status"] = "diverged"
                out["diverged"] = True
                out["divergence"] = sqlite_count
                out["message"] = (
                    f"SQLite holds {sqlite_count:,} embeddings but the HNSW segment "
                    "has no flushed metadata. Run `mnemion repair --mode rebuild`."
                )
            else:
                out["message"] = "HNSW segment metadata not yet flushed; skipping"
            return out

        divergence = sqlite_count - hnsw_count
        threshold = max(divergence_floor, int(sqlite_count * _HNSW_DIVERGENCE_FRACTION))
        out["divergence"] = divergence
        out["divergence_threshold"] = threshold
        if divergence > threshold:
            out["status"] = "diverged"
            out["diverged"] = True
            pct = 100.0 * divergence / max(sqlite_count, 1)
            out["message"] = (
                f"HNSW index holds {hnsw_count:,} elements but SQLite has "
                f"{sqlite_count:,}; {divergence:,} drawers ({pct:.0f}%) are "
                "invisible to vector search. Run `mnemion repair --mode rebuild`."
            )
        else:
            out["status"] = "ok"
            out["message"] = (
                f"HNSW {hnsw_count:,} / SQLite {sqlite_count:,} "
                "(within flush-lag tolerance)"
            )
    except Exception:
        logger.debug("hnsw_capacity_status failed", exc_info=True)
        out["message"] = "HNSW capacity probe raised; skipping"
    return out


def _pin_hnsw_threads(collection) -> None:
    """Best-effort retrofit for legacy collections created without single-thread HNSW."""
    try:
        from chromadb.api.collection_configuration import (
            UpdateCollectionConfiguration,
            UpdateHNSWConfiguration,
        )
    except ImportError:
        logger.debug("_pin_hnsw_threads skipped: chromadb too old", exc_info=True)
        return
    try:
        collection.modify(
            configuration=UpdateCollectionConfiguration(
                hnsw=UpdateHNSWConfiguration(num_threads=1)
            )
        )
    except Exception:
        logger.debug("_pin_hnsw_threads modify failed", exc_info=True)


def cached_client(path: str):
    resolved = str(Path(path).expanduser().resolve())
    Path(resolved).mkdir(parents=True, exist_ok=True)
    fix_blob_seq_ids(resolved)
    fix_legacy_collection_config_json(resolved)
    fix_legacy_hnsw_metadata_pickle(resolved)
    stamp = _path_stamp(resolved)
    key = (resolved, stamp)
    client = _CLIENT_CACHE.get(key)
    if client is not None:
        return client

    for old_key in [old for old in _CLIENT_CACHE if old[0] == resolved and old != key]:
        _CLIENT_CACHE.pop(old_key, None)

    client = chromadb.PersistentClient(path=resolved)
    _CLIENT_CACHE[key] = client
    return client


class ChromaCollection(BaseCollection):
    def __init__(self, raw_collection):
        self.raw_collection = raw_collection

    def __getattr__(self, name: str) -> Any:
        return getattr(self.raw_collection, name)

    def add(self, **kwargs):
        return self.raw_collection.add(**kwargs)

    def upsert(self, **kwargs):
        return self.raw_collection.upsert(**kwargs)

    def update(self, **kwargs):
        return self.raw_collection.update(**kwargs)

    def delete(self, **kwargs):
        return self.raw_collection.delete(**kwargs)

    def count(self) -> int:
        return self.raw_collection.count()

    def query(self, **kwargs) -> QueryResult:
        validate_where(kwargs.get("where"))
        return QueryResult.from_mapping(self.raw_collection.query(**kwargs))

    def get(self, **kwargs) -> GetResult:
        validate_where(kwargs.get("where"))
        return GetResult.from_mapping(self.raw_collection.get(**kwargs))

    def health(self):
        from .base import HealthStatus

        try:
            self.raw_collection.count()
            return HealthStatus(ok=True)
        except Exception as e:
            return HealthStatus(ok=False, detail=str(e))


class ChromaBackend(BaseBackend):
    name = "chroma"

    def __init__(self, anaktoron_path: str, embedding_device: str | None = None):
        self.anaktoron_path = str(Path(anaktoron_path).expanduser().resolve())
        self.embedding_device = embedding_device
        self.client = cached_client(self.anaktoron_path)
        self.embedding_function = get_embedding_function(embedding_device)

    def _collection_kwargs(self, metadata: dict | None = None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if metadata is not None:
            merged = dict(DEFAULT_HNSW_METADATA)
            merged.update(metadata)
            kwargs["metadata"] = merged
        if self.embedding_function is not None:
            kwargs["embedding_function"] = self.embedding_function
        return kwargs

    def get_collection(self, name: str, create: bool = False) -> ChromaCollection:
        if create:
            raw = self.client.get_or_create_collection(
                name,
                **self._collection_kwargs(DEFAULT_HNSW_METADATA),
            )
        else:
            raw = self.client.get_collection(name, **self._collection_kwargs())
        _pin_hnsw_threads(raw)
        return ChromaCollection(raw)

    def create_collection(self, name: str, metadata: dict | None = None) -> ChromaCollection:
        raw = self.client.create_collection(name, **self._collection_kwargs(metadata))
        _pin_hnsw_threads(raw)
        return ChromaCollection(raw)

    def delete_collection(self, name: str):
        return self.client.delete_collection(name)

    def close(self) -> None:
        for old_key in [old for old in _CLIENT_CACHE if old[0] == self.anaktoron_path]:
            _CLIENT_CACHE.pop(old_key, None)
