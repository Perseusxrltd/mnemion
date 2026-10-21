"""Real HTTP service commits, lost replies and restarted local inbox delivery."""

import os
from uuid import UUID

import httpx
import pytest

from mnemion.connectors.capture_delivery import deliver
from mnemion.connectors.conversation_capture import capture_available
from mnemion.connectors.conversation_inbox import InboxError, open_inbox
from mnemion.connectors.live_conversations import ConversationProvider
from mnemion.sdk import Client, MnemionError
from mnemion.service.api import create_app
from service_tests.test_clients import running
from service_tests.test_capture_custody import custody as custody
from service_tests.test_live_conversations import (
    conversation_source as conversation_source,
    encoded,
)


def settings(env, custody, conversation_source, tmp_path):
    _, source_id, grant_id, _, _ = custody
    _, connector, _, _, _, config = conversation_source
    config.provider.capture_mode = "messages"
    binding = {
        "tenant_id": str(env.owner.tenant_id),
        "connector_id": str(connector),
        "source_id": str(source_id),
        "grant_id": str(grant_id),
        "namespace": "fixture",
        "capture_mode": "messages",
    }
    return tmp_path / "private-inbox", binding, os.urandom(32)


@pytest.mark.parametrize("forget_while_offline", [False, True])
def test_local_capture_then_lost_http_reply_restart_and_current_forgetting(
    env, custody, conversation_source, tmp_path, forget_while_offline
):
    private = settings(env, custody, conversation_source, tmp_path)
    _, _, _, reader, secret, config = conversation_source
    path = config.provider.path / "chat.jsonl"
    path.write_bytes(
        encoded("Evidence accepted while offline")
        + encoded("Tool text excluded by selection", "tool")
    )
    with open_inbox(*private, create=True) as inbox:
        captured = capture_available(inbox, ConversationProvider(config.provider))
        assert captured["completed"] and captured["pending_events"] == 1
    path.unlink()
    committed = []
    with (
        running(create_app(env.db, env.embedder)) as url,
        Client(url, secret, retries=0) as client,
        open_inbox(*private) as inbox,
    ):
        original = client.request

        def lose_one_reply(method, route, **kwargs):
            assert not inbox.connection.in_transaction, (
                "Never keep a SQLite transaction across HTTP"
            )
            value = original(method, route, **kwargs)
            if method == "POST" and route.endswith("/pages"):
                committed.append(value)
                raise httpx.ReadTimeout("Synthetic lost reply after the actual service commit")
            return value

        client.request = lose_one_reply
        with pytest.raises(httpx.ReadTimeout):
            deliver(inbox, client)
        assert inbox.status()["unknown_pages"] == 1 and inbox.status()["pending_events"] == 1
    assert len(committed) == 1
    memory = UUID(committed[0]["items"][0]["memory_id"])
    assert env.memory.fetch(reader, memory)["content"].find("Evidence accepted while offline") >= 0
    if forget_while_offline:
        env.memory.forget(
            reader, memory, expected_version=1, key="forgotten-during-offline-capture"
        )
    # New service listener, new client and reopened encrypted local state.
    requests = []
    with (
        running(create_app(env.db, env.embedder)) as url,
        Client(url, secret, retries=0) as client,
        open_inbox(*private) as inbox,
    ):
        original = client.request

        def observed(method, route, **kwargs):
            requests.append((method, route))
            return original(method, route, **kwargs)

        client.request = observed
        result = deliver(inbox, client)
        assert result["pending_events"] == result["unknown_pages"] == 0
        assert result["forgotten_events"] == int(forget_while_offline)
        assert not any(method == "POST" for method, _ in requests)
        if not forget_while_offline:
            assert any(route.endswith("/pages/" + committed[0]["page_id"]) for _, route in requests)
    if forget_while_offline:
        from mnemion.service.errors import ServiceError

        with pytest.raises(ServiceError):
            env.memory.fetch(reader, memory)


def test_revoked_device_retains_local_evidence_without_attempting_delivery(
    env, custody, conversation_source, tmp_path
):
    private = settings(env, custody, conversation_source, tmp_path)
    service, _, grant_id, _, _ = custody
    _, _, _, _, secret, config = conversation_source
    (config.provider.path / "chat.jsonl").write_bytes(encoded("Accepted before grant revocation"))
    with open_inbox(*private, create=True) as inbox:
        capture_available(inbox, ConversationProvider(config.provider))
    service.status(env.owner, grant_id, revoke=True)
    with (
        running(create_app(env.db, env.embedder)) as url,
        Client(url, secret, retries=0) as client,
        open_inbox(*private) as inbox,
    ):
        original = client.request

        def no_write(method, route, **kwargs):
            assert method == "GET"
            return original(method, route, **kwargs)

        client.request = no_write
        with pytest.raises((InboxError, MnemionError)):
            deliver(inbox, client)
        assert inbox.status()["pending_events"] == 1
        assert inbox.status()["unknown_pages"] == 0
