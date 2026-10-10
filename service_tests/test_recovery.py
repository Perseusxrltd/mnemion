import io
import json
import os
import zipfile
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from mnemion.service import recovery
from mnemion.service.db import Database
from mnemion.service.errors import ServiceError
from mnemion.service.memory import MemoryService
from mnemion.service.models import (
    BlockInput,
    ExportInput,
    GrantInput,
    KeyInput,
    MemoryInput,
    PrincipalInput,
    RecallInput,
    RevisionInput,
    ReviewInput,
    SourceInput,
)
from mnemion.service.export import ExportService
from mnemion.service.retrieval import RetrievalService


@pytest.fixture
def destination(postgres):
    name = "recovered_" + uuid4().hex
    yield name
    with psycopg.connect(postgres[0], autocommit=True) as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
        )


def exists(dsn, name):
    with psycopg.connect(dsn) as conn:
        return (
            conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone()
            is not None
        )


def test_complete_recovery_reconciles_later_deletion_grants_and_keys(
    env, postgres, pg_bin, tmp_path, destination
):
    kept = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(
            content="We chose Postgres.",
            subject="Architecture",
            source=SourceInput(
                title="Original decision",
                content="Meeting: We chose Postgres. Next item.",
                start=9,
                end=27,
            ),
        ),
        "recovery-kept",
    )
    kept_id = UUID(kept["memory_id"])
    env.memory.revise(
        env.owner,
        kept_id,
        RevisionInput(
            content="We chose two Postgres replicas.",
            expected_version=1,
            reason="Capacity decision",
        ),
        "recovery-revision",
    )
    doomed = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="RECOVERY_WITHDRAWN_BYTES", subject="DELETE_SUBJECT"),
        "recovery-doomed",
    )
    flagged = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="RECOVERY_QUARANTINED_BYTES"),
        "recovery-quarantine",
    )
    env.memory.review(
        env.owner,
        UUID(flagged["memory_id"]),
        ReviewInput(expected_version=1, state="quarantined", reason="Unverified"),
    )
    env.memory.put_block(
        env.owner,
        env.space,
        "context",
        BlockInput(content="Use source evidence", expected_version=0),
    )
    principal = env.identities.create_principal(
        env.owner, PrincipalInput(name="Revoked after backup")
    )
    key = env.identities.create_key(env.owner, UUID(principal["id"]), KeyInput(name="Old key"))
    env.identities.grant(env.owner, env.space, UUID(principal["id"]), GrantInput(role="reader"))
    while env.worker.run_once():
        pass
    pending = env.memory.save(
        env.owner, env.space, MemoryInput(content="Queued at the snapshot"), "recovery-pending"
    )
    leased = env.worker.claim()
    assert leased and str(leased["operation_id"]) == pending["operation_id"]
    archive, ledger, credentials = (
        tmp_path / n for n in ("backup.mnemion", "ledger.json", "owner.json")
    )
    backup = recovery.create_backup(env.admin_dsn, archive, pg_bin=pg_bin)
    env.memory.forget(
        env.owner, UUID(doomed["memory_id"]), expected_version=1, key="delete-after-backup"
    )
    later = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Created then deleted after snapshot"),
        "recovery-later",
    )
    env.memory.forget(env.owner, UUID(later["memory_id"]), expected_version=1, key="delete-later")
    env.identities.revoke_grant(env.owner, env.space, UUID(principal["id"]))
    env.identities.revoke_key(env.owner, UUID(key["id"]))
    recovery.export_ledger(env.admin_dsn, ledger)
    result = recovery.restore_backup(
        env.admin_dsn,
        archive,
        database_name=destination,
        deletion_ledger=ledger,
        credentials_output=credentials,
        pg_bin=pg_bin,
    )
    assert result["backup_id"] == backup["backup_id"] and result["keys_rotated"]
    restored_dsn = make_conninfo(postgres[1], dbname=destination)
    db = Database(restored_dsn)
    db.open()
    try:
        with pytest.raises(ServiceError):
            db.authenticate(env.token)
        with pytest.raises(ServiceError):
            db.authenticate(key["api_key"])
        owner = next(
            p
            for p in json.loads(credentials.read_text())["organizations"]
            if p["tenant_id"] == str(env.owner.tenant_id)
        )
        identity = db.authenticate(owner["api_key"])
        memory = MemoryService(db, env.embedder.generation)
        assert memory.fetch(identity, kept_id)["content"] == "We chose two Postgres replicas."
        assert len(memory.history(identity, kept_id)) == 2
        assert memory.blocks(identity, env.space)[0]["content"] == "Use source evidence"
        for hidden in (doomed, flagged):
            with pytest.raises(ServiceError):
                memory.fetch(identity, UUID(hidden["memory_id"]))
        hits = RetrievalService(db, env.embedder).recall(
            identity, RecallInput(query="Postgres", space_ids=[env.space])
        )
        assert kept["memory_id"] in [h["memory_id"] for h in hits["hits"]]
        artifact = ExportService(db).export(identity, ExportInput(space_ids=[env.space]))
        with zipfile.ZipFile(io.BytesIO(artifact)) as export:
            exported_text = b"\n".join(export.read(n) for n in export.namelist())
        assert b"RECOVERY_WITHDRAWN_BYTES" not in exported_text
        assert b"RECOVERY_QUARANTINED_BYTES" not in exported_text
        with psycopg.connect(
            make_conninfo(postgres[0], dbname=destination), row_factory=dict_row
        ) as conn:
            assert (
                conn.execute(
                    "SELECT count(*) AS n FROM mnemion.memory_revisions WHERE content='RECOVERY_WITHDRAWN_BYTES'"
                ).fetchone()["n"]
                == 0
            )
            assert (
                conn.execute(
                    "SELECT count(*) AS n FROM mnemion.source_revisions WHERE content='RECOVERY_WITHDRAWN_BYTES'"
                ).fetchone()["n"]
                == 0
            )
            assert conn.execute(
                "SELECT purged_at FROM mnemion.deletion_receipts WHERE memory_id=%s",
                (doomed["memory_id"],),
            ).fetchone()["purged_at"]
            assert (
                conn.execute(
                    "SELECT FROM mnemion.recovery_denials WHERE memory_id=%s", (later["memory_id"],)
                ).fetchone()
                is not None
            )
            assert (
                conn.execute(
                    "SELECT FROM mnemion.space_grants WHERE principal_id=%s", (principal["id"],)
                ).fetchone()
                is None
            )
            assert conn.execute(
                "SELECT state, lease_id FROM mnemion.jobs WHERE id=%s", (leased["id"],)
            ).fetchone() == {"state": "pending", "lease_id": None}
    finally:
        db.close()
    if os.name != "nt":
        assert archive.stat().st_mode & 0o777 == credentials.stat().st_mode & 0o777 == 0o600


def test_backup_uses_one_snapshot_during_concurrent_writes(env, pg_bin, tmp_path, monkeypatch):
    run = recovery._run_pg
    changed = False

    def concurrent_write(name, dsn, arguments, pg_bin):
        nonlocal changed
        if name == "pg_dump" and not changed:
            env.memory.save(
                env.owner,
                env.space,
                MemoryInput(content="After exported snapshot"),
                "snapshot-race",
            )
            changed = True
        return run(name, dsn, arguments, pg_bin)

    monkeypatch.setattr(recovery, "_run_pg", concurrent_write)
    with psycopg.connect(env.admin_dsn) as conn:
        before = conn.execute("SELECT count(*) FROM mnemion.memories").fetchone()[0]
    result = recovery.create_backup(env.admin_dsn, tmp_path / "snapshot.mnemion", pg_bin=pg_bin)
    assert changed and result["tables"]["memories"] == before


@pytest.mark.parametrize("damage", ["truncated", "checksum", "version", "partial"])
def test_bad_backup_never_creates_a_destination(env, pg_bin, tmp_path, destination, damage):
    source, broken, ledger = (
        tmp_path / n for n in ("valid.mnemion", "broken.mnemion", "ledger.json")
    )
    recovery.create_backup(env.admin_dsn, source, pg_bin=pg_bin)
    recovery.export_ledger(env.admin_dsn, ledger)
    if damage == "truncated":
        broken.write_bytes(source.read_bytes()[:-25])
    else:
        with zipfile.ZipFile(source) as archive:
            members = {n: archive.read(n) for n in archive.namelist()}
        if damage == "checksum":
            members["database.dump"] = b"X" + members["database.dump"][1:]
        elif damage == "version":
            manifest = json.loads(members["manifest.json"])
            manifest["version"] = 9000
            members["manifest.json"] = json.dumps(manifest).encode()
        else:
            members.pop("database.dump")
        with zipfile.ZipFile(broken, "w") as archive:
            for name, data in members.items():
                archive.writestr(name, data)
    with pytest.raises(ValueError):
        recovery.restore_backup(
            env.admin_dsn,
            broken,
            database_name=destination,
            deletion_ledger=ledger,
            credentials_output=tmp_path / "owner.json",
            pg_bin=pg_bin,
        )
    assert not exists(env.admin_dsn, destination) and not (tmp_path / "owner.json").exists()


def test_restore_disk_failure_does_not_publish_database(
    env, pg_bin, tmp_path, destination, monkeypatch
):
    source, ledger = tmp_path / "backup.mnemion", tmp_path / "ledger.json"
    recovery.create_backup(env.admin_dsn, source, pg_bin=pg_bin)
    recovery.export_ledger(env.admin_dsn, ledger)

    def full(*args):
        raise OSError("disk full")

    monkeypatch.setattr(recovery, "private_json", full)
    with pytest.raises(OSError, match="disk full"):
        recovery.restore_backup(
            env.admin_dsn,
            source,
            database_name=destination,
            deletion_ledger=ledger,
            credentials_output=tmp_path / "owner.json",
            pg_bin=pg_bin,
        )
    assert not exists(env.admin_dsn, destination)
    with psycopg.connect(env.admin_dsn) as conn:
        assert (
            conn.execute(
                "SELECT datname FROM pg_database WHERE datname LIKE 'mnemion_restore_%'"
            ).fetchall()
            == []
        )


def test_restore_rejects_a_stale_ledger_and_existing_database(env, pg_bin, tmp_path, destination):
    source, ledger = tmp_path / "backup.mnemion", tmp_path / "ledger.json"
    recovery.export_ledger(env.admin_dsn, ledger)
    recovery.create_backup(env.admin_dsn, source, pg_bin=pg_bin)
    with pytest.raises(ValueError, match="at least as recent"):
        recovery.restore_backup(
            env.admin_dsn,
            source,
            database_name=destination,
            deletion_ledger=ledger,
            credentials_output=tmp_path / "owner.json",
            pg_bin=pg_bin,
        )
    current = tmp_path / "current.json"
    recovery.export_ledger(env.admin_dsn, current)
    with psycopg.connect(env.admin_dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(destination)))
    with pytest.raises(ValueError, match="already exists"):
        recovery.restore_backup(
            env.admin_dsn,
            source,
            database_name=destination,
            deletion_ledger=current,
            credentials_output=tmp_path / "owner.json",
            pg_bin=pg_bin,
        )
    assert exists(env.admin_dsn, destination)
