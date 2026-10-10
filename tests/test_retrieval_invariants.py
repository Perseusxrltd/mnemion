"""Observable retrieval contracts from the October 2026 audit."""

from pathlib import Path

from mnemion.cognitive_graph import CognitiveGraph
from mnemion.hybrid_searcher import HybridSearcher
from mnemion.knowledge_graph import KnowledgeGraph
from mnemion.reconstruction import Reconstructor
from mnemion.trust_lifecycle import DrawerTrust


def test_searcher_sees_first_write_without_restart(anaktoron_path):
    database = str(Path(anaktoron_path).parent / "knowledge_graph.sqlite3")
    KnowledgeGraph(database)
    DrawerTrust(database)
    searcher = HybridSearcher(anaktoron_path, kg_path=database)
    assert searcher.collection is None
    writer = searcher.backend.get_collection(searcher.collection_name, create=True)
    writer.upsert(
        ids=["first"],
        documents=["quartz onboarding decision"],
        metadatas=[{"wing": "team", "room": "decisions"}],
    )
    assert [hit["id"] for hit in searcher.search("quartz onboarding decision")] == ["first"]


def test_confidence_is_applied_before_limit_and_threshold(
    collection, anaktoron_path, tmp_path, monkeypatch
):
    database = str(tmp_path / "ranking.sqlite3")
    KnowledgeGraph(database)
    trust = DrawerTrust(database)
    collection.upsert(
        ids=["low", "high"],
        documents=["quartz uncertain", "quartz confirmed"],
        metadatas=[{"wing": "team", "room": "notes"}] * 2,
    )
    trust.create("low", "team", "notes", confidence=0.05)
    trust.create("high", "team", "notes", confidence=1.0)
    searcher = HybridSearcher(anaktoron_path, kg_path=database)
    monkeypatch.setattr(searcher, "_vector_search", lambda *a, **k: ["low", "high"])
    monkeypatch.setattr(searcher, "_fts_search", lambda *a, **k: [])
    hits = searcher.search("quartz", n_results=1, min_similarity=0.5)
    assert [hit["id"] for hit in hits] == ["high"]
    trust.update_status("high", "quarantined")
    assert not searcher.search("quartz", n_results=1, min_similarity=0.5, include_superseded=True)


def test_graph_evidence_requires_live_source_trust_and_requested_scope(
    collection, anaktoron_path, tmp_path, monkeypatch
):
    database = str(tmp_path / "graph.sqlite3")
    graph = KnowledgeGraph(database)
    trust = DrawerTrust(database)
    collection.upsert(
        ids=["source-b"],
        documents=["Alice joined Team Beta."],
        metadatas=[{"wing": "team_b", "room": "decisions"}],
    )
    trust.create("source-b", "team_b", "decisions")
    graph.add_triple("Alice", "joined", "TeamBeta", source_closet="source-b")
    searcher = HybridSearcher(anaktoron_path, kg_path=database)
    monkeypatch.setattr(searcher, "_vector_search", lambda *a, **k: [])
    monkeypatch.setattr(searcher, "_fts_search", lambda *a, **k: [])
    allowed = searcher.search("Alice", wing="team_b", room="decisions", n_results=1)
    assert len(allowed) == 1
    assert allowed[0]["source_drawer_id"] == "source-b"
    assert not searcher.search("Alice", wing="team_a", n_results=1)
    assert not searcher.search("Alice", room="private", n_results=1)
    trust.update_status("source-b", "quarantined")
    assert not searcher.search("Alice", include_superseded=True)
    trust.update_status("source-b", "current")
    collection.delete(ids=["source-b"])
    assert not searcher.search("Alice")


def test_quarantine_after_consolidation_hides_every_cognitive_read(collection, tmp_path):
    database = str(tmp_path / "cognitive.sqlite3")
    trust = DrawerTrust(database)
    graph = CognitiveGraph(database)
    collection.upsert(
        ids=["decision", "related"],
        documents=[
            "quartz launch is Friday because testing finished.",
            "quartz launch needs a review.",
        ],
        metadatas=[{"wing": "team", "room": "decisions"}] * 2,
    )
    for identifier in ["decision", "related"]:
        trust.create(identifier, "team", "decisions")
    graph.consolidate_collection(collection, trust=trust)
    assert len(Reconstructor(graph, collection).reconstruct("quartz launch")["results"]) == 2
    trust.update_status("decision", "quarantined")
    result = Reconstructor(graph, collection).reconstruct("quartz launch")
    assert [hit["id"] for hit in result["results"]] == ["related"]
    assert graph.units_for_drawer("decision", include_hidden=False) == []
    assert graph.edges_for_drawer("decision", include_hidden=False) == []
    assert all("decision" not in t["drawer_ids"] for t in graph.topic_tunnels())


def test_reconsolidation_replaces_changed_evidence_and_respects_result_budget(collection, tmp_path):
    graph = CognitiveGraph(str(tmp_path / "cognitive.sqlite3"))
    collection.upsert(
        ids=["decision", "related"],
        documents=["quartz launch is Friday.", "quartz launch has a review."],
        metadatas=[{"wing": "team", "room": "decisions"}] * 2,
    )
    graph.consolidate_collection(collection)
    collection.update(ids=["decision"], documents=["quartz launch is Monday."])
    assert graph.consolidate_collection(collection)["drawers_consolidated"] == 1
    units = graph.units_for_drawer("decision")
    assert any("Monday" in unit["text"] for unit in units)
    assert all("Friday" not in unit["text"] for unit in units)
    result = Reconstructor(graph, collection).reconstruct("quartz launch", budget=1)
    assert len(result["results"]) == 1
    assert all(t["drawer_count"] <= 1 for t in result["topic_tunnels"])
    assert Reconstructor(graph, collection).reconstruct("quartz", budget=0)["results"] == []
