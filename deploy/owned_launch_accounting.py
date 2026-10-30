"""Diagnostic owned-launch resource accounting.

The measured child is placed in a disposable OS group before it executes.
Lifetime CPU comes from that group, not from a later poll of surviving PIDs.
Working-set figures stay per process. Cgroup memory and Windows job commit
are never reported as RSS. Missing counters stay null.

This module does not start product telemetry, change disclosure, or compare
a run with the unaccepted 8 MiB / 0.5% budget.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import threading
import time


ADDITIONAL_RSS_BUDGET_BYTES = 8_388_608
CPU_BUDGET_ONE_CORE_FRACTION = 0.005
BUDGET_STATUS = "UNACCEPTED"
MAX_BOUND_SECONDS = 120.0
MAX_SAMPLES = 3_000
MAX_LEDGER = 512
_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_INACTIVE = {"before-first-mark", "idle", "settlement", "send-settlement", "wait"}
_CODE = re.compile(r"[a-z0-9_]{1,80}\Z")


class OwnedLaunchError(RuntimeError):
    def __init__(self, code: str):
        if not _CODE.fullmatch(code):
            code = "invalid_error"
        super().__init__(code)
        self.code = code


class OwnedLaunchUnsupported(OwnedLaunchError):
    pass


def installed_journey_boundary() -> dict:
    """Next call for the installed workload. Does not launch anything."""
    return {
        "wired_into_smoke_installed_hosting": False,
        "launcher": "studio/electron/scripts/smoke-installed-hosting.mjs",
        "function": "launch",
        "next_call": (
            "start_owned_launch before the installed child executes; "
            "mark_phase only around the existing 128-cycle canonical workload "
            "and one fixed counterbalance"
        ),
        "budget": {
            "additional_rss_bytes_per_process": ADDITIONAL_RSS_BUDGET_BYTES,
            "cpu_one_core_fraction": CPU_BUDGET_ONE_CORE_FRACTION,
            "status": BUDGET_STATUS,
            "compared": False,
        },
    }


def combine_active_cpu(phases: list[dict]) -> dict:
    """CPU and wall time of phases declared active.

    A phase with a missing counter makes the active total unavailable.
    A measured delta of zero stays zero. No active phase stays unavailable.
    """
    saw = False
    cpu = 0
    wall = 0
    for phase in phases:
        if phase.get("active") is not True:
            continue
        saw = True
        start = phase.get("cpu_start")
        end = phase.get("cpu_end")
        if type(start) is not int or type(end) is not int or end < start:
            return {"cpu_microseconds": None, "wall_microseconds": None}
        start_ns = phase.get("start_ns")
        end_ns = phase.get("end_ns")
        if type(start_ns) is not int or type(end_ns) is not int or end_ns < start_ns:
            return {"cpu_microseconds": None, "wall_microseconds": None}
        cpu += end - start
        wall += (end_ns - start_ns) // 1000
    if not saw:
        return {"cpu_microseconds": None, "wall_microseconds": None}
    return {"cpu_microseconds": cpu, "wall_microseconds": wall}


def _code(prefix: str, number: int | None = None) -> str:
    if not _CODE.fullmatch(prefix):
        prefix = "error"
    if number is None:
        return prefix
    return f"{prefix}_{int(number) & 0xFFFFFFFF:x}"


def _check_bound(bound_seconds: float, sample_seconds: float) -> tuple[float, float]:
    if type(bound_seconds) not in (int, float) or type(sample_seconds) not in (int, float):
        raise OwnedLaunchError("invalid_bound")
    bound = float(bound_seconds)
    sample = float(sample_seconds)
    if not 0 < bound <= MAX_BOUND_SECONDS or not 0.02 <= sample <= 0.2:
        raise OwnedLaunchError("invalid_bound")
    return bound, sample


def _check_phase(name: str, count: int, active: bool) -> None:
    if type(name) is not str or not _NAME.fullmatch(name):
        raise OwnedLaunchError("invalid_phase")
    if type(count) is not int or not 0 <= count <= 1_000_000:
        raise OwnedLaunchError("invalid_phase")
    if type(active) is not bool:
        raise OwnedLaunchError("invalid_phase")
    if active and name in _INACTIVE:
        raise OwnedLaunchError("inactive_phase_marked_active")


def _linux_start_ticks(pid: int) -> int | None:
    path = Path(f"/proc/{pid}/stat")
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) > 16384 or not raw.startswith(f"{pid} (".encode()):
        return None
    suffix = raw.rpartition(b") ")[2]
    fields = suffix.split()
    if len(fields) < 20 or not fields[19].isdigit():
        return None
    ticks = int(fields[19])
    if ticks >= 2**64:
        return None
    return ticks


def _linux_residency(pid: int) -> dict | None:
    fields = {"VmRSS", "VmHWM", "RssAnon", "RssFile", "RssShmem"}
    try:
        raw = Path(f"/proc/{pid}/status").read_text(encoding="ascii", errors="strict")
    except (OSError, UnicodeError):
        return None
    if len(raw) > 65536:
        return None
    found = {}
    for line in raw.splitlines():
        key, _, value = line.partition(":")
        if key not in fields:
            continue
        parts = value.split()
        if len(parts) != 2 or parts[1] != "kB" or not parts[0].isdigit():
            return None
        found[key] = int(parts[0]) * 1024
    if set(found) != fields:
        return None
    return found


def _usage_usec(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="ascii", errors="strict")
    except (OSError, UnicodeError):
        return None
    if len(raw) > 65536:
        return None
    for line in raw.splitlines():
        key, _, value = line.partition(" ")
        if key == "usage_usec" and value.isdigit():
            return int(value)
    return None


def _single_counter(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="ascii", errors="strict").strip()
    except (OSError, UnicodeError):
        return None
    if not raw.isdigit() or len(raw) > 20:
        return None
    return int(raw)


class _Ledger:
    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.truncated = False

    def add_identity(self, pid: int, creation: int) -> dict | None:
        if type(pid) is not int or type(creation) is not int or not 0 < pid < 2**32:
            return None
        if creation < 0:
            return None
        identity = f"{pid}:{creation}"
        row = self.rows.get(identity)
        if row is not None:
            return row
        if len(self.rows) >= MAX_LEDGER:
            self.truncated = True
            return None
        row = {
            "pid": pid,
            "creation": str(creation),
            "identity": identity,
            "peak_working_set_bytes": None,
            "first_working_set_bytes": None,
            "last_working_set_bytes": None,
            "kernel_high_water_while_observed": False,
        }
        self.rows[identity] = row
        return row

    def observe(
        self, pid: int, creation: int, *, current: int | None, high_water: int | None
    ) -> None:
        row = self.add_identity(pid, creation)
        if row is None:
            return
        if type(current) is int and current >= 0:
            if row["first_working_set_bytes"] is None:
                row["first_working_set_bytes"] = current
            row["last_working_set_bytes"] = current
        if type(high_water) is int and high_water >= 0:
            previous = row["peak_working_set_bytes"]
            row["peak_working_set_bytes"] = (
                high_water if previous is None else max(previous, high_water)
            )
            row["kernel_high_water_while_observed"] = True

    def public(self) -> list[dict]:
        return [dict(self.rows[key]) for key in sorted(self.rows)]


class OwnedLaunch:
    def __init__(self, backend, *, bound_seconds: float, sample_seconds: float):
        self.backend = backend
        self.bound_seconds = bound_seconds
        self.sample_seconds = sample_seconds
        self.started = time.monotonic_ns()
        cpu = backend.cpu_microseconds()
        self._open = {
            "name": "before-first-mark",
            "active": False,
            "start_ns": self.started,
            "end_ns": None,
            "cpu_start": cpu,
            "cpu_end": None,
            "count_start": 0,
            "count_end": None,
        }
        self._phases: list[dict] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample_loop, name="owned-launch-sample")
        self._thread.start()
        self._finished = False
        self._sample_truncated = False
        self._sample_error = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        if not self._finished:
            self.finish()
        return False

    def mark_phase(self, name: str, *, canonical_operations_completed: int, active: bool) -> None:
        if self._finished:
            raise OwnedLaunchError("already_finished")
        _check_phase(name, canonical_operations_completed, active)
        self._close_open(canonical_operations_completed)
        now = time.monotonic_ns()
        self._open = {
            "name": name,
            "active": active,
            "start_ns": now,
            "end_ns": None,
            "cpu_start": self.backend.cpu_microseconds(),
            "cpu_end": None,
            "count_start": canonical_operations_completed,
            "count_end": None,
        }

    def wait_root(self, timeout_seconds: float) -> bool:
        if self._finished:
            raise OwnedLaunchError("already_finished")
        if (
            type(timeout_seconds) not in (int, float)
            or not 0 < float(timeout_seconds) <= MAX_BOUND_SECONDS
        ):
            raise OwnedLaunchError("invalid_bound")
        return self.backend.wait_root(float(timeout_seconds))

    def finish(self, *, canonical_operations_completed: int | None = None) -> dict:
        if self._finished:
            raise OwnedLaunchError("already_finished")
        self._finished = True
        if canonical_operations_completed is not None and (
            type(canonical_operations_completed) is not int
            or not 0 <= canonical_operations_completed <= 1_000_000
        ):
            canonical_operations_completed = None
        cleanup_failure = None
        terminated = False
        timed_out = False
        snapshot = {"cpu_microseconds": None}
        try:
            self._stop.set()
            self._thread.join(2)
            if self._thread.is_alive() and cleanup_failure is None:
                cleanup_failure = "sampler_still_running"
            self._close_open(canonical_operations_completed)
            active = self.backend.still_active()
            past_bound = (time.monotonic_ns() - self.started) / 1_000_000_000 >= self.bound_seconds
            if active is None or active is True:
                timed_out = past_bound
                ok, failure = self.backend.terminate()
                terminated = True
                if not ok and cleanup_failure is None:
                    cleanup_failure = failure or "terminate_failed"
                self.backend.wait_root(5)
            snapshot = self.backend.snapshot()
        except Exception:
            if cleanup_failure is None:
                cleanup_failure = "finish_failed"
        ok, failure = self.backend.close()
        if not ok and cleanup_failure is None:
            cleanup_failure = failure or "close_failed"
        return self._report(snapshot, cleanup_failure, terminated, timed_out)

    def _close_open(self, count: int | None) -> None:
        if self._open is None:
            return
        self._open["end_ns"] = time.monotonic_ns()
        self._open["cpu_end"] = self.backend.cpu_microseconds()
        self._open["count_end"] = count
        self._phases.append(self._open)
        self._open = None

    def _sample_loop(self) -> None:
        samples = 0
        try:
            while not self._stop.is_set():
                if (time.monotonic_ns() - self.started) / 1_000_000_000 >= self.bound_seconds:
                    break
                self.backend.sample(self.backend.ledger)
                samples += 1
                if samples >= MAX_SAMPLES:
                    self._sample_truncated = True
                    break
                if self._stop.wait(self.sample_seconds):
                    break
        except Exception:
            self._sample_error = "sample_failed"

    def _report(
        self, snapshot: dict, cleanup_failure: str | None, terminated: bool, timed_out: bool
    ) -> dict:
        phases = []
        for phase in self._phases:
            cpu = None
            if (
                type(phase["cpu_start"]) is int
                and type(phase["cpu_end"]) is int
                and phase["cpu_end"] >= phase["cpu_start"]
            ):
                cpu = phase["cpu_end"] - phase["cpu_start"]
            phases.append(
                {
                    "name": phase["name"],
                    "active": phase["active"],
                    "start_offset_ns": phase["start_ns"] - self.started,
                    "end_offset_ns": None
                    if phase["end_ns"] is None
                    else phase["end_ns"] - self.started,
                    "canonical_operations_at_start": phase["count_start"],
                    "canonical_operations_at_end": phase["count_end"],
                    "cpu_microseconds": cpu,
                }
            )
        active = combine_active_cpu(self._phases)
        ledger = self.backend.ledger.public()
        lifetime = snapshot.get("cpu_microseconds")
        if type(lifetime) is not int or lifetime < 0:
            lifetime = None
        coverage = self.backend.coverage(snapshot, ledger)
        missing_high_water = any(row["peak_working_set_bytes"] is None for row in ledger) or bool(
            snapshot.get("identities_missing")
        )
        if missing_high_water and coverage["rss_high_water"] == "per_process_kernel_while_alive":
            coverage["rss_high_water"] = "per_process_kernel_while_alive_partial"
            coverage["status"] = "partial" if coverage["status"] != "unsupported" else "unsupported"
        unavailable = []
        if lifetime is None:
            unavailable.append("lifetime_cpu_microseconds")
        if active["cpu_microseconds"] is None:
            unavailable.append("active_cpu_microseconds")
        if snapshot.get("cgroup_memory_peak_bytes") is None and coverage.get("platform") == "linux":
            unavailable.append("cgroup_memory_peak_bytes")
        if missing_high_water:
            unavailable.append("unseen_or_unsampled_process_working_set")
        for name in snapshot.get("unavailable") or []:
            if name not in unavailable:
                unavailable.append(name)
        cold = [
            {"identity": row["identity"], "working_set_bytes": row["first_working_set_bytes"]}
            for row in ledger
            if row["first_working_set_bytes"] is not None
        ]
        fraction = None
        if active["cpu_microseconds"] is not None and active["wall_microseconds"]:
            fraction = f"{active['cpu_microseconds'] / active['wall_microseconds']:.6f}"
        return {
            "qualification": "unqualified",
            "resource_acceptance": False,
            "budget": {
                "additional_rss_bytes_per_process": ADDITIONAL_RSS_BUDGET_BYTES,
                "cpu_one_core_fraction": CPU_BUDGET_ONE_CORE_FRACTION,
                "status": BUDGET_STATUS,
                "compared": False,
            },
            "platform_method": snapshot.get("method"),
            "coverage": coverage,
            "unavailable_counters": unavailable,
            "missing_recorded_as_zero": False,
            "idle_or_settlement_included_in_active_cpu": False,
            "lifetime_cpu_microseconds": lifetime,
            "active_cpu_microseconds": active["cpu_microseconds"],
            "active_wall_microseconds": active["wall_microseconds"],
            "active_core_fraction": fraction,
            "cold_start": {
                "kind": "first_observed_absolute",
                "subtracted": False,
                "processes": cold,
            },
            "phases": phases,
            "ledger": ledger,
            "ledger_truncated": self.backend.ledger.truncated,
            "identities_missing": snapshot.get("identities_missing"),
            "sampled_peaks": snapshot.get("sampled_peaks"),
            "kernel": snapshot.get("kernel"),
            "observer_in_measured_group": snapshot.get("observer_in_measured_group"),
            "cleanup": {
                "ok": cleanup_failure is None,
                "failure": cleanup_failure,
                "retried": False,
                "terminated_owned_group": terminated,
            },
            "bounds": {
                "lifetime_seconds_cap": self.bound_seconds,
                "timed_out": timed_out,
                "sample_seconds": self.sample_seconds,
                "sample_truncated": self._sample_truncated,
                "sample_error": self._sample_error,
            },
        }


def start_owned_launch(
    argv: list[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    bound_seconds: float = 30.0,
    sample_seconds: float = 0.05,
) -> OwnedLaunch:
    """Create the OS group, start argv inside it, and only then let it run."""
    bound, sample = _check_bound(bound_seconds, sample_seconds)
    if sys.platform == "win32":
        backend = WindowsJobBackend(argv, cwd=cwd, env=env)
    elif sys.platform == "linux":
        backend = LinuxCgroupBackend(argv, cwd=cwd, env=env)
    elif sys.platform == "darwin":
        backend = DarwinBackend(argv, cwd=cwd, env=env)
    else:
        raise OwnedLaunchUnsupported("unsupported_platform")
    try:
        backend.spawn()
    except Exception:
        backend.close()
        raise
    return OwnedLaunch(backend, bound_seconds=bound, sample_seconds=sample)


class WindowsJobBackend:
    """A job created and assigned before the child thread runs.

    TotalUserTime and TotalKernelTime keep terminated processes.
    PeakJobMemoryUsed is commit charge, not working set.
    """

    def __init__(self, argv: list[str], *, cwd: str | None, env: dict[str, str] | None):
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            raise OwnedLaunchUnsupported("windows_pointer_width")
        if not argv or any(type(arg) is not str or "\x00" in arg for arg in argv):
            raise OwnedLaunchError("invalid_argv")
        if sum(len(arg) for arg in argv) > 30_000:
            raise OwnedLaunchError("invalid_argv")
        self.argv = argv
        self.cwd = cwd
        self.env = env
        self.ledger = _Ledger()
        self.job = None
        self.process = None
        self.thread = None
        self.root_pid = None
        self.root_creation = None
        self._api = _WinApi()
        self._sampled_sum_peak = None
        self._closed = False

    def spawn(self) -> None:
        api = self._api
        job = api.create_job()
        self.job = job
        api.set_kill_on_close(job)
        process, thread, pid = api.create_suspended_in_job(job, self.argv, self.cwd, self.env)
        self.process = process
        self.thread = thread
        self.root_pid = pid
        creation = api.creation_ticks(process)
        members = api.job_pids(job)
        if creation is None or members is None or pid not in members:
            api.terminate_process(process)
            raise OwnedLaunchError("not_in_job_before_resume")
        self.root_creation = creation
        self.ledger.add_identity(pid, creation)
        if api.resume(thread) == 0xFFFFFFFF:
            api.terminate_job(job)
            raise OwnedLaunchError("resume_failed")
        self.sample(self.ledger)

    def cpu_microseconds(self) -> int | None:
        info = self._api.accounting(self.job) if self.job else None
        if info is None:
            return None
        return (info["user_100ns"] + info["kernel_100ns"]) // 10

    def still_active(self) -> bool | None:
        info = self._api.accounting(self.job) if self.job else None
        if info is None:
            return None
        return info["active_processes"] > 0

    def wait_root(self, timeout_seconds: float) -> bool:
        if not self.process:
            return False
        return self._api.wait(self.process, timeout_seconds)

    def sample(self, ledger: _Ledger) -> None:
        if not self.job:
            return
        current_sum = 0
        saw = 0
        members = self._api.job_pids(self.job)
        if members is None:
            return
        for pid in members:
            if pid == os.getpid():
                continue
            opened = self._api.open_query(pid)
            if opened is None:
                continue
            try:
                creation = self._api.creation_ticks(opened)
                memory = self._api.working_set(opened)
            finally:
                self._api.close(opened)
            if creation is None or memory is None:
                if creation is not None:
                    ledger.add_identity(pid, creation)
                continue
            ledger.observe(
                pid, creation, current=memory["working_set"], high_water=memory["peak_working_set"]
            )
            current_sum += memory["working_set"]
            saw += 1
        if saw:
            self._sampled_sum_peak = (
                current_sum
                if self._sampled_sum_peak is None
                else max(self._sampled_sum_peak, current_sum)
            )

    def terminate(self) -> tuple[bool, str | None]:
        if not self.job:
            return False, "job_missing"
        return self._api.terminate_job(self.job)

    def snapshot(self) -> dict:
        info = self._api.accounting(self.job) if self.job else None
        extended = self._api.extended(self.job) if self.job else None
        cpu = None if info is None else (info["user_100ns"] + info["kernel_100ns"]) // 10
        missing = None
        if info is not None:
            missing = info["total_processes"] - len(self.ledger.rows)
            if missing < 0:
                missing = None
        pids = self._api.job_pids(self.job) if self.job else None
        return {
            "method": "windows_job_before_resume",
            "cpu_microseconds": cpu,
            "identities_missing": missing,
            "observer_in_measured_group": None if pids is None else os.getpid() in pids,
            "sampled_peaks": {
                "sum_working_set_bytes": self._sampled_sum_peak,
                "sum_double_counts_shared": True,
                "not_a_budget_measurement": True,
                "sampled_pid_cpu_is_complete": False,
            },
            "kernel": None
            if info is None
            else {
                "total_user_100ns": info["user_100ns"],
                "total_kernel_100ns": info["kernel_100ns"],
                "total_processes": info["total_processes"],
                "active_processes": info["active_processes"],
                "processes_no_longer_active": info["total_processes"] - info["active_processes"],
                "terminated_by_limit": info["terminated_by_limit"],
                "peak_process_commit_bytes": None if extended is None else extended["peak_process"],
                "peak_job_commit_bytes": None if extended is None else extended["peak_job"],
                "commit_counters_are_working_set": False,
            },
            "cpu_complete": info is not None,
            "unavailable": [] if extended is not None else ["job_commit_peak"],
        }

    def coverage(self, snapshot: dict, ledger: list[dict]) -> dict:
        complete = (
            snapshot.get("cpu_complete") is True and snapshot.get("cpu_microseconds") is not None
        )
        # PeakWorkingSetSize is the kernel peak as of the last successful query.
        # A process can still grow, or exit, before the next query. CPU from the
        # job is complete; working-set coverage therefore stays partial.
        return {
            "platform": "windows",
            "status": "partial" if complete else "unsupported",
            "cpu_lifetime_complete": complete,
            "cpu_includes_exited_descendants": complete,
            "sampled_pid_cpu_is_complete": False,
            "rss_high_water": "per_process_kernel_while_alive"
            if any(row["kernel_high_water_while_observed"] for row in ledger)
            else "unavailable",
            "rss_high_water_covers_unseen_exited_processes": False,
            "cgroup_memory_peak_is_per_process_rss": False,
        }

    def close(self) -> tuple[bool, str | None]:
        if self._closed:
            return True, None
        self._closed = True
        failure = None
        for handle in (self.thread, self.process, self.job):
            if handle:
                ok, code = self._api.close(handle)
                if not ok and failure is None:
                    failure = code
        self.thread = self.process = self.job = None
        return failure is None, failure


class _WinApi:
    def __init__(self):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        k = self.kernel
        k.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        k.CreateJobObjectW.restype = ctypes.c_void_p
        k.SetInformationJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        k.SetInformationJobObject.restype = wintypes.BOOL
        k.QueryInformationJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        k.QueryInformationJobObject.restype = wintypes.BOOL
        k.InitializeProcThreadAttributeList.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        k.InitializeProcThreadAttributeList.restype = wintypes.BOOL
        k.UpdateProcThreadAttribute.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        k.UpdateProcThreadAttribute.restype = wintypes.BOOL
        k.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
        k.DeleteProcThreadAttributeList.restype = None
        k.CreateProcessW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.POINTER(ctypes.c_wchar),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        k.CreateProcessW.restype = wintypes.BOOL
        k.ResumeThread.argtypes = [ctypes.c_void_p]
        k.ResumeThread.restype = wintypes.DWORD
        k.TerminateJobObject.argtypes = [ctypes.c_void_p, wintypes.UINT]
        k.TerminateJobObject.restype = wintypes.BOOL
        k.TerminateProcess.argtypes = [ctypes.c_void_p, wintypes.UINT]
        k.TerminateProcess.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        k.CloseHandle.restype = wintypes.BOOL
        k.WaitForSingleObject.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        k.WaitForSingleObject.restype = wintypes.DWORD
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = ctypes.c_void_p
        k.GetProcessTimes.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        k.GetProcessTimes.restype = wintypes.BOOL
        k.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD]
        k.K32GetProcessMemoryInfo.restype = wintypes.BOOL

    def create_job(self):
        handle = self.kernel.CreateJobObjectW(None, None)
        if not handle:
            raise OwnedLaunchError(_code("create_job", ctypes.get_last_error()))
        return handle

    def set_kill_on_close(self, job) -> None:
        if ctypes.sizeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION) != 144:
            raise OwnedLaunchError("job_structure_size")
        if ctypes.sizeof(JOBOBJECT_BASIC_ACCOUNTING_INFORMATION) != 48:
            raise OwnedLaunchError("accounting_structure_size")
        if ctypes.sizeof(PROCESS_MEMORY_COUNTERS) != 72:
            raise OwnedLaunchError("memory_structure_size")
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x2000
        ok = self.kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        if not ok:
            raise OwnedLaunchError(_code("job_limit", ctypes.get_last_error()))

    def create_suspended_in_job(self, job, argv, cwd, env):
        size = ctypes.c_size_t(0)
        self.kernel.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        if not 0 < size.value <= 65536:
            raise OwnedLaunchError("attribute_list_size")
        buf = ctypes.create_string_buffer(size.value)
        if not self.kernel.InitializeProcThreadAttributeList(buf, 1, 0, ctypes.byref(size)):
            raise OwnedLaunchError(_code("attribute_list", ctypes.get_last_error()))
        handles = (ctypes.c_void_p * 1)(job)
        try:
            updated = self.kernel.UpdateProcThreadAttribute(
                buf,
                0,
                0x0002000D,
                ctypes.cast(handles, ctypes.c_void_p),
                ctypes.sizeof(handles),
                None,
                None,
            )
            if not updated:
                raise OwnedLaunchError(_code("job_attribute", ctypes.get_last_error()))
            startup = STARTUPINFOEXW()
            startup.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
            startup.lpAttributeList = ctypes.addressof(buf)
            process_info = PROCESS_INFORMATION()
            command = _wchar_buffer(" ".join(_quote_windows(arg) for arg in argv))
            environment = None if env is None else _environment_block(env)
            flags = 0x4 | 0x08000000 | 0x00000200 | 0x00080000
            if environment is not None:
                flags |= 0x400
            ok = self.kernel.CreateProcessW(
                argv[0],
                command,
                None,
                None,
                False,
                flags,
                None if environment is None else ctypes.cast(environment, ctypes.c_void_p),
                cwd,
                ctypes.byref(startup),
                ctypes.byref(process_info),
            )
            if not ok:
                raise OwnedLaunchError(_code("create_process", ctypes.get_last_error()))
            return process_info.hProcess, process_info.hThread, int(process_info.dwProcessId)
        finally:
            self.kernel.DeleteProcThreadAttributeList(buf)

    def creation_ticks(self, process) -> int | None:
        created = ctypes.c_uint64()
        ignored = ctypes.c_uint64()
        ok = self.kernel.GetProcessTimes(
            process,
            ctypes.byref(created),
            ctypes.byref(ignored),
            ctypes.byref(ignored),
            ctypes.byref(ignored),
        )
        if not ok:
            return None
        return int(created.value)

    def job_pids(self, job) -> list[int]:
        class Listing(ctypes.Structure):
            _fields_ = [
                ("assigned", wintypes.DWORD),
                ("count", wintypes.DWORD),
                ("pids", ctypes.c_size_t * 64),
            ]

        info = Listing()
        ok = self.kernel.QueryInformationJobObject(
            job, 3, ctypes.byref(info), ctypes.sizeof(info), None
        )
        if not ok and ctypes.get_last_error() == 234 and info.assigned:
            capacity = min(int(info.assigned), 512)

            class Larger(ctypes.Structure):
                _fields_ = [
                    ("assigned", wintypes.DWORD),
                    ("count", wintypes.DWORD),
                    ("pids", ctypes.c_size_t * capacity),
                ]

            info = Larger()
            ok = self.kernel.QueryInformationJobObject(
                job, 3, ctypes.byref(info), ctypes.sizeof(info), None
            )
        if not ok:
            return None
        count = min(int(info.count), len(info.pids))
        return [int(info.pids[index]) for index in range(count)]

    def accounting(self, job) -> dict | None:
        info = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()
        ok = self.kernel.QueryInformationJobObject(
            job, 1, ctypes.byref(info), ctypes.sizeof(info), None
        )
        if not ok:
            return None
        return {
            "user_100ns": int(info.TotalUserTime),
            "kernel_100ns": int(info.TotalKernelTime),
            "total_processes": int(info.TotalProcesses),
            "active_processes": int(info.ActiveProcesses),
            "terminated_by_limit": int(info.TotalTerminatedProcesses),
        }

    def extended(self, job) -> dict | None:
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        ok = self.kernel.QueryInformationJobObject(
            job, 9, ctypes.byref(info), ctypes.sizeof(info), None
        )
        if not ok:
            return None
        return {
            "peak_process": int(info.PeakProcessMemoryUsed),
            "peak_job": int(info.PeakJobMemoryUsed),
        }

    def working_set(self, process) -> dict | None:
        info = PROCESS_MEMORY_COUNTERS()
        info.cb = ctypes.sizeof(info)
        ok = self.kernel.K32GetProcessMemoryInfo(process, ctypes.byref(info), info.cb)
        if not ok:
            return None
        return {
            "working_set": int(info.WorkingSetSize),
            "peak_working_set": int(info.PeakWorkingSetSize),
        }

    def open_query(self, pid: int):
        handle = self.kernel.OpenProcess(0x1000, False, pid)
        return handle or None

    def resume(self, thread) -> int:
        return int(self.kernel.ResumeThread(thread))

    def wait(self, process, timeout_seconds: float) -> bool:
        waited = self.kernel.WaitForSingleObject(process, int(timeout_seconds * 1000))
        return waited == 0

    def terminate_process(self, process) -> None:
        self.kernel.TerminateProcess(process, 1)

    def terminate_job(self, job) -> tuple[bool, str | None]:
        # A null or stale handle fails this call. It does not select a process.
        if self.kernel.TerminateJobObject(job, 1):
            return True, None
        return False, _code("terminate_job", ctypes.get_last_error())

    def close(self, handle) -> tuple[bool, str | None]:
        if not handle:
            return True, None
        if self.kernel.CloseHandle(handle):
            return True, None
        return False, _code("close", ctypes.get_last_error())


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("_pad0", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("_pad1", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_int64),
        ("TotalKernelTime", ctypes.c_int64),
        ("ThisPeriodTotalUserTime", ctypes.c_int64),
        ("ThisPeriodTotalKernelTime", ctypes.c_int64),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", ctypes.c_wchar_p),
        ("lpDesktop", ctypes.c_wchar_p),
        ("lpTitle", ctypes.c_wchar_p),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", ctypes.c_void_p),
        ("hStdOutput", ctypes.c_void_p),
        ("hStdError", ctypes.c_void_p),
    ]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", ctypes.c_void_p),
        ("hThread", ctypes.c_void_p),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def _quote_windows(arg: str) -> str:
    if arg == "":
        return '""'
    if not any(character in arg for character in ' \t"'):
        return arg
    out = ['"']
    slashes = 0
    for character in arg:
        if character == "\\":
            slashes += 1
            continue
        if character == '"':
            out.append("\\" * (slashes * 2 + 1))
            out.append('"')
        else:
            if slashes:
                out.append("\\" * slashes)
            out.append(character)
        slashes = 0
    if slashes:
        out.append("\\" * (slashes * 2))
    out.append('"')
    return "".join(out)


def _wchar_buffer(text: str):
    buf = (ctypes.c_wchar * (len(text) + 1))()
    for index, character in enumerate(text):
        buf[index] = character
    return buf


def _environment_block(env: dict[str, str]):
    if type(env) is not dict:
        raise OwnedLaunchError("invalid_environment")
    parts = []
    for key in sorted(env):
        value = env[key]
        if (
            type(key) is not str
            or type(value) is not str
            or not key
            or "=" in key
            or "\x00" in key
            or "\x00" in value
        ):
            raise OwnedLaunchError("invalid_environment")
        parts.append(f"{key}={value}")
    text = "\x00".join(parts) + "\x00\x00"
    buf = (ctypes.c_wchar * len(text))()
    for index, character in enumerate(text):
        buf[index] = character
    return buf


class LinuxCgroupBackend:
    """One disposable child cgroup. usage_usec covers this cgroup and descendants.

    memory.peak, when the controller exposes it, is cgroup memory, not RSS.
    The host subtree_control file is not modified.
    """

    def __init__(self, argv, *, cwd, env):
        if not argv or any(type(arg) is not str or "\x00" in arg for arg in argv):
            raise OwnedLaunchError("invalid_argv")
        self.argv = argv
        self.cwd = cwd
        self.env = env
        self.ledger = _Ledger()
        self.process = None
        self.leaf = None
        self._sampled_sum_peak = None
        self._closed = False
        parent = _own_cgroup_parent()
        if parent is None:
            raise OwnedLaunchUnsupported("cgroup_unavailable")
        leaf = parent / ("mnemion-owned-" + secrets.token_hex(8))
        try:
            leaf.mkdir(mode=0o755)
        except OSError:
            raise OwnedLaunchUnsupported("cgroup_unavailable") from None
        self.leaf = leaf
        if _usage_usec(leaf / "cpu.stat") is None:
            self._remove_leaf()
            raise OwnedLaunchUnsupported("cpu_stat_unavailable")

    def spawn(self) -> None:
        procs = str(self.leaf / "cgroup.procs")

        def move_before_exec():
            fd = os.open(procs, os.O_WRONLY | os.O_CLOEXEC)
            try:
                written = os.write(fd, str(os.getpid()).encode("ascii"))
            finally:
                os.close(fd)
            if written <= 0:
                raise OSError("cgroup assignment failed")

        self.process = subprocess.Popen(
            self.argv,
            cwd=self.cwd,
            env=self.env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=move_before_exec,
        )
        ticks = _linux_start_ticks(self.process.pid)
        if ticks is None:
            raise OwnedLaunchError("identity_unavailable")
        self.ledger.add_identity(self.process.pid, ticks)
        self.sample(self.ledger)

    def cpu_microseconds(self) -> int | None:
        if self.leaf is None:
            return None
        return _usage_usec(self.leaf / "cpu.stat")

    def still_active(self) -> bool | None:
        if self.leaf is None:
            return None
        try:
            raw = (self.leaf / "cgroup.procs").read_text(encoding="ascii")
        except (OSError, UnicodeError):
            return None
        return any(line.isdigit() for line in raw.splitlines())

    def wait_root(self, timeout_seconds: float) -> bool:
        if self.process is None:
            return False
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                return True
            time.sleep(0.02)
        return self.process.poll() is not None

    def sample(self, ledger: _Ledger) -> None:
        if self.leaf is None:
            return
        try:
            raw = (self.leaf / "cgroup.procs").read_text(encoding="ascii")
        except (OSError, UnicodeError):
            return
        current_sum = 0
        saw = 0
        for line in raw.splitlines():
            if not line.isdigit() or int(line) == os.getpid():
                continue
            pid = int(line)
            ticks = _linux_start_ticks(pid)
            residency = _linux_residency(pid)
            if ticks is None:
                continue
            if residency is None:
                ledger.add_identity(pid, ticks)
                continue
            ledger.observe(pid, ticks, current=residency["VmRSS"], high_water=residency["VmHWM"])
            current_sum += residency["VmRSS"]
            saw += 1
        if saw:
            self._sampled_sum_peak = (
                current_sum
                if self._sampled_sum_peak is None
                else max(self._sampled_sum_peak, current_sum)
            )

    def terminate(self) -> tuple[bool, str | None]:
        return _signal_cgroup(self.leaf)

    def snapshot(self) -> dict:
        cpu = self.cpu_microseconds()
        memory_peak = None if self.leaf is None else _single_counter(self.leaf / "memory.peak")
        return {
            "method": "linux_cgroup_v2_cpu_stat",
            "cpu_microseconds": cpu,
            "identities_missing": None,
            "cgroup_memory_peak_bytes": memory_peak,
            "observer_in_measured_group": _observer_in_cgroup(self.leaf),
            "sampled_peaks": {
                "sum_working_set_bytes": self._sampled_sum_peak,
                "sum_double_counts_shared": True,
                "not_a_budget_measurement": True,
                "sampled_pid_cpu_is_complete": False,
            },
            "kernel": {
                "cpu_usage_usec": cpu,
                "cpu_usage_includes_descendant_cgroups": True,
                "cgroup_memory_peak_bytes": memory_peak,
                "cgroup_memory_peak_is_per_process_rss": False,
            },
            "cpu_complete": cpu is not None,
            "unavailable": [] if memory_peak is not None else ["cgroup_memory_peak_bytes"],
        }

    def coverage(self, snapshot: dict, ledger: list[dict]) -> dict:
        complete = snapshot.get("cpu_complete") is True
        return {
            "platform": "linux",
            "status": "partial" if complete else "unsupported",
            "cpu_lifetime_complete": complete,
            "cpu_includes_exited_descendants": complete,
            "sampled_pid_cpu_is_complete": False,
            "rss_high_water": "per_process_kernel_while_alive"
            if any(row["kernel_high_water_while_observed"] for row in ledger)
            else "unavailable",
            "rss_high_water_covers_unseen_exited_processes": False,
            "cgroup_memory_peak_is_per_process_rss": False,
            "process_lifetime_count": "unavailable",
        }

    def close(self) -> tuple[bool, str | None]:
        if self._closed:
            return True, None
        self._closed = True
        if self.process is not None and self.process.poll() is None:
            _signal_cgroup(self.leaf)
            self.wait_root(2)
        failure = None
        if self.leaf is not None:
            try:
                self.leaf.rmdir()
            except OSError:
                failure = "cgroup_rmdir_failed"
            self.leaf = None
        return failure is None, failure

    def _remove_leaf(self) -> None:
        if self.leaf is not None:
            try:
                self.leaf.rmdir()
            except OSError:
                pass
            self.leaf = None


def _own_cgroup_parent() -> Path | None:
    try:
        raw = Path("/proc/self/cgroup").read_text(encoding="ascii", errors="strict")
    except (OSError, UnicodeError):
        return None
    relative = None
    for line in raw.splitlines():
        if line.startswith("0::"):
            relative = line[3:]
    if (
        not relative
        or relative == "/"
        or ".." in relative
        or not relative.startswith("/")
        or "(deleted)" in relative
    ):
        return None
    if not Path("/sys/fs/cgroup/cgroup.controllers").is_file():
        return None
    parent = Path(os.path.realpath("/sys/fs/cgroup" + relative))
    root = Path(os.path.realpath("/sys/fs/cgroup"))
    if parent == root or root not in parent.parents:
        return None
    return parent


def _observer_in_cgroup(leaf: Path | None) -> bool | None:
    if leaf is None:
        return None
    try:
        raw = (leaf / "cgroup.procs").read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return None
    return str(os.getpid()) in {line for line in raw.splitlines() if line.isdigit()}


def _signal_cgroup(leaf: Path | None) -> tuple[bool, str | None]:
    if leaf is None:
        return False, "cgroup_missing"
    try:
        raw = (leaf / "cgroup.procs").read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return False, "cgroup_procs_unreadable"
    if len(raw) > 1_000_000:
        return False, "cgroup_procs_too_large"
    failure = None
    for line in raw.splitlines():
        if not line.isdigit():
            continue
        pid = int(line)
        if pid == os.getpid():
            return False, "observer_inside_measured_cgroup"
        ticks = _linux_start_ticks(pid)
        if ticks is None:
            continue
        if not _pid_in_leaf(pid, leaf):
            failure = failure or "identity_left_cgroup"
            continue
        if not _signal_pinned(pid, ticks):
            failure = failure or "signal_failed"
    return failure is None, failure


def _pid_in_leaf(pid: int, leaf: Path) -> bool:
    try:
        raw = Path(f"/proc/{pid}/cgroup").read_text(encoding="ascii", errors="strict")
    except (OSError, UnicodeError):
        return False
    for line in raw.splitlines():
        if line.startswith("0::") and os.path.realpath(
            "/sys/fs/cgroup" + line[3:]
        ) == os.path.realpath(leaf):
            return True
    return False


def _signal_pinned(pid: int, ticks: int) -> bool:
    pidfd = None
    if hasattr(os, "pidfd_open"):
        try:
            pidfd = os.pidfd_open(pid)
        except OSError:
            return _linux_start_ticks(pid) != ticks
        if _linux_start_ticks(pid) != ticks:
            os.close(pidfd)
            return False
        try:
            signal.pidfd_send_signal(pidfd, signal.SIGKILL)
        except ProcessLookupError:
            return True
        except OSError:
            return False
        finally:
            os.close(pidfd)
        return True
    if _linux_start_ticks(pid) != ticks:
        return False
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return True


class DarwinBackend:
    """wait4 plus proc_pid_rusage resident size.

    Darwin has no job-wide lifetime counter. wait4 reports the direct child
    and descendants that child reaped. Orphans are outside that total, so
    coverage stays partial. Physical footprint is not read. Cleanup follows
    the owned process group after the root exits; that does not make the
    CPU total complete.
    """

    def __init__(self, argv, *, cwd, env):
        if not argv or any(type(arg) is not str or "\x00" in arg for arg in argv):
            raise OwnedLaunchError("invalid_argv")
        self.argv = argv
        self.cwd = cwd
        self.env = env
        self.ledger = _Ledger()
        self.process = None
        self.root_creation = None
        self._sampled_sum_peak = None
        self._closed = False
        self._waited = None
        self._reaped = False
        self._terminate_attempted = False
        self._libproc = None
        self._timebase = None

    def spawn(self) -> None:
        def own_group():
            os.setpgrp()

        self.process = subprocess.Popen(
            self.argv,
            cwd=self.cwd,
            env=self.env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=own_group,
        )
        self.sample(self.ledger)

    def cpu_microseconds(self) -> int | None:
        if self._waited is not None:
            return self._waited
        if self._reaped or self.process is None:
            return None
        usage = _darwin_rusage(self._library(), self.process.pid)
        if usage is None:
            return None
        own = _mach_to_microseconds(usage["user"] + usage["system"], self._base())
        children = _mach_to_microseconds(usage["child_user"] + usage["child_system"], self._base())
        if own is None or children is None:
            return None
        return own + children

    def still_active(self) -> bool | None:
        if self.process is None:
            return None
        self._capture_wait4()
        if not self._reaped:
            return True
        state = self._group_state()
        if state == "occupied":
            return True
        if state == "empty":
            return False
        return None

    def wait_root(self, timeout_seconds: float) -> bool:
        if self.process is None:
            return False
        deadline = time.monotonic() + timeout_seconds
        while True:
            self._capture_wait4()
            if self._reaped:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)

    def sample(self, ledger: _Ledger) -> None:
        if self.process is None:
            return
        root = self.process.pid
        seen = set()
        pending = [root]
        current_sum = 0
        saw = 0
        while pending and len(seen) < 64:
            pid = pending.pop()
            if pid in seen or pid <= 0 or pid == os.getpid():
                continue
            if pid != root and _darwin_ppid(self._library(), pid) not in seen:
                continue
            usage = _darwin_rusage(self._library(), pid)
            if usage is None:
                continue
            if pid == root:
                if self.root_creation is None:
                    self.root_creation = usage["start"]
                elif usage["start"] != self.root_creation:
                    continue
            seen.add(pid)
            ledger.observe(pid, usage["start"], current=usage["resident"], high_water=None)
            if type(usage["resident"]) is int:
                current_sum += usage["resident"]
                saw += 1
            for child in _darwin_children(self._library(), pid):
                if _darwin_ppid(self._library(), child) == pid:
                    pending.append(child)
        if saw:
            self._sampled_sum_peak = (
                current_sum
                if self._sampled_sum_peak is None
                else max(self._sampled_sum_peak, current_sum)
            )

    def terminate(self) -> tuple[bool, str | None]:
        if self.process is None:
            return False, "process_missing"
        if self._terminate_attempted:
            return False, "already_attempted"
        self._terminate_attempted = True
        pgid = self.process.pid
        if pgid <= 1 or pgid == os.getpid() or self.root_creation is None:
            return False, "group_unverified"
        leader = _darwin_rusage(self._library(), pgid)
        if leader is not None and leader["start"] != self.root_creation:
            return False, "pid_reused"
        try:
            os.kill(-pgid, getattr(signal, "SIGKILL", 9))
        except ProcessLookupError:
            return True, None
        except OSError:
            return False, "signal_failed"
        return True, None

    def snapshot(self) -> dict:
        self._capture_wait4()
        cpu = self._waited if self._reaped else self.cpu_microseconds()
        return {
            "method": "darwin_wait4_and_resident_size",
            "cpu_microseconds": cpu,
            "identities_missing": None,
            "observer_in_measured_group": False,
            "sampled_peaks": {
                "sum_working_set_bytes": self._sampled_sum_peak,
                "sum_double_counts_shared": True,
                "not_a_budget_measurement": True,
                "sampled_pid_cpu_is_complete": False,
            },
            "kernel": {
                "wait4_direct_child_cpu_microseconds": self._waited,
                "includes_only_reaped_descendants": True,
                "footprint_used_as_rss": False,
            },
            "cpu_complete": False,
            "unavailable": [
                "darwin_unreaped_descendant_cpu",
                "darwin_rss_high_water",
            ],
        }

    def coverage(self, snapshot: dict, ledger: list[dict]) -> dict:
        return {
            "platform": "darwin",
            "status": "partial",
            "cpu_lifetime_complete": False,
            "cpu_includes_exited_descendants": False,
            "sampled_pid_cpu_is_complete": False,
            "rss_high_water": "sampled_current"
            if any(row["first_working_set_bytes"] is not None for row in ledger)
            else "unavailable",
            "rss_high_water_covers_unseen_exited_processes": False,
            "cgroup_memory_peak_is_per_process_rss": False,
        }

    def close(self) -> tuple[bool, str | None]:
        if self._closed:
            return True, None
        self._closed = True
        if self.process is None:
            return False, "process_missing"
        self._capture_wait4()
        if not self._terminate_attempted and self._group_state() != "empty":
            ok, failure = self.terminate()
            if not ok:
                return False, failure
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and self._group_state() == "occupied":
            self._capture_wait4()
            time.sleep(0.02)
        state = self._group_state()
        if state == "empty":
            return True, None
        if state == "reused":
            return False, "pid_reused"
        if state == "occupied":
            return False, "descendants_survived"
        return False, "group_unverified"

    def _group_state(self) -> str:
        """empty, occupied, reused, or unverified. Never a full pid scan."""
        if self.process is None:
            return "unverified"
        pgid = self.process.pid
        if pgid <= 1 or self.root_creation is None:
            return "unverified"
        leader = _darwin_rusage(self._library(), pgid)
        if leader is not None and leader["start"] != self.root_creation:
            return "reused"
        members = _darwin_group_pids(self._library(), pgid)
        if members is None:
            return "unverified"
        if any(pid > 0 and pid != os.getpid() for pid in members):
            return "occupied"
        return "empty"

    def _capture_wait4(self) -> None:
        if self.process is None or self._reaped:
            return
        try:
            waited_pid, status, usage = os.wait4(self.process.pid, os.WNOHANG)
        except ChildProcessError:
            self._reaped = True
            return
        except (AttributeError, OSError):
            return
        if waited_pid != self.process.pid:
            return
        returncode = _wait_status_returncode(status)
        if returncode is None:
            return
        self._reaped = True
        if self.process.returncode is None:
            self.process.returncode = returncode
        self._waited = _rusage_microseconds(usage)

    def _library(self):
        if self._libproc is None:
            self._libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
            self._libproc.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
            self._libproc.proc_pid_rusage.restype = ctypes.c_int
            self._libproc.proc_pidinfo.argtypes = [
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint64,
                ctypes.c_void_p,
                ctypes.c_int,
            ]
            self._libproc.proc_pidinfo.restype = ctypes.c_int
            self._libproc.proc_listchildpids.argtypes = [
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.c_int,
            ]
            self._libproc.proc_listchildpids.restype = ctypes.c_int
            self._libproc.proc_listpids.argtypes = [
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.c_void_p,
                ctypes.c_int,
            ]
            self._libproc.proc_listpids.restype = ctypes.c_int
        return self._libproc

    def _base(self) -> tuple[int, int] | None:
        if self._timebase is not None:
            return self._timebase
        system = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)

        class Timebase(ctypes.Structure):
            _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]

        system.mach_timebase_info.argtypes = [ctypes.POINTER(Timebase)]
        system.mach_timebase_info.restype = ctypes.c_int
        info = Timebase()
        if system.mach_timebase_info(ctypes.byref(info)) != 0 or not info.denom:
            return None
        self._timebase = (int(info.numer), int(info.denom))
        return self._timebase


class _DarwinRUsage(ctypes.Structure):
    _fields_ = [
        ("uuid", ctypes.c_uint8 * 16),
        ("user", ctypes.c_uint64),
        ("system", ctypes.c_uint64),
        ("pkg_idle", ctypes.c_uint64),
        ("interrupt", ctypes.c_uint64),
        ("pageins", ctypes.c_uint64),
        ("wired", ctypes.c_uint64),
        ("resident", ctypes.c_uint64),
        ("footprint_unused", ctypes.c_uint64),
        ("start", ctypes.c_uint64),
        ("exit", ctypes.c_uint64),
        ("child_user", ctypes.c_uint64),
        ("child_system", ctypes.c_uint64),
        ("child_pkg_idle", ctypes.c_uint64),
        ("child_interrupt", ctypes.c_uint64),
        ("child_pageins", ctypes.c_uint64),
        ("child_elapsed", ctypes.c_uint64),
    ]


def _wait_status_returncode(status: int) -> int | None:
    """BSD wait status. Stopped (0x7f) is not an exit. Signaled keeps the low 7 bits."""
    if type(status) is not int or status < 0:
        return None
    low = status & 0x7F
    if low == 0:
        return (status >> 8) & 0xFF
    if low == 0x7F:
        return None
    return -low


def _rusage_microseconds(usage) -> int | None:
    """Python resource rusage stores ru_utime and ru_stime as float seconds."""
    try:
        user = usage.ru_utime
        system = usage.ru_stime
    except AttributeError:
        return None
    if type(user) is not float or type(system) is not float:
        return None
    if user < 0 or system < 0 or user != user or system != system:
        return None
    if user == float("inf") or system == float("inf"):
        return None
    microseconds = int((user + system) * 1_000_000)
    if microseconds < 0:
        return None
    return microseconds


def _darwin_group_pids(library, pgid: int) -> list[int] | None:
    """PIDs in one process group. PROC_PGRP_ONLY is 2 in Apple proc_info.h.

    A null buffer asks the kernel for `(nprocs + 20) * sizeof(int)`, which is
    every process plus margin, not this group (xnu proc_info.c). libproc turns
    a failed call into 0 and sets errno, while a real empty group is also 0
    with errno clear (libproc.c). This query uses a bounded buffer. A full
    buffer can hide another member, so that result stays unverified.
    """
    if library is None or type(pgid) is not int or pgid <= 1:
        return None
    cap = 64 * ctypes.sizeof(ctypes.c_int)
    buf = ctypes.create_string_buffer(cap)
    ctypes.set_errno(0)
    try:
        written = library.proc_listpids(2, pgid, buf, cap)
    except (AttributeError, OSError):
        return None
    errno = ctypes.get_errno()
    if type(written) is not int or written < 0 or written > cap:
        return None
    if written == cap or errno != 0:
        return None
    if written == 0:
        return []
    if written % ctypes.sizeof(ctypes.c_int) != 0:
        return None
    count = written // ctypes.sizeof(ctypes.c_int)
    values = ctypes.cast(buf, ctypes.POINTER(ctypes.c_int))
    pids = []
    for index in range(count):
        pid = int(values[index])
        if pid <= 0:
            return None
        pids.append(pid)
    return pids


def _darwin_rusage(library, pid: int) -> dict | None:
    info = _DarwinRUsage()
    if library.proc_pid_rusage(pid, 1, ctypes.byref(info)) != 0:
        return None
    return {
        "user": int(info.user),
        "system": int(info.system),
        "child_user": int(info.child_user),
        "child_system": int(info.child_system),
        "resident": int(info.resident),
        "start": int(info.start),
    }


def _mach_to_microseconds(ticks: int, timebase: tuple[int, int] | None) -> int | None:
    if timebase is None or ticks < 0:
        return None
    numer, denom = timebase
    return ticks * numer // denom // 1000


def _darwin_ppid(library, pid: int) -> int | None:
    raw = ctypes.create_string_buffer(256)
    size = library.proc_pidinfo(pid, 3, 0, raw, 256)
    if size < 20:
        return None
    values = ctypes.cast(raw, ctypes.POINTER(ctypes.c_uint32))
    if int(values[3]) != pid:
        return None
    return int(values[4])


def _darwin_children(library, pid: int) -> list[int]:
    needed = library.proc_listchildpids(pid, None, 0)
    if needed <= 0 or needed > 256 * 4:
        return []
    buf = ctypes.create_string_buffer(needed)
    written = library.proc_listchildpids(pid, buf, needed)
    if written <= 0:
        return []
    count = min(written // ctypes.sizeof(ctypes.c_int), 64)
    values = ctypes.cast(buf, ctypes.POINTER(ctypes.c_int))
    return [int(values[index]) for index in range(count) if int(values[index]) > 0]


def exercise_cleanup_failure() -> dict:
    """One failed terminate of an invalid handle. No process is signaled."""
    if sys.platform != "win32":
        return {"exercised": False, "reason": "windows_job_only", "retried": False}
    api = _WinApi()
    ok, failure = api.terminate_job(None)
    return {"exercised": True, "ok": ok, "failure": failure, "retried": False}
