"""Receipt gate for the Darwin resident-memory counter probe.

This module does not call Mach. It checks a scalar observation and, on Darwin,
runs the standalone probe once under a bounded timeout. A name-port rejection
stays a rejection even when a size field is zero. A zero peak and a child or
cleanup failure stay separate results. Nothing here is telemetry acceptance.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

PROBE_NAME = "darwin_residency_counters"
ALLOCATION_BYTES = 8 * 1024 * 1024
PROBE_TIMEOUT_S = 12
SIGKILL = getattr(signal, "SIGKILL", 9)
SIGTERM = getattr(signal, "SIGTERM", 15)
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
WORKFLOW_MACHINE = {"arm64": "arm64", "x64": "x86_64"}
OUTCOMES = {
    "live_counter_ok",
    "name_port_denied",
    "zero_peak_rss",
    "counter_missing",
    "child_or_cleanup_failure",
    "peak_or_allocation_check_failed",
}
ACCEPTANCE = (
    "telemetry_acceptance",
    "workload_acceptance",
    "resource_budget_acceptance",
)
UNITS = ("resident_size_unit", "resident_size_max_unit", "child_ru_maxrss_unit")
SIZE_FIELDS = (
    "baseline_resident_size",
    "baseline_resident_size_max",
    "live_resident_size",
    "live_resident_size_max",
    "child_ru_maxrss",
    "post_exit_resident_size",
    "post_exit_resident_size_max",
)
KERN_FIELDS = (
    "name_port_kern_return",
    "baseline_task_info_kern_return",
    "live_task_info_kern_return",
    "post_exit_task_info_kern_return",
    "port_deallocate_kern_return",
)
COUNT_FIELDS = (
    "baseline_task_info_count",
    "live_task_info_count",
    "post_exit_task_info_count",
)


def _int(value, *, minimum=None):
    if type(value) is not int:
        return False
    if minimum is not None and value < minimum:
        return False
    return True


def _optional_int(value, *, minimum=None):
    return value is None or _int(value, minimum=minimum)


def _text(value, limit):
    return (
        isinstance(value, str) and len(value) <= limit and all(32 <= ord(ch) < 127 for ch in value)
    )


def well_formed(obs):
    if not isinstance(obs, dict):
        return False
    if obs.get("probe") != PROBE_NAME or obs.get("allocation_bytes") != ALLOCATION_BYTES:
        return False
    if any(type(obs.get(name)) is not bool for name in ACCEPTANCE):
        return False
    if any(obs.get(name) is not False for name in ACCEPTANCE):
        return False
    source = obs.get("source")
    if source is not None and (not isinstance(source, str) or SHA_RE.fullmatch(source) is None):
        return False
    if type(obs.get("source_rejected")) is not bool:
        return False
    if not all(_text(obs.get(name), 64) for name in ("os", "os_release", "arch", "detail")):
        return False
    if obs.get("outcome") not in OUTCOMES:
        return False
    if any(obs.get(name) != "bytes" for name in UNITS):
        return False
    if not _optional_int(obs.get("child_pid"), minimum=2):
        return False
    if any(not _optional_int(obs.get(name)) for name in KERN_FIELDS):
        return False
    if any(not _optional_int(obs.get(name), minimum=0) for name in COUNT_FIELDS):
        return False
    if any(not _optional_int(obs.get(name), minimum=0) for name in SIZE_FIELDS):
        return False
    if not _optional_int(obs.get("child_exit_status"), minimum=0):
        return False
    if not _optional_int(obs.get("child_term_signal"), minimum=1):
        return False
    if obs.get("child_exit_kind") not in {"exited", "signaled", "unexited"}:
        return False
    for name in (
        "name_port_is_null",
        "child_reaped",
        "timed_out",
        "cleanup_ok",
        "post_exit_queried",
    ):
        if type(obs.get(name)) is not bool:
            return False
    for name in ("peaks_nondecreasing", "allocation_observed", "post_exit_supported"):
        if obs.get(name) is not None and type(obs.get(name)) is not bool:
            return False
    return True


def _post_exit_shape_ok(obs):
    sizes = (obs.get("post_exit_resident_size"), obs.get("post_exit_resident_size_max"))
    if obs.get("post_exit_queried") is False:
        return (
            obs.get("post_exit_supported") is None
            and obs.get("post_exit_task_info_kern_return") is None
            and obs.get("post_exit_task_info_count") is None
            and sizes == (None, None)
        )
    supported = obs.get("post_exit_supported")
    kern = obs.get("post_exit_task_info_kern_return")
    if supported is True:
        return _int(kern) and kern == 0 and all(_int(item, minimum=0) for item in sizes)
    if supported is False:
        return _int(kern) and sizes == (None, None)
    return False


def _clean_lifecycle(obs):
    return (
        obs.get("child_reaped") is True
        and obs.get("cleanup_ok") is True
        and obs.get("timed_out") is False
        and obs.get("child_exit_kind") == "exited"
        and obs.get("child_exit_status") == 0
    )


def _sample_complete(obs, prefix):
    return (
        obs.get(prefix + "_task_info_kern_return") == 0
        and _int(obs.get(prefix + "_task_info_count"), minimum=1)
        and _int(obs.get(prefix + "_resident_size"), minimum=0)
        and _int(obs.get(prefix + "_resident_size_max"), minimum=0)
    )


def recompute(obs):
    if not _clean_lifecycle(obs):
        return "child_or_cleanup_failure"
    kern = obs.get("name_port_kern_return")
    if kern is None:
        return "child_or_cleanup_failure"
    if kern != 0:
        return "name_port_denied"
    if obs.get("name_port_is_null") is True or not _sample_complete(obs, "baseline"):
        return "counter_missing"
    if not _sample_complete(obs, "live") or obs.get("child_ru_maxrss") is None:
        return "counter_missing"
    if obs.get("live_resident_size_max") == 0:
        return "zero_peak_rss"
    peaks_ok = obs["live_resident_size_max"] >= obs["baseline_resident_size_max"]
    alloc_ok = obs["live_resident_size"] > obs["baseline_resident_size"]
    if not peaks_ok or not alloc_ok:
        return "peak_or_allocation_check_failed"
    if obs.get("peaks_nondecreasing") is not True or obs.get("allocation_observed") is not True:
        return "peak_or_allocation_check_failed"
    return "live_counter_ok"


def classify(obs):
    if not well_formed(obs) or not _post_exit_shape_ok(obs):
        return "malformed_observation"
    result = recompute(obs)
    if obs.get("outcome") != result:
        return "malformed_observation"
    return result


def extract_observation(stdout):
    if stdout is None or stdout.strip() == "":
        return None, "missing"
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None, "missing"
    candidate = lines[-1]
    if not candidate.startswith("{") or not candidate.endswith("}"):
        return None, "truncated_or_invalid"
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None, "truncated_or_invalid"
    if not isinstance(data, dict):
        return None, "invalid"
    return data, None


def demonstrated(obs, *, source, workflow_arch, probe_returncode, outer_timeout):
    if outer_timeout or classify(obs) != "live_counter_ok" or probe_returncode != 0:
        return False
    if obs.get("source") != source or obs.get("os") != "Darwin":
        return False
    expected = WORKFLOW_MACHINE.get(workflow_arch)
    if expected is None or obs.get("arch") != expected:
        return False
    return all(obs.get(name) is False for name in ACCEPTANCE)


def stop_owned_probe(proc, *, getpgid, killpg, kill):
    """Stop only this probe. Kill its process group only when it is the leader."""
    if proc.poll() is not None:
        return "already_exited"
    pid = proc.pid
    if type(pid) is not int or pid <= 1:
        return "refused"
    try:
        pgid = getpgid(pid)
    except ProcessLookupError:
        return "already_exited"
    except OSError:
        return "refused"
    try:
        if type(pgid) is not int or pgid != pid:
            kill(pid, SIGTERM)
            return "signaled_pid_only"
        killpg(pid, SIGKILL)
        return "killed_group"
    except ProcessLookupError:
        return "already_exited"
    except OSError:
        return "kill_failed"


def _write(path: Path, payload):
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _stub(source, head, workflow_arch, classification, **extra):
    payload = {
        "arch": None,
        "classification": classification,
        "compiler_returncode": None,
        "head": head,
        "os": None,
        "outer_timeout": False,
        "probe": PROBE_NAME,
        "probe_returncode": None,
        "resource_budget_acceptance": False,
        "source": source,
        "telemetry_acceptance": False,
        "workflow_arch": workflow_arch,
        "workload_acceptance": False,
    }
    payload.update(extra)
    return payload


def _decode(data: bytes):
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def run_probe(binary: Path, source: str):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "MNEMION_PROBE_SOURCE": source}
    proc = subprocess.Popen(
        [str(binary)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=PROBE_TIMEOUT_S)
        return proc.returncode, stdout, stderr, False
    except subprocess.TimeoutExpired:
        stop_owned_probe(proc, getpgid=os.getpgid, killpg=os.killpg, kill=os.kill)
        try:
            stdout, stderr = proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            if proc.poll() is None and type(proc.pid) is int and proc.pid > 1:
                os.kill(proc.pid, SIGKILL)
            stdout, stderr = proc.communicate(timeout=2)
        return proc.returncode, stdout, stderr, True


def main(argv=None):
    del argv
    source = os.environ.get("REVIEWED_SOURCE", "")
    workflow_arch = os.environ.get("MNEMION_RESIDENCY_ARCH", "")
    head = None
    receipt_path = Path("output") / "darwin-residency" / "receipt.json"
    try:
        out = receipt_path.parent
        out.mkdir(parents=True, exist_ok=True)
        if SHA_RE.fullmatch(source) is None or workflow_arch not in WORKFLOW_MACHINE:
            _write(
                receipt_path,
                _stub(None, None, workflow_arch or None, "source_not_exact"),
            )
            return 1
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        if head != source:
            _write(receipt_path, _stub(source, head, workflow_arch, "head_mismatch"))
            return 1
        if sys.platform != "darwin":
            _write(receipt_path, _stub(source, head, workflow_arch, "not_darwin"))
            return 1
        binary = out / "probe_darwin_residency"
        compile_argv = [
            "xcrun",
            "--sdk",
            "macosx",
            "clang",
            "-Wall",
            "-Wextra",
            "-o",
            str(binary),
            "deploy/probe_darwin_residency.c",
        ]
        compiled = subprocess.run(compile_argv, capture_output=True, text=True)
        (out / "compiler.txt").write_text(
            "returncode: "
            + str(compiled.returncode)
            + "\nargv: "
            + json.dumps(compile_argv)
            + "\n"
            + compiled.stdout
            + compiled.stderr,
            encoding="utf-8",
        )
        if compiled.returncode != 0:
            _write(
                receipt_path,
                _stub(
                    source,
                    head,
                    workflow_arch,
                    "compile_failed",
                    compiler_returncode=compiled.returncode,
                ),
            )
            return 1
        returncode, stdout, stderr, outer_timeout = run_probe(binary, source)
        stdout_text = _decode(stdout)
        (out / "probe-stdout.txt").write_bytes(stdout or b"")
        (out / "probe-stderr.txt").write_bytes(stderr or b"")
        obs, error = extract_observation(stdout_text)
        if obs is None:
            _write(
                receipt_path,
                _stub(
                    source,
                    head,
                    workflow_arch,
                    error or "invalid",
                    compiler_returncode=0,
                    outer_timeout=outer_timeout,
                    probe_returncode=returncode,
                ),
            )
            return 1
        kind = classify(obs)
        payload = dict(obs)
        payload.update(
            {
                "classification": kind,
                "compiler_returncode": 0,
                "head": head,
                "outer_timeout": outer_timeout,
                "probe_returncode": returncode,
                "workflow_arch": workflow_arch,
            }
        )
        _write(receipt_path, payload)
        if not demonstrated(
            obs,
            source=source,
            workflow_arch=workflow_arch,
            probe_returncode=returncode,
            outer_timeout=outer_timeout,
        ):
            return returncode or 1
        return 0
    except Exception as exc:
        kept_source = source if SHA_RE.fullmatch(source or "") else None
        _write(
            receipt_path,
            _stub(
                kept_source,
                head,
                workflow_arch or None,
                "runner_error",
                detail=type(exc).__name__,
            ),
        )
        return 1
    finally:
        if not receipt_path.exists():
            _write(receipt_path, _stub(None, head, workflow_arch or None, "missing_receipt"))


if __name__ == "__main__":
    raise SystemExit(main())
