import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import time
from uuid import UUID, uuid4

import anyio
import httpx
import httpx2
import pytest
from jsonschema import Draft202012Validator
from mcp import Client as MCPClient
from mcp.client.streamable_http import streamable_http_client

from mnemion import agent_control as control
from mnemion import control_cli
from mnemion.sdk import Client
from mnemion.service.agent_contract import CONTRACT_PATH, build_contract
from mnemion.service.api import create_app
from mnemion.service.mcp_transport import InProcessAPITransport
from mnemion.service.models import KeyInput, PrincipalInput
from service_tests.test_clients import running


def test_reviewed_catalog_matches_every_public_operation_and_standalone_schema():
    schema = json.loads(Path("docs/service/openapi.json").read_text())
    contract = build_contract(schema)
    assert contract == json.loads(CONTRACT_PATH.read_text())
    operations = control.catalog(limit=100)
    assert operations["total"] == len(contract["operations"]) >= 81
    received = 0
    for offset in range(0, operations["total"], 100):
        page = operations if offset == 0 else control.catalog(offset=offset, limit=100)
        received += len(page["items"])
        expected_next = received if received < operations["total"] else None
        assert page["next_offset"] == expected_next
    assert received == operations["total"]
    assert control.catalog(limit=1)["next_offset"] == 1
    assert len(control.catalog(query="keys.create")["items"]) == 1
    for operation in contract["operations"]:
        Draft202012Validator.check_schema(operation["input_schema"])
        if operation["output_schema"]:
            Draft202012Validator.check_schema(operation["output_schema"])
    for path in ("/v1/new-unreviewed-action", "/v1/agent/unreviewed-action"):
        schema["paths"][path] = {"post": {}}
        with pytest.raises(ValueError, match="reviewed"):
            build_contract(schema)
        del schema["paths"][path]
    changed = control.describe("spaces.list")
    changed["path"] = "https://untrusted.invalid/"
    assert control.describe("spaces.list")["path"] == "/v1/spaces"


def test_validation_rejects_path_headers_effects_and_unbounded_inputs_without_requests():
    for name, request in [
        ("memories.get", {"parameters": {"memory_id": "../../principals"}}),
        ("spaces.list", {"headers": {"Authorization": "private-sentinel"}}),
        (
            "memories.save",
            {
                "parameters": {"space_id": str(uuid4())},
                "body": {"content": "x"},
                "idempotency_key": "bad\nheader",
            },
        ),
        ("spaces.create", {"body": {"name": float("nan")}}),
        ("spaces.create", {"body": {"name": "x" * control.INPUT_LIMIT}}),
        ("spaces.list", [1]),
    ]:
        with pytest.raises(control.ControlError) as caught:
            control.prepare(name, request)
        assert caught.value.outcome == "not_sent"
        assert "private-sentinel" not in str(caught.value)
    with pytest.raises(control.ControlError, match="matching read or write"):
        control.prepare("spaces.create", {"body": {"name": "Team"}}, effect="read")
    for kwargs in ({"offset": True}, {"limit": 1.5}, {"query": []}, {"group": "x" * 201}):
        with pytest.raises(control.ControlError):
            control.catalog(**kwargs)


def test_read_backpressure_is_obeyed_and_unknown_mutations_are_not_retried(monkeypatch):
    calls, delays = [], []
    monkeypatch.setattr(control.time, "sleep", delays.append)

    def busy(request):
        calls.append(request)
        return httpx.Response(
            503,
            headers={"Retry-After": "2"},
            json={"error": {"code": "inference_busy", "message": "private diagnostic"}},
        )

    with Client(
        "http://mnemion.test", "fixture-key", retries=1, transport=httpx.MockTransport(busy)
    ) as client:
        with pytest.raises(control.ControlError) as read:
            control.execute(client, "spaces.list")
        assert len(calls) == 2 and delays == [2]
        assert read.value.retryable and read.value.retry_after == 2
        calls.clear()
        delays.clear()
        with pytest.raises(control.ControlError) as write:
            control.execute(client, "principals.create", {"body": {"name": "Agent"}})
        assert len(calls) == 1 and delays == []
        assert write.value.outcome == "unknown" and not write.value.retryable
        assert "private diagnostic" not in str(write.value)


def test_an_interrupted_idempotent_write_reuses_the_exact_validated_request(monkeypatch):
    calls = []
    monkeypatch.setattr(control.time, "sleep", lambda _: None)

    def response(request):
        calls.append((request.headers["Idempotency-Key"], request.content))
        if len(calls) == 1:
            raise httpx.ReadTimeout("Interrupted after acceptance")
        return httpx.Response(202, json={"state": "accepted"})

    with Client(
        "http://mnemion.test", "fixture-key", transport=httpx.MockTransport(response)
    ) as client:
        result = control.execute(
            client,
            "memories.save",
            {
                "parameters": {"space_id": str(uuid4())},
                "body": {"content": "Evidence"},
                "idempotency_key": "one-logical-write",
            },
        )
    assert result["attempts"] == 2 and calls[0] == calls[1]


def test_concurrent_writes_expose_receipt_replay_without_leaking_request_state(env):
    request = {
        "parameters": {"space_id": str(env.space)},
        "body": {"content": "Synthetic receipt observation"},
        "idempotency_key": "same-logical-fixture-write",
    }
    with running(create_app(env.db, env.embedder)) as url:

        def save(_):
            with Client(url, env.token) as client:
                return control.execute(client, "memories.save", request)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.map(save, range(2))
        assert {first["idempotency"], second["idempotency"]} == {"new", "replayed"}
        assert first["result"] == second["result"]
        with Client(url, env.token) as client:
            inspected = client._http.get("/v1/spaces")
            assert inspected.status_code == 200
            assert "X-Mnemion-Idempotency" not in inspected.headers
            assert control.execute(client, "spaces.list")["idempotency"] is None


def test_response_bounds_reject_hostile_lengths_and_never_publish_truncated_json():
    for length in ("9" * 5000, "١٢٣", "-1", "2001"):
        response = httpx.Response(
            200, headers=[(b"Content-Length", length.encode())], stream=httpx.ByteStream(b"{}")
        )
        try:
            with pytest.raises(control.ControlError):
                control._read_bytes(response, 2000, time.monotonic() + 5)
        finally:
            response.close()
    with Client(
        "http://mnemion.test",
        "fixture-key",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"content": "x" * 2000})),
    ) as client:
        with pytest.raises(control.ControlError) as error:
            control.execute(client, "spaces.list", max_response_bytes=1024)
        assert error.value.code == "response_too_large" and error.value.outcome == "unknown"


def test_download_failure_does_not_truncate_a_callers_existing_stream():
    output = io.BytesIO(b"existing bytes")
    output.seek(0, 2)
    response = httpx.Response(200, headers={"X-Content-SHA256": "0" * 64}, content=b"new bytes")
    with Client(
        "http://mnemion.test", "fixture-key", transport=httpx.MockTransport(lambda _: response)
    ) as client:
        with pytest.raises(control.ControlError) as error:
            control.execute(
                client,
                "sources.attachment",
                {"parameters": {"source_revision_id": str(uuid4()), "attachment_id": str(uuid4())}},
                output=output,
            )
    assert error.value.code == "response_hash_mismatch"
    assert output.getvalue() == b"existing bytesnew bytes"


def test_response_budget_expires_when_a_peer_trickles_tiny_chunks(monkeypatch):
    clock = {"now": 0}
    monkeypatch.setattr(control.time, "monotonic", lambda: clock["now"])

    class Trickle(httpx.SyncByteStream):
        def __iter__(self):
            for instant in (0, 20, 100):
                clock["now"] = instant
                yield b"x"

    response = httpx.Response(200, stream=Trickle())
    output = io.BytesIO()
    try:
        with pytest.raises(control.ControlError) as error:
            control._read_bytes(response, 1024, 90, sink=output)
        assert error.value.code == "response_deadline" and output.getvalue() == b"xx"
    finally:
        response.close()


def test_cli_reserves_private_key_results_before_mutation_and_never_prints_them(
    tmp_path, monkeypatch, capsys
):
    calls = []
    secret = "mnm_" + "synthetic" * 5

    def response(request):
        calls.append(request)
        return httpx.Response(201, json={"id": str(uuid4()), "api_key": secret})

    monkeypatch.setenv("MNEMION_API_KEY", "fixture-key")
    monkeypatch.setenv("MNEMION_API_URL", "http://127.0.0.1:7892")
    monkeypatch.setattr(
        control_cli,
        "Client",
        lambda *a, **kw: Client(*a, **kw, transport=httpx.MockTransport(response)),
    )
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps({"parameters": {"principal_id": str(uuid4())}, "body": {"name": "Agent key"}})
    )
    args = ["call", "keys.create", "--input", str(request)]
    assert control_cli.main(args) == 1 and not calls
    assert "private_result_required" in capsys.readouterr().out
    result = tmp_path / "new-key.json"
    result.write_bytes(b"Keep existing data")
    assert control_cli.main([*args, "--result-file", str(result)]) == 1 and not calls
    assert result.read_bytes() == b"Keep existing data"
    capsys.readouterr()
    result.unlink()
    assert control_cli.main([*args, "--result-file", str(result)]) == 0 and len(calls) == 1
    assert json.loads(result.read_text())["api_key"] == secret
    assert control_cli.connection(result, None) == ("http://127.0.0.1:7892", secret)
    assert secret not in capsys.readouterr().out


def test_in_process_transport_bounds_before_buffering_the_entire_response():
    sent = []

    async def application(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        for i in range(100):
            sent.append(i)
            await send({"type": "http.response.body", "body": b"x" * 1024, "more_body": i < 99})

    async def run():
        def call():
            with httpx.Client(transport=InProcessAPITransport(application, maximum=2048)) as client:
                with pytest.raises(httpx.ReadError):
                    client.get("http://mnemion.internal/bounded")

        await anyio.to_thread.run_sync(call)

    asyncio.run(run())
    assert sent == [0, 1, 2]


def test_control_and_combined_mcp_reuse_live_permissions_and_keep_sensitive_results_off_tools(env):
    principal = env.identities.create_principal(env.owner, PrincipalInput(name="Unscoped agent"))
    key = env.identities.create_key(env.owner, UUID(principal["id"]), KeyInput(name="Test"))
    with running(create_app(env.db, env.embedder)) as url:
        with Client(url, env.token) as client:
            created = control.execute(
                client, "spaces.create", {"body": {"name": "Agent-created space"}}
            )["result"]
            assert created["name"] == "Agent-created space"
            discovered = client.request(
                "GET", "/v1/agent/operations", params={"query": "spaces.create"}
            )
            assert discovered["total"] == 1
            described = client.request("GET", "/v1/agent/operations/spaces.create")
            assert described["effect"] == "write" and described["input_schema"]
            unknown = client._http.get("/v1/agent/operations/no.such.operation")
            assert (
                unknown.status_code == 422
                and unknown.json()["error"]["code"] == "unknown_operation"
            )
        assert httpx.get(url + "/v1/agent/operations").status_code == 401
        with Client(url, key["api_key"]) as client:
            assert control.execute(client, "spaces.list")["result"]["items"] == []
            with pytest.raises(control.ControlError) as error:
                control.execute(client, "principals.create", {"body": {"name": "Forbidden"}})
            assert error.value.status == 403 and error.value.outcome == "rejected"

        async def run():
            async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + env.token}) as http:
                async with MCPClient(
                    streamable_http_client(url + "/mcp", http_client=http), read_timeout_seconds=15
                ) as client:
                    catalog = await client.call_tool("mnemion_operations", {"query": "librarian"})
                    assert not catalog.is_error and catalog.structured_content["items"]
                    saved = await client.call_tool(
                        "mnemion_write",
                        {
                            "operation": "memories.save",
                            "request": {
                                "parameters": {"space_id": str(env.space)},
                                "body": {"content": "Agent operation evidence"},
                                "idempotency_key": "agent-control-save",
                            },
                        },
                    )
                    assert not saved.is_error, saved
                    memory_id = saved.structured_content["result"]["memory_id"]
                    fetched = await client.call_tool(
                        "mnemion_read",
                        {
                            "operation": "memories.get",
                            "request": {"parameters": {"memory_id": memory_id}},
                        },
                    )
                    assert (
                        fetched.structured_content["result"]["content"]
                        == "Agent operation evidence"
                    )
                    wrong_tool = await client.call_tool(
                        "mnemion_read",
                        {
                            "operation": "spaces.create",
                            "request": {"body": {"name": "No accidental mutation"}},
                        },
                    )
                    assert (
                        wrong_tool.is_error
                        and wrong_tool.structured_content["code"] == "wrong_effect"
                    )
                    private = await client.call_tool(
                        "mnemion_write",
                        {
                            "operation": "keys.create",
                            "request": {
                                "parameters": {"principal_id": principal["id"]},
                                "body": {"name": "Not issued through a transcript"},
                            },
                        },
                    )
                    assert (
                        private.is_error
                        and private.structured_content["code"] == "private_file_required"
                    )
                    assert private.structured_content["retryable"] is False
                    for operation, body in (
                        (
                            "sign_in.create_invitation",
                            {"principal_id": str(env.owner.principal_id)},
                        ),
                        (
                            "sign_in.login",
                            {
                                "workspace_id": str(env.owner.tenant_id),
                                "username": "fixture",
                                "password": "synthetic-private-password",
                                "transport": "native",
                                "device_name": "Blocked tool fixture",
                            },
                        ),
                        ("sign_in.preview_invitation", {"invitation": "mnm_i_" + "x" * 43}),
                    ):
                        blocked = await client.call_tool(
                            "mnemion_read"
                            if operation == "sign_in.preview_invitation"
                            else "mnemion_write",
                            {"operation": operation, "request": {"body": body}},
                        )
                        assert blocked.is_error
                        assert blocked.structured_content["code"] == "private_file_required"
                        assert "synthetic-private-password" not in json.dumps(
                            blocked.structured_content
                        )
                        assert "mnm_i_" not in json.dumps(blocked.structured_content)

            async with httpx2.AsyncClient(
                headers={"Authorization": "Bearer " + key["api_key"]}
            ) as http:
                async with MCPClient(
                    streamable_http_client(url + "/mcp", http_client=http), read_timeout_seconds=15
                ) as client:
                    denied = await client.call_tool(
                        "mnemion_write",
                        {
                            "operation": "principals.create",
                            "request": {"body": {"name": "Forbidden through MCP too"}},
                        },
                    )
                    assert denied.is_error and denied.structured_content["code"] == "forbidden"
                    assert denied.structured_content["outcome"] == "rejected"
                    spaces = await client.call_tool("mnemion_read", {"operation": "spaces.list"})
                    assert spaces.structured_content["result"]["items"] == []

        asyncio.run(run())
        env.identities.revoke_key(env.owner, UUID(key["id"]))
        assert (
            httpx.get(
                url + "/v1/agent/operations", headers={"Authorization": "Bearer " + key["api_key"]}
            ).status_code
            == 401
        )
