"""Capture action metadata and immutable bindings over real PostgreSQL requests."""

from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mnemion.service.api import create_app
from mnemion.service.capture_models import CaptureGrantInput
from mnemion.service.errors import ServiceError
from mnemion.service.request_replay import request_replay
from service_tests.test_capture_custody import custody as custody
from service_tests.test_capture_policy_versions import proposed
from service_tests.test_live_conversations import conversation_source as conversation_source


def test_grant_id_collision_after_lookup_cannot_return_another_source(
    env, conversation_source, custody, monkeypatch
):
    service, source_id, _, _, source_command = custody
    _, connector, operator, _, _, _ = conversation_source
    other_source, grant_id = uuid4(), uuid4()
    service.source(
        env.owner,
        connector,
        other_source,
        source_command.model_copy(update={"namespace": "other-source"}),
    )
    command = CaptureGrantInput(device_key_id=operator.key_id)
    original_transaction = service.db.transaction
    interleaved = []

    class Cursor:
        def __init__(self, cursor):
            self.cursor = cursor

        def fetchone(self):
            row = self.cursor.fetchone()
            if row is None and not interleaved:
                interleaved.append(True)
                # A second real connection commits after the first request's
                # lookup, before its unique INSERT. Its HTTP context is separate.
                with request_replay():
                    winner = service.grant(env.owner, other_source, grant_id, command)
                assert winner["source_id"] == str(other_source)
            return row

    class Connection:
        def __init__(self, connection):
            self.connection = connection

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def execute(self, query, parameters=None, **kwargs):
            cursor = self.connection.execute(query, parameters, **kwargs)
            if (
                query == "SELECT * FROM mnemion.capture_grants WHERE grant_id=%s"
                and parameters == (grant_id,)
                and not interleaved
            ):
                return Cursor(cursor)
            return cursor

    @contextmanager
    def transaction(identity):
        with original_transaction(identity) as connection:
            yield Connection(connection)

    monkeypatch.setattr(service.db, "transaction", transaction)
    with request_replay() as observed:
        with pytest.raises(ServiceError, match="different or revoked device authorization"):
            service.grant(env.owner, source_id, grant_id, command)
    assert interleaved == [True]
    assert observed.value is None, "A conflicting request has no valid intake receipt"
    assert service.status(env.owner, grant_id)["source_id"] == str(other_source)


def test_five_capture_mutations_report_freshness_without_marking_reads(
    env, conversation_source, custody
):
    service, _, _, _, source_command = custody
    _, connector, operator, _, _, _ = conversation_source
    source_id, grant_id, transition_id = uuid4(), uuid4(), uuid4()
    source_path = f"/v1/connectors/{connector}/capture-sources/{source_id}"
    grant_path = f"/v1/capture-sources/{source_id}/grants/{grant_id}"
    revoke_path = f"/v1/capture-grants/{grant_id}"
    headers = {"Authorization": "Bearer " + env.token}

    with TestClient(create_app(env.db, env.embedder)) as client:

        def request(method, path, *, body=None, freshness=None, status=200):
            response = client.request(method, path, headers=headers, json=body)
            assert response.status_code == status, response.text
            assert response.headers.get("X-Mnemion-Idempotency") == freshness
            assert "X-Mnemion-Capture-Stored" not in response.headers
            return response.json()

        source_body = source_command.model_dump(mode="json")
        created = request("PUT", source_path, body=source_body, freshness="new")
        assert request("PUT", source_path, body=source_body, freshness="replayed") == created
        changed_body = {**source_body, "name": "Changed fixture", "expected_version": 1}
        changed = request("PUT", source_path, body=changed_body, freshness="new")
        assert request("PUT", source_path, body=changed_body, freshness="replayed") == changed
        request("PUT", source_path, body={**source_body, "name": "Stale fixture"}, status=409)

        grant_body = {"device_key_id": str(operator.key_id)}
        granted = request("PUT", grant_path, body=grant_body, freshness="new")
        assert request("PUT", grant_path, body=grant_body, freshness="replayed") == granted
        request("GET", revoke_path)
        request("GET", source_path + "/policy-review")
        policy_body = proposed(service, env.owner, connector, source_id).model_dump(mode="json")
        transition_path = source_path + f"/policy-transitions/{transition_id}"
        policy = request("PUT", transition_path, body=policy_body, freshness="new")
        assert request("PUT", transition_path, body=policy_body, freshness="replayed") == policy
        request(
            "PUT", transition_path, body={**policy_body, "previous_grants": "revoke"}, status=409
        )
        request("GET", source_path + "/policies")
        # Repeating enrollment retains the device's originally approved policy.
        assert (
            request("PUT", grant_path, body=grant_body, freshness="replayed")["policy_version"] == 1
        )
        revoked = request("DELETE", revoke_path, freshness="new")
        assert request("DELETE", revoke_path, freshness="replayed") == revoked
        request("PUT", grant_path, body=grant_body, status=409)
        retired = request("DELETE", source_path, freshness="new")
        assert request("DELETE", source_path, freshness="replayed") == retired
        request("GET", source_path)


def test_revocation_waiter_uses_the_state_after_acquiring_the_source_lock(
    env, conversation_source, custody, monkeypatch
):
    service, _, grant_id, _, _ = custody
    original = service._grant
    competing = []

    def interleaved(conn, identity, selected_grant, **kwargs):
        value = original(conn, identity, selected_grant, **kwargs)
        if selected_grant == grant_id and not competing:
            competing.append(None)
            with request_replay() as other:
                service.status(env.owner, grant_id, revoke=True)
            competing[0] = other.value
        return value

    monkeypatch.setattr(service, "_grant", interleaved)
    with request_replay() as current:
        revoked = service.status(env.owner, grant_id, revoke=True)
    assert revoked["revoked_at"] is not None
    assert competing == ["new"]
    assert current.value == "replayed"
