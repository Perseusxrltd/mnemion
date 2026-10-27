"""Real, short-lived native process custody; never a model or provider call."""

import subprocess
import sys
import time
import os
from pathlib import Path

import psutil
import pytest

from mnemion import local_state, process_identity
from mnemion.managed_model_process import ModelControlError, ModelController


SLEEP = [sys.executable, "-c", "import time; time.sleep(120)", "vllm", "serve"]


@pytest.fixture
def controller(tmp_path):
    value = ModelController(tmp_path / "custody")
    yield value
    try:
        value.stop()
    finally:
        if value._child is not None and value._child.poll() is None:
            value._child.kill()
            value._child.wait(timeout=5)


def test_fresh_operator_stops_owned_process_and_preserves_same_named_external_one(controller):
    foreign = subprocess.Popen(
        SLEEP, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        assert controller.launch(SLEEP) is True
        pid = controller._child.pid
        other = ModelController(controller.root)
        assert other.owned() is True
        assert other.launch(SLEEP) is False
        assert other.stop() is True
        assert controller._child.poll() is not None
        assert not other.owned() and local_state.read(other.path)["state"] == "stopped"
        assert other.stop() is True
        assert other.stop(only_unused=True) is False
        assert foreign.poll() is None and pid != foreign.pid
    finally:
        foreign.terminate()
        foreign.wait(timeout=5)


def test_stopping_a_foreground_launcher_also_stops_its_verified_child(controller, tmp_path):
    marker = tmp_path / "child.pid"
    program = "import subprocess,sys,time;from pathlib import Path; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);Path(sys.argv[1]).write_text(str(p.pid));time.sleep(120)"
    assert controller.launch([sys.executable, "-c", program, str(marker)])
    child = None
    try:
        deadline = time.monotonic() + 5
        while not marker.exists():
            assert time.monotonic() < deadline and controller._child.poll() is None
            time.sleep(0.02)
        child = psutil.Process(int(marker.read_text()))
        identity = process_identity.capture(child)
        assert ModelController(controller.root).stop() is True
        assert controller._process(identity) is None
    finally:
        if child is not None and child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
            child.kill()


def test_idle_and_automatic_restart_wait_for_other_clients_active_requests(controller):
    now = [10_000_000_000]
    controller.clock = lambda: now[0]
    controller.launch(SLEEP)
    launch = controller.launch_identity()
    other = ModelController(controller.root, clock=lambda: now[0])
    activity = other.begin_activity()
    now[0] += 1000 * 1_000_000_000
    assert not controller.stop(launch=launch, idle_seconds=5)
    assert not controller.stop(only_unused=True)
    assert not controller.restart(SLEEP)
    assert controller._child.poll() is None
    other.end_activity(activity)
    assert not controller.stop(launch=launch, idle_seconds=5)
    now[0] += 6 * 1_000_000_000
    assert controller.stop(launch=launch, idle_seconds=5)


def test_old_activity_and_idle_watcher_cannot_control_a_replacement(controller):
    controller.launch(SLEEP)
    old_launch = controller.launch_identity()
    old_activity = controller.begin_activity()
    assert controller.stop()
    controller.launch(SLEEP)
    before = local_state.read(controller.path)
    controller.end_activity(old_activity)
    assert local_state.read(controller.path) == before
    assert not controller.stop(launch=old_launch, idle_seconds=1)
    assert controller._child.poll() is None


def test_reused_pid_is_not_a_new_termination_target(controller, monkeypatch):
    controller.launch(SLEEP)
    before = local_state.read(controller.path)
    original = process_identity.matches
    monkeypatch.setattr(
        process_identity,
        "matches",
        lambda saved, process: False if saved == before["process"] else original(saved, process),
    )
    assert controller.stop() is True
    assert controller._child.poll() is None


def test_failed_custody_publication_reaps_only_its_new_launch(controller, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise OSError("synthetic publication failure")

    monkeypatch.setattr(local_state, "write", refuse)
    with pytest.raises(OSError, match="synthetic publication failure"):
        controller.launch(SLEEP)
    assert controller._child is not None and controller._child.poll() is not None
    assert not controller.path.exists()


def test_damaged_custody_does_not_authorize_launch_or_shutdown(controller, monkeypatch):
    controller._prepare()
    local_state.write(controller.path, {"version": 1, "process": {"pid": 1}})
    monkeypatch.setattr(
        subprocess, "Popen", lambda *_a, **_kw: pytest.fail("Damaged custody launched a process")
    )
    with pytest.raises(ModelControlError):
        controller.launch(SLEEP)
    with pytest.raises(ModelControlError):
        controller.stop()
    controller.path.unlink()


def test_unowned_observation_creates_no_state(tmp_path):
    controller = ModelController(tmp_path / "missing")
    assert not controller.owned()
    assert controller.launch_identity() is None
    assert controller.begin_activity() is None
    assert not controller.stop()
    assert not controller.root.exists()


def test_a_finished_caller_cannot_keep_an_idle_model_alive(controller):
    now = [10_000_000_000]
    controller.clock = lambda: now[0]
    controller.launch(SLEEP)
    script = "from pathlib import Path;import sys;from mnemion.managed_model_process import ModelController;assert ModelController(Path(sys.argv[1]),clock=lambda:10000000000).begin_activity()"
    subprocess.run(
        [sys.executable, "-c", script, str(controller.root)],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        timeout=10,
    )
    assert local_state.read(controller.path)["leases"]
    now[0] += 6_000_000_000
    assert controller.stop(idle_seconds=5)
    assert local_state.read(controller.path)["state"] == "stopped"


def test_unreadable_active_request_refuses_automatic_teardown(controller, monkeypatch):
    controller.launch(SLEEP)
    activity = controller.begin_activity()
    caller = local_state.read(controller.path)["leases"][activity[1]]
    original = controller._process

    def unreadable(identity):
        if identity == caller:
            raise psutil.AccessDenied(caller["pid"])
        return original(identity)

    with monkeypatch.context() as scope:
        scope.setattr(controller, "_process", unreadable)
        with pytest.raises(psutil.AccessDenied):
            controller.stop(only_unused=True)
    assert controller._child.poll() is None
    controller.end_activity(activity)


def test_an_ancestor_record_cannot_terminate_the_controlling_application(controller):
    controller.launch(SLEEP)
    original = local_state.read(controller.path)
    damaged = {**original, "process": process_identity.capture(psutil.Process())}
    local_state.write(controller.path, damaged)
    try:
        with pytest.raises(ModelControlError):
            controller.stop()
        assert controller._child.poll() is None
    finally:
        local_state.write(controller.path, original)


def test_linked_custody_is_not_a_process_control_authority(controller, tmp_path):
    controller.launch(SLEEP)
    linked = tmp_path / "linked-record.json"
    os.link(controller.path, linked)
    try:
        with pytest.raises(local_state.LocalSetupError):
            controller.stop()
        assert controller._child.poll() is None
    finally:
        linked.unlink()


def test_a_published_then_failed_launch_is_not_repeated(controller, monkeypatch):
    write = local_state.write

    def publish_then_fail(*args, **kwargs):
        write(*args, **kwargs)
        raise OSError("synthetic uncertain publication")

    with monkeypatch.context() as scope:
        scope.setattr(local_state, "write", publish_then_fail)
        with pytest.raises(OSError, match="synthetic uncertain publication"):
            controller.launch(SLEEP)
    record = local_state.read(controller.path)
    assert controller._child.poll() is not None
    assert controller._process(record["process"]) is None


def test_excessive_descendants_are_refused_before_any_signal(controller, monkeypatch):
    controller.launch(SLEEP)
    with monkeypatch.context() as scope:
        scope.setattr(psutil.Process, "children", lambda *_a, **_kw: [None] * 512)
        with pytest.raises(ModelControlError):
            controller.stop()
    assert controller._child.poll() is None


def test_restart_serializes_operators_and_does_not_undo_an_explicit_stop(controller):
    controller.launch(SLEEP)
    previous = controller._child
    other = ModelController(controller.root)
    checked = []

    def endpoint_is_available():
        assert previous.poll() is not None
        with pytest.raises(local_state.LocalSetupError):
            other.stop()
        checked.append(True)
        return True

    assert controller.restart(SLEEP, may_start=endpoint_is_available)
    assert checked == [True] and controller._child.pid != previous.pid
    assert controller._child.poll() is None
    assert other.stop()
    assert not controller.restart(SLEEP)
    assert not other.owned()


def test_a_reachable_endpoint_prevents_relaunch_after_owned_stop(controller):
    controller.launch(SLEEP)
    previous = controller._child
    assert not controller.restart(SLEEP, may_start=lambda: False)
    assert previous.poll() is not None
    assert controller._child is previous
    assert local_state.read(controller.path)["state"] == "stopped"


def test_unexpected_owned_process_exit_can_be_restarted(controller):
    controller.launch(SLEEP)
    previous = controller._child
    previous.kill()
    previous.wait(timeout=5)
    assert controller.restart(SLEEP)
    assert controller._child is not previous
    assert controller._child.poll() is None
