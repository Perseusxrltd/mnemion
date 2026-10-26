"""Real HTTP service commits, lost replies and restarted local inbox delivery."""

import os
from dataclasses import replace
from uuid import UUID

import httpx
import pytest

from mnemion.connectors.capture_delivery import deliver
from mnemion.connectors.capture_cycle import cycle
from mnemion.connectors.conversation_capture import capture_available
from mnemion.connectors.conversation_inbox import InboxError, Limits, open_inbox
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
        assert result["newly_stored_events"] == 0, "Readback must not become a fresh commit"
        assert result["forgotten_events"] == int(forget_while_offline)
        observed = result["coverage"]["index"]
        assert observed["status"] == "available"
        assert observed["completed"]["counts"]["events"] == 1
        assert observed["completed"]["counts"]["forgotten"] == int(forget_while_offline)
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


@pytest.mark.parametrize("failure", ["second_page_reply", "index_authorization"])
def test_cycle_preserves_acknowledged_progress_when_later_delivery_work_fails(
    env, custody, conversation_source, tmp_path, failure
):
    private = settings(env, custody, conversation_source, tmp_path)
    _, _, _, _, secret, config = conversation_source
    count = 51 if failure == "second_page_reply" else 2
    for index in range(count):
        (config.provider.path / f"part-{index:03d}.jsonl").write_bytes(encoded(f"Selected {index}"))
    provider = ConversationProvider(config.provider)
    requests, revocations = [], []
    with (
        running(create_app(env.db, env.embedder)) as url,
        open_inbox(*private, create=True) as inbox,
    ):

        def remote():
            client = Client(url, secret, retries=0)
            original = client.request

            def observed(method, route, **options):
                if failure == "index_authorization" and route.endswith("/index-progress"):
                    raise MnemionError(403, "capture_authorization_revoked", "Synthetic revocation")
                value = original(method, route, **options)
                if method == "POST" and route.endswith("/pages"):
                    requests.append(value)
                    if failure == "second_page_reply" and len(requests) == 2:
                        raise httpx.ReadTimeout("Synthetic lost second-page reply after commit")
                return value

            client.request = observed
            return client

        result = cycle(
            inbox,
            collect=lambda: capture_available(inbox, provider),
            client=remote,
            revoked=lambda: revocations.append(True),
            usage=lambda: inbox.status(),
        )
        capture = result["capture"]
        assert not result["completed"]
        assert capture["locally_accepted"] == count
        assert result["changed"] == capture["remote_committed_events"] == (50 if count == 51 else 2)
        assert capture["newly_stored_events"] == (None if count == 51 else 2)
        assert len(requests) == (2 if count == 51 else 1)
        assert bool(revocations) == (failure == "index_authorization")
        if failure == "second_page_reply":
            assert capture["pending_events"] == capture["unknown_pages"] == 1
            with Client(url, secret, retries=0) as recovered:
                settled = deliver(inbox, recovered)
            assert settled["remote_committed_events"] == 1
            assert settled["newly_stored_events"] == settled["pending_events"] == 0


def test_older_client_delivers_without_claiming_fresh_effect_metadata(
    env, custody, conversation_source, tmp_path
):
    private = settings(env, custody, conversation_source, tmp_path)
    _, _, _, _, secret, config = conversation_source
    (config.provider.path / "chat.jsonl").write_bytes(encoded("Legacy delivery"))
    with (
        running(create_app(env.db, env.embedder)) as url,
        Client(url, secret, retries=0) as client,
        open_inbox(*private, create=True) as inbox,
    ):
        client.request_with_receipt = None
        capture_available(inbox, ConversationProvider(config.provider))
        result = deliver(inbox, client)
        assert result["remote_committed_events"] == 1 and result["pending_events"] == 0
        assert result["newly_stored_events"] is None


def test_real_service_fence_overflow_preserves_delivery_and_all_held_deletions(
    env, custody, conversation_source, tmp_path
):
    private = settings(env, custody, conversation_source, tmp_path)
    _, binding, key = private
    _, _, _, reader, secret, config = conversation_source
    provider = ConversationProvider(config.provider)
    with running(create_app(env.db, env.embedder)) as url, Client(url, secret, retries=0) as client:
        # A different device already learned three deletions for this source.
        for index in range(3):
            (config.provider.path / f"foreign-{index}.jsonl").write_bytes(
                encoded(f"Foreign {index}")
            )
        with open_inbox(tmp_path / "other-device", binding, key, create=True) as other:
            capture_available(other, provider)
            page = other.page()["page"]
            accepted = client.request(
                "POST", f"/v1/capture-grants/{binding['grant_id']}/pages", body=page
            )
            other.acknowledge(accepted)
        for index, item in enumerate(accepted["items"]):
            env.memory.forget(
                reader,
                UUID(item["memory_id"]),
                expected_version=1,
                key=f"foreign-forgotten-{index}",
            )
        for path in config.provider.path.glob("foreign-*.jsonl"):
            path.unlink()
        for index in range(3):
            (config.provider.path / f"held-{index}.jsonl").write_bytes(encoded(f"Held {index}"))
        with open_inbox(*private, create=True) as inbox:
            assert capture_available(inbox, provider)["pending_events"] == 3
            held_page = inbox.page()["page"]
        with open_inbox(*private, limits=replace(Limits(), events=1)) as inbox:
            result = deliver(inbox, client)
            assert result["history"]["fence_history_blocked"] and result["fence_sweep_pending"]
            assert result["remote_committed_events"] == result["stored_events"] == 3
            assert result["pending_events"] == result["unknown_pages"] == 0
            held = client.request(
                "GET", f"/v1/capture-grants/{binding['grant_id']}/pages/{held_page['page_id']}"
            )
            for index, item in enumerate(held["items"]):
                env.memory.forget(
                    reader,
                    UUID(item["memory_id"]),
                    expected_version=1,
                    key=f"held-forgotten-{index}",
                )
            result = deliver(inbox, client)
            assert result["forgotten_events"] == 3 and result["stored_events"] == 0
            assert result["history"]["fence_history_blocked"]
            paused = capture_available(inbox, provider)
            assert not paused["completed"] and paused["errors"] == ["capture_fence_capacity"]
        with open_inbox(*private) as inbox:
            assert inbox.fence_history_blocked(), "A larger limit alone cannot erase the pause"
            recovered = deliver(inbox, client)
            assert not recovered["fence_sweep_pending"]
            assert not recovered["history"]["fence_history_blocked"]
            assert recovered["history"]["denials"] == 6
            assert recovered["forgotten_events"] == 3
