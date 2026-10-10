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
from mnemion.service.mcp import create_mcp
from mnemion.service.models import KeyInput, PrincipalInput


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
                assert (await call(None)).is_error
                unauthorized = await call(key["api_key"])
                assert unauthorized.is_error
                for mode in ("auto", "legacy"):
                    allowed = await call(env.token, mode)
                    assert not allowed.is_error, allowed
                    assert allowed.structured_content["state"] == "accepted"

            asyncio.run(run())
