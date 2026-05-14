import sqlite3

from mnemion.sources.store import SourceStore


def test_source_store_creates_required_tables(tmp_path):
    db_path = tmp_path / "knowledge_graph.sqlite3"

    SourceStore(db_path=db_path, source_path=tmp_path / "sources")

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
            )
        }
    finally:
        conn.close()

    assert "raw_sources" in tables
    assert "source_chunks" in tables
    assert "source_chunks_fts" in tables


def test_add_source_is_idempotent_by_content_hash(tmp_path):
    source_file = tmp_path / "notes.md"
    source_file.write_text(
        "# Hybrid Retrieval\n\nHybrid retrieval combines lexical and vector search.\n"
    )
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")

    first = store.add_path(source_file, privacy_class="internal")
    second = store.add_path(source_file, privacy_class="internal")

    assert first["source_id"] == second["source_id"]
    assert second["status"] == "existing"
    assert store.stats()["sources"] == 1
    assert store.stats()["chunks"] >= 1


def test_source_rows_store_privacy_and_raw_text_paths(tmp_path):
    source_file = tmp_path / "private.txt"
    source_file.write_text("Private source evidence about Mnemion source vaults.")
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")

    result = store.add_path(source_file, privacy_class="sensitive", title="Private Note")
    row = store.get_source(result["source_id"])

    assert row["privacy_class"] == "sensitive"
    assert row["title"] == "Private Note"
    assert row["raw_text_path"]
    assert (tmp_path / "sources" / "text" / f"{result['source_id']}.txt").exists()
