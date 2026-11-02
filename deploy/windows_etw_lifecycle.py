"""One disposable ETW lifecycle observation around one job-owned Python root.

This module does not change the production launch entry, installed-workload routing,
or the ETW provider. It does not start a trace on import. WinEtwApi and
WindowsJobBackend run only from the manual workflow entry, after the source,
architecture, and interpreter gates.

The worker follows observe_owned_launch: start the observer, then spawn.
The measured job is created before the fixture runs. A nested-job denial is
unsupported. There is no launch-then-assign fallback.

Envelope: 2s observer readiness, 5s observer drain, 30s for the whole worker,
then one 5s drain of the supervisor job after termination. The worker budget
is sampled before spawn and still applies when that spawn returns. Passing
the remaining time to a wait does not make a kernel call that has not
returned come back, and it does not prove the session or the job was
released. The observer may join its consumer twice. Those joins do not
bound a stuck stop or close. A supervisor timeout ends only the owned
worker job. It does not prove the worker released the session, and it does
not start another trace. Stopping the disposable runner is not a provider
or job cleanup receipt.

Start, End, and PerfCtr versions are checked separately. Opcode 33 rundown
is not part of that check. A missing or parser-rejected version does not
qualify. Root binding stays exact creation equality. A signed start-minus-
creation delta is published only inside a fixed 100ns bound and is not an
admission window. Candidate relations stay unproven until that equality
holds. Census samples around the existing job calls do not name an extra
process and do not change the expected total.

The receipt is not public-safe. lifecycle_receipt_qualifies is not this gate.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

import deploy.owned_launch_windows_etw as etw
from deploy.owned_launch_accounting import (
    OwnedLaunchError,
    OwnedLaunchUnsupported,
    WindowsJobBackend,
)
from deploy.owned_launch_windows_etw import (
    EtwLifetimeObserver,
    WinEtwApi,
    _GAP_REASONS,
    session_request,
)


CHECK = "windows_etw_lifecycle"
SCHEMA = 1
PROVIDER_SHA256 = "7bf10ca9ec44b3f121e5dbc7fc9e403f240dbb010a166004fdbeb9b5fe2c6b32"
ANCHOR_SOURCE = "30782814a92356991102316b8d64932850a0e938"
DECLARATION_RUN = 41248868407
DECLARATION_SOURCE = "7a7ee629e9be09f91aad79b311c885372a6993fb"
ORACLE_RUN = 41244785682
ORACLE_SOURCE = "f49ab34923d018efb3d2d30beb3a954aa6b73a48"
SDK_VERSION = "10.0.26100.0"
READY_SECONDS = 2
OBSERVER_DRAIN_SECONDS = 5
OBSERVER_DRAIN_JOINS = 2
WORKER_SECONDS = 30
SUPERVISOR_DRAIN_SECONDS = 5
BASELINE_PYTHON = "3.13.17"
PE_AMD64 = 34404
EXPECTED_TOTAL = 1
EXPECTED_ACTIVE = 0
# Publication ceiling in 100ns units. A FILETIME-scale difference is withheld.
# Root binding does not read this value.
CLOCK_DELTA_PUBLICATION_BOUND = 2**32
_CLOCK_REQUEST = session_request()
CLOCK_CLIENT_CONTEXT = _CLOCK_REQUEST["client_context"]
CLOCK_RAW_TIMESTAMP = _CLOCK_REQUEST["raw_timestamp"]
_CANDIDATE_RELATIONS = frozenset({"unproven", "exact_creation"})
_ROOT = Path(__file__).resolve().parents[1]
_PROVIDER_PATH = _ROOT / "deploy" / "owned_launch_windows_etw.py"
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_ATTEMPT = re.compile(r"[A-Za-z0-9._-]{1,32}\Z")
_RUN = re.compile(r"[0-9]{1,20}\Z")
_PY = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
_TOKEN = re.compile(r"[A-Za-z0-9._-]{1,32}\Z")
_PRESERVED = re.compile(r"[a-z0-9_]{1,40}\Z")
_API_HEX = re.compile(r"(start|stop|process)_[0-9a-f]{1,8}\Z")
_SPAWN_PREFIXES = ("create_job_", "create_process_", "job_attribute_", "job_limit_")
_NESTED_SUFFIXES = frozenset({"5", "32"})
_BLOCKING_GAPS = frozenset(
    {
        "root_binding_unproven",
        "root_unobserved",
        "root_ambiguous",
        "launch_identity_missing",
        "equal_time",
        "exit_key_mismatch",
        "exit_missing",
        "reused_pid",
        "terminal_counter_missing",
        "terminal_counter_unqualified",
        "terminal_counter_unproven",
        "census_births",
        "census_exits",
        "census_terminal_counters",
        "job_active_processes",
        "job_census_unavailable",
        "events_lost",
        "log_buffers_lost",
        "real_time_buffers_lost",
        "stop_or_drain_failed",
    }
)
PHASES = frozenset(
    {
        "unknown",
        "supervisor_checked",
        "before_worker_spawn",
        "supervisor_deadline",
        "before_supervisor_terminate",
        "before_supervisor_drain",
        "before_supervisor_close",
        "supervisor_finished",
        "worker_entered",
        "before_etw_construct",
        "before_session_start",
        "session_refused",
        "before_fixture_spawn",
        "fixture_spawn_failed",
        "before_job_drain",
        "before_snapshot",
        "before_observer_finish",
        "before_measured_job_close",
        "worker_finished",
    }
)
_API_CODES = frozenset(
    {
        "ok",
        "already_exists",
        "access_denied",
        "session_already_attempted",
        "invalid_session",
        "open_trace_failed",
        "open_already_attempted",
        "process_trace_failed",
        "unknown_handle",
        "stop_failed",
        "close_pending",
        "close_failed",
        "no_trace",
        "already_stopped",
        "already_closed",
        "not_attempted",
        "unknown",
        "not_ready",
        "consumer_still_live",
    }
)
_UNSUPPORTED = frozenset(
    {
        "dispatch_not_authorized",
        "wrong_source",
        "wrong_architecture",
        "interpreter_not_baseline",
        "worker_not_owned",
        "access_denied",
        "session_collision",
        "nested_job_denied",
        "open_trace_failed",
        "session_not_started",
        "fixture_spawn_failed",
        "worker_exception",
        "worker_receipt_invalid",
        "worker_deadline",
        "invalid_arguments",
        "privacy_rejected",
    }
)
_CLEANUP_FAILURES = frozenset(
    {"close_failed", "drain_timeout", "terminate_failed", "job_missing", "finish_failed"}
)
_ETW_REASONS = frozenset(
    {
        "worker_deadline",
        "close_pending",
        "close_failed",
        "stop_failed",
        "not_started",
        "unverified",
    }
)
_BINDINGS = frozenset({"exact_creation", "unbound", "unknown"})
_GATES = frozenset({"passed", "unpassed", "unknown"})
_FORBIDDEN_KEYS = frozenset(
    {
        "unique_process_key",
        "private_owner",
        "payload",
        "command_line",
        "environment",
        "control_handle",
        "trace_handle",
        "handle",
    }
)
_FIXTURE = "import pathlib,sys\npathlib.Path(sys.argv[1]).write_bytes(b'1')\n"
_TOP_KEYS = frozenset(
    {
        "api",
        "architecture_supported",
        "attempt",
        "baseline",
        "bounds",
        "callback_evidence",
        "callbacks",
        "check",
        "counter_reconciliation",
        "diagnostics",
        "dispatch_authorized",
        "etw_cleanup",
        "fixture_completion_marker",
        "fixture_launched",
        "head",
        "identity",
        "last_phase",
        "loss",
        "measured_job",
        "native_session_starts",
        "owned_event_qualified",
        "phases",
        "privacy",
        "preserved",
        "provider_sha256",
        "provider_sha256_matches",
        "readiness_before_process_trace",
        "requested_source",
        "retained_records",
        "run_id",
        "schema",
        "sequence",
        "session_start_calls",
        "source_matches",
        "supervisor_job",
        "unsupported",
        "worker",
    }
)


def provider_sha256(path: Path | None = None) -> str | None:
    target = _PROVIDER_PATH if path is None else path
    digest = hashlib.sha256()
    try:
        with target.open("rb") as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def git_head(root: Path | None = None) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_ROOT if root is None else root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return _sha40(completed.stdout.strip())


def pe_machine(path: Path) -> int | None:
    """Read the PE machine field. This does not load the image."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 64 or data[:2] != b"MZ":
        return None
    offset = int.from_bytes(data[0x3C:0x40], "little")
    if offset < 0 or offset + 6 > len(data) or data[offset : offset + 4] != b"PE\0\0":
        return None
    machine = int.from_bytes(data[offset + 4 : offset + 6], "little")
    if not 0 < machine < 65536:
        return None
    return machine


def host_identity(executable: Path | None = None, environ: dict | None = None) -> dict:
    env = os.environ if environ is None else environ
    target = Path(sys.executable) if executable is None else executable
    version = platform.python_version()
    implementation = platform.python_implementation()
    machine = platform.machine()
    system = sys.platform
    runner = env.get("RUNNER_OS", "")
    return {
        "pe_machine": pe_machine(target),
        "platform_machine": machine if _TOKEN.fullmatch(machine or "") else "unknown",
        "platform": system if _TOKEN.fullmatch(system or "") else "unknown",
        "python_version": version if _PY.fullmatch(version or "") else "unknown",
        "python_implementation": implementation
        if _TOKEN.fullmatch(implementation or "")
        else "unknown",
        "pointer_width": 8 if sys.maxsize > 2**32 else 4,
        "runner_os": runner if _TOKEN.fullmatch(runner or "") else "unknown",
    }


def architecture_supported(identity: dict) -> bool:
    return (
        identity.get("platform") == "win32"
        and identity.get("platform_machine") == "AMD64"
        and identity.get("pe_machine") == PE_AMD64
        and identity.get("pointer_width") == 8
    )


def interpreter_supported(identity: dict) -> bool:
    return (
        identity.get("python_version") == BASELINE_PYTHON
        and identity.get("python_implementation") == "CPython"
    )


def fixture_argv(executable: str, marker: str) -> list[str]:
    return [executable, "-c", _FIXTURE, marker]


def worker_command(
    executable: str, source: str, attempt: str, phase: str, result: str, marker: str
) -> list[str]:
    return [
        executable,
        "-m",
        "deploy.windows_etw_lifecycle",
        "--worker",
        "--source",
        source,
        "--attempt",
        attempt,
        "--phase",
        phase,
        "--result",
        result,
        "--marker",
        marker,
    ]


class PhaseLog:
    """Last phase is replaced on disk before the next native call."""

    def __init__(self, path: Path | None = None):
        self.path = path
        self.names: list[str] = []

    def mark(self, name: str) -> None:
        if name not in PHASES:
            name = "unknown"
        self.names.append(name)
        if self.path is None:
            return
        text = json.dumps({"phase": name, "seq": len(self.names)}, sort_keys=True) + "\n"
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)


def read_phase(path: Path | None) -> str:
    if path is None:
        return "unknown"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "unknown"
    if type(data) is not dict:
        return "unknown"
    phase = data.get("phase")
    if phase not in PHASES:
        return "unknown"
    return phase


class OutcomeRecorder:
    """Remember call outcomes. Handles stay on the inner API.

    Entry is recorded before the inner call. A raise leaves that attempt
    unknown. That wrapper attempt is not a native session acquisition.
    Candidate rows stay here so the receipt can project them without the
    provider's ownership verdict. Keys in those rows are not receipt fields.
    """

    def __init__(self, api):
        self._api = api
        self.start_calls = 0
        self.rows = {name: _blank_outcome() for name in _API_NAMES}
        self._flight = {name: "idle" for name in _API_NAMES}
        self._candidates: list[dict] = []
        self.candidates_complete = True

    def _entered(self, name: str) -> None:
        if self._flight[name] != "idle":
            return
        self._flight[name] = "open"
        self.rows[name] = {"attempted": True, "ok": None, "code": "unknown", "pending": None}

    def _complete(self, name: str, result) -> None:
        if self._flight[name] != "open":
            return
        self.rows[name] = _public_outcome(result)
        self._flight[name] = "done"

    def _seal_open(self, name: str) -> None:
        if self._flight[name] == "open":
            self._flight[name] = "done"

    def _invoke(self, name: str, call):
        self._entered(name)
        try:
            result = call()
        except Exception:
            self._seal_open(name)
            raise
        self._complete(name, result)
        return result

    def _retain_candidate(self, record) -> None:
        if self.candidates_complete is not True:
            return
        try:
            if len(self._candidates) >= etw.MAX_RETAINED_EVENTS:
                self.candidates_complete = False
                self._candidates.clear()
                return
            decoded = etw.decode_record(record)
        except Exception:
            self.candidates_complete = False
            self._candidates.clear()
            return
        if type(decoded) is not dict or decoded.get("disposition") != "event":
            return
        pid = decoded.get("pid")
        opcode = decoded.get("opcode")
        if type(pid) is not int or type(opcode) is not int:
            return
        kept = {
            "opcode": opcode,
            "version": decoded.get("version"),
            "pointer_width": decoded.get("pointer_width"),
            "pid": pid,
            "timestamp": decoded.get("timestamp"),
            "process_start_key_used": decoded.get("process_start_key_used") is True,
        }
        key = decoded.get("unique_process_key")
        if type(key) is int:
            kept["unique_process_key"] = key
        self._candidates.append(kept)

    @property
    def candidates(self) -> list[dict]:
        return list(self._candidates)

    def start_session(self, request):
        self.start_calls += 1
        return self._invoke("start_trace", lambda: self._api.start_session(request))

    def open_trace(self, session_name, on_event):
        def deliver(record):
            self._retain_candidate(record)
            return on_event(record)

        return self._invoke(
            "open_trace",
            lambda: self._api.open_trace(session_name, deliver),
        )

    def process_trace(self, trace_handle, on_ready):
        return self._invoke(
            "process_trace",
            lambda: self._api.process_trace(trace_handle, on_ready),
        )

    def stop_session(self, session_handle):
        return self._invoke("stop_trace", lambda: self._api.stop_session(session_handle))

    def close_trace(self, trace_handle):
        return self._invoke("close_trace", lambda: self._api.close_trace(trace_handle))

    def close_session(self, session_handle):
        close = getattr(self._api, "close_session", None)
        if close is None:
            return {"ok": False, "code": "unknown_handle"}
        return close(session_handle)

    def release_callbacks(self, trace_handle=None):
        release = getattr(self._api, "release_callbacks", None)
        if release is None:
            return True
        return release(trace_handle)

    def retain_recovery(self, state):
        retain = getattr(self._api, "retain_recovery", None)
        if retain is not None:
            retain(state)

    def note_consumer_close_completed(self, trace_handle):
        note = getattr(self._api, "note_consumer_close_completed", None)
        if note is None:
            return False
        return note(trace_handle)

    def ownership_view(self):
        view = getattr(self._api, "ownership_view", None)
        if view is None:
            return None
        return view()


_API_NAMES = ("start_trace", "open_trace", "process_trace", "stop_trace", "close_trace")


def _blank_outcome() -> dict:
    return {"attempted": False, "ok": None, "code": "not_attempted", "pending": None}


def _public_outcome(result) -> dict:
    if type(result) is not dict:
        return {"attempted": True, "ok": False, "code": "unknown", "pending": None}
    pending = result.get("pending")
    return {
        "attempted": True,
        "ok": result.get("ok") is True and pending is not True,
        "code": _api_code(result.get("code")),
        "pending": pending if type(pending) is bool else None,
    }


def _api_code(value) -> str:
    if type(value) is not str:
        return "unknown"
    if value in _API_CODES or _API_HEX.fullmatch(value):
        return value
    return "unknown"


def _nested_denial(code: str) -> bool:
    if code == "not_in_job_before_resume":
        return True
    for prefix in _SPAWN_PREFIXES:
        if code.startswith(prefix) and code[len(prefix) :] in _NESTED_SUFFIXES:
            return True
    return False


def _cleanup_code(value) -> str | None:
    if value is None:
        return None
    if type(value) is str and value in _CLEANUP_FAILURES:
        return value
    return "close_failed"


def _budget_remaining(started, now):
    """Seconds left from the pre-spawn sample. None means do not adopt.

    A backwards or unreadable clock is not a new window. This value does
    not interrupt a kernel wait that has not returned.
    """
    if type(started) not in (int, float) or type(now) not in (int, float):
        return None
    if now < started:
        return None
    remaining = WORKER_SECONDS - (now - started)
    if remaining <= 0:
        return 0
    return remaining


def _terminate_observation(result):
    """(succeeded, failure). Failure stays a termination code, not a close."""
    if type(result) is not tuple or len(result) != 2:
        return False, "terminate_failed"
    if result[0] is True:
        return True, None
    if result[1] in ("terminate_failed", "job_missing"):
        return False, result[1]
    return False, "terminate_failed"


def _close_observation(result):
    if type(result) is not tuple or len(result) != 2:
        return False, "close_failed"
    if result[0] is True:
        return True, None
    return False, _cleanup_code(result[1]) or "close_failed"


def _observed_terminate(job):
    try:
        return _terminate_observation(job.terminate())
    except Exception:
        return None, None


def _observed_drain(job, seconds):
    try:
        return job.wait_until_drained(seconds) is True
    except Exception:
        return None


def _job_cleanup(*, drain_ok, close_ok, prior_failure, close_failure):
    """Cleanup is drain plus close. Termination failure is not replaced."""
    failure = prior_failure
    if failure is None and drain_ok is False:
        failure = "drain_timeout"
    if failure is None and close_ok is False:
        failure = close_failure or "close_failed"
    if drain_ok is True and close_ok is True and failure is None:
        return True, None
    if drain_ok is False or close_ok is False or failure is not None:
        return False, failure
    return None, failure


def _supervisor_job(*, cleanup_ok, cleanup_failure, terminated, drain_ok, close_ok) -> dict:
    return {
        "cleanup_ok": cleanup_ok,
        "cleanup_failure": cleanup_failure,
        "terminated": terminated is True,
        "drain_ok": drain_ok,
        "close_ok": close_ok,
    }


def _count(value, limit: int = 1_000_000):
    if type(value) is not int or value < 0 or value > limit:
        return None
    return value


def _parser_version(opcode: int, version) -> bool:
    """Same version window as the lifecycle and counter decoders.

    Both reject a version below 2 or above 255. Rundown and any other opcode
    are not a Start, End, or PerfCtr version.
    """
    if type(opcode) is not int or type(version) is not int:
        return False
    if opcode not in (1, 2, 32):
        return False
    return 2 <= version <= 255


def _optional_parser_version(value) -> bool:
    return value is None or _parser_version(1, value)


def _projected_version(opcode: int, values: list) -> int | None:
    """One parser-supported version for one opcode, or refusal."""
    if not values:
        return None
    chosen = None
    for value in values:
        if not _parser_version(opcode, value):
            return None
        if chosen is None:
            chosen = value
        elif value != chosen:
            return None
    return chosen


def _clock_delta(start, creation):
    """Signed start minus creation in 100ns units, withheld outside the publication bound."""
    if type(start) is not int or type(creation) is not int:
        return None, None
    delta = start - creation
    if delta < -CLOCK_DELTA_PUBLICATION_BOUND or delta > CLOCK_DELTA_PUBLICATION_BOUND:
        return None, False
    return delta, True


def _ledger_count(job):
    if job is None:
        return None
    ledger = getattr(job, "ledger", None)
    rows = getattr(ledger, "rows", None)
    if type(rows) is not dict:
        return None
    return len(rows)


def _descendant_count(report):
    rows = None if type(report) is not dict else report.get("owned")
    if type(rows) is not list:
        return None
    found = 0
    for row in rows:
        if type(row) is dict and row.get("role") == "descendant":
            found += 1
    return found


def _sha40(value) -> str | None:
    if type(value) is str and _HEX40.fullmatch(value):
        return value
    return None


def _sha64(value) -> str | None:
    if type(value) is str and _HEX64.fullmatch(value):
        return value
    return None


def _loss_from(report) -> dict:
    loss = None if type(report) is not dict else report.get("loss")
    if type(loss) is not dict:
        return {"events_lost": None, "log_buffers_lost": None, "real_time_buffers_lost": None}
    return {
        "events_lost": _count(loss.get("events_lost")),
        "log_buffers_lost": _count(loss.get("log_buffers_lost")),
        "real_time_buffers_lost": _count(loss.get("real_time_buffers_lost")),
    }


def _gap_names(report) -> list[str]:
    if type(report) is not dict:
        return []
    coverage = report.get("coverage")
    found = []
    if type(coverage) is dict and type(coverage.get("gaps")) is list:
        found.extend(coverage["gaps"])
    names = sorted({item for item in found if type(item) is str and item in _GAP_REASONS})
    return names[:40]


def _diagnostic_count(report, name: str):
    if type(report) is not dict:
        return None
    limits = report.get("limits")
    counts = None if type(limits) is not dict else limits.get("gap_counts")
    if type(counts) is not dict or name not in counts:
        return 0
    return _count(counts.get(name), 65535)


def _owned_root(report, root_pid: int | None):
    rows = None if type(report) is not dict else report.get("owned")
    roots = []
    if type(rows) is not list or type(root_pid) is not int:
        return None
    for row in rows:
        if type(row) is dict and row.get("role") == "root" and row.get("pid") == root_pid:
            roots.append(row)
    if len(roots) != 1:
        return None
    return roots[0]


def _owned_binding(row: dict, root_creation: int | None, gaps: set[str]) -> tuple[bool, dict]:
    """Strict ownership fields. A candidate PID is not an owned root."""
    start = row.get("etw_start_filetime")
    end = row.get("etw_end_filetime")
    start_ok = type(start) is int and start == row.get("job_creation") == root_creation
    end_present = row.get("exit_observed") is True and type(end) is int
    timestamps_equal = start == end if end_present and type(start) is int else None
    key_equal = True if end_present and "exit_key_mismatch" not in gaps else None
    opcode32 = row.get("terminal_counter_opcode32") is True and end_present and not timestamps_equal
    blocked = bool(gaps & _BLOCKING_GAPS) or timestamps_equal is True
    bound = bool(
        start_ok
        and end_present
        and key_equal is True
        and opcode32
        and row.get("process_start_key_used") is False
        and row.get("opcode33_used_as_terminal") is False
        and not blocked
    )
    width = row.get("pointer_width")
    version = row.get("event_version")
    delta, delta_bounded = _clock_delta(start if type(start) is int else None, root_creation)
    return bound, {
        "start_end_key_equal": True if bound else key_equal,
        "opcodes": [1, 2, 32] if bound else [],
        "pointer_width": width if width in (4, 8) else None,
        "version_opcode_1": version if _parser_version(1, version) else None,
        "start_matches_creation": start_ok,
        "end_present": end_present,
        "timestamps_equal": timestamps_equal,
        "opcode32_inside_paired_lifetime": opcode32,
        "process_start_key_used": row.get("process_start_key_used") is True,
        "clock_delta_100ns": delta,
        "clock_delta_bounded": delta_bounded,
    }


def _candidate_fields(
    events,
    root_pid: int | None,
    root_creation: int | None,
    *,
    complete: bool,
) -> dict:
    """Bounded observations for one retained PID. The PID and key stay out.

    Versions are kept per opcode. Rundown is not one of them. The clock delta
    is not a second binding rule.
    """
    blank = {
        "start_end_key_equal": None,
        "opcodes": [],
        "pointer_width": None,
        "version_opcode_1": None,
        "version_opcode_2": None,
        "version_opcode_32": None,
        "start_matches_creation": None,
        "end_present": None,
        "timestamps_equal": None,
        "opcode32_inside_paired_lifetime": None,
        "process_start_key_used": False,
        "clock_delta_100ns": None,
        "clock_delta_bounded": None,
        "candidate_generations": None,
    }
    if complete is not True or type(events) is not list or type(root_pid) is not int:
        return blank
    selected = [event for event in events if type(event) is dict and event.get("pid") == root_pid]
    opcodes = []
    widths = []
    version_events = {1: [], 2: [], 32: []}
    starts = []
    ends = []
    counters = []
    key_used = False
    for event in selected:
        opcode = event.get("opcode")
        if opcode in (1, 2, 32) and opcode not in opcodes:
            opcodes.append(opcode)
        if event.get("process_start_key_used") is True:
            key_used = True
        width = event.get("pointer_width")
        if width in (4, 8):
            widths.append(width)
        if opcode in version_events:
            version_events[opcode].append(event.get("version"))
        if opcode == 1:
            starts.append(event)
        elif opcode == 2:
            ends.append(event)
        elif opcode == 32:
            counters.append(event)
    start_matches = None
    if len(starts) == 1 and type(root_creation) is int:
        stamp = starts[0].get("timestamp")
        if type(stamp) is int:
            start_matches = stamp == root_creation
    if len(ends) == 1:
        end_present = True
    elif len(ends) == 0 and len(starts) == 1:
        end_present = False
    else:
        end_present = None
    timestamps_equal = None
    key_equal = None
    opcode32 = None
    if len(starts) == 1 and len(ends) == 1:
        start_stamp = starts[0].get("timestamp")
        end_stamp = ends[0].get("timestamp")
        if type(start_stamp) is int and type(end_stamp) is int:
            timestamps_equal = start_stamp == end_stamp
        start_key = starts[0].get("unique_process_key")
        end_key = ends[0].get("unique_process_key")
        if type(start_key) is int and type(end_key) is int:
            key_equal = start_key == end_key
        # One paired lifetime needs this Start and End to share a key.
        # A different or incomparable key leaves the relation unknown.
        # The timestamp and key comparisons above stay on their own fields.
        if key_equal is True and timestamps_equal is True:
            opcode32 = False if counters else None
        elif key_equal is True and timestamps_equal is False:
            inside = 0
            boundary = 0
            comparable = True
            for counter in counters:
                counter_stamp = counter.get("timestamp")
                if type(counter_stamp) is not int:
                    comparable = False
                    break
                if counter_stamp == start_stamp or counter_stamp == end_stamp:
                    boundary += 1
                elif start_stamp < counter_stamp < end_stamp:
                    inside += 1
            if not comparable:
                opcode32 = None
            elif inside == 1 and boundary == 0:
                opcode32 = True
            elif counters:
                opcode32 = False
    width_value = widths[0] if widths and all(item == widths[0] for item in widths) else None
    delta, delta_bounded = None, None
    if len(starts) == 1:
        delta, delta_bounded = _clock_delta(starts[0].get("timestamp"), root_creation)
    blank.update(
        {
            "start_end_key_equal": key_equal,
            "opcodes": [code for code in (1, 2, 32) if code in opcodes],
            "pointer_width": width_value,
            "version_opcode_1": _projected_version(1, version_events[1]),
            "version_opcode_2": _projected_version(2, version_events[2]),
            "version_opcode_32": _projected_version(32, version_events[32]),
            "start_matches_creation": start_matches,
            "end_present": end_present,
            "timestamps_equal": timestamps_equal,
            "opcode32_inside_paired_lifetime": opcode32,
            "process_start_key_used": key_used,
            "clock_delta_100ns": delta,
            "clock_delta_bounded": delta_bounded,
            "candidate_generations": _count(len(starts)),
        }
    )
    return blank


def project_sequence(
    report,
    root_pid: int | None,
    root_creation: int | None,
    events=None,
    *,
    events_complete: bool = True,
) -> dict:
    """Candidate relations for the retained PID, then the ownership verdict.

    Opcode 33 stays a rundown count. Arrival order is not a sequence.
    A matching PID does not bind the root and the kernel key is not copied.
    Separate opcode versions do not prove that binding.
    """
    unknown = _sequence(bound=False, binding="unknown", gate="unknown")
    if type(report) is not dict:
        return unknown
    coverage = report.get("coverage") if type(report.get("coverage")) is dict else {}
    gaps = set(_gap_names(report))
    base = _sequence(bound=False, binding="unbound", gate="unpassed")
    base["opcode33_rundown_ignored"] = _count(coverage.get("opcode33_ignored"))
    if events is not None:
        base.update(
            _candidate_fields(
                events,
                root_pid,
                root_creation,
                complete=events_complete,
            )
        )
    row = _owned_root(report, root_pid)
    if row is None:
        base["candidate_relation"] = "unproven"
        return base
    bound, fields = _owned_binding(row, root_creation, gaps)
    if events is None:
        base.update(fields)
    base["bound"] = bound
    base["binding"] = "exact_creation" if bound else "unbound"
    base["start_end_gate"] = "passed" if bound else "unpassed"
    base["candidate_relation"] = "exact_creation" if bound else "unproven"
    return base


def _sequence(*, bound: bool, binding: str, gate: str) -> dict:
    return {
        "bound": bound,
        "binding": binding,
        "start_end_gate": gate,
        "start_end_key_equal": None,
        "opcodes": [],
        "pointer_width": None,
        "version_opcode_1": None,
        "version_opcode_2": None,
        "version_opcode_32": None,
        "start_matches_creation": None,
        "end_present": None,
        "timestamps_equal": None,
        "opcode32_inside_paired_lifetime": None,
        "opcode33_rundown_ignored": None,
        "process_start_key_used": False,
        "clock_delta_100ns": None,
        "clock_delta_bounded": None,
        "clock_client_context": CLOCK_CLIENT_CONTEXT,
        "clock_raw_timestamp": CLOCK_RAW_TIMESTAMP,
        "candidate_generations": None,
        "candidate_relation": "unproven",
    }


def _counter_view(report) -> dict:
    if type(report) is not dict:
        return {
            "passed": False,
            "births": None,
            "exits": None,
            "terminal_counters": None,
            "status": "unknown",
        }
    coverage = report.get("coverage") if type(report.get("coverage")) is dict else {}
    births = _count(coverage.get("births"))
    exits = _count(coverage.get("exits"))
    terminals = _count(coverage.get("terminal_counters"))
    status = coverage.get("status")
    if status not in ("reconciled", "missing"):
        status = "unknown"
    gaps = set(_gap_names(report))
    passed = bool(
        status == "reconciled"
        and not gaps
        and births == EXPECTED_TOTAL
        and exits == EXPECTED_TOTAL
        and terminals == EXPECTED_TOTAL
        and coverage.get("job_total_processes") == EXPECTED_TOTAL
        and coverage.get("job_active_processes") == EXPECTED_ACTIVE
    )
    return {
        "passed": passed,
        "births": births,
        "exits": exits,
        "terminal_counters": terminals,
        "status": status,
    }


def _preserved(report) -> dict:
    if type(report) is not dict:
        return {
            "qualification": "unknown",
            "native_unit_corroboration": "unknown",
            "resource_acceptance": None,
            "budget_compared": None,
            "production_accounting_switched": None,
            "telemetry_enabled": False,
        }
    budget = report.get("budget") if type(report.get("budget")) is dict else {}
    qualification = report.get("qualification")
    unit = report.get("native_unit_corroboration")
    switched = report.get("production_accounting_switched")
    acceptance = report.get("resource_acceptance")
    compared = budget.get("compared")
    return {
        "qualification": qualification
        if type(qualification) is str and _PRESERVED.fullmatch(qualification)
        else "unknown",
        "native_unit_corroboration": unit
        if type(unit) is str and _PRESERVED.fullmatch(unit)
        else "unknown",
        "resource_acceptance": acceptance if type(acceptance) is bool else None,
        "budget_compared": compared if type(compared) is bool else None,
        "production_accounting_switched": switched if type(switched) is bool else None,
        "telemetry_enabled": False,
    }


def _etw_cleanup(report, *, deadline: bool) -> dict:
    if deadline:
        return {
            "verified": False,
            "reason": "worker_deadline",
            "session_released": None,
            "callbacks_released": None,
            "consumer_finished": None,
            "close_pending": None,
            "close_failed": None,
            "stop_ok": None,
        }
    if type(report) is not dict:
        return {
            "verified": False,
            "reason": "not_started",
            "session_released": None,
            "callbacks_released": None,
            "consumer_finished": None,
            "close_pending": None,
            "close_failed": None,
            "stop_ok": None,
        }
    session = report.get("session") if type(report.get("session")) is dict else {}
    gaps = set(_gap_names(report))
    close_pending = "close_pending" in gaps
    close_failed = "close_failed" in gaps
    stop_ok = session.get("stop_ok") is True
    close_ok = session.get("close_ok") is True and not close_pending
    released = session.get("session_released") is True
    callbacks = session.get("callbacks_released") is True
    finished = session.get("consumer_finished") is True
    verified = bool(stop_ok and close_ok and released and callbacks and finished)
    reason = None
    if not verified:
        if close_pending:
            reason = "close_pending"
        elif close_failed:
            reason = "close_failed"
        elif not stop_ok:
            reason = "stop_failed"
        else:
            reason = "unverified"
    return {
        "verified": verified,
        "reason": reason,
        "session_released": released,
        "callbacks_released": callbacks,
        "consumer_finished": finished,
        "close_pending": close_pending,
        "close_failed": close_failed,
        "stop_ok": stop_ok,
    }


def _measured_job(report, snapshot, drain_ok, close_ok, cleanup_failure, observed=None) -> dict:
    coverage = {}
    if type(report) is dict and type(report.get("coverage")) is dict:
        coverage = report["coverage"]
    total = _count(coverage.get("job_total_processes"))
    active = _count(coverage.get("job_active_processes"))
    observer = None
    if type(snapshot) is dict and type(snapshot.get("observer_in_measured_group")) is bool:
        observer = snapshot["observer_in_measured_group"]
    cleanup_ok, failure = _job_cleanup(
        drain_ok=drain_ok,
        close_ok=close_ok,
        prior_failure=None,
        close_failure=cleanup_failure,
    )
    extra = observed if type(observed) is dict else {}
    return {
        "census_total": total,
        "census_active": active,
        "census_expected_total": EXPECTED_TOTAL,
        "census_expected_active": EXPECTED_ACTIVE,
        "census_matches_expected": total == EXPECTED_TOTAL and active == EXPECTED_ACTIVE,
        "observer_in_measured_job": observer,
        "drain_ok": drain_ok,
        "close_ok": close_ok,
        "cleanup_ok": cleanup_ok,
        "cleanup_failure": failure,
        "census_before_creation": _count(extra.get("census_before_creation")),
        "census_after_create_before_resume": _count(extra.get("census_after_create_before_resume")),
        "census_after_drain": _count(extra.get("census_after_drain")),
        "candidate_children": _count(extra.get("candidate_children")),
        "ledger_count": _count(extra.get("ledger_count")),
        "identities_missing": _count(extra.get("identities_missing")),
    }


def _marker_written(path: Path | None):
    if path is None:
        return None
    try:
        if not path.is_file() or path.stat().st_size != 1:
            return False
        return path.read_bytes() == b"1"
    except OSError:
        return False


def base_receipt() -> dict:
    return {
        "api": {name: _blank_outcome() for name in _API_NAMES},
        "architecture_supported": False,
        "attempt": "unknown",
        "baseline": _baseline(),
        "bounds": _bounds(),
        "callback_evidence": False,
        "callbacks": None,
        "check": CHECK,
        "counter_reconciliation": _counter_view(None),
        "diagnostics": {
            "parser_failed": None,
            "record_conversion_failed": None,
            "callbacks_exceeded": None,
            "retained_records_exceeded": None,
            "gaps": [],
        },
        "dispatch_authorized": False,
        "etw_cleanup": _etw_cleanup(None, deadline=False),
        "fixture_completion_marker": None,
        "fixture_launched": False,
        "head": None,
        "identity": _blank_identity(),
        "last_phase": "supervisor_checked",
        "loss": _loss_from(None),
        "measured_job": _measured_job(None, None, None, None, None),
        "native_session_starts": None,
        "owned_event_qualified": False,
        "phases": ["supervisor_checked"],
        "privacy": _privacy(),
        "preserved": _preserved(None),
        "provider_sha256": None,
        "provider_sha256_matches": False,
        "readiness_before_process_trace": None,
        "requested_source": None,
        "retained_records": None,
        "run_id": "unknown",
        "schema": SCHEMA,
        "sequence": _sequence(bound=False, binding="unknown", gate="unknown"),
        "session_start_calls": None,
        "source_matches": False,
        "supervisor_job": _supervisor_job(
            cleanup_ok=None,
            cleanup_failure=None,
            terminated=False,
            drain_ok=None,
            close_ok=None,
        ),
        "unsupported": None,
        "worker": {
            "deadline_exceeded": False,
            "bound_seconds": WORKER_SECONDS,
            "report_adopted": False,
        },
    }


def _baseline() -> dict:
    return {
        "anchor_source": ANCHOR_SOURCE,
        "declaration_run": DECLARATION_RUN,
        "declaration_source": DECLARATION_SOURCE,
        "oracle_run": ORACLE_RUN,
        "oracle_source": ORACLE_SOURCE,
        "sdk": SDK_VERSION,
        "provider_sha256": PROVIDER_SHA256,
    }


def _bounds() -> dict:
    return {
        "ready_seconds": READY_SECONDS,
        "observer_drain_seconds": OBSERVER_DRAIN_SECONDS,
        "observer_drain_joins": OBSERVER_DRAIN_JOINS,
        "worker_seconds": WORKER_SECONDS,
        "supervisor_drain_seconds": SUPERVISOR_DRAIN_SECONDS,
        "native_retries": 0,
    }


def _privacy() -> dict:
    return {
        "unique_process_key_omitted": True,
        "private_owner_omitted": True,
        "payloads_omitted": True,
        "handles_omitted": True,
        "unrelated_rows_omitted": True,
        "command_lines_omitted": True,
        "environment_omitted": True,
        "paths_omitted": True,
        "exception_text_omitted": True,
        "public_safe_disposition": False,
    }


def _blank_identity() -> dict:
    return {
        "pe_machine": None,
        "platform_machine": "unknown",
        "platform": "unknown",
        "python_version": "unknown",
        "python_implementation": "unknown",
        "pointer_width": None,
        "runner_os": "unknown",
    }


def _normalize_identity(identity: dict | None) -> dict:
    blank = _blank_identity()
    if type(identity) is not dict:
        return blank
    machine = identity.get("pe_machine")
    width = identity.get("pointer_width")
    blank["pe_machine"] = machine if type(machine) is int and 0 < machine < 65536 else None
    blank["pointer_width"] = width if width in (4, 8) else None
    for key in (
        "platform_machine",
        "platform",
        "python_implementation",
        "runner_os",
    ):
        value = identity.get(key)
        blank[key] = value if type(value) is str and _TOKEN.fullmatch(value) else "unknown"
    version = identity.get("python_version")
    blank["python_version"] = (
        version if type(version) is str and _PY.fullmatch(version) else "unknown"
    )
    return blank


def _phases(names: list[str]) -> list[str]:
    kept = [name for name in names if name in PHASES][:24]
    return kept or ["unknown"]


def receipt_schema_ok(data: object) -> bool:
    if type(data) is not dict or set(data) != _TOP_KEYS:
        return False
    if data["schema"] != SCHEMA or data["check"] != CHECK:
        return False
    if data["owned_event_qualified"] is not True and data["owned_event_qualified"] is not False:
        return False
    if not _schema_api(data["api"]):
        return False
    if not _schema_identity(data["identity"]) or not _schema_baseline(data["baseline"]):
        return False
    if data["bounds"] != _bounds() or data["privacy"] != _privacy():
        return False
    if not _schema_sequence(data["sequence"]) or not _schema_counter(
        data["counter_reconciliation"]
    ):
        return False
    if not _schema_diagnostics(data["diagnostics"]) or not _schema_loss(data["loss"]):
        return False
    if not _schema_measured(data["measured_job"]) or not _schema_supervisor(data["supervisor_job"]):
        return False
    if not _schema_etw(data["etw_cleanup"]) or not _schema_preserved(data["preserved"]):
        return False
    if not _schema_worker(data["worker"]):
        return False
    if data["unsupported"] is not None and data["unsupported"] not in _UNSUPPORTED:
        return False
    if data["last_phase"] not in PHASES:
        return False
    phases = data["phases"]
    if type(phases) is not list or not 1 <= len(phases) <= 24:
        return False
    if any(item not in PHASES for item in phases):
        return False
    if data["attempt"] != "unknown" and not _ATTEMPT.fullmatch(str(data["attempt"])):
        return False
    if data["run_id"] != "unknown" and not _RUN.fullmatch(str(data["run_id"])):
        return False
    for key in ("requested_source", "head"):
        if data[key] is not None and _sha40(data[key]) is None:
            return False
    if data["provider_sha256"] is not None and _sha64(data["provider_sha256"]) is None:
        return False
    for key in (
        "architecture_supported",
        "callback_evidence",
        "dispatch_authorized",
        "provider_sha256_matches",
        "source_matches",
    ):
        if type(data[key]) is not bool:
            return False
    if data["fixture_launched"] is not None and type(data["fixture_launched"]) is not bool:
        return False
    if (
        data["fixture_completion_marker"] is not None
        and type(data["fixture_completion_marker"]) is not bool
    ):
        return False
    if (
        data["readiness_before_process_trace"] is not None
        and type(data["readiness_before_process_trace"]) is not bool
    ):
        return False
    for key in ("callbacks", "retained_records", "native_session_starts", "session_start_calls"):
        if not _optional_count(data[key]):
            return False
    if _forbidden_text(data):
        return False
    return True


def _opcode_sequence(value) -> bool:
    """Empty or an ascending subset of the candidate opcodes 1, 2, and 32."""
    if type(value) is not list or len(value) > 3:
        return False
    previous = 0
    seen = set()
    for item in value:
        if item not in (1, 2, 32) or item in seen or not item > previous:
            return False
        seen.add(item)
        previous = item
    return True


def _optional_count(value) -> bool:
    return value is None or (type(value) is int and 0 <= value <= 1_000_000)


def _schema_api(value) -> bool:
    if type(value) is not dict or set(value) != set(_API_NAMES):
        return False
    for row in value.values():
        if type(row) is not dict or set(row) != {"attempted", "ok", "code", "pending"}:
            return False
        if row["attempted"] is not None and type(row["attempted"]) is not bool:
            return False
        if row["ok"] is not None and type(row["ok"]) is not bool:
            return False
        if row["pending"] is not None and type(row["pending"]) is not bool:
            return False
        if row["code"] not in _API_CODES and not _API_HEX.fullmatch(str(row["code"])):
            return False
    return True


def _schema_identity(value) -> bool:
    keys = {
        "pe_machine",
        "platform_machine",
        "platform",
        "python_version",
        "python_implementation",
        "pointer_width",
        "runner_os",
    }
    if type(value) is not dict or set(value) != keys:
        return False
    machine = value["pe_machine"]
    if machine is not None and (type(machine) is not int or not 0 < machine < 65536):
        return False
    if value["pointer_width"] not in (None, 4, 8):
        return False
    if not _PY.fullmatch(value["python_version"]) and value["python_version"] != "unknown":
        return False
    for key in ("platform_machine", "platform", "python_implementation", "runner_os"):
        if not _TOKEN.fullmatch(value[key]):
            return False
    return True


def _schema_baseline(value) -> bool:
    return type(value) is dict and value == _baseline()


def _schema_sequence(value) -> bool:
    keys = set(_sequence(bound=False, binding="unknown", gate="unknown"))
    if type(value) is not dict or set(value) != keys:
        return False
    if type(value["bound"]) is not bool or value["binding"] not in _BINDINGS:
        return False
    if value["start_end_gate"] not in _GATES:
        return False
    if value["start_end_key_equal"] is not None and type(value["start_end_key_equal"]) is not bool:
        return False
    if not _opcode_sequence(value["opcodes"]):
        return False
    if value["pointer_width"] not in (None, 4, 8):
        return False
    for key in ("version_opcode_1", "version_opcode_2", "version_opcode_32"):
        if not _optional_parser_version(value[key]):
            return False
    if not _optional_count(value["opcode33_rundown_ignored"]):
        return False
    delta = value["clock_delta_100ns"]
    published = value["clock_delta_bounded"]
    if published is None:
        if delta is not None:
            return False
    elif published is True:
        if (
            type(delta) is not int
            or delta < -CLOCK_DELTA_PUBLICATION_BOUND
            or delta > CLOCK_DELTA_PUBLICATION_BOUND
        ):
            return False
    elif published is False:
        if delta is not None:
            return False
    else:
        return False
    if (
        type(value["clock_client_context"]) is not int
        or value["clock_client_context"] != CLOCK_CLIENT_CONTEXT
    ):
        return False
    if (
        type(value["clock_raw_timestamp"]) is not bool
        or value["clock_raw_timestamp"] is not CLOCK_RAW_TIMESTAMP
    ):
        return False
    if not _optional_count(value["candidate_generations"]):
        return False
    if value["candidate_relation"] not in _CANDIDATE_RELATIONS:
        return False
    for key in (
        "start_matches_creation",
        "end_present",
        "timestamps_equal",
        "opcode32_inside_paired_lifetime",
    ):
        if value[key] is not None and type(value[key]) is not bool:
            return False
    if type(value["process_start_key_used"]) is not bool:
        return False
    return True


def _schema_counter(value) -> bool:
    keys = {"passed", "births", "exits", "terminal_counters", "status"}
    if type(value) is not dict or set(value) != keys or type(value["passed"]) is not bool:
        return False
    if value["status"] not in ("reconciled", "missing", "unknown"):
        return False
    return all(_optional_count(value[key]) for key in ("births", "exits", "terminal_counters"))


def _schema_diagnostics(value) -> bool:
    keys = {
        "parser_failed",
        "record_conversion_failed",
        "callbacks_exceeded",
        "retained_records_exceeded",
        "gaps",
    }
    if type(value) is not dict or set(value) != keys:
        return False
    for key in keys - {"gaps"}:
        if not _optional_count(value[key]):
            return False
    gaps = value["gaps"]
    if type(gaps) is not list or len(gaps) > 40 or any(item not in _GAP_REASONS for item in gaps):
        return False
    return True


def _schema_loss(value) -> bool:
    keys = {"events_lost", "log_buffers_lost", "real_time_buffers_lost"}
    if type(value) is not dict or set(value) != keys:
        return False
    return all(_optional_count(value[key]) for key in keys)


def _schema_measured(value) -> bool:
    keys = {
        "census_total",
        "census_active",
        "census_expected_total",
        "census_expected_active",
        "census_matches_expected",
        "observer_in_measured_job",
        "drain_ok",
        "close_ok",
        "cleanup_ok",
        "cleanup_failure",
        "census_before_creation",
        "census_after_create_before_resume",
        "census_after_drain",
        "candidate_children",
        "ledger_count",
        "identities_missing",
    }
    if type(value) is not dict or set(value) != keys:
        return False
    if (
        value["census_expected_total"] != EXPECTED_TOTAL
        or value["census_expected_active"] != EXPECTED_ACTIVE
    ):
        return False
    if type(value["census_matches_expected"]) is not bool:
        return False
    if not _optional_count(value["census_total"]) or not _optional_count(value["census_active"]):
        return False
    for key in (
        "census_before_creation",
        "census_after_create_before_resume",
        "census_after_drain",
        "candidate_children",
        "ledger_count",
        "identities_missing",
    ):
        if not _optional_count(value[key]):
            return False
    if (
        value["observer_in_measured_job"] is not None
        and type(value["observer_in_measured_job"]) is not bool
    ):
        return False
    for key in ("drain_ok", "close_ok", "cleanup_ok"):
        if value[key] is not None and type(value[key]) is not bool:
            return False
    failure = value["cleanup_failure"]
    return failure is None or failure in _CLEANUP_FAILURES


def _schema_supervisor(value) -> bool:
    keys = {"cleanup_ok", "cleanup_failure", "terminated", "drain_ok", "close_ok"}
    if type(value) is not dict or set(value) != keys or type(value["terminated"]) is not bool:
        return False
    for key in ("cleanup_ok", "drain_ok", "close_ok"):
        if value[key] is not None and type(value[key]) is not bool:
            return False
    failure = value["cleanup_failure"]
    return failure is None or failure in _CLEANUP_FAILURES


def _schema_etw(value) -> bool:
    keys = {
        "verified",
        "reason",
        "session_released",
        "callbacks_released",
        "consumer_finished",
        "close_pending",
        "close_failed",
        "stop_ok",
    }
    if type(value) is not dict or set(value) != keys or type(value["verified"]) is not bool:
        return False
    if value["reason"] is not None and value["reason"] not in _ETW_REASONS:
        return False
    for key in keys - {"verified", "reason"}:
        if value[key] is not None and type(value[key]) is not bool:
            return False
    return True


def _schema_preserved(value) -> bool:
    keys = {
        "qualification",
        "native_unit_corroboration",
        "resource_acceptance",
        "budget_compared",
        "production_accounting_switched",
        "telemetry_enabled",
    }
    if type(value) is not dict or set(value) != keys or value["telemetry_enabled"] is not False:
        return False
    for key in ("qualification", "native_unit_corroboration"):
        if not _PRESERVED.fullmatch(value[key]):
            return False
    for key in ("resource_acceptance", "budget_compared", "production_accounting_switched"):
        if value[key] is not None and type(value[key]) is not bool:
            return False
    return True


def _schema_worker(value) -> bool:
    keys = {"deadline_exceeded", "bound_seconds", "report_adopted"}
    if type(value) is not dict or set(value) != keys:
        return False
    return (
        type(value["deadline_exceeded"]) is bool
        and value["bound_seconds"] == WORKER_SECONDS
        and type(value["report_adopted"]) is bool
    )


def _forbidden_text(data: dict) -> bool:
    try:
        text = json.dumps(data, sort_keys=True)
    except (TypeError, ValueError):
        return True
    for key in _FORBIDDEN_KEYS:
        if f'"{key}"' in text:
            return True
    return False


def etw_lifecycle_receipt_qualifies(data: object) -> bool:
    """True only for this driver's evidenced lifecycle. Job cleanup is not enough."""
    if not receipt_schema_ok(data):
        return False
    assert isinstance(data, dict)
    identity = data["identity"]
    sequence = data["sequence"]
    counter = data["counter_reconciliation"]
    measured = data["measured_job"]
    supervisor = data["supervisor_job"]
    cleanup = data["etw_cleanup"]
    preserved = data["preserved"]
    loss = data["loss"]
    diagnostics = data["diagnostics"]
    api = data["api"]
    if data["unsupported"] is not None or data["dispatch_authorized"] is not True:
        return False
    if data["source_matches"] is not True or data["provider_sha256_matches"] is not True:
        return False
    if data["requested_source"] != data["head"] or data["provider_sha256"] != PROVIDER_SHA256:
        return False
    if not architecture_supported(identity) or not interpreter_supported(identity):
        return False
    if identity["runner_os"] != "Windows":
        return False
    if data["run_id"] == "unknown" or data["attempt"] == "unknown":
        return False
    if data["fixture_launched"] is not True or data["fixture_completion_marker"] is not True:
        return False
    if data["native_session_starts"] != 1 or data["session_start_calls"] != 1:
        return False
    if data["readiness_before_process_trace"] is not True or data["callback_evidence"] is not True:
        return False
    if type(data["callbacks"]) is not int or data["callbacks"] < 1:
        return False
    if type(data["retained_records"]) is not int or data["retained_records"] < 1:
        return False
    for name in _API_NAMES:
        row = api[name]
        if row["attempted"] is not True or row["ok"] is not True or row["code"] != "ok":
            return False
        if name == "close_trace" and row["pending"] is not False:
            return False
    if sequence["bound"] is not True or sequence["binding"] != "exact_creation":
        return False
    if sequence["start_end_gate"] != "passed" or sequence["start_end_key_equal"] is not True:
        return False
    if sequence["opcodes"] != [1, 2, 32] or sequence["process_start_key_used"] is not False:
        return False
    if (
        sequence["opcode32_inside_paired_lifetime"] is not True
        or sequence["timestamps_equal"] is not False
    ):
        return False
    if sequence["start_matches_creation"] is not True or sequence["end_present"] is not True:
        return False
    if sequence["pointer_width"] != 8:
        return False
    for name in ("version_opcode_1", "version_opcode_2", "version_opcode_32"):
        version = sequence[name]
        if type(version) is not int or not 2 <= version <= 255:
            return False
    if sequence["candidate_relation"] != "exact_creation":
        return False
    if counter["passed"] is not True or counter["status"] != "reconciled":
        return False
    if counter["births"] != 1 or counter["exits"] != 1 or counter["terminal_counters"] != 1:
        return False
    census_holds = (
        measured["census_total"] == EXPECTED_TOTAL and measured["census_active"] == EXPECTED_ACTIVE
    )
    if measured["census_matches_expected"] is not census_holds or census_holds is not True:
        return False
    if measured["observer_in_measured_job"] is not False:
        return False
    measured_cleanup = (
        measured["drain_ok"] is True
        and measured["close_ok"] is True
        and measured["cleanup_failure"] is None
    )
    if measured["cleanup_ok"] is not measured_cleanup or measured_cleanup is not True:
        return False
    supervisor_cleanup = (
        supervisor["drain_ok"] is True
        and supervisor["close_ok"] is True
        and supervisor["cleanup_failure"] is None
    )
    if supervisor["cleanup_ok"] is not supervisor_cleanup or supervisor_cleanup is not True:
        return False
    if supervisor["terminated"] is not False:
        return False
    etw_holds = (
        cleanup["session_released"] is True
        and cleanup["callbacks_released"] is True
        and cleanup["consumer_finished"] is True
        and cleanup["stop_ok"] is True
        and cleanup["close_pending"] is False
        and cleanup["close_failed"] is False
        and cleanup["reason"] is None
    )
    if cleanup["verified"] is not etw_holds or etw_holds is not True:
        return False
    if (
        data["worker"]["deadline_exceeded"] is not False
        or data["worker"]["report_adopted"] is not True
    ):
        return False
    if data["last_phase"] != "supervisor_finished" or "worker_finished" not in data["phases"]:
        return False
    if any(loss[name] != 0 for name in loss) or diagnostics["gaps"]:
        return False
    for name in (
        "parser_failed",
        "record_conversion_failed",
        "callbacks_exceeded",
        "retained_records_exceeded",
    ):
        if diagnostics[name] != 0:
            return False
    if (
        preserved["qualification"] != "unqualified"
        or preserved["native_unit_corroboration"] != "unrun"
    ):
        return False
    if preserved["resource_acceptance"] is not False or preserved["budget_compared"] is not False:
        return False
    if (
        preserved["production_accounting_switched"] is not False
        or preserved["telemetry_enabled"] is not False
    ):
        return False
    if data["privacy"]["public_safe_disposition"] is not False:
        return False
    return True


def stored_qualification_matches(data: object) -> bool:
    if not receipt_schema_ok(data):
        return False
    assert isinstance(data, dict)
    return data["owned_event_qualified"] is etw_lifecycle_receipt_qualifies(data)


def _seal(receipt: dict) -> dict:
    receipt["owned_event_qualified"] = False
    if not receipt_schema_ok(receipt):
        return _static_receipt("privacy_rejected")
    receipt["owned_event_qualified"] = etw_lifecycle_receipt_qualifies(receipt)
    if not receipt_schema_ok(receipt) or not stored_qualification_matches(receipt):
        return _static_receipt("privacy_rejected")
    return receipt


def _static_receipt(unsupported: str) -> dict:
    receipt = base_receipt()
    if unsupported not in _UNSUPPORTED:
        unsupported = "worker_exception"
    receipt["unsupported"] = unsupported
    receipt["owned_event_qualified"] = False
    return receipt


def _context_receipt(
    *,
    requested_source: str | None,
    head: str | None,
    provider_hash: str | None,
    attempt: str,
    run_id: str,
    identity: dict,
    dispatch_authorized: bool,
) -> dict:
    receipt = base_receipt()
    source = _sha40(requested_source)
    checked = _sha40(head)
    digest = _sha64(provider_hash)
    receipt["requested_source"] = source
    receipt["head"] = checked
    receipt["source_matches"] = bool(source and source == checked)
    receipt["provider_sha256"] = digest
    receipt["provider_sha256_matches"] = digest == PROVIDER_SHA256
    receipt["attempt"] = attempt if _ATTEMPT.fullmatch(attempt or "") else "unknown"
    receipt["run_id"] = run_id if _RUN.fullmatch(run_id or "") else "unknown"
    receipt["identity"] = _normalize_identity(identity)
    receipt["architecture_supported"] = architecture_supported(receipt["identity"])
    receipt["dispatch_authorized"] = dispatch_authorized is True
    return receipt


def _apply_report(
    receipt: dict,
    report,
    recorder: OutcomeRecorder | None,
    snapshot,
    *,
    launched: bool,
    marker,
    starts: int | None,
    ready: bool | None,
    measured_drain,
    measured_close,
    measured_failure,
    failure: str | None,
    phases: list[str],
    job=None,
    census=None,
) -> dict:
    receipt["phases"] = _phases(phases)
    receipt["last_phase"] = receipt["phases"][-1]
    receipt["fixture_launched"] = launched is True
    receipt["fixture_completion_marker"] = marker
    receipt["native_session_starts"] = _count(starts, 65535) if starts is not None else None
    receipt["session_start_calls"] = (
        None if recorder is None else _count(recorder.start_calls, 65535)
    )
    receipt["readiness_before_process_trace"] = ready
    if recorder is not None:
        receipt["api"] = {name: dict(recorder.rows[name]) for name in _API_NAMES}
    callbacks = None
    retained = None
    if type(report) is dict and type(report.get("limits")) is dict:
        callbacks = _count(report["limits"].get("callbacks"), 65535)
        retained = _count(report["limits"].get("retained_records"), 65535)
    receipt["callbacks"] = callbacks
    receipt["retained_records"] = retained
    receipt["callback_evidence"] = type(callbacks) is int and callbacks > 0
    receipt["loss"] = _loss_from(report)
    receipt["diagnostics"] = {
        "parser_failed": _diagnostic_count(report, "parser_failed"),
        "record_conversion_failed": _diagnostic_count(report, "record_conversion_failed"),
        "callbacks_exceeded": _diagnostic_count(report, "callbacks_exceeded"),
        "retained_records_exceeded": _diagnostic_count(report, "retained_records_exceeded"),
        "gaps": _gap_names(report),
    }
    root_pid = None
    root_creation = None
    if type(snapshot) is dict:
        root_pid = snapshot.get("_root_pid")
        root_creation = snapshot.get("_root_creation")
    observed = None if recorder is None else recorder.candidates
    complete = True if recorder is None else recorder.candidates_complete
    receipt["sequence"] = project_sequence(
        report,
        root_pid if type(root_pid) is int else None,
        root_creation if type(root_creation) is int else None,
        observed,
        events_complete=complete,
    )
    receipt["counter_reconciliation"] = _counter_view(report)
    samples = census if type(census) is dict else {}
    bound = receipt["sequence"]["bound"] is True
    receipt["measured_job"] = _measured_job(
        report,
        snapshot,
        measured_drain,
        measured_close,
        measured_failure,
        {
            "census_before_creation": samples.get("before_creation"),
            "census_after_create_before_resume": samples.get("after_create_before_resume"),
            "census_after_drain": samples.get("after_drain"),
            "candidate_children": _descendant_count(report) if bound else None,
            "ledger_count": _ledger_count(job),
            "identities_missing": None
            if type(snapshot) is not dict
            else snapshot.get("identities_missing"),
        },
    )
    receipt["preserved"] = _preserved(report)
    receipt["etw_cleanup"] = _etw_cleanup(report, deadline=False)
    receipt["unsupported"] = failure if failure in _UNSUPPORTED else None
    if failure == "access_denied":
        receipt["unsupported"] = "access_denied"
    return _seal(receipt)


class _JobCensusAdapter:
    """Read TotalProcesses around the job's existing calls.

    The first sample is taken on entry to CreateProcess. The second is taken
    on entry to the existing resume, which is after CreateProcess has returned.
    The third is taken when the existing drain wait returns. This does not
    add a wait, poll, or resume, and it does not name a process.
    """

    def __init__(self, job):
        self._job = job
        self.census = {
            "before_creation": None,
            "after_create_before_resume": None,
            "after_drain": None,
        }

    def __getattr__(self, name):
        return getattr(self._job, name)

    def _total_processes(self):
        api = getattr(self._job, "_api", None)
        handle = getattr(self._job, "job", None)
        accounting = getattr(api, "accounting", None)
        if accounting is None or not handle:
            return None
        try:
            info = accounting(handle)
        except Exception:
            return None
        if type(info) is not dict:
            return None
        return info.get("total_processes")

    def _install(self):
        api = getattr(self._job, "_api", None)
        kernel = getattr(api, "kernel", None) if api is not None else None
        if kernel is None:
            return None
        create = getattr(kernel, "CreateProcessW", None)
        resume = getattr(kernel, "ResumeThread", None)
        if not callable(create) or not callable(resume):
            return None

        def create_process(*args, **kwargs):
            self.census["before_creation"] = self._total_processes()
            return create(*args, **kwargs)

        def resume_thread(*args, **kwargs):
            self.census["after_create_before_resume"] = self._total_processes()
            return resume(*args, **kwargs)

        kernel.CreateProcessW = create_process
        kernel.ResumeThread = resume_thread
        return kernel, create, resume

    def spawn(self):
        installed = self._install()
        try:
            return self._job.spawn()
        finally:
            if installed is not None:
                kernel, create, resume = installed
                kernel.CreateProcessW = create
                kernel.ResumeThread = resume

    def note_after_drain(self):
        self.census["after_drain"] = self._total_processes()


def run_worker(
    *,
    api_factory,
    job_factory,
    phase: PhaseLog,
    marker: Path | None,
    identity: dict,
    executable: str,
    requested_source: str | None,
    head: str | None,
    provider_hash: str | None,
    attempt: str,
    run_id: str,
    dispatch_authorized: bool,
) -> dict:
    """Start ETW, then one measured root. Caller closes nothing else."""
    phase.mark("worker_entered")
    receipt = _context_receipt(
        requested_source=requested_source,
        head=head,
        provider_hash=provider_hash,
        attempt=attempt,
        run_id=run_id,
        identity=identity,
        dispatch_authorized=dispatch_authorized,
    )
    if dispatch_authorized is not True:
        receipt["unsupported"] = "dispatch_not_authorized"
        receipt["phases"] = _phases(phase.names)
        receipt["last_phase"] = receipt["phases"][-1]
        return _seal(receipt)
    if not receipt["source_matches"] or not receipt["provider_sha256_matches"]:
        receipt["unsupported"] = "wrong_source"
        receipt["phases"] = _phases(phase.names)
        receipt["last_phase"] = receipt["phases"][-1]
        return _seal(receipt)
    if not receipt["architecture_supported"]:
        receipt["unsupported"] = "wrong_architecture"
        receipt["phases"] = _phases(phase.names)
        receipt["last_phase"] = receipt["phases"][-1]
        return _seal(receipt)
    if not interpreter_supported(receipt["identity"]):
        receipt["unsupported"] = "interpreter_not_baseline"
        receipt["phases"] = _phases(phase.names)
        receipt["last_phase"] = receipt["phases"][-1]
        return _seal(receipt)

    observer = None
    recorder = None
    job = None
    census = None
    report = None
    snapshot = None
    launched = False
    ready = None
    failure = None
    measured_drain = None
    measured_close = None
    measured_failure = None
    root_pid = None
    root_creation = None
    starts_before = etw.native_session_starts
    try:
        phase.mark("before_etw_construct")
        api = api_factory()
        recorder = OutcomeRecorder(api)
        observer = EtwLifetimeObserver(
            recorder,
            ready_seconds=READY_SECONDS,
            drain_seconds=OBSERVER_DRAIN_SECONDS,
        )
        if observer.request != session_request():
            failure = "session_not_started"
            phase.mark("session_refused")
            report = observer.finish(None)
        else:
            phase.mark("before_session_start")
            started = observer.start_before_root() is True
            ready = started
            if not started:
                failure = _start_failure(recorder)
                phase.mark("session_refused")
                report = observer.finish(None)
            else:
                phase.mark("before_fixture_spawn")
                try:
                    job = job_factory(
                        fixture_argv(executable, "" if marker is None else str(marker))
                    )
                    job = _JobCensusAdapter(job)
                    census = job.census
                    job.spawn()
                    launched = True
                except OwnedLaunchUnsupported:
                    failure = "wrong_architecture"
                    phase.mark("fixture_spawn_failed")
                except OwnedLaunchError as error:
                    failure = (
                        "nested_job_denied"
                        if _nested_denial(error.code)
                        else "fixture_spawn_failed"
                    )
                    phase.mark("fixture_spawn_failed")
                except Exception:
                    failure = "worker_exception"
                    phase.mark("fixture_spawn_failed")
                if launched:
                    root_pid = getattr(job, "root_pid", None)
                    root_creation = getattr(job, "root_creation", None)
                    if type(root_pid) is int and type(root_creation) is int:
                        observer.bind_root(root_pid, root_creation)
                    else:
                        observer.note_gap("launch_identity_missing")
                    phase.mark("before_job_drain")
                    try:
                        measured_drain = job.wait_until_drained(OBSERVER_DRAIN_SECONDS) is True
                    except Exception:
                        measured_drain = None
                    if measured_drain is not None:
                        job.note_after_drain()
                    if measured_drain is False:
                        observer.note_gap("job_active_processes")
                    phase.mark("before_snapshot")
                    snapshot = job.snapshot()
                    if type(snapshot) is not dict:
                        snapshot = {}
                    phase.mark("before_observer_finish")
                    report = observer.finish(dict(snapshot))
                elif observer is not None and report is None:
                    phase.mark("before_observer_finish")
                    report = observer.finish(None)
    except Exception:
        failure = "worker_exception"
        if observer is not None and report is None:
            try:
                phase.mark("before_observer_finish")
                report = observer.finish(None)
            except Exception:
                report = None
    finally:
        if observer is not None:
            try:
                observer.close()
            except Exception:
                if failure is None:
                    failure = "worker_exception"
            if recorder is not None:
                try:
                    recorder.retain_recovery(observer.recovery_state())
                except Exception:
                    if failure is None:
                        failure = "worker_exception"
        if job is not None:
            phase.mark("before_measured_job_close")
            try:
                measured_close, measured_failure = _close_observation(job.close())
            except Exception:
                measured_close = None
                measured_failure = None
        phase.mark("worker_finished")
    if measured_drain is False:
        measured_failure = "drain_timeout"
    elif measured_close is not False:
        measured_failure = None
    if type(snapshot) is dict:
        snapshot = dict(snapshot)
        snapshot["_root_pid"] = root_pid
        snapshot["_root_creation"] = root_creation
    starts = etw.native_session_starts - starts_before
    if starts < 0:
        starts = None
    return _apply_report(
        receipt,
        report,
        recorder,
        snapshot,
        launched=launched,
        marker=_marker_written(marker) if launched else None,
        starts=starts,
        ready=ready,
        measured_drain=measured_drain,
        measured_close=measured_close,
        measured_failure=measured_failure,
        failure=failure,
        phases=phase.names,
        job=job,
        census=census,
    )


def _start_failure(recorder: OutcomeRecorder) -> str:
    code = recorder.rows["start_trace"]["code"]
    if code == "access_denied":
        return "access_denied"
    if code == "already_exists":
        return "session_collision"
    if (
        recorder.rows["open_trace"]["attempted"] is True
        and recorder.rows["open_trace"]["ok"] is not True
    ):
        return "open_trace_failed"
    return "session_not_started"


def run_supervisor(
    *,
    requested_source: str | None,
    head: str | None,
    provider_hash: str | None,
    identity: dict,
    attempt: str,
    run_id: str,
    dispatch_authorized: bool,
    spawn_worker,
    read_worker_phase,
    read_worker_result,
    clock=time.monotonic,
) -> dict:
    """Own one worker for the budget sampled before spawn.

    A late return is not adopted and does not open a new window. A wait that
    never returns is not proved cleaned up by this deadline or by runner stop.
    """
    phase = PhaseLog()
    phase.mark("supervisor_checked")
    receipt = _context_receipt(
        requested_source=requested_source,
        head=head,
        provider_hash=provider_hash,
        attempt=attempt,
        run_id=run_id,
        identity=identity,
        dispatch_authorized=dispatch_authorized,
    )
    receipt["native_session_starts"] = 0
    receipt["session_start_calls"] = 0
    refusal = _preflight(receipt)
    if refusal is not None:
        receipt["unsupported"] = refusal
        receipt["phases"] = _phases(phase.names)
        receipt["last_phase"] = receipt["phases"][-1]
        return _seal(receipt)

    phase.mark("before_worker_spawn")
    started = clock()
    job = None
    try:
        job = spawn_worker()
    except OwnedLaunchUnsupported:
        receipt["unsupported"] = "wrong_architecture"
    except OwnedLaunchError as error:
        receipt["unsupported"] = (
            "nested_job_denied" if _nested_denial(error.code) else "worker_not_owned"
        )
    except Exception:
        receipt["unsupported"] = "worker_not_owned"
    if job is None:
        receipt["phases"] = _phases(phase.names)
        receipt["last_phase"] = receipt["phases"][-1]
        return _seal(receipt)

    try:
        remaining = _budget_remaining(started, clock())
        in_budget = False
        if remaining is not None and remaining > 0:
            # The allowance is not an interrupt. A stuck wait never reaches here.
            in_budget = job.wait_until_drained(remaining) is True
            if in_budget:
                left = _budget_remaining(started, clock())
                in_budget = left is not None and left > 0
        if not in_budget:
            phase.mark("supervisor_deadline")
            phase.mark("before_supervisor_terminate")
            terminated_ok, terminate_failure = _observed_terminate(job)
            phase.mark("before_supervisor_drain")
            drain_ok = _observed_drain(job, SUPERVISOR_DRAIN_SECONDS)
            try:
                worker_phase = read_worker_phase()
            except Exception:
                worker_phase = "unknown"
            receipt = _deadline_receipt(receipt, phase.names, worker_phase)
            receipt["supervisor_job"] = _supervisor_job(
                cleanup_ok=None,
                cleanup_failure=terminate_failure,
                terminated=terminated_ok is True,
                drain_ok=drain_ok,
                close_ok=None,
            )
            receipt["worker"]["deadline_exceeded"] = True
            return _close_supervisor(receipt, job, phase)
        try:
            result = read_worker_result()
        except Exception:
            result = None
        observed_drain = _supervisor_job(
            cleanup_ok=None,
            cleanup_failure=None,
            terminated=False,
            drain_ok=True,
            close_ok=None,
        )
        if not receipt_schema_ok(result):
            receipt["unsupported"] = "worker_receipt_invalid"
            receipt["supervisor_job"] = observed_drain
            receipt["phases"] = _phases(phase.names)
            receipt["last_phase"] = receipt["phases"][-1]
            return _close_supervisor(receipt, job, phase)
        merged = dict(result)
        merged["phases"] = _phases(
            ["supervisor_checked", "before_worker_spawn", *result["phases"], "supervisor_finished"]
        )
        merged["last_phase"] = "supervisor_finished"
        merged["worker"] = dict(result["worker"])
        merged["worker"]["deadline_exceeded"] = False
        merged["worker"]["report_adopted"] = True
        merged["run_id"] = receipt["run_id"]
        merged["requested_source"] = receipt["requested_source"]
        merged["head"] = receipt["head"]
        merged["source_matches"] = receipt["source_matches"]
        merged["provider_sha256"] = receipt["provider_sha256"]
        merged["provider_sha256_matches"] = receipt["provider_sha256_matches"]
        merged["dispatch_authorized"] = True
        merged["attempt"] = receipt["attempt"]
        merged["identity"] = receipt["identity"]
        merged["architecture_supported"] = receipt["architecture_supported"]
        merged["supervisor_job"] = observed_drain
        return _close_supervisor(merged, job, phase)
    except Exception:
        phase.mark("before_supervisor_terminate")
        terminated_ok, terminate_failure = _observed_terminate(job)
        phase.mark("before_supervisor_drain")
        drain_ok = _observed_drain(job, SUPERVISOR_DRAIN_SECONDS)
        receipt = _deadline_receipt(receipt, phase.names, "unknown")
        receipt["unsupported"] = "worker_exception"
        receipt["etw_cleanup"]["reason"] = "unverified"
        receipt["worker"]["deadline_exceeded"] = False
        receipt["supervisor_job"] = _supervisor_job(
            cleanup_ok=None,
            cleanup_failure=terminate_failure,
            terminated=terminated_ok is True,
            drain_ok=drain_ok,
            close_ok=None,
        )
        return _close_supervisor(receipt, job, phase)


def _preflight(receipt: dict) -> str | None:
    if receipt["dispatch_authorized"] is not True:
        return "dispatch_not_authorized"
    if not receipt["source_matches"] or not receipt["provider_sha256_matches"]:
        return "wrong_source"
    if not receipt["architecture_supported"]:
        return "wrong_architecture"
    if not interpreter_supported(receipt["identity"]):
        return "interpreter_not_baseline"
    return None


def _deadline_receipt(receipt: dict, supervisor_phases: list[str], worker_phase: str) -> dict:
    phases = list(supervisor_phases)
    if worker_phase in PHASES and worker_phase != "unknown":
        phases.insert(2, worker_phase)
    receipt["phases"] = _phases(phases)
    receipt["last_phase"] = receipt["phases"][-1]
    receipt["native_session_starts"] = None
    receipt["session_start_calls"] = None
    receipt["etw_cleanup"] = _etw_cleanup(None, deadline=True)
    receipt["unsupported"] = "worker_deadline"
    receipt["fixture_launched"] = None
    receipt["worker"]["report_adopted"] = False
    for name in _API_NAMES:
        receipt["api"][name] = {
            "attempted": None,
            "ok": None,
            "code": "unknown",
            "pending": None,
        }
    return receipt


def _close_supervisor(receipt: dict, job, phase: PhaseLog) -> dict:
    phase.mark("before_supervisor_close")
    close_ok = None
    close_failure = None
    try:
        close_ok, close_failure = _close_observation(job.close())
    except Exception:
        close_ok = None
        close_failure = None
    phase.mark("supervisor_finished")
    current = dict(receipt.get("supervisor_job") or {})
    cleanup_ok, cleanup_failure = _job_cleanup(
        drain_ok=current.get("drain_ok"),
        close_ok=close_ok,
        prior_failure=current.get("cleanup_failure"),
        close_failure=close_failure,
    )
    receipt["supervisor_job"] = _supervisor_job(
        cleanup_ok=cleanup_ok,
        cleanup_failure=cleanup_failure,
        terminated=current.get("terminated") is True,
        drain_ok=current.get("drain_ok"),
        close_ok=close_ok,
    )
    names = list(receipt.get("phases") or [])
    if "before_supervisor_close" not in names:
        if names and names[-1] == "supervisor_finished":
            names.insert(-1, "before_supervisor_close")
        else:
            names.append("before_supervisor_close")
    if "supervisor_finished" not in names:
        names.append("supervisor_finished")
    receipt["phases"] = _phases(names)
    receipt["last_phase"] = "supervisor_finished"
    return _seal(receipt)


def write_receipt(path: Path, receipt: dict) -> None:
    if not receipt_schema_ok(receipt):
        receipt = _static_receipt("privacy_rejected")
    text = json.dumps(receipt, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def parse_args(argv: list[str]) -> dict | None:
    options = {
        "worker": False,
        "source": "",
        "attempt": "1",
        "receipt": "",
        "phase": "",
        "result": "",
        "marker": "",
    }
    index = 0
    flags = {
        "--source": "source",
        "--attempt": "attempt",
        "--receipt": "receipt",
        "--phase": "phase",
        "--result": "result",
        "--marker": "marker",
    }
    while index < len(argv):
        item = argv[index]
        if item == "--worker":
            options["worker"] = True
            index += 1
            continue
        key = flags.get(item)
        if key is None or index + 1 >= len(argv):
            return None
        options[key] = argv[index + 1]
        index += 2
    return options


def _run_id(environ: dict) -> str:
    value = environ.get("GITHUB_RUN_ID", "")
    if _RUN.fullmatch(value or ""):
        return value
    return "unknown"


def _dispatch_ok(environ: dict) -> bool:
    return environ.get("MNEMION_ETW_LIFECYCLE_DISPATCH") == "1"


def production_api():
    return WinEtwApi()


def production_measured_job(argv: list[str]):
    return WindowsJobBackend(argv, cwd=None, env=None)


def production_supervisor_job(argv: list[str]):
    job = WindowsJobBackend(argv, cwd=None, env=None)
    try:
        job.spawn()
    except Exception:
        try:
            job.close()
        except Exception:
            pass
        raise
    return job


def main(
    argv: list[str] | None = None,
    *,
    environ: dict | None = None,
    spawn_worker=None,
    identity: dict | None = None,
    head: str | None = None,
    provider_hash: str | None = None,
    clock=time.monotonic,
    run_id: str | None = None,
) -> int:
    env = os.environ if environ is None else environ
    options = parse_args(list(sys.argv[1:] if argv is None else argv))
    if options is None:
        return 2
    if options["worker"]:
        return _worker_entry(options, env, identity, head, provider_hash, run_id)
    receipt_path = options["receipt"]
    if not receipt_path:
        return 2
    path = Path(receipt_path)
    try:
        receipt = _supervise(
            options,
            env,
            spawn_worker=spawn_worker,
            identity=identity,
            head=head,
            provider_hash=provider_hash,
            clock=clock,
            run_id=run_id,
        )
        code = 0 if etw_lifecycle_receipt_qualifies(receipt) else 1
    except Exception:
        receipt = _static_receipt("worker_exception")
        code = 1
    write_receipt(path, receipt)
    return code


def _supervise(
    options,
    env,
    *,
    spawn_worker,
    identity,
    head,
    provider_hash,
    clock,
    run_id,
) -> dict:
    import tempfile

    checked_head = git_head() if head is None else head
    digest = provider_sha256() if provider_hash is None else provider_hash
    current = host_identity(environ=env) if identity is None else identity
    label = run_id if run_id is not None else _run_id(env)
    directory = tempfile.TemporaryDirectory(prefix="mnemion-etw-lifecycle-")
    try:
        root = Path(directory.name)
        phase_path = root / "phase.json"
        result_path = root / "worker.json"
        marker_path = root / "marker"
        command = worker_command(
            sys.executable,
            options["source"],
            options["attempt"],
            str(phase_path),
            str(result_path),
            str(marker_path),
        )

        def default_spawn():
            return production_supervisor_job(command)

        def read_result():
            try:
                raw = result_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                return None
            if len(raw) > 65536:
                return None
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None

        return run_supervisor(
            requested_source=options["source"],
            head=checked_head,
            provider_hash=digest,
            identity=current,
            attempt=options["attempt"],
            run_id=label,
            dispatch_authorized=_dispatch_ok(env),
            spawn_worker=default_spawn if spawn_worker is None else spawn_worker,
            read_worker_phase=lambda: read_phase(phase_path),
            read_worker_result=read_result,
            clock=clock,
        )
    finally:
        directory.cleanup()


def _worker_entry(options, env, identity, head, provider_hash, run_id) -> int:
    result_path = options["result"]
    if not result_path:
        return 2
    phase = PhaseLog(Path(options["phase"]) if options["phase"] else None)
    marker = Path(options["marker"]) if options["marker"] else None
    current = host_identity(environ=env) if identity is None else identity
    try:
        receipt = run_worker(
            api_factory=production_api,
            job_factory=production_measured_job,
            phase=phase,
            marker=marker,
            identity=current,
            executable=sys.executable,
            requested_source=options["source"],
            head=git_head() if head is None else head,
            provider_hash=provider_sha256() if provider_hash is None else provider_hash,
            attempt=options["attempt"],
            run_id=_run_id(env) if run_id is None else run_id,
            dispatch_authorized=_dispatch_ok(env),
        )
    except Exception:
        receipt = _static_receipt("worker_exception")
    write_receipt(Path(result_path), receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
