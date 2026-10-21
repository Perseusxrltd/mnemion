"""Reviewed selection, no-write previews and immutable local/server policy."""

import json
import os
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mnemion import desktop_sources as desktop
from mnemion.capture_policy import CapturePolicy
from mnemion.connectors.capture_delivery import deliver, verify_grant
from mnemion.connectors.config import ConversationConfig
from mnemion.connectors.conversation_capture import capture_available
from mnemion.connectors.conversation_inbox import InboxError, open_inbox
from mnemion.connectors.live_conversations import ConversationProvider
from mnemion.desktop_capture_preview import CapturePreview, PreviewSelection, preview, selection_for
from mnemion.local_state import LocalSetupError
from mnemion.sdk import Client
from mnemion.service.api import create_app
from mnemion.service import capture_recovery
from mnemion.service.capture_custody import CaptureCustody
from mnemion.service.capture_models import CaptureGrantInput, CaptureSourceInput
from mnemion.service.errors import ServiceError
from mnemion.service.models import json_value
from service_tests.test_capture_custody import page
from service_tests.test_clients import running
from service_tests.test_live_conversations import (
    conversation_source as conversation_source,
    encoded,
)


def policy(**changes):
    return CapturePolicy.model_validate(
        {
            "preset": "selected",
            "capture_mode": "messages",
            "include": ["kept/*.jsonl"],
            "exclude": ["*/private/*"],
            "retention": "until_deleted",
            **changes,
        }
    )


def producer(tmp_path):
    folder = tmp_path / "producer"
    (folder / "kept/private").mkdir(parents=True)
    (folder / ".git").mkdir()
    visible = encoded("Selected café \u2028 retained message") + encoded(
        "tool secret marker", "tool"
    )
    (folder / "kept/chat.jsonl").write_bytes(
        visible + b"\n" + b'{"role":"user","content":"unfinished'
    )
    (folder / "kept/private/other.jsonl").write_bytes(encoded("excluded session marker"))
    (folder / ".git/chat.jsonl").write_bytes(encoded("excluded git marker"))
    return folder, len(visible) + 1


def test_preview_matches_selected_prefix_without_http_models_or_saved_content(
    tmp_path, monkeypatch
):
    folder, prefix_bytes = producer(tmp_path)
    root = tmp_path / "private-state"
    monkeypatch.setattr(
        Client, "request", lambda *a, **kw: pytest.fail("Preview contacted a server")
    )
    selection = PreviewSelection(
        path=str(folder), capture_mode="messages", capture_policy=policy(), keep_accepted=True
    )
    observed = desktop.perform(
        root, {"operation": "preview", "selection": selection.model_dump(mode="json")}
    )
    result = CapturePreview.model_validate(observed)
    assert result.configuration_hash == selection.fingerprint
    assert result.catalog == "complete" and result.policy_revision == policy().revision
    assert [file.path for file in result.files] == ["kept/chat.jsonl"]
    assert result.files[0].prefix_bytes == prefix_bytes
    assert result.files[0].file_bytes > prefix_bytes
    assert result.records.model_dump() == {
        "lines": 3,
        "selected": 1,
        "omitted": 2,
        "unsupported": 0,
    }
    assert not root.exists() and result.content_saved is False
    assert "secret marker" not in json.dumps(observed) and "retained message" not in json.dumps(
        observed
    )
    assert result.attachment_binaries == "not_read" and result.hidden_reasoning == "unavailable"


def test_preview_limits_and_invalid_records_do_not_claim_full_capture(tmp_path):
    folder = tmp_path / "large"
    folder.mkdir()
    for index in range(12):
        (folder / f"{index}.jsonl").write_bytes(encoded("sample") * 6000)
    result = preview(
        tmp_path / "state",
        PreviewSelection(path=str(folder), capture_mode="complete", keep_accepted=False).model_dump(
            mode="json"
        ),
    )
    assert result["catalog"] == "limited" and len(result["files"]) == 8
    assert result["read_bytes"] <= 1024 * 1024
    assert all(file["prefix_bytes"] < file["file_bytes"] for file in result["files"])
    assert result["records"]["selected"] == result["records"]["lines"]
    one = folder / "0.jsonl"
    one.write_bytes(b'{"bad json"\n')
    selection = PreviewSelection(
        path=str(folder),
        capture_mode="messages",
        capture_policy=policy(include=["0.jsonl"]),
        keep_accepted=True,
    )
    observed = preview(tmp_path / "state", selection.model_dump(mode="json"))
    assert observed["files"][0]["status"] == "invalid_jsonl"
    assert observed["records"]["lines"] == observed["files"][0]["prefix_bytes"] == 0


def test_preview_reports_size_limits_and_never_follows_selected_symlink(tmp_path):
    folder = tmp_path / "source"
    folder.mkdir()
    (folder / "big.jsonl").write_bytes(encoded("larger than allowed record"))
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(encoded("outside marker"))
    (folder / "linked.jsonl").symlink_to(outside)
    selection = PreviewSelection(
        path=str(folder),
        capture_mode="messages",
        capture_policy=policy(include=["*.jsonl"], max_record_bytes=10),
        keep_accepted=True,
    )
    result = preview(tmp_path / "state", selection.model_dump(mode="json"))
    assert result["catalog"] == "unavailable"
    assert result["files"][0]["status"] == "record_too_large"
    assert all(file["path"] != "linked.jsonl" for file in result["files"])
    assert "outside marker" not in json.dumps(result)


def test_changed_selection_needs_new_preview_before_credentials_are_used(tmp_path, monkeypatch):
    folder, _ = producer(tmp_path)
    source = desktop.Source(
        id=uuid4(),
        endpoint="https://memory.example.invalid",
        tenant_id=uuid4(),
        connector_id=uuid4(),
        principal_id=uuid4(),
        name="Selected",
        provider="conversations",
        path=str(folder),
        capture_mode="messages",
        capture_policy=policy(),
        members=[],
        publish_to_mapped_members=True,
        custody={"source_id": uuid4(), "grant_id": uuid4(), "keep_accepted": True},
    )
    before = preview(tmp_path / "state", selection_for(source).model_dump(mode="json"))
    source.memory_limit_mib = 512
    monkeypatch.setattr(
        Client, "request", lambda *a, **kw: pytest.fail("Unreviewed setup used credentials")
    )
    with pytest.raises(LocalSetupError, match="Preview the current capture settings"):
        desktop.perform(
            tmp_path / "state",
            {
                "operation": "verify",
                "source": source.model_dump(mode="json"),
                "credential": "unused-private-fixture-credential",
                "preview_hash": before["configuration_hash"],
            },
        )


def test_recovery_ledger_cannot_drop_or_change_an_approved_capture_policy(env, conversation_source):
    _, connector, _, _, _, _ = conversation_source
    service, source_id = CaptureCustody(env.memory), uuid4()
    service.source(
        env.owner,
        connector,
        source_id,
        CaptureSourceInput(
            namespace="fixture",
            name="Reviewed recovery policy",
            members=[],
            capture_mode="messages",
            keep_accepted=True,
            capture_policy=policy(),
        ),
    )
    with env.db.transaction(env.owner) as connection:
        ledger = json_value(capture_recovery.capture(connection))
    tenants = {str(env.owner.tenant_id)}
    capture_recovery.validate(ledger, tenants)
    for replacement in (None, policy(include=["*.jsonl"]).model_dump(mode="json")):
        changed = deepcopy(ledger)
        changed["sources"][0]["capture_policy"] = replacement
        capture_recovery.validate(changed, tenants)
        with pytest.raises(ValueError, match="immutable source binding"):
            with env.db.transaction(env.owner) as connection:
                capture_recovery.restore(connection, changed)
        assert service.source_status(env.owner, connector, source_id)["revoked_at"] is None
    invalid = deepcopy(ledger)
    invalid["sources"][0]["capture_policy"]["retention"] = "source_mirror"
    with pytest.raises(ValueError, match="custody policy"):
        capture_recovery.validate(invalid, tenants)


def test_reviewed_policy_survives_offline_capture_restart_and_real_delivery(
    env, conversation_source, tmp_path
):
    _, connector, operator, reader, secret, config = conversation_source
    selected_policy = policy()
    config.provider = ConversationConfig.model_validate(
        {
            **config.provider.model_dump(),
            "capture_mode": "messages",
            "capture_policy": selected_policy,
        }
    )
    folder = config.provider.path
    (folder / "kept/private").mkdir(parents=True)
    (folder / "kept/chat.jsonl").write_bytes(
        encoded("approved policy content") + encoded("unselected tool content", "tool")
    )
    (folder / "kept/private/chat.jsonl").write_bytes(encoded("unselected private content"))
    service, source_id, grant_id = CaptureCustody(env.memory), uuid4(), uuid4()
    command = CaptureSourceInput(
        namespace="fixture",
        name="Reviewed capture",
        members=["employee:reader"],
        capture_mode="messages",
        keep_accepted=True,
        capture_policy=selected_policy,
    )
    service.source(env.owner, connector, source_id, command)
    service.grant(env.owner, source_id, grant_id, CaptureGrantInput(device_key_id=operator.key_id))
    binding = {
        "tenant_id": str(env.owner.tenant_id),
        "connector_id": str(connector),
        "source_id": str(source_id),
        "grant_id": str(grant_id),
        "namespace": "fixture",
        "capture_mode": "messages",
        "capture_policy": selected_policy.model_dump(mode="json"),
    }
    key, inbox_path = os.urandom(32), tmp_path / "encrypted-inbox"
    with open_inbox(inbox_path, binding, key, create=True) as inbox:
        result = capture_available(inbox, ConversationProvider(config.provider))
        assert result["completed"] and result["pending_events"] == 1
    (folder / "kept/chat.jsonl").unlink()
    with running(create_app(env.db, env.embedder)) as endpoint, Client(endpoint, secret) as client:
        legacy_binding = {key: value for key, value in binding.items() if key != "capture_policy"}
        with pytest.raises(InboxError, match="capture_binding_mismatch"):
            verify_grant(SimpleNamespace(binding=legacy_binding), client)
        with open_inbox(inbox_path, binding, key) as inbox:
            delivered = deliver(inbox, client)
            assert delivered["remote_committed_events"] == 1
            assert inbox.status()["stored_events"] == 1
    with env.db.transaction(operator) as conn:
        row = conn.execute(
            "SELECT memory_id FROM mnemion.capture_events WHERE source_id=%s", (source_id,)
        ).fetchone()
    memory = env.memory.fetch(reader, row["memory_id"])
    assert memory["metadata"]["capture_policy_revision"] == selected_policy.revision
    assert "approved policy content" in memory["content"] and "unselected" not in memory["content"]
    changed = selected_policy.model_copy(update={"include": ["*.jsonl"]})
    with pytest.raises(ServiceError) as rejected:
        service.source(
            env.owner, connector, source_id, command.model_copy(update={"capture_policy": changed})
        )
    assert rejected.value.code == "capture_policy_immutable"
    with pytest.raises(InboxError):
        with open_inbox(
            inbox_path, {**binding, "capture_policy": changed.model_dump(mode="json")}, key
        ):
            pytest.fail("A changed policy opened the existing encrypted inbox")


def test_service_rejects_excluded_paths_and_forged_policy_revisions(
    env, conversation_source, tmp_path
):
    _, connector, operator, _, secret, config = conversation_source
    selected_policy = policy()
    service, source_id, grant_id = CaptureCustody(env.memory), uuid4(), uuid4()
    command = CaptureSourceInput(
        namespace="fixture",
        name="Reviewed",
        members=[],
        capture_mode="messages",
        keep_accepted=True,
        capture_policy=selected_policy,
    )
    service.source(env.owner, connector, source_id, command)
    service.grant(env.owner, source_id, grant_id, CaptureGrantInput(device_key_id=operator.key_id))
    config.provider.capture_mode = "messages"
    (config.provider.path / "excluded.jsonl").write_bytes(encoded("Excluded path payload"))
    provider = ConversationProvider(config.provider)
    scope = provider.scopes()[0]
    with provider.snapshot(scope, None) as snapshot:
        items = [item for item in snapshot.items() if item is not None]
    items[0].memory.metadata["capture_policy_revision"] = selected_policy.revision
    with TestClient(create_app(env.db, env.embedder)) as client:
        response = client.post(
            f"/v1/capture-grants/{grant_id}/pages",
            headers={"Authorization": "Bearer " + secret},
            json=page(source_id, scope, items[0]).model_dump(mode="json"),
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "capture_selection_invalid"
    assert "Excluded path payload" not in response.text
    (config.provider.path / "kept").mkdir()
    (config.provider.path / "kept/chat.jsonl").write_bytes(
        encoded("Approved path with forged policy")
    )
    config.provider = ConversationConfig.model_validate(
        {
            **config.provider.model_dump(),
            "capture_policy": selected_policy,
        }
    )
    provider = ConversationProvider(config.provider)
    allowed_scope = provider.scopes()[0]
    with provider.snapshot(allowed_scope, None) as snapshot:
        allowed_items = [item for item in snapshot.items() if item is not None]
    allowed_items[0].memory.metadata["capture_policy_revision"] = "0" * 64
    with pytest.raises(ServiceError) as forged:
        service.page(operator, grant_id, page(source_id, allowed_scope, allowed_items[0]))
    assert forged.value.code == "capture_selection_invalid"
    with env.db.transaction(operator) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.capture_events WHERE source_id=%s", (source_id,)
            ).fetchone()["n"]
            == 0
        )
