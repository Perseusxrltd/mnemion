"""Real replacement-folder capture retains the original evidence and permissions."""

import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from mnemion import desktop_sources as desktop
from mnemion.connectors.runner import sync
from mnemion.sdk import Client
from mnemion.service.api import create_app
from mnemion.service.connector_models import BindingInput, ConnectorInput
from mnemion.service.connectors import ConnectorService
from mnemion.service.errors import ServiceError
from mnemion.service.models import KeyInput, PrincipalInput
from service_tests.test_clients import running as serve


@pytest.fixture
def conversation(env, tmp_path):
    bridge = ConnectorService(env.memory)
    actor = env.identities.create_principal(env.owner, PrincipalInput(name="Capture fixture"))
    key = env.identities.create_key(env.owner, UUID(actor["id"]), KeyInput(name="Fixture"))
    operator = env.db.authenticate(key["api_key"])
    reader = env.identities.create_principal(env.owner, PrincipalInput(name="Reader fixture"))
    reader_key = env.identities.create_key(env.owner, UUID(reader["id"]), KeyInput(name="Fixture"))
    identity = env.db.authenticate(reader_key["api_key"])
    connection = bridge.create(
        env.owner,
        ConnectorInput(
            name="Existing conversation",
            provider="conversations",
            principal_id=operator.principal_id,
            access_mode="published",
        ),
    )
    connector = UUID(connection["id"])
    bridge.binding(
        env.owner, connector, BindingInput(external_id="reader", principal_id=identity.principal_id)
    )
    folder = tmp_path / "original"
    folder.mkdir()
    (folder / "session.jsonl").write_text(
        json.dumps(
            {"role": "user", "content": "The fixture selected PostgreSQL for shared memory."}
        )
        + "\n"
    )
    with serve(create_app(env.db, env.embedder)) as endpoint:
        source = desktop.Source(
            id=uuid4(),
            endpoint=endpoint,
            tenant_id=env.owner.tenant_id,
            connector_id=connector,
            principal_id=operator.principal_id,
            name="Existing conversation",
            provider="conversations",
            path=str(folder),
            members=["reader"],
            publish_to_mapped_members=True,
        )
        original = source.connector(tmp_path / "original-state")
        original.provider.scope_id = "original-capture"
        with Client(endpoint, key["api_key"], retries=0) as client:
            assert sync(original, client=client)["completed"]
        scope = bridge.scopes(operator, connector)["items"][0]
        space = UUID(scope["space_id"])
        memories = env.memory.list(identity, space)["items"]
        assert len(memories) == 2
        restored = tmp_path / "restored"
        shutil.copytree(folder, restored)
        assert (folder / "session.jsonl").stat().st_ino != (
            restored / "session.jsonl"
        ).stat().st_ino
        yield SimpleNamespace(
            source=source,
            key=key["api_key"],
            restored=restored,
            reader=identity,
            bridge=bridge,
            operator=operator,
            connector=connector,
            space=space,
            scope=scope,
            memories=memories,
        )


def request(fixture, operation="scan", **changes):
    return {
        "operation": operation,
        "source": {
            **fixture.source.model_dump(mode="json"),
            "path": str(fixture.restored),
            "scope_id": "original-capture",
            **changes,
        },
        "credential": fixture.key,
    }


def test_restored_copy_retains_namespace_original_memories_and_versions(
    env, conversation, tmp_path
):
    f = conversation
    root = tmp_path / "desktop"
    verified = desktop.perform(root, request(f, "verify"))
    assert verified["scope_id"] == "original-capture"
    report = desktop.perform(root, {**request(f), "source": verified})
    assert report["completed"] and report["changed"] == report["removed"] == 0
    scopes = f.bridge.scopes(f.operator, f.connector)["items"]
    assert [s["space_id"] for s in scopes] == [str(f.space)]
    for old in f.memories:
        current = env.memory.fetch(f.reader, UUID(old["memory_id"]))
        assert (current["version"], current["content"]) == (old["version"], old["content"])
    # The verified selection remains usable when its final file is removed.
    (f.restored / "session.jsonl").unlink()
    assert desktop.perform(root, request(f))["completed"]
    for old in f.memories:
        with pytest.raises(ServiceError):
            env.memory.fetch(f.reader, UUID(old["memory_id"]))


@pytest.mark.parametrize("namespace", [None, "wrong-identity"])
def test_unknown_namespace_stops_before_import(env, conversation, tmp_path, namespace):
    f = conversation
    before = f.bridge.scopes(f.operator, f.connector)
    with pytest.raises(desktop.local_state.LocalSetupError) as failure:
        desktop.perform(tmp_path / "desktop", request(f, scope_id=namespace))
    assert failure.value.code == "source_conversation_identity_required"
    assert f.bridge.scopes(f.operator, f.connector) == before
    assert (
        env.memory.fetch(f.reader, UUID(f.memories[0]["memory_id"]))["content"]
        == f.memories[0]["content"]
    )


def test_unrelated_replacement_bytes_do_not_replace_original_capture(env, conversation, tmp_path):
    f = conversation
    (f.restored / "session.jsonl").write_text(
        json.dumps({"role": "user", "content": "Unrelated source bytes."}) + "\n"
    )
    before = f.bridge.scopes(f.operator, f.connector)
    with pytest.raises(desktop.local_state.LocalSetupError) as failure:
        desktop.perform(tmp_path / "desktop", request(f))
    assert failure.value.code == "source_conversation_copy_unverified"
    assert f.bridge.scopes(f.operator, f.connector) == before
    assert (
        env.memory.fetch(f.reader, UUID(f.memories[0]["memory_id"]))["content"]
        == f.memories[0]["content"]
    )


def test_legacy_checkpoint_needs_original_file_before_portable_copy(conversation):
    from mnemion.desktop_source_identity import _verify_copy
    import time

    f = conversation
    checkpoint = json.loads(f.scope["checkpoint"][9:])
    checkpoint.pop("captured_sha256")
    legacy = "jsonl:v1:" + json.dumps(checkpoint)
    _verify_copy(Path(f.source.path), "session.jsonl", legacy, time.monotonic() + 30)
    with pytest.raises(desktop.local_state.LocalSetupError) as failure:
        _verify_copy(f.restored, "session.jsonl", legacy, time.monotonic() + 30)
    assert failure.value.code == "source_conversation_copy_unverified"


@pytest.mark.parametrize("already_absent", [False, True])
def test_replacement_requires_active_original_files(env, conversation, tmp_path, already_absent):
    f = conversation
    second = Path(f.source.path) / "second.jsonl"
    second.write_text(json.dumps({"role": "user", "content": "Retain the second session."}) + "\n")
    config = f.source.connector(tmp_path / "original-state")
    config.provider.scope_id = "original-capture"
    with Client(f.source.endpoint, f.key, retries=0) as client:
        assert sync(config, client=client)["completed"]
        if already_absent:
            second.unlink()
            assert sync(config, client=client)["completed"]
    before = f.bridge.scopes(f.operator, f.connector)
    assert len(before["items"]) == 2
    root = tmp_path / "replacement"
    if already_absent:
        assert any(s["suspension_reason"] == "access_lost" for s in before["items"])
        report = desktop.perform(root, request(f))
        assert report["completed"] and report["changed"] == report["removed"] == 0
    else:
        with pytest.raises(desktop.local_state.LocalSetupError) as failure:
            desktop.perform(root, request(f))
        assert failure.value.code == "source_conversation_incomplete_copy"
        assert f.bridge.scopes(f.operator, f.connector) == before
        assert not (root / f"conversation-identity-{f.source.id}.json").exists()
        # Completing the copy then permits the same source to reconnect.
        shutil.copy2(second, f.restored / second.name)
        report = desktop.perform(root, request(f))
        assert report["completed"] and report["changed"] == report["removed"] == 0
    for old in f.memories:
        assert env.memory.fetch(f.reader, UUID(old["memory_id"]))["version"] == old["version"]
