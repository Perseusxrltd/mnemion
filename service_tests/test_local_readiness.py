"""Native startup verifies current retrieval without draining an indexing backlog."""

import asyncio
from contextlib import contextmanager
import threading
import time
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import httpx
import pytest

from mnemion import local_state as state, local_workspace
from mnemion.sdk import Client, MnemionError
from mnemion.service.api import create_app
from mnemion.service.errors import ServiceError
from mnemion.service.memory_budget import GIB, MIB, MemoryBudget, MemoryOptions, MemorySample
from mnemion.service.model_registry import ModelRegistry
from mnemion.service.models import MemoryInput


def fixture(env, tmp_path, monkeypatch, *, restarted=True):
    monkeypatch.setenv("MNEMION_EVALUATIONS_DISABLED", "1")
    monkeypatch.setenv("MNEMION_LIBRARIAN_DISABLED", "1")
    root = state.directory(tmp_path / "local-workspace")
    if restarted:
        state.write(root / "readiness.json", {"semantic_index": True, "model_inference": True})
    registry = ModelRegistry(env.embedder)
    budget = MemoryBudget(
        MemoryOptions(mode="manual", limit_mib=1024),
        sample=lambda: MemorySample(8 * GIB, 5 * GIB, 100 * MIB),
    )
    budget.attach(registry)
    credentials = {
        "api_key": env.token,
        "tenant_id": str(env.owner.tenant_id),
        "principal_id": str(env.owner.principal_id),
        "space_id": str(env.space),
    }
    settings = {"workspace_id": str(uuid4()), "port": 17400}
    return root, registry, budget, credentials, settings


@contextmanager
def real_api(env, registry, monkeypatch):
    """Use the real HTTP handlers and database; only the network hop is in process."""
    with TestClient(create_app(database=env.db, registry=registry, mcp_enabled=False)) as api:
        calls = []

        def send(request):
            calls.append((request.method, request.url.path, request.content))
            response = api.request(
                request.method, request.url.path, content=request.content, headers=request.headers
            )
            return httpx.Response(
                response.status_code, headers=response.headers, content=response.content
            )

        monkeypatch.setattr(
            "mnemion.sdk.Client",
            lambda endpoint, key, **options: Client(
                endpoint, key, transport=httpx.MockTransport(send), **options
            ),
        )
        yield calls


def verify(root, registry, credentials, settings):
    local_workspace._verify(root, "http://127.0.0.1:17400", credentials, settings, registry)
    return state.read(root / "readiness.json")


def test_restart_performs_current_semantic_and_keyword_retrieval_without_new_writes(
    env, tmp_path, monkeypatch
):
    root, registry, _, credentials, settings = fixture(env, tmp_path, monkeypatch)
    receipt = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Private workspace assistants use Postgres"),
        "existing",
    )
    while env.memory.operation(env.owner, UUID(receipt["operation_id"]))["state"] != "ready":
        assert env.worker.run_once()
    queries = []
    query = env.embedder.query
    monkeypatch.setattr(env.embedder, "query", lambda text: queries.append(text) or query(text))
    with real_api(env, registry, monkeypatch) as calls:
        result = verify(root, registry, credentials, settings)
    assert result["lexical_search"] and result["model_inference"] and result["semantic_index"]
    assert queries == ["private workspace"]
    assert [path for method, path, _ in calls if method == "POST"] == ["/v1/recall", "/v1/recall"]


def test_empty_restarted_workspace_does_not_invent_index_evidence_or_recreate_welcome(
    env, tmp_path, monkeypatch
):
    root, registry, _, credentials, settings = fixture(env, tmp_path, monkeypatch)
    with real_api(env, registry, monkeypatch) as calls:
        result = verify(root, registry, credentials, settings)
    assert result["model_inference"] and result["lexical_search"]
    assert result["semantic_index"] is False
    assert all("/memories" not in path for _, path, _ in calls)


@pytest.mark.parametrize("reduction", [False, True])
def test_restart_keeps_verified_keyword_access_when_model_is_busy_or_budget_changes(
    env, tmp_path, monkeypatch, reduction
):
    root, registry, budget, credentials, settings = fixture(env, tmp_path, monkeypatch)

    def deferred(_):
        if reduction:
            budget.configure(MemoryOptions(mode="manual", limit_mib=256), "reduced")
        raise ServiceError(
            503, "inference_memory_budget" if reduction else "inference_busy", "Deferred"
        )

    monkeypatch.setattr(env.embedder, "query", deferred)
    with real_api(env, registry, monkeypatch):
        result = verify(root, registry, credentials, settings)
    assert result["lexical_search"]
    assert result["model_inference"] is False and result["semantic_index"] is False


def test_restart_does_not_hide_real_model_failures(env, tmp_path, monkeypatch):
    root, registry, _, credentials, settings = fixture(env, tmp_path, monkeypatch)

    def broken(_):
        raise RuntimeError("Fixture model failure")

    monkeypatch.setattr(env.embedder, "query", broken)
    with real_api(env, registry, monkeypatch):
        with pytest.raises(MnemionError) as failure:
            verify(root, registry, credentials, settings)
        assert failure.value.code == "embedding_unavailable"
        assert "lexical_search" not in state.read(root / "readiness.json")


def test_first_start_with_small_budget_saves_and_searches_before_claiming_readiness(
    env, tmp_path, monkeypatch
):
    root, registry, budget, credentials, settings = fixture(
        env, tmp_path, monkeypatch, restarted=False
    )
    budget.configure(MemoryOptions(mode="manual", limit_mib=256), "small")
    with real_api(env, registry, monkeypatch) as calls:
        result = verify(root, registry, credentials, settings)
    assert result["lexical_search"] and result["model_inference"] is False
    assert sum("/memories" in path for _, path, _ in calls) == 1


def test_first_start_verifies_real_indexed_welcome(env, tmp_path, monkeypatch):
    root, registry, _, credentials, settings = fixture(env, tmp_path, monkeypatch, restarted=False)
    stopped = threading.Event()

    def index():
        while not stopped.is_set():
            if not env.worker.run_once():
                stopped.wait(0.02)

    worker = threading.Thread(target=index, daemon=True)
    worker.start()
    try:
        with real_api(env, registry, monkeypatch):
            result = verify(root, registry, credentials, settings)
        assert result["model_inference"] and result["semantic_index"]
    finally:
        stopped.set()
        worker.join(timeout=5)
        assert not worker.is_alive()


@pytest.mark.parametrize("worker_fails", [False, True])
def test_running_worker_backlog_does_not_hold_workspace_startup(
    env, postgres, tmp_path, monkeypatch, worker_fails
):
    root, registry, _, credentials, settings = fixture(env, tmp_path, monkeypatch)
    settings["port"] = local_workspace.available_port()
    stopped = threading.Event()
    worked = threading.Event()
    ready = []

    def backlog(_):
        worked.set()
        if worker_fails:
            raise RuntimeError("Fixture indexing failure")
        time.sleep(0.01)
        return True  # A busy indexing queue never reports an idle iteration.

    monkeypatch.setattr("mnemion.service.model_worker.ModelWorker.run_once", backlog)

    def emit(value):
        if value["event"] == "ready":
            ready.append(value)
            stopped.set()

    async def scenario():
        task = asyncio.create_task(
            local_workspace._serve(
                root,
                settings,
                credentials,
                SimpleNamespace(dsn=lambda role: postgres[1 if role == "api" else 2]),
                registry,
                None,
                emit,
                stopped,
            )
        )
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5)
        finally:
            stopped.set()
            await asyncio.wait_for(task, timeout=5)

    if worker_fails:
        with pytest.raises(state.LocalSetupError) as failure:
            asyncio.run(scenario())
        assert failure.value.code == "service_start"
        assert not ready and "lexical_search" not in state.read(root / "readiness.json")
    else:
        asyncio.run(scenario())
        assert len(ready) == 1
        assert state.read(root / "readiness.json")["lexical_search"]
    assert worked.is_set()
