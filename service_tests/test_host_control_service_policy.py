"""An external restart manager must not undo an administrator's durable stop."""

from datetime import datetime, timedelta, timezone
import os
import signal
import subprocess
import sys

import pytest

from mnemion.host_control import HostControlError, installation, memory_lifecycle
from mnemion.host_control.store import Store
from mnemion.service import supervision, update_state as state_io
from service_tests.test_host_control_installation import prepared_host as prepared_host
from service_tests.test_host_control_store import adopted as adopted, grant, operator, request
from service_tests.test_supervision import wait_until

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Unix adopted-host supervision")


def effect(store, identity, action):
    spec = request(identity, action, approve_service_interruption=True)
    store.enqueue(identity["operator_id"], spec)
    assert store.claim()["operation_id"] == str(spec.request_id)
    store.guard(spec.request_id, record_effect=True)
    return spec


def test_only_current_authorized_effect_changes_the_service_decision(adopted):
    store, identity = adopted
    delegated = grant(adopted, operator("Temporary operator", "operator"))
    spec = request(identity, "service.stop", approve_service_interruption=True)
    store.enqueue(delegated, spec)
    assert store.service_policy()["desired"] == "running"
    assert not store.service_policy()["automatic_start_allowed"]
    store.claim()
    revision = store.authority(identity["operator_id"], identity["host_id"])["revision"]
    store.revoke(
        identity["operator_id"],
        request(
            identity,
            "operators.revoke",
            expected_revision=revision,
            operator_id=delegated,
        ),
    )
    with pytest.raises(HostControlError, match="authority"):
        store.guard(spec.request_id, record_effect=True)
    assert store.service_policy()["desired"] == "running"


def test_stop_survives_history_pruning_and_a_new_reader(adopted):
    store, identity = adopted
    stop = effect(store, identity, "service.stop")
    store.finish(stop.request_id, result={"stopped": True})
    with store.transaction() as conn:
        conn.execute(
            "UPDATE operations SET valid_until=?",
            ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),),
        )
        Store._space(conn, 1)
        assert conn.execute("SELECT count(*) FROM operations").fetchone()[0] == 0
    policy = Store(store.root).service_policy()
    assert policy["desired"] == "stopped" and not policy["automatic_start_allowed"]
    assert policy["operation_id"] == str(stop.request_id)
    start = effect(store, identity, "service.start")
    assert not store.service_policy()["automatic_start_allowed"]
    store.finish(start.request_id, result={"running": True})
    assert Store(store.root).service_policy()["automatic_start_allowed"]


def test_uncertain_start_blocks_automatic_repair_until_observed_resolution(adopted):
    store, identity = adopted
    start = effect(store, identity, "service.start")
    store.interrupted()
    assert store.service_policy()["desired"] == "running"
    assert not store.service_policy()["automatic_start_allowed"]
    resolution = request(
        identity,
        "operations.resolve",
        operation_id=str(start.request_id),
        approve_current_state=True,
    )
    store.enqueue(identity["operator_id"], resolution)
    store.claim()
    store.guard(resolution.request_id, record_effect=True)
    result = store.resolve(identity["operator_id"], resolution, {"running": False, "ready": False})
    store.finish(resolution.request_id, result=result)
    policy = store.service_policy()
    assert policy["desired"] == "stopped" and not policy["pending_work"]
    assert not policy["automatic_start_allowed"]


def test_expired_stop_does_not_disable_healthy_service_repair(adopted, monkeypatch):
    from mnemion.host_control import store as store_module

    store, identity = adopted
    store.enqueue(
        identity["operator_id"],
        request(identity, "service.stop", approve_service_interruption=True),
    )
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    monkeypatch.setattr(store_module, "timestamp", lambda: later.isoformat(timespec="microseconds"))
    assert store.claim() is None
    assert store.service_policy()["automatic_start_allowed"]


def prepare_policy(prepared):
    service, root, operator, _, port = prepared
    identity = installation.adopt(root, service, operator, port=port)["connection"]
    return service, root, Store(root / "authority"), identity, installation.settings(root)[1]


def test_adoption_preserves_stopped_service_and_pending_migration(prepared_host, monkeypatch):
    service, root, store, identity, value = prepare_policy(prepared_host)
    starts = []
    monkeypatch.setattr(supervision, "start", lambda *_: starts.append(True))
    assert memory_lifecycle.policy(root)["desired"] == "stopped"
    assert not memory_lifecycle.observe(root, value, store)["start_requested"]
    start = effect(store, identity, "service.start")
    store.finish(start.request_id, result={"running": True})
    state_io.write(service / "updates/upgrade-journal.json", {"retained": True})
    assert memory_lifecycle.policy(root)["recovery_required"]
    assert not memory_lifecycle.observe(root, value, store)["start_requested"]
    assert not starts


def test_unconfirmed_boot_is_not_replayed_and_new_explicit_start_can_recover(
    prepared_host, monkeypatch
):
    _, root, store, identity, value = prepare_policy(prepared_host)
    start = effect(store, identity, "service.start")
    store.finish(start.request_id, result={"running": True})
    calls = []

    def lost(_):
        calls.append(True)
        raise TimeoutError("Lost startup observation")

    monkeypatch.setattr(supervision, "start", lost)
    with pytest.raises(TimeoutError):
        memory_lifecycle.observe(root, value, store)
    assert memory_lifecycle.policy(root)["start_needs_inspection"]
    assert not memory_lifecycle.observe(root, value, store)["start_requested"]
    assert calls == [True]
    replacement = effect(store, identity, "service.start")
    store.finish(replacement.request_id, result={"running": True})
    monkeypatch.setattr(supervision, "start", lambda _: {"running": True})
    assert memory_lifecycle.observe(root, value, store)["start_requested"]
    assert not memory_lifecycle.policy(root)["start_needs_inspection"]


def test_original_start_is_observed_without_replay(prepared_host, monkeypatch):
    _, root, store, identity, value = prepare_policy(prepared_host)
    state_io.directory(root / "memory-supervision")
    state_io.write(
        root / "memory-supervision/start-intent.json",
        {
            "format": 1,
            "kind": "start",
            "at": datetime.now(timezone.utc).isoformat(),
            "host_id": identity["host_id"],
            "operation_id": None,
        },
    )
    monkeypatch.setattr(supervision, "status", lambda _: {"running": True})
    monkeypatch.setattr(supervision, "start", lambda _: pytest.fail("Must observe, not repeat"))
    assert memory_lifecycle.observe(root, value, store)["running"]
    assert not (root / "memory-supervision/start-intent.json").exists()


def test_existing_worker_owns_the_start_boundary(prepared_host, monkeypatch):
    _, root, store, _, value = prepare_policy(prepared_host)
    monkeypatch.setattr(supervision, "start", lambda _: pytest.fail("Existing work owns the host"))
    with state_io.lock(root / "worker"), pytest.raises(state_io.OperationBusy):
        memory_lifecycle.observe(root, value, store)


def test_watchdog_repair_obeys_stop_and_does_not_repeat_uncertain_effects(
    prepared_host, monkeypatch
):
    _, root, store, identity, value = prepare_policy(prepared_host)
    calls = []
    monkeypatch.setattr(supervision, "status", lambda _: {"running": True, "ready": False})
    monkeypatch.setattr(supervision, "stop", lambda _: calls.append("stop") or {"stopped": True})
    monkeypatch.setattr(
        supervision, "start", lambda _: calls.append("start") or {"running": True, "ready": False}
    )
    assert not memory_lifecycle.repair(root)["start_requested"]
    assert not calls
    start = effect(store, identity, "service.start")
    store.finish(start.request_id, result={"running": True})
    assert memory_lifecycle.repair(root)["start_requested"]
    assert calls == ["stop", "start"]
    assert memory_lifecycle.policy(root)["start_needs_inspection"]
    assert not memory_lifecycle.observe(root, value, store)["start_requested"]
    assert not memory_lifecycle.repair(root)["start_requested"]
    assert calls == ["stop", "start"]
    monkeypatch.setattr(supervision, "status", lambda _: {"running": True, "ready": True})
    assert not memory_lifecycle.repair(root)["start_requested"]
    assert not memory_lifecycle.policy(root)["start_needs_inspection"]


@pytest.mark.parametrize("damaged", [{}, {"host_id": "unrelated-host"}, {"format": True}])
def test_damaged_start_receipt_cannot_authorize_a_restart(prepared_host, monkeypatch, damaged):
    _, root, store, identity, value = prepare_policy(prepared_host)
    start = effect(store, identity, "service.start")
    store.finish(start.request_id, result={"running": True})
    state_io.directory(root / "memory-supervision")
    state_io.write(root / "memory-supervision/start-intent.json", damaged)
    monkeypatch.setattr(
        supervision, "start", lambda _: pytest.fail("Damaged intent cannot restart memory")
    )
    with pytest.raises(HostControlError, match="Inspect"):
        memory_lifecycle.observe(root, value, store)


def test_real_os_entrypoint_keeps_approved_stop_across_process_restart(prepared_host, tmp_path):
    service, root, store, identity, value = prepare_policy(prepared_host)
    stop = effect(store, identity, "service.stop")
    store.finish(stop.request_id, result={"stopped": True})
    receipt_path = root / "memory-supervision/status.json"
    for attempt in range(2):
        with (tmp_path / f"memory-gate-{attempt}.log").open("wb") as output:
            process = subprocess.Popen(
                [sys.executable, str(root / "launcher.py"), str(root), "memory"],
                cwd=value["directory"],
                stdout=output,
                stderr=output,
            )
            try:

                def observed():
                    if not receipt_path.exists():
                        return None
                    result = state_io.read(receipt_path)
                    return result if result["process_identity"]["pid"] == process.pid else None

                receipt = wait_until(observed)
                assert receipt["policy"]["desired"] == "stopped"
                assert not receipt["running"] and not receipt["start_requested"]
                assert not supervision.status(service)["running"]
                assert Store(root / "authority").service_policy()["operation_id"] == str(
                    stop.request_id
                )
            finally:
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=15)
                assert process.returncode == 0
