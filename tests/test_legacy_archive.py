import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from mnemion.archives import verified_archive
from mnemion.legacy_archive import (
    FORMAT,
    create_legacy_backup,
    export_legacy_ledger,
    restore_legacy_backup,
)
from mnemion.legacy_freeze import freeze_profile, require_writable, thaw_profile


SEED = r"""
import json, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path
from mnemion.chroma_client import persistent_client
from mnemion.ingestion import LegacyMemoryWriter
from mnemion.knowledge_graph import KnowledgeGraph
from mnemion.sources.store import SourceStore
from mnemion.trust_lifecycle import DrawerTrust
p=Path(sys.argv[1]);p.mkdir(parents=True)
(p/'config.json').write_text(json.dumps({'collection_name':'mnemion_drawers'}))
client=persistent_client(path=str(p/'anaktoron'))
col=client.create_collection('mnemion_drawers',embedding_function=None)
writer=LegacyMemoryWriter(col,p/'knowledge_graph.sqlite3')
writer.save('keep','The team chose Postgres.',{'wing':'work','room':'decisions'},[1,0,0,0])
writer.save('withdraw','LEGACY_WITHDRAWN_BYTES',{'wing':'work','room':'decisions'},[0,1,0,0])
DrawerTrust(str(p/'knowledge_graph.sqlite3')).update_status('keep','contested',reason='Conflicting review')
KnowledgeGraph(str(p/'knowledge_graph.sqlite3')).update_core_memory('policy','Keep source evidence.')
original=p/'input.txt';original.write_text('Original source: café and team decisions.',encoding='utf-8')
SourceStore(p/'knowledge_graph.sqlite3',p/'sources').add_path(original,title='Original source')
vault=p/'obsidian-vault';(vault/'.obsidian').mkdir(parents=True)
(vault/'.obsidian/app.json').write_text(json.dumps({'alwaysUpdateLinks':True},indent=2)+'\n')
(vault/'Personal.md').write_text('# Personal\n\nMy own annotation and [[Decision]].\n')
(vault/'Decision.md').write_text('---\nid: keep\n---\n# Original path\n\nThe team chose Postgres.\n')
with sqlite3.connect(p/'knowledge_graph.sqlite3') as conn:
    conn.execute("INSERT INTO drawer_ingest_jobs(collection_id,drawer_id,payload_json,created_at) VALUES(?,?,?,?)",(str(col.id),'pending',json.dumps({'content':'Durable pending write','metadata':{'wing':'work','room':'decisions'},'embedding':[0,0,1,0]}),datetime.now(timezone.utc).isoformat()))
"""


@pytest.fixture
def legacy_profile(tmp_path):
    profile = tmp_path / "legacy"
    result = subprocess.run(
        [sys.executable, "-c", SEED, str(profile)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return profile


def test_complete_legacy_roundtrip_keeps_sources_history_core_vault_and_later_deletions(
    legacy_profile, tmp_path
):
    profile = legacy_profile
    backup, ledger, restored = (
        tmp_path / "v3.mnemion",
        tmp_path / "ledger.json",
        tmp_path / "restored",
    )
    result = create_legacy_backup(profile, backup, writers_stopped=True)
    assert result["collections"][0]["count"] == 2
    assert result["sidecar_counts"]["raw_sources"] == 1
    with verified_archive(backup, FORMAT) as (manifest, root):
        rows = [
            json.loads(line) for line in (root / "logical/drawers.jsonl").read_text().splitlines()
        ]
        assert {row["id"]: row["content"] for row in rows} == {
            "keep": "The team chose Postgres.",
            "withdraw": "LEGACY_WITHDRAWN_BYTES",
        }
        assert manifest["source_inventory"]
    deletion = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from pathlib import Path
from mnemion.chroma_client import persistent_client
from mnemion.ingestion import LegacyMemoryWriter
p=Path(sys.argv[1]);client=persistent_client(path=str(p/'anaktoron'))
c=client.get_collection('mnemion_drawers',embedding_function=None)
LegacyMemoryWriter(c,p/'knowledge_graph.sqlite3').delete('withdraw')
""",
            str(profile),
        ],
        capture_output=True,
        text=True,
    )
    assert deletion.returncode == 0, deletion.stderr
    export_legacy_ledger(profile, ledger)
    outcome = restore_legacy_backup(backup, restored, deletion_ledger=ledger)
    assert outcome["paused"] and outcome["deletions_reconciled"] == 1
    config = json.loads((restored / "config.json").read_text())
    assert config["anaktoron_path"] == str(restored / "anaktoron")
    for name in ("Personal.md", "Decision.md", ".obsidian/app.json"):
        assert (restored / "obsidian-vault" / name).read_bytes() == (
            profile / "obsidian-vault" / name
        ).read_bytes()
    with sqlite3.connect(restored / "knowledge_graph.sqlite3") as conn:
        assert (
            conn.execute("SELECT status FROM drawer_trust WHERE drawer_id='keep'").fetchone()[0]
            == "contested"
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM drawer_trust_history WHERE drawer_id='keep'"
            ).fetchone()[0]
            == 2
        )
        assert (
            conn.execute("SELECT content FROM core_memories WHERE key='policy'").fetchone()[0]
            == "Keep source evidence."
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM drawer_ingest_jobs WHERE state='pending'"
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute("SELECT count(*) FROM drawers_fts WHERE drawer_id='withdraw'").fetchone()[
                0
            ]
            == 0
        )
        source = conn.execute("SELECT file_path,raw_text_path FROM raw_sources").fetchone()
        assert all(
            Path(value).is_relative_to(restored) and Path(value).exists() for value in source
        )
        assert Path(source[0]).read_bytes() == (profile / "input.txt").read_bytes()
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import json,sys
from mnemion.chroma_client import persistent_client
c=persistent_client(path=sys.argv[1]).get_collection('mnemion_drawers',embedding_function=None)
r=c.get(include=['documents']);print(json.dumps(dict(zip(r['ids'],r['documents']))))
""",
            str(restored / "anaktoron"),
        ],
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr
    assert json.loads(probe.stdout) == {
        "keep": "The team chose Postgres.",
        "pending": "Durable pending write",
    }
    with pytest.raises(RuntimeError, match="paused"):
        require_writable(restored / "anaktoron")
    thaw_profile(restored, outcome["freeze_id"])
    require_writable(restored / "anaktoron")


def test_changed_snapshot_and_truncated_restore_fail_before_publication(
    legacy_profile, tmp_path, monkeypatch
):
    from mnemion import legacy_archive

    profile, backup = legacy_profile, tmp_path / "v3.mnemion"
    copy = legacy_archive._copy_snapshot

    def changing(inputs, destination):
        copy(inputs, destination)
        (profile / "input.txt").write_text("Concurrent change")

    with monkeypatch.context() as patch:
        patch.setattr(legacy_archive, "_copy_snapshot", changing)
        with pytest.raises(ValueError, match="changed during backup"):
            create_legacy_backup(profile, backup, writers_stopped=True)
    assert not backup.exists()
    create_legacy_backup(profile, backup, writers_stopped=True)
    ledger = tmp_path / "ledger.json"
    export_legacy_ledger(profile, ledger)
    backup.write_bytes(backup.read_bytes()[:-25])
    with pytest.raises(ValueError):
        restore_legacy_backup(backup, tmp_path / "restored", deletion_ledger=ledger)
    assert not (tmp_path / "restored").exists()


def test_pause_blocks_updated_legacy_entry_points(legacy_profile):
    from mnemion.knowledge_graph import KnowledgeGraph
    from mnemion.trust_lifecycle import DrawerTrust
    from mnemion.sources.store import SourceStore
    from mnemion.backends.chroma import ChromaBackend

    frozen = freeze_profile(legacy_profile)
    with pytest.raises(RuntimeError, match="paused"):
        KnowledgeGraph(str(legacy_profile / "knowledge_graph.sqlite3"))
    with pytest.raises(RuntimeError, match="paused"):
        DrawerTrust(str(legacy_profile / "knowledge_graph.sqlite3"))
    with pytest.raises(RuntimeError, match="paused"):
        SourceStore(legacy_profile / "knowledge_graph.sqlite3", legacy_profile / "sources")
    with pytest.raises(RuntimeError, match="paused"):
        ChromaBackend(str(legacy_profile / "anaktoron"))
    with pytest.raises(ValueError, match="does not match"):
        thaw_profile(legacy_profile, "wrong")
    assert freeze_profile(legacy_profile) == frozen
