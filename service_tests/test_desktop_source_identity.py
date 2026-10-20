"""Replacement devices retain real folder identities and current reader grants."""

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
def established(env, tmp_path):
    bridge = ConnectorService(env.memory)
    actor = env.identities.create_principal(env.owner, PrincipalInput(name="Source fixture"))
    key = env.identities.create_key(env.owner, UUID(actor["id"]), KeyInput(name="Fixture"))
    operator = env.db.authenticate(key["api_key"])
    reader = env.identities.create_principal(env.owner, PrincipalInput(name="Reader fixture"))
    reader_key = env.identities.create_key(env.owner, UUID(reader["id"]), KeyInput(name="Fixture"))
    reader_identity = env.db.authenticate(reader_key["api_key"])
    connection = bridge.create(
        env.owner,
        ConnectorInput(
            name="Established folder",
            provider="filesystem",
            principal_id=operator.principal_id,
            access_mode="published",
        ),
    )
    connector = UUID(connection["id"])
    bridge.binding(
        env.owner,
        connector,
        BindingInput(external_id="reader", principal_id=reader_identity.principal_id),
    )
    folder = tmp_path / "vault"
    folder.mkdir()
    (folder / "decision.md").write_text("The fixture team selected PostgreSQL for memory.")
    with serve(create_app(env.db, env.embedder)) as endpoint:
        source = desktop.Source(
            id=uuid4(),
            endpoint=endpoint,
            tenant_id=env.owner.tenant_id,
            connector_id=connector,
            principal_id=operator.principal_id,
            name="Established folder",
            provider="filesystem",
            path=str(folder),
            members=["reader"],
            publish_to_mapped_members=True,
        )
        original = source.connector(tmp_path / "original-capture")
        original.provider.scope_id = "established-office"
        with Client(endpoint, key["api_key"], retries=0) as client:
            assert sync(original, client=client)["completed"]
        scopes = bridge.scopes(operator, connector)["items"]
        space = UUID(scopes[0]["space_id"])
        memory = env.memory.list(reader_identity, space)["items"][0]
        yield SimpleNamespace(
            bridge=bridge,
            operator=operator,
            reader=reader_identity,
            connector=connector,
            source=source,
            original=original,
            key=key["api_key"],
            space=space,
            memory_id=UUID(memory["memory_id"]),
            content=memory["content"],
            endpoint=endpoint,
        )


def request(fixture, operation="scan", **changes):
    return {
        "operation": operation,
        "source": {**fixture.source.model_dump(mode="json"), **changes},
        "credential": fixture.key,
    }


def test_reconnect_and_reopen_preserve_the_original_space_memory_and_revision(
    env, established, tmp_path
):
    f = established
    verified = desktop.perform(tmp_path / "control", request(f, "verify"))
    assert verified["scope_id"] == "established-office"
    for source in (f.source.model_dump(mode="json"), verified):
        report = desktop.perform(
            tmp_path / "control",
            {
                "operation": "scan",
                "source": source,
                "credential": f.key,
            },
        )
        assert report["completed"] and report["changed"] == report["removed"] == 0
        scopes = f.bridge.scopes(f.operator, f.connector)["items"]
        assert [(item["space_id"], item["external_id"]) for item in scopes] == [
            (str(f.space), "filesystem:established-office")
        ]
        assert env.memory.fetch(f.reader, f.memory_id)["content"] == f.content


def test_an_explicit_different_identity_is_refused_before_scanning(env, established, tmp_path):
    f = established
    before = f.bridge.scopes(f.operator, f.connector)
    with pytest.raises(desktop.local_state.LocalSetupError) as error:
        desktop.perform(tmp_path / "control", request(f, scope_id="unrelated-folder"))
    assert error.value.code == "source_scope_mismatch"
    assert f.bridge.scopes(f.operator, f.connector) == before
    assert env.memory.fetch(f.reader, f.memory_id)["content"] == f.content


def test_an_ambiguous_previous_catalog_is_retained_for_operator_review(established, tmp_path):
    f = established
    f.original.provider.scope_id = "another-recorded-folder"
    with Client(f.endpoint, f.key, retries=0) as client:
        assert sync(f.original, client=client)["completed"]
    before = f.bridge.scopes(f.operator, f.connector)
    assert len(before["items"]) == 2
    with pytest.raises(desktop.local_state.LocalSetupError) as error:
        desktop.perform(tmp_path / "control", request(f))
    assert error.value.code == "source_scope_ambiguous"
    assert f.bridge.scopes(f.operator, f.connector) == before


def test_replacement_revalidates_new_readers_against_the_actual_folder(env, established, tmp_path):
    f = established
    actor = env.identities.create_principal(env.owner, PrincipalInput(name="New reader"))
    key = env.identities.create_key(env.owner, UUID(actor["id"]), KeyInput(name="Fixture"))
    identity = env.db.authenticate(key["api_key"])
    f.bridge.binding(
        env.owner,
        f.connector,
        BindingInput(
            external_id="new-reader",
            principal_id=identity.principal_id,
        ),
    )
    with pytest.raises(ServiceError):
        env.memory.fetch(identity, f.memory_id)
    report = desktop.perform(tmp_path / "control", request(f, members=["reader", "new-reader"]))
    assert report["completed"] and report["changed"] == 0
    assert env.memory.fetch(identity, f.memory_id)["content"] == f.content
    assert env.memory.fetch(f.reader, f.memory_id)["content"] == f.content
    with pytest.raises(ServiceError):
        env.memory.fetch(env.owner, f.memory_id)
