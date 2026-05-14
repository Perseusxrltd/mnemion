from mnemion.sources.store import SourceStore
from mnemion.wiki.compiler import WikiCompiler
from mnemion.wiki.context_pack import build_context_pack


def test_context_pack_returns_wiki_pages_and_source_chunks(tmp_path):
    source_file = tmp_path / "retrieval.md"
    source_file.write_text("# Retrieval\n\nHybrid retrieval uses FTS5 and Chroma with RRF.")
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")
    store.add_path(source_file)
    WikiCompiler(db_path=tmp_path / "kg.sqlite3", wiki_path=tmp_path / "wiki").compile_all(
        apply=True
    )

    pack = build_context_pack(
        "hybrid retrieval",
        db_path=tmp_path / "kg.sqlite3",
        wiki_path=tmp_path / "wiki",
        token_budget=400,
    )

    assert pack["query"] == "hybrid retrieval"
    assert pack["wiki_pages"]
    assert pack["source_chunks"]
    assert sum(len(chunk["text"]) for chunk in pack["source_chunks"]) <= 1600
    assert all(chunk["untrusted_source_content"] is True for chunk in pack["source_chunks"])


def test_context_pack_excludes_live_quarantined_wiki_and_source_chunks(tmp_path):
    import sqlite3

    source_file = tmp_path / "quarantine.md"
    source_file.write_text("Quarantined hybrid retrieval evidence must be hidden.")
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")
    source = store.add_path(source_file)
    WikiCompiler(db_path=tmp_path / "kg.sqlite3", wiki_path=tmp_path / "wiki").compile_all(
        apply=True
    )
    with sqlite3.connect(tmp_path / "kg.sqlite3") as conn:
        conn.execute(
            "UPDATE raw_sources SET trust_status = 'quarantined' WHERE id = ?",
            (source["source_id"],),
        )
        conn.commit()

    pack = build_context_pack(
        "hybrid retrieval quarantined",
        db_path=tmp_path / "kg.sqlite3",
        wiki_path=tmp_path / "wiki",
        token_budget=400,
    )

    assert not any(source["source_id"] in page["path"] for page in pack["wiki_pages"])
    assert not any(chunk["source_id"] == source["source_id"] for chunk in pack["source_chunks"])
    assert any("quarantined wiki page excluded" in warning for warning in pack["warnings"])
