"""Source checks for diagnostic owned-launch accounting.

The lifecycle case is the adapter's own self-check. It is not resource acceptance.
"""

import ctypes
import json
import os
import sys
from pathlib import Path

import pytest

from deploy.owned_launch_accounting import (
    ADDITIONAL_RSS_BUDGET_BYTES,
    CPU_BUDGET_ONE_CORE_FRACTION,
    OwnedLaunch,
    OwnedLaunchError,
    _Ledger,
    combine_active_cpu,
    installed_journey_boundary,
)
from deploy.owned_launch_self_check import (
    _require_owned_cleanup,
    lifecycle_receipt_qualifies,
    run_self_check,
)


def test_active_cpu_keeps_missing_counters_null_and_keeps_a_measured_zero():
    missing = combine_active_cpu(
        [
            {"active": True, "cpu_start": 10, "cpu_end": None, "start_ns": 0, "end_ns": 1000},
        ]
    )
    assert missing == {"cpu_microseconds": None, "wall_microseconds": None}
    measured = combine_active_cpu(
        [
            {"active": True, "cpu_start": 10, "cpu_end": 10, "start_ns": 0, "end_ns": 0},
            {"active": False, "cpu_start": 10, "cpu_end": 90, "start_ns": 0, "end_ns": 5_000_000},
        ]
    )
    assert measured == {"cpu_microseconds": 0, "wall_microseconds": 0}
    assert (
        combine_active_cpu(
            [
                {"active": False, "cpu_start": 0, "cpu_end": 50, "start_ns": 0, "end_ns": 1000},
            ]
        )["cpu_microseconds"]
        is None
    )


def test_negative_cpu_delta_is_unavailable_rather_than_clamped():
    assert (
        combine_active_cpu(
            [
                {"active": True, "cpu_start": 20, "cpu_end": 10, "start_ns": 0, "end_ns": 1000},
            ]
        )["cpu_microseconds"]
        is None
    )


def test_settlement_cannot_be_marked_active():
    backend = _FakeBackend()
    launch = OwnedLaunch(backend, bound_seconds=5, sample_seconds=0.02)
    try:
        with pytest.raises(OwnedLaunchError):
            launch.mark_phase("settlement", canonical_operations_completed=1, active=True)
        with pytest.raises(OwnedLaunchError):
            launch.mark_phase("send-settlement", canonical_operations_completed=1, active=True)
    finally:
        launch.finish()


def test_report_keeps_commit_and_cold_start_out_of_rss_acceptance():
    backend = _FakeBackend()
    launch = OwnedLaunch(backend, bound_seconds=5, sample_seconds=0.02)
    launch.mark_phase("canonical-work", canonical_operations_completed=0, active=True)
    backend.cpu = 8_000
    report = launch.finish(canonical_operations_completed=1)
    assert report["resource_acceptance"] is False
    assert report["budget"]["status"] == "UNACCEPTED"
    assert report["budget"]["compared"] is False
    assert report["budget"]["additional_rss_bytes_per_process"] == ADDITIONAL_RSS_BUDGET_BYTES
    assert report["budget"]["cpu_one_core_fraction"] == CPU_BUDGET_ONE_CORE_FRACTION
    assert report["cold_start"]["subtracted"] is False
    assert report["active_cpu_microseconds"] == 7_000
    assert report["kernel"]["peak_job_commit_bytes"] == 123456789
    assert report["kernel"]["commit_counters_are_working_set"] is False
    encoded = json.dumps(report)
    assert "123456789" not in encoded.split("peak_job_commit_bytes")[0]
    assert report["missing_recorded_as_zero"] is False
    assert "unseen_or_unsampled_process_working_set" in report["unavailable_counters"]
    with pytest.raises(OwnedLaunchError):
        launch.finish()


def test_missing_active_counter_is_not_zero():
    backend = _FakeBackend()
    backend.cpu = None
    launch = OwnedLaunch(backend, bound_seconds=5, sample_seconds=0.02)
    launch.mark_phase("canonical-work", canonical_operations_completed=0, active=True)
    report = launch.finish(canonical_operations_completed=1)
    assert report["active_cpu_microseconds"] is None
    assert report["active_core_fraction"] is None
    assert report["lifetime_cpu_microseconds"] == 5_000


def test_installed_launcher_wires_the_resource_workload_and_budget_is_unchanged():
    boundary = installed_journey_boundary()
    assert boundary["wired_into_smoke_installed_hosting"] is True
    assert boundary["delivery_is_canonical_workload"] is False
    assert boundary["budget"]["additional_rss_bytes_per_process"] == 8_388_608
    assert boundary["budget"]["cpu_one_core_fraction"] == 0.005
    assert boundary["budget"]["compared"] is False
    launcher = Path("studio/electron/scripts/smoke-installed-hosting.mjs").read_text(
        encoding="utf-8"
    )
    assert "deploy.owned_installed_launch" in launcher
    assert "MNEMION_TELEMETRY_INSTALLED_RESOURCE" in launcher
    disclosure = json.loads(
        Path("mnemion/product_telemetry/disclosure.json").read_text(encoding="utf-8")
    )
    assert "owned_launch" not in json.dumps(disclosure)


def test_ledger_does_not_reuse_a_pid_identity_or_invent_rss():
    ledger = _Ledger()
    ledger.add_identity(15, 100)
    ledger.observe(15, 200, current=None, high_water=None)
    assert [row["identity"] for row in ledger.public()] == ["15:100", "15:200"]
    assert ledger.public()[1]["peak_working_set_bytes"] is None


class _FloatUsage:
    def __init__(self, user, system):
        self.ru_utime = user
        self.ru_stime = system


class _Timeval:
    def __init__(self, sec, usec):
        self.tv_sec = sec
        self.tv_usec = usec


class _TimevalUsage:
    def __init__(self):
        self.ru_utime = _Timeval(4, 5)
        self.ru_stime = _Timeval(6, 7)


class _RootProcess:
    def __init__(self, pid):
        self.pid = pid
        self.returncode = None
        self.polls = 0

    def poll(self):
        self.polls += 1
        self.returncode = 0
        return self.returncode


def _patch_darwin_wait(monkeypatch, scripted):
    import deploy.owned_launch_accounting as accounting

    pending = list(scripted)
    seen = []

    def wait4(pid, options):
        seen.append((pid, options))
        if not pending:
            raise AssertionError("wait4 called after the scripted root exit")
        return pending.pop(0)

    monkeypatch.setattr(accounting.os, "wait4", wait4, raising=False)
    monkeypatch.setattr(accounting.os, "WNOHANG", 1, raising=False)
    return seen


def test_darwin_wait4_is_the_only_reaper_and_reads_float_seconds(monkeypatch):
    import deploy.owned_launch_accounting as accounting

    root = _RootProcess(4242)
    fat = {
        "user": 9_000_000_000,
        "system": 0,
        "child_user": 0,
        "child_system": 0,
        "resident": 10,
        "start": 111,
    }
    monkeypatch.setattr(accounting, "_darwin_rusage", lambda _library, _pid: fat)
    seen = _patch_darwin_wait(
        monkeypatch,
        [
            (4242, 0x7F, _FloatUsage(9.0, 9.0)),
            (0, 0, _FloatUsage(9.0, 9.0)),
            (4242, 3 << 8, _FloatUsage(0.5, 0.25)),
        ],
    )
    backend = accounting.DarwinBackend(["worker"], cwd=None, env=None)
    backend.process = root
    backend.root_creation = 111
    backend._libproc = object()
    backend._timebase = (1, 1)
    assert backend.still_active() is True
    assert root.returncode is None
    assert backend._waited is None
    assert backend.wait_root(1) is True
    assert root.polls == 0
    assert root.returncode == 3
    assert seen == [(4242, 1), (4242, 1), (4242, 1)]
    snapshot = backend.snapshot()
    assert snapshot["cpu_microseconds"] == 750_000
    assert snapshot["kernel"]["wait4_direct_child_cpu_microseconds"] == 750_000
    assert snapshot["cpu_complete"] is False
    assert backend.coverage(snapshot, [])["status"] == "partial"
    assert backend.coverage(snapshot, [])["cpu_lifetime_complete"] is False
    assert backend.coverage(snapshot, [])["cpu_includes_exited_descendants"] is False

    signaled = _RootProcess(4242)
    signaled_seen = _patch_darwin_wait(monkeypatch, [(4242, 9, _FloatUsage(0.125, 0.125))])
    signaled_backend = accounting.DarwinBackend(["worker"], cwd=None, env=None)
    signaled_backend.process = signaled
    signaled_backend.root_creation = 111
    signaled_backend._libproc = object()
    signaled_backend._timebase = (1, 1)
    assert signaled_backend.wait_root(1) is True
    assert signaled.polls == 0
    assert signaled.returncode == -9
    assert signaled_backend.snapshot()["cpu_microseconds"] == 250_000
    assert signaled_seen == [(4242, 1)]

    missed = _RootProcess(4242)
    _patch_darwin_wait(monkeypatch, [(4242, 1 << 8, _TimevalUsage())])
    missed_backend = accounting.DarwinBackend(["worker"], cwd=None, env=None)
    missed_backend.process = missed
    missed_backend.root_creation = 111
    missed_backend._libproc = object()
    missed_backend._timebase = (1, 1)
    assert missed_backend.wait_root(1) is True
    assert missed.polls == 0
    assert missed.returncode == 1
    missed_snapshot = missed_backend.snapshot()
    assert missed_snapshot["cpu_microseconds"] is None
    assert missed_snapshot["kernel"]["wait4_direct_child_cpu_microseconds"] is None
    assert missed_snapshot["cpu_microseconds"] != 9_000_000


def test_darwin_exited_root_reports_surviving_group_members(monkeypatch):
    import deploy.owned_launch_accounting as accounting

    kills = []
    monkeypatch.setattr(accounting.os, "kill", lambda pid, sig: kills.append((pid, sig)))
    monkeypatch.setattr(accounting, "_darwin_rusage", lambda _library, _pid: None)
    monkeypatch.setattr(
        accounting,
        "_darwin_group_pids",
        lambda _library, pgid: [os.getpid(), 5555] if pgid == 4242 else None,
    )
    _patch_darwin_wait(monkeypatch, [(4242, 0, _FloatUsage(0.5, 0.25))])
    backend = accounting.DarwinBackend(["worker"], cwd=None, env=None)
    backend.process = _RootProcess(4242)
    backend.root_creation = 111
    backend._libproc = object()
    backend._timebase = (1, 1)
    backend.sample = lambda _ledger: None
    launch = accounting.OwnedLaunch(backend, bound_seconds=5, sample_seconds=0.02)
    report = launch.finish(canonical_operations_completed=0)
    assert backend.process.polls == 0
    assert kills == [(-4242, 9)]
    assert report["cleanup"]["ok"] is False
    assert report["cleanup"]["failure"] == "descendants_survived"
    assert report["cleanup"]["retried"] is False
    assert report["coverage"]["status"] == "partial"
    assert report["coverage"]["cpu_lifetime_complete"] is False
    assert report["coverage"]["cpu_includes_exited_descendants"] is False
    assert report["kernel"]["wait4_direct_child_cpu_microseconds"] == 750_000
    assert report["lifetime_cpu_microseconds"] == 750_000
    assert report["resource_acceptance"] is False
    assert report["kernel"]["includes_only_reaped_descendants"] is True


def test_darwin_reused_leader_is_not_signaled(monkeypatch):
    import deploy.owned_launch_accounting as accounting

    kills = []
    monkeypatch.setattr(accounting.os, "kill", lambda pid, sig: kills.append((pid, sig)))

    def rusage(_library, pid):
        if pid == 4242:
            return {
                "user": 1,
                "system": 1,
                "child_user": 0,
                "child_system": 0,
                "resident": 1,
                "start": 999,
            }
        return None

    monkeypatch.setattr(accounting, "_darwin_rusage", rusage)
    monkeypatch.setattr(accounting, "_darwin_group_pids", lambda _library, _pgid: [4242, 5555])
    _patch_darwin_wait(monkeypatch, [(4242, 0, _FloatUsage(0.5, 0.25))])
    backend = accounting.DarwinBackend(["worker"], cwd=None, env=None)
    backend.process = _RootProcess(4242)
    backend.root_creation = 111
    backend._libproc = object()
    backend._timebase = (1, 1)
    backend.sample = lambda _ledger: None
    launch = accounting.OwnedLaunch(backend, bound_seconds=5, sample_seconds=0.02)
    report = launch.finish(canonical_operations_completed=0)
    assert kills == []
    assert backend.process.polls == 0
    assert report["cleanup"]["ok"] is False
    assert report["cleanup"]["failure"] == "pid_reused"
    assert report["cleanup"]["retried"] is False
    assert report["coverage"]["cpu_lifetime_complete"] is False
    assert report["lifetime_cpu_microseconds"] == 750_000


def test_darwin_group_list_reads_only_that_process_group():
    import deploy.owned_launch_accounting as accounting

    ctypes.set_errno(0)
    calls = []
    width = ctypes.sizeof(ctypes.c_int)
    cap = 64 * width

    class Library:
        def proc_listpids(self, kind, pgid, buf, size):
            calls.append((kind, pgid, buf is None, size))
            if buf is None or size == 0:
                return (400 + 20) * width
            values = ctypes.cast(buf, ctypes.POINTER(ctypes.c_int))
            values[0] = 4242
            values[1] = 5555
            return width * 2

    assert accounting._darwin_group_pids(Library(), 4242) == [4242, 5555]
    assert calls == [(2, 4242, False, cap)]

    class BusyHost:
        def proc_listpids(self, kind, pgid, buf, size):
            calls.append(("busy", buf is None, size))
            if buf is None or size == 0:
                return (400 + 20) * width
            values = ctypes.cast(buf, ctypes.POINTER(ctypes.c_int))
            values[0] = 4242
            return width

    assert accounting._darwin_group_pids(BusyHost(), 4242) == [4242]
    assert ("busy", True, 0) not in calls
    assert calls[-1] == ("busy", False, cap)

    class Empty:
        def proc_listpids(self, kind, pgid, buf, size):
            ctypes.set_errno(0)
            return 0

    assert accounting._darwin_group_pids(Empty(), 4242) == []

    class ErrorZero:
        def proc_listpids(self, kind, pgid, buf, size):
            ctypes.set_errno(22)
            return 0

    assert accounting._darwin_group_pids(ErrorZero(), 4242) is None

    class ErrnoWithPids:
        def proc_listpids(self, kind, pgid, buf, size):
            values = ctypes.cast(buf, ctypes.POINTER(ctypes.c_int))
            values[0] = 4242
            ctypes.set_errno(22)
            return width

    assert accounting._darwin_group_pids(ErrnoWithPids(), 4242) is None

    class Full:
        def proc_listpids(self, kind, pgid, buf, size):
            values = ctypes.cast(buf, ctypes.POINTER(ctypes.c_int))
            values[0] = 4242
            return size

    assert accounting._darwin_group_pids(Full(), 4242) is None

    class Over:
        def proc_listpids(self, kind, pgid, buf, size):
            calls.append(("over", buf is None, size))
            return size + width

    assert accounting._darwin_group_pids(Over(), 4242) is None
    assert calls[-1] == ("over", False, cap)

    class Hole:
        def proc_listpids(self, kind, pgid, buf, size):
            values = ctypes.cast(buf, ctypes.POINTER(ctypes.c_int))
            values[0] = 4242
            values[1] = 0
            values[2] = 5555
            return width * 3

    assert accounting._darwin_group_pids(Hole(), 4242) is None

    class Short:
        def proc_listpids(self, kind, pgid, buf, size):
            return 2

    assert accounting._darwin_group_pids(Short(), 4242) is None
    assert accounting._darwin_group_pids(Empty(), 1) is None
    assert accounting._darwin_group_pids(Empty(), True) is None
    assert accounting._darwin_group_pids(None, 4242) is None
    ctypes.set_errno(0)


def test_darwin_reused_pid_does_not_replace_the_root_identity(monkeypatch):
    import deploy.owned_launch_accounting as accounting

    kills = []
    monkeypatch.setattr(accounting.os, "kill", lambda pid, sig: kills.append((pid, sig)))
    monkeypatch.setattr(accounting, "_darwin_children", lambda _library, _pid: [])
    starts = {4242: 111}

    def rusage(_library, pid):
        if pid == 4242:
            return {
                "user": 1,
                "system": 1,
                "child_user": 0,
                "child_system": 0,
                "resident": 4,
                "start": starts[4242],
            }
        return None

    monkeypatch.setattr(accounting, "_darwin_rusage", rusage)
    backend = accounting.DarwinBackend(["worker"], cwd=None, env=None)
    backend.process = _RootProcess(4242)
    backend._libproc = object()
    backend.sample(backend.ledger)
    starts[4242] = 999
    backend.sample(backend.ledger)
    assert backend.root_creation == 111
    assert [row["identity"] for row in backend.ledger.public()] == ["4242:111"]
    starts[4242] = 111
    backend.sample(backend.ledger)
    assert backend.root_creation == 111
    assert [row["identity"] for row in backend.ledger.public()] == ["4242:111"]
    starts[4242] = 999
    ok, failure = backend.terminate()
    assert ok is False
    assert failure == "pid_reused"
    assert kills == []


def test_failed_owned_cleanup_does_not_qualify():
    with pytest.raises(AssertionError, match="^descendants_survived$"):
        _require_owned_cleanup(
            {
                "cleanup": {"ok": False, "failure": "descendants_survived", "retried": False},
            }
        )
    with pytest.raises(AssertionError, match="^cleanup_missing$"):
        _require_owned_cleanup({})

    darwin = {
        "held": True,
        "platform": "darwin",
        "resource_acceptance": False,
        "coverage_status": "partial",
        "cpu_lifetime_complete": False,
        "lifetime_cpu_microseconds": 750_000,
        "cleanup_ok": False,
        "cleanup_failure": "descendants_survived",
    }
    assert lifecycle_receipt_qualifies(darwin) is False
    missing = dict(darwin)
    del missing["cleanup_ok"]
    del missing["cleanup_failure"]
    assert lifecycle_receipt_qualifies(missing) is False
    assert lifecycle_receipt_qualifies({"held": False, "failure": "descendants_survived"}) is False
    good = dict(darwin)
    good["cleanup_ok"] = True
    good["cleanup_failure"] = None
    assert lifecycle_receipt_qualifies(good) is True
    exercised = dict(good)
    exercised["invalid_handle_exercise"] = {
        "exercised": True,
        "failure": "terminate_job_6",
        "retried": False,
    }
    assert lifecycle_receipt_qualifies(exercised) is True
    mixed = dict(exercised)
    mixed["cleanup_ok"] = False
    mixed["cleanup_failure"] = "terminate_job_6"
    assert lifecycle_receipt_qualifies(mixed) is False
    unsupported = dict(good)
    unsupported["honest_unsupported"] = "cgroup_unavailable"
    assert lifecycle_receipt_qualifies(unsupported) is False
    complete = dict(good)
    complete["cpu_lifetime_complete"] = True
    assert lifecycle_receipt_qualifies(complete) is False
    windows = {
        "held": True,
        "platform": "win32",
        "resource_acceptance": False,
        "cleanup_ok": True,
        "cleanup_failure": None,
        "invalid_handle_exercise": {
            "exercised": True,
            "failure": "terminate_job_6",
            "retried": False,
        },
    }
    assert lifecycle_receipt_qualifies(windows) is True
    windows_mixed = dict(windows)
    windows_mixed["cleanup_failure"] = "terminate_job_6"
    assert lifecycle_receipt_qualifies(windows_mixed) is False


def test_owned_launch_lifecycle_self_check():
    result = run_self_check()
    assert result["held"] is True
    assert result["resource_acceptance"] is False
    assert result["platform"] == sys.platform


class _FakeBackend:
    def __init__(self):
        self.ledger = _Ledger()
        self.ledger.add_identity(4, 10)
        self.cpu = 1_000

    def cpu_microseconds(self):
        return self.cpu

    def sample(self, ledger):
        return None

    def still_active(self):
        return False

    def wait_root(self, _timeout):
        return True

    def terminate(self):
        return True, None

    def snapshot(self):
        return {
            "method": "fake",
            "cpu_microseconds": 5_000,
            "identities_missing": 1,
            "observer_in_measured_group": False,
            "sampled_peaks": {"sampled_pid_cpu_is_complete": False},
            "kernel": {
                "peak_job_commit_bytes": 123456789,
                "commit_counters_are_working_set": False,
            },
            "cpu_complete": True,
            "unavailable": [],
        }

    def coverage(self, _snapshot, _ledger):
        return {
            "platform": "windows",
            "status": "partial",
            "cpu_lifetime_complete": True,
            "cpu_includes_exited_descendants": True,
            "sampled_pid_cpu_is_complete": False,
            "rss_high_water": "unavailable",
            "rss_high_water_covers_unseen_exited_processes": False,
            "cgroup_memory_peak_is_per_process_rss": False,
        }

    def close(self):
        return True, None


def test_linux_cleanup_drains_owned_members_before_removal(tmp_path, monkeypatch):
    import threading
    import time

    import deploy.owned_launch_accounting as accounting

    leaf = tmp_path / "owned-leaf"
    leaf.mkdir()
    (leaf / "cgroup.procs").write_text("4242\n", encoding="ascii")
    (leaf / "cgroup.events").write_text("populated 1\n", encoding="ascii")
    backend = accounting.LinuxCgroupBackend.__new__(accounting.LinuxCgroupBackend)
    backend.leaf = leaf
    backend.process = _RootProcess(50)
    backend._closed = False
    backend._sampled_sum_peak = None
    signaled = []
    killed = []
    monkeypatch.setattr(accounting, "_signal_cgroup", lambda _leaf: signaled.append(_leaf) or (True, None))
    monkeypatch.setattr(accounting.os, "kill", lambda *_args: killed.append(_args))

    def clear():
        time.sleep(0.12)
        (leaf / "cgroup.procs").write_text("", encoding="ascii")
        (leaf / "cgroup.events").write_text("populated 0\n", encoding="ascii")

    threading.Thread(target=clear, daemon=True).start()

    def remove():
        assert backend._member_state() == "empty"
        for child in list(leaf.iterdir()):
            child.unlink()
        leaf.rmdir()
        return not leaf.exists()

    backend._rmdir_leaf = remove
    ok, failure = backend.close(drain_seconds=2)
    assert ok is True and failure is None
    assert not leaf.exists()
    assert backend.leaf is None
    assert signaled == []
    assert killed == []
    assert backend._cleanup_retried is False


def test_linux_cleanup_keeps_a_group_that_remains(tmp_path, monkeypatch):
    import deploy.owned_launch_accounting as accounting

    leaf = tmp_path / "owned-leaf"
    leaf.mkdir()
    (leaf / "cgroup.procs").write_text("", encoding="ascii")
    (leaf / "cgroup.events").write_text("populated 0\n", encoding="ascii")
    (leaf / "child").mkdir()
    backend = accounting.LinuxCgroupBackend.__new__(accounting.LinuxCgroupBackend)
    backend.leaf = leaf
    backend.process = _RootProcess(50)
    backend._closed = False
    backend._sampled_sum_peak = None
    monkeypatch.setattr(
        accounting.os, "kill", lambda *_args: (_ for _ in ()).throw(AssertionError("killed"))
    )
    ok, failure = backend.close(drain_seconds=0.2)
    assert ok is False
    assert failure == "cgroup_rmdir_failed"
    assert leaf.exists()
    assert backend.leaf == leaf
    assert backend._cleanup_retried is True
    again_ok, again_failure = backend.close()
    assert (again_ok, again_failure) == (False, "cgroup_rmdir_failed")
    assert leaf.exists()


def test_startup_category_does_not_complete_or_keep_a_message(tmp_path):
    import json

    from deploy.owned_installed_launch import (
        _smoke_observation,
        owned_launch_succeeded,
        startup_failure_category,
    )

    secret = "super-secret-token-value"
    assert startup_failure_category(f"Error: Real save failed: {secret}") == "memory_save"
    assert secret not in startup_failure_category(f"Error: Real save failed: {secret}")
    assert startup_failure_category("not a known probe failure") == "unclassified"
    assert startup_failure_category(None) is None
    assert owned_launch_succeeded(False, 0, True, "startup-error") is False
    assert owned_launch_succeeded(True, 0, False, None) is False
    assert owned_launch_succeeded(True, 0, True, None) is True
    smoke = tmp_path / "smoke.json"
    smoke.write_text(
        json.dumps(
            {
                "stage": "startup-error",
                "error": f"Error: Real save failed: {secret}",
                "failure_category": "memory_save",
            }
        ),
        encoding="utf-8",
    )
    stage, category = _smoke_observation(smoke)
    assert (stage, category) == ("startup-error", "memory_save")
    smoke.write_text(
        json.dumps({"stage": "startup-error", "failure_category": secret, "error": f"C:\\Users\\{secret}"}),
        encoding="utf-8",
    )
    stage, category = _smoke_observation(smoke)
    assert stage == "startup-error"
    assert category == "unclassified"
    assert secret not in category
    smoke.write_text(
        json.dumps({"stage": "hosting-ready", "error": secret, "failure_category": "memory_save"}),
        encoding="utf-8",
    )
    assert _smoke_observation(smoke) == ("hosting-ready", None)


def test_linux_finish_reads_the_counter_after_child_drain(tmp_path, monkeypatch):
    """The reported lifetime is the post-drain cpu.stat value, then the leaf goes."""
    import threading
    import time

    import deploy.owned_launch_accounting as accounting

    leaf = tmp_path / "owned-leaf"
    leaf.mkdir()
    (leaf / "cgroup.procs").write_text("4242\n", encoding="ascii")
    (leaf / "cgroup.events").write_text("populated 1\n", encoding="ascii")
    (leaf / "cpu.stat").write_text("usage_usec 1000\n", encoding="ascii")
    (leaf / "memory.peak").write_text("100\n", encoding="ascii")
    backend = accounting.LinuxCgroupBackend.__new__(accounting.LinuxCgroupBackend)
    backend.leaf = leaf
    backend.process = _RootProcess(50)
    backend._closed = False
    backend._cleanup_retried = False
    backend._sampled_sum_peak = None
    backend.ledger = accounting._Ledger()
    order = []
    monkeypatch.setattr(accounting, "_signal_cgroup", lambda _leaf: (True, None))

    def snapshot():
        order.append("snapshot")
        return accounting.LinuxCgroupBackend.snapshot(backend)

    def remove():
        order.append("remove")
        for child in list(leaf.iterdir()):
            if child.is_file():
                child.unlink()
        return accounting.LinuxCgroupBackend._rmdir_leaf(backend)

    backend.snapshot = snapshot
    backend._rmdir_leaf = remove

    def clear():
        time.sleep(0.12)
        (leaf / "cpu.stat").write_text("usage_usec 3000\n", encoding="ascii")
        (leaf / "cgroup.procs").write_text("", encoding="ascii")
        (leaf / "cgroup.events").write_text("populated 0\n", encoding="ascii")

    threading.Thread(target=clear, daemon=True).start()
    launch = accounting.OwnedLaunch(backend, bound_seconds=30, sample_seconds=0.05)
    report = launch.finish()
    assert order == ["snapshot", "remove"]
    assert report["lifetime_cpu_microseconds"] == 3000
    assert report["kernel"]["cpu_usage_usec"] == 3000
    assert report["coverage"]["cpu_lifetime_complete"] is True
    assert report["coverage"]["cpu_includes_exited_descendants"] is True
    assert report["resource_acceptance"] is False
    assert report["cleanup"]["ok"] is True
    assert backend.leaf is None
    assert not leaf.exists()
