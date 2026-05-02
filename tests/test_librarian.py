import sqlite3

from mnemion.trust_lifecycle import DrawerTrust


class _FakeBackend:
    pass


class _FakeSearcher:
    def __init__(self, *_args, **_kwargs):
        pass

    def search(self, *_args, **_kwargs):
        return [{"id": "drawer_candidate", "text": "Old memory says REST is required."}]


class _FakeCollection:
    def __init__(self):
        self.updated = []

    def get(self, ids=None, include=None):
        docs = {
            "drawer_target": "New memory says GraphQL replaced REST.",
            "drawer_candidate": "Old memory says REST is required.",
        }
        return {
            "ids": ids or [],
            "documents": [docs[drawer_id] for drawer_id in ids or []],
            "metadatas": [{"room": "general"} for _ in ids or []],
        }

    def update(self, **kwargs):
        self.updated.append(kwargs)


class _FakeStorageBackend:
    def __init__(self, collection):
        self.collection = collection

    def get_collection(self, *_args, **_kwargs):
        return self.collection


def test_librarian_dry_run_does_not_write_conflicts_or_state(monkeypatch, tmp_path):
    from mnemion import librarian

    home = tmp_path / "home"
    home.mkdir()
    anaktoron = tmp_path / "anaktoron"
    anaktoron.mkdir()
    kg_path = tmp_path / "knowledge_graph.sqlite3"
    state_path = home / ".mnemion" / "librarian_state.json"

    trust = DrawerTrust(str(kg_path))
    trust.create("drawer_target", wing="project", room="general")
    trust.create("drawer_candidate", wing="project", room="general")
    collection = _FakeCollection()

    class _Cfg:
        anaktoron_path = str(anaktoron)
        collection_name = "mnemion_drawers"

    monkeypatch.setattr(librarian, "STATE_FILE", state_path)
    monkeypatch.setattr(librarian, "INTER_REQUEST_SLEEP", 0)
    monkeypatch.setattr("mnemion.config.MnemionConfig", lambda: _Cfg())
    monkeypatch.setattr("mnemion.llm_backend.get_backend", lambda _cfg: _FakeBackend())
    monkeypatch.setattr("mnemion.hybrid_searcher.HybridSearcher", _FakeSearcher)
    monkeypatch.setattr(
        "mnemion.backends.registry.get_backend", lambda **_kwargs: _FakeStorageBackend(collection)
    )
    monkeypatch.setattr(
        "mnemion.contradiction_detector.stage1_check",
        lambda *_args, **_kwargs: {"conflict_type": "contradicts", "confidence": 0.9},
    )
    monkeypatch.setattr(librarian, "_suggest_room", lambda *_args, **_kwargs: "technical")
    monkeypatch.setattr(
        librarian,
        "_extract_kg_triples",
        lambda *_args, **_kwargs: [
            {"subject": "Mnemion", "relation": "uses", "object": "GraphQL"}
        ],
    )

    result = librarian.run_librarian(limit=1, dry_run=True)

    conn = sqlite3.connect(kg_path)
    try:
        conflict_count = conn.execute("SELECT COUNT(*) FROM drawer_conflicts").fetchone()[0]
        triple_count = conn.execute("SELECT COUNT(*) FROM triples").fetchone()[0]
        target = conn.execute(
            "SELECT room, verifications, challenges FROM drawer_trust WHERE drawer_id = ?",
            ("drawer_target",),
        ).fetchone()
    finally:
        conn.close()

    assert result["processed"] == 1
    assert result["contradictions_found"] == 1
    assert conflict_count == 0
    assert triple_count == 0
    assert target == ("general", 0, 0)
    assert collection.updated == []
    assert not state_path.exists()
