"""Admission limits prevent concurrent model allocations and survive failures."""

from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest

from mnemion.service.embeddings import LocalEmbedder
from mnemion.service.errors import ServiceError
from mnemion.service.inference_limits import InferenceGate


def test_saturation_rejects_before_entering_model_and_recovers(tmp_path):
    model = LocalEmbedder(tmp_path, max_queued=0)
    entered, release = threading.Event(), threading.Event()

    def inference(text):
        entered.set()
        assert release.wait(2)
        return [1.0]

    model._query = inference
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(model.query, "first")
        try:
            assert entered.wait(1)
            with pytest.raises(ServiceError) as caught:
                model.document("second")
            assert (caught.value.status, caught.value.code) == (503, "inference_busy")
            assert model._inference_gate.snapshot()["active"] == 1
        finally:
            release.set()
        assert future.result(timeout=2) == [1.0]
    assert model.query("after release") == [1.0]
    stats = model._inference_gate.snapshot()
    assert stats["active"] == stats["queued"] == 0
    assert stats["completed"] == 2 and stats["rejected"] == 1


def test_timed_out_waiter_does_not_leak_capacity_or_release_running_model():
    gate = InferenceGate(max_queued=1, wait_seconds=0.005)
    with gate.acquire():
        for _ in range(3):
            with pytest.raises(ServiceError, match="busy"):
                with gate.acquire():
                    pytest.fail("Concurrent inference was admitted")
        assert gate.snapshot()["active"] == 1
    with pytest.raises(RuntimeError, match="inference failed"):
        with gate.acquire():
            raise RuntimeError("inference failed")
    with gate.acquire():
        pass
    stats = gate.snapshot()
    assert stats["failed"] == 1 and stats["rejected"] == 3 and stats["completed"] == 2
    assert stats["active"] == stats["queued"] == 0


def test_ten_caller_burst_queues_without_parallel_model_allocations():
    gate = InferenceGate()
    ready = threading.Barrier(10)
    active = maximum = 0
    lock = threading.Lock()

    def request():
        nonlocal active, maximum
        ready.wait(timeout=5)
        with gate.acquire():
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.04)
            with lock:
                active -= 1

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(lambda _: request(), range(10)))
    assert maximum == 1
    assert gate.snapshot()["completed"] == 10
    assert gate.snapshot()["rejected"] == 0


def test_operator_queue_configuration_is_bounded(monkeypatch):
    monkeypatch.setenv("MNEMION_MODEL_MAX_QUEUED", "12")
    monkeypatch.setenv("MNEMION_MODEL_WAIT_SECONDS", "3.5")
    gate = InferenceGate.from_environment()
    assert (gate.max_queued, gate.wait_seconds) == (12, 3.5)
    monkeypatch.setenv("MNEMION_MODEL_MAX_QUEUED", "100000")
    with pytest.raises(ValueError):
        InferenceGate.from_environment()


@pytest.mark.parametrize("value", [True, -1, 65, 1.5, "4"])
def test_invalid_queue_limits_fail_at_configuration(value):
    with pytest.raises(ValueError):
        InferenceGate(max_queued=value)


@pytest.mark.parametrize("value", [True, -1, 6, float("nan"), float("inf"), "1"])
def test_invalid_wait_limits_fail_at_configuration(value):
    with pytest.raises(ValueError):
        InferenceGate(wait_seconds=value)
