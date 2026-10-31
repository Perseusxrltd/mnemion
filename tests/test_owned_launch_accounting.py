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


def _child_buffer_bytes() -> int:
    return 64 * ctypes.sizeof(ctypes.c_int)


def test_darwin_child_list_uses_the_pid_count_from_one_bounded_query():
    import inspect

    import deploy.owned_launch_accounting as accounting

    source = inspect.getsource(accounting._darwin_children)
    assert "proc_listchildpids(pid, None, 0)" not in source
    assert "//" not in source
    implementation = Path("deploy/owned_launch_accounting.py").read_text(encoding="utf-8")
    assert "self._libproc.proc_listchildpids.restype = ctypes.c_int" in implementation
    cap = _child_buffer_bytes()

    for child_count in (1, 2, 3, 4):
        calls = []

        class Library:
            def proc_listchildpids(self, pid, buf, size):
                calls.append((pid, buf is None, 0 if buf is None else size))
                if buf is None or size == 0:
                    return 520
                values = ctypes.cast(buf, ctypes.POINTER(ctypes.c_int))
                for index in range(child_count):
                    values[index] = 6100 + index
                return child_count

        ctypes.set_errno(22)
        expected = [6100 + index for index in range(child_count)]
        assert accounting._darwin_children(Library(), 4242) == expected
        assert calls == [(4242, False, cap)]
    ctypes.set_errno(0)


def test_darwin_child_list_separates_empty_errors_and_truncation():
    import deploy.owned_launch_accounting as accounting

    cap = _child_buffer_bytes()
    calls = []

    class Empty:
        def proc_listchildpids(self, pid, buf, size):
            calls.append((pid, buf is None, 0 if buf is None else size))
            ctypes.set_errno(0)
            return 0

    assert accounting._darwin_children(Empty(), 4242) == []
    assert calls == [(4242, False, cap)]

    class ErrorZero:
        def proc_listchildpids(self, pid, buf, size):
            calls.append(("error", buf is None, 0 if buf is None else size))
            ctypes.set_errno(22)
            return 0

    assert accounting._darwin_children(ErrorZero(), 4242) is None

    class Negative:
        def proc_listchildpids(self, pid, buf, size):
            ctypes.set_errno(22)
            return -1

    assert accounting._darwin_children(Negative(), 4242) is None

    class ErrnoWithPid:
        def proc_listchildpids(self, pid, buf, size):
            values = ctypes.cast(buf, ctypes.POINTER(ctypes.c_int))
            values[0] = 6100
            ctypes.set_errno(22)
            return 1

    assert accounting._darwin_children(ErrnoWithPid(), 4242) is None

    class Oversized:
        def proc_listchildpids(self, pid, buf, size):
            calls.append(("over", buf is None, 0 if buf is None else size))
            if buf is None or size == 0:
                return 520
            values = ctypes.cast(buf, ctypes.POINTER(ctypes.c_int))
            values[0] = 6100
            ctypes.set_errno(0)
            return cap

    assert accounting._darwin_children(Oversized(), 4242) is None
    assert calls[-1] == ("over", False, cap)

    class Full:
        def proc_listchildpids(self, pid, buf, size):
            calls.append(("full", buf is None, 0 if buf is None else size))
            if buf is None or size == 0:
                return 520
            values = ctypes.cast(buf, ctypes.POINTER(ctypes.c_int))
            for index in range(64):
                values[index] = 7000 + index
            ctypes.set_errno(0)
            return 64

    assert accounting._darwin_children(Full(), 4242) is None
    assert calls[-1] == ("full", False, cap)

    class Hole:
        def proc_listchildpids(self, pid, buf, size):
            values = ctypes.cast(buf, ctypes.POINTER(ctypes.c_int))
            values[0] = 6100
            values[1] = 0
            values[2] = 6101
            ctypes.set_errno(0)
            return 3

    assert accounting._darwin_children(Hole(), 4242) is None

    class Text:
        def proc_listchildpids(self, pid, buf, size):
            return "4"

    assert accounting._darwin_children(Text(), 4242) is None

    class Broken:
        def proc_listchildpids(self, pid, buf, size):
            raise OSError("proc_listchildpids failed")

    assert accounting._darwin_children(Broken(), 4242) is None
    assert accounting._darwin_children(Empty(), 0) is None
    assert accounting._darwin_children(Empty(), True) is None
    assert accounting._darwin_children(Empty(), -1) is None
    assert accounting._darwin_children(None, 4242) is None
    assert ("error", True, 0) not in calls
    assert ("full", True, 0) not in calls
    ctypes.set_errno(0)


def test_counted_child_stays_behind_the_parent_check(monkeypatch):
    import deploy.owned_launch_accounting as accounting

    parents = {6100: 4242}
    asked = []

    def rusage(_library, pid):
        if pid == 4242:
            return _resident(111, 20)
        if pid == 6100:
            return _resident(222, 30)
        return None

    def ppid(_library, pid):
        asked.append(pid)
        return parents.get(pid)

    class Counted:
        def proc_listchildpids(self, pid, buf, size):
            if buf is None or size != _child_buffer_bytes():
                return 520
            if pid != 4242:
                ctypes.set_errno(0)
                return 0
            values = ctypes.cast(buf, ctypes.POINTER(ctypes.c_int))
            values[0] = 6100
            ctypes.set_errno(0)
            return 1

    class Failed:
        def proc_listchildpids(self, pid, buf, size):
            ctypes.set_errno(22)
            return 0

    monkeypatch.setattr(accounting, "_darwin_rusage", rusage)
    monkeypatch.setattr(accounting, "_darwin_ppid", ppid)

    def backend(library):
        value = accounting.DarwinBackend(["worker"], cwd=None, env=None)
        value.process = _RootProcess(4242)
        value.root_creation = 111
        value._libproc = library
        value._libsystem = False
        value._timebase = (1, 1)
        return value

    matched = backend(Counted())
    matched.sample(matched.ledger)
    assert [row["identity"] for row in matched.ledger.public()] == ["4242:111", "6100:222"]

    parents[6100] = 1
    rejected = backend(Counted())
    rejected.sample(rejected.ledger)
    assert [row["identity"] for row in rejected.ledger.public()] == ["4242:111"]

    asked.clear()
    unverified = backend(Failed())
    unverified.sample(unverified.ledger)
    assert [row["identity"] for row in unverified.ledger.public()] == ["4242:111"]
    assert 6100 not in asked
    ctypes.set_errno(0)


def test_child_is_charged_only_while_the_parent_creation_holds(monkeypatch):
    import deploy.owned_launch_accounting as accounting

    def run(*, reuse_before_charge=False, reuse_during_task=False, hide_parent=False):
        state = {"parent_start": 111, "parent_visible": True}
        child_tasks = []

        def rusage(_library, pid):
            if pid == 4242:
                if not state["parent_visible"]:
                    return None
                return _resident(state["parent_start"], 20)
            if pid == 5000:
                return _resident(333, 30)
            return None

        def ppid(_library, pid):
            return 4242 if pid == 5000 else None

        def children(_library, pid):
            if pid != 4242:
                return []
            if reuse_before_charge:
                state["parent_start"] = 222
            if hide_parent:
                state["parent_visible"] = False
            return [5000]

        def task(_system, pid):
            if pid == 5000:
                child_tasks.append(state["parent_start"])
                if reuse_during_task:
                    state["parent_start"] = 222
            return {
                "accepted": True,
                "kr": 0,
                "count": 12,
                "resident_size_max": 100,
                "released": [pid],
            }

        monkeypatch.setattr(accounting, "_darwin_rusage", rusage)
        monkeypatch.setattr(accounting, "_darwin_ppid", ppid)
        monkeypatch.setattr(accounting, "_darwin_children", children)
        monkeypatch.setattr(accounting, "_darwin_task_rss", task)
        backend = accounting.DarwinBackend(["worker"], cwd=None, env=None)
        backend.process = _RootProcess(4242)
        backend.root_creation = 111
        backend._libproc = object()
        backend._libsystem = object()
        backend._timebase = (1, 1)
        backend.sample(backend.ledger)
        identities = [row["identity"] for row in backend.ledger.public()]
        return identities, child_tasks, backend.root_creation

    reused, reused_tasks, reused_creation = run(reuse_before_charge=True)
    assert reused == ["4242:111"]
    assert reused_tasks == []
    assert reused_creation == 111

    during, during_tasks, during_creation = run(reuse_during_task=True)
    assert during == ["4242:111"]
    assert during_tasks == [111]
    assert during_creation == 111

    missing, missing_tasks, missing_creation = run(hide_parent=True)
    assert missing == ["4242:111"]
    assert missing_tasks == []
    assert missing_creation == 111

    stable, stable_tasks, stable_creation = run()
    assert stable == ["4242:111", "5000:333"]
    assert stable_tasks == [111]
    assert stable_creation == 111


def _darwin_observation_report():
    return {
        "qualification": "unqualified",
        "resource_acceptance": False,
        "budget": {
            "additional_rss_bytes_per_process": ADDITIONAL_RSS_BUDGET_BYTES,
            "cpu_one_core_fraction": CPU_BUDGET_ONE_CORE_FRACTION,
            "status": "UNACCEPTED",
            "compared": False,
        },
        "missing_recorded_as_zero": False,
        "coverage": {
            "status": "partial",
            "cpu_lifetime_complete": False,
            "cpu_includes_exited_descendants": False,
            "sampled_pid_cpu_is_complete": False,
            "cgroup_memory_peak_is_per_process_rss": False,
        },
        "cold_start": {"subtracted": False, "processes": []},
        "idle_or_settlement_included_in_active_cpu": False,
        "phases": [{"name": "descendant-observation", "active": False}],
        "cleanup": {"ok": True, "failure": None, "retried": False},
        "ledger": [],
    }


def test_hold_fifo_closes_the_read_fd_when_the_write_open_raises(monkeypatch):
    import deploy.owned_launch_self_check as self_check

    closed = []
    monkeypatch.setattr(self_check.os, "O_NONBLOCK", 0x800, raising=False)
    monkeypatch.setattr(self_check.os, "mkfifo", lambda _path, _mode: None, raising=False)
    monkeypatch.setattr(self_check.os, "close", lambda fd: closed.append(fd))

    def fail_write(_path, flags):
        if flags & self_check.os.O_WRONLY:
            raise OSError("write open failed")
        return 19

    monkeypatch.setattr(self_check.os, "open", fail_write)
    with pytest.raises(OSError, match="write open failed"):
        self_check._hold_fifo(Path("descendant-ready"))
    assert closed == [19]

    closed.clear()

    def both(_path, flags):
        if flags & self_check.os.O_WRONLY:
            return 23
        return 19

    monkeypatch.setattr(self_check.os, "open", both)
    assert self_check._hold_fifo(Path("descendant-ready")) == (19, 23)
    assert closed == []


def test_observe_darwin_descendant_requires_a_zero_fixture_exit(monkeypatch):
    import deploy.owned_launch_self_check as self_check

    closed = []
    finished = []

    def run(returncode):
        closed.clear()
        finished.clear()
        monkeypatch.setattr(self_check.os, "O_NONBLOCK", 0x800, raising=False)
        monkeypatch.setattr(self_check.os, "mkfifo", lambda _path, _mode: None, raising=False)
        monkeypatch.setattr(self_check.os, "close", lambda fd: closed.append(fd))
        opened = iter((19, 23, 31, 37))
        monkeypatch.setattr(self_check.os, "open", lambda _path, _flags: next(opened))
        monkeypatch.setattr(
            self_check.select,
            "select",
            lambda reads, _writes, _errors, _timeout: (list(reads), [], []),
        )
        monkeypatch.setattr(self_check.os, "read", lambda fd, _size: b"1" if fd == 19 else b"")
        monkeypatch.setattr(
            self_check.os,
            "write",
            lambda fd, data: 1 if fd == 37 and data == b"1" else 0,
        )

        class Process:
            pid = 4242

            def __init__(self):
                self.returncode = returncode

        class Ledger:
            def public(self):
                return [{"pid": 4242}, {"pid": 5000}]

        class Backend:
            def __init__(self):
                self.process = Process()
                self.ledger = Ledger()

            def sample(self, ledger):
                assert ledger is self.ledger

        class Launch:
            def __init__(self):
                self.backend = Backend()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def mark_phase(self, name, *, canonical_operations_completed, active):
                assert name == "descendant-observation"
                assert canonical_operations_completed == 0
                assert active is False

            def wait_root(self, timeout):
                assert timeout == 10
                return True

            def finish(self, *, canonical_operations_completed):
                assert canonical_operations_completed == 0
                finished.append(self.backend.process.returncode)
                return _darwin_observation_report()

        monkeypatch.setattr(self_check, "start_owned_launch", lambda *_args, **_kwargs: Launch())
        return self_check._observe_darwin_descendant(
            Path("worker.py"),
            Path("descendant-ready"),
            Path("descendant-ack"),
        )

    with pytest.raises(AssertionError, match="root failed"):
        run(7)
    assert finished == [7]
    assert closed == [19, 23, 31, 37]
    assert run(0) == (True, 1)
    assert finished == [0]
    assert closed == [19, 23, 31, 37]
    from deploy.owned_launch_self_check import _WORKER, _darwin_live_descendant_receipt

    compile(_WORKER, "<owned-worker>", "exec")
    assert 'mode == "hold"' in _WORKER
    assert 'mode == "wait"' in _WORKER
    assert 'mode == "work"' in _WORKER
    assert 'mode == "sleep"' in _WORKER
    assert _darwin_live_descendant_receipt([{"pid": 10}, {"pid": 11}], 10) == (True, 1)
    assert _darwin_live_descendant_receipt(
        [{"pid": 10}, {"pid": 11}, {"pid": 12}],
        10,
    ) == (True, 2)
    with pytest.raises(AssertionError, match="not observed"):
        _darwin_live_descendant_receipt([{"pid": 10}], 10)
    with pytest.raises(AssertionError, match="missing"):
        _darwin_live_descendant_receipt([], 1)
    with pytest.raises(AssertionError, match="malformed"):
        _darwin_live_descendant_receipt([{"pid": 10}, {"pid": 0}], 10)
    with pytest.raises(AssertionError, match="malformed"):
        _darwin_live_descendant_receipt([{"pid": 10}, {"pid": 10}], 10)
    with pytest.raises(AssertionError, match="malformed"):
        _darwin_live_descendant_receipt([{"pid": True}], 10)


def test_two_mac_workflow_fails_when_the_descendant_invariant_fails():
    text = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "native-residency-counters.yml"
    ).read_text(encoding="utf-8")
    assert text.count("os: macos-26") == 1
    assert text.count("os: macos-15-intel") == 1
    assert "source_not_exact" in text
    assert "arch_mismatch" in text
    assert "from deploy.darwin_residency_receipt import main" in text
    assert "darwin_live_descendant_observed" in text
    assert "darwin_live_descendant_count" in text
    assert "descendant_not_observed" in text
    assert "Not owned-launch" not in text


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


class _TaskPort:
    def __init__(
        self,
        *,
        name_kr=0,
        port=77,
        info_kr=0,
        count=12,
        peak=9_371_648,
        boom=False,
        dealloc_kr=0,
        dealloc_error=None,
    ):
        self.name_kr = name_kr
        self.port = port
        self.info_kr = info_kr
        self.count = count
        self.peak = peak
        self.boom = boom
        self.dealloc_kr = dealloc_kr
        self.dealloc_error = dealloc_error
        self.deallocated = []
        self.self_port = 42

    def mach_task_self(self):
        return self.self_port

    def task_name_for_pid(self, task, pid, port):
        assert task == self.self_port
        assert pid > 0
        port._obj.value = self.port
        return self.name_kr

    def task_info(self, task, flavor, info, count):
        assert task == self.port
        assert flavor == 20
        if self.boom:
            raise OSError("task_info failed")
        count._obj.value = self.count
        if self.info_kr == 0 and self.count == 12:
            info._obj.resident_size = 1_000
            info._obj.resident_size_max = self.peak
        return self.info_kr

    def mach_port_deallocate(self, task, name):
        assert task == self.self_port
        self.deallocated.append(int(name))
        if self.dealloc_error is not None:
            raise OSError(self.dealloc_error)
        return self.dealloc_kr


def _resident(start, resident=40):
    return {
        "user": 1,
        "system": 1,
        "child_user": 0,
        "child_system": 0,
        "resident": resident,
        "start": start,
    }


def test_darwin_task_port_release_covers_success_denial_partial_and_exceptions():
    import deploy.owned_launch_accounting as accounting

    assert ctypes.sizeof(accounting._MachTaskBasicInfo) == 48
    text = Path("deploy/owned_launch_accounting.py").read_text(encoding="utf-8")
    assert "task_name_for_pid" in text
    assert "task_for_pid(" not in text
    assert "mach_vm_read" not in text

    success = _TaskPort()
    result = accounting._darwin_task_rss(success, 4242)
    assert result["accepted"] is True
    assert result["kr"] == 0
    assert result["count"] == 12
    assert result["resident_size_max"] == 9_371_648
    assert result["released"] == [77]
    assert success.deallocated == [77]

    denied = _TaskPort(name_kr=5, port=0)
    denied_result = accounting._darwin_task_rss(denied, 4242)
    assert denied_result["accepted"] is False
    assert denied_result["kr"] == 5
    assert denied_result["resident_size_max"] is None
    assert denied_result["released"] == []
    assert denied.deallocated == []

    stray = _TaskPort(name_kr=5, port=55)
    stray_result = accounting._darwin_task_rss(stray, 4242)
    assert stray_result["accepted"] is False
    assert stray_result["resident_size_max"] is None
    assert stray_result["released"] == [55]
    assert stray.deallocated == [55]

    dead = _TaskPort(info_kr=268435459, count=12)
    dead_result = accounting._darwin_task_rss(dead, 4242)
    assert dead_result["accepted"] is False
    assert dead_result["kr"] == 268435459
    assert dead_result["count"] == 12
    assert dead_result["resident_size_max"] is None
    assert dead.deallocated == [77]

    partial = _TaskPort(info_kr=0, count=11, peak=5)
    partial_result = accounting._darwin_task_rss(partial, 4242)
    assert partial_result["accepted"] is False
    assert partial_result["count"] == 11
    assert partial_result["resident_size_max"] is None
    assert partial.deallocated == [77]

    exploded = _TaskPort(boom=True)
    exploded_result = accounting._darwin_task_rss(exploded, 4242)
    assert exploded_result["accepted"] is False
    assert exploded_result["resident_size_max"] is None
    assert exploded.deallocated == [77]


def test_darwin_failed_port_release_is_not_cleanup_success(monkeypatch):
    import deploy.owned_launch_accounting as accounting

    reviewed = _TaskPort(port=65, peak=200, dealloc_kr=5)
    reviewed.self_port = 99
    reviewed_result = accounting._darwin_task_rss(reviewed, 4242)
    assert reviewed.deallocated == [65]
    assert reviewed_result["accepted"] is True
    assert reviewed_result["kr"] == 0
    assert reviewed_result["count"] == 12
    assert reviewed_result["resident_size_max"] == 200
    assert reviewed_result["released"] == []
    assert reviewed_result["port_deallocate_kern_return"] == 5
    assert reviewed_result["port_deallocate_error"] == "port_release_failed"

    denied = _TaskPort(info_kr=5, port=65, peak=0, dealloc_kr=5)
    denied_result = accounting._darwin_task_rss(denied, 4242)
    assert denied_result["accepted"] is False
    assert denied_result["resident_size_max"] is None
    assert denied_result["released"] == []
    assert denied_result["port_deallocate_kern_return"] == 5
    assert denied.deallocated == [65]

    partial = _TaskPort(info_kr=0, count=11, peak=0, dealloc_kr=5)
    partial_result = accounting._darwin_task_rss(partial, 4242)
    assert partial_result["accepted"] is False
    assert partial_result["count"] == 11
    assert partial_result["resident_size_max"] is None
    assert partial_result["released"] == []
    assert partial.deallocated == [77]

    leaked = "mach_port_deallocate " + ("x" * 180)
    raised = _TaskPort(port=65, peak=200, dealloc_error=leaked)
    raised_result = accounting._darwin_task_rss(raised, 4242)
    assert raised.deallocated == [65]
    assert raised_result["accepted"] is True
    assert raised_result["resident_size_max"] == 200
    assert raised_result["released"] == []
    assert raised_result["port_deallocate_kern_return"] is None
    assert raised_result["port_deallocate_error"] == "port_release_failed"
    assert leaked not in str(raised_result["port_deallocate_error"])

    exploded = _TaskPort(boom=True, dealloc_error=leaked)
    exploded_result = accounting._darwin_task_rss(exploded, 4242)
    assert exploded.deallocated == [77]
    assert exploded_result["accepted"] is False
    assert exploded_result["resident_size_max"] is None
    assert exploded_result["released"] == []
    assert exploded_result["port_deallocate_error"] == "port_release_failed"

    kills = []
    monkeypatch.setattr(accounting.os, "kill", lambda pid, sig: kills.append((pid, sig)))
    monkeypatch.setattr(accounting, "_darwin_rusage", lambda _library, _pid: _resident(111, 40))
    monkeypatch.setattr(accounting, "_darwin_children", lambda _library, _pid: [])
    monkeypatch.setattr(accounting, "_darwin_group_pids", lambda _library, _pgid: [])

    def backend_for(system):
        backend = accounting.DarwinBackend(["worker"], cwd=None, env=None)
        backend.process = _RootProcess(4242)
        backend.root_creation = 111
        backend._libproc = object()
        backend._libsystem = system
        backend._timebase = (1, 1)
        backend.sample(backend.ledger)
        backend._reaped = True
        backend._waited = 750_000
        return backend

    owned_port = _TaskPort(port=65, peak=200, dealloc_kr=5)
    owned_port.self_port = 99
    owned = backend_for(owned_port)
    owned.sample = lambda _ledger: None
    launch = accounting.OwnedLaunch(owned, bound_seconds=5, sample_seconds=0.02)
    report = launch.finish(canonical_operations_completed=0)
    row = report["ledger"][0]
    assert row["identity"] == "4242:111"
    assert row["last_working_set_bytes"] == 40
    assert row["peak_working_set_bytes"] == 200
    assert row["kernel_high_water_while_observed"] is True
    assert row["peak_working_set_final"] is False
    assert report["coverage"]["status"] == "partial"
    assert report["coverage"]["rss_high_water"] == "live_kernel_high_water"
    assert report["coverage"]["rss_high_water_covers_unseen_exited_processes"] is False
    assert "darwin_final_lifetime_rss" in report["unavailable_counters"]
    assert report["cleanup"]["ok"] is False
    assert report["cleanup"]["failure"] == "port_release_failed"
    assert report["cleanup"]["retried"] is False
    assert report["resource_acceptance"] is False
    assert report["lifetime_cpu_microseconds"] == 750_000
    assert owned.close() == (False, "port_release_failed")
    assert kills == []
    assert owned_port.deallocated == [65]
    assert leaked not in json.dumps(report)

    denied_port = _TaskPort(info_kr=5, port=66, peak=0, dealloc_kr=5)
    denied_backend = backend_for(denied_port)
    denied_row = denied_backend.ledger.public()[0]
    assert denied_row["last_working_set_bytes"] == 40
    assert denied_row["peak_working_set_bytes"] is None
    assert denied_row["kernel_high_water_while_observed"] is False
    assert denied_row["peak_working_set_final"] is False
    denied_coverage = denied_backend.coverage(
        denied_backend.snapshot(), denied_backend.ledger.public()
    )
    assert denied_coverage["status"] == "partial"
    assert denied_coverage["rss_high_water"] == "sampled_current"
    assert denied_coverage["rss_high_water_covers_unseen_exited_processes"] is False
    assert denied_backend.close() == (False, "port_release_failed")
    assert denied_backend.close() == (False, "port_release_failed")
    assert denied_port.deallocated == [66]
    assert kills == []

    raised_port = _TaskPort(port=67, peak=200, dealloc_error=leaked)
    raised_backend = backend_for(raised_port)
    raised_row = raised_backend.ledger.public()[0]
    assert raised_row["peak_working_set_bytes"] == 200
    assert raised_row["peak_working_set_final"] is False
    assert raised_backend.close() == (False, "port_release_failed")
    assert raised_backend.close() == (False, "port_release_failed")
    assert raised_port.deallocated == [67]
    assert kills == []


def test_darwin_cpu_read_keeps_wait4_and_rejects_a_reaped_reused_pid(monkeypatch):
    import deploy.owned_launch_accounting as accounting

    def make(creation=111):
        backend = accounting.DarwinBackend(["worker"], cwd=None, env=None)
        backend.process = _RootProcess(4242)
        backend.root_creation = creation
        backend._libproc = object()
        backend._timebase = (1, 1)
        return backend

    def counter(start):
        return {
            "user": 9_000_000,
            "system": 0,
            "child_user": 0,
            "child_system": 0,
            "resident": 1,
            "start": start,
        }

    raced = make()
    calls = []

    def race_rusage(_library, pid):
        assert raced._sample_lock.locked()
        calls.append(pid)
        raced._reaped = True
        return counter(222)

    monkeypatch.setattr(accounting, "_darwin_rusage", race_rusage)
    assert raced.cpu_microseconds() is None
    assert raced.cpu_microseconds() is None
    assert calls == [4242]
    assert raced.root_creation == 111
    assert raced._waited is None

    preserved = make()

    def preserve_rusage(_library, _pid):
        assert preserved._sample_lock.locked()
        preserved._reaped = True
        preserved._waited = 750_000
        return counter(222)

    monkeypatch.setattr(accounting, "_darwin_rusage", preserve_rusage)
    assert preserved.cpu_microseconds() == 750_000
    assert preserved.root_creation == 111

    unfrozen = make(None)

    def late_rusage(_library, _pid):
        unfrozen._reaped = True
        return counter(222)

    monkeypatch.setattr(accounting, "_darwin_rusage", late_rusage)
    assert unfrozen.cpu_microseconds() is None
    assert unfrozen.root_creation is None

    mismatched = make()
    monkeypatch.setattr(accounting, "_darwin_rusage", lambda _library, _pid: counter(222))
    assert mismatched.cpu_microseconds() is None
    assert mismatched._reaped is False
    assert mismatched.root_creation == 111

    matched = make()
    monkeypatch.setattr(accounting, "_darwin_rusage", lambda _library, _pid: counter(111))
    assert matched.cpu_microseconds() == 9_000
    assert matched.root_creation == 111

    reaped = make()
    reaped._reaped = True
    reaped._waited = None

    def rusage_after_reap(*_args):
        raise AssertionError("rusage after reap")

    monkeypatch.setattr(accounting, "_darwin_rusage", rusage_after_reap)
    assert reaped.cpu_microseconds() is None
    reaped._waited = 0
    assert reaped.cpu_microseconds() == 0


def test_darwin_reaped_root_without_creation_does_not_freeze_a_later_pid(monkeypatch):
    import deploy.owned_launch_accounting as accounting

    def refuse(*_args):
        raise AssertionError("must not query a later pid")

    monkeypatch.setattr(accounting, "_darwin_rusage", refuse)
    monkeypatch.setattr(accounting, "_darwin_task_rss", refuse)
    monkeypatch.setattr(accounting, "_darwin_children", refuse)
    backend = accounting.DarwinBackend(["worker"], cwd=None, env=None)
    backend.process = _RootProcess(4242)
    backend._reaped = True
    backend.root_creation = None
    backend._libproc = object()
    backend.sample(backend.ledger)
    assert backend.root_creation is None
    assert backend.ledger.public() == []


def test_darwin_pid_reuse_between_checks_adds_no_memory(monkeypatch):
    import deploy.owned_launch_accounting as accounting

    phase = {"start": 111}

    monkeypatch.setattr(
        accounting,
        "_darwin_rusage",
        lambda _library, _pid: _resident(phase["start"], 40),
    )
    monkeypatch.setattr(accounting, "_darwin_children", lambda _library, _pid: [])

    def task(_system, _pid):
        phase["start"] = 999
        return {
            "accepted": True,
            "kr": 0,
            "count": 12,
            "resident_size_max": 12_345,
            "released": [7],
        }

    monkeypatch.setattr(accounting, "_darwin_task_rss", task)
    backend = accounting.DarwinBackend(["worker"], cwd=None, env=None)
    backend.process = _RootProcess(4242)
    backend.root_creation = 111
    backend._libproc = object()
    backend._libsystem = False
    backend.sample(backend.ledger)
    assert backend.root_creation == 111
    assert backend.ledger.public() == []


def test_darwin_denied_and_partial_task_info_keep_current_without_a_zero_peak(monkeypatch):
    import deploy.owned_launch_accounting as accounting

    real_task_rss = accounting._darwin_task_rss
    monkeypatch.setattr(accounting, "_darwin_rusage", lambda _library, _pid: _resident(111, 40))
    monkeypatch.setattr(accounting, "_darwin_children", lambda _library, _pid: [])
    monkeypatch.setattr(
        accounting,
        "_darwin_task_rss",
        lambda _system, _pid: {
            "accepted": False,
            "kr": 5,
            "count": None,
            "resident_size_max": 0,
            "released": [],
        },
    )
    backend = accounting.DarwinBackend(["worker"], cwd=None, env=None)
    backend.process = _RootProcess(4242)
    backend.root_creation = 111
    backend._libproc = object()
    backend._libsystem = False
    backend._timebase = (1, 1)
    backend.sample(backend.ledger)
    row = backend.ledger.public()[0]
    assert row["identity"] == "4242:111"
    assert row["last_working_set_bytes"] == 40
    assert row["peak_working_set_bytes"] is None
    assert row["kernel_high_water_while_observed"] is False
    assert row["peak_working_set_final"] is False
    coverage = backend.coverage(backend.snapshot(), backend.ledger.public())
    assert coverage["status"] == "partial"
    assert coverage["rss_high_water"] == "sampled_current"
    assert coverage["rss_high_water_covers_unseen_exited_processes"] is False

    calls = []

    def partial(_system, pid):
        calls.append(pid)
        return real_task_rss(_TaskPort(info_kr=0, count=11, peak=0), pid)

    monkeypatch.setattr(accounting, "_darwin_task_rss", partial)
    other = accounting.DarwinBackend(["worker"], cwd=None, env=None)
    other.process = _RootProcess(4242)
    other.root_creation = 111
    other._libproc = object()
    other._libsystem = False
    other.sample(other.ledger)
    assert calls == [4242]
    partial_row = other.ledger.public()[0]
    assert partial_row["last_working_set_bytes"] == 40
    assert partial_row["peak_working_set_bytes"] is None
    assert partial_row["peak_working_set_final"] is False


def test_darwin_live_kernel_peak_stays_current_rss_and_not_final(monkeypatch):
    import deploy.owned_launch_accounting as accounting

    monkeypatch.setattr(accounting, "_darwin_rusage", lambda _library, _pid: _resident(111, 100))
    monkeypatch.setattr(accounting, "_darwin_children", lambda _library, _pid: [])
    monkeypatch.setattr(
        accounting,
        "_darwin_task_rss",
        lambda _system, _pid: {
            "accepted": True,
            "kr": 0,
            "count": 12,
            "resident_size_max": 9_371_648,
            "released": [77],
        },
    )
    backend = accounting.DarwinBackend(["worker"], cwd=None, env=None)
    backend.process = _RootProcess(4242)
    backend.root_creation = 111
    backend._libproc = object()
    backend._libsystem = False
    backend._timebase = (1, 1)
    backend.sample(backend.ledger)
    row = backend.ledger.public()[0]
    assert row["last_working_set_bytes"] == 100
    assert row["peak_working_set_bytes"] == 9_371_648
    assert row["kernel_high_water_while_observed"] is True
    assert row["peak_working_set_final"] is False
    snapshot = backend.snapshot()
    assert snapshot["kernel"]["footprint_used_as_rss"] is False
    assert snapshot["kernel"]["rss_high_water_is_final_lifetime"] is False
    assert snapshot["kernel"]["orphans_outside_wait4"] is True
    assert "darwin_rss_high_water" not in snapshot["unavailable"]
    assert "darwin_unreaped_descendant_cpu" in snapshot["unavailable"]
    assert "darwin_orphan_cpu" in snapshot["unavailable"]
    assert "darwin_final_lifetime_rss" in snapshot["unavailable"]
    coverage = backend.coverage(snapshot, backend.ledger.public())
    assert coverage["status"] == "partial"
    assert coverage["rss_high_water"] == "live_kernel_high_water"
    assert coverage["rss_high_water_covers_unseen_exited_processes"] is False
    assert coverage["cpu_lifetime_complete"] is False
    partial_rows = backend.ledger.public() + [
        {
            "first_working_set_bytes": 10,
            "peak_working_set_bytes": None,
            "kernel_high_water_while_observed": False,
            "peak_working_set_final": False,
        }
    ]
    partial = backend.coverage(snapshot, partial_rows)
    assert partial["status"] == "partial"
    assert partial["rss_high_water"] == "live_kernel_high_water_partial"
    assert partial["rss_high_water_covers_unseen_exited_processes"] is False


def test_darwin_reparented_descendant_does_not_contribute_memory(monkeypatch):
    import deploy.owned_launch_accounting as accounting

    parent_of = {5555: 4242}

    def rusage(_library, pid):
        if pid == 4242:
            return _resident(111, 20)
        if pid == 5555:
            return _resident(222, 30)
        return None

    def ppid(_library, pid):
        return parent_of.get(pid)

    def children(_library, pid):
        return [5555] if pid == 4242 else []

    def task(_system, pid):
        if pid == 5555:
            parent_of[5555] = 1
        return {
            "accepted": True,
            "kr": 0,
            "count": 12,
            "resident_size_max": 8_000,
            "released": [pid],
        }

    monkeypatch.setattr(accounting, "_darwin_rusage", rusage)
    monkeypatch.setattr(accounting, "_darwin_ppid", ppid)
    monkeypatch.setattr(accounting, "_darwin_children", children)
    monkeypatch.setattr(accounting, "_darwin_task_rss", task)
    backend = accounting.DarwinBackend(["worker"], cwd=None, env=None)
    backend.process = _RootProcess(4242)
    backend.root_creation = 111
    backend._libproc = object()
    backend._libsystem = False
    backend._timebase = (1, 1)
    backend.sample(backend.ledger)
    rows = backend.ledger.public()
    assert [row["identity"] for row in rows] == ["4242:111"]
    assert rows[0]["peak_working_set_bytes"] == 8_000
    assert rows[0]["last_working_set_bytes"] == 20
    assert rows[0]["peak_working_set_final"] is False
    coverage = backend.coverage(backend.snapshot(), rows)
    assert coverage["rss_high_water"] == "live_kernel_high_water"
    assert coverage["rss_high_water_covers_unseen_exited_processes"] is False


def test_darwin_self_check_requires_a_positive_live_peak_and_not_final_coverage():
    from deploy.owned_launch_self_check import _darwin_kernel_peak_receipt

    report = {
        "coverage": {
            "status": "partial",
            "rss_high_water": "live_kernel_high_water",
            "rss_high_water_covers_unseen_exited_processes": False,
        },
        "ledger": [
            {
                "peak_working_set_bytes": 9_371_648,
                "kernel_high_water_while_observed": True,
                "peak_working_set_final": False,
            }
        ],
        "unavailable_counters": [
            "darwin_unreaped_descendant_cpu",
            "darwin_orphan_cpu",
            "darwin_final_lifetime_rss",
        ],
        "kernel": {
            "footprint_used_as_rss": False,
            "rss_high_water_is_final_lifetime": False,
        },
        "cleanup": {"ok": True, "failure": None},
    }
    assert _darwin_kernel_peak_receipt(report) == (
        9_371_648,
        False,
        "live_kernel_high_water",
        False,
    )
    final = {
        "coverage": report["coverage"],
        "ledger": [dict(report["ledger"][0], peak_working_set_final=True)],
        "unavailable_counters": report["unavailable_counters"],
        "kernel": report["kernel"],
    }
    with pytest.raises(AssertionError, match="marked final"):
        _darwin_kernel_peak_receipt(final)
    missing = {
        "coverage": dict(report["coverage"], rss_high_water="sampled_current"),
        "ledger": [
            {
                "peak_working_set_bytes": None,
                "kernel_high_water_while_observed": False,
                "peak_working_set_final": False,
            }
        ],
        "unavailable_counters": report["unavailable_counters"],
        "kernel": report["kernel"],
    }
    with pytest.raises(AssertionError, match="not retained"):
        _darwin_kernel_peak_receipt(missing)


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
    monkeypatch.setattr(
        accounting, "_signal_cgroup", lambda _leaf: signaled.append(_leaf) or (True, None)
    )
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
        json.dumps(
            {"stage": "startup-error", "failure_category": secret, "error": f"C:\\Users\\{secret}"}
        ),
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


class _JobApi:
    """Scripted job queries. Handles are plain integers, not kernel objects."""

    def __init__(self):
        self.calls = []
        self.closed = []
        self.opened = []
        self.job = 11
        self.process = 22
        self.thread = 33
        self.root_pid = 100
        self.query_for_root = 50
        self.next_handle = 70
        self.members = [100]
        self.creation = {22: 1000}
        self.live = {}
        self.in_job = {}
        self.memory = {}
        self.pid_creation = {}
        self.pid_memory = {}
        self.pid_member = {}
        self.pid_live = {}
        self.handle_for_pid = {}
        self.fail_open = set()
        self.duplicate_fail = False
        self.duplicate_creation = None
        self.resume_result = 1
        self.active = 1
        self.total = 1
        self.user = 50_000
        self.kernel_time = 10_000
        self.extended_ok = True
        self.list_fail = False
        self.pid_list_truncated = False
        self.close_fail = set()
        self.terminate_jobs = []
        self.terminate_processes = []

    def create_job(self):
        self.calls.append("create_job")
        return self.job

    def set_kill_on_close(self, job):
        self.calls.append(("kill_on_close", job))

    def create_suspended_in_job(self, job, argv, cwd, env):
        self.calls.append("create")
        self.creation[self.process] = 1000
        return self.process, self.thread, self.root_pid

    def creation_ticks(self, process):
        return self.creation.get(process)

    def is_in_job(self, process, job):
        self.calls.append(("in_job", process, job))
        if process in self.in_job:
            return self.in_job[process]
        return True

    def duplicate_query(self, process):
        self.calls.append(("duplicate", process))
        if self.duplicate_fail:
            return None
        handle = self.query_for_root
        copied = (
            self.creation.get(process)
            if self.duplicate_creation is None
            else self.duplicate_creation
        )
        self.creation[handle] = copied
        self.live[handle] = True
        self.in_job.setdefault(handle, True)
        self.memory.setdefault(handle, {"working_set": 11087872, "peak_working_set": 11087872})
        return handle

    def open_query(self, pid):
        self.opened.append(pid)
        if pid in self.fail_open:
            return None
        handle = self.next_handle
        self.next_handle += 1
        self.creation[handle] = self.pid_creation.get(pid, 1)
        self.live[handle] = self.pid_live.get(pid, True)
        self.in_job[handle] = self.pid_member.get(pid, True)
        raw = self.pid_memory.get(pid, {"working_set": 100, "peak_working_set": 100})
        self.memory[handle] = None if raw is None else dict(raw)
        self.handle_for_pid.setdefault(pid, []).append(handle)
        return handle

    def process_is_live(self, process):
        return self.live.get(process, True)

    def working_set(self, process):
        self.calls.append(("memory", process))
        value = self.memory.get(process)
        return None if value is None else dict(value)

    def resume(self, thread):
        self.calls.append(("resume", thread))
        return self.resume_result

    def job_pids(self, job):
        if self.list_fail:
            return None
        return list(self.members)

    def accounting(self, job):
        if self.user is None:
            return None
        return {
            "user_100ns": self.user,
            "kernel_100ns": self.kernel_time,
            "total_processes": self.total,
            "active_processes": self.active,
            "terminated_by_limit": 0,
        }

    def extended(self, job):
        if not self.extended_ok:
            return None
        return {"peak_process": 10, "peak_job": 20}

    def close(self, handle):
        self.closed.append(handle)
        if handle in self.close_fail:
            return False, "close_6"
        return True, None

    def terminate_process(self, process):
        self.terminate_processes.append(process)

    def terminate_job(self, job):
        self.terminate_jobs.append(job)
        return True, None

    def wait(self, process, timeout_seconds):
        self.calls.append(("wait_root", process, timeout_seconds))
        return True


def _windows(api):
    import deploy.owned_launch_accounting as accounting

    backend = accounting.WindowsJobBackend.__new__(accounting.WindowsJobBackend)
    backend.argv = ["worker"]
    backend.cwd = None
    backend.env = None
    backend.ledger = accounting._Ledger()
    backend.job = None
    backend.process = None
    backend.thread = None
    backend.root_pid = None
    backend.root_creation = None
    backend._api = api
    backend._sampled_sum_peak = None
    backend._closed = False
    backend._close_result = (True, None)
    backend._lock = __import__("threading").Lock()
    backend._retained = {}
    backend._live_pid = {}
    backend._gaps = {
        "query_handle_unavailable_observations": 0,
        "membership_rejected": 0,
        "identity_or_membership_unproven": 0,
        "final_query_failed": 0,
        "pid_list_unreadable": False,
    }
    return backend


def _row(backend, identity):
    return next(row for row in backend.ledger.public() if row["identity"] == identity)


def test_windows_query_handles_keep_limited_information_rights():
    import deploy.owned_launch_accounting as accounting

    api = accounting._WinApi.__new__(accounting._WinApi)
    seen = []

    class Kernel:
        def OpenProcess(self, access, inherit, pid):
            seen.append(("open", access, inherit, pid))
            return 9

        def GetCurrentProcess(self):
            return -1

        def DuplicateHandle(
            self, source_process, source, target_process, out, access, inherit, options
        ):
            seen.append(("dup", access, inherit, options))
            out._obj.value = 12
            return 1

        def IsProcessInJob(self, process, job, result):
            seen.append(("member", process, job))
            result._obj.value = 0
            return 1

        def GetExitCodeProcess(self, process, code):
            code._obj.value = accounting._STILL_ACTIVE
            return 1

    api.kernel = Kernel()
    assert api.open_query(41) == 9
    assert api.duplicate_query(22) == 12
    assert api.is_in_job(22, 11) is False
    assert api.process_is_live(22) is True
    assert seen[0] == ("open", 0x1000, False, 41)
    assert seen[1][0] == "dup"
    assert seen[1][1:] == (0x1000, False, 0)
    assert 0x1F0FFF not in [item[1] for item in seen if item[0] in ("open", "dup")]


def test_windows_retained_handle_is_reused_and_final_peak_can_grow():
    """The held-handle probe saw each final peak 12288 bytes above its live peak."""
    import deploy.owned_launch_accounting as accounting

    api = _JobApi()
    api.total = 3
    api.members = [api.root_pid]
    backend = _windows(api)
    backend.spawn()
    assert ("resume", api.thread) in api.calls
    assert api.calls.index(("duplicate", api.process)) < api.calls.index(("resume", api.thread))
    assert api.root_pid not in api.opened
    assert "100:1000" in backend._retained
    api.members = [api.root_pid, 200]
    api.pid_creation[200] = 2000
    api.pid_memory[200] = {"working_set": 19546112, "peak_working_set": 19546112}
    backend.sample(backend.ledger)
    backend.sample(backend.ledger)
    assert api.opened == [200]
    assert len(backend._retained) == 2
    root = _row(backend, "100:1000")
    child = _row(backend, "200:2000")
    assert root["peak_working_set_bytes"] == 11087872
    assert root["last_working_set_bytes"] == 11087872
    assert root["kernel_high_water_while_observed"] is True
    assert root["peak_working_set_final"] is False
    assert child["kernel_high_water_while_observed"] is True
    assert child["peak_working_set_final"] is False
    for handle in list(backend._retained.values()):
        api.live[handle.handle] = False
    api.memory[50] = {"working_set": 32768, "peak_working_set": 11100160}
    child_handle = api.handle_for_pid[200][0]
    api.memory[child_handle] = {"working_set": 32768, "peak_working_set": 19558400}
    api.fail_open.update({api.root_pid, 200})
    api.active = 0
    opened_before_finish = list(api.opened)
    launch = accounting.OwnedLaunch(backend, bound_seconds=5, sample_seconds=0.05)
    try:
        report = launch.finish()
    except Exception:
        if not launch._finished:
            launch.finish()
        raise
    assert opened_before_finish == [200]
    assert [row["identity"] for row in report["ledger"]] == ["100:1000", "200:2000"]
    finished_root = _row(backend, "100:1000")
    finished_child = _row(backend, "200:2000")
    assert finished_root["peak_working_set_bytes"] == 11100160
    assert finished_root["last_working_set_bytes"] == 11087872
    assert finished_root["peak_working_set_final"] is True
    assert finished_root["kernel_high_water_while_observed"] is True
    assert finished_child["peak_working_set_bytes"] == 19558400
    assert finished_child["last_working_set_bytes"] == 19546112
    assert finished_child["peak_working_set_final"] is True
    assert report["identities_missing"] == 1
    assert report["kernel"]["peak_job_commit_bytes"] == 20
    assert report["kernel"]["commit_counters_are_working_set"] is False
    assert report["kernel"]["active_processes"] == 0
    assert report["coverage"]["cpu_lifetime_complete"] is True
    assert report["coverage"]["status"] == "partial"
    assert report["coverage"]["working_set_accounting"] == "final_on_observed_handles"
    assert report["coverage"]["retained_handles_cover_unseen_processes"] is False
    assert report["coverage"]["rss_high_water_covers_unseen_exited_processes"] is False
    assert "final_working_set_peak" not in report["unavailable_counters"]
    assert "unseen_or_unsampled_process_working_set" in report["unavailable_counters"]
    assert report["resource_acceptance"] is False
    assert report["budget"]["status"] == "UNACCEPTED"
    assert report["budget"]["compared"] is False
    assert report["budget"]["additional_rss_bytes_per_process"] == 8_388_608
    handles = [50, child_handle, api.thread, api.process, api.job]
    assert api.closed == handles
    again = backend.close()
    assert again == (True, None)
    assert api.closed == handles


def test_windows_pid_outside_this_job_is_not_admitted():
    api = _JobApi()
    backend = _windows(api)
    backend.job = api.job
    api.members = [300]
    api.pid_member[300] = False
    api.pid_creation[300] = 3000
    api.total = 1
    api.active = 0
    backend.sample(backend.ledger)
    assert backend.ledger.public() == []
    assert api.opened == [300]
    rejected = api.handle_for_pid[300][0]
    assert api.closed == [rejected]
    assert backend._retained == {}
    snap = backend.snapshot()
    assert snap["identities_missing"] == 1
    assert snap["observation_gaps"]["membership_rejected"] == 1
    assert "process_identity_or_membership_unproven" in snap["unavailable"]
    assert snap["cpu_complete"] is True


def test_windows_reused_pid_keeps_the_previous_identity():
    api = _JobApi()
    backend = _windows(api)
    backend.job = api.job
    api.members = [410]
    api.pid_creation[410] = 4100
    api.pid_memory[410] = {"working_set": 500, "peak_working_set": 500}
    backend.sample(backend.ledger)
    first = api.handle_for_pid[410][0]
    assert api.opened == [410]
    api.live[first] = False
    api.in_job[first] = False
    api.pid_creation[410] = 4101
    api.pid_memory[410] = {"working_set": 800, "peak_working_set": 800}
    backend.sample(backend.ledger)
    assert api.opened == [410, 410]
    assert [row["identity"] for row in backend.ledger.public()] == ["410:4100", "410:4101"]
    assert set(backend._retained) == {"410:4100", "410:4101"}
    api.live[api.handle_for_pid[410][1]] = True
    api.in_job[api.handle_for_pid[410][1]] = True
    backend.sample(backend.ledger)
    assert api.opened == [410, 410]
    api.active = 0
    api.total = 2
    api.memory[first] = {"working_set": 32768, "peak_working_set": 612}
    second = api.handle_for_pid[410][1]
    api.memory[second] = {"working_set": 32768, "peak_working_set": 900}
    snap = backend.snapshot()
    assert _row(backend, "410:4100")["peak_working_set_bytes"] == 612
    assert _row(backend, "410:4100")["last_working_set_bytes"] == 500
    assert _row(backend, "410:4101")["peak_working_set_bytes"] == 900
    assert snap["working_set_accounting"] == "final_on_observed_handles"
    assert snap["identities_missing"] == 0


def test_windows_missed_final_read_keeps_the_sampled_peak_unlabeled():
    api = _JobApi()
    backend = _windows(api)
    backend.job = api.job
    api.members = [70, 71]
    api.pid_creation[70] = 700
    api.pid_creation[71] = 710
    api.pid_memory[70] = {"working_set": 11087872, "peak_working_set": 11087872}
    api.pid_memory[71] = None
    api.total = 3
    backend.sample(backend.ledger)
    assert api.opened == [70, 71]
    live = _row(backend, "70:700")
    missed = _row(backend, "71:710")
    assert live["peak_working_set_bytes"] == 11087872
    assert live["kernel_high_water_while_observed"] is True
    assert missed["peak_working_set_bytes"] is None
    assert missed["kernel_high_water_while_observed"] is False
    api.memory[api.handle_for_pid[70][0]] = None
    api.memory[api.handle_for_pid[71][0]] = {"working_set": 32768, "peak_working_set": 11100160}
    api.active = 0
    snap = backend.snapshot()
    assert _row(backend, "70:700")["peak_working_set_bytes"] == 11087872
    assert _row(backend, "70:700")["last_working_set_bytes"] == 11087872
    assert _row(backend, "70:700")["peak_working_set_final"] is False
    assert _row(backend, "71:710")["peak_working_set_bytes"] == 11100160
    assert _row(backend, "71:710")["peak_working_set_final"] is True
    assert _row(backend, "71:710")["kernel_high_water_while_observed"] is False
    assert _row(backend, "71:710")["last_working_set_bytes"] is None
    assert snap["working_set_accounting"] == "latest_observation"
    assert snap["observation_gaps"]["final_query_failed"] == 1
    assert snap["identities_missing"] == 1
    assert len(backend.ledger.public()) == 2
    assert "final_working_set_peak" in snap["unavailable"]


def test_windows_unavailable_query_does_not_invent_an_identity():
    api = _JobApi()
    backend = _windows(api)
    backend.job = api.job
    api.members = [80]
    api.fail_open.add(80)
    api.total = 2
    api.active = 0
    backend.sample(backend.ledger)
    snap = backend.snapshot()
    assert backend.ledger.public() == []
    assert snap["identities_missing"] == 2
    assert snap["observation_gaps"]["query_handle_unavailable_observations"] == 1
    assert "query_handle_unavailable" in snap["unavailable"]
    assert "exited_before_query_handle" not in snap["observation_gaps"]
    assert "process_exited_before_query_handle" not in snap["unavailable"]
    assert snap["working_set_accounting"] == "unavailable"


def test_windows_cpu_stays_incomplete_while_processes_remain():
    api = _JobApi()
    backend = _windows(api)
    backend.job = api.job
    api.members = [90]
    api.pid_creation[90] = 900
    api.pid_memory[90] = {"working_set": 1000, "peak_working_set": 1000}
    api.active = 2
    api.total = 2
    backend.sample(backend.ledger)
    api.memory[api.handle_for_pid[90][0]] = {"working_set": 32768, "peak_working_set": 999999}
    snap = backend.snapshot()
    assert snap["cpu_microseconds"] == 6_000
    assert snap["cpu_complete"] is False
    assert snap["kernel"]["active_processes"] == 2
    assert snap["kernel"]["commit_counters_are_working_set"] is False
    assert _row(backend, "90:900")["peak_working_set_bytes"] == 1000
    assert _row(backend, "90:900")["peak_working_set_final"] is False
    coverage = backend.coverage(snap, backend.ledger.public())
    assert coverage["cpu_lifetime_complete"] is False
    assert coverage["cpu_includes_exited_descendants"] is False
    assert coverage["status"] == "partial"
    assert coverage["working_set_accounting"] == "latest_observation"
    assert ("memory", api.handle_for_pid[90][0]) in api.calls
    assert api.calls.count(("memory", api.handle_for_pid[90][0])) == 1


def test_windows_handle_cap_leaves_the_rest_visible_and_closed():
    import deploy.owned_launch_accounting as accounting

    api = _JobApi()
    backend = _windows(api)
    backend.job = api.job
    first = 100_000
    api.members = list(range(first, first + accounting.MAX_LEDGER + 1))
    api.total = accounting.MAX_LEDGER + 1
    api.active = 0
    backend.sample(backend.ledger)
    assert len(backend._retained) == accounting.MAX_LEDGER
    assert len(api.opened) == accounting.MAX_LEDGER
    assert api.members[-1] not in api.opened
    assert backend.ledger.truncated is True
    snap = backend.snapshot()
    assert snap["identities_missing"] == 1
    assert snap["observation_gaps"]["ledger_truncated"] is True
    assert len(backend.ledger.public()) == accounting.MAX_LEDGER
    backend.close()
    assert api.closed.count(api.job) == 1
    query_closes = [handle for handle in api.closed if handle != api.job]
    assert len(query_closes) == accounting.MAX_LEDGER
    assert len(api.closed) == len(set(api.closed))


def test_windows_close_paths_release_each_handle_once():
    import deploy.owned_launch_accounting as accounting

    missing = _JobApi()
    missing.in_job[missing.process] = False
    backend = _windows(missing)
    with pytest.raises(accounting.OwnedLaunchError, match="not_in_job_before_resume"):
        backend.spawn()
    assert missing.calls.count(("resume", missing.thread)) == 0
    assert missing.terminate_processes == [missing.process]
    assert missing.query_for_root not in missing.closed
    first = backend.close()
    assert first == (True, None)
    assert missing.closed == [missing.thread, missing.process, missing.job]
    assert backend.close() == (True, None)
    assert missing.closed == [missing.thread, missing.process, missing.job]

    mismatched = _JobApi()
    mismatched.duplicate_creation = 999
    backend = _windows(mismatched)
    with pytest.raises(accounting.OwnedLaunchError, match="root_query_handle_unavailable"):
        backend.spawn()
    assert mismatched.query_for_root in mismatched.closed
    assert ("resume", mismatched.thread) not in mismatched.calls
    assert _row(backend, "100:1000")["peak_working_set_bytes"] is None
    backend.close()
    assert mismatched.closed.count(mismatched.query_for_root) == 1
    assert mismatched.closed.count(mismatched.process) == 1

    stalled = _JobApi()
    stalled.resume_result = 0xFFFFFFFF
    backend = _windows(stalled)
    with pytest.raises(accounting.OwnedLaunchError, match="resume_failed"):
        backend.spawn()
    assert stalled.terminate_jobs == [stalled.job]
    assert stalled.query_for_root not in stalled.closed
    backend.close()
    assert stalled.closed.count(stalled.query_for_root) == 1
    assert stalled.closed.count(stalled.thread) == 1
    assert stalled.closed.count(stalled.process) == 1
    assert stalled.closed.count(stalled.job) == 1
    closed_once = list(stalled.closed)
    assert backend.close() == (True, None)
    assert stalled.closed == closed_once

    partial = _JobApi()
    partial.close_fail.add(44)
    backend = _windows(partial)
    backend.job = 11
    backend.thread = None
    backend.process = 22
    backend._retained["1:1"] = accounting._RetainedQuery(1, 1, 44)
    assert backend.close() == (False, "close_6")
    assert partial.closed == [44, 22, 11]
    assert backend.close() == (False, "close_6")
    assert partial.closed == [44, 22, 11]


def test_windows_finish_drains_once_and_does_not_add_a_root_wait(monkeypatch):
    import time

    import deploy.owned_launch_accounting as accounting

    api = _JobApi()
    api.active = 4
    backend = _windows(api)
    backend.job = api.job
    started = time.monotonic()
    assert backend.wait_until_drained(0.2) is False
    assert time.monotonic() - started < 2
    api.active = 0
    assert backend.wait_until_drained(5) is True

    api = _JobApi()
    api.members = [api.root_pid]
    api.active = 1
    backend = _windows(api)
    backend.spawn()
    seen = []

    def drain(seconds):
        seen.append(("drain", seconds))
        api.active = 0
        return True

    def wait_root(seconds):
        seen.append(("root", seconds))
        return True

    backend.wait_until_drained = drain
    backend.wait_root = wait_root
    launch = accounting.OwnedLaunch(backend, bound_seconds=30, sample_seconds=0.05)
    report = launch.finish()
    assert seen == [("drain", 5)]
    assert report["cleanup"]["ok"] is True
    assert report["cleanup"]["failure"] is None
    assert report["cleanup"]["terminated_owned_group"] is True
    assert report["kernel"]["active_processes"] == 0
    assert report["coverage"]["cpu_lifetime_complete"] is True
    assert ("wait_root", api.process, 5) not in api.calls

    quiet = _JobApi()
    quiet.members = [quiet.root_pid]
    quiet.active = 0
    quiet.total = 1
    backend = _windows(quiet)
    backend.spawn()
    seen.clear()
    backend.wait_until_drained = lambda seconds: seen.append(("drain", seconds)) or True
    backend.wait_root = lambda seconds: seen.append(("root", seconds)) or True
    launch = accounting.OwnedLaunch(backend, bound_seconds=5, sample_seconds=0.05)
    report = launch.finish()
    assert seen == []
    assert report["cleanup"]["ok"] is True
    assert report["cleanup"]["failure"] is None
    assert report["cleanup"]["terminated_owned_group"] is False
    assert report["coverage"]["cpu_lifetime_complete"] is True

    stuck = _JobApi()
    stuck.members = [stuck.root_pid]
    stuck.active = 1
    backend = _windows(stuck)
    backend.spawn()
    seen.clear()

    def stuck_drain(seconds):
        seen.append(("drain", seconds))
        return False

    backend.wait_until_drained = stuck_drain
    backend.wait_root = lambda seconds: seen.append(("root", seconds)) or True
    launch = accounting.OwnedLaunch(backend, bound_seconds=30, sample_seconds=0.05)
    report = launch.finish()
    assert seen == [("drain", 5)]
    assert report["cleanup"]["ok"] is False
    assert report["cleanup"]["failure"] == "drain_timeout"
    assert report["kernel"]["active_processes"] == 1
    assert report["coverage"]["cpu_lifetime_complete"] is False
    closed_once = [stuck.query_for_root, stuck.thread, stuck.process, stuck.job]
    assert stuck.closed == closed_once
    assert backend.close() == (True, None)
    assert stuck.closed == closed_once

    earlier = _JobApi()
    earlier.members = [earlier.root_pid]
    earlier.active = 1
    backend = _windows(earlier)
    backend.spawn()
    backend.terminate = lambda: (False, "job_missing")
    backend.wait_until_drained = lambda seconds: False
    launch = accounting.OwnedLaunch(backend, bound_seconds=30, sample_seconds=0.05)
    report = launch.finish()
    assert report["cleanup"]["ok"] is False
    assert report["cleanup"]["failure"] == "job_missing"
    assert report["kernel"]["active_processes"] == 1
    assert report["coverage"]["cpu_lifetime_complete"] is False
    assert earlier.closed == [earlier.query_for_root, earlier.thread, earlier.process, earlier.job]


def test_windows_sample_waits_for_close_instead_of_sharing_a_handle():
    import threading

    api = _JobApi()
    backend = _windows(api)
    backend.job = api.job
    api.members = [610]
    api.pid_creation[610] = 6100
    entered = threading.Event()
    release = threading.Event()
    original = api.working_set

    def blocking(process):
        entered.set()
        assert release.wait(2)
        return original(process)

    api.working_set = blocking
    sampler = threading.Thread(target=lambda: backend.sample(backend.ledger))
    sampler.start()
    assert entered.wait(2)
    assert backend._lock.acquire(blocking=False) is False
    closer = threading.Thread(target=backend.close)
    closer.start()
    assert release.wait(0.05) is False
    release.set()
    sampler.join(2)
    closer.join(2)
    assert sampler.is_alive() is False
    assert closer.is_alive() is False
    handle = api.handle_for_pid[610][0]
    assert api.closed.count(handle) == 1
    assert backend.close()[0] is True
    assert api.closed.count(handle) == 1


def test_final_peak_fields_survive_both_normalizers():
    import json
    import subprocess

    from deploy.report_telemetry_renderer import _ledger_row, retain_owned_launch

    unknown = {
        "pid": 40,
        "creation": "9",
        "identity": "40:9",
        "peak_working_set_bytes": 11087872,
        "first_working_set_bytes": 1000,
        "last_working_set_bytes": 11087872,
        "kernel_high_water_while_observed": True,
    }
    assert _ledger_row(unknown)["peak_working_set_final"] is None
    assert _ledger_row(unknown)["peak_working_set_bytes"] == 11087872
    final = dict(unknown, peak_working_set_bytes=11100160, peak_working_set_final=True)
    missed = dict(unknown, pid=41, identity="41:9", peak_working_set_final=False)
    assert _ledger_row(final)["peak_working_set_final"] is True
    assert _ledger_row(final)["kernel_high_water_while_observed"] is True
    assert _ledger_row(missed)["peak_working_set_final"] is False
    assert _ledger_row(missed)["peak_working_set_bytes"] == 11087872
    report = {
        "ledger": [final, missed, unknown],
        "coverage": {
            "platform": "windows",
            "status": "partial",
            "cpu_lifetime_complete": True,
            "working_set_accounting": "latest_observation",
            "retained_handles_cover_unseen_processes": False,
            "rss_high_water": "per_process_kernel_while_alive_partial",
        },
        "resource_acceptance": True,
    }
    public = retain_owned_launch(report)
    assert public["resource_acceptance"] is False
    assert public["budget"]["compared"] is False
    assert public["budget"]["status"] == "UNACCEPTED"
    assert [row["peak_working_set_final"] for row in public["ledger"]] == [True, False, None]
    assert public["ledger"][2]["peak_working_set_bytes"] == 11087872
    assert public["coverage"]["working_set_accounting"] == "latest_observation"
    assert public["coverage"]["retained_handles_cover_unseen_processes"] is False
    assert public["coverage"]["status"] == "partial"
    script = (
        "import { publicOwnedReport } from './studio/electron/scripts/installed-resource-report.mjs';"
        "const chunks = [];"
        "process.stdin.on('data', chunk => chunks.push(chunk));"
        "process.stdin.on('end', () => {"
        "const report = publicOwnedReport(JSON.parse(Buffer.concat(chunks).toString('utf8')));"
        "process.stdout.write(JSON.stringify(report));"
        "});"
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        input=json.dumps(report),
        text=True,
        capture_output=True,
        check=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    javascript = json.loads(completed.stdout)
    assert [row["peak_working_set_final"] for row in javascript["ledger"]] == [True, False, None]
    assert javascript["ledger"][0]["peak_working_set_bytes"] == 11100160
    assert javascript["ledger"][1]["peak_working_set_bytes"] == 11087872
    assert javascript["coverage"]["working_set_accounting"] == "latest_observation"
    assert javascript["coverage"]["retained_handles_cover_unseen_processes"] is False
    assert javascript["resource_acceptance"] is False
    assert javascript["budget"]["compared"] is False
