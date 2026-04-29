"""
test_searcher.py — Tests for the programmatic search_memories API.

Tests the library-facing search interface (not the CLI print variant).
"""

from mnemion.searcher import search_memories


class TestSearchMemories:
    def test_basic_search(self, anaktoron_path, seeded_collection):
        result = search_memories("JWT authentication", anaktoron_path)
        assert "results" in result
        assert len(result["results"]) > 0
        assert result["query"] == "JWT authentication"

    def test_wing_filter(self, anaktoron_path, seeded_collection):
        result = search_memories("planning", anaktoron_path, wing="notes")
        assert all(r["wing"] == "notes" for r in result["results"])

    def test_room_filter(self, anaktoron_path, seeded_collection):
        result = search_memories("database", anaktoron_path, room="backend")
        assert all(r["room"] == "backend" for r in result["results"])

    def test_wing_and_room_filter(self, anaktoron_path, seeded_collection):
        result = search_memories("code", anaktoron_path, wing="project", room="frontend")
        assert all(r["wing"] == "project" and r["room"] == "frontend" for r in result["results"])

    def test_n_results_limit(self, anaktoron_path, seeded_collection):
        result = search_memories("code", anaktoron_path, n_results=2)
        assert len(result["results"]) <= 2

    def test_no_anaktoron_returns_error(self, tmp_path):
        result = search_memories("anything", str(tmp_path / "missing"))
        assert "error" in result

    def test_result_fields(self, anaktoron_path, seeded_collection):
        result = search_memories("authentication", anaktoron_path)
        hit = result["results"][0]
        assert "text" in hit
        assert "wing" in hit
        assert "room" in hit
        assert "source_file" in hit
        assert "similarity" in hit
        assert isinstance(hit["similarity"], float)


def test_hybrid_searcher_vector_safe_fallback_uses_fts(monkeypatch, tmp_path):
    from mnemion.chroma_compat import VectorStoreUnsafe
    from mnemion.hybrid_searcher import HybridSearcher
    from mnemion.knowledge_graph import KnowledgeGraph

    anaktoron = tmp_path / "anaktoron"
    anaktoron.mkdir()
    kg_path = tmp_path / "knowledge_graph.sqlite3"
    KnowledgeGraph(db_path=str(kg_path))
    with __import__("sqlite3").connect(kg_path) as conn:
        conn.execute(
            "INSERT INTO drawers_fts (drawer_id, content, wing, room) VALUES (?, ?, ?, ?)",
            ("drawer_fallback", "repair fallback lexical result", "ops", "repair"),
        )
        conn.commit()

    def refuse_open(*args, **kwargs):
        raise VectorStoreUnsafe({"status": "diverged", "message": "unsafe vector store"})

    monkeypatch.setattr("mnemion.hybrid_searcher.make_persistent_client", refuse_open)

    searcher = HybridSearcher(anaktoron_path=str(anaktoron), kg_path=str(kg_path))
    hits = searcher.search("repair fallback", n_results=1)

    assert searcher.vector_disabled is True
    assert hits[0]["id"] == "drawer_fallback"
    assert hits[0]["vector_disabled"] is True
