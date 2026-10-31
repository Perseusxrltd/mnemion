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
    abi_field_offsets,
    consumer_layout_sizes,
    counter_payload_size,
    decode_record,
    host_offset,
    native_api_loaded,
    native_session_starts,
    observe_owned_launch,
    session_request,
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
    ):
        self.records = list(records or [])
        self.start_code = start_code
        self.open_ok = open_ok
        self.stop_unblocks = stop_unblocks
        self.raise_in_process = raise_in_process
        self.delay_ready = delay_ready
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
        if self.stop_unblocks:
            self._stop.wait(5)
        else:
            self._closed.wait(5)
        return {"ok": True, "code": "ok"}

    def stop_session(self, session_handle):
        self.stops.append(session_handle)
        if self.stop_unblocks:
            self._stop.set()
        return {"ok": True, "code": "ok", "loss": dict(self.loss)}

    def close_trace(self, trace_handle):
        self.closes_trace.append(trace_handle)
        self._closed.set()
        self._stop.set()

    def close_session(self, session_handle):
        self.closes_session.append(session_handle)
        self.session = None


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


def test_single_root_binds_when_the_filetime_differs_from_job_creation():
    records = generation(ROOT_PID, 1, 0xC, 1_111, 3_000, 80, header_pid=0xFFFFFFFF)
    report, _api, _job = run(records, total=1, creation=2_222)
    row = report["owned"][0]
    assert row["identity"] == "10:2222"
    assert row["etw_start_filetime"] == 1_111
    assert row["job_creation"] == 2_222
    assert report["coverage"]["pid_reuse_resolved_by_exact_creation"] is False
    assert report["coverage"]["status"] == "reconciled"


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
    assert opened.stops == [101, 101]
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
