"""Busy inference preserves explicit caller choices, scope and retry contracts."""

import asyncio
import json
from uuid import UUID

import httpx
import httpx2
import pytest
from fastapi.testclient import TestClient
from mcp import Client as MCPClient
from mcp.client.streamable_http import streamable_http_client

from mnemion.sdk import Client
from mnemion.service.api import create_app
from mnemion.service.errors import ServiceError
from mnemion.service.inference_limits import InferenceGate
from mnemion.service.insights import InsightsService
from mnemion.service.models import (
    BlockInput,
    ContextInput,
    GrantInput,
    KeyInput,
    MemoryInput,
    PrincipalInput,
    RecallInput,
    SpaceInput,
)
from mnemion.service.retrieval import RetrievalService
from mnemion.service.telemetry import Telemetry
from service_tests.test_clients import running


def occupy_model(env, monkeypatch):
    gate = InferenceGate(max_queued=0, wait_seconds=0)
    original = env.embedder.query
    original_count = env.embedder.token_count

    def query(text):
        with gate.acquire():
            return original(text)

    monkeypatch.setattr(env.embedder, "query", query)

    def token_count(text):
        with gate.acquire():
            return original_count(text)

    monkeypatch.setattr(env.embedder, "token_count", token_count)
    return gate


@pytest.mark.parametrize(
    "endpoint,mode",
    [
        ("recall", "hybrid"),
        ("recall", "semantic"),
        ("context", "hybrid"),
        ("context", "semantic"),
        ("context", "lexical"),
    ],
)
def test_real_admission_busy_is_opt_in_and_scope_preserving(env, monkeypatch, mode, endpoint):
    saved = env.memory.save(env.owner, env.space, MemoryInput(content="billing decision"), "busy")
    other = UUID(env.identities.create_space(env.owner, SpaceInput(name="Other space"))["id"])
    env.memory.save(env.owner, other, MemoryInput(content="billing unrelated space"), "other")
    while env.worker.run_once():
        pass
    gate = occupy_model(env, monkeypatch)
    body = {"query": "billing", "space_ids": [str(env.space)], "mode": mode}
    with TestClient(create_app(env.db, env.embedder)) as client:
        auth = {"Authorization": "Bearer " + env.token}
        with gate.acquire():
            rejected = client.post("/v1/" + endpoint, headers=auth, json=body)
            assert rejected.status_code == 503
            assert rejected.json()["error"]["code"] == "inference_busy"
            assert rejected.headers["Retry-After"] == "1"
            accepted = client.post(
                "/v1/" + endpoint, headers=auth, json={**body, "on_inference_busy": "lexical"}
            )
            assert accepted.status_code == 200, accepted.text
            result = accepted.json()
            assert result["warnings"] == ["inference_busy_lexical_only"]
            rows = result["hits"] if endpoint == "recall" else result["citations"]
            assert {row["memory_id"] for row in rows} == {saved["memory_id"]}
            assert {row["space_id"] for row in rows} == {str(env.space)}
            if endpoint == "recall":
                assert result["hits"][0]["ranking"]["ranks"] == {"lexical": 1}
                assert result["hits"][0]["ranking"]["cosine_similarity"] is None
                assert result["hits"][0]["relevance_score"] == 1
            else:
                assert result["token_count"] <= result["token_budget"]
                assert result["token_count_unit"] == "utf8_bytes"
                assert result["token_count"] == len(result["text"].encode("utf-8"))
            assert gate.snapshot()["completed"] == 0
        recovered = client.post(
            "/v1/" + endpoint, headers=auth, json={**body, "on_inference_busy": "lexical"}
        )
        assert recovered.status_code == 200
        assert "inference_busy_lexical_only" not in recovered.json()["warnings"]
        assert gate.snapshot()["completed"] >= 2  # Held slot, then admitted model work.


@pytest.mark.parametrize("successful_counts", [0, 1, 3])
def test_context_rebuilds_with_one_counting_unit_if_tokenizer_becomes_busy(
    env, monkeypatch, successful_counts
):
    env.memory.put_block(
        env.owner, env.space, "scope", BlockInput(content="Billing context", expected_version=0)
    )
    for number in range(3):
        env.memory.save(
            env.owner,
            env.space,
            MemoryInput(content=f"billing café {number}"),
            f"late-busy-{number}",
        )
    calls = 0

    def token_count(text):
        nonlocal calls
        calls += 1
        if calls > successful_counts:
            raise InferenceGate.busy()
        return len(text.split())

    monkeypatch.setattr(env.embedder, "token_count", token_count)
    result = RetrievalService(env.db, env.embedder).context(
        env.owner,
        ContextInput(
            query="billing", space_ids=[env.space], on_inference_busy="lexical", token_budget=1024
        ),
    )
    assert calls == successful_counts + 1  # Byte fallback makes no more model calls.
    assert "inference_busy_lexical_only" in result["warnings"]
    assert result["token_count_unit"] == "utf8_bytes"
    assert result["token_count"] == len(result["text"].encode("utf-8")) <= 1024
    assert result["citations"] and result["core_blocks"]


@pytest.mark.parametrize(
    "status,code", [(403, "forbidden"), (409, "generation_changed"), (503, "other_failure")]
)
def test_busy_fallback_does_not_mask_other_service_errors(env, monkeypatch, status, code):
    failure = ServiceError(status, code, "Expected service failure")

    def fail(_):
        raise failure

    monkeypatch.setattr(env.embedder, "query", fail)
    with pytest.raises(ServiceError) as caught:
        RetrievalService(env.db, env.embedder).recall(
            env.owner,
            RecallInput(query="billing", space_ids=[env.space], on_inference_busy="lexical"),
        )
    assert caught.value is failure


@pytest.mark.parametrize("revocation", ["grant", "key"])
def test_busy_fallback_rechecks_access_after_inference_wait(env, monkeypatch, revocation):
    env.memory.save(env.owner, env.space, MemoryInput(content="billing private evidence"), "race")
    person = env.identities.create_principal(env.owner, PrincipalInput(name="Reader"))
    principal = UUID(person["id"])
    key = env.identities.create_key(env.owner, principal, KeyInput(name="Reader key"))
    env.identities.grant(env.owner, env.space, principal, GrantInput(role="reader"))
    identity = env.db.authenticate(key["api_key"])

    def busy(_):
        if revocation == "grant":
            env.identities.revoke_grant(env.owner, env.space, principal)
        else:
            env.identities.revoke_key(env.owner, identity.key_id)
        raise InferenceGate.busy()

    monkeypatch.setattr(env.embedder, "query", busy)
    with pytest.raises(ServiceError) as caught:
        RetrievalService(env.db, env.embedder).recall(
            identity,
            RecallInput(query="billing", space_ids=[env.space], on_inference_busy="lexical"),
        )
    assert caught.value.status in (401, 403, 404)


def test_lexical_mode_does_not_request_inference_and_fallback_is_counted(env, monkeypatch):
    env.memory.save(env.owner, env.space, MemoryInput(content="billing decision"), "telemetry")
    gate = occupy_model(env, monkeypatch)
    telemetry = Telemetry(env.db)
    service = RetrievalService(env.db, env.embedder, telemetry)
    with gate.acquire():
        lexical = service.recall(
            env.owner,
            RecallInput(
                query="billing", space_ids=[env.space], mode="lexical", on_inference_busy="lexical"
            ),
        )
        assert "inference_busy_lexical_only" not in lexical["warnings"]
        fallback = service.recall(
            env.owner,
            RecallInput(query="billing", space_ids=[env.space], on_inference_busy="lexical"),
        )
        assert "inference_busy_lexical_only" in fallback["warnings"]
        assert gate.snapshot()["rejected"] == 1
    telemetry.flush()
    report = InsightsService(env.db, env.embedder).read(env.owner, env.space)
    assert sum(group["fallbacks"] for group in report["metrics"]["groups"]) == 1


@pytest.mark.parametrize("operation", ["search", "context"])
def test_python_sdk_keeps_default_requests_compatible_with_older_strict_servers(operation):
    bodies = []
    index = {
        "generation_id": None,
        "eligible_records": 0,
        "indexed_records": 0,
        "pending_records": 0,
        "observed_at": "2026-10-12T00:00:00Z",
    }

    def handle(request):
        bodies.append(json.loads(request.content))
        if operation == "search":
            result = {
                "request_id": "fixture",
                "query": "billing",
                "hits": [],
                "warnings": [],
                "index": index,
                "timing_ms": 1,
                "score_description": "fixture",
            }
        else:
            result = {
                "request_id": "fixture",
                "text": "",
                "citations": [],
                "core_blocks": [],
                "token_count": 0,
                "token_budget": 2048,
                "tokenizer": "fixture",
                "tokenizer_generation": "fixture",
                "omitted_items": 0,
                "warnings": [],
                "index": index,
            }
        return httpx.Response(200, json=result)

    with Client(
        "https://example.invalid", "fixture", transport=httpx.MockTransport(handle)
    ) as client:
        invoke = getattr(client, operation)
        invoke("billing", all_accessible=True)
        invoke("billing", all_accessible=True, on_inference_busy="error")
        invoke("billing", all_accessible=True, on_inference_busy="lexical")
    assert "on_inference_busy" not in bodies[0] and "on_inference_busy" not in bodies[1]
    assert bodies[2]["on_inference_busy"] == "lexical"


def test_mcp_busy_hint_and_explicit_fallback_use_the_same_live_gate(env, monkeypatch):
    saved = env.memory.save(
        env.owner, env.space, MemoryInput(content="billing MCP evidence"), "mcp-busy"
    )
    gate = occupy_model(env, monkeypatch)
    with running(create_app(env.db, env.embedder)) as url:

        async def exercise():
            async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + env.token}) as http:
                async with MCPClient(
                    streamable_http_client(url + "/mcp", http_client=http), read_timeout_seconds=15
                ) as client:
                    tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                    for name in ("memory_search", "memory_context"):
                        policy = tools[name].input_schema["properties"]["on_inference_busy"]
                        assert policy["default"] == "error" and policy["enum"] == [
                            "error",
                            "lexical",
                        ]
                    query = {"query": "billing", "space_ids": [str(env.space)]}
                    rejected = await client.call_tool("memory_search", query)
                    assert (
                        rejected.is_error
                        and rejected.structured_content["code"] == "inference_busy"
                    )
                    assert rejected.structured_content["retryable"] is True
                    assert rejected.structured_content["retry_after_seconds"] == 1
                    for name, key in (("memory_search", "hits"), ("memory_context", "citations")):
                        result = await client.call_tool(
                            name, {**query, "on_inference_busy": "lexical"}
                        )
                        assert not result.is_error, result
                        assert (
                            "inference_busy_lexical_only" in result.structured_content["warnings"]
                        )
                        assert {row["memory_id"] for row in result.structured_content[key]} == {
                            saved["memory_id"]
                        }

        with gate.acquire():
            asyncio.run(exercise())
