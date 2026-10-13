"""Compact discovery and optional sessions preserve live authorization."""

import json
from uuid import UUID

from fastapi.testclient import TestClient

from mnemion.service.api import create_app
from mnemion.service.models import GrantInput, KeyInput, MemoryInput, PrincipalInput


def request(client, token, method, params=None, session=None):
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json, text/event-stream"}
    if session:
        headers["Mcp-Session-Id"] = session
    return client.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )


def call(client, token, name, arguments=None, session=None):
    response = request(
        client, token, "tools/call", {"name": name, "arguments": arguments or {}}, session
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]


def test_compact_discovery_keeps_full_control_and_small_validated_schemas(env, monkeypatch):
    monkeypatch.setenv("MNEMION_MCP_TOOL_PROFILE", "compact")
    with TestClient(create_app(env.db, env.embedder), base_url="http://127.0.0.1") as client:
        listing = request(client, env.token, "tools/list").json()["result"]
        assert [tool["name"] for tool in listing["tools"]] == [
            "search",
            "fetch",
            "mnemion",
            "memory_profile",
        ]
        assert len(json.dumps(listing, separators=(",", ":")).encode()) < 4000
        search = listing["tools"][0]
        assert search["inputSchema"]["properties"]["query"]["maxLength"] == 4000
        assert search["inputSchema"]["properties"]["limit"]["maximum"] == 50
        assert "outputSchema" not in search
        assert listing["tools"][-1]["_meta"]["openai/profile"] is True
        catalog = call(client, env.token, "mnemion")["structuredContent"]
        assert catalog["next_offset"] > 0
        following = call(client, env.token, "mnemion", {"offset": catalog["next_offset"]})[
            "structuredContent"
        ]
        assert catalog["items"] != following["items"]
        filtered = call(client, env.token, "mnemion", {"query": "librarian"})["structuredContent"]
        assert filtered["items"] and all("librarian" in item["name"] for item in filtered["items"])
        described = call(
            client, env.token, "mnemion", {"action": "describe", "operation": "memories.save"}
        )
        assert not described["isError"] and described["structuredContent"]["input_schema"]
        saved = call(
            client,
            env.token,
            "mnemion",
            {
                "action": "write",
                "operation": "memories.save",
                "request": {
                    "parameters": {"space_id": str(env.space)},
                    "body": {"content": "Compact discovery evidence"},
                    "idempotency_key": "compact-save",
                },
            },
        )
        assert not saved["isError"], saved
        memory_id = saved["structuredContent"]["result"]["memory_id"]
        found = call(client, env.token, "search", {"query": "Compact discovery"})
        assert found["structuredContent"]["hits"][0]["memory_id"] == memory_id
        fetched = call(client, env.token, "fetch", {"memory_id": memory_id})
        assert fetched["structuredContent"]["content"] == "Compact discovery evidence"
        denied = call(
            client,
            env.token,
            "mnemion",
            {
                "action": "read",
                "operation": "spaces.create",
                "request": {"body": {"name": "Must not be created"}},
            },
        )
        assert denied["isError"] and denied["structuredContent"]["code"] == "wrong_effect"
        private = call(
            client,
            env.token,
            "mnemion",
            {
                "action": "write",
                "operation": "keys.create",
                "request": {
                    "parameters": {"principal_id": str(env.owner.principal_id)},
                    "body": {"name": "Must stay private"},
                },
            },
        )
        assert (
            private["isError"] and private["structuredContent"]["code"] == "private_file_required"
        )


def test_stateful_sdk_sessions_are_credential_bound_and_recheck_revocation(env, monkeypatch):
    monkeypatch.setenv("MNEMION_MCP_SESSIONS", "1")
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Session reader", kind="application")
    )
    principal = UUID(person["id"])
    first = env.identities.create_key(env.owner, principal, KeyInput(name="First device"))
    second = env.identities.create_key(env.owner, principal, KeyInput(name="Other device"))
    env.identities.grant(env.owner, env.space, principal, GrantInput(role="reader"))
    env.memory.save(
        env.owner, env.space, MemoryInput(content="Session evidence"), "session-evidence"
    )
    with TestClient(create_app(env.db, env.embedder), base_url="http://127.0.0.1") as client:
        initialized = request(
            client,
            first["api_key"],
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "session-fixture", "version": "1"},
            },
        )
        assert initialized.status_code == 200, initialized.text
        session = initialized.headers["Mcp-Session-Id"]
        found = call(client, first["api_key"], "search", {"query": "Session"}, session)
        assert found["structuredContent"]["hits"]
        crossed = request(client, second["api_key"], "tools/list", session=session)
        assert (
            crossed.status_code == 404
            and crossed.json()["error"]["code"] == "mcp_session_unavailable"
        )
        env.identities.revoke_grant(env.owner, env.space, principal)
        empty = call(client, first["api_key"], "search", {"query": "Session"}, session)
        assert empty["isError"] or empty["structuredContent"]["hits"] == []
        env.identities.revoke_key(env.owner, UUID(first["id"]))
        denied = request(client, first["api_key"], "tools/list", session=session)
        assert denied.status_code == 401


def test_default_http_transport_stays_stateless(env, monkeypatch):
    monkeypatch.delenv("MNEMION_MCP_SESSIONS", raising=False)
    with TestClient(create_app(env.db, env.embedder), base_url="http://127.0.0.1") as client:
        result = request(client, env.token, "tools/list")
        assert result.status_code == 200
        assert "Mcp-Session-Id" not in result.headers
        names = {tool["name"] for tool in result.json()["result"]["tools"]}
        assert {"search", "fetch", "memory_search", "memory_context", "mnemion"} <= names
