import pickle
import sqlite3
import builtins

from mnemion.config import DRAWER_HNSW_METADATA
from mnemion.chroma_compat import (
    BLOB_FIX_MARKER,
    VectorStoreUnsafe,
    fix_blob_seq_ids,
    hnsw_capacity_status,
    make_persistent_client,
    sqlite_metadata_summary,
)


def _init_blob_db(path):
    path.mkdir(parents=True, exist_ok=True)
    db_path = path / "chroma.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE embeddings (id TEXT, segment_id TEXT, seq_id)")
        conn.execute("CREATE TABLE max_seq_id (segment_id TEXT PRIMARY KEY, seq_id)")
        conn.execute("INSERT INTO embeddings VALUES ('ok', 'seg1', ?)", ((42).to_bytes(8, "big"),))
        conn.execute("INSERT INTO embeddings VALUES ('sysdb', 'seg1', ?)", (b"\x11\x11abcdef",))
        conn.execute("INSERT INTO max_seq_id VALUES ('seg1', ?)", (b"\x11\x11abcdef",))
        conn.commit()
    return db_path


def test_fix_blob_seq_ids_only_converts_legacy_embedding_rows(tmp_path):
    db_path = _init_blob_db(tmp_path)

    fix_blob_seq_ids(str(tmp_path))

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, seq_id, typeof(seq_id) FROM embeddings ORDER BY id"
        ).fetchall()
        max_row = conn.execute("SELECT seq_id, typeof(seq_id) FROM max_seq_id").fetchone()

    assert rows[0] == ("ok", 42, "integer")
    assert rows[1][0] == "sysdb"
    assert rows[1][1] == b"\x11\x11abcdef"
    assert rows[1][2] == "blob"
    assert max_row == (b"\x11\x11abcdef", "blob")
    assert (tmp_path / BLOB_FIX_MARKER).exists()


def test_fix_blob_seq_ids_marker_prevents_repeated_work(tmp_path):
    db_path = _init_blob_db(tmp_path)
    fix_blob_seq_ids(str(tmp_path))

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO embeddings VALUES ('later', 'seg1', ?)", ((7).to_bytes(8, "big"),)
        )
        conn.commit()

    fix_blob_seq_ids(str(tmp_path))

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT seq_id, typeof(seq_id) FROM embeddings WHERE id = 'later'"
        ).fetchone()
    assert row == ((7).to_bytes(8, "big"), "blob")


def test_fix_blob_seq_ids_fresh_or_missing_db_is_noop(tmp_path):
    fix_blob_seq_ids(str(tmp_path / "missing"))
    assert not (tmp_path / "missing" / BLOB_FIX_MARKER).exists()

    fresh = tmp_path / "fresh"
    fresh.mkdir()
    (fresh / "chroma.sqlite3").write_bytes(b"")
    fix_blob_seq_ids(str(fresh))
    assert not (fresh / BLOB_FIX_MARKER).exists()


def test_drawer_hnsw_metadata_has_bloat_guard_values():
    assert DRAWER_HNSW_METADATA == {
        "hnsw:space": "cosine",
        "hnsw:num_threads": 1,
        "hnsw:batch_size": 50_000,
        "hnsw:sync_threshold": 50_000,
    }


def test_hnsw_capacity_status_flags_divergence_without_chroma(tmp_path):
    db_path = tmp_path / "chroma.sqlite3"
    segment_id = "11111111-1111-1111-1111-111111111111"
    collection_id = "collection-1"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE segments (id TEXT PRIMARY KEY, collection TEXT, scope TEXT)")
        conn.execute("CREATE TABLE embeddings (id TEXT, segment_id TEXT, seq_id INTEGER)")
        conn.execute("INSERT INTO collections VALUES (?, ?)", (collection_id, "mnemion_drawers"))
        conn.execute("INSERT INTO segments VALUES (?, ?, 'VECTOR')", (segment_id, collection_id))
        conn.executemany(
            "INSERT INTO embeddings VALUES (?, ?, ?)",
            [(f"id{i}", segment_id, i) for i in range(2501)],
        )
        conn.commit()

    segment_dir = tmp_path / segment_id
    segment_dir.mkdir()
    with open(segment_dir / "index_metadata.pickle", "wb") as f:
        pickle.dump({"id_to_label": {"id0": 0}}, f)

    status = hnsw_capacity_status(str(tmp_path), "mnemion_drawers")

    assert status["status"] == "diverged"
    assert status["sqlite_count"] == 2501
    assert status["hnsw_count"] == 1
    assert status["diverged"] is True


def _init_metadata_db(path):
    db_path = path / "chroma.sqlite3"
    segment_id = "segment-1"
    collection_id = "collection-1"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE segments (id TEXT PRIMARY KEY, collection TEXT, scope TEXT)")
        conn.execute(
            "CREATE TABLE embeddings (id INTEGER PRIMARY KEY, segment_id TEXT, seq_id INTEGER)"
        )
        conn.execute(
            "CREATE TABLE embedding_metadata (id INTEGER, key TEXT, string_value TEXT, int_value INTEGER, float_value REAL, bool_value INTEGER)"
        )
        conn.execute("INSERT INTO collections VALUES (?, ?)", (collection_id, "mnemion_drawers"))
        conn.execute("INSERT INTO segments VALUES (?, ?, 'VECTOR')", (segment_id, collection_id))
        conn.executemany(
            "INSERT INTO embeddings VALUES (?, ?, ?)",
            [(1, segment_id, 1), (2, segment_id, 2), (3, segment_id, 3)],
        )
        conn.executemany(
            "INSERT INTO embedding_metadata VALUES (?, ?, ?, NULL, NULL, NULL)",
            [
                (1, "wing", "ops"),
                (1, "room", "repair"),
                (2, "wing", "ops"),
                (2, "room", "repair"),
                (3, "wing", "notes"),
                (3, "room", "planning"),
            ],
        )
        conn.commit()
    return db_path


def test_sqlite_metadata_summary_returns_wing_and_room_counts(tmp_path):
    _init_metadata_db(tmp_path)

    summary = sqlite_metadata_summary(str(tmp_path), "mnemion_drawers")

    assert summary["total_drawers"] == 3
    assert summary["wing_count"] == 2
    assert summary["room_count"] == 2
    assert summary["wings"] == {"ops": 2, "notes": 1}
    assert summary["rooms"] == {"repair": 2, "planning": 1}
    assert summary["metadata_unavailable"] is False


def test_sqlite_metadata_summary_reports_unavailable_when_metadata_missing(tmp_path):
    db_path = tmp_path / "chroma.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT)")
        conn.commit()

    summary = sqlite_metadata_summary(str(tmp_path), "mnemion_drawers")

    assert summary["metadata_unavailable"] is True
    assert summary["metadata_message"]


def test_vector_safe_client_refuses_diverged_store_before_importing_chroma(monkeypatch, tmp_path):
    _init_metadata_db(tmp_path)
    segment_dir = tmp_path / "segment-1"
    segment_dir.mkdir()
    with open(segment_dir / "index_metadata.pickle", "wb") as f:
        pickle.dump({"id_to_label": {}}, f)
    with sqlite3.connect(tmp_path / "chroma.sqlite3") as conn:
        conn.executemany(
            "INSERT INTO embeddings VALUES (?, 'segment-1', ?)",
            [(i, i) for i in range(4, 2505)],
        )
        conn.commit()

    real_import = builtins.__import__

    def fail_chroma_import(name, *args, **kwargs):
        if name == "chromadb" or name.startswith("chromadb."):
            raise AssertionError("chromadb should not be imported for diverged vector-safe open")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_chroma_import)

    try:
        make_persistent_client(str(tmp_path), vector_safe=True, collection_name="mnemion_drawers")
    except VectorStoreUnsafe as exc:
        assert exc.health["diverged"] is True
    else:
        raise AssertionError("expected VectorStoreUnsafe")
