"""Release unused sessions without preempting requests or loading another model."""

from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest

from mnemion.service.embeddings import LocalEmbedder
from mnemion.service.model_catalog import BGE_SMALL_GENERATION
from mnemion.service.model_registry import ModelRegistry


def registry(tmp_path, *, idle_seconds=30):
    model = LocalEmbedder(tmp_path, offline=True)
    model._model = object()
    model._tokenizer = object()
    return ModelRegistry(model, idle_seconds=idle_seconds)


def test_idle_cleanup_waits_for_the_last_completed_inference(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("mnemion.service.inference_limits.time.monotonic", lambda: clock[0])
    models = registry(tmp_path)
    original = models.default._model
    clock[0] = 29
    assert models.release_idle() == 0
    with models.inference_gate.acquire():
        clock[0] = 100
        assert models.release_idle() == 0
        assert models.default._model is original
    clock[0] = 129
    assert models.release_idle() == 0
    clock[0] = 130
    assert models.release_idle() == 1
    assert models.default._model is None and models.default._tokenizer is None
    assert models.release_idle() == 0
    assert models.cache_status()["idle_model_evictions"] == 1
    assert not list(tmp_path.iterdir()), "Cleanup must neither load nor remove model files"


def test_failed_inference_also_resets_idle_age(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("mnemion.service.inference_limits.time.monotonic", lambda: clock[0])
    models = registry(tmp_path)
    clock[0] = 40
    with pytest.raises(ValueError), models.inference_gate.acquire():
        raise ValueError("synthetic invalid query")
    assert models.release_idle() == 0
    clock[0] = 70
    assert models.release_idle() == 1
    assert models.inference_gate.snapshot()["failed"] == 1


def test_pending_native_work_is_never_unloaded_by_maintenance(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("mnemion.service.inference_limits.time.monotonic", lambda: clock[0])
    models = registry(tmp_path)
    entered, finish = threading.Event(), threading.Event()
    original = models.default._model

    def inference():
        with models.inference_gate.acquire():
            entered.set()
            assert finish.wait(2)
            assert models.default._model is original

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(inference)
        assert entered.wait(2)
        try:
            clock[0] = 300
            assert models.release_idle() == 0
        finally:
            finish.set()
        pending.result(timeout=2)
    assert models.release_idle() == 0
    clock[0] = 330
    assert models.release_idle() == 1


def test_background_cleanup_is_single_and_stops_when_registry_closes(tmp_path, monkeypatch):
    models = registry(tmp_path)
    # Advance only the admission clock; keep real thread waits and scheduling.
    models.inference_gate._last_used -= 60
    monkeypatch.setattr(models, "_idle_interval", lambda: 0.005)
    models.start_idle_cleanup()
    first = models._idle_thread
    models.start_idle_cleanup()
    assert models._idle_thread is first
    try:
        end = time.monotonic() + 2
        while models.cache_status()["idle_model_evictions"] == 0 and time.monotonic() < end:
            time.sleep(0.005)
        assert models.cache_status()["idle_model_evictions"] == 1
        assert models.default._model is None
    finally:
        models.close()
    assert not first.is_alive()


def test_opt_out_preserves_a_warm_cache_and_creates_no_monitor(tmp_path):
    models = registry(tmp_path, idle_seconds=0)
    models.inference_gate._last_used -= 86400
    models.start_idle_cleanup()
    assert models.release_idle() == 0
    assert models.default._model is not None
    assert models._idle_thread is None
    assert models.cache_status()["idle_cleanup_enabled"] is False
    models.close()


def test_monitor_retries_failed_cleanup_without_exposing_native_error(tmp_path, monkeypatch):
    models = registry(tmp_path)
    models.inference_gate._last_used -= 60
    unload = models.default._unload
    calls = [0]

    def once_failed():
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError("synthetic-private-native-detail")
        unload()

    monkeypatch.setattr(models.default, "_unload", once_failed)
    monkeypatch.setattr(models, "_idle_interval", lambda: 0.005)
    models.start_idle_cleanup()
    try:
        end = time.monotonic() + 2
        while models.cache_status()["idle_model_evictions"] == 0 and time.monotonic() < end:
            time.sleep(0.005)
        assert models.cache_status()["idle_model_evictions"] == 1
        assert models.cache_status()["cleanup_failures"] == 1
        assert "private" not in str(models.cache_status())
    finally:
        models.close()


def test_partial_cleanup_preserves_successful_release_counts(tmp_path, monkeypatch):
    first = LocalEmbedder(tmp_path, offline=True)
    second = LocalEmbedder(tmp_path, offline=True, generation=BGE_SMALL_GENERATION)
    first._model = object()
    second._model = object()
    models = ModelRegistry(first, {"e5-small": first, "bge-small": second}, idle_seconds=30)
    models.inference_gate._last_used -= 60
    unload = second._unload

    def fail():
        raise RuntimeError("synthetic cleanup failure")

    monkeypatch.setattr(second, "_unload", fail)
    with pytest.raises(RuntimeError):
        models.release_idle()
    assert first._model is None and second._model is not None
    assert models.cache_status()["idle_model_evictions"] == 1
    monkeypatch.setattr(second, "_unload", unload)
    assert models.release_idle() == 1
    assert models.cache_status()["idle_model_evictions"] == 2
    models.close()


@pytest.mark.parametrize("value", [-1, 1, 9, 86401, True, None, 30.5])
def test_invalid_idle_policy_fails_before_a_monitor_starts(tmp_path, value):
    with pytest.raises(ValueError, match="idle cleanup"):
        registry(tmp_path, idle_seconds=value)


@pytest.mark.parametrize("value", ["-1", "1.0", " 30", "secret", "999999", "٣٠"])
def test_malformed_operator_setting_is_not_echoed(monkeypatch, value):
    monkeypatch.setenv("MNEMION_MODEL_IDLE_SECONDS", value)
    with pytest.raises(ValueError) as error:
        ModelRegistry.from_environment()
    assert str(error.value) == "Model idle cleanup must be disabled with 0 or use 10–86400 seconds"
