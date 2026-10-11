"""Budget changes must not race inference, lose writes, or block deletion."""

from concurrent.futures import ThreadPoolExecutor
import threading
from uuid import UUID

import pytest

from mnemion.service.embeddings import LocalEmbedder
from mnemion.service.errors import ServiceError
from mnemion.service.memory_budget import (
    GIB,
    MIB,
    MemoryBudget,
    MemoryOptions,
    MemorySample,
    working_target,
)
from mnemion.service.model_registry import ModelRegistry
from mnemion.service.models import MemoryInput, RecallInput
from mnemion.service.retrieval import RetrievalService


@pytest.mark.parametrize("total", [2, 4, 8, 16, 64])
def test_automatic_budget_leaves_headroom_and_does_not_shrink_as_own_model_loads(total):
    before = MemorySample(total * GIB, (total - 1) * GIB, 100 * MIB)
    after = MemorySample(total * GIB, (total - 1) * GIB - 512 * MIB, 612 * MIB)
    target, reserve = working_target(MemoryOptions(), before)
    assert target == working_target(MemoryOptions(), after)[0]
    assert target <= total * GIB // 4 and target <= 4 * GIB
    assert target + reserve <= total * GIB
    requested, _ = working_target(MemoryOptions(mode="manual", limit_mib=256), before)
    assert requested == 256 * MIB


def test_lowering_budget_never_unloads_an_active_native_call(tmp_path):
    model = LocalEmbedder(tmp_path)
    registry = ModelRegistry(model)
    budget = MemoryBudget(
        MemoryOptions(mode="manual", limit_mib=2048),
        sample=lambda: MemorySample(8 * GIB, 5 * GIB, 600 * MIB),
    )
    budget.attach(registry)
    model._model = object()
    active, finish = threading.Event(), threading.Event()

    def query(_):
        budget.admit(model)
        active.set()
        assert finish.wait(5)
        assert model._model is not None
        return [1.0]

    model._query = query
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(model.query, "running")
        try:
            assert active.wait(2)
            budget.configure(MemoryOptions(mode="manual", limit_mib=256), "changed")
            assert not budget.trim()
            assert model._model is not None
        finally:
            finish.set()
        assert future.result(timeout=5) == [1.0]
    assert budget.trim()
    assert model._model is None
    with pytest.raises(ServiceError) as caught:
        model.prepare()
    assert caught.value.code == "inference_memory_budget"
    assert budget.snapshot()["model_evictions"] == 1
    budget.configure(MemoryOptions(mode="manual", limit_mib=2048), "restored")
    assert budget.can_schedule(model)


def test_system_pressure_and_missing_measurements_pause_even_a_large_manual_budget():
    sample = MemorySample(4 * GIB, 64 * MIB, 600 * MIB)
    budget = MemoryBudget(MemoryOptions(mode="manual", limit_mib=1048576), sample=lambda: sample)
    view = budget.snapshot()
    assert view["background_paused"] and view["reason"] == "system_pressure"
    assert view["target_bytes"] < 4 * GIB
    budget.policy_unavailable()
    assert budget.snapshot()["reason"] == "policy_unavailable"
    assert budget.snapshot()["requested_limit_mib"] == 1048576


def test_paused_indexing_still_claims_purges_without_spending_retries(env):
    class Paused:
        def can_schedule(self, model):
            return False

    env.embedder._memory_budget = Paused()
    saved = env.memory.save(
        env.owner, env.space, MemoryInput(content="RAM budget durable evidence"), "budget-save"
    )
    for _ in range(7):
        # The session database may also contain purges from another tenant.
        # Those must still run while this memory's index job remains pending.
        env.worker.run_once()
    with env.db.transaction(env.owner) as conn:
        row = conn.execute(
            "SELECT state,attempts FROM mnemion.jobs WHERE operation_id=%s",
            (saved["operation_id"],),
        ).fetchone()
        assert row == {"state": "pending", "attempts": 0}
    removed = env.memory.forget(
        env.owner, UUID(saved["memory_id"]), expected_version=1, key="budget-delete"
    )
    for _ in range(1000):
        assert env.worker.run_once()
        with env.db.transaction(env.owner) as conn:
            state = conn.execute(
                "SELECT state FROM mnemion.operations WHERE id=%s", (removed["operation_id"],)
            ).fetchone()["state"]
        if state == "ready":
            break
    else:
        pytest.fail("The deletion did not finish while indexing was paused")


def test_mid_job_budget_change_defers_whole_job_and_hybrid_retrieval_is_explicit(env):
    saved = env.memory.save(
        env.owner, env.space, MemoryInput(content="Postgres RAM budget evidence"), "budget-race"
    )

    def paused(_):
        raise ServiceError(503, "inference_memory_budget", "Paused by host RAM budget")

    env.embedder.document = paused
    env.embedder.query = paused
    for _ in range(1000):
        assert env.worker.run_once()
        with env.db.transaction(env.owner) as conn:
            row = conn.execute(
                "SELECT state,attempts,error_code FROM mnemion.jobs WHERE operation_id=%s",
                (saved["operation_id"],),
            ).fetchone()
        if row["error_code"] == "inference_memory_budget":
            break
    else:
        pytest.fail("The target memory did not reach the model worker")
    assert row == {"state": "pending", "attempts": 0, "error_code": "inference_memory_budget"}
    retrieval = RetrievalService(env.db, env.embedder)
    result = retrieval.recall(env.owner, RecallInput(query="Postgres RAM", space_ids=[env.space]))
    assert result["hits"][0]["memory_id"] == saved["memory_id"]
    assert "semantic_unavailable_lexical_only" in result["warnings"]
    with pytest.raises(ServiceError) as caught:
        retrieval.recall(
            env.owner, RecallInput(query="Postgres", space_ids=[env.space], mode="semantic")
        )
    assert caught.value.code == "embedding_unavailable"
