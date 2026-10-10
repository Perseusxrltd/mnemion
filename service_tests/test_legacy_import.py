"""Portable legacy migration fixtures; Chroma is not required by the v4 service."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone
from threading import Event
from uuid import UUID, uuid4

import psycopg
import pytest

from mnemion.archives import canonical_json, verified_archive, write_archive
from mnemion.legacy_archive import FORMAT, LEDGER_FORMAT
from mnemion.legacy_freeze import freeze_profile
from mnemion.service.db import require_space
from mnemion.service.errors import ServiceError
from mnemion.service.export import ExportService
from mnemion.service.fences import pause_space, resume_space
from mnemion.service.legacy_import import import_v3, memory_id
from mnemion.service.models import ExportInput, MemoryInput
from mnemion.service.models import (
    BlockInput,
    GrantInput,
    KeyInput,
    PrincipalInput,
    RevisionInput,
    ReviewInput,
)
from mnemion.service.rollback import FORMAT as ROLLBACK_FORMAT, export_rollback
from mnemion.vault_client import sync_bundle
from mnemion.vault_refresh import refresh


@pytest.fixture
def legacy_archive(tmp_path):
    profile_id, collection_id = str(uuid4()), str(uuid4())
    original = b"Original source: caf\xc3\xa9, private decisions.\x00\xff"

    def make(*, paused=False, changed=False, missing=False, invalid=False):
        directory = tmp_path / uuid4().hex
        root = directory / "contents"
        profile = root / "profile"
        (profile / "sources").mkdir(parents=True)
        (profile / "sources" / "original.bin").write_bytes(original)
        (profile / "sources" / "extracted.txt").write_text(
            "Evidence from the original café decision.", encoding="utf-8"
        )
        if paused:
            freeze_profile(profile)
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            {
                "collection_id": collection_id,
                "collection_name": "mnemion_drawers",
                "id": "keep",
                "content": "The team chose two Postgres replicas."
                if changed
                else "The team chose Postgres.",
                "meta": {"wing": "work", "room": "decisions"},
            },
            {
                "collection_id": collection_id,
                "collection_name": "mnemion_drawers",
                "id": "withdraw",
                "content": "OLD_WITHDRAWN_PRIVATE_BYTES",
                "meta": {"wing": "work"},
            },
        ]
        if missing:
            rows.append(
                {
                    "collection_id": collection_id,
                    "collection_name": "mnemion_drawers",
                    "id": "unknown",
                    "content": "Unknown trust",
                    "meta": {},
                }
            )
        trust = [
            {
                "drawer_id": r["id"],
                "status": "contested" if r["id"] == "keep" else "current",
                "created_at": "2024-04-05T09:30:00+00:00",
                "verifications": 100,
            }
            for r in rows
            if r["id"] != "unknown"
        ]
        lifecycle = {
            "drawer_trust": trust,
            "drawer_trust_history": [
                {
                    "drawer_id": "keep",
                    "new_status": "contested",
                    "reason": "Conflicting source",
                    "changed_at": "2024-04-06T09:30:00+00:00",
                }
            ],
            "drawer_conflicts": [{"drawer_id_a": "keep", "drawer_id_b": "withdraw", "resolved": 0}],
            "drawer_ingest_jobs": [
                {
                    "write_id": 3,
                    "collection_id": collection_id,
                    "drawer_id": "pending",
                    "state": "pending",
                    "payload_json": json.dumps(
                        {
                            "content": "Acknowledged before a legacy crash",
                            "metadata": {"wing": "work"},
                        }
                    ),
                }
            ]
            if missing
            else [],
            "core_memories": [
                {
                    "key": "policy",
                    "content": "Keep source evidence.",
                    "updated_at": "2024-04-05T09:30:00+00:00",
                }
            ],
            "raw_sources": [
                {
                    "id": "original-source",
                    "title": "Café source",
                    "file_path": "/original/profile/sources/original.bin",
                    "raw_text_path": "/original/profile/sources/extracted.txt",
                    "trust_status": "current",
                    "created_at": "2024-04-05T09:30:00+00:00",
                }
            ],
        }
        deletions = (
            [{"collection_id": collection_id, "drawer_id": "withdraw", "requested_at": now}]
            if changed
            else []
        )
        ledger = {
            "format": LEDGER_FORMAT,
            "version": 1,
            "profile_id": profile_id,
            "snapshot_at": now,
            "deletions": deletions,
        }
        ledger["sha256"] = hashlib.sha256(canonical_json(ledger)).hexdigest()
        logical = root / "logical"
        logical.mkdir()
        (logical / "drawers.jsonl").write_bytes(b"".join(canonical_json(r) + b"\n" for r in rows))
        (logical / "collections.json").write_bytes(
            canonical_json(
                [
                    {
                        "id": collection_id,
                        "name": "mnemion_drawers",
                        "count": len(rows) + int(invalid),
                    }
                ]
            )
        )
        (logical / "lifecycle.json").write_bytes(canonical_json(lifecycle))
        (logical / "deletions.json").write_bytes(canonical_json(ledger))
        archive = directory / "legacy.mnemion"
        write_archive(
            archive,
            {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()},
            {
                "format": FORMAT,
                "version": 1,
                "profile_id": profile_id,
                "snapshot_at": now,
                "backup_id": str(uuid4()),
                "original_paths": {
                    "profile": "/original/profile",
                    "sources": "/original/profile/sources",
                },
                "layout": {"profile": "profile", "sources": "profile/sources"},
            },
        )
        return archive

    make.profile_id, make.collection_id, make.raw_bytes = profile_id, collection_id, original
    return make


def run_import(env, archive, **kwargs):
    return import_v3(
        env.admin_dsn,
        archive,
        tenant=env.owner.tenant_id,
        owner=env.owner.principal_id,
        generation=env.embedder.generation,
        **kwargs,
    )


def test_import_keeps_private_scope_ids_trust_evidence_and_obsidian_paths(
    env, legacy_archive, tmp_path
):
    archive = legacy_archive()
    report = run_import(env, archive)
    space = UUID(report["space_id"])
    assert report["paused"] and not report["exceptions"]
    assert report["counts"] == {"created": 3, "core_blocks": 1}
    keep = memory_id(space, legacy_archive.collection_id, "keep")
    item = env.memory.fetch(env.owner, keep)
    assert item["claim_status"] == "contested" and item["version"] == 1
    assert item["created_at"].startswith("2024-04-05")
    evidence = env.memory.source(env.owner, UUID(item["evidence"]["source_revision_id"]))
    attachment = evidence["attachments"][0]
    stored = env.memory.attachment(
        env.owner, UUID(evidence["source_revision_id"]), UUID(attachment["attachment_id"])
    )
    assert json.loads(stored["content"])["history"][0]["reason"] == "Conflicting source"
    assert json.loads(stored["content"])["trust"]["verifications"] == 100
    source = env.memory.fetch(env.owner, memory_id(space, "raw-sources", "original-source"))
    evidence = env.memory.source(env.owner, UUID(source["evidence"]["source_revision_id"]))
    raw = next(a for a in evidence["attachments"] if a["name"].startswith("file_path"))
    assert (
        env.memory.attachment(
            env.owner, UUID(evidence["source_revision_id"]), UUID(raw["attachment_id"])
        )["content"]
        == legacy_archive.raw_bytes
    )
    with env.db.transaction(env.owner) as conn:
        assert (
            len(
                conn.execute(
                    "SELECT * FROM mnemion.space_grants WHERE space_id=%s", (space,)
                ).fetchall()
            )
            == 1
        )
    with pytest.raises(ServiceError) as error:
        env.memory.save(env.owner, space, MemoryInput(content="A premature v4 write"), "paused")
    assert error.value.code == "space_paused"
    repeat = run_import(env, archive)
    assert repeat["counts"] == {"unchanged": 3}
    assert len(env.memory.history(env.owner, keep)) == 1
    vault = tmp_path / "copied-vault"
    vault.mkdir()
    # Existing v3 aliases select an established path, preserving native links.
    refresh(
        vault,
        {
            "Decision.md": "---\nid: keep\nmnemion_managed: true\n---\n# Existing decision\n\nThe team chose Postgres.\n"
        },
        {},
        ".mnemion-obsidian-manifest.json",
    )
    with (vault / "Decision.md").open("a") as note:
        note.write("My personal annotation.\n")
    (vault / "Personal.md").write_text("Read [[Decision]].\n")
    result = sync_bundle(
        ExportService(env.db).export(env.owner, ExportInput(space_ids=[space])), vault
    )
    assert result["completed"]
    assert "My personal annotation." in (vault / "Decision.md").read_text()
    assert "The team chose Postgres." in (vault / "Decision.md").read_text()
    assert (vault / "Personal.md").read_text() == "Read [[Decision]].\n"


def test_final_delta_reconciles_deletions_and_pending_writes_before_cutover(env, legacy_archive):
    initial = run_import(env, legacy_archive())
    final_archive = legacy_archive(paused=True, changed=True, missing=True)
    final = run_import(env, final_archive, final=True)
    space = UUID(final["space_id"])
    assert space == UUID(initial["space_id"])
    assert final["paused"] and not final["cutover_complete"]
    assert final["counts"]["withdrawn"] == 1 and final["counts"]["revised"] == 1
    assert {e["code"] for e in final["exceptions"]} == {"missing_trust_quarantined"}
    with pytest.raises(ServiceError):
        env.memory.fetch(env.owner, memory_id(space, legacy_archive.collection_id, "withdraw"))
    with psycopg.connect(env.admin_dsn) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.source_attachments a JOIN mnemion.source_revisions s ON s.id=a.source_revision_id WHERE s.tenant_id=%s AND s.content LIKE '%%OLD_WITHDRAWN_PRIVATE_BYTES%%'",
                (env.owner.tenant_id,),
            ).fetchone()[0]
            == 0
        )
    pending = memory_id(space, legacy_archive.collection_id, "pending")
    with pytest.raises(ServiceError):
        env.memory.fetch(env.owner, pending)
    assert env.memory.fetch(env.owner, pending, review=True)["review_state"] == "quarantined"
    completed = run_import(
        env, final_archive, final=True, accept_exceptions=final["exception_sha256"]
    )
    assert completed["cutover_complete"] and completed["exceptions_accepted"]
    env.memory.save(env.owner, space, MemoryInput(content="First post-cutover write"), "live")
    with pytest.raises(ValueError, match="completed cutover"):
        run_import(env, final_archive)


def test_invalid_snapshot_and_failed_import_do_not_publish_partial_space(
    env, legacy_archive, monkeypatch
):
    with pytest.raises(ValueError, match="counts"):
        run_import(env, legacy_archive(invalid=True))
    with pytest.raises(ValueError, match="persistently paused"):
        run_import(env, legacy_archive(), final=True)
    from mnemion.service.memory import MemoryService

    def fail(*args, **kwargs):
        raise OSError("Injected durable job insertion failure")

    monkeypatch.setattr(MemoryService, "_operation", fail)
    with pytest.raises(OSError):
        run_import(env, legacy_archive())
    with psycopg.connect(env.admin_dsn) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.legacy_profiles WHERE tenant_id=%s",
                (env.owner.tenant_id,),
            ).fetchone()[0]
            == 0
        )


def test_pause_waits_for_inflight_writes_and_allows_reads(env):
    started = Event()

    def pause():
        started.set()
        return pause_space(env.admin_dsn, env.owner.tenant_id, env.space, reason="rollback")

    with ThreadPoolExecutor(max_workers=1) as executor:
        with env.db.transaction(env.owner) as conn:
            require_space(conn, env.space, 20, writing=True)
            future = executor.submit(pause)
            assert started.wait(2)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.1)
        result = future.result(timeout=5)
    assert env.memory.list(env.owner, env.space)["items"] == []
    with pytest.raises(ServiceError) as error:
        env.memory.save(env.owner, env.space, MemoryInput(content="After the boundary"), "late")
    assert error.value.code == "space_paused"
    resume_space(env.admin_dsn, env.owner.tenant_id, env.space, UUID(result["token"]))
    env.memory.save(env.owner, env.space, MemoryInput(content="Resumed"), "resumed")


def test_tail_export_is_scoped_complete_and_never_contains_withdrawn_content(
    env, legacy_archive, tmp_path
):
    final = run_import(env, legacy_archive(paused=True), final=True)
    space = UUID(final["space_id"])
    keep = memory_id(space, legacy_archive.collection_id, "keep")
    env.memory.revise(
        env.owner,
        keep,
        RevisionInput(
            content="Changed after cutover.", expected_version=1, reason="New requirement"
        ),
        "tail-update",
    )
    env.memory.forget(
        env.owner,
        memory_id(space, legacy_archive.collection_id, "withdraw"),
        expected_version=1,
        key="delete",
    )
    env.memory.save(
        env.owner, env.space, MemoryInput(content="OTHER_SPACE_NEVER_EXPORTED"), "other"
    )
    env.memory.save(env.owner, space, MemoryInput(content="New after cutover"), "new")
    output = tmp_path / "tail.mnemion"
    report = export_rollback(env.admin_dsn, tenant=env.owner.tenant_id, space=space, output=output)
    assert report["memory_count"] == 3 and report["deletion_count"] == 1
    with verified_archive(output, ROLLBACK_FORMAT) as (manifest, root):
        assert manifest["base_backup_id"] == final["backup_id"]
        rows = [json.loads(line) for line in (root / "memories.jsonl").read_text().splitlines()]
        assert len(next(r for r in rows if r["memory_id"] == str(keep))["history"]) == 2
        assert any(r["content"] == "New after cutover" for r in rows)
        all_bytes = b"".join(p.read_bytes() for p in root.rglob("*") if p.is_file())
        assert (
            b"OLD_WITHDRAWN_PRIVATE_BYTES" not in all_bytes
            and b"OTHER_SPACE_NEVER_EXPORTED" not in all_bytes
        )
        assert legacy_archive.raw_bytes in all_bytes
        notes = json.loads((root / "change-notes.json").read_text())
        assert len(notes) == 1 and notes[0]["reason"] == "New requirement"
    with pytest.raises(ServiceError) as error:
        env.memory.save(env.owner, space, MemoryInput(content="Too late"), "late")
    assert error.value.code == "space_paused"


def test_failed_report_does_not_open_a_migration_space(env, legacy_archive):
    def fail(report):
        raise OSError("Injected report disk failure")

    with pytest.raises(OSError):
        run_import(env, legacy_archive(paused=True), final=True, report_sink=fail)
    with psycopg.connect(env.admin_dsn) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.legacy_profiles WHERE tenant_id=%s",
                (env.owner.tenant_id,),
            ).fetchone()[0]
            == 0
        )


def test_alias_and_original_attachment_follow_current_scope_review_and_deletion(
    env, legacy_archive
):
    from fastapi.testclient import TestClient
    from mnemion.service.api import create_app

    report = run_import(env, legacy_archive(paused=True), final=True)
    space = UUID(report["space_id"])
    original = env.memory.resolve_alias(env.owner, space, "original-source")
    memory = UUID(original["memory_id"])
    source_id = UUID(original["evidence"]["source_revision_id"])
    source = env.memory.source(env.owner, source_id)
    blob = next(a for a in source["attachments"] if a["name"].startswith("file_path"))
    principal = env.identities.create_principal(env.owner, PrincipalInput(name="Reader"))
    key = env.identities.create_key(
        env.owner, UUID(principal["id"]), KeyInput(name="Scoped reader")
    )
    reader = env.db.authenticate(key["api_key"])
    with TestClient(create_app(env.db, env.embedder)) as client:
        path = f"/v1/sources/{source_id}/attachments/{blob['attachment_id']}"
        auth = {"Authorization": "Bearer " + key["api_key"]}
        assert client.get(path, headers=auth).status_code == 404
        env.identities.grant(env.owner, space, reader.principal_id, GrantInput(role="reader"))
        downloaded = client.get(path, headers=auth)
        assert downloaded.status_code == 200 and downloaded.content == legacy_archive.raw_bytes
        assert (
            downloaded.headers["X-Content-SHA256"] == hashlib.sha256(downloaded.content).hexdigest()
        )
        resolved = client.get(
            f"/v1/spaces/{space}/resolve", params={"legacy_id": "original-source"}, headers=auth
        )
        assert resolved.status_code == 200 and resolved.json()["memory_id"] == str(memory)
        env.memory.review(
            env.owner,
            memory,
            ReviewInput(expected_version=1, state="quarantined", reason="Needs review"),
        )
        assert client.get(path, headers=auth).status_code == 404
        assert client.get(path + "?review=true", headers=auth).status_code == 403
        owner = {"Authorization": "Bearer " + env.token}
        assert client.get(path + "?review=true", headers=owner).content == legacy_archive.raw_bytes
        env.memory.forget(env.owner, memory, expected_version=2, key="erase-source")
        assert client.get(path + "?review=true", headers=owner).status_code == 404
        assert (
            client.get(
                f"/v1/spaces/{space}/resolve",
                params={"legacy_id": "original-source", "review": "true"},
                headers=owner,
            ).status_code
            == 404
        )
        while env.worker.run_once():
            pass
    with psycopg.connect(env.admin_dsn) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.source_attachments WHERE tenant_id=%s AND source_revision_id=%s",
                (env.owner.tenant_id, source_id),
            ).fetchone()[0]
            == 0
        )


def test_real_legacy_rollback_preserves_new_writes_corrections_core_and_deletions(env, tmp_path):
    pytest.importorskip(
        "chromadb", reason="Native v3 replay runs in the Python 3.12 legacy environment"
    )
    import subprocess
    import sys
    from mnemion.legacy_archive import create_legacy_backup
    from mnemion.legacy_rollback import restore_rollback

    profile = tmp_path / "original-legacy"
    seed = r"""
import json,sys,chromadb
from pathlib import Path
from mnemion.embedding import get_embedding_function
from mnemion.ingestion import LegacyMemoryWriter
from mnemion.knowledge_graph import KnowledgeGraph
p=Path(sys.argv[1]);p.mkdir()
(p/'config.json').write_text(json.dumps({'collection_name':'mnemion_drawers','embedding_device':'hash'}))
c=chromadb.PersistentClient(path=str(p/'anaktoron')).create_collection('mnemion_drawers',embedding_function=None)
w=LegacyMemoryWriter(c,p/'knowledge_graph.sqlite3');e=get_embedding_function('hash')
for id_,content in [('keep','Before cutover'),('withdraw','PRIVATE_DELETE_THIS')]:
    w.save(id_,content,{'wing':'team','room':'decisions'},e([content])[0])
KnowledgeGraph(str(p/'knowledge_graph.sqlite3')).update_core_memory('policy','Old policy')
print(c.id)
"""
    seeded = subprocess.run(
        [sys.executable, "-c", seed, str(profile)], capture_output=True, text=True
    )
    assert seeded.returncode == 0, seeded.stderr
    collection = seeded.stdout.strip()
    freeze_profile(profile)
    backup = tmp_path / "final-legacy.mnemion"
    create_legacy_backup(profile, backup, writers_stopped=True)
    final = run_import(env, backup, final=True)
    assert final["cutover_complete"], final["exceptions"]
    space = UUID(final["space_id"])
    keep = memory_id(space, collection, "keep")
    env.memory.revise(
        env.owner,
        keep,
        RevisionInput(content="Corrected after cutover", expected_version=1, reason="New evidence"),
        "correct",
    )
    added = env.memory.save(env.owner, space, MemoryInput(content="New v4 memory"), "add")
    env.memory.review(
        env.owner,
        UUID(added["memory_id"]),
        ReviewInput(expected_version=1, state="quarantined", reason="Review first"),
    )
    env.memory.forget(
        env.owner, memory_id(space, collection, "withdraw"), expected_version=1, key="erase"
    )
    env.memory.put_block(
        env.owner, space, "policy", BlockInput(content="New policy", expected_version=1)
    )
    tail = tmp_path / "v4-tail.mnemion"
    export_rollback(env.admin_dsn, tenant=env.owner.tenant_id, space=space, output=tail)
    restored = tmp_path / "rollback-copy"
    outcome = restore_rollback(backup, tail, restored)
    assert outcome["paused"] and outcome["verified_records"] == 2
    assert (profile / ".mnemion-writers-paused.json").is_file()
    assert (
        restored / "recovery" / (outcome["snapshot_id"] + ".mnemion")
    ).read_bytes() == tail.read_bytes()
    probe = r"""
import json,sys,sqlite3,chromadb
from pathlib import Path
p=Path(sys.argv[1]);c=chromadb.PersistentClient(path=str(p/'anaktoron')).get_collection('mnemion_drawers',embedding_function=None)
r=c.get(include=['documents']);out={'memories':dict(zip(r['ids'],r['documents']))}
with sqlite3.connect(p/'knowledge_graph.sqlite3') as conn:
    out['trust']=dict(conn.execute('SELECT drawer_id,status FROM drawer_trust'))
    out['policy']=conn.execute("SELECT content FROM core_memories WHERE key='policy'").fetchone()[0]
print(json.dumps(out))
"""
    verified = subprocess.run(
        [sys.executable, "-c", probe, str(restored)], capture_output=True, text=True
    )
    assert verified.returncode == 0, verified.stderr
    result = json.loads(verified.stdout)
    assert result["memories"] == {
        "keep": "Corrected after cutover",
        "v4:" + added["memory_id"]: "New v4 memory",
    }
    assert result["trust"]["v4:" + added["memory_id"]] == "quarantined"
    assert result["policy"] == "New policy"
    damaged = tmp_path / "truncated.mnemion"
    damaged.write_bytes(tail.read_bytes()[:-10])
    with pytest.raises(ValueError):
        restore_rollback(backup, damaged, tmp_path / "not-published")
    assert not (tmp_path / "not-published").exists()
