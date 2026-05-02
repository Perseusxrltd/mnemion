import os
import pickle
import sqlite3
from pathlib import Path

import pytest

from mnemion.backends.chroma import (
    _SafePersistentDataUnpickler,
    _read_sync_threshold,
    _pin_hnsw_threads,
    hnsw_capacity_status,
    quarantine_stale_hnsw,
    scan_stale_hnsw,
)


class _DisallowedPickleClass:
    pass


def _make_chroma_db(
    anaktoron: Path,
    *,
    collection_name: str = "mnemion_drawers",
    segment_id: str = "segment-a",
    embedding_count: int = 0,
    sync_threshold: int | None = None,
) -> Path:
    anaktoron.mkdir(parents=True, exist_ok=True)
    db = anaktoron / "chroma.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE segments (id TEXT PRIMARY KEY, collection TEXT, scope TEXT)")
        conn.execute("CREATE TABLE embeddings (id TEXT PRIMARY KEY, segment_id TEXT)")
        conn.execute("CREATE TABLE collection_metadata (collection_id TEXT, key TEXT, int_value INTEGER)")
        conn.execute("INSERT INTO collections VALUES ('collection-a', ?)", (collection_name,))
        conn.execute("INSERT INTO segments VALUES (?, 'collection-a', 'VECTOR')", (segment_id,))
        conn.executemany(
            "INSERT INTO embeddings VALUES (?, ?)",
            [(f"drawer-{i}", segment_id) for i in range(embedding_count)],
        )
        if sync_threshold is not None:
            conn.execute(
                "INSERT INTO collection_metadata VALUES "
                "('collection-a', 'hnsw:sync_threshold', ?)",
                (sync_threshold,),
            )
    return db


def _write_hnsw_pickle(anaktoron: Path, segment_id: str, count: int) -> Path:
    segment = anaktoron / segment_id
    segment.mkdir(parents=True, exist_ok=True)
    metadata = segment / "index_metadata.pickle"
    with open(metadata, "wb") as f:
        pickle.dump({"id_to_label": {f"drawer-{i}": i for i in range(count)}}, f)
    return metadata


def test_hnsw_capacity_status_handles_missing_db(tmp_path):
    result = hnsw_capacity_status(str(tmp_path / "missing"), "mnemion_drawers")

    assert result["collection_name"] == "mnemion_drawers"
    assert result["status"] == "unknown"
    assert result["sqlite_count"] is None
    assert result["diverged"] is False


def test_hnsw_capacity_status_reports_healthy_counts(tmp_path):
    anaktoron = tmp_path / "anaktoron"
    _make_chroma_db(anaktoron, embedding_count=3)
    _write_hnsw_pickle(anaktoron, "segment-a", count=3)

    result = hnsw_capacity_status(str(anaktoron), "mnemion_drawers")

    assert result["status"] == "ok"
    assert result["sqlite_count"] == 3
    assert result["hnsw_count"] == 3
    assert result["divergence"] == 0


def test_hnsw_capacity_status_flags_missing_metadata_past_flush_tolerance(tmp_path):
    anaktoron = tmp_path / "anaktoron"
    _make_chroma_db(anaktoron, embedding_count=2001, sync_threshold=1)

    result = hnsw_capacity_status(str(anaktoron), "mnemion_drawers")

    assert result["status"] == "diverged"
    assert result["diverged"] is True
    assert result["divergence"] == 2001


def test_hnsw_capacity_status_scales_tolerance_with_sync_threshold(tmp_path):
    anaktoron = tmp_path / "anaktoron"
    _make_chroma_db(anaktoron, embedding_count=50_050, sync_threshold=50_000)
    _write_hnsw_pickle(anaktoron, "segment-a", count=0)

    result = hnsw_capacity_status(str(anaktoron), "mnemion_drawers")

    assert result["status"] == "ok"
    assert result["diverged"] is False
    assert result["sync_threshold"] == 50_000
    assert result["divergence_threshold"] == 100_000


def test_read_sync_threshold_falls_back_to_collection_config_json(tmp_path):
    anaktoron = tmp_path / "anaktoron"
    anaktoron.mkdir()
    with sqlite3.connect(anaktoron / "chroma.sqlite3") as conn:
        conn.execute("CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT, config_json_str TEXT)")
        conn.execute(
            "INSERT INTO collections VALUES "
            "('collection-a', 'mnemion_drawers', "
            "'{\"hnsw_configuration\":{\"sync_threshold\":12345}}')"
        )

    assert _read_sync_threshold(str(anaktoron), "mnemion_drawers") == 12345


def test_safe_persistent_data_unpickler_rejects_unexpected_classes(tmp_path):
    payload = tmp_path / "index_metadata.pickle"
    with open(payload, "wb") as f:
        pickle.dump(_DisallowedPickleClass(), f)

    with pytest.raises(pickle.UnpicklingError):
        _SafePersistentDataUnpickler.load(str(payload))


def test_stale_hnsw_scan_and_quarantine_are_conservative(tmp_path):
    anaktoron = tmp_path / "anaktoron"
    db = _make_chroma_db(anaktoron)
    stale_time = db.stat().st_mtime - 1000

    healthy = anaktoron / "healthy-segment"
    healthy.mkdir()
    (healthy / "data_level0.bin").write_bytes(b"data")
    _write_hnsw_pickle(anaktoron, "healthy-segment", count=1)

    corrupt = anaktoron / "corrupt-segment"
    corrupt.mkdir()
    (corrupt / "data_level0.bin").write_bytes(b"data")
    (corrupt / "index_metadata.pickle").write_bytes(b"bad")

    for segment in (healthy, corrupt):
        os.utime(segment / "data_level0.bin", (stale_time, stale_time))

    findings = scan_stale_hnsw(str(anaktoron), stale_seconds=300)
    by_id = {Path(item["path"]).name: item for item in findings}

    assert by_id["healthy-segment"]["would_quarantine"] is False
    assert by_id["corrupt-segment"]["would_quarantine"] is True

    dry_run = quarantine_stale_hnsw(str(anaktoron), stale_seconds=300, dry_run=True)
    assert dry_run == [str(corrupt)]
    assert healthy.is_dir()
    assert corrupt.is_dir()

    moved = quarantine_stale_hnsw(str(anaktoron), stale_seconds=300, dry_run=False)
    assert len(moved) == 1
    assert healthy.is_dir()
    assert not corrupt.exists()
    assert Path(moved[0]).is_dir()


def test_pin_hnsw_threads_is_best_effort():
    class FakeCollection:
        def __init__(self):
            self.calls = []

        def modify(self, **kwargs):
            self.calls.append(kwargs)

    fake = FakeCollection()

    _pin_hnsw_threads(fake)

    assert isinstance(fake.calls, list)
