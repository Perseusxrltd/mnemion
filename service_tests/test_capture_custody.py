"""Real PostgreSQL and HTTP custody acceptance, isolated from all user sources."""

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from psycopg import sql
from psycopg.conninfo import make_conninfo

from mnemion.capture_identity import canonical_capture_json, capture_event_id
from mnemion.connectors.live_conversations import ConversationProvider
from mnemion.service.api import create_app
from mnemion.service import recovery
from mnemion.service.capture_custody import CaptureCustody
from mnemion.service.capture_models import CaptureGrantInput, CapturePageInput, CaptureSourceInput
from mnemion.service.connector_models import BindingInput, ConnectorItemInput
from mnemion.service.errors import ServiceError
from mnemion.service.db import Database
from mnemion.service.identity import IdentityService
from mnemion.service.memory import MemoryService
from mnemion.service.models import GrantInput, KeyInput
from service_tests.test_live_conversations import (
    conversation_source as conversation_source,
    encoded,
)


def selected(config, text="Keep this selected user message", *, mode="messages"):
    config.provider.capture_mode = mode
    (config.provider.path / "chat.jsonl").write_bytes(
        encoded(text) + encoded("Excluded tool trace", "tool")
    )
    provider = ConversationProvider(config.provider)
    scope = provider.scopes()[0]
    with provider.snapshot(scope, None) as snapshot:
        items = [item for item in snapshot.items() if item is not None]
    return scope, items


def changed_revision(item, *, text="A second accepted revision", keep_revision=False):
    data = item.model_dump(mode="json")
    data["memory"]["content"] = text
    data["memory"]["source"]["content"] = text
    if not keep_revision:
        revision = hashlib.sha256(text.encode()).hexdigest()
        data["memory"]["metadata"]["source_revision"] = revision
        data["revision"] = hashlib.sha256((revision + ":mnemion-text-v1").encode()).hexdigest()
    return ConnectorItemInput.model_validate(data)


def page(source_id, scope, *items, page_id=None):
    return CapturePageInput.model_validate(
        {
            "page_id": str(page_id or uuid4()),
            "events": [
                {
                    "producer_scope": scope,
                    "item": item.model_dump(mode="json"),
                    "event_id": capture_event_id(source_id, scope, item.model_dump(mode="json")),
                }
                for item in items
            ],
        }
    )


@pytest.fixture
def custody(env, conversation_source):
    legacy, connector, operator, reader, secret, config = conversation_source
    service, source_id, grant_id = CaptureCustody(env.memory), uuid4(), uuid4()
    command = CaptureSourceInput(
        namespace="fixture",
        name="Durable conversations",
        members=["employee:reader"],
        capture_mode="messages",
        keep_accepted=True,
    )
    source = service.source(env.owner, connector, source_id, command)
    service.grant(env.owner, source_id, grant_id, CaptureGrantInput(device_key_id=operator.key_id))
    return service, source_id, grant_id, source, command


@pytest.mark.parametrize("mode", ["messages", "complete"])
def test_selected_events_survive_producer_disappearance_without_mirror_scopes(
    env, conversation_source, mode
):
    legacy, connector, operator, reader, secret, config = conversation_source
    service, source_id, grant_id = CaptureCustody(env.memory), uuid4(), uuid4()
    source = service.source(
        env.owner,
        connector,
        source_id,
        CaptureSourceInput(
            namespace="fixture",
            name="Custody",
            members=["employee:reader"],
            capture_mode=mode,
            keep_accepted=True,
        ),
    )
    service.grant(env.owner, source_id, grant_id, CaptureGrantInput(device_key_id=operator.key_id))
    scope, items = selected(config, mode=mode)
    request = page(source_id, scope, *items)
    (config.provider.path / "chat.jsonl").unlink()
    assert legacy.scopes(operator, connector)["items"] == []
    with TestClient(create_app(env.db, env.embedder)) as client:
        assert client.get("/health/live").json()["durable_capture"] == "v1"
        auth = {"Authorization": "Bearer " + secret}
        result = client.post(
            f"/v1/capture-grants/{grant_id}/pages",
            headers=auth,
            json=request.model_dump(mode="json"),
        )
        assert result.status_code == 200, result.text
        receipt = result.json()
        assert receipt["durable"] and all(item["outcome"] == "stored" for item in receipt["items"])
        replay = client.get(f"/v1/capture-grants/{grant_id}/pages/{request.page_id}", headers=auth)
        assert replay.json() == receipt
    values = [env.memory.fetch(reader, UUID(item["memory_id"])) for item in receipt["items"]]
    assert len(values) == (1 if mode == "messages" else 2)
    assert (
        all("Excluded tool trace" not in item["content"] for item in values)
        if mode == "messages"
        else any("Excluded tool trace" in item["content"] for item in values)
    )
    with env.db.transaction(operator) as conn:
        assert conn.execute(
            "SELECT count(*) AS n FROM mnemion.capture_events WHERE source_id=%s", (source_id,)
        ).fetchone()["n"] == len(items)
    assert UUID(source["space_id"]) != env.space


def test_every_accepted_revision_is_immutable_and_replay_does_not_create_more_memories(
    env, conversation_source, custody
):
    service, source_id, grant_id, source, _ = custody
    _, _, operator, reader, _, config = conversation_source
    scope, items = selected(config)
    first = page(source_id, scope, items[0])
    a = service.page(operator, grant_id, first)
    assert service.page(operator, grant_id, first) == a
    b = service.page(operator, grant_id, page(source_id, scope, changed_revision(items[0])))
    assert a["items"][0]["memory_id"] != b["items"][0]["memory_id"]
    assert (
        env.memory.fetch(reader, UUID(a["items"][0]["memory_id"]))["content"]
        == items[0].memory.content
    )
    with env.db.transaction(operator) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.memories WHERE space_id=%s",
                (UUID(source["space_id"]),),
            ).fetchone()["n"]
            == 2
        )


def test_changed_page_or_origin_revision_rolls_back_the_entire_page(
    env, conversation_source, custody
):
    service, source_id, grant_id, source, _ = custody
    _, _, operator, _, _, config = conversation_source
    scope, items = selected(config)
    first = page(source_id, scope, items[0])
    service.page(operator, grant_id, first)
    with pytest.raises(ServiceError, match="immutable bytes"):
        service.page(
            operator,
            grant_id,
            page(source_id, scope, changed_revision(items[0]), page_id=first.page_id),
        )
    bad = page(
        source_id,
        scope,
        changed_revision(items[0], text="New version"),
        changed_revision(items[0], text="Same revision changed bytes", keep_revision=True),
    )
    with pytest.raises(ServiceError, match="immutable evidence"):
        service.page(operator, grant_id, bad)
    with env.db.transaction(operator) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.capture_events WHERE source_id=%s", (source_id,)
            ).fetchone()["n"]
            == 1
        )
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.capture_pages WHERE grant_id=%s", (grant_id,)
            ).fetchone()["n"]
            == 1
        )


def test_only_admin_can_consent_and_grants_bind_the_exact_api_key(
    env, conversation_source, custody
):
    service, source_id, grant_id, _, command = custody
    _, connector, operator, _, _, config = conversation_source
    with pytest.raises(ServiceError):
        service.source(operator, connector, uuid4(), command)
    second = env.identities.create_key(
        env.owner, operator.principal_id, KeyInput(name="Other device")
    )
    other_device = env.db.authenticate(second["api_key"])
    scope, items = selected(config)
    with pytest.raises(ServiceError):
        service.page(other_device, grant_id, page(source_id, scope, *items))
    with pytest.raises(ServiceError, match="migration"):
        service.source(
            env.owner, connector, source_id, command.model_copy(update={"capture_mode": "complete"})
        )
    with pytest.raises(ServiceError, match="migration"):
        service.source(
            env.owner, connector, source_id, command.model_copy(update={"namespace": "different"})
        )
    with pytest.raises(ServiceError):
        service.grant(
            operator, source_id, uuid4(), CaptureGrantInput(device_key_id=other_device.key_id)
        )


def test_messages_policy_rejects_raw_fragments_and_forged_event_identity(
    env, conversation_source, custody
):
    service, source_id, grant_id, _, _ = custody
    _, _, operator, _, _, config = conversation_source
    scope, items = selected(config, mode="complete")
    with pytest.raises(ServiceError, match="approved selected evidence"):
        service.page(operator, grant_id, page(source_id, scope, *items))
    scope, items = selected(config)
    invalid = page(source_id, scope, *items).model_dump(mode="json")
    invalid["events"][0]["event_id"] = "0" * 64
    with pytest.raises(ServiceError, match="does not match"):
        service.page(operator, grant_id, CapturePageInput.model_validate(invalid))
    hidden_raw = items[0].model_dump(mode="json")
    hidden_raw["memory"]["source"]["content"] = "Raw private tool input behind a selected message"
    with pytest.raises(ServiceError, match="approved selected evidence"):
        service.page(
            operator,
            grant_id,
            page(source_id, scope, ConnectorItemInput.model_validate(hidden_raw)),
        )
    config.provider.scope_id = "not-the-authorized-namespace"
    config.provider.state_directory = config.provider.state_directory.parent / "other-state"
    other_scope, other_items = selected(config)
    with pytest.raises(ServiceError, match="approved selected evidence"):
        service.page(operator, grant_id, page(source_id, other_scope, *other_items))


def test_current_membership_and_managed_grant_ceiling_apply_to_custody(
    env, conversation_source, custody
):
    service, source_id, grant_id, source, _ = custody
    legacy, connector, operator, reader, _, config = conversation_source
    scope, items = selected(config)
    receipt = service.page(operator, grant_id, page(source_id, scope, *items))
    memory = UUID(receipt["items"][0]["memory_id"])
    assert env.memory.fetch(reader, memory)
    with pytest.raises(ServiceError):
        env.identities.grant(
            env.owner,
            UUID(source["space_id"]),
            reader.principal_id,
            GrantInput(role="administrator"),
        )
    legacy.binding(
        env.owner,
        connector,
        BindingInput(
            external_id="employee:reader", principal_id=reader.principal_id, role="reviewer"
        ),
        remove=True,
    )
    with pytest.raises(ServiceError):
        env.memory.fetch(reader, memory)
    assert service.page(operator, grant_id, page(source_id, scope, *items))["durable"]


@pytest.mark.parametrize("revocation", ["grant", "source", "key", "connector"])
def test_revocation_prevents_receipt_replay_and_new_ingestion(
    env, conversation_source, custody, revocation
):
    service, source_id, grant_id, _, _ = custody
    legacy, connector, operator, _, _, config = conversation_source
    scope, items = selected(config)
    request = page(source_id, scope, *items)
    service.page(operator, grant_id, request)
    if revocation == "grant":
        assert service.status(operator, grant_id, revoke=True)["active"] is False
    elif revocation == "source":
        service.revoke_source(env.owner, connector, source_id)
    elif revocation == "key":
        env.identities.revoke_key(env.owner, operator.key_id)
    else:
        legacy.disable(env.owner, connector)
    with pytest.raises(ServiceError):
        service.page(operator, grant_id, request)


def test_forget_fences_late_revisions_and_reconciles_an_old_page_receipt(
    env, conversation_source, custody
):
    service, source_id, grant_id, _, _ = custody
    _, _, operator, reader, _, config = conversation_source
    scope, items = selected(config)
    request = page(source_id, scope, *items)
    initial = service.page(operator, grant_id, request)
    memory = UUID(initial["items"][0]["memory_id"])
    env.memory.forget(reader, memory, expected_version=1, key="forget-capture-event")
    current = service.page(operator, grant_id, page_id=request.page_id)
    assert current["items"][0]["outcome"] == "forgotten"
    assert current["items"][0]["memory_id"] is None
    late = service.page(operator, grant_id, page(source_id, scope, changed_revision(items[0])))
    assert late["items"][0]["outcome"] == "forgotten"
    assert late["items"][0]["lineage_id"] == initial["items"][0]["lineage_id"]
    assert (
        service.fences(operator, grant_id)["items"][0]["lineage_id"]
        == late["items"][0]["lineage_id"]
    )
    with env.db.transaction(operator) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.memories WHERE space_id=(SELECT space_id FROM mnemion.capture_sources WHERE source_id=%s)",
                (source_id,),
            ).fetchone()["n"]
            == 1
        )


def test_page_bounds_and_duplicate_events_fail_before_any_database_work(conversation_source):
    *_, config = conversation_source
    scope, items = selected(config)
    value = page(uuid4(), scope, *items).model_dump(mode="json")
    value["events"] *= 51
    with pytest.raises(ValidationError):
        CapturePageInput.model_validate(value)
    value["events"] = value["events"][:2]
    with pytest.raises(ValidationError):
        CapturePageInput.model_validate(value)
    assert canonical_capture_json({"é": 1, "a": 2}) == canonical_capture_json({"a": 2, "é": 1})


@pytest.mark.parametrize("revocation", ["key", "connector"])
def test_in_flight_acceptance_serializes_with_authority_revocation(
    env, conversation_source, custody, monkeypatch, revocation
):
    service, source_id, grant_id, _, _ = custody
    legacy, connector, operator, _, _, config = conversation_source
    scope, items = selected(config)
    command = page(source_id, scope, *items)
    saving, release = threading.Event(), threading.Event()
    original = env.memory.save_in_transaction

    def paused(*args, **kwargs):
        saving.set()
        assert release.wait(4)
        return original(*args, **kwargs)

    monkeypatch.setattr(env.memory, "save_in_transaction", paused)

    def revoke():
        if revocation == "key":
            return env.identities.revoke_key(env.owner, operator.key_id)
        return legacy.disable(env.owner, connector)

    table = "api_keys" if revocation == "key" else "connectors"
    with ThreadPoolExecutor(max_workers=2) as pool:
        acceptance = pool.submit(service.page, operator, grant_id, command)
        assert saving.wait(3)
        revocation_result = pool.submit(revoke)
        try:
            deadline = time.monotonic() + 2
            with psycopg.connect(env.admin_dsn, autocommit=True) as conn:
                while not conn.execute(
                    "SELECT 1 FROM pg_stat_activity WHERE datname=current_database() "
                    "AND wait_event_type='Lock' AND query LIKE %s",
                    ("%UPDATE mnemion." + table + " SET%",),
                ).fetchone():
                    assert time.monotonic() < deadline
                    time.sleep(0.01)
            assert not revocation_result.done()
        finally:
            release.set()
        assert acceptance.result(timeout=3)["durable"]
        revocation_result.result(timeout=3)
    with pytest.raises(ServiceError):
        service.page(operator, grant_id, command)


def test_page_waiting_behind_device_revocation_does_not_write(
    env, conversation_source, custody, monkeypatch
):
    from mnemion.service import capture_custody

    service, source_id, grant_id, _, _ = custody
    _, _, operator, _, _, config = conversation_source
    scope, items = selected(config)
    waiting = threading.Event()
    original = capture_custody.source_lock

    def observed(conn, source):
        waiting.set()
        original(conn, source)

    monkeypatch.setattr(capture_custody, "source_lock", observed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with env.db.transaction(env.owner) as conn:
            original(conn, source_id)
            future = pool.submit(service.page, operator, grant_id, page(source_id, scope, *items))
            assert waiting.wait(3)
            conn.execute("SELECT mnemion.revoke_capture_grant(%s,%s)", (grant_id, env.owner.key_id))
        with pytest.raises(ServiceError):
            future.result(timeout=3)
    with env.db.transaction(operator) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.capture_events WHERE source_id=%s", (source_id,)
            ).fetchone()["n"]
            == 0
        )


def test_recovery_preserves_current_custody_revocation_and_late_forget_fences(
    env, conversation_source, custody, postgres, pg_bin, tmp_path
):
    service, source_id, grant_id, _, command = custody
    legacy, connector, operator, reader, _, config = conversation_source
    scope, items = selected(config)
    accepted = page(source_id, scope, *items)
    receipt = service.page(operator, grant_id, accepted)
    memory = UUID(receipt["items"][0]["memory_id"])
    archive, ledger, credentials = [
        tmp_path / name for name in ("capture.mnemion", "current-ledger.json", "recovery.json")
    ]
    recovery.create_backup(env.admin_dsn, archive, pg_bin=pg_bin)
    # This second source and its negative identity exist only after the backup.
    later_source, later_grant = uuid4(), uuid4()
    service.source(
        env.owner, connector, later_source, command.model_copy(update={"namespace": "later"})
    )
    service.grant(
        env.owner, later_source, later_grant, CaptureGrantInput(device_key_id=operator.key_id)
    )
    config.provider.scope_id = "later"
    config.provider.state_directory = config.provider.state_directory.parent / "later-state"
    later_scope, later_items = selected(config)
    later_receipt = service.page(
        operator, later_grant, page(later_source, later_scope, *later_items)
    )
    env.memory.forget(
        reader,
        UUID(later_receipt["items"][0]["memory_id"]),
        expected_version=1,
        key="forget-after-backup-source",
    )
    env.memory.forget(reader, memory, expected_version=1, key="forget-after-backup")
    service.status(env.owner, grant_id, revoke=True)
    service.source(
        env.owner,
        connector,
        source_id,
        command.model_copy(update={"expected_version": 1, "members": []}),
    )
    legacy.binding(
        env.owner,
        connector,
        BindingInput(
            external_id="employee:reader", principal_id=reader.principal_id, role="reviewer"
        ),
        remove=True,
    )
    recovery.export_ledger(env.admin_dsn, ledger)
    contents = json.loads(ledger.read_text())
    assert contents["connector_state"]["version"] == 3
    name, db = "capture_recovery_" + uuid4().hex, None
    try:
        recovery.restore_backup(
            env.admin_dsn,
            archive,
            database_name=name,
            deletion_ledger=ledger,
            credentials_output=credentials,
            pg_bin=pg_bin,
        )
        db = Database(make_conninfo(postgres[1], dbname=name))
        db.open()
        owner_data = next(
            row
            for row in json.loads(credentials.read_text())["organizations"]
            if row["tenant_id"] == str(env.owner.tenant_id)
        )
        owner = db.authenticate(owner_data["api_key"])
        ids = IdentityService(db)
        key = ids.create_key(
            owner, operator.principal_id, KeyInput(name="Reviewed restored device")
        )
        device = db.authenticate(key["api_key"])
        restored = CaptureCustody(MemoryService(db, env.embedder.generation))
        assert restored.source_status(owner, connector, source_id)["version"] == 2
        with pytest.raises(ServiceError, match="reload"):
            restored.source(owner, connector, source_id, command)
        assert restored.status(owner, grant_id)["revoked_at"] is not None
        with pytest.raises(ServiceError):
            restored.page(operator, grant_id, accepted)
        replacement_grant = uuid4()
        restored.grant(
            owner, source_id, replacement_grant, CaptureGrantInput(device_key_id=device.key_id)
        )
        # Current negative lineage state wins over the positive event in the dump.
        result = restored.page(device, replacement_grant, accepted)
        assert result["items"][0]["outcome"] == "forgotten"
        assert (
            restored.page(
                device, replacement_grant, page(source_id, scope, changed_revision(items[0]))
            )["items"][0]["outcome"]
            == "forgotten"
        )
        new_later_grant = uuid4()
        restored.grant(
            owner, later_source, new_later_grant, CaptureGrantInput(device_key_id=device.key_id)
        )
        assert (
            restored.page(device, new_later_grant, page(later_source, later_scope, *later_items))[
                "items"
            ][0]["outcome"]
            == "forgotten"
        )
        with db.transaction(owner) as conn:
            assert (
                conn.execute(
                    "SELECT count(*) AS n FROM mnemion.space_grants WHERE principal_id=%s",
                    (reader.principal_id,),
                ).fetchone()["n"]
                == 0
            )
            assert (
                conn.execute(
                    "SELECT count(*) AS n FROM mnemion.capture_denials WHERE source_id=ANY(%s)",
                    ([source_id, later_source],),
                ).fetchone()["n"]
                == 2
            )
    finally:
        if db:
            db.close()
        with psycopg.connect(env.admin_dsn, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
