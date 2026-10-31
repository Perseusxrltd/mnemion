"""Offline tests for the ETW lifetime counter. No ETW API, process, or tracer."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import inspect
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from deploy.owned_launch_accounting import start_owned_launch
from deploy.owned_launch_windows_etw import (
    EVENT_HEADER_EXT_TYPE_PROCESS_START_KEY,
    EVENT_HEADER_FLAG_32_BIT_HEADER,
    EVENT_HEADER_FLAG_64_BIT_HEADER,
    EVENT_HEADER_FLAG_PROCESSOR_INDEX,
    MAX_CALLBACKS,
    MAX_RETAINED_EVENTS,
    OPCODE_DCSTART,
    OPCODE_DEFUNCT,
    OPCODE_END,
    OPCODE_PERFCTR,
    OPCODE_PERFCTR_RUNDOWN,
    OPCODE_START,
    PROCESS_PROVIDER_GUID,
    _EVENT_HEADER_EXTENDED_DATA_ITEM,
    _EVENT_RECORD,
    _record_to_dict,
    _COUNT_SATURATION,
    abi_field_offsets,
    bridge_event,
    consumer_layout_sizes,
    counter_payload_size,
    decode_record,
    host_offset,
    AdapterOwnership,
    LocalCleanupOwner,
    interpret_close_trace,
    native_api_loaded,
    native_session_starts,
    observe_owned_launch,
    resolve_owned,
    session_request,
    SESSION_NAME,
    EtwLifetimeObserver,
)


SECRET = b"MNEMION_ETW_SECRET_PATH\\S-1-5-21-999"
ROOT_PID = 10
ROOT_CREATION = 5_000


class FakeEtwApi:
    """Scripted session. It never calls advapi32."""

    def __init__(
        self,
        records=None,
        *,
        start_code="ok",
        open_ok=True,
        stop_unblocks=True,
        raise_in_process=False,
        delay_ready=False,
        loss=None,
        stop_ok=True,
        close_pending=False,
        close_error=False,
        finish_without_blocking=False,
        bridge_failure=False,
        bridge_secret=r"C:\Secret\should-not-leak",
    ):
        self.records = list(records or [])
        self.start_code = start_code
        self.open_ok = open_ok
        self.stop_unblocks = stop_unblocks
        self.raise_in_process = raise_in_process
        self.delay_ready = delay_ready
        self.stop_ok = stop_ok
        self.close_pending = close_pending
        self.close_error = close_error
        self.finish_without_blocking = finish_without_blocking
        self.bridge_failure = bridge_failure
        self.bridge_secret = bridge_secret
        self.callbacks_released = False
        self.loss = loss or {
            "events_lost": 0,
            "log_buffers_lost": 0,
            "real_time_buffers_lost": 0,
        }
        self.request = None
        self.session = None
        self.trace = None
        self.stops = []
        self.open_calls = []
        self.closes_trace = []
        self.closes_session = []
        self.consumer_ready = False
        self.on_event = None
        self._stop = threading.Event()
        self._closed = threading.Event()

    def start_session(self, request):
        self.request = dict(request)
        if self.start_code != "ok":
            return {"ok": False, "code": self.start_code, "handle": None}
        self.session = 101
        return {"ok": True, "code": "ok", "handle": self.session}

    def open_trace(self, session_name, on_event):
        self.open_calls.append(session_name)
        self.on_event = on_event
        if not self.open_ok:
            return {"ok": False, "code": "open_trace_failed", "handle": None}
        self.trace = 202
        return {"ok": True, "code": "ok", "handle": self.trace}

    def process_trace(self, handle, on_ready):
        if self.delay_ready:
            self._stop.wait(5)
            return {"ok": False, "code": "not_ready"}
        self.consumer_ready = True
        on_ready()
        if self.raise_in_process:
            raise RuntimeError("consumer failed")
        for record in self.records:
            self.on_event(record)
        if self.bridge_failure:
            secret = self.bridge_secret

            def convert():
                raise RuntimeError(secret)

            bridge_event(convert, self.on_event)
        if self.finish_without_blocking:
            return {"ok": True, "code": "ok"}
        if self.close_pending or self.close_error or not self.stop_unblocks:
            self._closed.wait(5)
        else:
            self._stop.wait(5)
        return {"ok": True, "code": "ok"}

    def stop_session(self, session_handle):
        self.stops.append(session_handle)
        if not self.stop_ok:
            return {"ok": False, "code": "stop_failed", "loss": {}}
        if self.stop_unblocks:
            self._stop.set()
        return {"ok": True, "code": "ok", "loss": dict(self.loss)}

    def close_trace(self, trace_handle):
        self.closes_trace.append(trace_handle)
        if self.close_pending:
            return {"ok": False, "code": "close_pending", "pending": True}
        if self.close_error:
            return {"ok": False, "code": "close_failed", "pending": False}
        self._closed.set()
        self._stop.set()
        return {"ok": True, "code": "ok", "pending": False}

    def close_session(self, session_handle):
        self.closes_session.append(session_handle)
        self.session = None
        return {"ok": True, "code": "ok"}

    def release_callbacks(self, trace_handle=None):
        self.callbacks_released = True

    def retain_recovery(self, state):
        self.private_owner = LocalCleanupOwner(self, state)

    def unblock(self):
        self._closed.set()
        self._stop.set()


class FakeJob:
    def __init__(self, snapshot, *, pid=ROOT_PID, creation=ROOT_CREATION, api=None, fail_spawn=False):
        self.root_pid = None
        self.root_creation = None
        self._pid = pid
        self._creation = creation
        self._snapshot = snapshot
        self.api = api
        self.fail_spawn = fail_spawn
        self.spawn_calls = 0
        self.spawned_after_ready = False

    def spawn(self):
        self.spawn_calls += 1
        if self.api is not None:
            self.spawned_after_ready = self.api.consumer_ready is True
        if self.fail_spawn:
            raise RuntimeError("spawn failed")
        self.root_pid = self._pid
        self.root_creation = self._creation

    def wait_until_drained(self, _seconds):
        return True

    def snapshot(self):
        return self._snapshot


def _u32(value):
    return int(value).to_bytes(4, "little", signed=False)


def _i32(value):
    return int(value).to_bytes(4, "little", signed=True)


def _usize(value, width):
    return int(value).to_bytes(width, "little", signed=False)


def counter_payload(pid, peak, width, *, virtual=0x1111, pagefile=0x2222, quota_paged=0x3333):
    dwords = b"".join(_u32(part) for part in (pid, 7, 8, 0))
    values = [virtual, peak, pagefile, quota_paged]
    values.extend(0x4000 + index for index in range(7))
    return dwords + b"".join(_usize(value, width) for value in values)


def lifecycle_payload(pid, parent, key, exit_status, width):
    size = width + 16
    buffer = bytearray(size)
    buffer[0:width] = _usize(key, width)
    buffer[host_offset(4, 1, width) : host_offset(4, 1, width) + 4] = _u32(pid)
    buffer[host_offset(8, 1, width) : host_offset(8, 1, width) + 4] = _u32(parent)
    buffer[host_offset(12, 1, width) : host_offset(12, 1, width) + 4] = _u32(1)
    buffer[host_offset(16, 1, width) : host_offset(16, 1, width) + 4] = _i32(exit_status)
    return bytes(buffer) + SECRET


def record(
    opcode,
    payload,
    timestamp,
    *,
    header_pid=0xFFFFFFFF,
    processor=0,
    version=2,
    flags=EVENT_HEADER_FLAG_64_BIT_HEADER,
    start_key=False,
    provider=PROCESS_PROVIDER_GUID,
):
    return {
        "provider": provider,
        "version": version,
        "opcode": opcode,
        "flags": flags,
        "timestamp": timestamp,
        "processor_index": processor,
        "header_pid": header_pid,
        "payload": payload,
        "process_start_key_present": start_key,
    }


def life(opcode, pid, parent, key, timestamp, exit_status=0, **kwargs):
    width = 4 if kwargs.get("flags") == EVENT_HEADER_FLAG_32_BIT_HEADER else 8
    return record(
        opcode,
        lifecycle_payload(pid, parent, key, exit_status, width),
        timestamp,
        **kwargs,
    )


def counter(pid, peak, timestamp, *, opcode=OPCODE_PERFCTR, width=8, version=2, **kwargs):
    flags = EVENT_HEADER_FLAG_32_BIT_HEADER if width == 4 else EVENT_HEADER_FLAG_64_BIT_HEADER
    payload = counter_payload(pid, peak, width)
    if version > 2:
        payload += SECRET
    return record(opcode, payload, timestamp, version=version, flags=flags, **kwargs)


def generation(pid, parent, key, start, end, peak, **kwargs):
    return [
        life(OPCODE_START, pid, parent, key, start, **kwargs),
        life(OPCODE_END, pid, parent, key, end, exit_status=0, **kwargs),
        counter(pid, peak, start + 1, **kwargs),
    ]


def snapshot(total, active=0, *, cpu=424242, process_commit=111, job_commit=222):
    return {
        "cpu_microseconds": cpu,
        "kernel": {
            "total_processes": total,
            "active_processes": active,
            "peak_process_commit_bytes": process_commit,
            "peak_job_commit_bytes": job_commit,
            "commit_counters_are_working_set": False,
        },
    }


def run(records, *, total, active=0, pid=ROOT_PID, creation=ROOT_CREATION, api_kwargs=None, **observe_kwargs):
    api = FakeEtwApi(records, **(api_kwargs or {}))
    job = FakeJob(snapshot(total, active), pid=pid, creation=creation, api=api)
    report = observe_owned_launch(job, api, **observe_kwargs)
    return report, api, job


def _rows(report):
    return {row["pid"]: row for row in report["owned"]}


def _assert_closed(api):
    assert api.session is None
    assert api.closes_trace
    assert api.closes_session
    assert all(isinstance(handle, int) for handle in api.stops)


def _assert_unaccepted(report):
    assert report["qualification"] == "unqualified"
    assert report["resource_acceptance"] is False
    assert report["budget_comparison_allowed"] is False
    assert report["budget"]["status"] == "UNACCEPTED"
    assert report["budget"]["compared"] is False
    assert report["proves_8mib_or_half_percent"] is False
    assert report["native_unit_corroboration"] == "unrun"
    assert report["production_accounting_switched"] is False
    assert report["production_method_unchanged"] == "windows_job_before_resume"
    assert report["cpu_authority"] == "windows_job"
    assert report["pagefile_and_job_peak_are_commit"] is True
    assert report["commit_counters_are_working_set"] is False
    assert report["rss_component_breakdown"] is False
    assert report["observer_overhead"]["disclosed"] is True
    assert report["observer_overhead"]["measured"] is False
    text = json.dumps(report)
    assert "MNEMION_ETW_SECRET_PATH" not in text
    assert "S-1-5-21-999" not in text
    assert all("payload" not in row for row in report["owned"])


def test_terminal_counter_beats_rundown_and_keeps_the_nested_tree():
    records = []
    records.extend(generation(12, 11, 0xB, 5_200, 5_300, 300_000))
    records.extend(generation(11, ROOT_PID, 0xA, 5_100, 5_400, 200_000))
    records.extend(generation(ROOT_PID, 1, 0xC, ROOT_CREATION, 5_600, 100_000, start_key=True, header_pid=99))
    records.append(counter(ROOT_PID, 9_999_999, 4_900, opcode=OPCODE_PERFCTR_RUNDOWN))
    records.append(record(10, SECRET, 50, provider="other-provider"))
    report, api, job = run(list(reversed(records)), total=3)
    rows = _rows(report)
    assert job.spawned_after_ready is True
    assert job.spawn_calls == 1
    assert set(rows) == {10, 11, 12}
    assert rows[10]["identity"] == "10:5000"
    assert rows[10]["peak_working_set_bytes"] == 100_000
    assert rows[10]["opcode33_used_as_terminal"] is False
    assert rows[10]["process_start_key_used"] is False
    assert rows[10]["parent_pid"] is None
    assert rows[11]["identity"] == "11:etw:5100"
    assert rows[11]["parent_identity"] == "10:5000"
    assert rows[11]["peak_working_set_bytes"] == 200_000
    assert rows[12]["parent_identity"] == "11:etw:5100"
    assert rows[12]["peak_working_set_bytes"] == 300_000
    assert rows[10]["peak_working_set_bytes"] != 111
    assert report["job_peak_process_commit_bytes"] == 111
    assert report["job_peak_job_commit_bytes"] == 222
    assert report["lifetime_cpu_microseconds"] == 424242
    assert report["coverage"]["status"] == "reconciled"
    assert report["coverage"]["gaps"] == []
    assert report["coverage"]["opcode33_ignored"] == 1
    assert report["loss"] == {
        "events_lost": 0,
        "log_buffers_lost": 0,
        "real_time_buffers_lost": 0,
    }
    _assert_closed(api)
    _assert_unaccepted(report)
    assert api.request["session_name"] == "Mnemion Owned Launch ETW"
    assert api.request["enable_flags"] == 0x9
    assert api.request["log_file_mode"] == 0x12000100


def test_orphan_child_stays_owned_after_the_parent_exit():
    records = generation(ROOT_PID, 1, 0xC, 1_000, 1_200, 100)
    records.extend(generation(11, ROOT_PID, 0xA, 1_100, 1_300, 250))
    report, _api, _job = run(records, total=2, creation=1_000)
    rows = _rows(report)
    assert rows[11]["exit_observed"] is True
    assert rows[11]["etw_end_filetime"] == 1_300
    assert rows[10]["etw_end_filetime"] == 1_200
    assert report["coverage"]["status"] == "reconciled"


def test_child_born_after_the_parent_exit_is_not_owned():
    records = generation(ROOT_PID, 1, 0xC, 1_000, 1_200, 100)
    records.extend(generation(11, ROOT_PID, 0xA, 1_300, 1_400, 250))
    report, _api, _job = run(records, total=2, creation=1_000)
    assert set(_rows(report)) == {ROOT_PID}
    assert "census_births" in report["coverage"]["gaps"]
    assert report["coverage"]["status"] == "missing"


def test_single_root_with_a_different_filetime_stays_unproven():
    records = generation(ROOT_PID, 1, 0xC, 1_111, 3_000, 80, header_pid=0xFFFFFFFF)
    report, _api, _job = run(records, total=1, creation=2_222)
    assert report["owned"] == []
    assert "root_binding_unproven" in report["coverage"]["gaps"]
    assert "root_unobserved" not in report["coverage"]["gaps"]
    assert report["coverage"]["pid_reuse_resolved_by_exact_creation"] is False
    assert report["coverage"]["status"] == "missing"
    assert "10:2222" not in json.dumps(report)
    _assert_unaccepted(report)


def test_reused_root_pid_binds_only_the_exact_creation():
    records = generation(ROOT_PID, 1, 0xABC, 1_000, 1_400, 11)
    records.extend(generation(ROOT_PID, 1, 0xABC, ROOT_CREATION, 5_600, 22))
    report, _api, _job = run(records, total=1)
    assert [row["identity"] for row in report["owned"]] == ["10:5000"]
    assert report["owned"][0]["peak_working_set_bytes"] == 22
    assert report["owned"][0]["unique_process_key"] == 0xABC
    assert report["owned"][0]["unique_process_key_is_generation_key"] is False
    assert report["coverage"]["pid_reuse_resolved_by_exact_creation"] is True
    assert report["coverage"]["status"] == "reconciled"


def test_reused_root_without_an_exact_creation_is_not_guessed():
    records = generation(ROOT_PID, 1, 0x1, 1_000, 1_400, 11)
    records.extend(generation(ROOT_PID, 1, 0x2, 2_000, 2_400, 22))
    report, _api, _job = run(records, total=2, creation=9_000)
    assert report["owned"] == []
    assert "root_ambiguous" in report["coverage"]["gaps"]
    assert "reused_pid" in report["coverage"]["gaps"]
    assert report["coverage"]["status"] == "missing"
    text = json.dumps(report["owned"])
    assert "10:1000" not in text
    assert "10:2000" not in text


def test_equal_birth_times_on_one_pid_stay_unqualified():
    records = [
        life(OPCODE_START, ROOT_PID, 1, 0x1, 1_000),
        life(OPCODE_START, ROOT_PID, 1, 0x2, 1_000, processor=1),
        life(OPCODE_END, ROOT_PID, 1, 0x1, 1_500),
        counter(ROOT_PID, 40, 1_200),
    ]
    report, _api, _job = run(records, total=1)
    assert report["owned"] == []
    assert "equal_time" in report["coverage"]["gaps"]
    assert "reused_pid" in report["coverage"]["gaps"]


def test_equal_time_parent_and_child_on_different_cpus_are_not_joined():
    records = generation(ROOT_PID, 1, 0xC, 1_000, 2_000, 100, processor=0)
    records.append(life(OPCODE_START, 11, ROOT_PID, 0xA, 1_000, processor=3))
    report, _api, _job = run(records, total=2, creation=1_000)
    assert set(_rows(report)) == {ROOT_PID}
    edge = next(item for item in report["ambiguities"] if item["kind"] == "parent_edge")
    assert edge["equal_time"] is True
    assert edge["cross_cpu"] is True
    assert "equal_time" in report["coverage"]["gaps"]
    assert "ambiguous_parent" in report["coverage"]["gaps"]


def test_equal_time_without_two_processor_indexes_does_not_invent_cross_cpu():
    records = generation(ROOT_PID, 1, 0xC, 1_000, 2_000, 100, processor=None)
    records.append(life(OPCODE_START, 11, ROOT_PID, 0xA, 1_000, processor=None))
    report, _api, _job = run(records, total=2, creation=1_000)
    edge = next(item for item in report["ambiguities"] if item["kind"] == "parent_edge")
    assert edge["cross_cpu"] is None
    assert "equal_time" in report["coverage"]["gaps"]


def test_same_unique_process_key_does_not_merge_two_generations():
    records = generation(ROOT_PID, 1, 0xABC, 1_000, 2_000, 100)
    records.extend(generation(11, ROOT_PID, 0xABC, 1_500, 1_800, 250))
    report, _api, _job = run(records, total=2, creation=1_000)
    rows = _rows(report)
    assert rows[10]["identity"] != rows[11]["identity"]
    assert rows[10]["unique_process_key"] == rows[11]["unique_process_key"]
    assert rows[10]["unique_process_key_is_generation_key"] is False
    assert report["coverage"]["status"] == "reconciled"


def test_loss_and_census_gaps_stay_missing():
    records = generation(ROOT_PID, 1, 0xC, ROOT_CREATION, 1_500, 100)
    lost, _api, _job = run(
        records,
        total=1,
        api_kwargs={"loss": {"events_lost": 1, "log_buffers_lost": 0, "real_time_buffers_lost": 0}},
    )
    assert lost["coverage"]["status"] == "missing"
    assert "events_lost" in lost["coverage"]["gaps"]
    buffers, _api, _job = run(
        records,
        total=1,
        api_kwargs={"loss": {"events_lost": 0, "log_buffers_lost": 2, "real_time_buffers_lost": 0}},
    )
    assert "log_buffers_lost" in buffers["coverage"]["gaps"]
    realtime, _api, _job = run(
        records,
        total=1,
        api_kwargs={"loss": {"events_lost": 0, "log_buffers_lost": 0, "real_time_buffers_lost": 3}},
    )
    assert "real_time_buffers_lost" in realtime["coverage"]["gaps"]
    active, _api, _job = run(records, total=1, active=1)
    assert "job_active_processes" in active["coverage"]["gaps"]
    births, _api, _job = run(records, total=4)
    assert "census_births" in births["coverage"]["gaps"]
    no_end = [
        life(OPCODE_START, ROOT_PID, 1, 0xC, ROOT_CREATION),
        counter(ROOT_PID, 100, ROOT_CREATION + 1),
    ]
    exits, _api, _job = run(no_end, total=1)
    assert "exit_missing" in exits["coverage"]["gaps"]
    assert "census_exits" in exits["coverage"]["gaps"]
    no_counter = [
        life(OPCODE_START, ROOT_PID, 1, 0xC, ROOT_CREATION),
        life(OPCODE_END, ROOT_PID, 1, 0xC, ROOT_CREATION + 10),
        counter(ROOT_PID, 999, 100, opcode=OPCODE_PERFCTR_RUNDOWN),
    ]
    missing, _api, _job = run(no_counter, total=1)
    assert missing["owned"][0]["peak_working_set_bytes"] is None
    assert missing["owned"][0]["terminal_counter_opcode32"] is False
    assert "terminal_counter_missing" in missing["coverage"]["gaps"]
    assert "census_terminal_counters" in missing["coverage"]["gaps"]
    two_counters = [
        life(OPCODE_START, ROOT_PID, 1, 0xC, ROOT_CREATION),
        life(OPCODE_END, ROOT_PID, 1, 0xC, ROOT_CREATION + 10),
        counter(ROOT_PID, 100, ROOT_CREATION + 1),
        counter(ROOT_PID, 200, ROOT_CREATION + 2),
    ]
    unqualified, _api, _job = run(two_counters, total=1)
    assert unqualified["owned"][0]["peak_working_set_bytes"] is None
    assert "terminal_counter_unqualified" in unqualified["coverage"]["gaps"]


def test_malformed_payloads_and_pointer_widths_are_rejected():
    assert host_offset(20, 1, 8) == 24
    assert host_offset(20, 1, 4) == 20
    assert host_offset(60, 11, 8) == 104
    assert counter_payload_size(8) == 104
    assert counter_payload_size(4) == 60
    good = counter_payload(10, 0x100000008, 8, virtual=0x0123456789ABCDEF, pagefile=0x200000002, quota_paged=0x4444444455555555)
    assert int.from_bytes(good[24:32], "little") == 0x100000008
    assert int.from_bytes(good[40:48], "little") == 0x4444444455555555
    decoded = decode_record(record(OPCODE_PERFCTR, good, 10))
    assert decoded["peak_working_set_bytes"] == 0x100000008
    assert decoded["peak_working_set_bytes"] != int.from_bytes(good[20:24], "little")
    assert decoded["peak_working_set_bytes"] != int.from_bytes(good[40:48], "little")
    narrow = counter_payload(10, 0x89ABCDEF, 4, pagefile=0x11111111)
    assert int.from_bytes(narrow[20:24], "little") == 0x89ABCDEF
    assert int.from_bytes(narrow[20:28], "little") != 0x89ABCDEF
    decoded_narrow = decode_record(
        record(OPCODE_PERFCTR, narrow, 10, flags=EVENT_HEADER_FLAG_32_BIT_HEADER)
    )
    assert decoded_narrow["pointer_width"] == 4
    assert decoded_narrow["peak_working_set_bytes"] == 0x89ABCDEF
    both = EVENT_HEADER_FLAG_32_BIT_HEADER | EVENT_HEADER_FLAG_64_BIT_HEADER
    assert decode_record(record(OPCODE_PERFCTR, good, 10, flags=both))["disposition"] == "malformed"
    assert decode_record(record(OPCODE_PERFCTR, good, 10, flags=0))["disposition"] == "malformed"
    assert decode_record(record(OPCODE_PERFCTR, good[:-1], 10))["disposition"] == "malformed"
    assert decode_record(record(OPCODE_PERFCTR, good, 10, version=1))["disposition"] == "malformed"
    assert decode_record(record(OPCODE_START, lifecycle_payload(1, 0, 1, 0, 8)[:8], 10, version=1))[
        "disposition"
    ] == "malformed"
    longer = decode_record(record(OPCODE_PERFCTR, good + SECRET, 10, version=3))
    assert longer["peak_working_set_bytes"] == 0x100000008
    assert "MNEMION_ETW_SECRET_PATH" not in json.dumps(longer)
    lifecycle = decode_record(life(OPCODE_START, 10, 4, 0x1122334455667788, 10, header_pid=4))
    assert lifecycle["pid"] == 10
    assert lifecycle["parent_pid"] == 4
    assert lifecycle["header_pid_used"] is False
    assert lifecycle["process_start_key_used"] is False
    payload = lifecycle_payload(10, 4, 0x1122334455667788, 0, 8)
    assert int.from_bytes(payload[4:8], "little") != 10
    assert decode_record(record(OPCODE_DCSTART, lifecycle_payload(10, 1, 1, 0, 8), 10))["opcode"] == OPCODE_DCSTART
    assert decode_record(record(99, b"", 10))["disposition"] == "ignore"


def test_rundown_and_defunct_do_not_create_a_root():
    records = [
        life(OPCODE_DCSTART, ROOT_PID, 1, 0xC, ROOT_CREATION),
        life(OPCODE_DEFUNCT, ROOT_PID, 1, 0xC, ROOT_CREATION + 1),
        counter(ROOT_PID, 50, ROOT_CREATION + 2, opcode=OPCODE_PERFCTR_RUNDOWN),
    ]
    report, _api, _job = run(records, total=1)
    assert report["owned"] == []
    assert "root_unobserved" in report["coverage"]["gaps"]


def test_record_callback_reads_payload_pid_width_and_not_the_start_key_value():
    payload = counter_payload(10, 64, 8)
    buffer = ctypes.create_string_buffer(payload)
    item = _EVENT_HEADER_EXTENDED_DATA_ITEM()
    item.ExtType = EVENT_HEADER_EXT_TYPE_PROCESS_START_KEY
    item.DataPtr = 0xDEADBEEF
    native = _EVENT_RECORD()
    native.EventHeader.Flags = EVENT_HEADER_FLAG_64_BIT_HEADER | EVENT_HEADER_FLAG_PROCESSOR_INDEX
    native.EventHeader.TimeStamp = 80
    native.EventHeader.ProcessId = 0xFFFFFFFF
    native.EventHeader.EventDescriptor.Version = 2
    native.EventHeader.EventDescriptor.Opcode = OPCODE_PERFCTR
    native.EventHeader.ProviderId.Data1 = 0x3D6FA8D0
    native.EventHeader.ProviderId.Data2 = 0xFE05
    native.EventHeader.ProviderId.Data3 = 0x11D0
    data4 = bytes.fromhex("9dda00c04fd7ba7c")
    for index, value in enumerate(data4):
        native.EventHeader.ProviderId.Data4[index] = value
    native.BufferContext.ProcessorIndex = 0x0104
    native.ExtendedDataCount = 1
    native.ExtendedData = ctypes.addressof(item)
    native.UserDataLength = len(payload)
    native.UserData = ctypes.addressof(buffer)
    copied = _record_to_dict(native)
    assert copied["provider"] == PROCESS_PROVIDER_GUID
    assert copied["processor_index"] == 0x0104
    assert copied["process_start_key_present"] is True
    assert copied["header_pid"] == 0xFFFFFFFF
    decoded = decode_record(copied)
    assert decoded["pid"] == 10
    assert decoded["peak_working_set_bytes"] == 64
    assert decoded["process_start_key_used"] is False
    assert "deadbeef" not in json.dumps(decoded)
    native.EventHeader.Flags = EVENT_HEADER_FLAG_64_BIT_HEADER
    masked = _record_to_dict(native)
    assert masked["processor_index"] == 0x04


def test_failure_paths_release_handles_and_do_not_stop_someone_else():
    exists = FakeEtwApi(start_code="already_exists")
    job = FakeJob(snapshot(0), api=exists)
    report = observe_owned_launch(job, exists, ready_seconds=0.2, drain_seconds=0.2)
    assert job.spawn_calls == 0
    assert exists.stops == []
    assert exists.open_calls == []
    assert exists.closes_session == []
    assert "session_exists_not_stopped" in report["coverage"]["gaps"]
    assert "events_lost" not in report["coverage"]["gaps"]
    assert "stop_or_drain_failed" not in report["coverage"]["gaps"]
    denied = FakeEtwApi(start_code="access_denied")
    denied_job = FakeJob(snapshot(0), api=denied)
    denied_report = observe_owned_launch(denied_job, denied, ready_seconds=0.2, drain_seconds=0.2)
    assert denied.stops == []
    assert "access_denied" in denied_report["coverage"]["gaps"]
    opened = FakeEtwApi(open_ok=False)
    observer = EtwLifetimeObserver(opened, ready_seconds=0.2, drain_seconds=0.2)
    assert observer.start_before_root() is False
    opened_report = observer.finish(None)
    assert observer.callback_live is False
    assert opened.stops == [101]
    assert opened.closes_session == [101]
    assert "open_trace_failed" in opened_report["coverage"]["gaps"]
    late_report, late_api, late_job = run([], total=0, api_kwargs={"delay_ready": True}, ready_seconds=0.2, drain_seconds=0.3)
    assert late_job.spawn_calls == 0
    assert "consumer_not_ready" in late_report["coverage"]["gaps"]
    assert late_api.stops
    exploding = FakeEtwApi(raise_in_process=True)
    boom = FakeJob(snapshot(0), api=exploding)
    boom_report = observe_owned_launch(boom, exploding, ready_seconds=1, drain_seconds=0.5)
    assert "callback_failed" in boom_report["coverage"]["gaps"]
    _assert_closed(exploding)
    stuck = FakeEtwApi(stop_unblocks=False)
    stuck_job = FakeJob(snapshot(0), api=stuck)
    stuck_report = observe_owned_launch(stuck_job, stuck, ready_seconds=1, drain_seconds=0.25)
    assert "deadline_exceeded" in stuck_report["coverage"]["gaps"]
    assert stuck.closes_trace == [202]
    assert stuck.session is None


def test_spawn_failure_still_closes_the_session():
    api = FakeEtwApi([])
    job = FakeJob(snapshot(0), api=api, fail_spawn=True)
    try:
        observe_owned_launch(job, api, ready_seconds=1, drain_seconds=0.5)
    except RuntimeError as error:
        assert str(error) == "spawn failed"
    else:
        raise AssertionError("spawn failure must propagate")
    assert job.spawned_after_ready is True
    _assert_closed(api)


def test_retained_and_callback_caps_fail_closed():
    many = [
        life(OPCODE_START, index + 1, 0, index + 1, 1_000 + index)
        for index in range(MAX_RETAINED_EVENTS + 1)
    ]
    retained, _api, _job = run(many, total=1, pid=1, creation=1_000)
    assert "retained_records_exceeded" in retained["coverage"]["gaps"]
    ignored = [record(99, b"", index) for index in range(MAX_CALLBACKS + 1)]
    capped, _api, _job = run(ignored, total=0, pid=1, creation=1)
    assert "callbacks_exceeded" in capped["coverage"]["gaps"]


def test_session_request_is_a_private_realtime_system_logger():
    request = session_request()
    assert request == session_request()
    assert request["session_name"] == "Mnemion Owned Launch ETW"
    assert request["rejected_session_name"] == "NT Kernel Logger"
    assert request["guid_is_null"] is True
    assert request["rejected_guid"] == "9e814aad-3204-11d2-9a82-006008a86939"
    assert request["log_file_name"] is None
    assert request["etl_file"] is False
    assert request["real_time"] is True
    assert request["system_logger"] is True
    assert request["no_per_processor_buffering"] is True
    assert request["enable_flags"] == 0x1 | 0x8
    assert request["log_file_mode"] == 0x12000100
    assert request["buffer_size_kb"] == 16
    assert request["minimum_buffers"] == 2
    assert request["maximum_buffers"] == 16
    assert request["flush_timer_seconds"] == 1
    assert request["raw_timestamp"] is False
    assert request["process_start_key_enabled"] is False
    assert request["privilege_escalation"] is False
    assert request["stop_existing_session"] is False
    source = inspect.getsource(start_owned_launch)
    assert "owned_launch_windows_etw" not in source
    assert "StartTrace" not in source


def test_llp64_structure_offsets_match_the_sdk_field_list():
    sizes = consumer_layout_sizes()
    assert sizes["pointer"] == 8
    assert sizes["c_long"] == 4
    assert sizes["size_t"] == 8
    assert sizes["wnode"] == 48
    assert sizes["properties"] == 120
    assert sizes["event_header"] == 80
    assert sizes["event_record"] == 112
    assert sizes["time_zone"] == 172
    assert sizes["extended_item"] == 16
    assert sizes["event_trace"] == 88
    assert sizes["logfile_header"] == 280
    assert sizes["logfile"] == 448
    assert abi_field_offsets() == {
        "wnode_guid": 24,
        "wnode_client_context": 40,
        "wnode_flags": 44,
        "events_lost": 88,
        "log_buffers_lost": 96,
        "real_time_buffers_lost": 100,
        "event_record_user_context": 104,
        "logfile_buffer_callback": 400,
        "logfile_event_record_callback": 424,
        "logfile_context": 440,
        "logfile_process_trace_mode": 28,
    }
    assert native_session_starts == 0
    assert native_api_loaded is False
    assert ctypes.sizeof(wintypes.DWORD) == 4


def test_import_does_not_load_a_native_tracer(tmp_path):
    root = Path(__file__).resolve().parents[1]
    source = root / "deploy" / "owned_launch_windows_etw.py"
    text = source.read_text(encoding="utf-8")
    assert "owned_launch_windows_debug_capture" not in text
    assert "AdjustTokenPrivileges" not in text
    program = tmp_path / "import_etw.py"
    program.write_text(
        "import deploy.owned_launch_windows_etw as etw\n"
        "assert etw.native_session_starts == 0\n"
        "assert etw.native_api_loaded is False\n"
        "etw.session_request()\n"
        "etw.consumer_layout_sizes()\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, str(program)],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(root)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_old_ended_singleton_is_not_the_retained_root():
    records = generation(ROOT_PID, 1, 0xC, 1_000, 1_200, 80)
    report, _api, _job = run(records, total=1, active=0, creation=9_000_000_000)
    assert report["owned"] == []
    assert "root_binding_unproven" in report["coverage"]["gaps"]
    assert "root_unobserved" not in report["coverage"]["gaps"]
    assert report["coverage"]["status"] == "missing"
    assert report["loss"] == {
        "events_lost": 0,
        "log_buffers_lost": 0,
        "real_time_buffers_lost": 0,
    }
    assert "80" not in json.dumps(report["owned"])
    _assert_unaccepted(report)


def test_end_key_mismatch_is_not_joined():
    records = [
        life(OPCODE_START, ROOT_PID, 1, 0x111, ROOT_CREATION),
        life(OPCODE_END, ROOT_PID, 1, 0x222, ROOT_CREATION + 50),
        counter(ROOT_PID, 80, ROOT_CREATION + 1),
    ]
    report, _api, _job = run(records, total=1)
    assert report["owned"][0]["exit_observed"] is False
    assert report["owned"][0]["peak_working_set_bytes"] is None
    assert "exit_key_mismatch" in report["coverage"]["gaps"]
    assert "terminal_counter_unproven" in report["coverage"]["gaps"]
    assert report["coverage"]["status"] == "missing"


def test_counter_after_known_end_is_not_terminal():
    records = [
        life(OPCODE_START, ROOT_PID, 1, 0xC, ROOT_CREATION),
        life(OPCODE_END, ROOT_PID, 1, 0xC, ROOT_CREATION + 20),
        counter(ROOT_PID, 80, ROOT_CREATION + 1_000_000),
    ]
    report, _api, _job = run(records, total=1)
    assert report["owned"][0]["exit_observed"] is True
    assert report["owned"][0]["peak_working_set_bytes"] is None
    assert "terminal_counter_unproven" in report["coverage"]["gaps"]
    assert report["coverage"]["status"] == "missing"


def test_in_window_counter_survives_a_later_counter():
    records = [
        life(OPCODE_START, ROOT_PID, 1, 0xC, ROOT_CREATION),
        counter(ROOT_PID, 41, ROOT_CREATION + 1),
        life(OPCODE_END, ROOT_PID, 1, 0xC, ROOT_CREATION + 30),
        counter(ROOT_PID, 99, ROOT_CREATION + 10_000),
    ]
    report, _api, _job = run(records, total=1)
    assert report["owned"][0]["peak_working_set_bytes"] == 41
    assert report["coverage"]["status"] == "reconciled"
    assert report["coverage"]["gaps"] == []


def test_bridge_conversion_blocks_reconciliation():
    secret = r"C:\Secret\should-not-leak"
    seen = []

    def convert():
        raise RuntimeError(secret)

    bridge_event(convert, seen.append)
    assert seen == [{"bridge_diagnostic": "record_conversion"}]
    assert secret not in json.dumps(seen)
    records = generation(ROOT_PID, 1, 0xC, ROOT_CREATION, 5_600, 100)
    report, _api, _job = run(
        records,
        total=1,
        api_kwargs={"bridge_failure": True, "bridge_secret": secret},
    )
    assert "record_conversion_failed" in report["coverage"]["gaps"]
    assert report["coverage"]["status"] == "missing"
    text = json.dumps(report)
    assert secret not in text
    assert "should-not-leak" not in text
    _assert_unaccepted(report)


def test_post_cap_diagnostics_stay_bounded():
    api = FakeEtwApi([])
    observer = EtwLifetimeObserver(
        api,
        ready_seconds=0.2,
        drain_seconds=0.2,
        callback_limit=5,
        retain_limit=2,
    )
    for index in range(10):
        observer._on_event(life(OPCODE_START, index + 1, 0, index + 1, 1_000 + index))
    for index in range(_COUNT_SATURATION + 20):
        observer._on_event(record(99, b"", index))
        observer.note_gap(f"external-category-{index}-{'x' * 32}")
    report = observer.finish(None)
    assert "callbacks_exceeded" in report["coverage"]["gaps"]
    assert "retained_records_exceeded" in report["coverage"]["gaps"]
    assert report["limits"]["retained_records"] <= 2
    assert report["limits"]["callbacks"] == _COUNT_SATURATION
    assert report["limits"]["gap_counts"]["callbacks_exceeded"] == _COUNT_SATURATION
    assert report["limits"]["gap_counts"]["external_gap"] == _COUNT_SATURATION
    assert "external-category" not in json.dumps(report)
    assert len(report["limits"]["gap_counts"]) < 40
    assert len(report["coverage"]["gaps"]) < 40
    assert report["coverage"]["status"] == "missing"


def test_pending_close_keeps_callbacks_until_the_consumer_finishes():
    records = generation(ROOT_PID, 1, 0xC, ROOT_CREATION, ROOT_CREATION + 100, 80)
    api = FakeEtwApi(records, close_pending=True)
    observer = EtwLifetimeObserver(api, ready_seconds=1, drain_seconds=0.2)
    try:
        assert observer.start_before_root() is True
        observer.bind_root(ROOT_PID, ROOT_CREATION)
        report = observer.finish(snapshot(1))
        assert observer.callback_live is True
        assert api.callbacks_released is False
        assert "close_pending" in report["coverage"]["gaps"]
        assert "consumer_still_live" in report["coverage"]["gaps"]
        assert report["coverage"]["status"] == "missing"
        assert report["session"]["isolated_cleanup_process"] is False
        before = observer._callbacks
        api.on_event(counter(ROOT_PID, 5, ROOT_CREATION + 2))
        assert observer.callback_live is True
        assert api.callbacks_released is False
        assert observer._callbacks == before + 1
        api.unblock()
        assert observer.release_finished_consumer() is True
        assert observer.callback_live is False
        assert api.callbacks_released is True
        assert observer.finish(snapshot(1)) is report
        assert report["coverage"]["status"] == "missing"
        stops = list(api.stops)
        observer.close()
        assert api.stops == stops
    finally:
        api.unblock()
        observer.release_finished_consumer()


def test_failed_close_keeps_callbacks_while_the_consumer_is_live():
    records = generation(ROOT_PID, 1, 0xC, ROOT_CREATION, ROOT_CREATION + 100, 80)
    api = FakeEtwApi(records, close_error=True)
    observer = EtwLifetimeObserver(api, ready_seconds=1, drain_seconds=0.2)
    try:
        assert observer.start_before_root() is True
        observer.bind_root(ROOT_PID, ROOT_CREATION)
        report = observer.finish(snapshot(1))
        assert "close_failed" in report["coverage"]["gaps"]
        assert "consumer_still_live" in report["coverage"]["gaps"]
        assert "close_pending" not in report["coverage"]["gaps"]
        assert observer.callback_live is True
        assert api.callbacks_released is False
        assert report["coverage"]["status"] == "missing"
        api.on_event(counter(ROOT_PID, 5, ROOT_CREATION + 2))
        assert api.callbacks_released is False
    finally:
        api.unblock()
        observer.release_finished_consumer()


def test_failed_stop_retains_session_ownership():
    records = generation(ROOT_PID, 1, 0xC, ROOT_CREATION, 5_600, 100)
    report, api, _job = run(
        records,
        total=1,
        api_kwargs={"stop_ok": False, "finish_without_blocking": True},
    )
    assert api.stops == [101]
    assert api.closes_session == []
    assert api.session == 101
    assert "stop_failed" in report["coverage"]["gaps"]
    assert "session_still_owned" in report["coverage"]["gaps"]
    assert report["session"]["session_released"] is False
    assert report["session"]["stopped_existing_logger"] is False
    assert report["coverage"]["status"] == "missing"


def test_successful_stop_is_not_repeated():
    records = generation(ROOT_PID, 1, 0xC, ROOT_CREATION, 5_600, 100)
    api = FakeEtwApi(records)
    observer = EtwLifetimeObserver(api, ready_seconds=1, drain_seconds=1)
    assert observer.start_before_root() is True
    observer.bind_root(ROOT_PID, ROOT_CREATION)
    report = observer.finish(snapshot(1))
    observer.close()
    observer.close()
    assert report["coverage"]["status"] == "reconciled"
    assert report["coverage"]["gaps"] == []
    assert api.stops == [101]
    assert api.closes_trace == [202]
    assert api.closes_session == [101]
    assert observer.finish(snapshot(1)) is report
    source = inspect.getsource(EtwLifetimeObserver)
    assert "daemon" not in source


def test_close_trace_results_stay_explicit():
    assert interpret_close_trace(0) == {"ok": True, "code": "ok", "pending": False}
    pending = interpret_close_trace(7007)
    assert pending == {"ok": False, "code": "close_pending", "pending": True}
    assert interpret_close_trace(6) == {"ok": False, "code": "close_failed", "pending": False}
    assert "WinEtwApi(" not in inspect.getsource(interpret_close_trace)
    assert "WinEtwApi(" not in inspect.getsource(bridge_event)


class _Call:
    def __init__(self, function):
        self.function = function
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.function(*args)


def _ownership_api(*, start_code=0, stop_codes=(0,), block_consumer=False, close_code=0):
    """AdapterOwnership over a fake loader. No advapi32, ETW session, or workload."""
    stops = iter(stop_codes)

    def start(out_handle, _name, _properties):
        if start_code == 0:
            ctypes.cast(out_handle, ctypes.POINTER(ctypes.c_ulonglong)).contents.value = 101
        return start_code

    def process(*_args):
        library.consumer_thread = threading.current_thread()
        library.consumer_entered.set()
        try:
            if block_consumer:
                library.consumer_gate.wait(5)
            return 0
        finally:
            library.consumer_finished.set()

    library = type("Library", (), {})()
    library.StartTraceW = _Call(start)
    library.OpenTraceW = _Call(lambda _logfile: 202)
    library.ProcessTrace = _Call(process)
    library.StopTraceW = _Call(lambda *_args: next(stops, 0))
    library.CloseTrace = _Call(lambda *_args: close_code)
    library.consumer_gate = threading.Event()
    library.consumer_entered = threading.Event()
    library.consumer_finished = threading.Event()
    library.consumer_thread = None
    loads = []

    def load():
        loads.append(True)
        return library

    api = AdapterOwnership(load)

    def logfile(_on_event):
        api._callback = object()
        api._buffer_callback = object()
        api._logfile = ctypes.c_ulonglong(0)
        return api._logfile

    api._new_logfile = logfile
    return api, library, loads


def _capture(api, *, ready_seconds=1.0, drain_seconds=1.0):
    report = observe_owned_launch(
        FakeJob(snapshot(1)),
        api,
        ready_seconds=ready_seconds,
        drain_seconds=drain_seconds,
    )
    _assert_unaccepted(report)
    _assert_handle_free(report)
    return report


def _assert_handle_free(report):
    def walk(value):
        if isinstance(value, dict):
            assert not {"control_handle", "trace_handle", "private_owner"} & set(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(report)


def test_one_shot_keeps_known_cleanup_handles():
    api, library, loads = _ownership_api()
    assert api.start_session(session_request())["ok"] is True
    assert api.open_trace(SESSION_NAME, lambda _event: None)["ok"] is True
    callback = api._callback
    assert api.open_trace(SESSION_NAME, lambda _event: None)["ok"] is False
    assert api._callback is callback and len(library.OpenTraceW.calls) == 1
    for handle in (None, 999, True):
        assert api.stop_session(handle)["ok"] is False
        assert api.close_trace(handle)["ok"] is False
        assert api.close_session(handle)["ok"] is False
    assert not library.StopTraceW.calls and not library.CloseTrace.calls
    assert api.stop_session(101)["ok"] is True
    assert api.close_trace(202)["ok"] is True
    assert api.close_session(101)["ok"] is True
    assert api.start_session(session_request())["ok"] is False
    assert len(loads) == 1 and len(library.StartTraceW.calls) == 1
    for handle in (None, 999, True):
        assert api.stop_session(handle)["ok"] is False
        assert api.close_trace(handle)["ok"] is False
        assert api.close_session(handle)["ok"] is False
    assert api.stop_session(101)["ok"] is True
    assert api.close_trace(202)["ok"] is True
    assert len(library.StopTraceW.calls) == len(library.CloseTrace.calls) == 1


def test_failed_start_refuses_open_before_callbacks_or_open_trace():
    api, library, _loads = _ownership_api(start_code=183)
    assert api.start_session(session_request())["ok"] is False
    result = api.open_trace(SESSION_NAME, lambda _event: None)
    assert result["ok"] is False
    assert library.OpenTraceW.calls == []
    assert api._callback is None and api._buffer_callback is None and api._logfile is None


def test_first_open_after_stop_refuses_before_callbacks_or_open_trace():
    api, library, _loads = _ownership_api()
    assert api.start_session(session_request())["ok"] is True
    assert api.stop_session(101)["ok"] is True
    result = api.open_trace(SESSION_NAME, lambda _event: None)
    assert result["ok"] is False
    assert library.OpenTraceW.calls == []
    assert api._callback is None and api._buffer_callback is None and api._logfile is None


def test_foreign_or_null_consumer_does_not_signal_or_process():
    api, library, _loads = _ownership_api()
    assert api.start_session(session_request())["ok"] is True
    assert api.open_trace(SESSION_NAME, lambda _event: None)["ok"] is True
    for handle in (999, None):
        ready = []
        result = api.process_trace(handle, lambda: ready.append(handle))
        assert result["ok"] is False
        assert ready == []
        assert library.ProcessTrace.calls == []
    ready = []
    assert api.process_trace(202, lambda: ready.append(True))["ok"] is True
    assert ready == [True]
    assert len(library.ProcessTrace.calls) == 1


def test_refused_wrapper_preserves_the_pending_owner():
    api, library, _loads = _ownership_api(stop_codes=(5,))
    report = _capture(api)
    original = json.dumps(report, sort_keys=True)
    state = api.private_owner.snapshot()
    assert state["control_handle"] == 101 and state["recoverable"] is True
    assert state["isolated_cleanup_process"] is False
    _capture(api)
    state = api.private_owner.snapshot()
    assert state["control_handle"] == 101 and state["recoverable"] is True
    assert len(library.StartTraceW.calls) == len(library.StopTraceW.calls) == 1
    assert library.OpenTraceW.calls and len(library.OpenTraceW.calls) == 1
    assert json.dumps(report, sort_keys=True) == original
    _assert_handle_free(report)


def test_refused_wrapper_does_not_release_a_live_consumer():
    api, library, _loads = _ownership_api(block_consumer=True, close_code=7007)
    try:
        report = _capture(api, ready_seconds=1.0, drain_seconds=0.05)
        assert library.consumer_entered.wait(0.5)
        assert library.consumer_thread.is_alive()
        assert report["session"]["consumer_finished"] is False
        callback, buffer_callback, logfile = api._callback, api._buffer_callback, api._logfile
        assert callback is not None and buffer_callback is not None and logfile is not None
        _capture(api, ready_seconds=0.5, drain_seconds=0.05)
        assert library.consumer_thread.is_alive()
        assert api._callback is callback
        assert api._buffer_callback is buffer_callback
        assert api._logfile is logfile
        assert len(library.CloseTrace.calls) == 1
        assert len(library.ProcessTrace.calls) == 1
    finally:
        library.consumer_gate.set()
        if library.consumer_thread is not None:
            library.consumer_thread.join(1)
            assert not library.consumer_thread.is_alive()


def test_private_owner_reflects_completed_session_release():
    api, _library, _loads = _ownership_api(stop_codes=(5, 0))
    report = _capture(api)
    original = json.dumps(report, sort_keys=True)
    owner = api.private_owner
    assert owner.retry_stop(101)["ok"] is True
    assert api.close_session(101)["ok"] is True
    state = owner.snapshot()
    assert state["session_released"] is True
    assert state["session_outstanding"] is False
    assert state["recoverable"] is False
    assert state["isolated_cleanup_process"] is False
    assert json.dumps(report, sort_keys=True) == original
    _assert_handle_free(report)


def test_pending_close_completes_after_the_original_consumer_exits():
    api, library, _loads = _ownership_api(block_consumer=True, close_code=7007)
    try:
        report = _capture(api, ready_seconds=1.0, drain_seconds=0.05)
        original = json.dumps(report, sort_keys=True)
        assert library.consumer_entered.wait(0.5)
        assert library.consumer_thread.is_alive()
        callback = api._callback
        assert callback is not None
        owner = api.private_owner
        assert owner.snapshot()["close_pending"] is True
        assert owner.retry_close(202)["pending"] is True
        assert api._callback is callback
        assert len(library.CloseTrace.calls) == 1
        library.consumer_gate.set()
        library.consumer_thread.join(1)
        assert not library.consumer_thread.is_alive()
        assert api._callback is callback
        result = owner.retry_close(202)
        assert result["ok"] is True and result["pending"] is False
        assert len(library.CloseTrace.calls) == 1
        assert api._callback is None and api._buffer_callback is None and api._logfile is None
        state = owner.snapshot()
        assert state["close_ok"] is True
        assert state["close_pending"] is False
        assert state["trace_outstanding"] is False
        assert state["callback_outstanding"] is False
        assert state["consumer_completed"] is True
        assert state["isolated_cleanup_process"] is False
        assert json.dumps(report, sort_keys=True) == original
        _assert_handle_free(report)
    finally:
        library.consumer_gate.set()
        if library.consumer_thread is not None:
            library.consumer_thread.join(1)


def test_mismatched_parent_end_does_not_admit_a_later_child():
    def life_event(opcode, pid, parent, key, timestamp):
        return {
            "kind": "lifecycle",
            "opcode": opcode,
            "pid": pid,
            "parent_pid": parent,
            "unique_process_key": key,
            "timestamp": timestamp,
            "processor_index": 0,
            "exit_status": 0,
            "pointer_width": 8,
            "version": 2,
        }

    events = [
        life_event(OPCODE_START, 10, 1, 0xA, 5000),
        life_event(OPCODE_END, 10, 1, 0xB, 5100),
        life_event(OPCODE_START, 11, 10, 0xC, 5200),
        life_event(OPCODE_END, 11, 10, 0xC, 5300),
        {
            "kind": "counter",
            "opcode": OPCODE_PERFCTR,
            "pid": 11,
            "timestamp": 5250,
            "peak_working_set_bytes": 80,
        },
    ]
    result = resolve_owned(events, 10, 5000)
    assert [row["pid"] for row in result["rows"]] == [10]
    assert result["rows"][0]["peak_working_set_bytes"] is None
    assert {"exit_key_mismatch", "exit_missing"} <= set(result["gaps"])
