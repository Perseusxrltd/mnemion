"""Diagnostic owned-launch resource accounting.

The measured child is placed in a disposable OS group before it executes.
Lifetime CPU comes from that group, not from a later poll of surviving PIDs.
Working-set figures stay per process. Cgroup memory and Windows job commit
are never reported as RSS. On Windows, PeakWorkingSetSize is read again
through retained query handles only after the job has no active process.
Missing counters stay null.

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
# PROCESS_QUERY_LIMITED_INFORMATION. IsProcessInJob, GetProcessTimes,
# GetExitCodeProcess, and GetProcessMemoryInfo accept this right.
# https://learn.microsoft.com/en-us/windows/win32/api/jobapi/nf-jobapi-isprocessinjob
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
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
    """Where the installed workload is attached. Does not launch anything."""
    return {
        "wired_into_smoke_installed_hosting": True,
        "delivery_is_canonical_workload": False,
        "launcher": "studio/electron/scripts/smoke-installed-hosting.mjs",
        "function": "runInstalledTelemetryResources",
        "resource_entry": "deploy.owned_installed_launch",
        "canonical_cycles": 128,
        "canonical_checkpoints": 9,
        "cases": 6,
        "next_call": (
            "start_owned_launch before the installed executable executes; "
            "the two-launch delivery check is not this workload"
        ),
        "budget": {
            "additional_rss_bytes_per_process": ADDITIONAL_RSS_BUDGET_BYTES,
            "cpu_one_core_fraction": CPU_BUDGET_ONE_CORE_FRACTION,
            "status": BUDGET_STATUS,
            "compared": False,
        },
        "limitations": [
            "darwin_wait4_direct_child_only",
            "group_sampling_is_not_complete_cpu",
            "rss_high_water_is_sampled",
            "resource_acceptance_unestablished",
        ],
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
            # Distinct from the live flag above. True only after a successful
            # post-drain query. A later failed query clears it and keeps the bytes.
            "peak_working_set_final": False,
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

    def note_final_peak(self, pid: int, creation: int, high_water: int) -> bool:
        """Record a post-drain peak. Does not change the live-sample flag."""
        identity = f"{pid}:{creation}"
        row = self.rows.get(identity)
        if row is None:
            row = self.add_identity(pid, creation)
        if row is None or type(high_water) is not int or high_water < 0:
            if row is not None:
                row["peak_working_set_final"] = False
            return False
        previous = row["peak_working_set_bytes"]
        row["peak_working_set_bytes"] = (
            high_water if previous is None else max(previous, high_water)
        )
        row["peak_working_set_final"] = True
        return True

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
        linux_group = isinstance(self.backend, LinuxCgroupBackend)
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
                # Linux close owns the one five-second cleanup deadline.
                # Windows spends that same single allowance on the job, not
                # on another wait after the root handle is already signaled.
                # Darwin still waits for the root handle only.
                if isinstance(self.backend, WindowsJobBackend):
                    if self.backend.wait_until_drained(5) is not True and cleanup_failure is None:
                        cleanup_failure = "drain_timeout"
                elif not linux_group:
                    self.backend.wait_root(5)
            if not linux_group:
                snapshot = self.backend.snapshot()
        except Exception:
            if cleanup_failure is None:
                cleanup_failure = "finish_failed"
        ok, failure = self.backend.close()
        if linux_group:
            final = getattr(self.backend, "_final_snapshot", None)
            if type(final) is dict:
                snapshot = final
            else:
                snapshot = {
                    "cpu_microseconds": None,
                    "cpu_complete": False,
                    "unavailable": ["lifetime_cpu_microseconds"],
                }
        if not ok and cleanup_failure is None:
            cleanup_failure = failure or "close_failed"
        retried = getattr(self.backend, "_cleanup_retried", False) is True
        return self._report(snapshot, cleanup_failure, terminated, timed_out, retried)

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
        self,
        snapshot: dict,
        cleanup_failure: str | None,
        terminated: bool,
        timed_out: bool,
        retried: bool = False,
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
            "observation_gaps": snapshot.get("observation_gaps"),
            "sampled_peaks": snapshot.get("sampled_peaks"),
            "kernel": snapshot.get("kernel"),
            "observer_in_measured_group": snapshot.get("observer_in_measured_group"),
            "cleanup": {
                "ok": cleanup_failure is None,
                "failure": cleanup_failure,
                "retried": retried is True,
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


class _RetainedQuery:
    __slots__ = ("pid", "creation", "handle")

    def __init__(self, pid: int, creation: int, handle):
        self.pid = pid
        self.creation = creation
        self.handle = handle


class WindowsJobBackend:
    """A job created and assigned before the child thread runs.

    TotalUserTime and TotalKernelTime keep terminated processes.
    PeakJobMemoryUsed is commit charge, not working set.
    Query handles use PROCESS_QUERY_LIMITED_INFORMATION only. A process is
    admitted when IsProcessInJob on that handle says it is running in this
    job. The same live process is not opened again. Final PeakWorkingSetSize
    is read on the retained handles after ActiveProcesses is zero.
    kernel_high_water_while_observed means a live query succeeded. It does
    not mean the stored peak is that live sample, and it is not the final flag.
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
        self._close_result = (True, None)
        self._lock = threading.Lock()
        self._retained: dict[str, _RetainedQuery] = {}
        self._live_pid: dict[int, str] = {}
        self._gaps = {
            "query_handle_unavailable_observations": 0,
            "membership_rejected": 0,
            "identity_or_membership_unproven": 0,
            "final_query_failed": 0,
            "pid_list_unreadable": False,
        }

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
        in_job = api.is_in_job(process, job)
        if creation is None or in_job is not True:
            api.terminate_process(process)
            raise OwnedLaunchError("not_in_job_before_resume")
        self.root_creation = creation
        if not self._retain_root(process, pid, creation):
            api.terminate_process(process)
            raise OwnedLaunchError("root_query_handle_unavailable")
        if api.resume(thread) == 0xFFFFFFFF:
            api.terminate_job(job)
            raise OwnedLaunchError("resume_failed")
        self.sample(self.ledger)

    def _retain_root(self, process, pid: int, creation: int) -> bool:
        """Hold a limited-query handle before the root is allowed to run."""
        api = self._api
        handle = api.duplicate_query(process)
        if not handle:
            handle = api.open_query(pid)
            opened_creation = None if not handle else api.creation_ticks(handle)
            if handle and opened_creation != creation:
                api.close(handle)
                self._gaps["membership_rejected"] += 1
                self.ledger.add_identity(pid, creation)
                return False
        if not handle:
            self.ledger.add_identity(pid, creation)
            self._gaps["identity_or_membership_unproven"] += 1
            return False
        member = api.is_in_job(handle, self.job)
        copied = api.creation_ticks(handle)
        if member is not True or copied != creation:
            api.close(handle)
            if member is False or (copied is not None and copied != creation):
                self._gaps["membership_rejected"] += 1
            else:
                self._gaps["identity_or_membership_unproven"] += 1
            self.ledger.add_identity(pid, creation)
            return False
        if not self._keep_handle(pid, creation, handle, self.ledger):
            return False
        self._read_live(self._retained[f"{pid}:{creation}"], self.ledger)
        return True

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
        """Return when the root handle is signaled. Descendants may still be alive."""
        if not self.process:
            return False
        return self._api.wait(self.process, timeout_seconds)

    def wait_until_drained(self, timeout_seconds: float) -> bool:
        """One bounded poll for ActiveProcesses == 0. Not a second cleanup budget."""
        if type(timeout_seconds) not in (int, float) or float(timeout_seconds) <= 0:
            return False
        deadline = time.monotonic() + float(timeout_seconds)
        while True:
            info = self._api.accounting(self.job) if self.job else None
            if info is not None and info["active_processes"] == 0:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.05, remaining))

    def sample(self, ledger: _Ledger) -> None:
        with self._lock:
            self._sample_locked(ledger)

    def _sample_locked(self, ledger: _Ledger) -> None:
        if self._closed or not self.job:
            return
        members = self._api.job_pids(self.job)
        if members is None:
            self._gaps["pid_list_unreadable"] = True
            return
        if getattr(self._api, "pid_list_truncated", False):
            ledger.truncated = True
        current_sum = 0
        saw = 0
        seen: set[int] = set()
        for pid in members:
            if pid == os.getpid() or pid in seen:
                continue
            seen.add(pid)
            current = self._sample_pid(pid, ledger)
            if current is not None:
                current_sum += current
                saw += 1
        if saw:
            self._sampled_sum_peak = (
                current_sum
                if self._sampled_sum_peak is None
                else max(self._sampled_sum_peak, current_sum)
            )

    def _sample_pid(self, pid: int, ledger: _Ledger) -> int | None:
        identity = self._live_pid.get(pid)
        held = None if identity is None else self._retained.get(identity)
        if held is not None and held.handle and self._same_live_member(held):
            return self._read_live(held, ledger)
        if identity is not None:
            self._live_pid.pop(pid, None)
        return self._open_member(pid, ledger)

    def _same_live_member(self, held: _RetainedQuery) -> bool:
        # Both calls use the retained handle. A still-active process cannot
        # have its PID reused. IsProcessInJob is "running in this job".
        if self._api.process_is_live(held.handle) is not True:
            return False
        if self._api.is_in_job(held.handle, self.job) is not True:
            return False
        return self._api.creation_ticks(held.handle) == held.creation

    def _open_member(self, pid: int, ledger: _Ledger) -> int | None:
        if len(self._retained) >= MAX_LEDGER:
            ledger.truncated = True
            return None
        handle = self._api.open_query(pid)
        if not handle:
            # Each failed OpenProcess is one observation. Access denial and
            # any other error count the same way; exit is not proved. The
            # total is failed observations, not unique missing processes.
            # identities_missing reconciles TotalProcesses with ledger rows.
            if not any(item.pid == pid for item in self._retained.values()):
                self._gaps["query_handle_unavailable_observations"] += 1
            return None
        try:
            member = self._api.is_in_job(handle, self.job)
            creation = self._api.creation_ticks(handle)
            if member is not True or creation is None:
                if member is False:
                    self._gaps["membership_rejected"] += 1
                else:
                    self._gaps["identity_or_membership_unproven"] += 1
                return None
            if not self._keep_handle(pid, creation, handle, ledger):
                handle = None
                return None
            handle = None
            held = self._retained[f"{pid}:{creation}"]
            return self._read_live(held, ledger)
        finally:
            if handle:
                self._api.close(handle)

    def _keep_handle(self, pid: int, creation: int, handle, ledger: _Ledger) -> bool:
        identity = f"{pid}:{creation}"
        existing = self._retained.get(identity)
        if existing is not None:
            self._api.close(handle)
            if existing.handle:
                self._live_pid[pid] = identity
            return True
        if len(self._retained) >= MAX_LEDGER or (
            len(ledger.rows) >= MAX_LEDGER and identity not in ledger.rows
        ):
            ledger.truncated = True
            self._api.close(handle)
            return False
        if ledger.add_identity(pid, creation) is None:
            ledger.truncated = True
            self._api.close(handle)
            return False
        self._retained[identity] = _RetainedQuery(pid, creation, handle)
        self._live_pid[pid] = identity
        return True

    def _read_live(self, held: _RetainedQuery, ledger: _Ledger) -> int | None:
        memory = self._api.working_set(held.handle)
        if type(memory) is not dict:
            return None
        current = memory.get("working_set")
        peak = memory.get("peak_working_set")
        if type(current) is not int or type(peak) is not int:
            return None
        ledger.observe(held.pid, held.creation, current=current, high_water=peak)
        return current

    def _read_final_peaks_locked(self) -> None:
        failed = 0
        for identity, held in list(self._retained.items()):
            memory = None
            if held.handle:
                creation = self._api.creation_ticks(held.handle)
                if creation == held.creation:
                    memory = self._api.working_set(held.handle)
            peak = None if type(memory) is not dict else memory.get("peak_working_set")
            if type(peak) is int and self.ledger.note_final_peak(held.pid, held.creation, peak):
                continue
            failed += 1
            row = self.ledger.rows.get(identity)
            if row is not None:
                row["peak_working_set_final"] = False
        self._gaps["final_query_failed"] = failed

    def terminate(self) -> tuple[bool, str | None]:
        if not self.job:
            return False, "job_missing"
        return self._api.terminate_job(self.job)

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict:
        info = self._api.accounting(self.job) if self.job else None
        extended = self._api.extended(self.job) if self.job else None
        drained = info is not None and info["active_processes"] == 0
        if drained:
            self._read_final_peaks_locked()
        cpu = None if info is None else (info["user_100ns"] + info["kernel_100ns"]) // 10
        missing = None
        if info is not None:
            missing = info["total_processes"] - len(self.ledger.rows)
            if missing < 0:
                missing = None
        pids = self._api.job_pids(self.job) if self.job else None
        if getattr(self._api, "pid_list_truncated", False):
            self.ledger.truncated = True
        state = self._working_set_state(drained)
        unavailable = [] if extended is not None else ["job_commit_peak"]
        self._gap_tokens(unavailable)
        return {
            "method": "windows_job_before_resume",
            "cpu_microseconds": cpu,
            "identities_missing": missing,
            "observer_in_measured_group": None if pids is None else os.getpid() in pids,
            "working_set_accounting": state,
            "observation_gaps": {
                "query_handle_unavailable_observations": self._gaps[
                    "query_handle_unavailable_observations"
                ],
                "membership_rejected": self._gaps["membership_rejected"],
                "identity_or_membership_unproven": self._gaps["identity_or_membership_unproven"],
                "final_query_failed": self._gaps["final_query_failed"],
                "pid_list_unreadable": self._gaps["pid_list_unreadable"] is True,
                "ledger_truncated": self.ledger.truncated is True,
                "active_processes": None if info is None else info["active_processes"],
            },
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
            "cpu_complete": drained and cpu is not None,
            "unavailable": unavailable,
        }

    def _working_set_state(self, drained: bool) -> str:
        rows = list(self.ledger.rows.values())
        if drained and rows and all(row.get("peak_working_set_final") is True for row in rows):
            return "final_on_observed_handles"
        if any(row.get("peak_working_set_bytes") is not None for row in rows):
            return "latest_observation"
        return "unavailable"

    def _gap_tokens(self, unavailable: list[str]) -> None:
        if self._gaps["query_handle_unavailable_observations"]:
            unavailable.append("query_handle_unavailable")
        if self._gaps["membership_rejected"] or self._gaps["identity_or_membership_unproven"]:
            unavailable.append("process_identity_or_membership_unproven")
        if self._gaps["pid_list_unreadable"]:
            unavailable.append("job_process_list_unreadable")
        if any(row.get("peak_working_set_final") is not True for row in self.ledger.rows.values()):
            unavailable.append("final_working_set_peak")

    def coverage(self, snapshot: dict, ledger: list[dict]) -> dict:
        cpu = snapshot.get("cpu_microseconds")
        complete = snapshot.get("cpu_complete") is True and type(cpu) is int and cpu >= 0
        has_counter = type(cpu) is int and cpu >= 0
        state = snapshot.get("working_set_accounting")
        if state not in ("final_on_observed_handles", "latest_observation", "unavailable"):
            state = "unavailable"
        # A counter can exist before the job is empty. That reading is partial,
        # not a finished lifetime. Final peaks on handles we already hold do
        # not cover processes whose query handle was unavailable, or processes
        # past the ledger cap. Status stays partial even when every observed
        # row is final.
        return {
            "platform": "windows",
            "status": "partial" if complete or has_counter else "unsupported",
            "cpu_lifetime_complete": complete,
            "cpu_includes_exited_descendants": complete,
            "sampled_pid_cpu_is_complete": False,
            "rss_high_water": "per_process_kernel_while_alive"
            if any(row["kernel_high_water_while_observed"] for row in ledger)
            else "unavailable",
            "rss_high_water_covers_unseen_exited_processes": False,
            "cgroup_memory_peak_is_per_process_rss": False,
            "working_set_accounting": state,
            "retained_handles_cover_unseen_processes": False,
        }

    def close(self) -> tuple[bool, str | None]:
        with self._lock:
            if self._closed:
                return self._close_result
            self._closed = True
            failure = None
            ordered = []
            seen = set()
            for held in self._retained.values():
                if held.handle and held.handle not in seen:
                    seen.add(held.handle)
                    ordered.append(held.handle)
                held.handle = None
            self._retained.clear()
            self._live_pid.clear()
            for handle in (self.thread, self.process, self.job):
                if handle and handle not in seen:
                    seen.add(handle)
                    ordered.append(handle)
            self.thread = self.process = self.job = None
            for handle in ordered:
                ok, code = self._api.close(handle)
                if not ok and failure is None:
                    failure = code
            self._close_result = (failure is None, failure)
            return self._close_result


class _WinApi:
    def __init__(self):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.pid_list_truncated = False
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
        k.IsProcessInJob.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.BOOL),
        ]
        k.IsProcessInJob.restype = wintypes.BOOL
        k.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
        k.GetExitCodeProcess.restype = wintypes.BOOL
        k.GetCurrentProcess.argtypes = []
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.DuplicateHandle.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        k.DuplicateHandle.restype = wintypes.BOOL

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
        if int(info.assigned) > count:
            self.pid_list_truncated = True
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
        handle = self.kernel.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        return handle or None

    def duplicate_query(self, process):
        """Narrow an existing process handle. Do not duplicate its full access."""
        if not process:
            return None
        current = self.kernel.GetCurrentProcess()
        target = ctypes.c_void_p()
        ok = self.kernel.DuplicateHandle(
            current,
            process,
            current,
            ctypes.byref(target),
            _PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            0,
        )
        if not ok or not target.value:
            return None
        return target.value

    def is_in_job(self, process, job) -> bool | None:
        if not process or not job:
            return None
        result = wintypes.BOOL()
        ok = self.kernel.IsProcessInJob(process, job, ctypes.byref(result))
        if not ok:
            return None
        return bool(result.value)

    def process_is_live(self, process) -> bool | None:
        if not process:
            return None
        code = wintypes.DWORD()
        ok = self.kernel.GetExitCodeProcess(process, ctypes.byref(code))
        if not ok:
            return None
        return int(code.value) == _STILL_ACTIVE

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
        self._cleanup_retried = False
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
        cpu = snapshot.get("cpu_microseconds")
        has_counter = type(cpu) is int and cpu >= 0
        return {
            "platform": "linux",
            "status": "partial" if complete or has_counter else "unsupported",
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

    def close(self, drain_seconds: float = 5.0) -> tuple[bool, str | None]:
        """Drain this owned group, read its counter, then remove the leaf.

        Root exit and descendant drain share one deadline of at most five
        seconds. The lifetime counter is read only after the group is empty
        and before removal. A failed removal keeps the leaf and the stored
        failure. A later close does not turn that failure into success.
        """
        if self._closed:
            return getattr(self, "_close_result", (False, "cgroup_rmdir_failed"))
        self._closed = True
        self._cleanup_retried = False
        self._final_snapshot = None
        if type(drain_seconds) not in (int, float) or not 0 < float(drain_seconds) <= 5:
            drain_seconds = 5.0
        deadline = time.monotonic() + float(drain_seconds)
        if self.process is not None and self.process.poll() is None:
            _signal_cgroup(self.leaf)
            remaining = deadline - time.monotonic()
            if remaining > 0:
                self.wait_root(remaining)
        if self.leaf is None:
            self._final_snapshot = {
                "method": "linux_cgroup_v2_cpu_stat",
                "cpu_microseconds": None,
                "cpu_complete": False,
                "unavailable": ["lifetime_cpu_microseconds"],
            }
            self._close_result = (False, "cgroup_missing")
            return self._close_result
        removal_attempts = 0
        while True:
            if self._member_state() == "empty":
                if self._final_snapshot is None:
                    self._final_snapshot = self.snapshot()
                removal_attempts += 1
                if removal_attempts > 1:
                    self._cleanup_retried = True
                if self._rmdir_leaf():
                    self.leaf = None
                    self._close_result = (True, None)
                    return self._close_result
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        if self._final_snapshot is None:
            partial = self.snapshot()
            partial["cpu_complete"] = False
            self._final_snapshot = partial
        self._close_result = (False, "cgroup_rmdir_failed")
        return self._close_result

    def _member_state(self) -> str:
        """empty, populated, or unreadable. This owned leaf only."""
        if self.leaf is None:
            return "unreadable"
        try:
            raw = (self.leaf / "cgroup.procs").read_text(encoding="ascii")
        except (OSError, UnicodeError):
            return "unreadable"
        if any(line.isdigit() for line in raw.splitlines()):
            return "populated"
        try:
            events = (self.leaf / "cgroup.events").read_text(encoding="ascii")
        except (OSError, UnicodeError):
            return "empty"
        for line in events.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == "populated" and parts[1] == "1":
                return "populated"
        return "empty"

    def _rmdir_leaf(self) -> bool:
        if self.leaf is None:
            return False
        try:
            self.leaf.rmdir()
        except OSError:
            return False
        return not self.leaf.exists()

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
    """wait4, proc_pid_rusage current resident size, and a live task-name peak.

    Darwin has no job-wide lifetime counter. wait4 reports the direct child
    and descendants that child reaped. Orphans are outside that total.
    MACH_TASK_BASIC_INFO.resident_size_max is the live kernel high water of a
    process that is still queried through a task-name port. It is not a final
    lifetime peak and it does not cover processes that have already exited.
    Physical footprint is not read. Cleanup follows the owned process group
    after the root exits; that does not make the CPU total complete.
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
        self._port_release_failure = None
        self._libproc = None
        self._libsystem = None
        self._timebase = None
        self._sample_lock = threading.Lock()

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
        # Same lock as wait4. After that lock is held, a reaped root keeps the
        # wait4 total (including a missing one). Live rusage is used only when
        # its creation still is the frozen root. This does not freeze a new one.
        with self._sample_lock:
            if self._waited is not None:
                return self._waited
            if self._reaped or self.process is None:
                return None
            usage = _darwin_rusage(self._library(), self.process.pid)
            if self._waited is not None or self._reaped:
                return self._waited
            if usage is None:
                return None
            if type(self.root_creation) is not int or usage.get("start") != self.root_creation:
                return None
            own = _mach_to_microseconds(usage["user"] + usage["system"], self._base())
            children = _mach_to_microseconds(
                usage["child_user"] + usage["child_system"], self._base()
            )
            if self._waited is not None or self._reaped:
                return self._waited
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
        with self._sample_lock:
            if self.process is None:
                return
            # A reaped root whose creation was never frozen must not adopt the
            # next process that reuses the pid.
            if self._reaped and self.root_creation is None:
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
                parent = None
                if pid != root:
                    parent = _darwin_ppid(self._library(), pid)
                    if parent not in seen:
                        continue
                charged = self._charge_owned(pid, parent=parent, root=root)
                if charged is None:
                    continue
                seen.add(pid)
                ledger.observe(
                    pid,
                    charged["start"],
                    current=charged["resident"],
                    high_water=charged["high_water"],
                )
                if type(charged["resident"]) is int:
                    current_sum += charged["resident"]
                    saw += 1
                children = _darwin_children(self._library(), pid)
                # None is unverified. It is not an empty child set, and none of
                # its pids are added.
                if children is None:
                    continue
                for child in children:
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
                "orphans_outside_wait4": True,
                "footprint_used_as_rss": False,
                "rss_high_water_is_final_lifetime": False,
            },
            "cpu_complete": False,
            "unavailable": [
                "darwin_unreaped_descendant_cpu",
                "darwin_orphan_cpu",
                "darwin_final_lifetime_rss",
            ],
        }

    def coverage(self, snapshot: dict, ledger: list[dict]) -> dict:
        del snapshot
        observed_kernel = any(row.get("kernel_high_water_while_observed") is True for row in ledger)
        observed_current = any(row.get("first_working_set_bytes") is not None for row in ledger)
        missing_peak = any(row.get("peak_working_set_bytes") is None for row in ledger)
        if observed_kernel and missing_peak:
            rss = "live_kernel_high_water_partial"
        elif observed_kernel:
            rss = "live_kernel_high_water"
        elif observed_current:
            rss = "sampled_current"
        else:
            rss = "unavailable"
        return {
            "platform": "darwin",
            "status": "partial",
            "cpu_lifetime_complete": False,
            "cpu_includes_exited_descendants": False,
            "sampled_pid_cpu_is_complete": False,
            "rss_high_water": rss,
            "rss_high_water_covers_unseen_exited_processes": False,
            "cgroup_memory_peak_is_per_process_rss": False,
        }

    def close(self) -> tuple[bool, str | None]:
        if self._closed:
            return self._close_result
        self._closed = True
        self._close_result = self._close_group()
        return self._close_result

    def _close_group(self) -> tuple[bool, str | None]:
        if self.process is None:
            return self._with_port_release(False, "process_missing")
        self._capture_wait4()
        if not self._terminate_attempted and self._group_state() != "empty":
            ok, failure = self.terminate()
            if not ok:
                return self._with_port_release(False, failure)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and self._group_state() == "occupied":
            self._capture_wait4()
            time.sleep(0.02)
        state = self._group_state()
        if state == "empty":
            return self._with_port_release(True, None)
        if state == "reused":
            return self._with_port_release(False, "pid_reused")
        if state == "occupied":
            return self._with_port_release(False, "descendants_survived")
        return self._with_port_release(False, "group_unverified")

    def _with_port_release(self, ok: bool, failure: str | None) -> tuple[bool, str | None]:
        """An empty process group must not hide a name port that was not dropped."""
        if ok and self._port_release_failure is not None:
            return False, self._port_release_failure
        return ok, failure

    def _remember_port_release(self, basic) -> None:
        if self._port_release_failure is not None or type(basic) is not dict:
            return
        error = basic.get("port_deallocate_error")
        kr = basic.get("port_deallocate_kern_return")
        if error is not None or (type(kr) is int and kr != 0):
            self._port_release_failure = _PORT_RELEASE_FAILED

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
        with self._sample_lock:
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

    def _charge_owned(self, pid: int, *, parent: int | None, root: int) -> dict | None:
        """Record one owned pid. Identity is checked before and after the port."""
        library = self._library()
        before = _darwin_rusage(library, pid)
        if before is None or type(before.get("start")) is not int:
            return None
        if pid == root:
            if self.root_creation is None:
                if self._reaped:
                    return None
                self.root_creation = before["start"]
            if before["start"] != self.root_creation:
                return None
        elif type(parent) is not int or _darwin_ppid(library, pid) != parent:
            return None
        basic = _darwin_task_rss(self._task_system(), pid)
        self._remember_port_release(basic)
        after = _darwin_rusage(library, pid)
        if after is None or after.get("start") != before["start"]:
            return None
        if pid == root:
            if after["start"] != self.root_creation:
                return None
        elif _darwin_ppid(library, pid) != parent:
            return None
        resident = after.get("resident")
        if type(resident) is not int or resident < 0:
            resident = None
        high = None
        if (
            type(basic) is dict
            and basic.get("accepted") is True
            and basic.get("kr") == 0
            and basic.get("count") == _MACH_TASK_BASIC_INFO_COUNT
            and type(basic.get("resident_size_max")) is int
            and basic["resident_size_max"] >= 0
        ):
            high = basic["resident_size_max"]
        return {"start": before["start"], "resident": resident, "high_water": high}

    def _task_system(self):
        if self._libsystem is False:
            return None
        if self._libsystem is not None:
            return self._libsystem
        if sys.platform != "darwin":
            self._libsystem = False
            return None
        try:
            self._libsystem = _load_darwin_task_port()
        except (AttributeError, OSError):
            self._libsystem = False
            return None
        return self._libsystem

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
            # pid, buffer, buffer size in bytes. The return is a pid count.
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


# mach_task_basic_info in xnu osfmk/mach/task_info.h. natural_t is 4 bytes,
# so 48 bytes is MACH_TASK_BASIC_INFO_COUNT 12. Flavor 20 accepts a task-name port.
_MACH_TASK_BASIC_INFO = 20
_MACH_TASK_BASIC_INFO_COUNT = 12
_MACH_TASK_BASIC_BYTES = 48
# Fixed cleanup token. The kern return stays on the task-query result.
_PORT_RELEASE_FAILED = "port_release_failed"


class _MachTaskBasicInfo(ctypes.Structure):
    _fields_ = [
        ("virtual_size", ctypes.c_uint64),
        ("resident_size", ctypes.c_uint64),
        ("resident_size_max", ctypes.c_uint64),
        ("user_seconds", ctypes.c_int32),
        ("user_microseconds", ctypes.c_int32),
        ("system_seconds", ctypes.c_int32),
        ("system_microseconds", ctypes.c_int32),
        ("policy", ctypes.c_int32),
        ("suspend_count", ctypes.c_int32),
    ]


def _load_darwin_task_port():
    """libSystem task-name queries. No task_for_pid and no VM read."""
    system = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    system.mach_task_self.argtypes = []
    system.mach_task_self.restype = ctypes.c_uint32
    system.task_name_for_pid.argtypes = [
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    system.task_name_for_pid.restype = ctypes.c_int
    system.task_info.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    system.task_info.restype = ctypes.c_int
    system.mach_port_deallocate.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    system.mach_port_deallocate.restype = ctypes.c_int
    return system


def _task_rss_result(
    *,
    accepted,
    kr,
    count,
    resident_size_max,
    released,
    port_deallocate_kern_return=None,
    port_deallocate_error=None,
):
    return {
        "accepted": accepted,
        "kr": kr,
        "count": count,
        "resident_size_max": resident_size_max,
        "released": list(released),
        "port_deallocate_kern_return": port_deallocate_kern_return,
        "port_deallocate_error": port_deallocate_error,
    }


def _darwin_task_rss(system, pid: int) -> dict:
    """One MACH_TASK_BASIC_INFO query. Each acquired name port is deallocated once.

    KERN_SUCCESS is 0. A nonzero return or a raised error is kept and is not
    listed in ``released``. The task_info reading stays as it was: a failed
    drop does not turn a valid peak into zero and does not invent one for a
    denied query.
    """
    released: list[int] = []
    if (
        system is None
        or type(pid) is not int
        or pid <= 0
        or ctypes.sizeof(_MachTaskBasicInfo) != _MACH_TASK_BASIC_BYTES
    ):
        return _task_rss_result(
            accepted=False,
            kr=None,
            count=None,
            resident_size_max=None,
            released=released,
        )
    port = ctypes.c_uint32(0)
    drop = {"kr": None, "error": None}

    def release() -> None:
        name = int(port.value)
        if name == 0:
            return
        port.value = 0
        try:
            returned = int(system.mach_port_deallocate(system.mach_task_self(), name))
        except Exception:
            drop["error"] = _PORT_RELEASE_FAILED
            return
        drop["kr"] = returned
        if returned != 0:
            drop["error"] = _PORT_RELEASE_FAILED
            return
        released.append(name)

    def pack(*, accepted, kr, count, resident_size_max):
        return _task_rss_result(
            accepted=accepted,
            kr=kr,
            count=count,
            resident_size_max=resident_size_max,
            released=released,
            port_deallocate_kern_return=drop["kr"],
            port_deallocate_error=drop["error"],
        )

    try:
        kr = int(system.task_name_for_pid(system.mach_task_self(), pid, ctypes.byref(port)))
        if kr != 0 or int(port.value) == 0:
            release()
            return pack(
                accepted=False,
                kr=kr,
                count=None,
                resident_size_max=None,
            )
        info = _MachTaskBasicInfo()
        count = ctypes.c_uint32(_MACH_TASK_BASIC_INFO_COUNT)
        kr = int(
            system.task_info(
                int(port.value),
                _MACH_TASK_BASIC_INFO,
                ctypes.byref(info),
                ctypes.byref(count),
            )
        )
        got = int(count.value)
        if kr != 0 or got != _MACH_TASK_BASIC_INFO_COUNT:
            release()
            return pack(
                accepted=False,
                kr=kr,
                count=got,
                resident_size_max=None,
            )
        peak = int(info.resident_size_max)
        release()
        return pack(
            accepted=True,
            kr=0,
            count=got,
            resident_size_max=peak,
        )
    except Exception:
        release()
        return pack(
            accepted=False,
            kr=None,
            count=None,
            resident_size_max=None,
        )


def _darwin_ppid(library, pid: int) -> int | None:
    raw = ctypes.create_string_buffer(256)
    size = library.proc_pidinfo(pid, 3, 0, raw, 256)
    if size < 20:
        return None
    values = ctypes.cast(raw, ctypes.POINTER(ctypes.c_uint32))
    if int(values[3]) != pid:
        return None
    return int(values[4])


def _darwin_children(library, pid: int) -> list[int] | None:
    """One bounded proc_listchildpids query. The return value is a pid count.

    Apple libproc divides the kernel byte count by sizeof(int) before
    returning (libproc.c). The buffer size argument stays in bytes. A null
    buffer asks for every process plus margin, not this parent's children
    (xnu proc_info.c), so this query never uses one. libproc reports both a
    failed call and a real empty list as 0; errno separates them. A full
    64-pid buffer can hide another child. An oversized, negative, or
    malformed result is not a child list. Those results stay unverified
    and are not returned as an empty list.
    """
    if library is None or type(pid) is not int or pid <= 0:
        return None
    cap_pids = 64
    cap_bytes = cap_pids * ctypes.sizeof(ctypes.c_int)
    buf = ctypes.create_string_buffer(cap_bytes)
    ctypes.set_errno(0)
    try:
        returned = library.proc_listchildpids(pid, buf, cap_bytes)
    except (AttributeError, OSError):
        return None
    errno = ctypes.get_errno()
    if type(returned) is not int or returned < 0 or returned > cap_pids or errno != 0:
        return None
    if returned == cap_pids:
        return None
    if returned == 0:
        return []
    values = ctypes.cast(buf, ctypes.POINTER(ctypes.c_int))
    pids = []
    for index in range(returned):
        child = int(values[index])
        if child <= 0:
            return None
        pids.append(child)
    return pids


def exercise_cleanup_failure() -> dict:
    """One failed terminate of an invalid handle. No process is signaled."""
    if sys.platform != "win32":
        return {"exercised": False, "reason": "windows_job_only", "retried": False}
    api = _WinApi()
    ok, failure = api.terminate_job(None)
    return {"exercised": True, "ok": ok, "failure": failure, "retried": False}
