"""Durable recovery and projection parity for every legacy ingestion adapter."""

import json
import sqlite3

import pytest

from mnemion.ingestion import LegacyMemoryWriter
from mnemion.trust_lifecycle import DrawerTrust


def test_retry_recovers_vector_only_write_and_does_not_reset_trust(
    collection, tmp_path, monkeypatch
):
    database = tmp_path / "sidecar.sqlite3"
    writer = LegacyMemoryWriter(collection, database)
    metadata = {"wing": "team", "room": "decisions"}
    original = writer._write_indexes

    def sidecar_failure(*args):
        raise sqlite3.OperationalError("injected sidecar interruption")

    monkeypatch.setattr(writer, "_write_indexes", sidecar_failure)
    with pytest.raises(sqlite3.OperationalError):
        writer.save("decision", "quartz reliable save", metadata)
    assert collection.get(ids=["decision"])["ids"] == ["decision"]
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT state FROM drawer_ingest_jobs").fetchone()[0] == "pending"
        assert conn.execute("SELECT COUNT(*) FROM drawers_fts").fetchone()[0] == 0
    monkeypatch.setattr(writer, "_write_indexes", original)
    # A new writer instance stands in for restarting after an interrupted save.
    result = LegacyMemoryWriter(collection, database).save(
        "decision", "quartz reliable save", metadata
    )
    assert result["state"] == "ready"
    assert result["applied_jobs"] == 2
    assert collection.count() == 1
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM drawers_fts").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM drawer_trust_history").fetchone()[0] == 1
        assert all(
            row[0] == "{}" for row in conn.execute("SELECT payload_json FROM drawer_ingest_jobs")
        )
    trust = DrawerTrust(str(database))
    trust.update_status("decision", "quarantined", reason="review")
    writer.save("decision", "quartz reliable save", metadata)
    assert trust.get("decision")["status"] == "quarantined"
    assert trust.create("decision", "team", "decisions")["status"] == "quarantined"
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM drawer_trust_history").fetchone()[0] == 2


def test_remining_replaces_lexical_rows_and_invalidates_old_evidence(collection, tmp_path):
    from mnemion.cognitive_graph import CognitiveGraph
    from mnemion.knowledge_graph import KnowledgeGraph

    database = tmp_path / "sidecar.sqlite3"
    writer = LegacyMemoryWriter(collection, database)
    metadata = {"wing": "team", "room": "decisions"}
    writer.save("decision", "Alice works at OldTeam because she moved.", metadata)
    graph = CognitiveGraph(str(database))
    graph.consolidate_collection(collection)
    kg = KnowledgeGraph(str(database))
    kg.add_triple("Alice", "works_at", "OldTeam", source_closet="decision")
    assert graph.units_for_drawer("decision")
    writer.save("decision", "Alice works at NewTeam.", metadata)
    with sqlite3.connect(database) as conn:
        assert conn.execute(
            "SELECT content FROM drawers_fts WHERE drawer_id='decision'"
        ).fetchall() == [("Alice works at NewTeam.",)]
    assert graph.units_for_drawer("decision") == []
    assert not any(t["current"] for t in kg.query_entity("Alice"))
    assert graph.consolidate_collection(collection)["drawers_consolidated"] == 1


def test_sweeper_populates_lexical_and_trust_and_repeated_runs_are_complete(tmp_path):
    from mnemion.sweeper import sweep

    source = tmp_path / "session.jsonl"
    source.write_text(
        json.dumps(
            {
                "uuid": "message1",
                "session_id": "study",
                "role": "user",
                "content": "quartz ALPHA_739 exact identifier",
            }
        )
        + "\n"
    )
    target = tmp_path / "anaktoron"
    result = sweep(str(source), anaktoron_path=str(target))
    assert result["filed"] == 1
    repeat = sweep(str(source), anaktoron_path=str(target))
    assert repeat["filed"] == 0
    with sqlite3.connect(tmp_path / "knowledge_graph.sqlite3") as conn:
        assert conn.execute("SELECT COUNT(*) FROM drawers_fts").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM drawer_trust").fetchone()[0] == 1
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM drawer_ingest_jobs WHERE state='pending'"
            ).fetchone()[0]
            == 0
        )


def test_mcp_retry_repairs_incomplete_drawer(monkeypatch, config, anaktoron_path, tmp_path):
    from mnemion import mcp_server as mcp
    from mnemion.hybrid_searcher import HybridSearcher

    database = str(tmp_path / "sidecar.sqlite3")
    monkeypatch.setattr(mcp, "_config", config)
    monkeypatch.setattr(mcp, "_client_cache", None)
    monkeypatch.setattr(mcp, "_collection_cache", None)
    monkeypatch.setattr(mcp, "_hybrid", HybridSearcher(anaktoron_path, kg_path=database))
    monkeypatch.setattr(mcp, "_trust", DrawerTrust(database))
    monkeypatch.setattr(mcp._cd, "spawn_detection", lambda *args: None)
    original = LegacyMemoryWriter._write_indexes
    monkeypatch.setattr(
        LegacyMemoryWriter,
        "_write_indexes",
        lambda *args: (_ for _ in ()).throw(sqlite3.OperationalError("interrupted")),
    )
    assert mcp.tool_add_drawer("team", "notes", "quartz recorded choice")["success"] is False
    monkeypatch.setattr(LegacyMemoryWriter, "_write_indexes", original)
    result = mcp.tool_add_drawer("team", "notes", "quartz recorded choice")
    assert result["success"] is True
    assert result["state"] == "ready"
    assert mcp._trust.get(result["drawer_id"]) is not None
    assert len(mcp._hybrid.search("quartz recorded choice")) == 1


def test_deletion_cancels_pending_save_and_cannot_be_replayed(collection, tmp_path, monkeypatch):
    writer = LegacyMemoryWriter(collection, tmp_path / "sidecar.sqlite3")
    original = writer._write_indexes
    monkeypatch.setattr(
        writer,
        "_write_indexes",
        lambda *args: (_ for _ in ()).throw(RuntimeError("Interrupted save")),
    )
    with pytest.raises(RuntimeError):
        writer.save("deleted", "Secret content", {"wing": "team", "room": "notes"})
    monkeypatch.setattr(writer, "_write_indexes", original)
    assert writer.delete("deleted")["state"] == "ready"
    assert writer.recover() == 0
    assert not collection.get(ids=["deleted"])["ids"]
    with pytest.raises(ValueError, match="deleted"):
        writer.save("deleted", "Secret content", {"wing": "team", "room": "notes"})
    with sqlite3.connect(writer.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM drawers_fts").fetchone()[0] == 0
        assert all(
            row[0] == "{}" for row in conn.execute("SELECT payload_json FROM drawer_ingest_jobs")
        )


def test_failed_vector_deletion_hides_cognitive_and_search_until_recovery(
    collection, tmp_path, monkeypatch, anaktoron_path
):
    from mnemion.cognitive_graph import CognitiveGraph
    from mnemion.hybrid_searcher import HybridSearcher

    writer = LegacyMemoryWriter(collection, tmp_path / "sidecar.sqlite3")
    writer.save(
        "withdrawn",
        "Alice prefers Postgres because billing requires transactions.",
        {"wing": "team", "room": "notes"},
    )
    graph = CognitiveGraph(writer.db_path)
    graph.consolidate_collection(collection)
    real_collection = writer.collection

    class FailingDelete:
        def delete(self, **kwargs):
            raise RuntimeError("Vector store temporarily unavailable")

    writer.collection = FailingDelete()
    with pytest.raises(RuntimeError):
        writer.delete("withdrawn")
    assert real_collection.get(ids=["withdrawn"])["ids"]
    searcher = HybridSearcher(anaktoron_path, kg_path=writer.db_path)
    assert searcher.search("Alice Postgres", include_superseded=True) == []
    assert graph.search_units("Alice Postgres") == []
    writer.collection = real_collection
    assert writer.recover() == 1
    assert not real_collection.get(ids=["withdrawn"])["ids"]


def test_reconcile_repairs_pre_journal_records_without_resetting_trust(collection, tmp_path):
    metadata = {"wing": "team", "room": "notes"}
    collection.upsert(ids=["legacy"], documents=["Older vector-only source"], metadatas=[metadata])
    writer = LegacyMemoryWriter(collection, tmp_path / "sidecar.sqlite3")
    trust = DrawerTrust(writer.db_path)
    trust.create("legacy", "team", "notes")
    trust.update_status("legacy", "quarantined", reason="Pending review")
    assert writer.reconcile()["reconciled_records"] == 1
    assert trust.get("legacy")["status"] == "quarantined"
    with sqlite3.connect(writer.db_path) as conn:
        assert (
            conn.execute("SELECT content FROM drawers_fts WHERE drawer_id='legacy'").fetchone()[0]
            == "Older vector-only source"
        )
