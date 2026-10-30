"""Own one installed executable for the existing resource workload.

The bridge stays outside the measured child. It does not launch an
unmeasured app when the platform cannot account for the child. A Windows
exit code is read with GetExitCodeProcess. STILL_ACTIVE (259) and a missing
code are not success.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import platform
import re
import sys
import time

from deploy.owned_launch_accounting import (
    OwnedLaunchError,
    OwnedLaunchUnsupported,
    start_owned_launch,
)
from deploy.report_telemetry_renderer import (
    OwnedPhaseCursor,
    apply_owned_marker,
    close_owned_progress,
    observation_failure_code,
    owned_unsupported_report,
    read_owned_marker,
)

# Microsoft documents this as STILL_ACTIVE, the macro for STATUS_PENDING.
_STILL_ACTIVE = 259
_APP_WAIT_SECONDS = 12 * 60
_SHUTDOWN_SECONDS = 120
_POLL_SECONDS = 0.05
_STAGE = re.compile(r"[a-z-]{1,64}\Z")
_FAILURE_STAGES = {
    "startup-error",
    "uncaught-exception",
    "unhandled-rejection",
    "backend-exit",
    "backend-timeout",
}
_DENIED_ENV = {"GH_TOKEN", "GITHUB_TOKEN", "NODE_AUTH_TOKEN"}
# The separate delivery diagnostic is activated by this flag together with the
# hosting probe. Invented counter names are not a detector.
_DELIVERY_DIAGNOSTIC = "MNEMION_TELEMETRY_INSTALLED_DELIVERY"


def delivery_diagnostics_enabled(environ: object) -> bool:
    """True when the child inherited the installed delivery diagnostic."""
    if type(environ) is not dict:
        return False
    return environ.get(_DELIVERY_DIAGNOSTIC) == "1"


def _root_exit_code(launch) -> int | None:
    """The direct child exit code. Missing and still-active are not zero."""
    process = getattr(launch.backend, "process", None)
    if not process:
        return None
    if sys.platform == "win32":
        code = wintypes.DWORD()
        kernel = launch.backend._api.kernel
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        # The creator handle remains open until finish closes it.
        ok = kernel.GetExitCodeProcess(process, ctypes.byref(code))
        if not ok:
            return None
        value = int(code.value)
        if value == _STILL_ACTIVE:
            return None
        return value
    code = getattr(process, "returncode", None)
    if type(code) is not int:
        return None
    return code


def _smoke_stage(path: Path) -> str | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if type(value) is not dict:
        return None
    stage = value.get("stage")
    if type(stage) is not str or not _STAGE.fullmatch(stage):
        return None
    return stage


def _write_quit(path: Path) -> None:
    path.write_text("quit\n", encoding="utf-8")


def _emit(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def _progress_fields(report: dict, cursor) -> None:
    report["canonical_operations_completed"] = cursor.completed
    known = getattr(cursor, "completed_known", None)
    report["canonical_operations_known"] = known if type(known) is bool else None
    failure = getattr(cursor, "observation_failure", None)
    if type(failure) is str and not report.get("observation_error"):
        report["observation_error"] = failure
    if getattr(cursor, "marker_failed", False):
        report["marker_applied"] = False


def _remember_marker_failure(cursor, error: BaseException) -> None:
    cursor.marker_failed = True
    cursor.completed_known = False
    if getattr(cursor, "observation_failure", None) is None:
        cursor.observation_failure = observation_failure_code(error)


def _annotate(report: dict, *, cursor, exit_code, hosting_ready, failure_stage, environ) -> dict:
    _progress_fields(report, cursor)
    report["resource_acceptance"] = False
    report["root_exit_code"] = exit_code
    report["hosting_ready"] = hosting_ready
    report["failure_stage"] = failure_stage
    report["delivery_diagnostics_enabled"] = delivery_diagnostics_enabled(environ)
    report["phase_cpu"] = "sampled_descriptive"
    report["lifetime_cpu_is_separate"] = True
    report["observer"] = {
        "platform": sys.platform,
        "machine": platform.machine(),
        "pointer_bits": ctypes.sizeof(ctypes.c_void_p) * 8,
        "implementation": platform.python_implementation(),
        "executable": Path(sys.executable).name,
    }
    return report


def _fallback(code: str, *, launched: bool, completed: int, environ: dict) -> dict:
    return _annotate(
        {
            "qualification": "unqualified",
            "resource_acceptance": False,
            "launched": launched,
            "lifetime_cpu_microseconds": None,
            "active_cpu_microseconds": None,
            "active_wall_microseconds": None,
            "identities_missing": None,
            "missing_recorded_as_zero": False,
            "canonical_operations_completed": completed,
            "cleanup": {"ok": False, "failure": code, "retried": False},
            "phases": [],
        },
        cursor=type("Cursor", (), {"completed": completed})(),
        exit_code=None,
        hosting_ready=False,
        failure_stage=None,
        environ=environ,
    )


def _check_spec(spec: object) -> dict:
    if type(spec) is not dict:
        raise OwnedLaunchError("invalid_spec")
    argv = spec.get("argv")
    env = spec.get("env")
    if (
        type(argv) is not list
        or not argv
        or any(type(arg) is not str or "\x00" in arg for arg in argv)
        or type(spec.get("cwd")) is not str
        or "\x00" in spec["cwd"]
        or type(env) is not dict
        or any(
            type(key) is not str or type(value) is not str or "\x00" in key or "\x00" in value
            for key, value in env.items()
        )
        or any(key in _DENIED_ENV for key in env)
        or any(
            type(spec.get(name)) is not str or not spec[name]
            for name in ("profile", "quit_file", "smoke_file", "report")
        )
    ):
        raise OwnedLaunchError("invalid_spec")
    return spec


def owned_launch_succeeded(hosting_ready, exit_code, cleanup_ok, failure_stage) -> bool:
    """Missing and still-active exit codes are not a clean owned launch."""
    return hosting_ready is True and exit_code == 0 and cleanup_ok is True and failure_stage is None


def _unfinished_report(code: str) -> dict:
    """Finish did not return a report. Counters stay null rather than zero."""
    return {
        "qualification": "unqualified",
        "resource_acceptance": False,
        "launched": True,
        "lifetime_cpu_microseconds": None,
        "active_cpu_microseconds": None,
        "active_wall_microseconds": None,
        "missing_recorded_as_zero": False,
        "cleanup": {"ok": False, "failure": str(code), "retried": False},
    }


def finalize_owned_launch(launch, cursor, observe) -> dict:
    """Read markers best-effort, then finish the owned group exactly once."""
    observation_error = None
    exit_code = None
    hosting_ready = False
    failure_stage = None
    try:
        observed = observe()
        if type(observed) is not tuple or len(observed) != 3:
            raise OwnedLaunchError("observation_failed")
        hosting_ready, failure_stage, exit_code = observed
    except Exception as error:
        observation_error = error
        try:
            exit_code = _root_exit_code(launch)
        except Exception:
            exit_code = None
    try:
        report = launch.finish(canonical_operations_completed=cursor.completed)
    except Exception as error:
        code = getattr(error, "code", None)
        report = _unfinished_report(code if type(code) is str else "finish_failed")
    if type(report) is not dict:
        report = _unfinished_report("finish_failed")
    if type(exit_code) is not int or exit_code == _STILL_ACTIVE:
        exit_code = None
    close_owned_progress(cursor)
    if isinstance(observation_error, BaseException):
        report["observation_error"] = observation_failure_code(observation_error)
    report["root_exit_code"] = exit_code
    report["hosting_ready"] = hosting_ready is True
    report["failure_stage"] = failure_stage if type(failure_stage) is str else None
    _progress_fields(report, cursor)
    report["resource_acceptance"] = False
    return report


def run_spec(spec_path: Path) -> int:
    """Start the owned child, consume the terminal count, then finish once."""
    try:
        spec = _check_spec(json.loads(spec_path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError, OwnedLaunchError):
        return 1
    report_path = Path(spec["report"])
    profile = Path(spec["profile"])
    quit_file = Path(spec["quit_file"])
    smoke_file = Path(spec["smoke_file"])
    env = spec["env"]
    if delivery_diagnostics_enabled(env):
        _emit(
            report_path,
            _fallback("delivery_diagnostics_enabled", launched=False, completed=0, environ=env),
        )
        return 1
    try:
        launch = start_owned_launch(
            spec["argv"],
            cwd=spec["cwd"],
            env=env,
            bound_seconds=120,
            sample_seconds=_POLL_SECONDS,
        )
    except OwnedLaunchUnsupported as error:
        _emit(report_path, owned_unsupported_report(error.code))
        return 2
    except OwnedLaunchError as error:
        _emit(report_path, _fallback(error.code, launched=False, completed=0, environ=env))
        return 1
    cursor = OwnedPhaseCursor()

    def observe():
        hosting_ready = False
        failure_stage = None
        root_done = False
        exit_code = None
        deadline = time.monotonic() + _APP_WAIT_SECONDS
        while time.monotonic() < deadline:
            try:
                apply_owned_marker(launch, read_owned_marker(profile), cursor)
            except Exception as error:
                _remember_marker_failure(cursor, error)
            stage = _smoke_stage(smoke_file)
            if stage == "hosting-ready":
                hosting_ready = True
                break
            if stage in _FAILURE_STAGES:
                failure_stage = stage
                break
            if launch.wait_root(_POLL_SECONDS):
                root_done = True
                break
        if not root_done:
            try:
                _write_quit(quit_file)
            except OSError:
                failure_stage = failure_stage or "quit-unwritable"
            shutdown = time.monotonic() + _SHUTDOWN_SECONDS
            while time.monotonic() < shutdown:
                try:
                    apply_owned_marker(launch, read_owned_marker(profile), cursor)
                except Exception as error:
                    _remember_marker_failure(cursor, error)
                if launch.wait_root(_POLL_SECONDS):
                    root_done = True
                    break
        try:
            apply_owned_marker(launch, read_owned_marker(profile), cursor)
        except Exception as error:
            _remember_marker_failure(cursor, error)
        try:
            exit_code = _root_exit_code(launch)
        except Exception:
            exit_code = None
        return hosting_ready, failure_stage, exit_code

    report = finalize_owned_launch(launch, cursor, observe)
    report = _annotate(
        report,
        cursor=cursor,
        exit_code=report.get("root_exit_code"),
        hosting_ready=report.get("hosting_ready") is True,
        failure_stage=report.get("failure_stage"),
        environ=env,
    )
    try:
        _emit(report_path, report)
    except OSError:
        return 1
    cleanup = report.get("cleanup") if type(report.get("cleanup")) is dict else {}
    if report.get("observation_error") or report.get("marker_applied") is False:
        return 1
    if owned_launch_succeeded(
        report.get("hosting_ready") is True,
        report.get("root_exit_code"),
        cleanup.get("ok") is True,
        report.get("failure_stage"),
    ):
        return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args(argv)
    return run_spec(args.spec)


if __name__ == "__main__":
    raise SystemExit(main())
