"""An operator can obtain a turn without interrupting scans or replaying work."""

from concurrent.futures import ThreadPoolExecutor
import sys
import time

import pytest

from mnemion.service import update_state as state
from mnemion.service.update_manifest import ManifestError

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Managed host uses POSIX locks")


def test_running_scan_finishes_before_operator_enters_and_pause_is_removed(tmp_path):
    root = state.directory(tmp_path / "updates")
    observed = []

    def scan():
        with state.lock(root, shared=True):
            observed.append("scan_started")
            deadline = time.monotonic() + 5
            while not state.connector_update_waiting(root):
                assert time.monotonic() < deadline
                time.sleep(0.01)
            observed.append("scan_finished")

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(scan)
        deadline = time.monotonic() + 5
        while not observed:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        with state.operator_lock(root, wait_seconds=5):
            assert observed == ["scan_started", "scan_finished"]
            with pytest.raises(state.OperationBusy):
                with state.lock(root, shared=True):
                    pass
        future.result(timeout=5)
    assert not (root / "connector-update-pending.json").exists()


def test_busy_operation_body_is_not_replayed(tmp_path):
    root = state.directory(tmp_path / "updates")
    calls = []
    with pytest.raises(state.OperationBusy, match="inside the operation"):
        with state.operator_lock(root):
            calls.append(1)
            raise state.OperationBusy("inside the operation")
    assert calls == [1]
    with state.lock(root):
        pass


def test_zero_wait_defers_without_stealing_or_clearing_existing_pause(tmp_path):
    root = state.directory(tmp_path / "updates")
    state.pause_new_connector_scans(root)
    before = state.read(root / "connector-update-pending.json")
    with state.lock(root, shared=True), pytest.raises(state.OperationBusy):
        with state.operator_lock(root, wait_seconds=0):
            pytest.fail("The scan still owns its lock")
    assert state.read(root / "connector-update-pending.json") == before


def test_wait_deadline_clears_only_its_own_pause(tmp_path, monkeypatch):
    root = state.directory(tmp_path / "updates")
    clock = iter([10.0, 10.0, 10.0, 12.0])
    monkeypatch.setattr(state.time, "monotonic", lambda: next(clock, 12.0))
    monkeypatch.setattr(state.time, "sleep", lambda _: None)
    with state.lock(root, shared=True), pytest.raises(state.OperationBusy):
        with state.operator_lock(root, wait_seconds=1):
            pytest.fail("The deadline must defer")
    assert not (root / "connector-update-pending.json").exists()


def test_a_replacement_pause_is_not_claimed_by_the_waiting_operator(tmp_path, monkeypatch):
    root = state.directory(tmp_path / "updates")
    clock = iter([10.0, 10.0, 10.0, 12.0])
    monkeypatch.setattr(state.time, "monotonic", lambda: next(clock, 12.0))
    original = state.pause_new_connector_scans

    def announce_then_replace(root):
        owned = original(root)
        replacement = {**owned, "until_monotonic": owned["until_monotonic"] + 1}
        state.write(root / "connector-update-pending.json", replacement)
        return owned

    monkeypatch.setattr(state, "pause_new_connector_scans", announce_then_replace)
    monkeypatch.setattr(state.time, "sleep", lambda _: None)
    with state.lock(root, shared=True), pytest.raises(state.OperationBusy):
        with state.operator_lock(root, wait_seconds=1):
            pytest.fail("The existing scan still owns the lock")
    assert (root / "connector-update-pending.json").exists()


@pytest.mark.parametrize("value", [-1, 301, 1.5, True])
def test_invalid_wait_never_creates_operator_state(tmp_path, value):
    root = tmp_path / "updates"
    with pytest.raises(ManifestError, match="0 to 300"):
        with state.operator_lock(root, wait_seconds=value):
            pytest.fail("Invalid wait accepted")
    assert not root.exists()
