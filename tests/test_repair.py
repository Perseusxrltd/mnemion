import sqlite3
from pathlib import Path

import pytest

from mnemion.config import DRAWER_HNSW_METADATA
from mnemion.repair import (
    MAX_SEQ_ID_SANITY_THRESHOLD,
    MaxSeqIdVerificationError,
    check_extraction_safety,
    prune_corrupt,
    rebuild_index,
    repair_max_seq_id,
    status,
    TruncationDetected,
)


def _init_max_seq_db(path):
    path.mkdir(parents=True, exist_ok=True)
    db_path = path / "chroma.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE segments (id TEXT PRIMARY KEY, collection TEXT, scope TEXT)")
        conn.execute("CREATE TABLE embeddings (id TEXT, segment_id TEXT, seq_id INTEGER)")
        conn.execute("CREATE TABLE max_seq_id (segment_id TEXT PRIMARY KEY, seq_id)")
        conn.execute("INSERT INTO collections VALUES ('c1', 'mnemion_drawers')")
        conn.execute("INSERT INTO segments VALUES ('segA', 'c1', 'METADATA')")
        conn.execute("INSERT INTO segments VALUES ('segB', 'c1', 'VECTOR')")
        conn.executemany(
            "INSERT INTO embeddings VALUES (?, ?, ?)",
            [("a1", "segA", 10), ("a2", "segA", 15), ("b1", "segB", 12)],
        )
        conn.execute(
            "INSERT INTO max_seq_id VALUES ('segA', ?)", (MAX_SEQ_ID_SANITY_THRESHOLD + 1,)
        )
        conn.execute("INSERT INTO max_seq_id VALUES ('segB', 12)")
        conn.commit()
    return db_path


class _FakeCollection:
    def __init__(self, client, name, ids=None, docs=None, metas=None, fail_upsert=False):
        self.client = client
        self.name = name
        self.ids = list(ids or [])
        self.docs = list(docs or [])
        self.metas = list(metas or [])
        self.metadata = {}
        self.fail_upsert = fail_upsert
        self.deleted_ids = []

    def count(self):
        return len(self.ids)

    def get(self, ids=None, include=None, limit=None, offset=0, where=None):
        if ids is not None:
            keep = [i for i, did in enumerate(self.ids) if did in ids]
        else:
            end = None if limit is None else offset + limit
            keep = list(range(offset, min(end or len(self.ids), len(self.ids))))
        out = {"ids": [self.ids[i] for i in keep]}
        if include and "documents" in include:
            out["documents"] = [self.docs[i] for i in keep]
        if include and "metadatas" in include:
            out["metadatas"] = [self.metas[i] for i in keep]
        return out

    def upsert(self, ids, documents, metadatas):
        if self.fail_upsert:
            raise RuntimeError("simulated upsert failure")
        self.ids.extend(ids)
        self.docs.extend(documents)
        self.metas.extend(metadatas)

    def delete(self, ids):
        for did in ids:
            if did == "fail_delete":
                raise RuntimeError("simulated delete failure")
        self.deleted_ids.extend(ids)
        keep = [i for i, did in enumerate(self.ids) if did not in set(ids)]
        self.ids = [self.ids[i] for i in keep]
        self.docs = [self.docs[i] for i in keep]
        self.metas = [self.metas[i] for i in keep]

    def modify(self, name=None, metadata=None, configuration=None):
        if metadata is not None:
            self.metadata = metadata
        if name:
            old = self.name
            self.name = name
            self.client.collections.pop(old, None)
            self.client.collections[name] = self


class _FakeClient:
    def __init__(self, original, fail_temp_upsert=False):
        self.collections = {"mnemion_drawers": original}
        original.client = self
        self.fail_temp_upsert = fail_temp_upsert

    def get_collection(self, name):
        return self.collections[name]

    def create_collection(self, name, metadata=None):
        col = _FakeCollection(self, name, fail_upsert=self.fail_temp_upsert)
        col.metadata = metadata or {}
        self.collections[name] = col
        return col

    def delete_collection(self, name):
        self.collections.pop(name, None)


def test_repair_max_seq_id_dry_run_does_not_mutate(tmp_path):
    db_path = _init_max_seq_db(tmp_path)

    result = repair_max_seq_id(str(tmp_path), dry_run=True)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT seq_id FROM max_seq_id WHERE segment_id = 'segA'").fetchone()
    assert result["dry_run"] is True
    assert result["before"] == {"segA": MAX_SEQ_ID_SANITY_THRESHOLD + 1}
    assert row[0] == MAX_SEQ_ID_SANITY_THRESHOLD + 1


def test_repair_max_seq_id_repairs_poisoned_rows_and_creates_backup(tmp_path):
    db_path = _init_max_seq_db(tmp_path)

    result = repair_max_seq_id(str(tmp_path), assume_yes=True)

    with sqlite3.connect(db_path) as conn:
        rows = dict(conn.execute("SELECT segment_id, seq_id FROM max_seq_id").fetchall())
    assert rows["segA"] == 15
    assert rows["segB"] == 12
    assert result["segment_repaired"] == ["segA"]
    assert result["backup"]
    assert Path(result["backup"]).exists()


def test_repair_max_seq_id_ignores_unrelated_collection_by_default(tmp_path):
    db_path = _init_max_seq_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO collections VALUES ('c2', 'other_collection')")
        conn.execute("INSERT INTO segments VALUES ('segOther', 'c2', 'VECTOR')")
        conn.execute("INSERT INTO embeddings VALUES ('o1', 'segOther', 99)")
        conn.execute(
            "INSERT INTO max_seq_id VALUES ('segOther', ?)",
            (MAX_SEQ_ID_SANITY_THRESHOLD + 9,),
        )
        conn.commit()

    result = repair_max_seq_id(str(tmp_path), assume_yes=True, backup=False)

    with sqlite3.connect(db_path) as conn:
        rows = dict(conn.execute("SELECT segment_id, seq_id FROM max_seq_id").fetchall())
    assert result["segment_repaired"] == ["segA"]
    assert rows["segA"] == 15
    assert rows["segOther"] == MAX_SEQ_ID_SANITY_THRESHOLD + 9


def test_repair_max_seq_id_all_collections_repairs_unrelated_collection(tmp_path):
    db_path = _init_max_seq_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO collections VALUES ('c2', 'other_collection')")
        conn.execute("INSERT INTO segments VALUES ('segOther', 'c2', 'VECTOR')")
        conn.execute("INSERT INTO embeddings VALUES ('o1', 'segOther', 99)")
        conn.execute(
            "INSERT INTO max_seq_id VALUES ('segOther', ?)",
            (MAX_SEQ_ID_SANITY_THRESHOLD + 9,),
        )
        conn.commit()

    result = repair_max_seq_id(str(tmp_path), assume_yes=True, backup=False, all_collections=True)

    with sqlite3.connect(db_path) as conn:
        rows = dict(conn.execute("SELECT segment_id, seq_id FROM max_seq_id").fetchall())
    assert set(result["segment_repaired"]) == {"segA", "segOther"}
    assert rows["segA"] == 15
    assert rows["segOther"] == 99


def test_repair_max_seq_id_segment_filter(tmp_path):
    db_path = _init_max_seq_db(tmp_path)

    result = repair_max_seq_id(str(tmp_path), segment="segB", assume_yes=True)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT seq_id FROM max_seq_id WHERE segment_id = 'segA'").fetchone()
    assert result["segment_repaired"] == []
    assert row[0] == MAX_SEQ_ID_SANITY_THRESHOLD + 1


def test_repair_max_seq_id_post_verification_fails_loudly(tmp_path):
    db_path = _init_max_seq_db(tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE embeddings SET seq_id = ?", (MAX_SEQ_ID_SANITY_THRESHOLD + 2,))
        conn.commit()

    with pytest.raises(MaxSeqIdVerificationError):
        repair_max_seq_id(str(tmp_path), assume_yes=True, backup=False)


def test_extraction_safety_aborts_when_sqlite_has_more_drawers(tmp_path):
    db_path = tmp_path / "chroma.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE segments (id TEXT PRIMARY KEY, collection TEXT)")
        conn.execute("CREATE TABLE embeddings (id TEXT, segment_id TEXT)")
        conn.execute("INSERT INTO collections VALUES ('c1', 'mnemion_drawers')")
        conn.execute("INSERT INTO segments VALUES ('segA', 'c1')")
        conn.executemany(
            "INSERT INTO embeddings VALUES (?, 'segA')",
            [(f"id{i}",) for i in range(3)],
        )
        conn.commit()

    with pytest.raises(TruncationDetected):
        check_extraction_safety(str(tmp_path), extracted=2)


def test_repair_status_returns_health_shape_for_missing_anaktoron(tmp_path):
    result = status(str(tmp_path / "missing"))

    assert result["vector_disabled"] is False
    assert result["drawers"]["status"] == "unknown"
    assert result["repair_command"] == "mnemion repair --mode status"


def test_rebuild_upsert_failure_preserves_original_collection(monkeypatch, tmp_path):
    original = _FakeCollection(
        None,
        "mnemion_drawers",
        ids=["a", "b"],
        docs=["alpha", "beta"],
        metas=[{"wing": "w", "room": "r"}, {"wing": "w", "room": "s"}],
    )
    client = _FakeClient(original, fail_temp_upsert=True)
    monkeypatch.setattr("mnemion.chroma_compat.make_persistent_client", lambda _path: client)
    monkeypatch.setattr("mnemion.repair.sqlite_embedding_count", lambda _path, _name: 2)

    result = rebuild_index(str(tmp_path), backup=False)

    assert result["aborted"] is True
    assert "upsert" in result["reason"]
    assert client.get_collection("mnemion_drawers").count() == 2
    assert client.get_collection("mnemion_drawers").ids == ["a", "b"]


def test_rebuild_success_verifies_count_and_hnsw_metadata(monkeypatch, tmp_path):
    original = _FakeCollection(
        None,
        "mnemion_drawers",
        ids=["a", "b"],
        docs=["alpha", "beta"],
        metas=[{"wing": "w", "room": "r"}, {"wing": "w", "room": "s"}],
    )
    client = _FakeClient(original)
    monkeypatch.setattr("mnemion.chroma_compat.make_persistent_client", lambda _path: client)
    monkeypatch.setattr("mnemion.repair.sqlite_embedding_count", lambda _path, _name: 2)
    monkeypatch.setattr(
        "mnemion.repair.verify_hnsw_metadata", lambda col: col.metadata == DRAWER_HNSW_METADATA
    )

    result = rebuild_index(str(tmp_path), backup=False)

    assert result["aborted"] is False
    assert result["rebuilt"] == 2
    assert result["final_count"] == 2
    assert client.get_collection("mnemion_drawers").metadata == DRAWER_HNSW_METADATA


def _init_prune_state(root: Path):
    anaktoron = root / "anaktoron"
    anaktoron.mkdir()
    (anaktoron / "corrupt_ids.txt").write_text("bad1\nfail_delete\n", encoding="utf-8")
    kg_path = root / "knowledge_graph.sqlite3"
    from mnemion.knowledge_graph import KnowledgeGraph
    from mnemion.trust_lifecycle import DrawerTrust

    KnowledgeGraph(db_path=str(kg_path))
    trust = DrawerTrust(db_path=str(kg_path))
    with sqlite3.connect(kg_path) as conn:
        conn.executemany(
            "INSERT INTO drawers_fts (drawer_id, content, wing, room) VALUES (?, ?, ?, ?)",
            [
                ("bad1", "bad content", "w", "r"),
                ("fail_delete", "keep content", "w", "r"),
            ],
        )
        conn.commit()
    trust.create("bad1", "w", "r")
    trust.create("fail_delete", "w", "r")
    return anaktoron, kg_path


def test_prune_removes_fts_and_marks_trust_historical(monkeypatch, tmp_path):
    anaktoron, kg_path = _init_prune_state(tmp_path)
    col = _FakeCollection(None, "mnemion_drawers", ids=["bad1"], docs=["bad"], metas=[{}])
    client = _FakeClient(col)
    monkeypatch.setattr("mnemion.chroma_compat.make_persistent_client", lambda _path: client)

    result = prune_corrupt(str(anaktoron), assume_yes=True)

    with sqlite3.connect(kg_path) as conn:
        fts_rows = conn.execute("SELECT drawer_id FROM drawers_fts").fetchall()
        statuses = dict(conn.execute("SELECT drawer_id, status FROM drawer_trust").fetchall())
    assert result["deleted_from_chroma"] == 1
    assert result["removed_from_fts"] == 1
    assert result["trust_marked_historical"] == 1
    assert ("bad1",) not in fts_rows
    assert statuses["bad1"] == "historical"


def test_prune_failed_chroma_delete_does_not_touch_fts_or_trust(monkeypatch, tmp_path):
    anaktoron, kg_path = _init_prune_state(tmp_path)
    col = _FakeCollection(
        None,
        "mnemion_drawers",
        ids=["bad1", "fail_delete"],
        docs=["bad", "keep"],
        metas=[{}, {}],
    )
    client = _FakeClient(col)
    monkeypatch.setattr("mnemion.chroma_compat.make_persistent_client", lambda _path: client)

    result = prune_corrupt(str(anaktoron), assume_yes=True)

    with sqlite3.connect(kg_path) as conn:
        fts = dict(conn.execute("SELECT drawer_id, content FROM drawers_fts").fetchall())
        statuses = dict(conn.execute("SELECT drawer_id, status FROM drawer_trust").fetchall())
    assert result["failed"] == ["fail_delete"]
    assert "fail_delete" in fts
    assert statuses["fail_delete"] == "current"


def test_prune_dry_run_mutates_nothing(tmp_path):
    anaktoron, kg_path = _init_prune_state(tmp_path)

    result = prune_corrupt(str(anaktoron), assume_yes=False)

    with sqlite3.connect(kg_path) as conn:
        fts_count = conn.execute("SELECT COUNT(*) FROM drawers_fts").fetchone()[0]
        current_count = conn.execute(
            "SELECT COUNT(*) FROM drawer_trust WHERE status='current'"
        ).fetchone()[0]
    assert result["dry_run"] is True
    assert fts_count == 2
    assert current_count == 2
