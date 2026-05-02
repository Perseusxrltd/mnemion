import json
import pickle
import sqlite3

from mnemion.chroma_compat import (
    fix_blob_seq_ids,
    fix_legacy_collection_config_json,
    fix_legacy_hnsw_metadata_pickle,
)
from mnemion.repair import (
    MAX_SEQ_ID_SANITY_THRESHOLD,
    repair_max_seq_id,
    scan,
    scan_max_seq_id,
    status,
)


def _make_db(tmp_path):
    anaktoron = tmp_path / "anaktoron"
    anaktoron.mkdir()
    db = anaktoron / "chroma.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE max_seq_id (segment_id TEXT PRIMARY KEY, seq_id INTEGER)")
        conn.execute("CREATE TABLE embeddings (segment_id TEXT, seq_id INTEGER)")
    return anaktoron, db


def test_chroma_compat_does_not_rewrite_max_seq_id(tmp_path):
    anaktoron = tmp_path / "anaktoron"
    anaktoron.mkdir()
    db = anaktoron / "chroma.sqlite3"
    blob = (42).to_bytes(8, byteorder="big")
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE embeddings (seq_id BLOB)")
        conn.execute("CREATE TABLE max_seq_id (seq_id BLOB)")
        conn.execute("INSERT INTO embeddings VALUES (?)", (blob,))
        conn.execute("INSERT INTO max_seq_id VALUES (?)", (blob,))

    fix_blob_seq_ids(str(anaktoron))

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT typeof(seq_id), seq_id FROM embeddings").fetchone() == (
            "integer",
            42,
        )
        assert conn.execute("SELECT typeof(seq_id) FROM max_seq_id").fetchone()[0] == "blob"


def test_chroma_compat_adds_missing_collection_config_type(tmp_path):
    anaktoron = tmp_path / "anaktoron"
    anaktoron.mkdir()
    db = anaktoron / "chroma.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT, config_json_str TEXT)"
        )
        conn.execute("INSERT INTO collections VALUES ('one', 'drawers', '{}')")
        conn.execute(
            "INSERT INTO collections VALUES "
            "('two', 'cosine_drawers', '{\"hnsw_configuration\":{\"space\":\"cosine\"}}')"
        )

    fix_legacy_collection_config_json(str(anaktoron))

    with sqlite3.connect(db) as conn:
        rows = dict(conn.execute("SELECT name, config_json_str FROM collections").fetchall())
    assert json.loads(rows["drawers"]) == {"_type": "CollectionConfigurationInternal"}
    cosine_config = json.loads(rows["cosine_drawers"])
    assert cosine_config["_type"] == "CollectionConfigurationInternal"
    assert cosine_config["hnsw_configuration"]["space"] == "cosine"


def test_chroma_compat_converts_legacy_hnsw_metadata_pickle(tmp_path):
    anaktoron = tmp_path / "anaktoron"
    segment = anaktoron / "segment-a"
    segment.mkdir(parents=True)
    with sqlite3.connect(anaktoron / "chroma.sqlite3") as conn:
        conn.execute("CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT, dimension INTEGER)")
        conn.execute("CREATE TABLE segments (id TEXT PRIMARY KEY, collection TEXT)")
        conn.execute("INSERT INTO collections VALUES ('collection-a', 'drawers', 384)")
        conn.execute("INSERT INTO segments VALUES ('segment-a', 'collection-a')")
    metadata = segment / "index_metadata.pickle"
    legacy_payload = {
        "dimensionality": None,
        "total_elements_added": 2,
        "max_seq_id": 9,
        "id_to_label": {"drawer_a": 1},
        "label_to_id": {1: "drawer_a"},
        "id_to_seq_id": {"drawer_a": 9},
    }
    with open(metadata, "wb") as f:
        pickle.dump(legacy_payload, f)

    fix_legacy_hnsw_metadata_pickle(str(anaktoron))

    with open(metadata, "rb") as f:
        repaired = pickle.load(f)
    assert repaired.dimensionality == 384
    assert repaired.total_elements_added == 2
    assert repaired.max_seq_id == 9
    assert repaired.id_to_label == {"drawer_a": 1}
    assert (segment / "index_metadata.pickle.legacy-dict.bak").exists()


def test_max_seq_id_repair_detects_and_restores_from_embeddings(tmp_path):
    anaktoron, db = _make_db(tmp_path)
    poisoned = MAX_SEQ_ID_SANITY_THRESHOLD + 100
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO max_seq_id VALUES ('seg-a', ?)", (poisoned,))
        conn.execute("INSERT INTO embeddings VALUES ('seg-a', 17)")
        conn.execute("INSERT INTO embeddings VALUES ('seg-a', 23)")

    issues = scan_max_seq_id(str(anaktoron))
    assert len(issues) == 1
    assert issues[0].replacement == 23

    dry_run = repair_max_seq_id(str(anaktoron), dry_run=True)
    assert dry_run["would_update"] == 1
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT seq_id FROM max_seq_id").fetchone()[0] == poisoned

    repaired = repair_max_seq_id(str(anaktoron), dry_run=False)
    assert repaired["updated"] == 1
    assert repaired["backup_path"]
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT seq_id FROM max_seq_id").fetchone()[0] == 23


def test_repair_status_preserves_max_seq_id_keys_and_adds_hnsw(tmp_path):
    anaktoron, db = _make_db(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE segments (id TEXT PRIMARY KEY, collection TEXT, scope TEXT)")
        conn.execute("INSERT INTO collections VALUES ('collection-a', 'mnemion_drawers')")
        conn.execute("INSERT INTO segments VALUES ('segment-a', 'collection-a', 'VECTOR')")

    result = status(str(anaktoron), collection_name="mnemion_drawers")

    assert result["anaktoron_path"] == str(anaktoron)
    assert result["sqlite_exists"] is True
    assert result["max_seq_id_issues"] == []
    assert result["hnsw_status"]["collection_name"] == "mnemion_drawers"
    assert result["hnsw_status"]["segment_id"] == "segment-a"
    assert result["stale_hnsw_segments"] == []


def test_repair_scan_is_read_only_for_stale_hnsw_segments(tmp_path):
    anaktoron, db = _make_db(tmp_path)
    segment = anaktoron / "corrupt-segment"
    segment.mkdir()
    hnsw = segment / "data_level0.bin"
    hnsw.write_bytes(b"data")
    (segment / "index_metadata.pickle").write_bytes(b"bad")
    old = db.stat().st_mtime - 1000
    import os

    os.utime(hnsw, (old, old))

    result = scan(str(anaktoron), collection_name="mnemion_drawers")

    assert result["dry_run"] is True
    assert result["would_quarantine_count"] == 1
    assert segment.is_dir()
