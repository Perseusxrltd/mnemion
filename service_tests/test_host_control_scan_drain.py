"""Real scan leases can outlast a minute without losing an operator's intent."""

from contextlib import contextmanager
import os
from types import SimpleNamespace

import pytest

from mnemion.host_control import adapter, installation, worker
from mnemion.host_control.store import Store
from mnemion.service import supervision, update_state as state_io
from service_tests.test_host_control_installation import prepared_host as prepared_host
from service_tests.test_host_control_store import adopted as adopted, request

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Unix managed source leases")


@contextmanager
def source_scan(monkeypatch, root, *, finish_after=None):
    # Keep real OS file locks; advance only the coordination clock so CI need
    # not spend five wall-clock minutes on the live failure's timing boundary.
    reader = state_io.lock(root, shared=True)
    reader.__enter__()
    clock = {"elapsed": 0.0, "finished": False}

    def sleep(seconds):
        assert state_io.connector_update_waiting(root)
        clock["elapsed"] += seconds
        if finish_after is not None and clock["elapsed"] >= finish_after and not clock["finished"]:
            reader.__exit__(None, None, None)
            clock["finished"] = True

    monkeypatch.setattr(
        state_io, "time", SimpleNamespace(monotonic=lambda: clock["elapsed"], sleep=sleep)
    )
    try:
        yield clock
    finally:
        if not clock["finished"]:
            reader.__exit__(None, None, None)


def test_stop_waits_for_a_long_scan_then_checks_authority_and_runs_once(
    adopted, tmp_path, monkeypatch
):
    store, identity = adopted
    service = tmp_path / "managed-service"
    spec = request(identity, "service.stop", approve_service_interruption=True)
    store.enqueue(identity["operator_id"], spec)
    job = store.claim()
    effects = []

    with source_scan(monkeypatch, service / "updates", finish_after=75) as scan:

        def stop(_):
            assert scan["finished"]
            effects.append(scan["elapsed"])
            return {"stopped": True}

        monkeypatch.setattr(supervision, "stop", stop)
        result, context = adapter.execute(
            store.root,
            {"service_state": str(service)},
            store,
            job,
            spec,
            before_effect=lambda: store.guard(spec.request_id, record_effect=True),
        )
        store.finish(spec.request_id, result=result, context=context)

    observed = store.operation(identity["operator_id"], identity["host_id"], spec.request_id)
    assert observed["phase"] == "succeeded" and observed["effect_started_at"] is not None
    assert effects == [75.0]
    assert not (service / "updates/connector-update-pending.json").exists()


def test_worker_records_busy_without_starting_an_effect_or_ending_the_scan(
    prepared_host, monkeypatch
):
    service, root, operator, _, port = prepared_host
    identity = installation.adopt(root, service, operator, port=port)["connection"]
    store = Store(root / "authority")
    original_policy = store.service_policy()
    spec = request(identity, "service.stop", approve_service_interruption=True)
    store.enqueue(identity["operator_id"], spec)
    monkeypatch.setattr(
        supervision, "stop", lambda _: pytest.fail("The source still owns its lease")
    )

    with source_scan(monkeypatch, service / "updates") as scan:
        with state_io.lock(root / "worker") as descriptor:
            # The real worker owns its inherited descriptor in another process.
            assert worker.work(root, os.dup(descriptor)) == 0
        assert scan == {"elapsed": 300.0, "finished": False}
        with pytest.raises(state_io.OperationBusy), state_io.lock(service / "updates"):
            pytest.fail("The original reader must retain its runtime")

    observed = store.operation(identity["operator_id"], identity["host_id"], spec.request_id)
    assert observed["phase"] == "failed" and observed["error"] == "host_busy"
    assert observed["effect_started_at"] is None
    policy = store.service_policy()
    assert policy["desired"] == original_policy["desired"]
    assert policy["operation_id"] == original_policy["operation_id"]
    assert not policy["pending_work"]
    assert not (service / "updates/connector-update-pending.json").exists()
