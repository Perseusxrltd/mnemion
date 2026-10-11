import asyncio
import os
import socket
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

import httpx
import httpx2
import pytest
import uvicorn
from mcp import Client as MCPClient, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

from mnemion.sdk import Client, MnemionError
from mnemion.service.api import create_app
from mnemion.service.contracts import IdentityInfo
from mnemion.service.mcp import create_mcp
from mnemion.service.models import KeyInput, PrincipalInput


def test_identity_contract_keeps_older_services_compatible():
    # A desktop/client patch must still accept a server that predates reporting.
    wire = {
        "principal_id": "fixture-person",
        "tenant_id": "fixture-team",
        "name": "Fixture person",
        "tenant_name": "Fixture team",
        "kind": "human",
        "administrator": False,
    }
    with Client(
        "https://example.invalid",
        "fixture-key",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=wire)),
    ) as client:
        identity = IdentityInfo.model_validate(client.request("GET", "/v1/me"))
    assert identity.service_version is None and not identity.administrator


def test_sdk_identifies_an_offline_tunnel_without_echoing_proxy_content():
    private = "private-fixture-token"
    with Client(
        "https://example.invalid",
        private,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                404,
                text=private,
                headers={"ngrok-error-code": "ERR_NGROK_3200", "X-Request-ID": private},
            )
        ),
    ) as client:
        with pytest.raises(MnemionError) as caught:
            client.request("GET", "/v1/me")
    assert caught.value.code == "tunnel_offline"
    assert caught.value.request_id is None and private not in str(caught.value)


@pytest.mark.parametrize("content_grant", [False, True])
def test_connection_doctor_accepts_an_independent_admins_visible_ungranted_spaces(
    env, content_grant
):
    from mnemion.connection_diagnostics import diagnose

    with running(create_app(env.db, env.embedder)) as url:
        with Client(url, env.token) as owner:
            person = owner.request(
                "POST",
                "/v1/principals",
                body={
                    "name": "Independent fixture administrator",
                    "kind": "human",
                    "administrator": True,
                },
            )
            key = owner.request(
                "POST", f"/v1/principals/{person['id']}/keys", body={"name": "Fixture access"}
            )
            if content_grant:
                owner.request(
                    "PUT", f"/v1/spaces/{env.space}/grants/{person['id']}", body={"role": "reader"}
                )
        report = asyncio.run(diagnose(url, key["api_key"]))
    assert report["ready"] is content_grant, report
    assert report["checks"]["identity"]["administrator"]
    assert report["checks"]["spaces"]["count"] == 1
    assert report["checks"]["spaces"]["accessible_count"] == int(content_grant)
    assert report["checks"]["spaces"]["code"] == ("ok" if content_grant else "no_spaces")
    assert report["checks"]["mcp"]["ok"]
    assert key["api_key"] not in str(report)


def test_connection_doctor_checks_real_api_and_mcp_without_memory_writes(env):
    from mnemion.connection_diagnostics import diagnose

    with running(create_app(env.db, env.embedder)) as url:
        report = asyncio.run(diagnose(url, env.token))
    assert report["ready"], report
    assert report["checks"]["mcp"]["tool_count"] >= 4
    assert report["checks"]["spaces"]["count"] >= 1
    assert env.token not in str(report) and str(env.space) not in str(report)


def test_sdk_respects_retry_after_without_replaying_an_unsafe_write(monkeypatch):
    delays, requests = [], []
    monkeypatch.setattr("mnemion.sdk.time.sleep", delays.append)

    def busy(request):
        requests.append(request)
        return httpx.Response(
            503,
            headers={"Retry-After": "1"},
            json={
                "error": {"code": "inference_busy", "message": "Busy"},
                "request_id": "request-test",
            },
        )

    with Client(
        "http://mnemion.test", "fixture-key", transport=httpx.MockTransport(busy), retries=1
    ) as client:
        with pytest.raises(MnemionError) as caught:
            client.request("POST", "/v1/recall", body={"query": "test", "all_accessible": True})
        assert delays == [1] and len(requests) == 2
        assert caught.value.retryable and caught.value.retry_after == 1
        requests.clear()
        delays.clear()
        with pytest.raises(MnemionError):
            client.request("POST", "/v1/principals", body={"name": "Not safe to replay"})
        assert len(requests) == 1 and delays == []


@contextmanager
def running(app):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started, "Test server did not start"
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(5)
        listener.close()
        assert not thread.is_alive(), "Test server did not stop"


def test_python_sdk_real_http_roundtrip_and_optimistic_updates(env, tmp_path):
    with running(create_app(env.db, env.embedder)) as url, Client(url, env.token) as client:
        saved = client.save(
            str(env.space),
            "Billing uses Postgres",
            idempotency_key="sdk",
            subject="Billing app",
            metadata={"owner": "Finance"},
        )
        assert saved.state == "accepted"
        assert (
            client.save(
                str(env.space),
                "Billing uses Postgres",
                idempotency_key="sdk",
                subject="Billing app",
                metadata={"owner": "Finance"},
            )
            == saved
        )
        result = client.search("Billing", [str(env.space)], mode="lexical")
        assert result.hits[0].memory_id == saved.memory_id
        updated = client.revise(
            saved.memory_id,
            "Billing uses Postgres replicas",
            expected_version=1,
            reason="Replication",
            idempotency_key="sdk-update",
        )
        record = client.fetch(saved.memory_id)
        assert (
            record.version == 2
            and record.subject == "Billing app"
            and record.metadata["owner"] == "Finance"
        )
        with pytest.raises(MnemionError) as error:
            client.revise(
                saved.memory_id,
                "Stale edit",
                expected_version=1,
                reason="Stale",
                idempotency_key="sdk-stale",
            )
        assert error.value.code == "version_conflict"
        assert client.sync_obsidian(str(tmp_path / "vault"), [str(env.space)])["completed"]
        assert client.operation(updated.operation_id)["state"] == "accepted"
        changes = client.activity(str(env.space), memory_id=saved.memory_id)
        assert any(event.reason == "Replication" for event in changes)
        assert client.forget(saved.memory_id, expected_version=2).deleted
        assert all(event.reason is None for event in client.activity(str(env.space)))
        repeated = client.forget(saved.memory_id, expected_version=2)
        assert repeated.deleted and repeated.space_id == str(env.space)
        while env.worker.run_once():
            pass
        assert client.forget(saved.memory_id, expected_version=2).state == "ready"


def test_python_sdk_retries_preserve_one_write_identity():
    calls = []

    def transport(request):
        calls.append((request.headers["Idempotency-Key"], request.content))
        if len(calls) == 1:
            raise httpx.ReadTimeout("Connection closed after commit")
        return httpx.Response(
            202,
            json={
                "operation_id": "operation",
                "memory_id": "memory",
                "revision_id": "revision",
                "space_id": "space",
                "state": "accepted",
            },
        )

    with Client("http://example.test", "dummy", transport=httpx.MockTransport(transport)) as client:
        assert client.save("space", "evidence").state == "accepted"
    assert len(calls) == 2 and calls[0] == calls[1]


def test_mcp_stdio_negotiation_and_tools_use_http_contract(env):
    with running(create_app(env.db, env.embedder)) as url:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mnemion.service.cli", "mcp", "--legacy-space", str(env.space)],
            cwd=str(Path(__file__).resolve().parents[1]),
            env={**os.environ, "MNEMION_API_URL": url, "MNEMION_API_KEY": env.token},
        )

        async def run():
            async with MCPClient(parameters, read_timeout_seconds=15) as client:
                names = {tool.name for tool in (await client.list_tools()).tools}
                assert {
                    "memory_spaces",
                    "memory_map",
                    "memory_save",
                    "memory_search",
                    "memory_fetch",
                    "memory_context",
                    "memory_revise",
                    "memory_forget",
                    "capture_thought",
                    "search",
                    "fetch",
                } <= names
                spaces = await client.call_tool("memory_spaces", {})
                assert not spaces.is_error
                assert any(
                    row["id"] == str(env.space) and row["role"] == "administrator"
                    for row in spaces.structured_content["items"]
                )
                saved = await client.call_tool(
                    "memory_save",
                    {
                        "space_id": str(env.space),
                        "content": "Billing evidence from stdio",
                        "idempotency_key": "mcp-stdio",
                    },
                )
                assert not saved.is_error, saved
                payload = saved.structured_content
                assert payload["state"] == "accepted"
                fetched = await client.call_tool(
                    "memory_fetch", {"memory_id": payload["memory_id"]}
                )
                assert (
                    not fetched.is_error
                    and fetched.structured_content["content"] == "Billing evidence from stdio"
                )
                mapped = await client.call_tool(
                    "memory_map", {"space_ids": [], "all_accessible": True}
                )
                assert not mapped.is_error
                assert (
                    "memories" not in mapped.structured_content
                    and "markdown" not in mapped.structured_content
                )
                assert any(
                    node.get("memory_id") == payload["memory_id"]
                    for node in mapped.structured_content["nodes"]
                )

        asyncio.run(run())


def test_typescript_sdk_real_http_shared_memory_and_revocation(env):
    root = Path(__file__).resolve().parents[1]
    if not shutil.which("node") or not (root / "packages/client/dist/index.js").is_file():
        if os.environ.get("MNEMION_REQUIRE_NODE_SDK") == "1":
            pytest.fail("Build packages/client before the required Node integration test")
        pytest.skip("Build packages/client to exercise the real Node client")
    with running(create_app(env.db, env.embedder)) as url:
        result = subprocess.run(
            ["node", "packages/client/test/integration.mjs"],
            cwd=root,
            env={
                **os.environ,
                "MNEMION_API_URL": url,
                "MNEMION_API_KEY": env.token,
                "MNEMION_SPACE_ID": str(env.space),
            },
            text=True,
            capture_output=True,
            timeout=30,
        )
    assert result.returncode == 0, result.stderr


def test_mcp_http_auth_is_per_request_and_never_falls_back_to_owner(env):
    principal = env.identities.create_principal(
        env.owner, PrincipalInput(name="Unscoped application")
    )
    key = env.identities.create_key(env.owner, UUID(principal["id"]), KeyInput(name="Unscoped"))
    with running(create_app(env.db, env.embedder)) as api_url:
        # Deliberately configure a stdio credential too: HTTP must still require
        # and use each request's own credential, never this owner fallback.
        gateway = create_mcp(api_url, stdio_token=env.token)
        with running(
            gateway.streamable_http_app(stateless_http=True, json_response=True)
        ) as gateway_url:

            async def call(token, mode="auto"):
                headers = {"Authorization": "Bearer " + token} if token else {}
                async with httpx2.AsyncClient(headers=headers) as http:
                    async with MCPClient(
                        streamable_http_client(gateway_url + "/mcp", http_client=http),
                        mode=mode,
                        read_timeout_seconds=15,
                    ) as client:
                        return await client.call_tool(
                            "memory_save",
                            {
                                "space_id": str(env.space),
                                "content": "HTTP gateway evidence",
                                "idempotency_key": "mcp-http-" + mode,
                            },
                        )

            async def run():
                async with httpx2.AsyncClient() as raw:
                    for method in ("initialize", "tools/list"):
                        response = await raw.post(
                            gateway_url + "/mcp",
                            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": {}},
                        )
                        assert response.status_code == 401
                        assert response.headers["WWW-Authenticate"].startswith("Bearer")
                        assert "memory_save" not in response.text
                    response = await raw.post(
                        gateway_url + "/mcp",
                        headers={"Authorization": "Bearer invalid-key"},
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    )
                    assert response.status_code == 401
                    duplicate = await raw.post(
                        gateway_url + "/mcp",
                        headers=[
                            ("Authorization", "Bearer " + env.token),
                            ("Authorization", "Bearer invalid-key"),
                        ],
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    )
                    assert duplicate.status_code == 401
                unauthorized = await call(key["api_key"])
                assert unauthorized.is_error
                assert unauthorized.structured_content["code"] == "not_found"
                assert unauthorized.structured_content["retryable"] is False
                for mode in ("auto", "legacy"):
                    allowed = await call(env.token, mode)
                    assert not allowed.is_error, allowed
                    assert allowed.structured_content["state"] == "accepted"
                env.identities.revoke_key(env.owner, UUID(key["id"]))
                async with httpx2.AsyncClient() as raw:
                    revoked = await raw.post(
                        gateway_url + "/mcp",
                        headers={"Authorization": "Bearer " + key["api_key"]},
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    )
                    assert revoked.status_code == 401

            asyncio.run(run())


def test_combined_mcp_uses_one_port_and_preserves_api_auth_and_structured_errors(env):
    with running(create_app(env.db, env.embedder)) as api_url:

        async def run():
            async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + env.token}) as http:
                async with MCPClient(
                    streamable_http_client(api_url + "/mcp", http_client=http),
                    read_timeout_seconds=15,
                ) as client:
                    tools = await client.list_tools()
                    for tool in tools.tools:
                        for name, field in tool.input_schema.get("properties", {}).items():
                            assert field.get("description"), (tool.name, name)
                    invalid = await client.call_tool(
                        "memory_search",
                        {"query": "private-query-sentinel", "space_ids": ["private-invalid-uuid"]},
                    )
                    assert invalid.is_error
                    assert invalid.structured_content["code"] == "invalid_arguments"
                    assert "private-invalid-uuid" not in str(invalid)
                    assert "private-query-sentinel" not in str(invalid)
                    no_scope = await client.call_tool(
                        "memory_search", {"query": "test", "space_ids": []}
                    )
                    assert no_scope.is_error
                    assert "all_accessible=true" in no_scope.structured_content["message"]
                    saved = await client.call_tool(
                        "memory_save",
                        {
                            "space_id": str(env.space),
                            "content": "Combined MCP evidence",
                            "idempotency_key": "combined-mcp",
                        },
                    )
                    assert not saved.is_error, saved
                    fetched = await client.call_tool(
                        "memory_fetch", {"memory_id": saved.structured_content["memory_id"]}
                    )
                    assert not fetched.is_error
                    assert fetched.structured_content["content"] == "Combined MCP evidence"
                    # More tools than the gateway worker capacity must make progress.
                    results = await asyncio.gather(
                        *[client.call_tool("memory_spaces", {}) for _ in range(12)]
                    )
                    assert all(not result.is_error for result in results)

        asyncio.run(run())


def test_mcp_public_host_is_explicit_and_other_hosts_remain_rejected(env):
    with running(create_app(env.db, env.embedder, mcp_enabled=False)) as api_url:
        gateway = create_mcp(api_url, public_url="https://memory.example.com")
        with running(gateway.streamable_http_app(stateless_http=True, json_response=True)) as url:
            headers = {
                "Authorization": "Bearer " + env.token,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            message = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "gateway-test", "version": "1"},
                },
            }
            allowed = httpx.post(
                url + "/mcp",
                headers={
                    **headers,
                    "Host": "memory.example.com",
                    "Origin": "https://memory.example.com",
                },
                json=message,
            )
            assert allowed.status_code == 200, allowed.text
            refused = httpx.post(
                url + "/mcp", headers={**headers, "Host": "unapproved.example.com"}, json=message
            )
            assert refused.status_code == 421
            wrong_origin = httpx.post(
                url + "/mcp",
                headers={
                    **headers,
                    "Host": "memory.example.com",
                    "Origin": "https://unapproved.example.com",
                },
                json=message,
            )
            assert wrong_origin.status_code == 403
