"""Real policy transitions, offline queues, recovery, and administrator boundaries."""

from copy import deepcopy
import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from psycopg.conninfo import make_conninfo

from mnemion.capture_policy import CapturePolicy
from mnemion import agent_control
from mnemion.connectors.capture_cycle import cycle
from mnemion.connectors.capture_delivery import deliver, verify_grant
from mnemion.connectors.conversation_capture import capture_available
from mnemion.connectors.conversation_inbox import open_inbox
from mnemion.connectors.live_conversations import ConversationProvider
from mnemion.sdk import Client
from mnemion.service import capture_recovery
from mnemion.service import recovery
from mnemion.service.api import create_app
from mnemion.service.capture_custody import CaptureCustody
from mnemion.service.capture_models import CaptureGrantInput, CapturePolicyChange
from mnemion.service.db import Database
from mnemion.service.errors import ServiceError
from mnemion.service.identity import IdentityService
from mnemion.service.memory import MemoryService
from mnemion.service.models import KeyInput, json_value
from service_tests.test_capture_custody import custody as custody, page, selected
from service_tests.test_clients import running
from service_tests.test_live_conversations import (
    conversation_source as conversation_source,
    encoded,
)
from service_tests.test_recovery import destination as destination


def proposed(service, owner, connector, source_id, *, previous_grants="retain", **policy):
    review = service.policy_review(owner, connector, source_id)
    return CapturePolicyChange(
        expected_version=review["source"]["version"],
        review_token=review["review_token"],
        capture_policy=CapturePolicy(
            preset="detailed", capture_mode="complete", retention="until_deleted", **policy
        ),
        previous_grants=previous_grants,
        confirm=True,
    )


def binding(owner, connector, source_id, grant_id):
    return {
        "tenant_id": str(owner.tenant_id),
        "connector_id": str(connector),
        "source_id": str(source_id),
        "grant_id": str(grant_id),
        "namespace": "fixture",
        "capture_mode": "messages",
    }


def test_old_offline_queue_delivers_under_its_original_policy_after_default_changes(
    env, conversation_source, custody, tmp_path
):
    service, source_id, grant_id, before, _ = custody
    _, connector, operator, reader, secret, config = conversation_source
    config.provider.capture_mode = "messages"
    (config.provider.path / "chat.jsonl").write_bytes(
        encoded("Offline selected memory") + encoded("Not consented tool trace", "tool")
    )
    with open_inbox(
        tmp_path / "inbox",
        binding(env.owner, connector, source_id, grant_id),
        b"x" * 32,
        create=True,
    ) as inbox:
        assert (
            capture_available(inbox, ConversationProvider(config.provider))["pending_events"] == 1
        )
        changed = service.change_policy(
            env.owner,
            connector,
            source_id,
            uuid4(),
            proposed(service, env.owner, connector, source_id),
        )
        assert changed["source"]["policy_version"] == 2
        assert changed["source"]["space_id"] == before["space_id"]
        with running(create_app(env.db, env.embedder)) as url, Client(url, secret) as client:
            grant = verify_grant(inbox, client)
            assert (
                grant.policy_version == 1
                and grant.capture_mode == "messages"
                and grant.capture_policy is None
            )
            result = deliver(inbox, client)
            assert result["pending_events"] == 0 and result["stored_events"] == 1
        with env.db.transaction(reader) as conn:
            rows = conn.execute(
                "SELECT id FROM mnemion.memories WHERE space_id=%s",
                (UUID(before["space_id"]),),
            ).fetchall()
        memories = [env.memory.fetch(reader, row["id"]) for row in rows]
        assert len(memories) == 1 and "Offline selected memory" in memories[0]["content"]
        assert "Not consented" not in memories[0]["content"]


def test_new_grant_uses_new_policy_and_cannot_relabel_old_event(env, conversation_source, custody):
    service, source_id, old_grant, _, _ = custody
    _, connector, operator, _, _, config = conversation_source
    scope, items = selected(config)
    request = page(source_id, scope, *items)
    command = proposed(service, env.owner, connector, source_id)
    service.change_policy(env.owner, connector, source_id, uuid4(), command)
    new_grant = uuid4()
    granted = service.grant(
        env.owner, source_id, new_grant, CaptureGrantInput(device_key_id=operator.key_id)
    )
    assert granted["policy_version"] == 2 and granted[
        "capture_policy"
    ] == command.capture_policy.model_dump(mode="json")
    with pytest.raises(ServiceError, match="approved selected evidence"):
        service.page(operator, new_grant, request)
    accepted = service.page(operator, old_grant, request)
    assert service.page(operator, old_grant, request) == accepted
    # Idempotent old-client enrollment does not move an existing grant to v2.
    assert (
        service.grant(
            env.owner, source_id, old_grant, CaptureGrantInput(device_key_id=operator.key_id)
        )["policy_version"]
        == 1
    )


def test_review_detects_device_created_without_source_version_change(
    env, conversation_source, custody
):
    service, source_id, _, _, _ = custody
    _, connector, operator, _, _, _ = conversation_source
    command = proposed(service, env.owner, connector, source_id)
    service.grant(env.owner, source_id, uuid4(), CaptureGrantInput(device_key_id=operator.key_id))
    with pytest.raises(ServiceError, match="review them again"):
        service.change_policy(env.owner, connector, source_id, uuid4(), command)
    assert service.source_status(env.owner, connector, source_id)["policy_version"] == 1


def test_repeated_revoke_transition_never_revokes_a_later_device(env, conversation_source, custody):
    service, source_id, old_grant, _, _ = custody
    _, connector, operator, _, _, _ = conversation_source
    command = proposed(service, env.owner, connector, source_id, previous_grants="revoke")
    transition = uuid4()
    result = service.change_policy(env.owner, connector, source_id, transition, command)
    assert result["transition"]["affected_grants"] == 1
    assert service.status(env.owner, old_grant)["revoked_at"]
    new_grant = uuid4()
    service.grant(env.owner, source_id, new_grant, CaptureGrantInput(device_key_id=operator.key_id))
    assert service.change_policy(env.owner, connector, source_id, transition, command) == result
    assert service.status(env.owner, new_grant)["active"]
    with pytest.raises(ServiceError, match="same reviewed request"):
        service.change_policy(
            env.owner,
            connector,
            source_id,
            transition,
            command.model_copy(update={"previous_grants": "retain"}),
        )


def test_explicit_historical_recovery_preserves_receipts_and_current_deletion_fences(
    env, conversation_source, custody
):
    service, source_id, old_grant, _, _ = custody
    _, connector, operator, reader, _, config = conversation_source
    scope, items = selected(config)
    request = page(source_id, scope, *items)
    original = service.page(operator, old_grant, request)
    env.memory.forget(
        reader, UUID(original["items"][0]["memory_id"]), expected_version=1, key="policy-forgotten"
    )
    service.change_policy(
        env.owner,
        connector,
        source_id,
        uuid4(),
        proposed(service, env.owner, connector, source_id, previous_grants="revoke"),
    )
    recovered = uuid4()
    grant = service.grant(
        env.owner,
        source_id,
        recovered,
        CaptureGrantInput(
            device_key_id=operator.key_id, previous_grant_id=old_grant, confirm_previous_policy=True
        ),
    )
    assert grant["policy_version"] == 1 and grant["capture_policy"] is None
    result = service.page(operator, recovered, request)
    assert result["items"][0]["outcome"] == "forgotten"
    assert result["items"][0]["memory_id"] is None
    with pytest.raises(ServiceError, match="no longer has active"):
        service.page(operator, old_grant, request)
    for value in ({"previous_grant_id": old_grant}, {"confirm_previous_policy": True}):
        with pytest.raises(ValidationError):
            CaptureGrantInput(device_key_id=operator.key_id, **value)


def test_admin_pages_are_bounded_and_operators_cannot_change_policy(
    env, conversation_source, custody
):
    service, source_id, _, _, _ = custody
    _, connector, operator, reader, secret, _ = conversation_source
    for _ in range(3):
        service.grant(
            env.owner, source_id, uuid4(), CaptureGrantInput(device_key_id=operator.key_id)
        )
    review = service.policy_review(env.owner, connector, source_id, limit=2)
    assert (
        len(review["devices"]) == 2 and review["unrevoked_grants"] == review["active_grants"] == 4
    )
    more = service.policy_review(
        env.owner, connector, source_id, after=UUID(review["next_cursor"]), limit=2
    )
    assert (
        len(more["devices"]) == 2
        and more["next_cursor"] is None
        and more["review_token"] == review["review_token"]
    )
    assert not (
        {row["grant_id"] for row in review["devices"]}
        & {row["grant_id"] for row in more["devices"]}
    )
    command = proposed(service, env.owner, connector, source_id)
    for identity in (operator, reader):
        with pytest.raises(ServiceError):
            service.change_policy(identity, connector, source_id, uuid4(), command)
        with pytest.raises(ServiceError):
            service.policy_review(identity, connector, source_id)
    with TestClient(create_app(env.db, env.embedder)) as client:
        assert client.get("/health/live").json()["capture_policy_versions"] == "v1"
        route = f"/v1/connectors/{connector}/capture-sources/{source_id}/policy-review"
        assert client.get(route, headers={"Authorization": "Bearer " + secret}).status_code == 403


def test_recovery_ledger_keeps_all_policy_versions_and_cannot_mutate_them(
    env, conversation_source, custody
):
    service, source_id, old_grant, _, _ = custody
    _, connector, _, _, _, _ = conversation_source
    service.change_policy(
        env.owner, connector, source_id, uuid4(), proposed(service, env.owner, connector, source_id)
    )
    with env.db.transaction(env.owner) as conn:
        ledger = json_value(capture_recovery.capture(conn))
    capture_recovery.validate(ledger, {str(env.owner.tenant_id)})
    assert ledger["version"] == 3 and len(ledger["policies"]) == 2 and ledger["expiries"] == []
    with env.db.transaction(env.owner) as conn:
        capture_recovery.restore(conn, ledger)
    assert service.status(env.owner, old_grant)["policy_version"] == 1
    changed = deepcopy(ledger)
    changed["policies"][0]["capture_mode"] = "complete"
    capture_recovery.validate(changed, {str(env.owner.tenant_id)})
    with pytest.raises(ValueError, match="immutable capture policy version"):
        with env.db.transaction(env.owner) as conn:
            capture_recovery.restore(conn, changed)
    assert service.status(env.owner, old_grant)["capture_mode"] == "messages"
    incomplete = deepcopy(ledger)
    incomplete["policies"] = incomplete["policies"][1:]
    with pytest.raises(ValueError, match="history is incomplete"):
        capture_recovery.validate(incomplete, {str(env.owner.tenant_id)})
    unpinned = deepcopy(ledger)
    del unpinned["grants"][0]["policy_version"]
    with pytest.raises(ValueError, match="Unknown device capture policy"):
        capture_recovery.validate(unpinned, {str(env.owner.tenant_id)})


def test_full_backup_recovery_keeps_later_policy_history_and_original_device_approval(
    env, conversation_source, custody, postgres, pg_bin, tmp_path, destination
):
    service, source_id, original_grant, source, _ = custody
    _, connector, operator, reader, _, config = conversation_source
    scope, items = selected(config)
    request = page(source_id, scope, *items)
    accepted = service.page(operator, original_grant, request)
    archive, ledger, credentials = [
        tmp_path / name for name in ("policies.mnemion", "ledger.json", "owner.json")
    ]
    recovery.create_backup(env.admin_dsn, archive, pg_bin=pg_bin)
    service.change_policy(
        env.owner, connector, source_id, uuid4(), proposed(service, env.owner, connector, source_id)
    )
    later_grant = uuid4()
    service.grant(
        env.owner, source_id, later_grant, CaptureGrantInput(device_key_id=operator.key_id)
    )
    service.change_policy(
        env.owner,
        connector,
        source_id,
        uuid4(),
        proposed(service, env.owner, connector, source_id, exclude=["private/*.jsonl"]),
    )
    env.memory.forget(
        reader,
        UUID(accepted["items"][0]["memory_id"]),
        expected_version=1,
        key="policy-deleted-after-backup",
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
        owner_data = next(
            row
            for row in json.loads(credentials.read_text())["organizations"]
            if row["tenant_id"] == str(env.owner.tenant_id)
        )
        owner = db.authenticate(owner_data["api_key"])
        restored = CaptureCustody(MemoryService(db, env.embedder.generation))
        current = restored.source_status(owner, connector, source_id)
        assert current["policy_version"] == 3 and current["space_id"] == source["space_id"]
        assert [
            row["policy_version"]
            for row in restored.policy_versions(owner, connector, source_id)["items"]
        ] == [1, 2, 3]
        assert restored.status(owner, original_grant)["policy_version"] == 1
        assert restored.status(owner, later_grant)["policy_version"] == 2
        key = IdentityService(db).create_key(
            owner, operator.principal_id, KeyInput(name="Reviewed policy recovery device")
        )
        device = db.authenticate(key["api_key"])
        replacement = uuid4()
        approved = restored.grant(
            owner,
            source_id,
            replacement,
            CaptureGrantInput(
                device_key_id=device.key_id,
                previous_grant_id=original_grant,
                confirm_previous_policy=True,
            ),
        )
        assert approved["policy_version"] == 1 and approved["capture_policy"] is None
        assert restored.page(device, replacement, request)["items"][0]["outcome"] == "forgotten"
    finally:
        db.close()


def test_legacy_single_policy_recovery_stays_compatible(env, conversation_source, custody):
    service, source_id, grant_id, _, _ = custody
    _, connector, _, _, _, _ = conversation_source
    with env.db.transaction(env.owner) as conn:
        ledger = json_value(capture_recovery.capture(conn))
    ledger["version"] = 1
    del ledger["policies"]
    del ledger["expiries"]
    for row in ledger["sources"] + ledger["grants"]:
        row.pop("policy_version")
    capture_recovery.validate(ledger, {str(env.owner.tenant_id)})
    with env.db.transaction(env.owner) as conn:
        capture_recovery.restore(conn, ledger)
    assert service.status(env.owner, grant_id)["active"]
    service.change_policy(
        env.owner, connector, source_id, uuid4(), proposed(service, env.owner, connector, source_id)
    )
    with pytest.raises(ValueError, match="immutable source binding"):
        with env.db.transaction(env.owner) as conn:
            capture_recovery.restore(conn, ledger)


@pytest.mark.parametrize("target", ["source", "connector"])
def test_whole_source_revocation_stops_intake_without_exposing_hidden_metadata(
    env, conversation_source, custody, tmp_path, target
):
    service, source_id, grant_id, _, _ = custody
    _, connector, operator, _, secret, config = conversation_source
    config.provider.capture_mode = "messages"
    (config.provider.path / "chat.jsonl").write_bytes(
        encoded("Locally committed before authority check")
    )
    if target == "source":
        service.revoke_source(env.owner, connector, source_id)
    else:
        with TestClient(create_app(env.db, env.embedder)) as client:
            response = client.delete(
                f"/v1/connectors/{connector}", headers={"Authorization": "Bearer " + env.token}
            )
            assert response.status_code == 200
    with pytest.raises(ServiceError) as refused:
        service.status(operator, grant_id)
    assert refused.value.status == 403 and refused.value.code == "capture_grant_inactive"
    with pytest.raises(ServiceError) as unknown:
        service.status(operator, uuid4())
    assert unknown.value.status == 404
    stopped = []
    with (
        open_inbox(
            tmp_path / "inbox",
            binding(env.owner, connector, source_id, grant_id),
            b"x" * 32,
            create=True,
        ) as inbox,
        running(create_app(env.db, env.embedder)) as url,
    ):

        def collect():
            return capture_available(inbox, ConversationProvider(config.provider))

        result = cycle(
            inbox,
            collect=collect,
            client=lambda: Client(url, secret, retries=0),
            revoked=lambda: stopped.append(True),
            usage=inbox.status,
        )
        assert (
            stopped == [True]
            and result["capture"]["reason_code"] == "capture_authorization_revoked"
        )
        assert (
            result["capture"]["pending_events"] == 1
            and result["capture"]["remote_committed_events"] == 0
        )
        next_cycle = cycle(
            inbox,
            collect=None,
            client=lambda: Client(url, secret, retries=0),
            revoked=lambda: None,
            usage=inbox.status,
        )
        assert (
            next_cycle["capture"]["locally_accepted"] == 0
            and next_cycle["capture"]["pending_events"] == 1
        )


def test_agent_operations_use_the_same_policy_review_transition_and_recovery(
    env, conversation_source, custody
):
    service, source_id, old_grant, _, _ = custody
    _, connector, operator, _, secret, _ = conversation_source
    parameters = {"connector_id": str(connector), "source_id": str(source_id)}
    with (
        running(create_app(env.db, env.embedder)) as url,
        Client(url, env.token, retries=0) as client,
    ):
        sources = agent_control.execute(
            client, "capture.source.list", {"parameters": {"connector_id": str(connector)}}
        )["result"]
        assert sources["items"][0]["source_id"] == str(source_id)
        review = agent_control.execute(client, "capture.policy.review", {"parameters": parameters})[
            "result"
        ]
        command = proposed(service, env.owner, connector, source_id)
        assert review["review_token"] == command.review_token
        request = {
            "parameters": {**parameters, "transition_id": str(uuid4())},
            "body": command.model_dump(mode="json"),
        }
        first = agent_control.execute(client, "capture.policy.change", request)
        result = first["result"]
        assert first["idempotency"] == "new"
        assert result["source"]["policy_version"] == 2
        repeated = agent_control.execute(client, "capture.policy.change", request)
        assert repeated["idempotency"] == "replayed"
        assert repeated["result"] == result
        history = agent_control.execute(
            client, "capture.policy.versions", {"parameters": parameters}
        )["result"]
        assert [item["policy_version"] for item in history["items"]] == [1, 2]
        recovered = agent_control.execute(
            client,
            "capture.grant.configure",
            {
                "parameters": {"source_id": str(source_id), "grant_id": str(uuid4())},
                "body": {
                    "device_key_id": str(operator.key_id),
                    "previous_grant_id": str(old_grant),
                    "confirm_previous_policy": True,
                },
            },
        )["result"]
        assert recovered["policy_version"] == 1 and recovered["active"]
        with Client(url, secret, retries=0) as device:
            with pytest.raises(agent_control.ControlError) as error:
                agent_control.execute(device, "capture.policy.change", request)
            assert error.value.status == 403
