import json
import sqlite3

from mnemion.capture.cli_capture import capture_text
from mnemion.sources.store import SourceStore
from mnemion.wiki.compiler import WikiCompiler
from mnemion.wiki.context_pack import build_context_pack
from mnemion.wiki.linter import WikiLinter
from mnemion.wiki.obsidian_export import export_compiled_wiki_to_obsidian


def test_alpha_harness_ingests_compiles_lints_exports_without_live_home(monkeypatch, tmp_path):
    db_path = tmp_path / "alpha" / "knowledge_graph.sqlite3"
    source_path = tmp_path / "alpha" / "sources"
    wiki_path = tmp_path / "alpha" / "wiki"
    diffs_path = tmp_path / "alpha" / "wiki_diffs"
    anaktoron_path = tmp_path / "alpha" / "anaktoron"
    vault_path = tmp_path / "alpha" / "obsidian"
    source_dir = tmp_path / "fixtures"
    source_dir.mkdir()
    files = [
        source_dir / "alpha.md",
        source_dir / "notes.txt",
        source_dir / "facts.json",
        source_dir / "events.jsonl",
        source_dir / "table.csv",
    ]
    files[0].write_text("# Alpha\n\nHybrid retrieval uses source-backed claims.")
    files[1].write_text("Trust lifecycle marks contested memories for review.")
    files[2].write_text(json.dumps({"topic": "privacy", "status": "private"}))
    files[3].write_text(json.dumps({"event": "compiled wiki", "year": 2026}) + "\n")
    files[4].write_text("name,value\ncitation,coverage\n")

    store = SourceStore(
        db_path=db_path, source_path=source_path, anaktoron_path=str(anaktoron_path)
    )
    created = [store.add_path(path) for path in files]
    duplicate = store.add_path(files[0])

    class FakeCollection:
        def __init__(self):
            self.ids = set()

        def get(self, ids=None, **kwargs):
            found = [drawer_id for drawer_id in ids or [] if drawer_id in self.ids]
            return {"ids": found}

        def upsert(self, ids=None, documents=None, metadatas=None):
            self.ids.update(ids or [])

    class FakeBackend:
        def __init__(self):
            self.collection = FakeCollection()

        def get_collection(self, name, create=False):
            return self.collection

    monkeypatch.setattr("mnemion.capture.cli_capture.get_backend", lambda **kwargs: FakeBackend())

    capture_text(
        "Alpha hardening captures normal Mnemion drawers.",
        tags=["alpha"],
        anaktoron_path=str(anaktoron_path),
    )
    compiler = WikiCompiler(
        db_path=db_path,
        wiki_path=wiki_path,
        diffs_path=diffs_path,
        source_path=source_path,
    )
    review = compiler.compile_all(review=True)
    applied = compiler.apply_job(review["job_id"])
    lint = WikiLinter(db_path=db_path, wiki_path=wiki_path).lint()
    pack = build_context_pack(
        "hybrid retrieval trust lifecycle",
        db_path=db_path,
        wiki_path=wiki_path,
        anaktoron_path=str(anaktoron_path),
        token_budget=1200,
    )
    unmanaged = vault_path / "_Mnemion" / "Compiled Wiki" / "human.md"
    unmanaged.parent.mkdir(parents=True)
    unmanaged.write_text("do not delete\n")
    export = export_compiled_wiki_to_obsidian(wiki_path, vault_path, db_path=db_path)

    assert all(result["status"] == "created" for result in created)
    assert duplicate["status"] == "existing"
    assert store.stats()["sources"] == len(files)
    assert review["status"] == "review"
    assert applied["pages_written"] >= len(files) + 2
    assert not [issue for issue in lint.issues if issue.severity == "error"]
    assert pack["wiki_pages"]
    assert pack["source_chunks"]
    assert export["file_count"] >= len(files) + 2
    assert unmanaged.exists()
    assert not (tmp_path / ".mnemion").exists()


def test_linter_flags_stale_source_hash_and_quarantined_page(tmp_path):
    source_file = tmp_path / "stale.md"
    source_file.write_text("Stale source hash detection protects compiled wiki pages.")
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")
    result = store.add_path(source_file)
    compiler = WikiCompiler(db_path=tmp_path / "kg.sqlite3", wiki_path=tmp_path / "wiki")
    compiler.compile_all(apply=True)
    page = tmp_path / "wiki" / "sources" / f"stale-{result['source_id']}.md"
    page.write_text(page.read_text(encoding="utf-8") + "\ntrust_status: quarantined\n")

    with sqlite3.connect(tmp_path / "kg.sqlite3") as conn:
        conn.execute(
            "UPDATE raw_sources SET content_hash = ? WHERE id = ?",
            ("sha256:" + "9" * 64, result["source_id"]),
        )
        conn.commit()

    lint = WikiLinter(db_path=tmp_path / "kg.sqlite3", wiki_path=tmp_path / "wiki").lint()
    categories = {issue.category for issue in lint.issues}

    assert "stale_source_hash" in categories
    assert "quarantined_evidence_visible" in categories


def test_context_pack_excludes_quarantined_sources_and_warns_on_contested(tmp_path):
    safe = tmp_path / "safe.md"
    contested = tmp_path / "contested.md"
    quarantined = tmp_path / "quarantined.md"
    safe.write_text("Hybrid retrieval remains current evidence.")
    contested.write_text("Hybrid retrieval has contested evidence.")
    quarantined.write_text("Hybrid retrieval quarantined evidence must not surface.")
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")
    safe_result = store.add_path(safe)
    contested_result = store.add_path(contested)
    quarantined_result = store.add_path(quarantined)
    with sqlite3.connect(tmp_path / "kg.sqlite3") as conn:
        conn.execute(
            "UPDATE raw_sources SET trust_status = 'contested' WHERE id = ?",
            (contested_result["source_id"],),
        )
        conn.execute(
            "UPDATE raw_sources SET trust_status = 'quarantined' WHERE id = ?",
            (quarantined_result["source_id"],),
        )
        conn.commit()
    WikiCompiler(db_path=tmp_path / "kg.sqlite3", wiki_path=tmp_path / "wiki").compile_all(
        apply=True
    )

    pack = build_context_pack(
        "hybrid retrieval",
        db_path=tmp_path / "kg.sqlite3",
        wiki_path=tmp_path / "wiki",
    )
    chunk_source_ids = {chunk["source_id"] for chunk in pack["source_chunks"]}

    assert safe_result["source_id"] in chunk_source_ids
    assert contested_result["source_id"] in chunk_source_ids
    assert quarantined_result["source_id"] not in chunk_source_ids
    assert any("contested" in warning.lower() for warning in pack["warnings"])
    assert pack["contested"]


def test_obsidian_export_reports_sensitive_and_quarantined_skips(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "current.md").write_text("---\ntitle: Current\n---\n# Current\n")
    (wiki / "sensitive.md").write_text(
        "---\ntitle: Sensitive\nprivacy_class: sensitive\n---\n# Sensitive\n"
    )
    (wiki / "quarantined.md").write_text(
        "---\ntitle: Quarantined\ntrust_status: quarantined\n---\n# Quarantined\n"
    )
    vault = tmp_path / "vault"

    result = export_compiled_wiki_to_obsidian(wiki, vault)

    assert result["file_count"] == 1
    assert result["skipped_sensitive"] == 1
    assert result["skipped_quarantined"] == 1
    assert result["warnings"]
    assert (vault / "_Mnemion" / "Compiled Wiki" / "current.md").exists()
    assert not (vault / "_Mnemion" / "Compiled Wiki" / "sensitive.md").exists()
    assert not (vault / "_Mnemion" / "Compiled Wiki" / "quarantined.md").exists()
