import json
import sqlite3

from mnemion.sources.store import SourceStore
from mnemion.wiki.compiler import WikiCompiler
from mnemion.wiki.obsidian_export import export_compiled_wiki_to_obsidian


def test_wiki_obsidian_export_writes_managed_subfolder_and_prunes_manifest_only(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "sources").mkdir(parents=True)
    (wiki / "sources" / "one.md").write_text("# One\n")
    vault = tmp_path / "vault"
    unmanaged = vault / "_Mnemion" / "Compiled Wiki" / "human.md"
    unmanaged.parent.mkdir(parents=True)
    unmanaged.write_text("keep\n")
    manifest = unmanaged.parent / ".mnemion-compiled-wiki-manifest.json"
    old = unmanaged.parent / "old.md"
    old.write_text("old\n")
    manifest.write_text(json.dumps({"files": ["old.md"]}))

    result = export_compiled_wiki_to_obsidian(wiki, vault)

    assert result["file_count"] == 1
    assert not old.exists()
    assert unmanaged.exists()
    assert (vault / "_Mnemion" / "Compiled Wiki" / "sources" / "one.md").exists()


def test_wiki_obsidian_export_skips_sensitive_pages_by_default(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "sensitive.md").write_text("---\nprivacy_class: sensitive\n---\n# Sensitive\n")
    vault = tmp_path / "vault"

    export_compiled_wiki_to_obsidian(wiki, vault)

    assert not (vault / "_Mnemion" / "Compiled Wiki" / "sensitive.md").exists()


def test_wiki_obsidian_export_uses_live_source_trust(tmp_path):
    source_file = tmp_path / "drift.md"
    source_file.write_text("Obsidian export must not copy quarantined source evidence.")
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

    result = export_compiled_wiki_to_obsidian(
        tmp_path / "wiki",
        tmp_path / "vault",
        db_path=tmp_path / "kg.sqlite3",
    )

    assert result["skipped_quarantined"] == 1
    assert not (
        tmp_path
        / "vault"
        / "_Mnemion"
        / "Compiled Wiki"
        / "sources"
        / f"drift-{source['source_id']}.md"
    ).exists()
