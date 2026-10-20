"""Actual file capture over HTTP with PostgreSQL and enforced reader permissions."""

import json
from uuid import UUID, uuid4

import pytest

from mnemion import desktop_sources as desktop
from mnemion.sdk import MnemionError
from mnemion.service.api import create_app
from mnemion.service.connector_models import BindingInput, ConnectorInput
from mnemion.service.connectors import ConnectorService
from mnemion.service.errors import ServiceError
from mnemion.service.models import KeyInput, PrincipalInput
from service_tests.test_clients import running as serve


@pytest.mark.parametrize("provider", ["filesystem", "conversations"])
def test_desktop_capture_keeps_grants_incremental_progress_and_safe_retention(
    env, tmp_path, provider
):
    bridge = ConnectorService(env.memory)
    actor = env.identities.create_principal(env.owner, PrincipalInput(name="Desktop source"))
    key = env.identities.create_key(env.owner, UUID(actor["id"]), KeyInput(name="Desktop fixture"))
    operator = env.db.authenticate(key["api_key"])
    reader = env.identities.create_principal(env.owner, PrincipalInput(name="Reader", kind="human"))
    reader_key = env.identities.create_key(env.owner, UUID(reader["id"]), KeyInput(name="Reader"))
    reader_identity = env.db.authenticate(reader_key["api_key"])
    connector = bridge.create(
        env.owner,
        ConnectorInput(
            name="Local source",
            provider=provider,
            principal_id=operator.principal_id,
            access_mode="published",
        ),
    )
    connector_id = UUID(connector["id"])
    bridge.binding(
        env.owner, connector_id, BindingInput(external_id="reader", principal_id=UUID(reader["id"]))
    )
    folder = tmp_path / "vault"
    folder.mkdir()
    body = "The team selected PostgreSQL for shared memory."
    file = folder / ("session.jsonl" if provider == "conversations" else "decision.md")
    file.write_text(
        (json.dumps({"role": "user", "content": body}) + "\n")
        if provider == "conversations"
        else body
    )
    (folder / ".env").write_text("PRIVATE_FIXTURE=must-not-import")
    root = tmp_path / "source-control"
    with serve(create_app(env.db, env.embedder)) as endpoint:
        source = desktop.Source(
            id=uuid4(),
            endpoint=endpoint,
            tenant_id=env.owner.tenant_id,
            connector_id=connector_id,
            principal_id=operator.principal_id,
            name="Local source",
            provider=provider,
            path=str(folder),
            members=["reader"],
            publish_to_mapped_members=True,
        )
        request = {
            "operation": "scan",
            "source": source.model_dump(mode="json"),
            "credential": key["api_key"],
        }
        # Neither an administrator key nor a different intended tenant is accepted.
        with pytest.raises(desktop.local_state.LocalSetupError):
            desktop.perform(root, {**request, "credential": env.token})
        with pytest.raises(desktop.local_state.LocalSetupError):
            desktop.perform(
                root, {**request, "source": {**request["source"], "tenant_id": str(uuid4())}}
            )
        assert bridge.scopes(operator, connector_id)["items"] == []
        first = desktop.perform(root, request)
        assert first["completed"] and first["changed"] == (2 if provider == "conversations" else 1)
        scope = bridge.scopes(operator, connector_id)["items"][0]
        space = UUID(scope["space_id"])
        listed = env.memory.list(reader_identity, space)["items"]
        assert len(listed) == first["changed"]
        memory_id = UUID(next(item["memory_id"] for item in listed if body in item["content"]))
        assert body in env.memory.fetch(reader_identity, memory_id)["content"]
        with pytest.raises(ServiceError):
            env.memory.fetch(env.owner, memory_id)
        second = desktop.perform(root, request)
        assert second["completed"] and second["changed"] == 0
        if provider == "filesystem":
            file.write_bytes(b"\xffinvalid utf8")
            partial = desktop.perform(root, request)
            assert not partial["completed"]
            assert body in env.memory.fetch(reader_identity, memory_id)["content"]
            file.unlink()
            assert desktop.perform(root, request)["removed"] == 1
            with pytest.raises(ServiceError):
                env.memory.fetch(reader_identity, memory_id)
        else:
            pending = json.dumps({"role": "assistant", "content": "A second decision."})
            with file.open("a") as stream:
                stream.write(pending[:-1])
            assert desktop.perform(root, request)["changed"] == 0
            with file.open("a") as stream:
                stream.write("}\n")
            assert desktop.perform(root, request)["changed"] >= 1
            assert any(
                "A second decision." in item["content"]
                for item in env.memory.list(reader_identity, space)["items"]
            )
        assert key["api_key"] not in json.dumps(first)
        assert body not in json.dumps(first)
        bridge.disable(env.owner, connector_id)
        with pytest.raises((desktop.local_state.LocalSetupError, MnemionError)):
            desktop.perform(root, request)
