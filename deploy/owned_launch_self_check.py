"""Bounded lifecycle check for the owned-launch accounting adapter.

Launches short-lived CPU work and a descendant, then a sleeper that must be
terminated with the owned group. This is not an application benchmark and it
does not accept the resource budget.

Run once on a hosted native target:

    python -m deploy.owned_launch_self_check
"""

from __future__ import annotations

import json
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from deploy.owned_launch_accounting import (
    _signal_cgroup,
    exercise_cleanup_failure,
    start_owned_launch,
    OwnedLaunchError,
    OwnedLaunchUnsupported,
)


_WORKER = """
import subprocess
import sys
import time

def burn():
    value = 1
    for index in range(1000000):
        value = (value * 1103515245 + 12345 + index) & 0x7FFFFFFF
    return value

def popen(argv):
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000
    return subprocess.Popen(argv, **kwargs)

mode = sys.argv[1]
if mode == "burn":
    result = burn()
    with open(sys.argv[2], "w", encoding="ascii") as handle:
        handle.write(str(result))
elif mode == "work":
    child = popen([sys.executable, __file__, "burn", sys.argv[2]])
    quick = popen([sys.executable, "-c", "raise SystemExit(0)"])
    burn()
    child.wait(timeout=20)
    quick.wait(timeout=20)
elif mode == "sleep":
    time.sleep(30)
else:
    raise SystemExit(2)
"""


def _private(path: Path) -> None:
    if sys.platform == "win32":
        return
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _assert_common(report: dict, private: str) -> None:
    encoded = json.dumps(report)
    if private in encoded:
        raise AssertionError("report contained a private path")
    if report["qualification"] != "unqualified" or report["resource_acceptance"] is not False:
        raise AssertionError("measurement was treated as acceptance")
    if report["budget"]["status"] != "UNACCEPTED" or report["budget"]["compared"] is not False:
        raise AssertionError("budget was compared or accepted")
    if report["budget"]["additional_rss_bytes_per_process"] != 8_388_608:
        raise AssertionError("rss budget changed")
    if report["budget"]["cpu_one_core_fraction"] != 0.005:
        raise AssertionError("cpu budget changed")
    if report["missing_recorded_as_zero"] is not False:
        raise AssertionError("missing data was zero")
    if report["coverage"]["sampled_pid_cpu_is_complete"] is not False:
        raise AssertionError("sampled pids were treated as complete cpu")
    if report["coverage"]["cgroup_memory_peak_is_per_process_rss"] is not False:
        raise AssertionError("cgroup memory was labeled rss")
    if report["cold_start"]["subtracted"] is not False:
        raise AssertionError("cold start was a growth delta")
    if report["idle_or_settlement_included_in_active_cpu"] is not False:
        raise AssertionError("idle was included in active cpu")
    if any(phase["name"] == "settlement" and phase["active"] for phase in report["phases"]):
        raise AssertionError("settlement was active")
    if report["cleanup"]["retried"] is not False:
        raise AssertionError("cleanup retried")
    for row in report["ledger"]:
        for key in ("peak_working_set_bytes", "first_working_set_bytes", "last_working_set_bytes"):
            if row[key] is not None and type(row[key]) is not int:
                raise AssertionError("working set was not an integer or null")
    kernel = report.get("kernel") or {}
    if kernel.get("commit_counters_are_working_set") not in (None, False):
        raise AssertionError("job commit was labeled working set")
    if kernel.get("cgroup_memory_peak_is_per_process_rss") not in (None, False):
        raise AssertionError("cgroup peak was labeled rss")
    if kernel.get("footprint_used_as_rss") not in (None, False):
        raise AssertionError("footprint was labeled rss")


def _require_owned_cleanup(report: dict) -> None:
    """The launch's own cleanup. Not the invalid-handle exercise."""
    cleanup = report.get("cleanup") if type(report) is dict else None
    if type(cleanup) is not dict or cleanup.get("ok") is not True:
        failure = None if type(cleanup) is not dict else cleanup.get("failure")
        raise AssertionError(failure or "cleanup_missing")


def lifecycle_receipt_qualifies(data: object) -> bool:
    """True only for a held run whose owned cleanup succeeded.

    An honest unsupported receipt is not qualification. The Windows
    invalid-handle exercise is not the cleanup result.
    """
    if type(data) is not dict or data.get("honest_unsupported"):
        return False
    if data.get("held") is not True or data.get("resource_acceptance") is not False:
        return False
    if data.get("cleanup_ok") is not True or data.get("cleanup_failure") is not None:
        return False
    if data.get("platform") == "darwin":
        waited = data.get("lifetime_cpu_microseconds")
        if (
            data.get("coverage_status") != "partial"
            or data.get("cpu_lifetime_complete") is not False
        ):
            return False
        if type(waited) is not int or waited <= 0:
            return False
    return True


def _assert_retained_cpu(report: dict) -> None:
    coverage = report["coverage"]
    if (
        coverage["cpu_lifetime_complete"] is not True
        or coverage["cpu_includes_exited_descendants"] is not True
    ):
        raise AssertionError("exited cpu was not retained")
    if (
        type(report["lifetime_cpu_microseconds"]) is not int
        or report["lifetime_cpu_microseconds"] < 5_000
    ):
        raise AssertionError("lifetime cpu was missing or trivial")
    if type(report["active_cpu_microseconds"]) is not int or report["active_cpu_microseconds"] <= 0:
        raise AssertionError("active cpu was missing")
    if report["active_cpu_microseconds"] > report["lifetime_cpu_microseconds"]:
        raise AssertionError("active cpu exceeded lifetime cpu")
    if report["observer_in_measured_group"] is not False:
        raise AssertionError("observer was inside the measured group")
    if report["cleanup"]["ok"] is not True:
        raise AssertionError(report["cleanup"]["failure"] or "cleanup failed")
    if not report["cold_start"]["processes"]:
        raise AssertionError("cold start absolute working set was missing")


def _work(script: Path, marker: Path) -> dict:
    argv = [sys.executable, str(script), "work", str(marker)]
    with start_owned_launch(argv, bound_seconds=20, sample_seconds=0.05) as launch:
        launch.mark_phase("canonical-work", canonical_operations_completed=0, active=True)
        if not launch.wait_root(15):
            raise AssertionError("owned work did not exit")
        if not marker.is_file():
            raise AssertionError("descendant did not run")
        launch.mark_phase("settlement", canonical_operations_completed=1, active=False)
        report = launch.finish(canonical_operations_completed=1)
    _assert_common(report, str(marker))
    return report


def _terminate(script: Path, marker: Path) -> dict:
    argv = [sys.executable, str(script), "sleep"]
    with start_owned_launch(argv, bound_seconds=10, sample_seconds=0.05) as launch:
        launch.mark_phase("canonical-work", canonical_operations_completed=0, active=True)
        report = launch.finish(canonical_operations_completed=0)
    _assert_common(report, str(marker))
    if (
        report["cleanup"]["ok"] is not True
        or report["cleanup"]["terminated_owned_group"] is not True
    ):
        raise AssertionError(report["cleanup"]["failure"] or "owned group was not terminated")
    if report["cleanup"]["retried"] is not False:
        raise AssertionError("termination retried")
    return report


def run_self_check() -> dict:
    """Return a JSON-ready result. Raise AssertionError when an invariant fails."""
    cleanup = exercise_cleanup_failure()
    signaled, signal_failure = _signal_cgroup(None)
    if signaled or signal_failure != "cgroup_missing":
        raise AssertionError("empty cleanup signaled a process")
    if sys.platform == "win32" and (
        cleanup["ok"] is not False or not cleanup["failure"] or cleanup["retried"]
    ):
        raise AssertionError("cleanup failure was not recorded")
    root = Path(tempfile.mkdtemp(prefix="owned-launch-"))
    script = root / "worker.py"
    marker = root / "descendant"
    try:
        script.write_text(_WORKER, encoding="ascii")
        _private(script)
        try:
            work = _work(script, marker)
        except OwnedLaunchUnsupported as error:
            if sys.platform == "win32":
                raise AssertionError(error.code) from None
            return {
                "self_check": "owned_launch_lifecycle",
                "held": True,
                "honest_unsupported": error.code,
                "platform": sys.platform,
                "machine": platform.machine(),
                "resource_acceptance": False,
                "invalid_handle_exercise": _invalid_handle_exercise(cleanup),
            }
        if sys.platform == "darwin":
            coverage = work["coverage"]
            if coverage["status"] != "partial" or coverage["cpu_lifetime_complete"] is not False:
                raise AssertionError("darwin was reported as complete lifetime accounting")
            if coverage["cpu_includes_exited_descendants"] is not False:
                raise AssertionError("darwin descendant cpu was reported complete")
            waited = (work.get("kernel") or {}).get("wait4_direct_child_cpu_microseconds")
            if type(waited) is not int or waited <= 0:
                raise AssertionError("darwin wait4 resource result was missing")
            if work["lifetime_cpu_microseconds"] != waited:
                raise AssertionError("darwin lifetime cpu did not use the waited resource result")
            _require_owned_cleanup(work)
        else:
            _assert_retained_cpu(work)
            if sys.platform == "win32":
                kernel = work["kernel"]
                if kernel["active_processes"] != 0 or kernel["total_processes"] < 3:
                    raise AssertionError("windows job did not retain the exited tree")
                if kernel["processes_no_longer_active"] < 3:
                    raise AssertionError("exited processes were dropped from the job")
                if work["identities_missing"] is None:
                    raise AssertionError("windows identity gap was hidden")
        stopped = _terminate(script, marker)
        if sys.platform == "win32" and stopped["kernel"]["active_processes"] != 0:
            raise AssertionError("terminated job still had active processes")
        _require_owned_cleanup(work)
        _require_owned_cleanup(stopped)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return {
        "self_check": "owned_launch_lifecycle",
        "held": True,
        "platform": sys.platform,
        "machine": platform.machine(),
        "resource_acceptance": False,
        "cpu_lifetime_complete": work["coverage"]["cpu_lifetime_complete"],
        "coverage_status": work["coverage"]["status"],
        "lifetime_cpu_microseconds": work["lifetime_cpu_microseconds"],
        "active_cpu_microseconds": work["active_cpu_microseconds"],
        "active_wall_microseconds": work["active_wall_microseconds"],
        "identities_missing": work["identities_missing"],
        "ledger_count": len(work["ledger"]),
        "total_processes": None
        if not work.get("kernel")
        else work["kernel"].get("total_processes"),
        "active_processes_after_exit": None
        if not work.get("kernel")
        else work["kernel"].get("active_processes"),
        "cleanup_ok": True,
        "cleanup_failure": None,
        "termination_exercised": stopped["cleanup"]["terminated_owned_group"],
        "invalid_handle_exercise": _invalid_handle_exercise(cleanup),
        "unavailable_counters": work["unavailable_counters"],
    }


def _invalid_handle_exercise(cleanup: dict) -> dict:
    exercised = cleanup.get("exercised") is True
    return {
        "exercised": exercised,
        "failure": cleanup.get("failure") if exercised else None,
        "retried": False,
    }


def main() -> None:
    try:
        result = run_self_check()
    except (AssertionError, OSError, subprocess.SubprocessError, OwnedLaunchError) as error:
        detail = getattr(error, "code", None) or str(error)
        print(
            json.dumps(
                {
                    "self_check": "owned_launch_lifecycle",
                    "held": False,
                    "failure": str(detail)[:120],
                }
            )
        )
        raise SystemExit(1) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
