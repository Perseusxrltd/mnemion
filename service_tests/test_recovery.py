import io
import json
import os
import zipfile
from pydantic import SecretStr
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


def test_recovery_erases_librarian_derivatives_and_pauses_model_schedules(
    env, postgres, pg_bin, tmp_path, destination
):
    from service_tests.test_librarian import setup, save, drain
    from mnemion.service.librarian import LibrarianService
    from mnemion.service.librarian_models import LibrarianRunInput

    service, runner = setup(env, interval=60)
    records = [
        save(env, content=f"Librarian recovery source {index}", key=f"librarian-recovery-{index}")
        for index in range(3)
    ]
    service.create_run(env.owner, env.space, LibrarianRunInput(mode="review"), "recovery-proposals")
    drain(runner)
    proposal = service.proposals(env.owner, env.space)["items"][0]
    queued = service.create_run(env.owner, env.space, LibrarianRunInput(), "queued-before-recovery")
    archive, ledger, credentials = (
        tmp_path / name for name in ("librarian.mnemion", "ledger.json", "owner.json")
    )
    recovery.create_backup(env.admin_dsn, archive, pg_bin=pg_bin)
    cited = {quote["memory_id"] for quote in proposal["suggestion"]["evidence"]}
    doomed = next(record for record in records if record["memory_id"] not in cited)
    env.memory.forget(
        env.owner, UUID(doomed["memory_id"]), expected_version=1, key="withdraw-after-backup"
    )
    recovery.export_ledger(env.admin_dsn, ledger)
    recovery.restore_backup(
        env.admin_dsn,
        archive,
        database_name=destination,
        deletion_ledger=ledger,
        credentials_output=credentials,
        pg_bin=pg_bin,
    )
    db = Database(make_conninfo(postgres[1], dbname=destination))
    db.open()
    try:
        owner = next(
            row
            for row in json.loads(credentials.read_text())["organizations"]
            if row["tenant_id"] == str(env.owner.tenant_id)
        )
        identity = db.authenticate(owner["api_key"])
        restored = LibrarianService(
            db, service.registry, MemoryService(db, env.embedder.generation)
        )
        settings = restored.settings(identity, env.space)
        assert (
            not settings["enabled"]
            and not settings["network_egress_approved"]
            and settings["next_run_at"] is None
        )
        assert restored.run(identity, env.space, UUID(queued["id"]))["state"] == "cancelled"
        hidden = restored.proposals(identity, env.space)["items"][0]
        assert hidden["state"] == "invalidated" and hidden["suggestion"] is None
        with db.transaction(identity) as conn:
            assert (
                conn.execute(
                    "SELECT suggestion FROM mnemion.librarian_proposals WHERE id=%s",
                    (proposal["id"],),
                ).fetchone()["suggestion"]
                is None
            )
        with pytest.raises(ServiceError):
            db.authenticate(env.token)
    finally:
        db.close()
        service.registry.close()


def test_complete_recovery_reconciles_later_deletion_grants_and_keys(
    env, postgres, pg_bin, tmp_path, destination
):
    from mnemion.service.recovery_directory import RecoveryDirectoryInput, RecoveryDirectoryService
    from service_tests.test_recovery_directory import directory
    from service_tests.test_writeback import setup as setup_journal

    journal_service, journal_destination = setup_journal(env, tmp_path)

    directory_service = RecoveryDirectoryService(env.db)
    saved_directory = directory_service.update(
        env.owner, RecoveryDirectoryInput(expected_revision=0, directory=directory())
    )
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
    from mnemion.service.backfill_models import BackfillStartInput

    backfill = journal_service.start_backfill(
        env.owner,
        env.space,
        BackfillStartInput(
            expected_version=1,
            publish_existing_memories=True,
            acknowledge_retained_git_history=True,
        ),
        "recovery-backfill",
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
        restored_directory = RecoveryDirectoryService(db)
        assert restored_directory.get(identity) == saved_directory
        changed_directory = restored_directory.update(
            identity,
            RecoveryDirectoryInput(
                expected_revision=1, directory={"instructions": "Restored host"}
            ),
        )
        assert changed_directory["revision"] == 2
        assert changed_directory["updated_by"] == str(identity.principal_id)
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
            assert conn.execute(
                "SELECT paused,last_error FROM mnemion.writeback_settings WHERE space_id=%s",
                (env.space,),
            ).fetchone() == {"paused": True, "last_error": "recovery_revalidation_required"}
            assert not conn.execute(
                "SELECT FROM mnemion.writeback_events WHERE memory_id=%s AND action='upsert' AND state IN ('pending','local')",
                (doomed["memory_id"],),
            ).fetchone()
        from mnemion.journal.config import Configuration
        from mnemion.service.writeback import WritebackService

        restored_journal = WritebackService(db, Configuration(destinations=[journal_destination]))
        restored_backfill = restored_journal.backfill_status(identity, env.space)
        assert restored_backfill["run"]["id"] == backfill["run"]["id"]
        assert restored_backfill["waiting_reason"] == "journal_paused"
        assert restored_journal.backfill_batch(identity, env.space)["examined"] == 0
        assert not restored_journal.run_once()
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


def test_restore_requires_fresh_model_endpoint_consent(
    env, postgres, pg_bin, tmp_path, destination
):
    import httpx
    from mnemion.service.admin import register_generation
    from mnemion.service.embedding_models import ReindexControl, ReindexInput
    from mnemion.service.http_embeddings import HttpEmbedder
    from mnemion.service.model_config import RemoteEmbeddingProfile
    from mnemion.service.model_registry import ModelRegistry
    from mnemion.service.reindex import ReindexBackfill, ReindexService
    from mnemion.service.worker import Worker

    calls = []

    def respond(request):
        inputs = json.loads(request.content)["input"]
        calls.append(len(inputs))
        return httpx.Response(
            200,
            json={
                "model": "fixture-model",
                "data": [{"index": index, "embedding": [1, 0]} for index, _ in enumerate(inputs)],
            },
        )

    models = [
        HttpEmbedder(
            RemoteEmbeddingProfile(
                id=f"cloud-{index}",
                label=f"Cloud fixture {index}",
                protocol="openai",
                endpoint="https://fixture.example/v1/embeddings",
                model="fixture-model",
                revision=str(index),
                dimensions=2,
            ),
            tmp_path,
            transport=httpx.MockTransport(respond),
        )
        for index in (1, 2)
    ]
    registry = ModelRegistry(
        env.embedder, {"baseline": env.embedder, "cloud-1": models[0], "cloud-2": models[1]}
    )
    with psycopg.connect(env.admin_dsn) as conn:
        for model in models:
            register_generation(conn, model.generation)
    env.memory.save(
        env.owner, env.space, MemoryInput(content="synthetic backup policy evidence"), uuid4().hex
    )
    service = ReindexService(env.db, registry)
    state = service.start(
        env.owner,
        env.space,
        ReindexInput(profile_id="cloud-1", expected_version=0, approve_network_egress=True),
        uuid4().hex,
    )
    backfill = ReindexBackfill(env.worker_db, registry)
    while backfill.run_once():
        pass
    worker = Worker(env.worker_db, models[0], default_generation=env.embedder.generation.id)
    while worker.run_once():
        pass
    state = service.control(
        env.owner, env.space, UUID(state["candidate"]["id"]), "activate", state["version"]
    )
    service.start(
        env.owner,
        env.space,
        ReindexInput(
            profile_id="cloud-2", expected_version=state["version"], approve_network_egress=True
        ),
        uuid4().hex,
    )
    archive, ledger, credentials = (
        tmp_path / name for name in ("models.mnemion", "ledger.json", "owners.json")
    )
    recovery.create_backup(env.admin_dsn, archive, pg_bin=pg_bin)
    recovery.export_ledger(env.admin_dsn, ledger)
    recovery.restore_backup(
        env.admin_dsn,
        archive,
        database_name=destination,
        deletion_ledger=ledger,
        credentials_output=credentials,
        pg_bin=pg_bin,
    )
    restored = Database(make_conninfo(postgres[1], dbname=destination))
    restored.open()
    try:
        owner = next(
            row
            for row in json.loads(credentials.read_text())["organizations"]
            if row["tenant_id"] == str(env.owner.tenant_id)
        )
        identity = restored.authenticate(owner["api_key"])
        service = ReindexService(restored, registry)
        state = service.read(identity, env.space)
        assert state["inference_paused"] and state["candidate"]["state"] == "paused"
        assert state["candidate"]["network_egress_approved"] is False
        previous_calls = len(calls)
        result = RetrievalService(restored, env.embedder, registry=registry).recall(
            identity, RecallInput(query="backup", space_ids=[env.space])
        )
        assert result["hits"] and "semantic_unavailable_lexical_only" in result["warnings"]
        assert len(calls) == previous_calls
        with pytest.raises(ServiceError) as caught:
            service.resume_processing(
                identity, env.space, ReindexControl(expected_version=state["version"])
            )
        assert caught.value.code == "embedding_egress_approval_required"
        state = service.resume_processing(
            identity,
            env.space,
            ReindexControl(expected_version=state["version"], approve_network_egress=True),
        )
        assert not state["inference_paused"]
        with pytest.raises(ServiceError) as caught:
            service.control(
                identity, env.space, UUID(state["candidate"]["id"]), "resume", state["version"]
            )
        assert caught.value.code == "embedding_egress_approval_required"
        state = service.control(
            identity,
            env.space,
            UUID(state["candidate"]["id"]),
            "resume",
            state["version"],
            approve_network_egress=True,
        )
        assert (
            state["candidate"]["state"] == "running"
            and state["candidate"]["network_egress_approved"]
        )
        assert len(calls) == previous_calls
    finally:
        restored.close()
        registry.close()


@pytest.mark.parametrize("transport", ["native", "browser"])
def test_restore_invalidates_passwords_invitations_and_rotating_sessions(
    env, postgres, pg_bin, tmp_path, destination, transport
):
    from mnemion.service.identity import IdentityService
    from mnemion.service.sign_in import (
        InvitationAcceptInput,
        InvitationInput,
        PasswordInput,
        SignInInput,
        SignInService,
    )

    original_password = "acorn comet satin harbour apricot"
    changed_password = "birch lantern cocoa summit calypso"
    restored_password = "paper orbit glacier meadow lantern"
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute("DELETE FROM mnemion.sign_in_attempts")
    service = SignInService(env.db)
    service.set_password(env.owner, PasswordInput(username="owner", password=original_password))
    login = SignInInput(
        workspace_id=env.owner.tenant_id,
        username="owner",
        password=original_password,
        device_name="Before restore",
        transport=transport,
    )
    first = service.sign_in(login)
    current = service.refresh(
        first["refresh_token"],
        transport=transport,
        csrf=first["csrf_token"],
        workspace=env.owner.tenant_id,
    )
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Pending recipient", kind="human")
    )
    invite = service.create_invitation(env.owner, InvitationInput(principal_id=UUID(person["id"])))
    saved = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="A durable memory before account recovery"),
        "account-recovery-memory",
    )
    archive, ledger, credentials = (
        tmp_path / name for name in ("accounts.mnemion", "ledger.json", "owner.json")
    )
    recovery.create_backup(env.admin_dsn, archive, pg_bin=pg_bin)
    service.set_password(
        env.owner,
        PasswordInput(
            username="owner", password=changed_password, current_password=original_password
        ),
    )
    service.revoke_invitation(env.owner, UUID(invite["id"]))
    recovery.export_ledger(env.admin_dsn, ledger)
    recovery.restore_backup(
        env.admin_dsn,
        archive,
        database_name=destination,
        deletion_ledger=ledger,
        credentials_output=credentials,
        pg_bin=pg_bin,
    )
    database = Database(make_conninfo(postgres[1], dbname=destination))
    database.open()
    try:
        restored = SignInService(database)
        for token in (env.token, first["access_token"], current["access_token"]):
            with pytest.raises(ServiceError) as rejected:
                database.authenticate(token)
            assert rejected.value.status == 401
        for issued in (first, current):
            with pytest.raises(ServiceError) as rejected:
                restored.refresh(
                    issued["refresh_token"],
                    transport=transport,
                    csrf=issued["csrf_token"],
                    workspace=env.owner.tenant_id,
                )
            assert rejected.value.status == 401
        for password in (original_password, changed_password):
            with pytest.raises(ServiceError) as rejected:
                restored.sign_in(login.model_copy(update={"password": SecretStr(password)}))
            assert rejected.value.status == 401
        with pytest.raises(ServiceError):
            restored.preview_invitation(invite["invitation_token"])
        with pytest.raises(ServiceError):
            restored.accept_invitation(
                InvitationAcceptInput(
                    invitation=invite["invitation_token"],
                    username="pending",
                    password=restored_password,
                    device_name="Stale invitation",
                    transport=transport,
                )
            )
        owner = next(
            row
            for row in json.loads(credentials.read_text())["organizations"]
            if row["tenant_id"] == str(env.owner.tenant_id)
        )
        identity = database.authenticate(owner["api_key"])
        assert identity.principal_id == env.owner.principal_id
        assert restored.account(identity)["account"]["reset_required"] is True
        fresh = restored.create_invitation(
            identity, InvitationInput(principal_id=identity.principal_id, purpose="reset")
        )
        issued = restored.accept_invitation(
            InvitationAcceptInput(
                invitation=fresh["invitation_token"],
                username="owner",
                password=restored_password,
                device_name="After restore",
                transport=transport,
            )
        )
        new_identity = database.authenticate(issued["access_token"])
        assert new_identity.principal_id == identity.principal_id
        assert IdentityService(database).me(new_identity)["administrator"]
        assert (
            MemoryService(database, env.embedder.generation).fetch(
                new_identity, UUID(saved["memory_id"])
            )["content"]
            == "A durable memory before account recovery"
        )
        assert database.authenticate(owner["api_key"]) == identity
    finally:
        database.close()
