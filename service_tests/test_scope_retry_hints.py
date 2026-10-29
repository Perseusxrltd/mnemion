import asyncio

import httpx
import httpx2
import pytest
from mcp import Client as MCPClient
from mcp.client.streamable_http import streamable_http_client

from mnemion import agent_control
from mnemion.sdk import Client, MnemionError
from mnemion.service.api import create_app
from mnemion.service.models import SpaceInput
from service_tests.test_clients import running


def test_real_scope_change_exposes_a_retry_hint_then_a_fresh_mcp_search_succeeds(env, monkeypatch):
    query = env.embedder.query
    changes = []

    def expand_once(text):
        if not changes:
            changes.append(env.identities.create_space(env.owner, SpaceInput(name="New scope")))
        return query(text)

    monkeypatch.setattr(env.embedder, "query", expand_once)
    with running(create_app(env.db, env.embedder)) as url:

        async def exercise():
            async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + env.token}) as http:
                async with MCPClient(
                    streamable_http_client(url + "/mcp", http_client=http),
                    read_timeout_seconds=15,
                ) as client:
                    arguments = {"query": "billing", "all_accessible": True}
                    refused = await client.call_tool("memory_search", arguments)
                    assert (
                        refused.is_error and refused.structured_content["code"] == "scope_changed"
                    )
                    assert refused.structured_content["retryable"] is True
                    assert "New scope" not in str(refused)
                    fresh = await client.call_tool("memory_search", arguments)
                    assert not fresh.is_error and fresh.structured_content["hits"] == []

        asyncio.run(exercise())
    assert len(changes) == 1


def test_sdk_scope_hint_does_not_replay_reads_or_change_other_conflicts():
    calls = []
    responses = iter(["scope_changed", "generation_changed", "version_conflict"])

    def reject(request):
        calls.append(request)
        return httpx.Response(
            409, json={"error": {"code": next(responses), "message": "Refresh the request"}}
        )

    with Client(
        "https://example.invalid", "fixture-key", transport=httpx.MockTransport(reject), retries=2
    ) as client:
        for code in ("scope_changed", "generation_changed", "version_conflict"):
            before = len(calls)
            with pytest.raises(MnemionError) as caught:
                client.search("billing", all_accessible=True)
            assert caught.value.code == code
            assert len(calls) == before + 1
            assert caught.value.retryable is (code == "scope_changed")


@pytest.mark.parametrize("status,outcome", [(409, "rejected"), (503, "unknown")])
def test_unprotected_write_keeps_its_agent_retry_fence(monkeypatch, status, outcome):
    # The same response cannot authorize replaying an unprotected write.
    calls, delays = [], []
    monkeypatch.setattr(agent_control.time, "sleep", delays.append)

    def conflict(request):
        calls.append(request)
        return httpx.Response(
            status, json={"error": {"code": "scope_changed", "message": "Refresh the search"}}
        )

    with Client(
        "https://example.invalid", "fixture-key", transport=httpx.MockTransport(conflict), retries=2
    ) as client:
        with pytest.raises(agent_control.ControlError) as write:
            agent_control.execute(client, "principals.create", {"body": {"name": "Fixture"}})
        assert len(calls) == 1 and delays == []
        assert write.value.outcome == outcome and not write.value.retryable
        with pytest.raises(agent_control.ControlError) as read:
            agent_control.execute(client, "spaces.list")
        assert len(calls) == (2 if status == 409 else 4) and read.value.retryable
