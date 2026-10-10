"""Rollback must reconcile raw sources and derived views, not just Chroma rows."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

from mnemion.legacy_archive import create_legacy_backup
from mnemion.legacy_freeze import freeze_profile
from mnemion.legacy_rollback import restore_rollback
from mnemion.service.legacy_import import import_v3
from mnemion.service.models import RevisionInput, ReviewInput
from mnemion.service.rollback import export_rollback


def test_rollback_rebuilds_source_search_wiki_and_managed_vault_from_current_records(env, tmp_path):
    pytest.importorskip(
        "chromadb", reason="Native rollback requires the Python 3.12 legacy environment"
    )
    profile = tmp_path / "legacy"
    seed = r"""
import json,sys,chromadb
from pathlib import Path
from mnemion.embedding import get_embedding_function
from mnemion.sources.store import SourceStore, SOURCE_CHROMA_COLLECTION
from mnemion.sources.chunking import sha256_hex
from mnemion.vault_refresh import refresh
from mnemion.wiki.store import WikiStore
p=Path(sys.argv[1]);p.mkdir()
(p/'config.json').write_text(json.dumps({'collection_name':'mnemion_drawers','embedding_device':'hash'}))
client=chromadb.PersistentClient(path=str(p/'anaktoron'));embedding=get_embedding_function('hash')
client.create_collection('mnemion_drawers',embedding_function=embedding)
store=SourceStore(p/'knowledge_graph.sqlite3',p/'sources')
ids={}
for name,text in [('keep','RAW_OLD_VALUE'),('withdraw','RAW_WITHDRAW_SENTINEL'),('indexed','VECTOR_OLD_VALUE')]:
    source=p/(name+'.txt');source.write_text(text)
    ids[name]=store.add_path(source,title=name)['source_id']
chunk=store.list_chunks(ids['indexed'])[0]
source_collection=client.create_collection(SOURCE_CHROMA_COLLECTION,embedding_function=embedding)
source_collection.upsert(ids=[chunk['id']],documents=[chunk['text']],embeddings=embedding([chunk['text']]),metadatas=[{'source_id':ids['indexed'],'chunk_index':0}])
ids['chunk']=chunk['id']
(p/'wiki').mkdir();page=p/'wiki/generated.md';page.write_text('VECTOR_OLD_VALUE')
WikiStore(p/'knowledge_graph.sqlite3').upsert_page('old-page',str(page),'concept','Old concept',sha256_hex(page.read_bytes()),[],[chunk['id']],[],1.0)
(p/'wiki/Personal.md').write_text('Keep this personal wiki note.')
vault=p/'obsidian-vault'
files={'Wings/Legacy/keep.md':f"---\nid: {ids['keep']}\n---\n# Keep\nRAW_OLD_VALUE\n",'Wings/Legacy/withdraw.md':f"---\nid: {ids['withdraw']}\n---\n# Withdraw\nRAW_WITHDRAW_SENTINEL\n"}
refresh(vault,files,{},'.mnemion-obsidian-manifest.json')
keep=vault/'Wings/Legacy/keep.md';keep.write_bytes(keep.read_bytes()+b'Personal annotation.\r\n')
(vault/'.obsidian').mkdir();(vault/'.obsidian/app.json').write_bytes(b'{"alwaysUpdateLinks":true}\n')
print(json.dumps(ids))
"""
    seeded = subprocess.run(
        [sys.executable, "-c", seed, str(profile)], capture_output=True, text=True
    )
    assert seeded.returncode == 0, seeded.stderr
    ids = json.loads(seeded.stdout)
    freeze_profile(profile)
    base, tail = tmp_path / "base.mnemion", tmp_path / "tail.mnemion"
    create_legacy_backup(profile, base, writers_stopped=True)
    imported = import_v3(
        env.admin_dsn,
        base,
        tenant=env.owner.tenant_id,
        owner=env.owner.principal_id,
        generation=env.embedder.generation,
        final=True,
    )
    assert imported["cutover_complete"], imported["exceptions"]
    space = UUID(imported["space_id"])
    keep = UUID(env.memory.resolve_alias(env.owner, space, ids["keep"])["memory_id"])
    withdrawn = UUID(env.memory.resolve_alias(env.owner, space, ids["withdraw"])["memory_id"])
    indexed = UUID(env.memory.resolve_alias(env.owner, space, ids["chunk"])["memory_id"])
    env.memory.revise(
        env.owner,
        keep,
        RevisionInput(content="RAW_CURRENT_VALUE", expected_version=1, reason="Corrected"),
        "raw-correct",
    )
    env.memory.revise(
        env.owner,
        indexed,
        RevisionInput(content="VECTOR_CURRENT_VALUE", expected_version=1, reason="Corrected"),
        "vector-correct",
    )
    env.memory.review(
        env.owner,
        indexed,
        ReviewInput(expected_version=2, state="quarantined", reason="Needs review"),
    )
    env.memory.forget(env.owner, withdrawn, expected_version=1, key="raw-delete")
    export_rollback(env.admin_dsn, tenant=env.owner.tenant_id, space=space, output=tail)
    restored = tmp_path / "recovered"
    result = restore_rollback(base, tail, restored)
    assert result["projections"]["ready_to_resume"]
    assert result["projections"]["sources_rebuilt"] == 2
    assert result["projections"]["source_groups_quarantined"] == 1
    assert result["projections"]["wiki_pages_invalidated"] == 1
    with sqlite3.connect(restored / "knowledge_graph.sqlite3") as conn:
        sources = conn.execute("SELECT id,raw_text_path,trust_status FROM raw_sources").fetchall()
        assert {r[0] for r in sources} == {ids["keep"], ids["indexed"]}
        for source_id, path, status in sources:
            assert Path(path).is_relative_to(restored) and Path(path).is_file()
            content = Path(path).read_text()
            assert "RAW_WITHDRAW_SENTINEL" not in content and "OLD_VALUE" not in content
            assert status == ("quarantined" if source_id == ids["indexed"] else "current")
        fts = " ".join(row[0] for row in conn.execute("SELECT text FROM source_chunks_fts"))
        assert "RAW_CURRENT_VALUE" in fts and "VECTOR_CURRENT_VALUE" in fts
        assert "OLD_VALUE" not in fts and "RAW_WITHDRAW_SENTINEL" not in fts
        assert conn.execute("SELECT count(*) FROM wiki_pages").fetchone()[0] == 0
        assert (
            conn.execute(
                "SELECT count(*) FROM drawer_deletions WHERE collection_id='raw-sources' AND drawer_id=?",
                (ids["withdraw"],),
            ).fetchone()[0]
            == 1
        )
    assert not (restored / "wiki/generated.md").exists()
    assert (restored / "wiki/Personal.md").read_text() == "Keep this personal wiki note."
    vault = restored / "obsidian-vault"
    assert (vault / "Wings/Legacy/keep.md").read_bytes().endswith(b"Personal annotation.\r\n")
    assert "RAW_CURRENT_VALUE" in (vault / "Wings/Legacy/keep.md").read_text()
    assert not (vault / "Wings/Legacy/withdraw.md").exists()
    assert (vault / ".obsidian/app.json").read_bytes() == b'{"alwaysUpdateLinks":true}\n'
    assert "RAW_WITHDRAW_SENTINEL" not in "\n".join(
        path.read_text() for path in vault.rglob("*.md")
    )
