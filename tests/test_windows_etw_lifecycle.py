"""Offline checks for the ETW lifecycle driver. No ETW API, process, or tracer."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from deploy.owned_launch_accounting import OwnedLaunchError
from deploy.owned_launch_self_check import lifecycle_receipt_qualifies
from deploy.owned_launch_windows_etw import (
    EVENT_HEADER_FLAG_64_BIT_HEADER,
    OPCODE_END,
    OPCODE_PERFCTR,
    OPCODE_PERFCTR_RUNDOWN,
    OPCODE_START,
    PROCESS_PROVIDER_GUID,
    host_offset,
    session_request,
)
from deploy.windows_etw_lifecycle import (
    PROVIDER_SHA256,
    PhaseLog,
    base_receipt,
    etw_lifecycle_receipt_qualifies,
    main,
    read_phase,
    receipt_schema_ok,
    run_supervisor,
    run_worker,
    stored_qualification_matches,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "a" * 40
OTHER = "b" * 40
KEY = 8877665544
NOISE_PID = 424242
NOISE_KEY = 246813579
SECRET = b"MNEMION_ETW_SECRET_PATH"
MARKER_TOKEN = "MNEMION_PRIVATE_MARKER_PATH"
EXCEPTION_TOKEN = "MNEMION_RAW_EXCEPTION_TEXT"
ACCOUNTING_SHA256 = "324276fd8eb1520fe0a78d9ba8a2ae9228bfcc9918fa3142027c7ee012e7278a"


def _u32(value: int) -> bytes:
    return int(value).to_bytes(4, "little", signed=False)


def _i32(value: int) -> bytes:
    return int(value).to_bytes(4, "little", signed=True)


def _usize(value: int, width: int = 8) -> bytes:
    return int(value).to_bytes(width, "little", signed=False)


def _lifecycle_payload(pid: int, parent: int, key: int, exit_status: int) -> bytes:
    width = 8
    buffer = bytearray(width + 16)
    buffer[0:width] = _usize(key, width)
    start = host_offset(4, 1, width)
    buffer[start : start + 4] = _u32(pid)
    parent_at = host_offset(8, 1, width)
    buffer[parent_at : parent_at + 4] = _u32(parent)
    session = host_offset(12, 1, width)
    buffer[session : session + 4] = _u32(1)
    exit_at = host_offset(16, 1, width)
    buffer[exit_at : exit_at + 4] = _i32(exit_status)
    return bytes(buffer) + SECRET


def _counter_payload(pid: int, peak: int) -> bytes:
    width = 8
    dwords = b"".join(_u32(part) for part in (pid, 7, 8, 0))
    values = [0x1111, peak, 0x2222, 0x3333]
    values.extend(0x4000 + index for index in range(7))
    return dwords + b"".join(_usize(value, width) for value in values)


def _record(opcode: int, payload: bytes, timestamp: int, *, version: int = 2) -> dict:
    return {
        "provider": PROCESS_PROVIDER_GUID,
        "version": version,
        "opcode": opcode,
        "flags": EVENT_HEADER_FLAG_64_BIT_HEADER,
        "timestamp": timestamp,
        "processor_index": 0,
        "header_pid": 0xFFFFFFFF,
        "payload": payload,
        "process_start_key_present": False,
    }


def _life(
    opcode: int, pid: int, parent: int, key: int, timestamp: int, *, exit_status: int = 0
) -> dict:
    return _record(opcode, _lifecycle_payload(pid, parent, key, exit_status), timestamp)


def _counter(pid: int, peak: int, timestamp: int, *, opcode: int = OPCODE_PERFCTR) -> dict:
    return _record(opcode, _counter_payload(pid, peak), timestamp)


def _generation(pid: int, parent: int, key: int, start: int, end: int, peak: int) -> list[dict]:
    return [
        _life(OPCODE_START, pid, parent, key, start),
        _life(OPCODE_END, pid, parent, key, end, exit_status=0),
        _counter(pid, peak, start + 50),
    ]


def _identity(**overrides) -> dict:
    identity = {
        "pe_machine": 34404,
        "platform_machine": "AMD64",
        "platform": "win32",
        "python_version": "3.13.17",
        "python_implementation": "CPython",
        "pointer_width": 8,
        "runner_os": "Windows",
    }
    identity.update(overrides)
    return identity


class SyncApi:
    def __init__(
        self, records=None, *, start_code="ok", open_ok=True, close_mode="ok", stop_ok=True
    ):
        self.records = list(records or [])
        self.start_code = start_code
        self.open_ok = open_ok
        self.close_mode = close_mode
        self.stop_ok = stop_ok
        self.request = None
        self.ready = False
        self.stops = []
        self.opens = []
        self.closes = []
        self.private_owner = None
        self.on_event = None
        self.loss = {"events_lost": 0, "log_buffers_lost": 0, "real_time_buffers_lost": 0}

    def start_session(self, request):
        self.request = dict(request)
        if self.start_code != "ok":
            return {"ok": False, "code": self.start_code, "handle": None}
        return {"ok": True, "code": "ok", "handle": 101}

    def open_trace(self, name, on_event):
        self.opens.append(name)
        self.on_event = on_event
        if not self.open_ok:
            return {"ok": False, "code": "open_trace_failed", "handle": None}
        return {"ok": True, "code": "ok", "handle": 202}

    def process_trace(self, _handle, on_ready):
        self.ready = True
        on_ready()
        for record in self.records:
            self.on_event(record)
        return {"ok": True, "code": "ok"}

    def stop_session(self, handle):
        self.stops.append(handle)
        if not self.stop_ok:
            return {"ok": False, "code": "stop_failed", "loss": {}}
        return {"ok": True, "code": "ok", "loss": dict(self.loss)}

    def close_trace(self, handle):
        self.closes.append(handle)
        if self.close_mode == "pending":
            return {"ok": False, "code": "close_pending", "pending": True}
        if self.close_mode == "fail":
            return {"ok": False, "code": "close_failed", "pending": False}
        return {"ok": True, "code": "ok", "pending": False}

    def close_session(self, _handle):
        return {"ok": True, "code": "ok"}

    def release_callbacks(self, _handle=None):
        return True

    def retain_recovery(self, state):
        self.private_owner = state


class SyncJob:
    def __init__(
        self,
        snapshot,
        *,
        pid=10,
        creation=5000,
        fail=None,
        close_result=(True, None),
        marker=None,
        drain_result=True,
    ):
        self._snapshot = snapshot
        self._pid = pid
        self._creation = creation
        self.fail = fail
        self.close_result = close_result
        self.marker = marker
        self.drain_result = drain_result
        self.root_pid = None
        self.root_creation = None
        self.spawn_calls = 0
        self.argv = None
        self.ready = None

    def spawn(self):
        self.spawn_calls += 1
        if self.fail is not None:
            raise self.fail
        self.root_pid = self._pid
        self.root_creation = self._creation
        if self.marker is not None and self.argv is not None:
            Path(self.argv[-1]).write_bytes(b"1")

    def wait_until_drained(self, _seconds):
        if isinstance(self.drain_result, BaseException):
            raise self.drain_result
        return self.drain_result

    def snapshot(self):
        if isinstance(self._snapshot, Exception):
            raise self._snapshot
        return self._snapshot

    def close(self):
        return self.close_result


def _snapshot(total=1, active=0, observer=False) -> dict:
    return {
        "observer_in_measured_group": observer,
        "cpu_microseconds": 10,
        "kernel": {"total_processes": total, "active_processes": active},
    }


def _run(
    records=None, *, api=None, job=None, marker=None, identity=None, source=SOURCE, head=SOURCE
):
    api = api or SyncApi(records or [])
    job = job or SyncJob(_snapshot(), marker=marker)
    calls = {"factory": 0}

    def api_factory():
        return api

    def job_factory(argv):
        calls["factory"] += 1
        job.argv = argv
        job.ready = api.ready
        return job

    phase = PhaseLog()
    receipt = run_worker(
        api_factory=api_factory,
        job_factory=job_factory,
        phase=phase,
        marker=marker,
        identity=identity or _identity(),
        executable="python",
        requested_source=source,
        head=head,
        provider_hash=PROVIDER_SHA256,
        attempt="1",
        run_id="99",
        dispatch_authorized=True,
    )
    return receipt, api, job, phase, calls


def _assert_schema(receipt) -> None:
    assert receipt_schema_ok(receipt)
    assert stored_qualification_matches(receipt)


def _evidence() -> dict:
    """Schema-valid evidence. It does not come from a native trace."""
    receipt = base_receipt()
    receipt["dispatch_authorized"] = True
    receipt["requested_source"] = SOURCE
    receipt["head"] = SOURCE
    receipt["source_matches"] = True
    receipt["provider_sha256"] = PROVIDER_SHA256
    receipt["provider_sha256_matches"] = True
    receipt["attempt"] = "1"
    receipt["run_id"] = "99"
    receipt["identity"] = _identity()
    receipt["architecture_supported"] = True
    receipt["fixture_launched"] = True
    receipt["fixture_completion_marker"] = True
    receipt["native_session_starts"] = 1
    receipt["session_start_calls"] = 1
    receipt["readiness_before_process_trace"] = True
    receipt["callback_evidence"] = True
    receipt["callbacks"] = 4
    receipt["retained_records"] = 3
    for name in receipt["api"]:
        receipt["api"][name] = {"attempted": True, "ok": True, "code": "ok", "pending": None}
    receipt["api"]["close_trace"]["pending"] = False
    receipt["sequence"] = {
        "bound": True,
        "binding": "exact_creation",
        "start_end_gate": "passed",
        "start_end_key_equal": True,
        "opcodes": [1, 2, 32],
        "pointer_width": 8,
        "event_version": 2,
        "start_matches_creation": True,
        "end_present": True,
        "timestamps_equal": False,
        "opcode32_inside_paired_lifetime": True,
        "opcode33_rundown_ignored": 0,
        "process_start_key_used": False,
    }
    receipt["counter_reconciliation"] = {
        "passed": True,
        "births": 1,
        "exits": 1,
        "terminal_counters": 1,
        "status": "reconciled",
    }
    receipt["diagnostics"] = {
        "parser_failed": 0,
        "record_conversion_failed": 0,
        "callbacks_exceeded": 0,
        "retained_records_exceeded": 0,
        "gaps": [],
    }
    receipt["loss"] = {"events_lost": 0, "log_buffers_lost": 0, "real_time_buffers_lost": 0}
    receipt["measured_job"] = {
        "census_total": 1,
        "census_active": 0,
        "census_expected_total": 1,
        "census_expected_active": 0,
        "census_matches_expected": True,
        "observer_in_measured_job": False,
        "drain_ok": True,
        "close_ok": True,
        "cleanup_ok": True,
        "cleanup_failure": None,
    }
    receipt["etw_cleanup"] = {
        "verified": True,
        "reason": None,
        "session_released": True,
        "callbacks_released": True,
        "consumer_finished": True,
        "close_pending": False,
        "close_failed": False,
        "stop_ok": True,
    }
    receipt["preserved"] = {
        "qualification": "unqualified",
        "native_unit_corroboration": "unrun",
        "resource_acceptance": False,
        "budget_compared": False,
        "production_accounting_switched": False,
        "telemetry_enabled": False,
    }
    receipt["phases"] = [
        "worker_entered",
        "before_etw_construct",
        "before_session_start",
        "before_fixture_spawn",
        "before_job_drain",
        "before_snapshot",
        "before_observer_finish",
        "before_measured_job_close",
        "worker_finished",
    ]
    receipt["last_phase"] = "worker_finished"
    receipt["unsupported"] = None
    receipt["owned_event_qualified"] = False
    assert receipt_schema_ok(receipt)
    assert etw_lifecycle_receipt_qualifies(receipt) is False
    return receipt


def _supervisor(result=None, **overrides):
    calls = []

    class Job:
        def wait_until_drained(self, seconds):
            calls.append(("wait", seconds))
            script = overrides.get("wait_results")
            if script is not None:
                outcome = script.pop(0)
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome
            return overrides.get("drained", True)

        def terminate(self):
            calls.append(("terminate",))
            result = overrides.get("terminate_result", (True, None))
            if isinstance(result, BaseException):
                raise result
            return result

        def close(self):
            calls.append(("close",))
            return overrides.get("close", (True, None))

    def spawn():
        calls.append(("spawn",))
        error = overrides.get("spawn_error")
        if error is not None:
            raise error
        return Job()

    def read_phase():
        calls.append(("phase",))
        return overrides.get("phase", "before_session_start")

    def read_result():
        calls.append(("result",))
        if overrides.get("read_result") is not None:
            return overrides["read_result"]()
        return result

    receipt = run_supervisor(
        requested_source=overrides.get("source", SOURCE),
        head=overrides.get("head", SOURCE),
        provider_hash=overrides.get("digest", PROVIDER_SHA256),
        identity=overrides.get("identity", _identity()),
        attempt="1",
        run_id="99",
        dispatch_authorized=overrides.get("dispatch", True),
        spawn_worker=spawn,
        read_worker_phase=read_phase,
        read_worker_result=read_result,
        clock=overrides.get("clock", lambda: 50.0),
    )
    return receipt, calls


def test_wrong_source_and_provider_hash_do_not_spawn():
    wrong_head, calls = _supervisor(head=OTHER)
    _assert_schema(wrong_head)
    assert wrong_head["unsupported"] == "wrong_source"
    assert wrong_head["source_matches"] is False
    assert calls == []
    assert etw_lifecycle_receipt_qualifies(wrong_head) is False
    wrong_hash, hash_calls = _supervisor(digest="d" * 64)
    _assert_schema(wrong_hash)
    assert wrong_hash["unsupported"] == "wrong_source"
    assert wrong_hash["source_matches"] is True
    assert wrong_hash["provider_sha256_matches"] is False
    assert hash_calls == []


def test_wrong_architecture_is_recorded_and_does_not_spawn():
    receipt, calls = _supervisor(identity=_identity(pe_machine=43620, platform_machine="ARM64"))
    _assert_schema(receipt)
    assert receipt["unsupported"] == "wrong_architecture"
    assert receipt["architecture_supported"] is False
    assert receipt["identity"]["pe_machine"] == 43620
    assert receipt["identity"]["platform_machine"] == "ARM64"
    assert receipt["fixture_launched"] is False
    assert calls == []
    assert etw_lifecycle_receipt_qualifies(receipt) is False


def test_start_refusal_does_not_launch_the_fixture():
    for code, expected in (
        ("already_exists", "session_collision"),
        ("access_denied", "access_denied"),
    ):
        receipt, api, job, _phase, calls = _run(api=SyncApi(start_code=code))
        _assert_schema(receipt)
        assert calls["factory"] == 0
        assert job.spawn_calls == 0
        assert api.opens == []
        assert api.stops == []
        assert receipt["fixture_launched"] is False
        assert receipt["unsupported"] == expected
        assert receipt["native_session_starts"] == 0
        assert etw_lifecycle_receipt_qualifies(receipt) is False
    opened, open_api, open_job, _phase, open_calls = _run(api=SyncApi(open_ok=False))
    _assert_schema(opened)
    assert open_calls["factory"] == 0
    assert open_job.spawn_calls == 0
    assert open_api.stops == [101]
    assert opened["unsupported"] == "open_trace_failed"
    assert opened["fixture_launched"] is False


def test_missing_callbacks_are_not_readiness_evidence():
    receipt, api, job, phase, _calls = _run([])
    _assert_schema(receipt)
    assert job.spawn_calls == 1
    assert job.ready is True
    assert api.request == session_request()
    assert receipt["readiness_before_process_trace"] is True
    assert receipt["callback_evidence"] is False
    assert receipt["callbacks"] == 0
    assert receipt["sequence"]["binding"] == "unbound"
    assert receipt["sequence"]["opcodes"] == []
    assert "root_unobserved" in receipt["diagnostics"]["gaps"]
    assert phase.names.index("before_session_start") < phase.names.index("before_fixture_spawn")
    assert etw_lifecycle_receipt_qualifies(receipt) is False


def test_unbound_events_stay_unbound_without_the_kernel_key():
    records = _generation(10, 1, KEY, 1111, 3000, 80)
    receipt, _api, _job, _phase, _calls = _run(records)
    _assert_schema(receipt)
    text = json.dumps(receipt)
    assert receipt["callback_evidence"] is True
    assert receipt["sequence"]["bound"] is False
    assert receipt["sequence"]["binding"] == "unbound"
    assert receipt["sequence"]["start_end_gate"] == "unpassed"
    assert receipt["sequence"]["opcodes"] == [1, 2, 32]
    assert receipt["sequence"]["event_version"] == 2
    assert receipt["sequence"]["pointer_width"] == 8
    assert receipt["sequence"]["start_matches_creation"] is False
    assert receipt["sequence"]["end_present"] is True
    assert receipt["sequence"]["timestamps_equal"] is False
    assert receipt["sequence"]["start_end_key_equal"] is True
    assert receipt["sequence"]["opcode32_inside_paired_lifetime"] is True
    assert receipt["counter_reconciliation"]["passed"] is False
    assert "root_binding_unproven" in receipt["diagnostics"]["gaps"]
    assert str(KEY) not in text
    assert SECRET.decode() not in text
    assert '"unique_process_key"' not in text
    assert receipt["privacy"]["unique_process_key_omitted"] is True
    assert receipt["privacy"]["private_owner_omitted"] is True
    assert receipt["privacy"]["payloads_omitted"] is True
    assert receipt["privacy"]["handles_omitted"] is True
    assert receipt["privacy"]["unrelated_rows_omitted"] is True
    assert receipt["privacy"]["command_lines_omitted"] is True
    assert receipt["privacy"]["environment_omitted"] is True
    assert receipt["privacy"]["paths_omitted"] is True
    assert receipt["privacy"]["exception_text_omitted"] is True
    assert receipt["privacy"]["public_safe_disposition"] is False
    assert '"pid"' not in text
    assert etw_lifecycle_receipt_qualifies(receipt) is False


def test_partial_candidate_sequence_stays_unbound():
    receipt, _api, _job, _phase, _calls = _run([_life(OPCODE_START, 10, 1, KEY, 1111)])
    _assert_schema(receipt)
    text = json.dumps(receipt)
    assert receipt["sequence"]["bound"] is False
    assert receipt["sequence"]["binding"] == "unbound"
    assert receipt["sequence"]["opcodes"] == [1]
    assert receipt["sequence"]["event_version"] == 2
    assert receipt["sequence"]["pointer_width"] == 8
    assert receipt["sequence"]["start_matches_creation"] is False
    assert receipt["sequence"]["end_present"] is False
    assert receipt["sequence"]["timestamps_equal"] is None
    assert receipt["sequence"]["start_end_key_equal"] is None
    assert receipt["sequence"]["opcode32_inside_paired_lifetime"] is None
    assert receipt["counter_reconciliation"]["passed"] is False
    assert str(KEY) not in text
    assert SECRET.decode() not in text
    assert '"unique_process_key"' not in text
    assert receipt["privacy"]["unique_process_key_omitted"] is True
    assert receipt["privacy"]["private_owner_omitted"] is True
    assert receipt["privacy"]["payloads_omitted"] is True
    assert receipt["privacy"]["handles_omitted"] is True
    assert receipt["privacy"]["unrelated_rows_omitted"] is True
    assert receipt["privacy"]["command_lines_omitted"] is True
    assert receipt["privacy"]["environment_omitted"] is True
    assert receipt["privacy"]["paths_omitted"] is True
    assert receipt["privacy"]["exception_text_omitted"] is True
    assert receipt["privacy"]["public_safe_disposition"] is False
    assert etw_lifecycle_receipt_qualifies(receipt) is False


def test_mismatched_start_end_keys_leave_the_paired_lifetime_unknown():
    records = [
        _life(OPCODE_START, 10, 1, KEY, 5000),
        _life(OPCODE_END, 10, 1, NOISE_KEY, 5600),
        _counter(10, 80, 5050),
    ]
    receipt, _api, _job, _phase, _calls = _run(records)
    _assert_schema(receipt)
    sequence = receipt["sequence"]
    assert sequence["opcodes"] == [1, 2, 32]
    assert sequence["event_version"] == 2
    assert sequence["pointer_width"] == 8
    assert sequence["start_matches_creation"] is True
    assert sequence["end_present"] is True
    assert sequence["timestamps_equal"] is False
    assert sequence["start_end_key_equal"] is False
    assert sequence["opcode32_inside_paired_lifetime"] is None
    assert sequence["bound"] is False
    assert sequence["binding"] == "unbound"
    assert sequence["start_end_gate"] == "unpassed"
    assert sequence["process_start_key_used"] is False
    assert "exit_key_mismatch" in receipt["diagnostics"]["gaps"]
    assert etw_lifecycle_receipt_qualifies(receipt) is False
    text = json.dumps(receipt)
    assert str(KEY) not in text
    assert str(NOISE_KEY) not in text
    assert SECRET.decode() not in text
    assert '"unique_process_key"' not in text
    assert receipt["privacy"]["unique_process_key_omitted"] is True
    assert receipt["privacy"]["private_owner_omitted"] is True
    assert receipt["privacy"]["payloads_omitted"] is True
    assert receipt["privacy"]["handles_omitted"] is True
    assert receipt["privacy"]["unrelated_rows_omitted"] is True
    assert receipt["privacy"]["command_lines_omitted"] is True
    assert receipt["privacy"]["environment_omitted"] is True
    assert receipt["privacy"]["paths_omitted"] is True
    assert receipt["privacy"]["exception_text_omitted"] is True
    assert receipt["privacy"]["public_safe_disposition"] is False


def test_worker_timeout_marks_cleanup_unverified_and_does_not_retry():
    def explode():
        raise AssertionError("worker receipt was adopted after the deadline")

    receipt, calls = _supervisor(drained=False, phase="before_session_start", read_result=explode)
    _assert_schema(receipt)
    assert calls == [("spawn",), ("wait", 30), ("terminate",), ("wait", 5), ("phase",), ("close",)]
    assert receipt["unsupported"] == "worker_deadline"
    assert receipt["worker"]["deadline_exceeded"] is True
    assert receipt["worker"]["report_adopted"] is False
    assert receipt["fixture_launched"] is None
    assert receipt["etw_cleanup"]["verified"] is False
    assert receipt["etw_cleanup"]["reason"] == "worker_deadline"
    assert receipt["native_session_starts"] is None
    assert receipt["api"]["stop_trace"]["attempted"] is None
    assert receipt["api"]["stop_trace"]["code"] == "unknown"
    assert receipt["supervisor_job"]["terminated"] is True
    assert receipt["supervisor_job"]["drain_ok"] is False
    assert receipt["supervisor_job"]["close_ok"] is True
    assert receipt["supervisor_job"]["cleanup_ok"] is False
    assert receipt["supervisor_job"]["cleanup_failure"] == "drain_timeout"
    assert "before_session_start" in receipt["phases"]
    assert "supervisor_deadline" in receipt["phases"]
    assert etw_lifecycle_receipt_qualifies(receipt) is False
    launched, _launched_calls = _supervisor(
        drained=False,
        phase="before_observer_finish",
        read_result=explode,
    )
    _assert_schema(launched)
    assert launched["fixture_launched"] is None
    assert launched["worker"]["report_adopted"] is False
    assert launched["unsupported"] == "worker_deadline"


def test_late_launch_does_not_reset_the_worker_budget():
    ticks = {"count": 0}

    def clock():
        ticks["count"] += 1
        return 0.0 if ticks["count"] == 1 else 31.0

    def explode():
        raise AssertionError("late worker result was adopted")

    receipt, calls = _supervisor(
        drained=False,
        phase="before_observer_finish",
        clock=clock,
        read_result=explode,
    )
    _assert_schema(receipt)
    assert ("wait", 30) not in calls
    assert ("wait", 30.0) not in calls
    assert ("result",) not in calls
    assert ("wait", 5) in calls
    assert calls.count(("spawn",)) == 1
    assert receipt["unsupported"] == "worker_deadline"
    assert receipt["fixture_launched"] is None
    assert receipt["worker"]["deadline_exceeded"] is True
    assert receipt["worker"]["report_adopted"] is False
    assert receipt["etw_cleanup"]["verified"] is False
    assert receipt["etw_cleanup"]["reason"] == "worker_deadline"
    assert etw_lifecycle_receipt_qualifies(receipt) is False


def test_supervisor_exception_keeps_termination_and_drain_failures():
    def explode():
        raise AssertionError("worker receipt was adopted after the supervisor exception")

    receipt, calls = _supervisor(
        wait_results=[RuntimeError(EXCEPTION_TOKEN), False],
        terminate_result=(False, "boom"),
        close=(True, None),
        read_result=explode,
    )
    _assert_schema(receipt)
    text = json.dumps(receipt)
    assert calls.count(("spawn",)) == 1
    assert ("terminate",) in calls
    assert ("wait", 5) in calls
    assert ("result",) not in calls
    assert receipt["unsupported"] == "worker_exception"
    assert receipt["fixture_launched"] is None
    assert receipt["worker"]["deadline_exceeded"] is False
    assert receipt["worker"]["report_adopted"] is False
    assert receipt["supervisor_job"]["terminated"] is False
    assert receipt["supervisor_job"]["drain_ok"] is False
    assert receipt["supervisor_job"]["close_ok"] is True
    assert receipt["supervisor_job"]["cleanup_ok"] is False
    assert receipt["supervisor_job"]["cleanup_failure"] == "terminate_failed"
    assert receipt["etw_cleanup"]["verified"] is False
    assert receipt["etw_cleanup"]["reason"] == "unverified"
    assert "boom" not in text
    assert EXCEPTION_TOKEN not in text
    assert "before_supervisor_terminate" in receipt["phases"]
    assert "before_supervisor_drain" in receipt["phases"]
    assert etw_lifecycle_receipt_qualifies(receipt) is False


def test_api_wrapper_entry_stays_attempted_when_the_call_raises():
    class RaisingStart(SyncApi):
        def start_session(self, request):
            raise RuntimeError(EXCEPTION_TOKEN)

    receipt, _api, job, _phase, _calls = _run(api=RaisingStart())
    _assert_schema(receipt)
    text = json.dumps(receipt)
    assert job.spawn_calls == 0
    assert receipt["unsupported"] == "worker_exception"
    assert receipt["fixture_launched"] is False
    assert receipt["session_start_calls"] == 1
    assert receipt["native_session_starts"] == 0
    assert receipt["api"]["start_trace"]["attempted"] is True
    assert receipt["api"]["start_trace"]["ok"] is None
    assert receipt["api"]["start_trace"]["code"] == "unknown"
    assert receipt["api"]["open_trace"]["attempted"] is False
    assert receipt["api"]["open_trace"]["code"] == "not_attempted"
    assert EXCEPTION_TOKEN not in text
    assert etw_lifecycle_receipt_qualifies(receipt) is False


def test_close_pending_is_distinct_from_close_failure():
    pending, pending_api, _job, _phase, _calls = _run(
        _generation(10, 1, KEY, 5000, 5600, 80),
        api=SyncApi(close_mode="pending"),
    )
    failed, failed_api, _job, _phase, _calls = _run(
        _generation(10, 1, KEY, 5000, 5600, 80),
        api=SyncApi(close_mode="fail"),
    )
    _assert_schema(pending)
    _assert_schema(failed)
    assert pending_api.closes == [202]
    assert failed_api.closes == [202]
    assert pending["api"]["close_trace"]["code"] == "close_pending"
    assert pending["api"]["close_trace"]["pending"] is True
    assert pending["etw_cleanup"]["reason"] == "close_pending"
    assert pending["etw_cleanup"]["close_failed"] is False
    assert "close_pending" in pending["diagnostics"]["gaps"]
    assert failed["api"]["close_trace"]["code"] == "close_failed"
    assert failed["api"]["close_trace"]["pending"] is False
    assert failed["etw_cleanup"]["reason"] == "close_failed"
    assert "close_pending" not in failed["diagnostics"]["gaps"]
    assert etw_lifecycle_receipt_qualifies(pending) is False
    assert etw_lifecycle_receipt_qualifies(failed) is False


def test_measured_job_close_failure_blocks_qualification():
    receipt, _api, job, _phase, _calls = _run(
        _generation(10, 1, KEY, 5000, 5600, 80),
        job=SyncJob(_snapshot(), close_result=(False, "boom")),
    )
    _assert_schema(receipt)
    assert job.spawn_calls == 1
    assert receipt["measured_job"]["drain_ok"] is True
    assert receipt["measured_job"]["close_ok"] is False
    assert receipt["measured_job"]["cleanup_ok"] is False
    assert receipt["measured_job"]["cleanup_failure"] == "close_failed"
    assert "boom" not in json.dumps(receipt)
    assert etw_lifecycle_receipt_qualifies(receipt) is False


def test_measured_drain_failure_is_not_closed_as_cleanup():
    receipt, _api, _job, _phase, _calls = _run(
        _generation(10, 1, KEY, 5000, 5600, 80),
        job=SyncJob(_snapshot(), drain_result=False),
    )
    _assert_schema(receipt)
    assert receipt["measured_job"]["drain_ok"] is False
    assert receipt["measured_job"]["close_ok"] is True
    assert receipt["measured_job"]["cleanup_ok"] is False
    assert receipt["measured_job"]["cleanup_failure"] == "drain_timeout"
    assert "job_active_processes" in receipt["diagnostics"]["gaps"]
    assert etw_lifecycle_receipt_qualifies(receipt) is False


def test_supervisor_close_failure_blocks_a_complete_worker_report():
    failed, calls = _supervisor(result=_evidence(), close=(False, "boom"))
    _assert_schema(failed)
    assert ("spawn",) in calls
    assert calls.count(("spawn",)) == 1
    assert failed["supervisor_job"]["drain_ok"] is True
    assert failed["supervisor_job"]["close_ok"] is False
    assert failed["supervisor_job"]["cleanup_ok"] is False
    assert failed["supervisor_job"]["cleanup_failure"] == "close_failed"
    assert failed["supervisor_job"]["terminated"] is False
    assert failed["worker"]["report_adopted"] is True
    assert "boom" not in json.dumps(failed)
    assert etw_lifecycle_receipt_qualifies(failed) is False
    adopted, _ok_calls = _supervisor(result=_evidence(), close=(True, None))
    _assert_schema(adopted)
    assert adopted["supervisor_job"]["drain_ok"] is True
    assert adopted["supervisor_job"]["close_ok"] is True
    assert adopted["supervisor_job"]["cleanup_ok"] is True
    assert adopted["supervisor_job"]["terminated"] is False
    assert adopted["owned_event_qualified"] is True
    assert etw_lifecycle_receipt_qualifies(adopted) is True
    assert adopted["last_phase"] == "supervisor_finished"
    assert "worker_finished" in adopted["phases"]


def test_nested_job_denial_does_not_launch_outside_the_job():
    worker, api, job, _phase, calls = _run(
        api=SyncApi([]),
        job=SyncJob(_snapshot(), fail=OwnedLaunchError("create_process_5")),
    )
    _assert_schema(worker)
    assert calls["factory"] == 1
    assert job.spawn_calls == 1
    assert worker["fixture_launched"] is False
    assert worker["unsupported"] == "nested_job_denied"
    assert api.stops == [101]
    assert etw_lifecycle_receipt_qualifies(worker) is False
    supervisor, supervisor_calls = _supervisor(spawn_error=OwnedLaunchError("create_process_5"))
    _assert_schema(supervisor)
    assert supervisor_calls == [("spawn",)]
    assert supervisor["unsupported"] == "nested_job_denied"
    assert supervisor["fixture_launched"] is False


def test_receipt_allowlist_drops_private_material():
    with tempfile.TemporaryDirectory() as directory:
        marker = Path(directory) / MARKER_TOKEN
        records = _generation(10, 1, KEY, 5000, 5600, 80)
        records.extend(_generation(NOISE_PID, 1, NOISE_KEY, 8000, 9000, 90))
        records.append(_counter(10, 70, 4000, opcode=OPCODE_PERFCTR_RUNDOWN))
        receipt, api, _job, _phase, _calls = _run(records, marker=marker)
    _assert_schema(receipt)
    text = json.dumps(receipt)
    assert api.private_owner is not None
    assert receipt["unsupported"] is None
    assert receipt["sequence"]["bound"] is True
    assert receipt["sequence"]["opcodes"] == [1, 2, 32]
    assert receipt["sequence"]["opcode33_rundown_ignored"] == 1
    assert receipt["sequence"]["process_start_key_used"] is False
    assert receipt["fixture_completion_marker"] is True
    assert receipt["native_session_starts"] == 0
    assert receipt["preserved"]["qualification"] == "unqualified"
    assert receipt["preserved"]["native_unit_corroboration"] == "unrun"
    assert receipt["preserved"]["resource_acceptance"] is False
    assert receipt["preserved"]["telemetry_enabled"] is False
    assert etw_lifecycle_receipt_qualifies(receipt) is False
    for hidden in (
        '"unique_process_key"',
        '"private_owner"',
        '"control_handle"',
        '"payload"',
        MARKER_TOKEN,
        str(KEY),
        str(NOISE_PID),
        str(NOISE_KEY),
        SECRET.decode(),
    ):
        assert hidden not in text
    dirty, _calls = _supervisor(result={"unique_process_key": KEY, "path": "C:\\" + MARKER_TOKEN})
    _assert_schema(dirty)
    assert dirty["unsupported"] == "worker_receipt_invalid"
    dirty_text = json.dumps(dirty)
    assert str(KEY) not in dirty_text
    assert MARKER_TOKEN not in dirty_text


def test_exception_text_is_not_copied():
    receipt, _api, _job, _phase, _calls = _run(job=SyncJob(RuntimeError(EXCEPTION_TOKEN)))
    _assert_schema(receipt)
    assert receipt["unsupported"] == "worker_exception"
    assert EXCEPTION_TOKEN not in json.dumps(receipt)


def test_job_only_lifecycle_gate_is_not_the_etw_gate():
    job_receipt = {
        "held": True,
        "resource_acceptance": False,
        "cleanup_ok": True,
        "cleanup_failure": None,
    }
    assert lifecycle_receipt_qualifies(job_receipt) is True
    assert etw_lifecycle_receipt_qualifies(job_receipt) is False
    evidenced = _evidence()
    evidenced["phases"] = list(evidenced["phases"]) + ["supervisor_finished"]
    evidenced["last_phase"] = "supervisor_finished"
    evidenced["worker"]["report_adopted"] = True
    evidenced["supervisor_job"] = {
        "cleanup_ok": True,
        "cleanup_failure": None,
        "terminated": False,
        "drain_ok": True,
        "close_ok": True,
    }
    assert etw_lifecycle_receipt_qualifies(evidenced) is True
    evidenced["owned_event_qualified"] = True
    assert stored_qualification_matches(evidenced) is True
    blockers = [
        ("callback_evidence", False),
        ("native_session_starts", 0),
        ("fixture_launched", False),
        ("readiness_before_process_trace", False),
    ]
    for key, value in blockers:
        broken = json.loads(json.dumps(evidenced))
        broken[key] = value
        broken["owned_event_qualified"] = True
        assert etw_lifecycle_receipt_qualifies(broken) is False
        assert stored_qualification_matches(broken) is False
    unbound = json.loads(json.dumps(evidenced))
    unbound["sequence"]["bound"] = False
    unbound["sequence"]["binding"] = "unbound"
    unbound["sequence"]["opcodes"] = []
    unbound["measured_job"]["census_matches_expected"] = True
    assert etw_lifecycle_receipt_qualifies(unbound) is False
    contradictions = [
        (("measured_job", "census_active"), 1),
        (("measured_job", "census_total"), 2),
        (("measured_job", "census_matches_expected"), False),
        (("measured_job", "drain_ok"), False),
        (("measured_job", "close_ok"), False),
        (("measured_job", "cleanup_ok"), False),
        (("etw_cleanup", "callbacks_released"), False),
        (("etw_cleanup", "session_released"), False),
        (("etw_cleanup", "consumer_finished"), False),
        (("etw_cleanup", "stop_ok"), False),
        (("etw_cleanup", "close_pending"), True),
        (("etw_cleanup", "close_failed"), True),
        (("etw_cleanup", "verified"), False),
        (("supervisor_job", "drain_ok"), False),
        (("supervisor_job", "close_ok"), False),
        (("supervisor_job", "cleanup_ok"), False),
    ]
    for path, value in contradictions:
        broken = json.loads(json.dumps(evidenced))
        cursor = broken
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = value
        broken["owned_event_qualified"] = True
        assert receipt_schema_ok(broken)
        assert etw_lifecycle_receipt_qualifies(broken) is False
        assert stored_qualification_matches(broken) is False


def test_phase_file_stores_only_the_token():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "phase.json"
        log = PhaseLog(path)
        log.mark("before_session_start")
        assert read_phase(path) == "before_session_start"
        body = json.loads(path.read_text(encoding="utf-8"))
        assert set(body) == {"phase", "seq"}


def test_main_refuses_dispatch_and_wrong_architecture_without_spawning():
    with tempfile.TemporaryDirectory() as directory:
        receipt_path = Path(directory) / "receipt.json"
        calls = []

        def spawn():
            calls.append("spawn")
            raise AssertionError("spawned")

        code = main(
            ["--source", SOURCE, "--receipt", str(receipt_path), "--attempt", "1"],
            environ={},
            spawn_worker=spawn,
            identity=_identity(),
            head=SOURCE,
            provider_hash=PROVIDER_SHA256,
            run_id="99",
        )
        assert code == 1
        assert calls == []
        refused = json.loads(receipt_path.read_text(encoding="utf-8"))
        _assert_schema(refused)
        assert refused["unsupported"] == "dispatch_not_authorized"
        code = main(
            ["--source", SOURCE, "--receipt", str(receipt_path), "--attempt", "1"],
            environ={"MNEMION_ETW_LIFECYCLE_DISPATCH": "1"},
            spawn_worker=spawn,
            identity=_identity(pe_machine=43620, platform_machine="ARM64"),
            head=SOURCE,
            provider_hash=PROVIDER_SHA256,
            run_id="99",
        )
        assert code == 1
        assert calls == []
        archived = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert archived["unsupported"] == "wrong_architecture"


def test_provider_bytes_and_driver_boundaries_stay_fixed():
    provider = (ROOT / "deploy" / "owned_launch_windows_etw.py").read_bytes()
    accounting = (ROOT / "deploy" / "owned_launch_accounting.py").read_bytes()
    assert hashlib.sha256(provider).hexdigest() == PROVIDER_SHA256
    assert hashlib.sha256(accounting).hexdigest() == ACCOUNTING_SHA256
    text = (ROOT / "deploy" / "windows_etw_lifecycle.py").read_text(encoding="utf-8")
    for banned in (
        "Popen",
        "taskkill",
        "StopTrace",
        "StartTrace",
        "AssignProcessToJobObject",
        "advapi32",
        "kernel32",
        "start_owned_launch",
    ):
        assert banned not in text
    assert text.count("WinEtwApi(") == 1
    workflow = (ROOT / ".github" / "workflows" / "windows-etw-lifecycle.yml").read_text(
        encoding="utf-8"
    )
    assert "workflow_dispatch:" in workflow
    assert "push:" not in workflow
    assert "pull_request:" not in workflow
    assert "windows-2022" in workflow
    assert "windows-11-arm" not in workflow
    assert "arm64" not in workflow.lower()
    assert "strategy:" not in workflow
    assert 'python-version: "3.13.17"' in workflow
    assert "architecture: x64" in workflow
    assert "persist-credentials: false" in workflow
    assert "timeout-minutes: 10" in workflow
    assert "if: always()" in workflow
    assert "path: output/windows-etw-lifecycle/receipt.json" in workflow
    assert "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803" in workflow
    assert "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1" in workflow
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in workflow
    assert 'MNEMION_ETW_LIFECYCLE_DISPATCH: "1"' in workflow
    assert "self-hosted" not in workflow
    assert "rev-parse" in workflow
    assert "[0-9a-f]{40}" in workflow
    assert "head != source" in workflow


def test_import_does_not_load_a_native_tracer():
    with tempfile.TemporaryDirectory() as directory:
        program = Path(directory) / "import_lifecycle.py"
        program.write_text(
            "import deploy.windows_etw_lifecycle as driver\n"
            "import deploy.owned_launch_windows_etw as etw\n"
            "assert etw.native_session_starts == 0\n"
            "assert etw.native_api_loaded is False\n"
            "assert driver.session_request()['stop_existing_session'] is False\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [sys.executable, str(program)],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            capture_output=True,
            text=True,
            check=False,
        )
    assert completed.returncode == 0, completed.stderr
