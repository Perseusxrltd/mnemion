"""Actual desktop helper custody, offline intake and explicit removal over HTTP.

Opaque sealed-key fixtures exercise helper ownership; Electron/native platform
acceptance separately checks the operating system's credential cipher.
"""

import base64
import json
import os
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4

import httpx
import pytest

from mnemion import desktop_capture as capture, desktop_sources as desktop, local_state
from mnemion.connectors.conversation_inbox import InboxError
from mnemion.service.api import create_app
from service_tests.test_clients import running
from service_tests.test_capture_custody import custody as custody
from service_tests.test_live_conversations import (
    conversation_source as conversation_source,
    encoded,
)


@pytest.fixture
def enrolled(env, custody, conversation_source, tmp_path):
    _, source_id, grant_id, _, _ = custody
    _, connector, operator, reader, secret, config = conversation_source
    root, inbox_key = tmp_path / "desktop", base64.b64encode(os.urandom(32)).decode()
    with running(create_app(env.db, env.embedder)) as endpoint:
        source = desktop.Source(
            id=uuid4(),
            endpoint=endpoint,
            tenant_id=env.owner.tenant_id,
            connector_id=connector,
            principal_id=operator.principal_id,
            name="Selected chats",
            provider="conversations",
            capture_mode="messages",
            scope_id="fixture",
            path=str(config.provider.path),
            members=["employee:reader"],
            publish_to_mapped_members=True,
            custody={"source_id": source_id, "grant_id": grant_id, "keep_accepted": True},
        )
        verified = desktop.perform(
            root,
            {"operation": "verify", "source": source.model_dump(mode="json"), "credential": secret},
        )
        saved = desktop.SavedSource(
            **verified,
            sealed_key=base64.b64encode(b"opaque protected application key").decode(),
            sealed_inbox_key=base64.b64encode(b"different opaque protected inbox key").decode(),
        )
        desktop.store(root, "not-configured", [saved])
        request = {
            "operation": "scan",
            "source": source.model_dump(mode="json"),
            "credential": secret,
            "inbox_key": inbox_key,
        }
        yield root, source, request, reader


def offline(monkeypatch, root, source, *, expect_pending=True):
    observed = []

    class Offline:
        def __init__(self, *args, **kwargs):
            path = capture.inbox_path(root, source.id) / "inbox.sqlite3"
            with sqlite3.connect(path) as connection:
                count = connection.execute(
                    "SELECT COUNT(*) FROM events WHERE state='pending'"
                ).fetchone()[0]
            if expect_pending:
                assert count > 0, "Selected evidence must be committed before ANY service request"
            observed.append(count)
            raise httpx.ConnectError("Synthetic service outage")

    monkeypatch.setattr(capture, "Client", Offline)
    return observed


def test_native_offline_capture_then_missing_folder_delivery_and_status(env, enrolled, monkeypatch):
    root, source, request, reader = enrolled
    path = Path(source.path) / "chat.jsonl"
    path.write_bytes(encoded("Durably selected text") + encoded("Excluded tool secret", "tool"))
    with monkeypatch.context() as patch:
        observed = offline(patch, root, source)
        first = desktop.perform(root, request)
    assert observed == [1]
    assert first["capture"]["locally_accepted"] == first["capture"]["pending_events"] == 1
    assert first["capture"]["reason_code"] == "capture_delivery_unavailable"
    assert not first["completed"] and first["capture"]["capture_complete"]
    raw = (capture.inbox_path(root, source.id) / "inbox.sqlite3").read_bytes()
    assert b"Durably selected text" not in raw and b"Excluded tool secret" not in raw
    path.unlink()
    path.parent.rmdir()
    second = desktop.perform(root, request)
    assert second["capture"]["delivery_complete"] and second["capture"]["pending_events"] == 0
    assert second["capture"]["stored_events"] == 1 and not second["capture"]["capture_complete"]
    assert second["capture"]["reason_code"] == "capture_source_unavailable"
    with env.db.transaction(reader) as connection:
        items = connection.execute(
            "SELECT id FROM mnemion.memories WHERE deleted_at IS NULL"
        ).fetchall()
    assert any(
        "Durably selected text" in env.memory.fetch(reader, row["id"])["content"] for row in items
    )
    owner, run = str(uuid4()), str(uuid4())
    current = desktop.load(root)
    desktop.perform(
        root,
        {
            "operation": "status_begin",
            "owner": owner,
            "run": run,
            "id": str(source.id),
            "expected_revision": current.revision,
        },
    )
    finished = desktop.perform(
        root,
        {
            "operation": "status_finish",
            "owner": owner,
            "run": run,
            "id": str(source.id),
            "report": second,
        },
    )
    assert finished["activity"]["report"]["capture"]["stored_events"] == 1
    assert finished["activity"]["report"]["capture"] == second["capture"]
    assert "Durably selected text" not in json.dumps(finished)


def test_ready_inbox_loss_or_wrong_key_never_reinitializes(enrolled, monkeypatch):
    root, source, request, _ = enrolled
    path = Path(source.path) / "chat.jsonl"
    path.write_bytes(encoded("Must survive key errors"))
    with monkeypatch.context() as patch:
        offline(patch, root, source)
        desktop.perform(root, request)
    database = capture.inbox_path(root, source.id) / "inbox.sqlite3"
    before = database.read_bytes()
    with pytest.raises(InboxError, match="capture_integrity_failed"):
        desktop.perform(root, {**request, "inbox_key": base64.b64encode(os.urandom(32)).decode()})
    assert database.read_bytes() == before
    database.unlink()
    with pytest.raises(InboxError, match="capture_inbox_missing"):
        desktop.perform(root, request)
    assert not database.exists()


def test_device_capacity_stops_acceptance_but_can_deliver_existing_backlog(enrolled, monkeypatch):
    root, source, request, _ = enrolled
    path = Path(source.path) / "chat.jsonl"
    path.write_bytes(encoded("Accepted before the device limit changed"))
    with monkeypatch.context() as patch:
        offline(patch, root, source)
        desktop.perform(root, request)
    with path.open("ab") as stream:
        stream.write(encoded("This new record must wait"))
    monkeypatch.setattr(capture, "DEVICE_PENDING_BYTES", 1)
    result = desktop.perform(root, request)
    assert result["capture"]["reason_code"] == "capture_capacity_blocked"
    assert result["capture"]["locally_accepted"] == 0
    assert result["capture"]["stored_events"] == 1 and result["capture"]["pending_events"] == 0
    assert result["capture"]["delivery_complete"]


def test_history_budget_edits_keep_device_identity_key_and_accepted_evidence(enrolled, monkeypatch):
    root, source, request, _ = enrolled
    (Path(source.path) / "chat.jsonl").write_bytes(encoded("Accepted before a budget change"))
    with monkeypatch.context() as patch:
        offline(patch, root, source)
        desktop.perform(root, request)
    state = desktop.load(root)
    original = state.sources[0]
    enrollment = capture.enrollment(root, original)
    database = capture.inbox_path(root, source.id) / "inbox.sqlite3"
    before = database.read_bytes()
    changed = original.model_copy(deep=True)
    changed.custody.history_limit_events = 1000
    changed.custody.database_limit_mib = 64
    desktop.store(root, state.revision, [changed])
    saved = desktop.load(root).sources[0]
    assert capture.enrollment(root, saved) == enrollment
    assert saved.sealed_key == original.sealed_key
    assert saved.sealed_inbox_key == original.sealed_inbox_key
    assert database.read_bytes() == before
    public = desktop.Source.model_validate(
        saved.model_dump(include=set(desktop.Source.model_fields))
    )
    result = desktop.perform(root, {**request, "source": public.model_dump(mode="json")})
    history = result["capture"]["history"]
    assert history["event_limit"] == 1000 and history["database_limit_bytes"] == 64 * 1024**2
    assert history["events"] == result["capture"]["stored_events"] == 1
    assert result["capture"]["pending_events"] == 0


def test_pending_capacity_is_shared_across_actual_sources_and_ignores_retired_folders(
    env, enrolled, custody, conversation_source, monkeypatch
):
    from mnemion.service.capture_models import CaptureGrantInput, CaptureSourceInput
    from mnemion.service.connector_models import BindingInput, ConnectorInput
    from mnemion.service.models import KeyInput, PrincipalInput

    root, first_source, first_request, reader = enrolled
    legacy = conversation_source[0]
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Second capture", kind="application")
    )
    second_key = env.identities.create_key(
        env.owner, UUID(person["id"]), KeyInput(name="Second capture key")
    )
    operator = env.db.authenticate(second_key["api_key"])
    (Path(first_source.path) / "first.jsonl").write_bytes(encoded("The first device queue"))
    with monkeypatch.context() as patch:
        offline(patch, root, first_source)
        first = desktop.perform(root, first_request)["capture"]
    second_connector = UUID(
        legacy.create(
            env.owner,
            ConnectorInput(
                name="Second selected source",
                provider="conversations",
                access_mode="published",
                principal_id=operator.principal_id,
            ),
        )["id"]
    )
    legacy.binding(
        env.owner,
        second_connector,
        BindingInput(
            external_id="employee:reader", principal_id=reader.principal_id, role="reviewer"
        ),
    )
    source_id, grant_id = uuid4(), uuid4()
    service = custody[0]
    service.source(
        env.owner,
        second_connector,
        source_id,
        CaptureSourceInput(
            namespace="second",
            name="Second capture",
            members=["employee:reader"],
            capture_mode="messages",
            keep_accepted=True,
        ),
    )
    service.grant(env.owner, source_id, grant_id, CaptureGrantInput(device_key_id=operator.key_id))
    folder = Path(first_source.path).parent / "second-sessions"
    folder.mkdir()
    (folder / "second.jsonl").write_bytes(encoded("The second device queue"))
    second = first_source.model_copy(
        update={
            "id": uuid4(),
            "connector_id": second_connector,
            "principal_id": operator.principal_id,
            "scope_id": "second",
            "path": str(folder),
            "custody": capture.Custody(source_id=source_id, grant_id=grant_id, keep_accepted=True),
        }
    )
    verified = desktop.perform(
        root,
        {
            "operation": "verify",
            "source": second.model_dump(mode="json"),
            "credential": second_key["api_key"],
        },
    )
    current = desktop.load(root)
    desktop.store(
        root,
        current.revision,
        [
            *current.sources,
            desktop.SavedSource(
                **verified,
                sealed_key=base64.b64encode(b"second opaque API key").decode(),
                sealed_inbox_key=base64.b64encode(b"independent second inbox key").decode(),
            ),
        ],
    )
    second_request = {
        **first_request,
        "credential": second_key["api_key"],
        "source": second.model_dump(mode="json"),
        "inbox_key": base64.b64encode(os.urandom(32)).decode(),
    }
    with monkeypatch.context() as patch:
        patch.setattr(capture, "DEVICE_PENDING_BYTES", first["pending_bytes"])
        offline(patch, root, second, expect_pending=False)
        full = desktop.perform(root, second_request)["capture"]
    assert full["locally_accepted"] == full["pending_events"] == 0
    assert full["device_pending_bytes"] == first["pending_bytes"]
    assert full["reason_code"] == "capture_capacity_blocked"
    # Retired enrollment markers and emptied inboxes are permanent identity
    # evidence; their accumulation must not count as active retained databases.
    for _ in range(70):
        retired_id = uuid4()
        (root / f"inbox-{retired_id}").mkdir(mode=0o700)
        (root / f"inbox-enrollment-{retired_id}.json").write_text("{}")
    with monkeypatch.context() as patch:
        offline(patch, root, second)
        accepted = desktop.perform(root, second_request)["capture"]
    assert accepted["pending_events"] == 1
    assert accepted["device_pending_bytes"] == first["pending_bytes"] + accepted["pending_bytes"]


def test_lost_revoke_reply_preserves_inbox_and_next_remove_reconciles(enrolled, monkeypatch):
    root, source, request, _ = enrolled
    path = Path(source.path) / "chat.jsonl"
    path.write_bytes(encoded("Only an explicit removal may discard this pending memory"))
    with monkeypatch.context() as patch:
        offline(patch, root, source)
        desktop.perform(root, request)
    current = desktop.load(root)
    saved = current.sources[0].model_copy(update={"enabled": False})
    paused = desktop.store(root, current.revision, [saved])
    removal = {
        "operation": "capture_retire",
        "id": str(source.id),
        "expected_revision": paused["revision"],
        "credential": request["credential"],
        "discard_local_inbox": True,
    }
    with pytest.raises(InboxError, match="capture_retire_required"):
        desktop.store(root, paused["revision"], [])
    original, calls = capture.Client.request, []

    def lose_reply(client, method, route, **kwargs):
        value = original(client, method, route, **kwargs)
        calls.append(method)
        if method == "DELETE":
            raise httpx.ReadTimeout("Synthetic lost reply after actual grant revocation")
        return value

    with monkeypatch.context() as patch:
        patch.setattr(capture.Client, "request", lose_reply)
        with pytest.raises(httpx.ReadTimeout):
            desktop.perform(root, removal)
    assert calls == ["GET", "DELETE"]
    database = capture.inbox_path(root, source.id) / "inbox.sqlite3"
    assert database.exists()
    calls.clear()
    with monkeypatch.context() as patch:
        patch.setattr(capture.Client, "request", lose_reply)
        result = desktop.perform(root, removal)
    assert calls == ["GET"] and result["local_inbox_discarded"]
    assert not database.exists() and path.is_file()
    assert desktop.store(root, paused["revision"], [])["sources"] == []


def test_older_retained_history_requires_the_matching_private_inbox(env, enrolled):
    root, source, request, _ = enrolled
    (Path(source.path) / "chat.jsonl").write_bytes(encoded("An existing retained generation"))
    result = desktop.perform(root, request)
    assert result["completed"]
    verify = {
        "operation": "verify",
        "source": request["source"],
        "credential": request["credential"],
    }
    assert desktop.perform(root, verify)["id"] == str(source.id)
    with pytest.raises(InboxError, match="capture_policy_change_requires_migration"):
        desktop.perform(root, {**verify, "source": {**request["source"], "id": str(uuid4())}})
    route = f"/v1/connectors/{source.connector_id}/capture-sources/{source.custody.source_id}"
    with capture.Client(source.endpoint, env.token) as administrator:
        policy = administrator.request("GET", route)
        assert policy["has_capture_history"]
        edit = {key: policy[key] for key in ["namespace", "name", "members", "capture_mode"]}
        edit.update(keep_accepted=True, expected_version=policy["version"])
        assert administrator.request("PUT", route, body=edit)["has_capture_history"]
        assert administrator.request(
            "PUT", route, body={**edit, "name": "Renamed retained source"}
        )["has_capture_history"]
        assert administrator.request("DELETE", route)["has_capture_history"]


@pytest.mark.parametrize(
    "lost_material", ["none", "api_key", "inbox_key", "both_keys", "malformed_inbox_key"]
)
def test_administrator_can_retire_after_device_key_revocation(
    env, enrolled, conversation_source, monkeypatch, lost_material
):
    root, source, request, _ = enrolled
    (Path(source.path) / "chat.jsonl").write_bytes(
        encoded("Preserve this until authorized removal")
    )
    with monkeypatch.context() as patch:
        offline(patch, root, source)
        desktop.perform(root, request)
    current = desktop.load(root)
    paused = desktop.store(
        root, current.revision, [current.sources[0].model_copy(update={"enabled": False})]
    )
    removal = {
        "operation": "capture_retire",
        "id": str(source.id),
        "expected_revision": paused["revision"],
        "credential": request["credential"],
        "discard_local_inbox": True,
    }
    if lost_material != "none":
        damaged = local_state.read(root / "sources.json")
        if lost_material in {"api_key", "both_keys"}:
            del damaged["sources"][0]["sealed_key"]
        if lost_material in {"inbox_key", "both_keys"}:
            del damaged["sources"][0]["sealed_inbox_key"]
        if lost_material == "malformed_inbox_key":
            damaged["sources"][0]["sealed_inbox_key"] = "%not-base64%"
        local_state.write(root / "sources.json", damaged)
    env.identities.revoke_key(env.owner, conversation_source[2].key_id)
    database = capture.inbox_path(root, source.id) / "inbox.sqlite3"
    before = database.read_bytes()
    for credential in [request["credential"], None]:
        with pytest.raises(InboxError, match="capture_retirement_credentials"):
            desktop.perform(root, {**removal, "credential": credential})
        assert database.read_bytes() == before
    result = desktop.perform(root, {**removal, "credential": env.token})
    assert result["remote_grant_revoked"] and result["local_inbox_discarded"]
    assert not database.exists()
    # A completed remote retirement may be retried without credentials. No
    # online request or key decryption is needed for its local acknowledgement.
    with monkeypatch.context() as patch:
        patch.setattr(capture, "Client", lambda *a, **k: pytest.fail("Already retired: no HTTP"))
        assert desktop.perform(root, {**removal, "credential": None})["retired"]
    assert desktop.store(root, paused["revision"], [])["sources"] == []


def test_ready_marker_must_commit_before_any_local_acceptance(enrolled, monkeypatch):
    root, source, request, _ = enrolled
    (Path(source.path) / "chat.jsonl").write_bytes(encoded("Only after a durable ready marker"))
    write = capture.local_state.write

    def lost_marker(path, value):
        if path == capture.record_path(root, source.id) and value.get("state") == "ready":
            raise OSError("Synthetic full disk before marker commit")
        return write(path, value)

    with monkeypatch.context() as patch:
        patch.setattr(capture.local_state, "write", lost_marker)
        with pytest.raises(OSError):
            desktop.perform(root, request)
    database = capture.inbox_path(root, source.id) / "inbox.sqlite3"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert desktop.perform(root, request)["completed"]
