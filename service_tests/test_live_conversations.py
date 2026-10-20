"""Real HTTP and PostgreSQL acceptance for checkpointed conversation sources."""

import json
from uuid import UUID

import httpx
import pytest

from mnemion.connectors.config import ConnectorConfig
from mnemion.connectors.live_conversations import ConversationProvider
from mnemion.connectors.runner import ConnectorConfigurationError, sync
from mnemion.sdk import Client
from mnemion.service.api import create_app
from mnemion.service.connector_models import (
    BatchInput,
    BindingInput,
    ConnectorInput,
    ConnectorItemInput,
    FinishInput,
)
from mnemion.service.connectors import ConnectorService
from mnemion.service.errors import ServiceError
from mnemion.service.models import KeyInput, PrincipalInput, ReviewInput, RevisionInput
from service_tests.test_clients import running as serve
from service_tests.test_connectors import begin, ingest, item
from service_tests.test_connectors import connected as connected


def encoded(text, role="user"):
    return (json.dumps({"role": role, "content": text}) + "\n").encode()


@pytest.fixture
def conversation_source(env, tmp_path):
    service = ConnectorService(env.memory)
    principals = {}
    for name in ("capture", "reader"):
        person = env.identities.create_principal(
            env.owner,
            PrincipalInput(name=name, kind="application" if name == "capture" else "human"),
        )
        key = env.identities.create_key(env.owner, UUID(person["id"]), KeyInput(name=name))
        principals[name] = env.db.authenticate(key["api_key"]), key["api_key"]
    operator, secret = principals["capture"]
    reader = principals["reader"][0]
    connection = UUID(
        service.create(
            env.owner,
            ConnectorInput(
                name="Live fixture",
                provider="conversations",
                access_mode="published",
                principal_id=operator.principal_id,
            ),
        )["id"]
    )
    service.binding(
        env.owner,
        connection,
        BindingInput(
            external_id="employee:reader",
            principal_id=reader.principal_id,
            role="reviewer",
        ),
    )
    source = tmp_path / "sessions"
    source.mkdir()
    config = ConnectorConfig.model_validate(
        {
            "service_url": "http://127.0.0.1",
            "connector_id": str(connection),
            "service_token": {"env": "UNUSED_INJECTED_FIXTURE"},
            "remote_sync": False,
            "provider": {
                "type": "conversations",
                "path": source,
                "state_directory": tmp_path / "state",
                "scope_id": "fixture",
                "name": "Fixture",
                "members": ["employee:reader"],
                "publish_to_mapped_members": True,
                "segment_records": 2,
            },
        }
    )
    return service, connection, operator, reader, secret, config


def memories(env, operator, reader, space):
    with env.db.transaction(operator) as connection:
        ids = connection.execute(
            "SELECT id FROM mnemion.memories WHERE space_id=%s AND deleted_at IS NULL ORDER BY id",
            (space,),
        ).fetchall()
    return [env.memory.fetch(reader, row["id"]) for row in ids]


def test_capture_mode_change_publishes_only_messages_after_complete_inventory(
    env, conversation_source
):
    service, connection, operator, reader, secret, config = conversation_source
    (config.provider.path / "selected.jsonl").write_bytes(
        encoded("Visible message") + encoded("Private tool payload", "tool")
    )
    with serve(create_app(env.db, env.embedder)) as url, Client(url, secret) as client:
        assert sync(config, client=client)["completed"]
        space = service.scopes(env.owner, connection)["items"][0]["space_id"]
        original = memories(env, operator, reader, space)
        assert len(original) == 2 and any("Private tool payload" in m["content"] for m in original)
        config.provider.capture_mode = "messages"
        assert sync(config, client=client)["completed"]
        selected = memories(env, operator, reader, space)
        assert len(selected) == 1 and "Visible message" in selected[0]["content"]
        assert "Private tool payload" not in json.dumps(selected)
        assert selected[0]["metadata"]["capture_mode"] == "messages"
        checkpoint = service.scopes(env.owner, connection)["items"][0]["checkpoint"]
        assert json.loads(checkpoint[9:])["capture_mode"] == "messages"
        repeated = sync(config, client=client)
        assert repeated["completed"] and repeated["changed"] == 0


@pytest.mark.parametrize("external,revision", [("missing", "1"), ("kept", "not-current")])
def test_references_cannot_invent_source_evidence_or_change_an_existing_revision(
    env, connected, external, revision
):
    service, _, space, operator, identities = connected
    saved = ingest(service, operator, space, item("kept"))
    memory = UUID(saved["items"][0]["memory_id"])
    run = begin(service, operator, space)
    with pytest.raises(ServiceError) as error:
        service.page(
            operator,
            space,
            run,
            BatchInput(
                sequence=0,
                items=[
                    ConnectorItemInput(external_id=external, revision=revision, action="retain"),
                ],
            ),
        )
    assert error.value.code == "source_reference_unavailable"
    result = service.page(
        operator,
        space,
        run,
        BatchInput(
            sequence=0,
            items=[
                ConnectorItemInput(external_id="kept", revision="1", action="retain"),
            ],
        ),
    )
    service.finish(operator, space, run, FinishInput(complete_inventory=True))
    assert result["items"][0]["outcome"] == "unchanged"
    assert env.memory.fetch(identities["reader"][0], memory)["version"] == 1


def test_references_preserve_corrections_proposals_quarantine_and_forgetting(env, connected):
    service, _, space, operator, identities = connected
    result = ingest(service, operator, space, item())
    memory = UUID(result["items"][0]["memory_id"])
    reviewer = identities["reviewer"][0]
    env.memory.revise(
        reviewer,
        memory,
        RevisionInput(
            content="Human correction",
            expected_version=1,
            reason="Reviewed",
        ),
        "live-human-correction",
    )
    ingest(service, operator, space, item(text="Later upstream value", revision="2"))
    proposal = service.proposals(reviewer, space)["items"][0]
    reference = ConnectorItemInput(external_id="message:1", revision="2", action="retain")
    retained = ingest(service, operator, space, reference)
    assert retained["items"][0]["outcome"] == "conflict"
    assert service.proposals(reviewer, space)["items"][0] == proposal
    assert env.memory.fetch(reviewer, memory)["content"] == "Human correction"
    env.memory.review(
        reviewer,
        memory,
        ReviewInput(
            expected_version=2,
            state="quarantined",
            reason="Needs a separate review",
        ),
    )
    ingest(service, operator, space, reference)
    with pytest.raises(ServiceError):
        env.memory.fetch(identities["reader"][0], memory)
    env.memory.forget(reviewer, memory, expected_version=3, key="forget-live-reference")
    ingest(service, operator, space, reference)
    with pytest.raises(ServiceError):
        env.memory.fetch(reviewer, memory)
    assert service.proposals(reviewer, space)["items"] == []
    assert (
        ingest(service, operator, space, item(revision="3"))["items"][0]["outcome"]
        == "deletion_preserved"
    )


def test_partial_and_oversized_logs_are_isolated_and_progress_is_committed(
    env, conversation_source
):
    service, connection, operator, reader, secret, config = conversation_source
    folder = config.provider.path
    (folder / "healthy.jsonl").write_bytes(encoded("Unrelated healthy source"))
    complete = encoded("Complete live record")
    (folder / "live.jsonl").write_bytes(complete + b'{"role":')
    adapter = ConversationProvider(config.provider)
    paths = {path: scope for scope, path in ((s, adapter.paths[s]) for s in adapter.scopes())}
    with serve(create_app(env.db, env.embedder)) as url, Client(url, secret) as client:
        first = sync(config, client=client)
        assert first["completed"] and len(first["scopes"]) == 2
        scopes = {row["external_id"]: row for row in service.scopes(env.owner, connection)["items"]}
        live = scopes[paths["live.jsonl"]]
        progress = json.loads(live["checkpoint"][9:])
        assert progress["captured"] == len(complete) and progress["observed"] > progress["captured"]
        healthy = scopes[paths["healthy.jsonl"]]
        assert any(
            "Unrelated healthy source" in row["content"]
            for row in memories(env, operator, reader, healthy["space_id"])
        )
        config.provider.max_record_bytes = 128
        (folder / "live.jsonl").write_bytes(encoded("x" * 500))
        failed = sync(config, client=client)
        assert not failed["completed"]
        reports = {row["external_id"]: row for row in failed["scopes"]}
        assert reports[paths["live.jsonl"]]["error_code"] == "conversation_record_limit"
        assert reports[paths["live.jsonl"]]["access_suspended"]
        assert reports[paths["healthy.jsonl"]]["capture"]["segments_reused"] == 1
        assert memories(env, operator, reader, healthy["space_id"])
        with env.db.transaction(operator) as database:
            old = database.execute(
                "SELECT id FROM mnemion.memories WHERE space_id=%s LIMIT 1", (live["space_id"],)
            ).fetchone()
        with pytest.raises(ServiceError):
            env.memory.fetch(reader, old["id"])


def test_lost_finish_acknowledgment_replays_safely_and_cached_data_cannot_restore_access(
    env, conversation_source
):
    service, connection, operator, reader, secret, config = conversation_source
    (config.provider.path / "one.jsonl").write_bytes(encoded("Never duplicate this observation"))
    with serve(create_app(env.db, env.embedder)) as url, Client(url, secret) as client:

        class LoseAcknowledgment:
            lost = False

            def request(self, method, path, **kwargs):
                result = client.request(method, path, **kwargs)
                if (
                    not self.lost
                    and path.endswith("/finish")
                    and result.get("state") == "completed"
                ):
                    self.lost = True
                    raise httpx.ReadError("Synthetic response lost after commit")
                return result

        lost = sync(config, client=LoseAcknowledgment())
        assert not lost["completed"]
        retried = sync(config, client=client)
        assert retried["completed"] and retried["scopes"][0]["outcomes"] == {"unchanged": 2}
        scope = service.scopes(env.owner, connection)["items"][0]
        before = memories(env, operator, reader, scope["space_id"])
        assert len(before) == 2
        repeated = sync(config, client=client)
        assert repeated["scopes"][0]["capture"]["bytes_read"] == 0
        assert {row["memory_id"] for row in memories(env, operator, reader, scope["space_id"])} == {
            row["memory_id"] for row in before
        }
        service.binding(
            env.owner,
            connection,
            BindingInput(
                external_id="employee:reader",
                principal_id=reader.principal_id,
                role="reviewer",
            ),
            remove=True,
        )
        assert sync(config, client=client)["completed"]
        with pytest.raises(ServiceError):
            env.memory.fetch(reader, UUID(before[0]["memory_id"]))


def test_truncation_starts_a_new_generation_and_following_appends_are_not_lost(
    env, conversation_source
):
    service, connection, operator, reader, secret, config = conversation_source
    config.provider.segment_records = 1
    path = config.provider.path / "rotating.jsonl"
    path.write_bytes(b"".join(encoded(f"Old {i}") for i in range(5)))
    with serve(create_app(env.db, env.embedder)) as url, Client(url, secret) as client:
        assert sync(config, client=client)["completed"]
        scope = service.scopes(env.owner, connection)["items"][0]
        previous = memories(env, operator, reader, scope["space_id"])
        path.write_bytes(encoded("New 0"))
        shortened = sync(config, client=client)
        assert (
            shortened["completed"] and shortened["scopes"][0]["capture"]["change"] == "truncation"
        )
        with path.open("ab") as stream:
            stream.write(b"".join(encoded(f"New {i}") for i in range(1, 7)))
        assert sync(config, client=client)["completed"]
        current = memories(env, operator, reader, scope["space_id"])
        assert len(current) == 14
        assert not any("Old " in row["content"] for row in current)
        assert {row["memory_id"] for row in current}.isdisjoint(
            row["memory_id"] for row in previous
        )
        path.unlink()
        assert sync(config, client=client)["completed"]
        with pytest.raises(ServiceError):
            env.memory.fetch(reader, UUID(current[0]["memory_id"]))


def test_live_runner_explains_old_server_requirement_before_creating_source_state(
    env, conversation_source
):
    service, connection, _, _, secret, config = conversation_source
    (config.provider.path / "one.jsonl").write_bytes(encoded("Selected but not yet captured"))
    with serve(create_app(env.db, env.embedder)) as url, Client(url, secret) as client:

        class OlderService:
            def request(self, method, path, **kwargs):
                if path == "/health/live":
                    return {"service_version": "4.16.0"}
                return client.request(method, path, **kwargs)

        with pytest.raises(ConnectorConfigurationError) as error:
            sync(config, client=OlderService())
        assert error.value.code == "conversation_server_upgrade_required"
        assert service.scopes(env.owner, connection)["items"] == []
        assert not config.provider.state_directory.exists()
