"""Actual database/API recovery must not resurrect or overwrite private decisions."""

import json
from uuid import UUID, uuid4

import pytest
from psycopg.conninfo import make_conninfo

from mnemion import agent_control
from mnemion.journal.format import JournalCatalog, JournalEntry
from mnemion.sdk import Client
from mnemion.service import recovery
from mnemion.service.admin import bootstrap_tenant
from mnemion.service.api import create_app
from mnemion.service.db import Database
from mnemion.service.errors import ServiceError
from mnemion.service.journal_recovery import JournalRecoveryService
from mnemion.service.journal_recovery_models import JournalRecoveryApply, JournalRecoveryInput
from mnemion.service.memory import MemoryService
from mnemion.service.models import MemoryInput, ReviewInput, RevisionInput, SpaceInput
from service_tests.test_clients import running
from service_tests.test_memory_journal import git
from service_tests.test_recovery import destination as destination
from service_tests.test_writeback import identity, setup

TENANT, SPACE, WRITER = uuid4(), uuid4(), uuid4()


def entry(**changes):
    return JournalEntry(
        **{
            "id": uuid4(),
            "ts": "2026-10-01T10:20:30Z",
            "tenant_id": TENANT,
            "space_id": SPACE,
            "memory_id": uuid4(),
            "version": 1,
            "writer": WRITER,
            "subject": "Continuity",
            "text": "PostgreSQL journal continuity — mémoire 🌌",
            **changes,
        }
    )


def next_entry(previous, *, action="upsert", **changes):
    return JournalEntry.model_validate(
        {
            **previous.model_dump(),
            "id": uuid4(),
            "version": previous.version + 1,
            "action": action,
            **({"text": None, "subject": None, "metadata": {}} if action != "upsert" else {}),
            **changes,
        }
    )


def command(*entries, withdrawn=(), archived=False, **changes):
    catalog = JournalCatalog(
        tenant_id=entries[0].tenant_id if entries else TENANT,
        space_id=entries[0].space_id if entries else SPACE,
        records=len({row.id for row in entries}),
    )
    grouped = {}
    for row in entries:
        path = ("_archive/" if archived else "") + row.relative_path
        grouped[path] = grouped.get(path, "") + row.line().decode()
    return JournalRecoveryInput(
        catalog=catalog.encoded().decode(),
        files=[{"path": path, "text": value} for path, value in grouped.items()],
        withdrawn_ids=list(withdrawn),
        **changes,
    )


def approved(input, preview):
    return JournalRecoveryApply(
        **input.model_dump(),
        preview_sha256=preview["preview_sha256"],
        reviewed_complete_inventory=True,
        reviewed_withdrawals=True,
        acknowledge_source_only=True,
    )


def restore(service, env, input, key="recovery", space=None):
    space = space or env.space
    preview = service.preview(env.owner, space, input)
    return service.apply(env.owner, space, approved(input, preview), key)


def test_complete_archive_creates_editable_content_and_stable_identity(env):
    service = JournalRecoveryService(env.memory)
    first = entry(kind="procedure", metadata={"tags": ["continuity"]})
    newer = next_entry(first, text="PostgreSQL durable recovery — mémoire 🌌")
    input = command(first, newer, first, archived=True)
    preview = service.preview(env.owner, env.space, input)
    assert preview["records"] == 2 and preview["duplicates"] == 1
    assert preview["counts"] == {"create": 1}
    assert not env.memory.list(env.owner, env.space)["items"]
    permit = approved(input, preview)
    result = service.apply(env.owner, env.space, permit, "reviewed-recovery")
    assert service.apply(env.owner, env.space, permit, "reviewed-recovery") == result
    assert result["source_only"] and not result["remote_delivery_verified"]
    memory = UUID(result["items"][0]["memory_id"])
    assert memory == first.memory_id
    fetched = env.memory.fetch(env.owner, memory)
    assert fetched["content"] == newer.text and fetched["kind"] == "procedure"
    assert fetched["created_by"] == str(env.owner.principal_id)
    assert fetched["metadata"]["journal_recovery"]["origin"] == first.origin
    assert fetched["metadata"]["journal_recovery"]["writer"] == str(WRITER)
    assert fetched["metadata"]["journal_recovery"]["metadata"] == first.metadata
    env.memory.revise(
        env.owner,
        memory,
        RevisionInput(
            content="Local reviewed correction", expected_version=1, reason="New local decision"
        ),
        "local-correction",
    )
    again = restore(service, env, input, "same-original")
    assert again["items"][0]["memory_id"] == str(memory)
    assert again["counts"] == {"preserved_changes": 1}
    assert env.memory.fetch(env.owner, memory)["content"] == "Local reviewed correction"


def test_newer_complete_snapshots_update_only_untouched_native_copies(env):
    service = JournalRecoveryService(env.memory)
    first = entry()
    result = restore(service, env, command(first))
    memory = UUID(result["items"][0]["memory_id"])
    second = next_entry(first, text="Newer PostgreSQL evidence")
    assert restore(service, env, command(first, second), "new-source")["counts"] == {"update": 1}
    assert env.memory.fetch(env.owner, memory)["content"] == second.text
    assert restore(service, env, command(first), "old-source")["counts"] == {"stale_source": 1}
    env.memory.revise(
        env.owner,
        memory,
        RevisionInput(content="Human decision", expected_version=2, reason="New local decision"),
        "human-edit",
    )
    third = next_entry(second, text="Conflicting later source")
    assert restore(service, env, command(first, second, third), "later-source")["counts"] == {
        "preserved_changes": 1
    }
    assert env.memory.fetch(env.owner, memory)["content"] == "Human decision"


def test_original_id_collisions_are_refused_and_independent_copies_are_explicit(env):
    service = JournalRecoveryService(env.memory)
    first = entry()
    restore(service, env, command(first))
    other = UUID(env.identities.create_space(env.owner, SpaceInput(name="Separate copy"))["id"])
    preview = service.preview(env.owner, other, command(first))
    assert preview["counts"] == {"conflict": 1} and not preview["can_restore"]
    copied = command(first, identity_mode="copy")
    result = restore(service, env, copied, "independent-copy", space=other)
    assert result["identity_mode"] == "copy"
    assert result["items"][0]["memory_id"] != str(first.memory_id)
    assert restore(service, env, copied, "same-independent-copy", space=other)["counts"] == {
        "already_restored": 1
    }


def test_nonadministrator_cannot_probe_another_spaces_identity(env):
    service = JournalRecoveryService(env.memory)
    first = entry()
    restore(service, env, command(first))
    principal = identity(env, "administrator")
    with env.db.transaction(principal) as conn:
        assert (
            conn.execute(
                "SELECT mnemion.recovery_identity_available(%s,%s) AS allowed",
                (env.space, uuid4()),
            ).fetchone()["allowed"]
            is False
        )


def test_forget_dominates_later_positive_record_and_survives_purge(env):
    service = JournalRecoveryService(env.memory)
    first = entry()
    result = restore(service, env, command(first))
    memory = UUID(result["items"][0]["memory_id"])
    deleted = next_entry(first, action="forget")
    invalid_resurrection = next_entry(deleted, text="Must remain withdrawn", action="upsert")
    assert restore(service, env, command(first, deleted, invalid_resurrection), "denied")[
        "counts"
    ] == {"withdraw": 1}
    while env.worker.run_once():
        pass
    assert restore(service, env, command(first), "older-copy")["counts"] == {"withdrawn": 1}
    with pytest.raises(ServiceError) as missing:
        env.memory.fetch(env.owner, memory, review=True)
    assert missing.value.status == 404


def test_out_of_snapshot_withdrawal_and_local_deletion_block_later_recovery(env):
    service = JournalRecoveryService(env.memory)
    first, absent = entry(), entry()
    result = restore(service, env, command(first, withdrawn=[absent.memory_id]))
    assert result["counts"] == {"create": 1, "deny": 1} or result["counts"] == {
        "deny": 1,
        "create": 1,
    }
    memory = UUID(next(row["memory_id"] for row in result["items"] if row["action"] == "create"))
    env.memory.forget(env.owner, memory, expected_version=1, key="manual-forget")
    assert restore(service, env, command(first, absent), "old-input")["counts"] == {"withdrawn": 2}


def test_quarantine_without_any_text_is_retained_without_a_fake_memory(env):
    service = JournalRecoveryService(env.memory)
    old = entry()
    quarantined = next_entry(old, action="quarantine")
    result = restore(service, env, command(quarantined))
    assert result["counts"] == {"hold": 1}
    assert env.memory.list(env.owner, env.space, review=True)["items"] == []
    assert restore(service, env, command(old), "old-positive")["counts"] == {"stale_source": 1}
    released = next_entry(quarantined, text="Reviewed release", action="upsert")
    result = restore(service, env, command(quarantined, released), "released")
    assert result["counts"] == {"release": 1}
    assert (
        env.memory.fetch(env.owner, UUID(result["items"][0]["memory_id"]))["content"]
        == released.text
    )


@pytest.mark.parametrize("edited", [False, True])
def test_quarantine_and_release_preserve_prior_local_edits(env, edited):
    service = JournalRecoveryService(env.memory)
    first = entry()
    result = restore(service, env, command(first))
    memory = UUID(result["items"][0]["memory_id"])
    if edited:
        env.memory.revise(
            env.owner,
            memory,
            RevisionInput(
                content="Private local decision", expected_version=1, reason="New local decision"
            ),
            "local-decision",
        )
    held = next_entry(first, action="quarantine")
    assert restore(service, env, command(first, held), "hold-existing")["counts"] == {
        "quarantine": 1
    }
    with pytest.raises(ServiceError):
        env.memory.fetch(env.owner, memory)
    released = next_entry(held, text="Released upstream", action="upsert")
    result = restore(service, env, command(first, held, released), "release-existing")
    assert result["counts"] == ({"preserved_changes": 1} if edited else {"update": 1})
    fetched = env.memory.fetch(env.owner, memory, review=True)
    assert fetched["content"] == ("Private local decision" if edited else "Released upstream")
    assert fetched["review_state"] == ("quarantined" if edited else "ordinary")


@pytest.mark.parametrize(
    "problem",
    [
        "missing",
        "partial",
        "namespace",
        "path",
        "duplicate-path",
        "event-conflict",
        "version-conflict",
        "bytes",
    ],
)
def test_invalid_or_partial_inventory_is_rejected_before_any_write(env, problem):
    first = entry()
    input = command(first)
    body = {
        "catalog": input.catalog.get_secret_value(),
        "files": [{"path": f.path, "text": f.text.get_secret_value()} for f in input.files],
        "withdrawn_ids": [],
    }
    if problem == "missing":
        body["files"] = []
    elif problem == "partial":
        body["files"][0]["text"] = body["files"][0]["text"].rstrip("\n")
    elif problem == "namespace":
        body["catalog"] = (
            JournalCatalog(tenant_id=uuid4(), space_id=SPACE, records=1).encoded().decode()
        )
    elif problem == "path":
        body["files"][0]["path"] = "../" + body["files"][0]["path"]
    elif problem == "duplicate-path":
        body["files"] *= 2
    elif problem in {"event-conflict", "version-conflict"}:
        other = first.model_copy(
            update={"text": "Changed", **({"id": uuid4()} if problem == "version-conflict" else {})}
        )
        body["files"][0]["text"] += other.line().decode()
    else:
        body["files"][0]["text"] = first.line().decode() * (1048576 // len(first.line()))
        body["catalog"] += " " * 409
    with pytest.raises(ServiceError):
        JournalRecoveryService(env.memory).preview(
            env.owner, env.space, JournalRecoveryInput(**body)
        )
    assert env.memory.list(env.owner, env.space)["items"] == []


def test_conflicting_record_and_changed_destination_require_new_review(env):
    service = JournalRecoveryService(env.memory)
    first = entry()
    input = command(first)
    preview = service.preview(env.owner, env.space, input)
    restore(service, env, input)
    with pytest.raises(ServiceError, match="destination changed"):
        service.apply(env.owner, env.space, approved(input, preview), "stale-preview")
    changed = command(first.model_copy(update={"text": "Same version, conflicting bytes"}))
    preview = service.preview(env.owner, env.space, changed)
    assert not preview["can_restore"] and preview["counts"] == {"conflict": 1}
    with pytest.raises(ServiceError, match="Resolve conflicting"):
        service.apply(env.owner, env.space, approved(changed, preview), "conflict")


def test_privacy_checks_reject_whole_recovery_and_do_not_leak_content(env):
    service = JournalRecoveryService(env.memory)
    private_value = "fixture-private-sentinel-for-scanner"
    input = command(entry(), entry(metadata={"api_key": private_value}))
    preview = service.preview(env.owner, env.space, input)
    assert preview["counts"]["rejected"] == 1 and not preview["can_restore"]
    assert private_value not in json.dumps(preview)
    with pytest.raises(ServiceError):
        service.apply(env.owner, env.space, approved(input, preview), "privacy-refusal")
    assert env.memory.list(env.owner, env.space)["items"] == []


@pytest.mark.parametrize("role", ["reader", "contributor", "reviewer", "administrator"])
def test_space_grants_are_not_organization_import_authority(env, role):
    principal = identity(env, role)
    with pytest.raises(ServiceError) as denied:
        JournalRecoveryService(env.memory).preview(principal, env.space, command(entry()))
    assert denied.value.status == 403
    with env.db.transaction(principal) as conn:
        assert not conn.execute("SELECT 1 FROM mnemion.journal_recovery_origins").fetchone()


def test_shared_or_published_destinations_are_refused(env, tmp_path):
    service = JournalRecoveryService(env.memory)
    setup(env, tmp_path)
    with pytest.raises(ServiceError, match="private native space"):
        service.preview(env.owner, env.space, command(entry()))
    assert env.memory.list(env.owner, env.space)["items"] == []


def test_transaction_failure_rolls_back_content_origins_and_withdrawals(env, monkeypatch):
    service = JournalRecoveryService(env.memory)
    input = command(entry(), entry(), withdrawn=[uuid4()])
    operation = env.memory._operation
    count = 0

    def fail_later(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("Fixture storage failure")
        return operation(*args, **kwargs)

    monkeypatch.setattr(env.memory, "_operation", fail_later)
    with pytest.raises(RuntimeError, match="Fixture storage failure"):
        restore(service, env, input)
    with env.db.transaction(env.owner) as conn:
        for table in ("memories", "journal_recovery_origins", "recovery_denials"):
            assert not conn.execute(f"SELECT 1 FROM mnemion.{table}").fetchone()


def test_actual_published_git_journal_restores_original_ids_into_a_fresh_organization(
    env, tmp_path
):
    publisher, destination = setup(env, tmp_path)
    source = env.memory.save(
        env.owner, env.space, MemoryInput(content="PostgreSQL off-host continuity"), "original"
    )
    publisher.push(env.owner, env.space)
    prefix = destination.prefix + "/"
    paths = (
        git(destination.local_repository, "ls-tree", "-r", "--name-only", "main")
        .decode()
        .splitlines()
    )
    catalog = git(destination.local_repository, "show", "main:" + prefix + "catalog.json").decode()
    files = [
        {
            "path": path.removeprefix(prefix),
            "text": git(destination.local_repository, "show", "main:" + path).decode(),
        }
        for path in paths
        if path.startswith(prefix) and path.endswith(".jsonl")
    ]
    fresh = bootstrap_tenant(
        env.admin_dsn,
        tenant_name="Replacement host",
        administrator_name="Recovery operator",
        generation=env.embedder.generation,
    )
    owner = env.db.authenticate(fresh["api_key"])
    private_space = UUID(fresh["space_id"])
    service = JournalRecoveryService(env.memory)
    input = JournalRecoveryInput(catalog=catalog, files=files, withdrawn_ids=[])
    preview = service.preview(owner, private_space, input)
    result = service.apply(
        owner,
        private_space,
        approved(input, preview),
        "recover-published-git",
    )
    recovered = env.memory.fetch(owner, UUID(result["items"][0]["memory_id"]))
    assert recovered["space_id"] == str(private_space)
    assert recovered["content"] == "PostgreSQL off-host continuity"
    assert result["items"][0]["original_id"] == source["memory_id"]
    assert result["items"][0]["memory_id"] == source["memory_id"]
    with env.db.transaction(owner) as conn:
        assert not conn.execute(
            "SELECT 1 FROM mnemion.writeback_events WHERE space_id=%s",
            (private_space,),
        ).fetchone()


def test_full_database_recovery_retains_origins_and_newer_withdrawals(
    env, postgres, pg_bin, tmp_path, destination
):
    first, old_held = entry(), entry()
    held = next_entry(old_held, action="quarantine")
    restore(JournalRecoveryService(env.memory), env, command(first, held))
    archive, ledger, credentials = (
        tmp_path / name for name in ("journal.mnemion", "ledger.json", "owner.json")
    )
    recovery.create_backup(env.admin_dsn, archive, pg_bin=pg_bin)
    env.memory.forget(env.owner, first.memory_id, expected_version=1, key="later-denial")
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
        account = next(
            row
            for row in json.loads(credentials.read_text())["organizations"]
            if row["tenant_id"] == str(env.owner.tenant_id)
        )
        caller = db.authenticate(account["api_key"])
        service = JournalRecoveryService(MemoryService(db, env.embedder.generation))
        assert service.preview(caller, env.space, command(first))["counts"] == {"withdrawn": 1}
        assert service.preview(caller, env.space, command(old_held))["counts"] == {
            "stale_source": 1
        }
        with db.transaction(caller) as conn:
            assert (
                conn.execute(
                    "SELECT count(*) AS n FROM mnemion.journal_recovery_origins WHERE space_id=%s",
                    (env.space,),
                ).fetchone()["n"]
                == 2
            )
    finally:
        db.close()


def test_http_sdk_and_private_agent_contract_use_the_same_recovery(env):
    app = create_app(env.db, env.embedder, mcp_enabled=False, studio_enabled=False)
    with running(app) as url, Client(url, env.token) as client:
        input = command(entry())
        preview = client.preview_journal_recovery(str(env.space), input)
        result = client.restore_journal(
            str(env.space),
            approved(input, preview.model_dump()),
            idempotency_key="sdk-native-restore",
        )
        assert result.counts == {"create": 1}
        found = client.search("PostgreSQL journal continuity", [str(env.space)])
        assert str(result.items[0].memory_id) in found.model_dump_json()
    for name in ("memory.journal.preview", "memory.journal.restore"):
        operation = agent_control.describe(name)
        assert operation["sensitive_input"] is True


@pytest.mark.parametrize("local_edit", [False, True])
def test_current_ledger_preserves_holds_created_after_the_backup(
    env, postgres, pg_bin, tmp_path, destination, local_edit
):
    first, missing, absent_space_entry = entry(), entry(), entry()
    service = JournalRecoveryService(env.memory)
    restore(service, env, command(first))
    archive, ledger, credentials = (
        tmp_path / name for name in ("before-holds.mnemion", "current.json", "owner.json")
    )
    recovery.create_backup(env.admin_dsn, archive, pg_bin=pg_bin)
    if local_edit:
        env.memory.revise(
            env.owner,
            first.memory_id,
            RevisionInput(
                content="Later local correction", expected_version=1, reason="Human review"
            ),
            "later-edit",
        )
    held, held_missing, held_absent = (
        next_entry(item, action="quarantine") for item in (first, missing, absent_space_entry)
    )
    restore(service, env, command(first, held, held_missing), "later-holds")
    other = UUID(env.identities.create_space(env.owner, SpaceInput(name="After backup"))["id"])
    restore(service, env, command(held_absent), "later-space-hold", space=other)
    recovery.export_ledger(env.admin_dsn, ledger)
    exported = recovery.read_ledger(ledger)
    assert exported["version"] == 2
    scoped_holds = [
        row
        for row in exported["journal_recovery_state"]["quarantines"]
        if row["tenant_id"] == str(env.owner.tenant_id)
    ]
    assert len(scoped_holds) == 3
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
        account = next(
            row
            for row in json.loads(credentials.read_text())["organizations"]
            if row["tenant_id"] == str(env.owner.tenant_id)
        )
        caller = db.authenticate(account["api_key"])
        memory = MemoryService(db, env.embedder.generation)
        recovered = JournalRecoveryService(memory)
        assert not memory.list(caller, env.space)["items"]
        assert memory.fetch(caller, first.memory_id, review=True)["review_state"] == "quarantined"
        assert recovered.preview(caller, env.space, command(first, missing))["counts"] == {
            "stale_source": 2
        }
        with db.transaction(caller) as conn:
            assert not conn.execute(
                "SELECT 1 FROM mnemion.memories WHERE id=%s", (missing.memory_id,)
            ).fetchone()
        # The negative identity survives without fabricating a missing space or grant.
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(
            make_conninfo(postgres[0], dbname=destination), row_factory=dict_row
        ) as conn:
            assert not conn.execute("SELECT 1 FROM mnemion.spaces WHERE id=%s", (other,)).fetchone()
            assert (
                conn.execute(
                    "SELECT source_action FROM mnemion.journal_recovery_origins WHERE space_id=%s",
                    (other,),
                ).fetchone()["source_action"]
                == "quarantine"
            )
        released = next_entry(held, text="Reviewed source release")
        input = command(first, held, released)
        preview = recovered.preview(caller, env.space, input)
        assert preview["counts"] == {"preserved_changes" if local_edit else "update": 1}
        recovered.apply(caller, env.space, approved(input, preview), "reviewed-release")
        found = memory.fetch(caller, first.memory_id, review=True)
        assert found["review_state"] == ("quarantined" if local_edit else "ordinary")
        assert found["content"] == (first.text if local_edit else released.text)
    finally:
        db.close()


def test_ledger_preserves_later_manual_quarantine_of_a_recovered_memory(
    env, postgres, pg_bin, tmp_path, destination
):
    first = entry()
    restore(JournalRecoveryService(env.memory), env, command(first))
    archive, ledger, credentials = (
        tmp_path / name for name in ("before-review.mnemion", "current.json", "owner.json")
    )
    recovery.create_backup(env.admin_dsn, archive, pg_bin=pg_bin)
    env.memory.review(
        env.owner,
        first.memory_id,
        ReviewInput(expected_version=1, state="quarantined", reason="Needs administrator review"),
    )
    recovery.export_ledger(env.admin_dsn, ledger)
    captured = next(
        row
        for row in recovery.read_ledger(ledger)["journal_recovery_state"]["quarantines"]
        if row["memory_id"] == str(first.memory_id)
    )
    assert captured["source_action"] == "upsert" and captured["locally_modified"]
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
        account = next(
            row
            for row in json.loads(credentials.read_text())["organizations"]
            if row["tenant_id"] == str(env.owner.tenant_id)
        )
        caller = db.authenticate(account["api_key"])
        memory = MemoryService(db, env.embedder.generation)
        assert not memory.list(caller, env.space)["items"]
        assert JournalRecoveryService(memory).preview(caller, env.space, command(first))[
            "counts"
        ] == {"preserved_changes": 1}
    finally:
        db.close()


@pytest.mark.parametrize(
    "damage",
    ["duplicate", "unknown_tenant", "digest", "version", "date", "positive", "extra", "origin"],
)
def test_invalid_quarantine_ledger_is_rejected_before_recovery(damage):
    from mnemion.service.journal_recovery_ledger import validate

    first = entry()
    row = {
        "tenant_id": str(TENANT),
        "space_id": str(SPACE),
        "origin": first.origin,
        "memory_id": str(first.memory_id),
        "source_version": 2,
        "source_digest": "a" * 64,
        "source_action": "quarantine",
        "locally_modified": False,
        "updated_at": "2026-10-19T20:00:00+00:00",
    }
    value = {"version": 1, "quarantines": [row]}
    validate(value, {str(TENANT)})
    if damage == "duplicate":
        value["quarantines"].append(row.copy())
    elif damage == "unknown_tenant":
        row["tenant_id"] = str(uuid4())
    elif damage == "digest":
        row["source_digest"] = "not-a-digest"
    elif damage == "version":
        row["source_version"] = True
    elif damage == "date":
        row["updated_at"] = "2026-10-19T20:00:00"
    elif damage == "positive":
        row["source_action"] = "upsert"
    elif damage == "extra":
        row["content"] = "A ledger cannot restore positive content"
    else:
        row["origin"] = "not-an-origin"
    with pytest.raises(ValueError, match="Invalid journal quarantine"):
        validate(value, {str(TENANT)})


def test_ledger_version_requires_aware_reader_and_complete_extension(tmp_path):
    import hashlib

    from mnemion.service.recovery import canonical_json

    path = tmp_path / "ledger.json"
    value = {
        "format": recovery.LEDGER_FORMAT,
        "version": 2,
        "snapshot_at": "2026-10-19T20:00:00+00:00",
        "tenant_ids": [str(TENANT)],
        "deletions": [],
        "principals": [],
        "grants": [],
    }

    def write():
        path.write_bytes(
            canonical_json({**value, "sha256": hashlib.sha256(canonical_json(value)).hexdigest()})
        )

    write()
    with pytest.raises(ValueError, match="requires journal quarantine state"):
        recovery.read_ledger(path)
    value["version"] = 1
    write()
    assert recovery.read_ledger(path)["version"] == 1
    first = entry()
    value["journal_recovery_state"] = {
        "version": 1,
        "quarantines": [
            {
                "tenant_id": str(TENANT),
                "space_id": str(SPACE),
                "origin": first.origin,
                "memory_id": str(first.memory_id),
                "source_version": 2,
                "source_digest": "a" * 64,
                "source_action": "quarantine",
                "locally_modified": False,
                "updated_at": value["snapshot_at"],
            }
        ],
    }
    write()
    with pytest.raises(ValueError, match="require a version 2"):
        recovery.read_ledger(path)
    value["version"] = 2
    write()
    assert recovery.read_ledger(path)["version"] == 2
