"""Admission limits prevent concurrent model allocations and survive failures."""

from concurrent.futures import ThreadPoolExecutor
import threading
import time
from types import SimpleNamespace

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


def wait_for_queued(gate, count):
    deadline = time.monotonic() + 2
    while gate.snapshot()["queued"] != count:
        assert time.monotonic() < deadline, gate.snapshot()
        time.sleep(0.001)


def test_checkpoint_runs_a_queued_query_between_document_batches():
    gate = InferenceGate(max_queued=1)
    order = []

    def query():
        with gate.acquire():
            assert gate.snapshot()["active"] == 1
            order.append("query")

    with ThreadPoolExecutor(max_workers=1) as pool:
        with gate.acquire():
            order.append("batch one")
            pending = pool.submit(query)
            wait_for_queued(gate, 1)
            with pytest.raises(ServiceError, match="busy"), gate.acquire():
                pytest.fail("The document and query already hold both admission tokens")
            assert gate.checkpoint() is True
            order.append("batch two")
            assert gate.checkpoint() is False
        pending.result(timeout=2)
    assert order == ["batch one", "query", "batch two"]
    stats = gate.snapshot()
    assert stats["active"] == stats["queued"] == 0
    assert stats["completed"] == 2 and stats["failed"] == 0
    assert stats["rejected"] == 1


def test_checkpoint_joins_fifo_tail_and_new_arrivals_cannot_barge():
    gate = InferenceGate(max_queued=3)
    document_entered, yield_now, first_entered, release_first = (
        threading.Event() for _ in range(4)
    )
    order = []

    def document():
        with gate.acquire():
            order.append("document first")
            document_entered.set()
            assert yield_now.wait(3)
            assert gate.checkpoint()
            order.append("document resumed")

    def request(name):
        with gate.acquire():
            order.append(name)
            if name == "first":
                first_entered.set()
                assert release_first.wait(3)

    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = [pool.submit(document)]
        try:
            assert document_entered.wait(2)
            pending.append(pool.submit(request, "first"))
            wait_for_queued(gate, 1)
            pending.append(pool.submit(request, "second"))
            wait_for_queued(gate, 2)
            yield_now.set()
            assert first_entered.wait(2)
            pending.append(pool.submit(request, "late"))
            wait_for_queued(gate, 3)
            with gate.maintenance() as acquired:
                assert not acquired
        finally:
            yield_now.set()
            release_first.set()
        for future in pending:
            future.result(timeout=3)
    assert order == ["document first", "first", "second", "document resumed", "late"]
    assert gate.snapshot()["completed"] == 4


def test_cooperative_wait_allows_foreground_longer_than_initial_admission():
    gate = InferenceGate(wait_seconds=0.1)

    def foreground():
        with gate.acquire():
            time.sleep(0.2)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with gate.acquire(cooperative_wait_seconds=1):
            pending = pool.submit(foreground)
            wait_for_queued(gate, 1)
            assert gate.checkpoint()
            assert gate.snapshot()["active"] == 1
        pending.result(timeout=2)
    stats = gate.snapshot()
    assert stats["completed"] == 2 and stats["rejected"] == 0
    # Waiting for the foreground operation must not count as a second interval
    # of document execution in the process-wide sum.
    assert 180 <= stats["execution_ms"] < stats["wait_ms"] + 150


def test_cooperative_timeout_is_cumulative_and_never_releases_the_foreground():
    gate = InferenceGate(max_queued=1, wait_seconds=0.1)
    second_entered, release_second = threading.Event(), threading.Event()

    def foreground(first):
        with gate.acquire():
            if first:
                time.sleep(0.35)
            else:
                second_entered.set()
                assert release_second.wait(3)

    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            with pytest.raises(ServiceError, match="busy"):
                with gate.acquire(cooperative_wait_seconds=0.5):
                    first = pool.submit(foreground, True)
                    wait_for_queued(gate, 1)
                    assert gate.checkpoint()
                    first.result(timeout=2)
                    second = pool.submit(foreground, False)
                    wait_for_queued(gate, 1)
                    started = time.monotonic()
                    gate.checkpoint()
            elapsed = time.monotonic() - started
            # Only the remainder of the original allowance is available. A
            # reset-to-0.5 implementation would time out much later here.
            assert elapsed < 0.35
            assert second_entered.is_set()
            assert gate.snapshot()["active"] == 1
            with gate.maintenance() as acquired:
                assert not acquired
            with pytest.raises(ServiceError, match="busy"), gate.acquire():
                pytest.fail("Timed-out document released the foreground's execution")
            assert gate.snapshot()["active"] == 1
        finally:
            release_second.set()
        second.result(timeout=2)
    # The failed document returned its sole token and removed its queued turn.
    with gate.acquire():
        assert gate.checkpoint() is False
    stats = gate.snapshot()
    assert stats["active"] == stats["queued"] == 0
    assert stats["completed"] == 3 and stats["failed"] == 1
    assert stats["rejected"] == 2


def test_catching_a_checkpoint_timeout_cannot_report_success():
    gate = InferenceGate(max_queued=1, wait_seconds=0.1)
    release = threading.Event()

    def foreground():
        with gate.acquire():
            assert release.wait(3)

    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            with pytest.raises(ServiceError, match="busy"):
                with gate.acquire(cooperative_wait_seconds=0.01):
                    pending = pool.submit(foreground)
                    wait_for_queued(gate, 1)
                    with pytest.raises(ServiceError, match="busy"):
                        gate.checkpoint()
            assert gate.snapshot()["active"] == 1
        finally:
            release.set()
        pending.result(timeout=2)
    assert gate.snapshot()["failed"] == 1
    assert gate.snapshot()["completed"] == 1


def test_expired_checkpoint_cannot_resume_when_capacity_becomes_free(monkeypatch):
    from mnemion.service import inference_limits

    clock = [0.0]
    # Only the gate's observation clock changes. Thread waits and the test's
    # synchronization remain real, so the final wake-up is deterministic.
    monkeypatch.setattr(inference_limits, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    gate = InferenceGate()

    def foreground():
        with gate.acquire():
            clock[0] = 1.0

    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(ServiceError, match="busy"):
            with gate.acquire(cooperative_wait_seconds=0.5):
                pending = pool.submit(foreground)
                wait_for_queued(gate, 1)
                gate.checkpoint()
        pending.result(timeout=2)
    with gate.acquire():
        pass
    assert gate.snapshot()["failed"] == 1
    assert gate.snapshot()["completed"] == 2
    assert gate.snapshot()["active"] == gate.snapshot()["queued"] == 0


def test_checkpoint_requires_the_current_execution_owner():
    gate = InferenceGate(wait_seconds=0.005)
    with pytest.raises(RuntimeError, match="executing inference"):
        gate.checkpoint()
    with gate.maintenance() as acquired:
        assert acquired
        with pytest.raises(RuntimeError, match="executing inference"):
            gate.checkpoint()
        with pytest.raises(ServiceError, match="busy"), gate.acquire():
            pytest.fail("Maintenance and inference ran simultaneously")
    with ThreadPoolExecutor(max_workers=1) as pool:
        with gate.acquire():
            invalid = pool.submit(gate.checkpoint)
            with pytest.raises(RuntimeError, match="executing inference"):
                invalid.result(timeout=2)
            assert gate.checkpoint() is False
    with gate.maintenance() as acquired:
        assert acquired


@pytest.mark.parametrize("value", [True, -1, 121, float("nan"), float("inf"), "1"])
def test_cooperative_wait_configuration_is_bounded_without_consuming_capacity(value):
    gate = InferenceGate(max_queued=0)
    with pytest.raises(ValueError), gate.acquire(cooperative_wait_seconds=value):
        pytest.fail("Invalid cooperative allowance was accepted")
    with gate.acquire():
        assert gate.checkpoint() is False
    assert gate.snapshot()["completed"] == 1
