import json
import sqlite3

from mnemion.sources.store import SourceStore
from mnemion.wiki.compiler import WikiCompiler


def test_wiki_compile_all_apply_creates_source_index_log_and_claims(tmp_path):
    source_file = tmp_path / "README.md"
    source_file.write_text("# Mnemion\n\nHybrid retrieval combines lexical and semantic retrieval.")
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")
    source = store.add_path(source_file, privacy_class="private")
    compiler = WikiCompiler(db_path=tmp_path / "kg.sqlite3", wiki_path=tmp_path / "wiki")

    result = compiler.compile_all(apply=True)

    assert result["status"] == "applied"
    assert (tmp_path / "wiki" / "index.md").exists()
    assert (tmp_path / "wiki" / "log.md").exists()
    source_page_path = tmp_path / "wiki" / "sources" / f"readme-{source['source_id']}.md"
    assert source_page_path.exists()
    assert result["pages_written"] >= 3

    source_page = source_page_path.read_text(encoding="utf-8")
    assert f"source:{source['source_id']}" in source_page
    assert "<!-- claim:" in source_page

    conn = sqlite3.connect(tmp_path / "kg.sqlite3")
    try:
        claim_count = conn.execute("SELECT COUNT(*) FROM wiki_claims").fetchone()[0]
        page_count = conn.execute("SELECT COUNT(*) FROM wiki_pages").fetchone()[0]
    finally:
        conn.close()
    assert claim_count >= 1
    assert page_count >= 3


def test_wiki_compile_review_writes_diff_without_final_page(tmp_path):
    source_file = tmp_path / "notes.txt"
    source_file.write_text("Trust lifecycle tracks current and contested memories.")
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")
    source = store.add_path(source_file)
    compiler = WikiCompiler(
        db_path=tmp_path / "kg.sqlite3",
        wiki_path=tmp_path / "wiki",
        diffs_path=tmp_path / "wiki_diffs",
    )

    result = compiler.compile_source(source["source_id"], review=True)

    assert result["status"] == "review"
    assert result["job_id"].startswith("wjob_")
    assert not (tmp_path / "wiki" / "sources" / f"notes-{source['source_id']}.md").exists()
    assert list((tmp_path / "wiki_diffs" / result["job_id"]).glob("*.diff"))


def test_wiki_apply_job_updates_page_and_claim_registry(tmp_path):
    source_file = tmp_path / "registry.txt"
    source_file.write_text("Review apply must update wiki page and claim registries.")
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")
    store.add_path(source_file)
    compiler = WikiCompiler(
        db_path=tmp_path / "kg.sqlite3",
        wiki_path=tmp_path / "wiki",
        diffs_path=tmp_path / "wiki_diffs",
    )
    review = compiler.compile_all(review=True)

    compiler.apply_job(review["job_id"])

    conn = sqlite3.connect(tmp_path / "kg.sqlite3")
    try:
        page_count = conn.execute("SELECT COUNT(*) FROM wiki_pages").fetchone()[0]
        claim_count = conn.execute("SELECT COUNT(*) FROM wiki_claims").fetchone()[0]
    finally:
        conn.close()

    assert page_count >= 3
    assert claim_count >= 1


def test_wiki_apply_job_preserves_manual_sections(tmp_path):
    source_file = tmp_path / "manual.md"
    source_file.write_text("Manual sections must be preserved during recompilation.")
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")
    source = store.add_path(source_file)
    compiler = WikiCompiler(db_path=tmp_path / "kg.sqlite3", wiki_path=tmp_path / "wiki")
    compiler.compile_source(source["source_id"], apply=True)
    page = tmp_path / "wiki" / "sources" / f"manual-{source['source_id']}.md"
    page.write_text(page.read_text(encoding="utf-8") + "\n## Manual Notes\n\nDo not delete.\n")

    compiler.compile_source(source["source_id"], apply=True)

    assert "## Manual Notes" in page.read_text(encoding="utf-8")


def test_manifest_records_managed_pages(tmp_path):
    source_file = tmp_path / "manifest.txt"
    source_file.write_text("Manifest tracks compiled wiki pages.")
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")
    store.add_path(source_file)
    compiler = WikiCompiler(db_path=tmp_path / "kg.sqlite3", wiki_path=tmp_path / "wiki")

    compiler.compile_all(apply=True)
    manifest = json.loads((tmp_path / "wiki" / ".mnemion-wiki-manifest.json").read_text())
    source_id = store.list_sources(limit=1)[0]["id"]

    assert f"sources/manifest-{source_id}.md" in manifest["files"]


def test_source_pages_are_unique_for_same_slug_titles(tmp_path):
    first = tmp_path / "same.md"
    second = tmp_path / "nested" / "same.md"
    second.parent.mkdir()
    first.write_text("First source with a shared title.")
    second.write_text("Second source with a shared title and different content.")
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")
    first_source = store.add_path(first, title="Same")
    second_source = store.add_path(second, title="Same")

    compiler = WikiCompiler(db_path=tmp_path / "kg.sqlite3", wiki_path=tmp_path / "wiki")
    result = compiler.compile_all(apply=True)

    first_path = f"sources/same-{first_source['source_id']}.md"
    second_path = f"sources/same-{second_source['source_id']}.md"
    assert first_path in result["affected_pages"]
    assert second_path in result["affected_pages"]
    assert (tmp_path / "wiki" / first_path).exists()
    assert (tmp_path / "wiki" / second_path).exists()

    conn = sqlite3.connect(tmp_path / "kg.sqlite3")
    try:
        paths = {
            row[0]
            for row in conn.execute(
                "SELECT path FROM wiki_pages WHERE page_type = 'source'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert {first_path, second_path}.issubset(paths)


def test_compiler_rejects_duplicate_page_paths_before_writing(tmp_path, monkeypatch):
    first = tmp_path / "one.md"
    second = tmp_path / "two.md"
    first.write_text("First duplicate path source.")
    second.write_text("Second duplicate path source.")
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")
    store.add_path(first)
    store.add_path(second)
    compiler = WikiCompiler(db_path=tmp_path / "kg.sqlite3", wiki_path=tmp_path / "wiki")
    monkeypatch.setattr(compiler, "_source_page_path", lambda source: "sources/collision.md")

    try:
        compiler.compile_all(apply=True)
    except ValueError as exc:
        assert "duplicate wiki page path" in str(exc)
    else:
        raise AssertionError("duplicate wiki page paths should fail before writing")

    assert not (tmp_path / "wiki" / "sources" / "collision.md").exists()
