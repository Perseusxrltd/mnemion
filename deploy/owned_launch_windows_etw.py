"""Owned-process exit working-set candidates from a private ETW system logger.

Process_V2 opcode 32 (PerfCtr) is logged when a process ends and carries
PeakWorkingSetSize as a pointer-width SizeT. Opcode 33 (PerfCtrRundown) is the
counter rundown at session start, not an exit peak. The classic counter
payload has a PID and no creation time. UniqueProcessKey is the kernel object
address, so it can be reused. The optional Process Start Key is not read and
is not treated as the payload's target.

This module does not replace WindowsJobBackend, does not change
start_owned_launch, and does not start a trace on import. Job CPU and the job
census stay authoritative. PeakProcessMemoryUsed and pagefile figures stay
commit charge. resource_acceptance and budget comparison stay false.

Native ETW is not invoked by tests. WinEtwApi is constructed only by an
explicit caller after review.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading

from deploy.owned_launch_accounting import (
    ADDITIONAL_RSS_BUDGET_BYTES,
    BUDGET_STATUS,
    CPU_BUDGET_ONE_CORE_FRACTION,
    MAX_LEDGER,
    OwnedLaunchError,
    OwnedLaunchUnsupported,
)


# SDK 10.0.26100.0 evntrace.h / evntcons.h / wmistr.h. Windows is LLP64:
# DWORD stays 32-bit and SIZE_T follows the event pointer width.
EVENT_TRACE_FLAG_PROCESS = 0x00000001
EVENT_TRACE_FLAG_PROCESS_COUNTERS = 0x00000008
EVENT_TRACE_REAL_TIME_MODE = 0x00000100
EVENT_TRACE_SYSTEM_LOGGER_MODE = 0x02000000
EVENT_TRACE_NO_PER_PROCESSOR_BUFFERING = 0x10000000
WNODE_FLAG_TRACED_GUID = 0x00020000
EVENT_TRACE_CONTROL_STOP = 1
PROCESS_TRACE_MODE_REAL_TIME = 0x00000100
PROCESS_TRACE_MODE_RAW_TIMESTAMP = 0x00001000
PROCESS_TRACE_MODE_EVENT_RECORD = 0x10000000
EVENT_HEADER_FLAG_32_BIT_HEADER = 0x0020
EVENT_HEADER_FLAG_64_BIT_HEADER = 0x0040
EVENT_HEADER_FLAG_PROCESSOR_INDEX = 0x0200
EVENT_HEADER_EXT_TYPE_PROCESS_START_KEY = 0x000D
CLIENT_CONTEXT_QPC = 1

OPCODE_START = 1
OPCODE_END = 2
OPCODE_DCSTART = 3
OPCODE_DCEND = 4
OPCODE_PERFCTR = 32
OPCODE_PERFCTR_RUNDOWN = 33
OPCODE_DEFUNCT = 39

PROCESS_PROVIDER_GUID = "3d6fa8d0-fe05-11d0-9dda-00c04fd7ba7c"
SYSTEM_TRACE_CONTROL_GUID = "9e814aad-3204-11d2-9a82-006008a86939"
KERNEL_LOGGER_NAME = "NT Kernel Logger"
SESSION_NAME = "Mnemion Owned Launch ETW"

BUFFER_SIZE_KB = 16
MINIMUM_BUFFERS = 2
MAXIMUM_BUFFERS = 16
FLUSH_TIMER_SECONDS = 1
MAX_RETAINED_EVENTS = 4096
MAX_CALLBACKS = 16384
_COUNTER_UINT32S = 4
_COUNTER_SIZETS = 11
_PEAK_WORKING_SET_INDEX = 1
_LIFE_UINT32S = 4

_METHOD = "windows_etw_process_counter"
_PRODUCTION_METHOD = "windows_job_before_resume"

native_session_starts = 0
native_api_loaded = False


def host_offset(offset: int, pointers: int, pointer_width: int) -> int:
    """32-bit MOF offset plus the extra bytes each earlier pointer grows by.

    TraceEvent HostOffset is `offset + (PointerSize - 4) * numPointers`.
    SIZE_T is pointer-wide. A Windows DWORD does not grow with the pointer.
    """
    if pointer_width not in (4, 8) or pointers < 0 or offset < 0:
        raise OwnedLaunchError("invalid_layout")
    return offset + (pointer_width - 4) * pointers


def counter_payload_size(pointer_width: int) -> int:
    return (_COUNTER_UINT32S * 4) + (_COUNTER_SIZETS * pointer_width)


def session_request() -> dict:
    """The only session shape this component is allowed to start."""
    enable = EVENT_TRACE_FLAG_PROCESS | EVENT_TRACE_FLAG_PROCESS_COUNTERS
    mode = (
        EVENT_TRACE_REAL_TIME_MODE
        | EVENT_TRACE_SYSTEM_LOGGER_MODE
        | EVENT_TRACE_NO_PER_PROCESSOR_BUFFERING
    )
    return {
        "session_name": SESSION_NAME,
        "rejected_session_name": KERNEL_LOGGER_NAME,
        "guid_is_null": True,
        "rejected_guid": SYSTEM_TRACE_CONTROL_GUID,
        "log_file_name": None,
        "etl_file": False,
        "real_time": True,
        "system_logger": True,
        "no_per_processor_buffering": True,
        "enable_flags": enable,
        "log_file_mode": mode,
        "buffer_size_kb": BUFFER_SIZE_KB,
        "minimum_buffers": MINIMUM_BUFFERS,
        "maximum_buffers": MAXIMUM_BUFFERS,
        "flush_timer_seconds": FLUSH_TIMER_SECONDS,
        "client_context": CLIENT_CONTEXT_QPC,
        "raw_timestamp": False,
        "process_start_key_enabled": False,
        "privilege_escalation": False,
        "stop_existing_session": False,
    }


def pointer_width_from_flags(flags: int) -> int | None:
    if type(flags) is not int:
        return None
    wide = flags & EVENT_HEADER_FLAG_64_BIT_HEADER
    narrow = flags & EVENT_HEADER_FLAG_32_BIT_HEADER
    if wide and not narrow:
        return 8
    if narrow and not wide:
        return 4
    return None


def _u32(payload: bytes, offset: int) -> int | None:
    if offset < 0 or offset + 4 > len(payload):
        return None
    return int.from_bytes(payload[offset : offset + 4], "little", signed=False)


def _i32(payload: bytes, offset: int) -> int | None:
    if offset < 0 or offset + 4 > len(payload):
        return None
    return int.from_bytes(payload[offset : offset + 4], "little", signed=True)


def _usize(payload: bytes, offset: int, pointer_width: int) -> int | None:
    if offset < 0 or offset + pointer_width > len(payload):
        return None
    return int.from_bytes(payload[offset : offset + pointer_width], "little", signed=False)


def decode_record(record: dict) -> dict:
    """Decode one already-copied numeric record. Payload bytes are not kept."""
    if type(record) is not dict:
        return {"disposition": "malformed", "reason": "record_type"}
    provider = record.get("provider")
    if provider is not None and provider != PROCESS_PROVIDER_GUID:
        return {"disposition": "ignore", "reason": "other_provider"}
    opcode = record.get("opcode")
    version = record.get("version")
    if type(opcode) is not int or type(version) is not int:
        return {"disposition": "malformed", "reason": "opcode_or_version"}
    if opcode not in (
        OPCODE_START,
        OPCODE_END,
        OPCODE_DCSTART,
        OPCODE_DCEND,
        OPCODE_PERFCTR,
        OPCODE_PERFCTR_RUNDOWN,
        OPCODE_DEFUNCT,
    ):
        return {"disposition": "ignore", "reason": "other_opcode"}
    width = pointer_width_from_flags(record.get("flags"))
    if width is None:
        return {"disposition": "malformed", "reason": "pointer_width"}
    payload = record.get("payload")
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        return {"disposition": "malformed", "reason": "payload_type"}
    payload = bytes(payload)
    timestamp = record.get("timestamp")
    if type(timestamp) is not int or timestamp < 0:
        return {"disposition": "malformed", "reason": "timestamp"}
    processor = record.get("processor_index")
    if processor is not None and (type(processor) is not int or processor < 0):
        return {"disposition": "malformed", "reason": "processor"}
    # Present or absent, the extended Process Start Key is not a join input.
    start_key_present = record.get("process_start_key_present") is True
    if opcode in (OPCODE_PERFCTR, OPCODE_PERFCTR_RUNDOWN):
        return _decode_counter(
            opcode, version, width, payload, timestamp, processor, start_key_present
        )
    return _decode_lifecycle(
        opcode, version, width, payload, timestamp, processor, start_key_present
    )


def _decode_counter(opcode, version, width, payload, timestamp, processor, start_key_present):
    if version < 2 or version > 255:
        return {"disposition": "malformed", "reason": "counter_version"}
    needed = counter_payload_size(width)
    if version == 2 and len(payload) != needed:
        return {"disposition": "malformed", "reason": "counter_length"}
    if version > 2 and len(payload) < needed:
        return {"disposition": "malformed", "reason": "counter_truncated"}
    pid = _u32(payload, 0)
    peak_at = host_offset(20, _PEAK_WORKING_SET_INDEX, width)
    peak = _usize(payload, peak_at, width)
    if pid is None or peak is None:
        return {"disposition": "malformed", "reason": "counter_fields"}
    return {
        "disposition": "event",
        "kind": "counter",
        "opcode": opcode,
        "version": version,
        "pointer_width": width,
        "pid": pid,
        "peak_working_set_bytes": peak,
        "timestamp": timestamp,
        "processor_index": processor,
        "process_start_key_present": start_key_present,
        "process_start_key_used": False,
        "header_pid_used": False,
    }


def _decode_lifecycle(opcode, version, width, payload, timestamp, processor, start_key_present):
    # Version 2 places UniqueProcessKey at offset 0. Later versions keep that
    # prefix and add fields after ExitStatus, which this decoder does not read.
    if version < 2 or version > 255:
        return {"disposition": "malformed", "reason": "lifecycle_version"}
    if len(payload) < width + (_LIFE_UINT32S * 4):
        return {"disposition": "malformed", "reason": "lifecycle_truncated"}
    key = _usize(payload, 0, width)
    pid = _u32(payload, host_offset(4, 1, width))
    parent = _u32(payload, host_offset(8, 1, width))
    exit_status = _i32(payload, host_offset(16, 1, width))
    if key is None or pid is None or parent is None or exit_status is None:
        return {"disposition": "malformed", "reason": "lifecycle_fields"}
    return {
        "disposition": "event",
        "kind": "lifecycle",
        "opcode": opcode,
        "version": version,
        "pointer_width": width,
        "pid": pid,
        "parent_pid": parent,
        "unique_process_key": key,
        "exit_status": exit_status,
        "timestamp": timestamp,
        "processor_index": processor,
        "process_start_key_present": start_key_present,
        "process_start_key_used": False,
        "header_pid_used": False,
    }


def _group(events: list[dict], opcode: int) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for event in events:
        if event.get("opcode") != opcode:
            continue
        grouped.setdefault(event["pid"], []).append(event)
    return grouped


def _equal_timestamp(events: list[dict]) -> bool:
    seen = set()
    for event in events:
        stamp = event["timestamp"]
        if stamp in seen:
            return True
        seen.add(stamp)
    return False


def _cross_cpu(left: int | None, right: int | None) -> bool | None:
    # True only when both indexes exist and differ. A missing index is not
    # evidence of another CPU: NO_PER_PROCESSOR_BUFFERING can omit it.
    if type(left) is int and type(right) is int and left != right:
        return True
    return None


def resolve_owned(events: list[dict], root_pid: int | None, root_creation: int | None) -> dict:
    """Join lifecycle generations after the trace has drained.

    Arrival order is not a key. Equal timestamps stay unresolved. A counter
    PID binds only when one owned generation's open time window contains it.
    """
    gaps: list[str] = []
    ambiguities: list[dict] = []
    births = [event for event in events if event.get("kind") == "lifecycle" and event["opcode"] == OPCODE_START]
    ends = [event for event in events if event.get("kind") == "lifecycle" and event["opcode"] == OPCODE_END]
    counters = [
        event
        for event in events
        if event.get("kind") == "counter" and event["opcode"] == OPCODE_PERFCTR
    ]
    rundown = [
        event
        for event in events
        if event.get("kind") == "counter" and event["opcode"] == OPCODE_PERFCTR_RUNDOWN
    ]
    generations = _pair_generations(births, ends, gaps, ambiguities)
    root, reuse_resolved = _select_root(generations, root_pid, root_creation, gaps, ambiguities)
    owned = _own_descendants(generations, root, gaps, ambiguities)
    _assign_counters(owned, generations, counters, gaps, ambiguities)
    rows = [_public_row(generation, root, root_creation) for generation in owned]
    return {
        "rows": rows,
        "gaps": gaps,
        "ambiguities": ambiguities,
        "births": len(owned),
        "exits": sum(1 for row in rows if row["exit_observed"] is True),
        "terminal_counters": sum(1 for row in rows if row["terminal_counter_opcode32"] is True),
        "opcode33_ignored": len(rundown),
        "pid_reuse_resolved_by_exact_creation": reuse_resolved,
        "process_start_key_used": False,
    }


def _pair_generations(births, ends, gaps, ambiguities) -> list[dict]:
    generations = []
    births_by_pid = _group(births, OPCODE_START)
    ends_by_pid = _group(ends, OPCODE_END)
    for pid in births_by_pid:
        group = births_by_pid[pid]
        if _equal_timestamp(group):
            gaps.append("equal_time")
            gaps.append("reused_pid")
            for birth in group:
                ambiguities.append(
                    {
                        "kind": "equal_time_birth",
                        "pid": pid,
                        "timestamp": birth["timestamp"],
                        "processor_index": birth["processor_index"],
                        "cross_cpu": None,
                    }
                )
                generations.append(_generation(birth, None, birth_ambiguous=True))
            continue
        ordered = sorted(group, key=lambda event: event["timestamp"])
        pid_ends = list(ends_by_pid.get(pid, []))
        for index, birth in enumerate(ordered):
            next_stamp = None if index + 1 == len(ordered) else ordered[index + 1]["timestamp"]
            window = []
            boundary = []
            for end in pid_ends:
                stamp = end["timestamp"]
                if stamp == birth["timestamp"] or (next_stamp is not None and stamp == next_stamp):
                    boundary.append(end)
                elif stamp > birth["timestamp"] and (next_stamp is None or stamp < next_stamp):
                    window.append(end)
            chosen = None
            exit_ambiguous = False
            if len(window) == 1 and not boundary:
                chosen = window[0]
            elif boundary or len(window) > 1:
                exit_ambiguous = True
                gaps.append("equal_time" if boundary else "reused_pid")
                ambiguities.append(
                    {
                        "kind": "exit_unqualified",
                        "pid": pid,
                        "timestamp": birth["timestamp"],
                        "candidates": len(window) + len(boundary),
                    }
                )
            generations.append(
                _generation(birth, chosen, birth_ambiguous=False, exit_ambiguous=exit_ambiguous)
            )
    return generations


def _generation(
    birth: dict,
    end: dict | None,
    *,
    birth_ambiguous: bool,
    exit_ambiguous: bool = False,
) -> dict:
    return {
        "birth": birth,
        "end": end,
        "birth_ambiguous": birth_ambiguous,
        "exit_ambiguous": exit_ambiguous,
        "owned": False,
        "rejected": False,
        "parent_generation": None,
        "counter": None,
        "counter_state": None,
    }


def _select_root(generations, root_pid, root_creation, gaps, ambiguities):
    if type(root_pid) is not int or type(root_creation) is not int or not 0 < root_pid < 2**32:
        gaps.append("launch_identity_missing")
        return None, False
    candidates = [item for item in generations if item["birth"]["pid"] == root_pid]
    if not candidates:
        gaps.append("root_unobserved")
        return None, False
    clear = [item for item in candidates if item["birth_ambiguous"] is not True]
    if len(clear) == 1 and len(candidates) == 1:
        return clear[0], False
    exact = [item for item in clear if item["birth"]["timestamp"] == root_creation]
    if len(exact) == 1:
        return exact[0], True
    gaps.append("root_ambiguous")
    gaps.append("reused_pid")
    ambiguities.append(
        {
            "kind": "root_pid_reuse",
            "pid": root_pid,
            "candidates": len(candidates),
            "exact_creation_matches": len(exact),
        }
    )
    return None, False


def _inside(child: dict, parent: dict) -> str:
    start = child["birth"]["timestamp"]
    parent_start = parent["birth"]["timestamp"]
    parent_end = None if parent["end"] is None else parent["end"]["timestamp"]
    if start == parent_start or (parent_end is not None and start == parent_end):
        return "equal"
    if start <= parent_start:
        return "outside"
    if parent_end is not None and start >= parent_end:
        return "outside"
    return "inside"


def _own_descendants(generations, root, gaps, ambiguities) -> list[dict]:
    if root is None:
        return []
    root["owned"] = True
    root["role"] = "root"
    owned = [root]
    pending = [
        item
        for item in generations
        if item is not root and item["birth_ambiguous"] is not True
    ]
    while True:
        added = False
        still = []
        for child in pending:
            strict = []
            equal = []
            for parent in owned:
                if parent["exit_ambiguous"] is True:
                    continue
                if child["birth"]["parent_pid"] != parent["birth"]["pid"]:
                    continue
                relation = _inside(child, parent)
                if relation == "inside":
                    strict.append(parent)
                elif relation == "equal":
                    equal.append(parent)
            if len(strict) == 1 and not equal:
                child["owned"] = True
                child["role"] = "descendant"
                child["parent_generation"] = strict[0]
                owned.append(child)
                added = True
                continue
            if equal or len(strict) > 1:
                child["rejected"] = True
                gaps.append("ambiguous_parent")
                if equal:
                    gaps.append("equal_time")
                sample = equal[0] if equal else strict[0]
                ambiguities.append(
                    {
                        "kind": "parent_edge",
                        "pid": child["birth"]["pid"],
                        "parent_pid": child["birth"]["parent_pid"],
                        "timestamp": child["birth"]["timestamp"],
                        "equal_time": bool(equal),
                        "cross_cpu": _cross_cpu(
                            child["birth"]["processor_index"],
                            sample["birth"]["processor_index"],
                        ),
                    }
                )
                continue
            still.append(child)
        pending = still
        if not added:
            break
    for generation in owned:
        if generation["end"] is None:
            gaps.append("exit_missing")
    return owned


def _assign_counters(owned, generations, counters, gaps, ambiguities) -> None:
    for generation in owned:
        pid = generation["birth"]["pid"]
        start = generation["birth"]["timestamp"]
        later = [
            item["birth"]["timestamp"]
            for item in generations
            if item["birth"]["pid"] == pid and item["birth"]["timestamp"] > start
        ]
        next_stamp = min(later) if later else None
        window = []
        boundary = []
        for counter in counters:
            if counter["pid"] != pid:
                continue
            stamp = counter["timestamp"]
            if stamp == start or (next_stamp is not None and stamp == next_stamp):
                boundary.append(counter)
            elif stamp > start and (next_stamp is None or stamp < next_stamp):
                window.append(counter)
        if len(window) == 1 and not boundary:
            generation["counter"] = window[0]
            generation["counter_state"] = "opcode32"
            continue
        generation["counter_state"] = "unqualified" if window or boundary else "missing"
        if window or boundary:
            gaps.append("terminal_counter_unqualified")
            ambiguities.append(
                {
                    "kind": "terminal_counter",
                    "pid": pid,
                    "timestamp": start,
                    "candidates": len(window) + len(boundary),
                    "suppressed": True,
                }
            )
        else:
            gaps.append("terminal_counter_missing")


def _identity(generation: dict, root: dict | None, root_creation: int | None) -> str:
    pid = generation["birth"]["pid"]
    if generation is root and type(root_creation) is int:
        return f"{pid}:{root_creation}"
    return f"{pid}:etw:{generation['birth']['timestamp']}"


def _public_row(generation: dict, root: dict | None, root_creation: int | None) -> dict:
    birth = generation["birth"]
    end = generation["end"]
    counter = generation["counter"]
    parent = generation.get("parent_generation")
    peak = None if counter is None else counter["peak_working_set_bytes"]
    return {
        "identity": _identity(generation, root, root_creation),
        "role": generation.get("role"),
        "pid": birth["pid"],
        "parent_pid": None if parent is None else parent["birth"]["pid"],
        "parent_identity": None if parent is None else _identity(parent, root, root_creation),
        "job_creation": root_creation if generation is root else None,
        "etw_start_filetime": birth["timestamp"],
        "etw_end_filetime": None if end is None else end["timestamp"],
        "exit_observed": end is not None,
        "exit_status": None if end is None else end["exit_status"],
        "unique_process_key": birth["unique_process_key"],
        "unique_process_key_is_generation_key": False,
        "process_start_key_used": False,
        "peak_working_set_bytes": peak,
        "terminal_counter_opcode32": counter is not None,
        "opcode33_used_as_terminal": False,
        "pointer_width": birth["pointer_width"],
        "event_version": birth["version"],
    }


def _dedupe(items: list[str]) -> list[str]:
    return sorted(set(items))


def reconcile(resolved: dict, snapshot: dict | None, session: dict) -> dict:
    gaps = list(resolved["gaps"])
    gaps.extend(session.get("gaps") or [])
    kernel = None if type(snapshot) is not dict else snapshot.get("kernel")
    total = None
    active = None
    if type(kernel) is not dict:
        gaps.append("job_census_unavailable")
    else:
        total = kernel.get("total_processes")
        active = kernel.get("active_processes")
        if type(total) is not int or type(active) is not int:
            gaps.append("job_census_unavailable")
        else:
            if active != 0:
                gaps.append("job_active_processes")
            if total != resolved["births"]:
                gaps.append("census_births")
            if resolved["exits"] != resolved["births"]:
                gaps.append("census_exits")
            if resolved["terminal_counters"] != resolved["births"]:
                gaps.append("census_terminal_counters")
    loss = session.get("loss") or {}
    if session.get("started") is True:
        for name in ("events_lost", "log_buffers_lost", "real_time_buffers_lost"):
            value = loss.get(name)
            if value != 0:
                gaps.append(name)
        if session.get("stop_ok") is not True or session.get("drain_ok") is not True:
            gaps.append("stop_or_drain_failed")
    cpu = None if type(snapshot) is not dict else snapshot.get("cpu_microseconds")
    if type(cpu) is not int or cpu < 0:
        cpu = None
    gaps = _dedupe(gaps)
    reconciled = not gaps
    commit_process = None if type(kernel) is not dict else kernel.get("peak_process_commit_bytes")
    commit_job = None if type(kernel) is not dict else kernel.get("peak_job_commit_bytes")
    return {
        "qualification": "unqualified",
        "resource_acceptance": False,
        "budget_comparison_allowed": False,
        "budget": {
            "additional_rss_bytes_per_process": ADDITIONAL_RSS_BUDGET_BYTES,
            "cpu_one_core_fraction": CPU_BUDGET_ONE_CORE_FRACTION,
            "status": BUDGET_STATUS,
            "compared": False,
        },
        "platform_method": _METHOD,
        "production_method_unchanged": _PRODUCTION_METHOD,
        "production_accounting_switched": False,
        "cpu_authority": "windows_job",
        "lifetime_cpu_microseconds": cpu,
        "working_set_candidate": "etw_opcode32_peak_working_set_bytes",
        "peak_working_set_unit": "bytes_candidate",
        "native_unit_corroboration": "unrun",
        "pagefile_and_job_peak_are_commit": True,
        "job_peak_process_commit_bytes": commit_process,
        "job_peak_job_commit_bytes": commit_job,
        "commit_counters_are_working_set": False,
        "rss_component_breakdown": False,
        "proves_8mib_or_half_percent": False,
        "observer_overhead": {
            "kind": "system_logger_realtime",
            "measured": False,
            "disclosed": True,
            "buffer_size_kb": BUFFER_SIZE_KB,
            "minimum_buffers": MINIMUM_BUFFERS,
            "maximum_buffers": MAXIMUM_BUFFERS,
            "no_per_processor_buffering": True,
            "processor_index_may_be_omitted": True,
            "effects": [
                "kernel_process_and_counter_events",
                "session_buffers_reserved",
                "not_a_debug_heap",
                "not_a_debugger_hold",
                "sysconfig_events_may_arrive_and_are_discarded",
            ],
        },
        "architectures": {
            "abi": "windows_llp64",
            "decode_pointer_width": "event_header",
            "x64_and_arm64_sizet_bytes": 8,
            "native_emission_verified": False,
            "wow64_payload_width_honored": True,
        },
        "coverage": {
            "status": "reconciled" if reconciled else "missing",
            "births": resolved["births"],
            "exits": resolved["exits"],
            "terminal_counters": resolved["terminal_counters"],
            "job_total_processes": total,
            "job_active_processes": active,
            "opcode33_ignored": resolved["opcode33_ignored"],
            "pid_reuse_resolved_by_exact_creation": resolved[
                "pid_reuse_resolved_by_exact_creation"
            ],
            "gaps": gaps,
        },
        "ambiguities": resolved["ambiguities"],
        "owned": resolved["rows"],
        "loss": {
            "events_lost": loss.get("events_lost"),
            "log_buffers_lost": loss.get("log_buffers_lost"),
            "real_time_buffers_lost": loss.get("real_time_buffers_lost"),
        },
        "session": {
            "name": SESSION_NAME,
            "real_time": True,
            "etl_file": False,
            "stop_ok": session.get("stop_ok") is True,
            "drain_ok": session.get("drain_ok") is True,
            "stopped_existing_logger": False,
            "privilege_escalated": False,
        },
        "limits": {
            "max_retained_events": MAX_RETAINED_EVENTS,
            "max_callbacks": MAX_CALLBACKS,
            "max_owned": MAX_LEDGER,
            "retained_records": session.get("retained_records"),
            "callbacks": session.get("callbacks"),
        },
    }


class EtwLifetimeObserver:
    """Collect numeric process events, then resolve them after a full drain."""

    def __init__(self, api, *, ready_seconds: float = 2.0, drain_seconds: float = 5.0):
        if type(ready_seconds) not in (int, float) or type(drain_seconds) not in (int, float):
            raise OwnedLaunchError("invalid_bound")
        if ready_seconds <= 0 or drain_seconds <= 0:
            raise OwnedLaunchError("invalid_bound")
        self._api = api
        self._ready_seconds = float(ready_seconds)
        self._drain_seconds = float(drain_seconds)
        self._lock = threading.Lock()
        self._events: list[dict] = []
        self._gaps: list[str] = []
        self._callbacks = 0
        self._callback_live = False
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._session = None
        self._trace = None
        self._root_pid = None
        self._root_creation = None
        self._process_result = None
        self._started = False
        self._finished = False
        self._closed = False
        self._report = None
        self._request = session_request()

    @property
    def callback_live(self) -> bool:
        return self._callback_live

    @property
    def request(self) -> dict:
        return dict(self._request)

    def start_before_root(self) -> bool:
        if self._started or self._closed:
            self._gaps.append("session_not_started")
            return False
        started = self._api.start_session(self._request)
        if type(started) is not dict or started.get("ok") is not True:
            code = None if type(started) is not dict else started.get("code")
            if code == "already_exists":
                self._gaps.append("session_exists_not_stopped")
            elif code == "access_denied":
                self._gaps.append("access_denied")
            else:
                self._gaps.append("session_not_started")
            return False
        self._session = started.get("handle")
        opened = self._api.open_trace(self._request["session_name"], self._on_event)
        if type(opened) is not dict or opened.get("ok") is not True:
            self._gaps.append("open_trace_failed")
            self._stop_owned_session()
            return False
        self._trace = opened.get("handle")
        self._callback_live = True
        self._thread = threading.Thread(target=self._consume, name="mnemion-etw-consume")
        self._thread.start()
        if not self._ready.wait(self._ready_seconds):
            self._gaps.append("consumer_not_ready")
            self._stop_owned_session()
            self._join_consumer(self._drain_seconds)
            return False
        self._started = True
        return True

    def bind_root(self, pid: int, creation: int) -> None:
        if type(pid) is not int or type(creation) is not int or not 0 < pid < 2**32 or creation < 0:
            self._gaps.append("launch_identity_missing")
            return
        self._root_pid = pid
        self._root_creation = creation

    def note_gap(self, code: str) -> None:
        self._gaps.append(code)

    def finish(self, snapshot: dict | None) -> dict:
        if self._report is not None:
            return self._report
        self._finished = True
        stop_ok, drain_ok, loss = self._drain()
        retained = list(self._events)
        resolved = resolve_owned(retained, self._root_pid, self._root_creation)
        if len(resolved["rows"]) > MAX_LEDGER:
            self._gaps.append("retained_records_exceeded")
            resolved = dict(resolved)
            resolved["rows"] = []
            resolved["births"] = 0
            resolved["exits"] = 0
            resolved["terminal_counters"] = 0
            resolved["gaps"] = list(resolved["gaps"]) + ["retained_records_exceeded"]
        session = {
            "gaps": list(self._gaps),
            "loss": loss,
            "started": self._started,
            "stop_ok": stop_ok,
            "drain_ok": drain_ok,
            "retained_records": len(retained),
            "callbacks": self._callbacks,
        }
        self._report = reconcile(resolved, snapshot, session)
        self._release()
        self._closed = True
        return self._report

    def close(self) -> None:
        if self._closed:
            return
        if self._report is None:
            self.finish(None)
        self._release()
        self._closed = True

    def _consume(self) -> None:
        try:
            self._process_result = self._api.process_trace(self._trace, self._ready.set)
        except Exception:
            with self._lock:
                self._gaps.append("callback_failed")
            self._ready.set()
        finally:
            self._ready.set()

    def _on_event(self, record: dict) -> None:
        try:
            self._accept(record)
        except Exception:
            with self._lock:
                self._gaps.append("callback_failed")

    def _accept(self, record: dict) -> None:
        with self._lock:
            self._callbacks += 1
            if self._callbacks > MAX_CALLBACKS:
                self._gaps.append("callbacks_exceeded")
                return
            if len(self._events) >= MAX_RETAINED_EVENTS:
                self._gaps.append("retained_records_exceeded")
                return
        decoded = decode_record(record)
        if decoded.get("disposition") == "ignore":
            return
        if decoded.get("disposition") != "event":
            with self._lock:
                self._gaps.append("parser_failed")
            return
        kept = dict(decoded)
        kept.pop("disposition", None)
        with self._lock:
            if len(self._events) >= MAX_RETAINED_EVENTS:
                self._gaps.append("retained_records_exceeded")
                return
            self._events.append(kept)

    def _drain(self) -> tuple[bool, bool, dict]:
        if self._session is None and not self._started:
            return False, False, {
                "events_lost": None,
                "log_buffers_lost": None,
                "real_time_buffers_lost": None,
            }
        stopped = self._stop_owned_session()
        joined = self._join_consumer(self._drain_seconds)
        if not joined:
            self._gaps.append("deadline_exceeded")
            self._close_trace()
            joined = self._join_consumer(self._drain_seconds)
        loss = stopped.get("loss") if type(stopped) is dict else None
        if type(loss) is not dict:
            loss = {
                "events_lost": None,
                "log_buffers_lost": None,
                "real_time_buffers_lost": None,
            }
        stop_ok = type(stopped) is dict and stopped.get("ok") is True
        process_ok = type(self._process_result) is dict and self._process_result.get("ok") is True
        drain_ok = joined and process_ok and stop_ok
        if not stop_ok:
            self._gaps.append("stop_failed")
        if not process_ok or not joined:
            self._gaps.append("drain_failed")
        return stop_ok, drain_ok, loss

    def _stop_owned_session(self) -> dict:
        handle = self._session
        if handle is None:
            return {"ok": False, "loss": {}}
        if self._api is None:
            return {"ok": False, "loss": {}}
        try:
            result = self._api.stop_session(handle)
        except Exception:
            result = {"ok": False, "loss": {}}
        if type(result) is not dict:
            result = {"ok": False, "loss": {}}
        return result

    def _join_consumer(self, seconds: float) -> bool:
        thread = self._thread
        if thread is None:
            return True
        if not thread.is_alive() and thread.ident is None:
            return True
        thread.join(seconds)
        return not thread.is_alive()

    def _close_trace(self) -> None:
        handle = self._trace
        self._trace = None
        if handle is None or self._api is None:
            return
        try:
            self._api.close_trace(handle)
        except Exception:
            self._gaps.append("callback_failed")

    def _release(self) -> None:
        self._close_trace()
        handle = self._session
        self._session = None
        if handle is not None and self._api is not None:
            try:
                self._api.close_session(handle)
            except Exception:
                self._gaps.append("stop_failed")
        self._callback_live = False
        self._join_consumer(0.1)


def observe_owned_launch(job, api, *, ready_seconds: float = 2.0, drain_seconds: float = 5.0) -> dict:
    """Start ETW, then spawn through the existing job object.

    `job` is a WindowsJobBackend, or a test double with the same spawn,
    root_pid, root_creation, wait_until_drained, and snapshot surface.
    start_owned_launch is not called and is not switched over.
    """
    observer = EtwLifetimeObserver(api, ready_seconds=ready_seconds, drain_seconds=drain_seconds)
    try:
        if not observer.start_before_root():
            return observer.finish(None)
        job.spawn()
        pid = getattr(job, "root_pid", None)
        creation = getattr(job, "root_creation", None)
        if type(pid) is not int or type(creation) is not int:
            observer.note_gap("launch_identity_missing")
        else:
            observer.bind_root(pid, creation)
        drained = job.wait_until_drained(drain_seconds) is True
        if not drained:
            observer.note_gap("job_active_processes")
        snapshot = job.snapshot()
        if type(snapshot) is not dict:
            snapshot = {}
        else:
            snapshot = dict(snapshot)
        return observer.finish(snapshot)
    finally:
        observer.close()


def _load_advapi32():
    global native_api_loaded
    library = ctypes.WinDLL("advapi32", use_last_error=True)
    native_api_loaded = True
    return library


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class _WnodeVersionLinkage(ctypes.Structure):
    _fields_ = [("Version", wintypes.ULONG), ("Linkage", wintypes.ULONG)]


class _WnodeHistorical(ctypes.Union):
    """wmistr.h first union: ULONG64 HistoricalContext, or Version + Linkage."""

    _fields_ = [
        ("HistoricalContext", ctypes.c_ulonglong),
        ("VersionLinkage", _WnodeVersionLinkage),
    ]


class _WnodeCountLost(ctypes.Structure):
    _fields_ = [("CountLost", wintypes.ULONG)]


class _WnodeTimestamp(ctypes.Union):
    """wmistr.h second union. HANDLE and LARGE_INTEGER make it 8 bytes."""

    _fields_ = [
        ("CountLost", _WnodeCountLost),
        ("KernelHandle", ctypes.c_void_p),
        ("TimeStamp", ctypes.c_longlong),
    ]


class _WNODE_HEADER(ctypes.Structure):
    """SDK 10.0.26100.0 wmistr.h. Guid is at 24, not at 16.

    BufferSize and ProviderId occupy 0..8. Each following union is 8 bytes,
    so Guid starts at 24, ClientContext at 40, and Flags at 44. The structure
    is 48 bytes on both 32-bit and 64-bit Windows because the second union
    contains a LARGE_INTEGER.
    """

    _fields_ = [
        ("BufferSize", wintypes.ULONG),
        ("ProviderId", wintypes.ULONG),
        ("Historical", _WnodeHistorical),
        ("Timestamp", _WnodeTimestamp),
        ("Guid", _GUID),
        ("ClientContext", wintypes.ULONG),
        ("Flags", wintypes.ULONG),
    ]


class _EVENT_TRACE_PROPERTIES(ctypes.Structure):
    _fields_ = [
        ("Wnode", _WNODE_HEADER),
        ("BufferSize", wintypes.ULONG),
        ("MinimumBuffers", wintypes.ULONG),
        ("MaximumBuffers", wintypes.ULONG),
        ("MaximumFileSize", wintypes.ULONG),
        ("LogFileMode", wintypes.ULONG),
        ("FlushTimer", wintypes.ULONG),
        ("EnableFlags", wintypes.ULONG),
        ("AgeLimit", wintypes.LONG),
        ("NumberOfBuffers", wintypes.ULONG),
        ("FreeBuffers", wintypes.ULONG),
        ("EventsLost", wintypes.ULONG),
        ("BuffersWritten", wintypes.ULONG),
        ("LogBuffersLost", wintypes.ULONG),
        ("RealTimeBuffersLost", wintypes.ULONG),
        ("LoggerThreadId", ctypes.c_void_p),
        ("LogFileNameOffset", wintypes.ULONG),
        ("LoggerNameOffset", wintypes.ULONG),
    ]


class _SYSTEMTIME(ctypes.Structure):
    _fields_ = [
        ("Year", wintypes.WORD),
        ("Month", wintypes.WORD),
        ("DayOfWeek", wintypes.WORD),
        ("Day", wintypes.WORD),
        ("Hour", wintypes.WORD),
        ("Minute", wintypes.WORD),
        ("Second", wintypes.WORD),
        ("Milliseconds", wintypes.WORD),
    ]


class _TIME_ZONE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("Bias", wintypes.LONG),
        ("StandardName", wintypes.WCHAR * 32),
        ("StandardDate", _SYSTEMTIME),
        ("StandardBias", wintypes.LONG),
        ("DaylightName", wintypes.WCHAR * 32),
        ("DaylightDate", _SYSTEMTIME),
        ("DaylightBias", wintypes.LONG),
    ]


class _EVENT_DESCRIPTOR(ctypes.Structure):
    _fields_ = [
        ("Id", wintypes.USHORT),
        ("Version", wintypes.BYTE),
        ("Channel", wintypes.BYTE),
        ("Level", wintypes.BYTE),
        ("Opcode", wintypes.BYTE),
        ("Task", wintypes.USHORT),
        ("Keyword", ctypes.c_ulonglong),
    ]


class _EVENT_HEADER(ctypes.Structure):
    _fields_ = [
        ("Size", wintypes.USHORT),
        ("HeaderType", wintypes.USHORT),
        ("Flags", wintypes.USHORT),
        ("EventProperty", wintypes.USHORT),
        ("ThreadId", wintypes.ULONG),
        ("ProcessId", wintypes.ULONG),
        ("TimeStamp", ctypes.c_longlong),
        ("ProviderId", _GUID),
        ("EventDescriptor", _EVENT_DESCRIPTOR),
        ("ProcessorTime", ctypes.c_ulonglong),
        ("ActivityId", _GUID),
    ]


class _ETW_BUFFER_CONTEXT(ctypes.Structure):
    _fields_ = [
        ("ProcessorIndex", wintypes.USHORT),
        ("LoggerId", wintypes.USHORT),
    ]


class _EVENT_HEADER_EXTENDED_DATA_ITEM(ctypes.Structure):
    _fields_ = [
        ("Reserved1", wintypes.USHORT),
        ("ExtType", wintypes.USHORT),
        ("Linkage", wintypes.USHORT),
        ("DataSize", wintypes.USHORT),
        ("DataPtr", ctypes.c_ulonglong),
    ]


class _EVENT_RECORD(ctypes.Structure):
    _fields_ = [
        ("EventHeader", _EVENT_HEADER),
        ("BufferContext", _ETW_BUFFER_CONTEXT),
        ("ExtendedDataCount", wintypes.USHORT),
        ("UserDataLength", wintypes.USHORT),
        ("ExtendedData", ctypes.c_void_p),
        ("UserData", ctypes.c_void_p),
        ("UserContext", ctypes.c_void_p),
    ]


class _TraceHeaderType(ctypes.Structure):
    _fields_ = [("HeaderType", wintypes.BYTE), ("MarkerFlags", wintypes.BYTE)]


class _TraceFieldType(ctypes.Union):
    _fields_ = [
        ("FieldTypeFlags", wintypes.USHORT),
        ("HeaderBytes", _TraceHeaderType),
    ]


class _TraceClass(ctypes.Structure):
    _fields_ = [
        ("Type", wintypes.BYTE),
        ("Level", wintypes.BYTE),
        ("Version", wintypes.USHORT),
    ]


class _TraceVersion(ctypes.Union):
    _fields_ = [("Version", wintypes.ULONG), ("Class", _TraceClass)]


class _TraceGuid(ctypes.Union):
    _fields_ = [("Guid", _GUID), ("GuidPtr", ctypes.c_ulonglong)]


class _TraceKernelUser(ctypes.Structure):
    _fields_ = [("KernelTime", wintypes.ULONG), ("UserTime", wintypes.ULONG)]


class _TraceClientFlags(ctypes.Structure):
    _fields_ = [("ClientContext", wintypes.ULONG), ("Flags", wintypes.ULONG)]


class _TraceTimes(ctypes.Union):
    _fields_ = [
        ("KernelUser", _TraceKernelUser),
        ("ProcessorTime", ctypes.c_ulonglong),
        ("ClientFlags", _TraceClientFlags),
    ]


class _EVENT_TRACE_HEADER(ctypes.Structure):
    """evntrace.h EVENT_TRACE_HEADER. It overlays WNODE_HEADER and is 48 bytes."""

    _fields_ = [
        ("Size", wintypes.USHORT),
        ("FieldType", _TraceFieldType),
        ("Version", _TraceVersion),
        ("ThreadId", wintypes.ULONG),
        ("ProcessId", wintypes.ULONG),
        ("TimeStamp", ctypes.c_longlong),
        ("Guid", _TraceGuid),
        ("Times", _TraceTimes),
    ]


class _EVENT_TRACE(ctypes.Structure):
    _fields_ = [
        ("Header", _EVENT_TRACE_HEADER),
        ("InstanceId", wintypes.ULONG),
        ("ParentInstanceId", wintypes.ULONG),
        ("ParentGuid", _GUID),
        ("MofData", ctypes.c_void_p),
        ("MofLength", wintypes.ULONG),
        ("BufferContext", _ETW_BUFFER_CONTEXT),
    ]


class _TRACE_LOGFILE_HEADER(ctypes.Structure):
    """evntrace.h TRACE_LOGFILE_HEADER for this process's pointer width.

    TIME_ZONE_INFORMATION ends on a 4-byte boundary. BootTime is a
    LARGE_INTEGER, so the 4 bytes before it are padding on LLP64.
    """

    _fields_ = [
        ("BufferSize", wintypes.ULONG),
        ("Version", wintypes.ULONG),
        ("ProviderVersion", wintypes.ULONG),
        ("NumberOfProcessors", wintypes.ULONG),
        ("EndTime", ctypes.c_longlong),
        ("TimerResolution", wintypes.ULONG),
        ("MaximumFileSize", wintypes.ULONG),
        ("LogFileMode", wintypes.ULONG),
        ("BuffersWritten", wintypes.ULONG),
        ("LogInstanceGuid", _GUID),
        ("LoggerName", ctypes.c_void_p),
        ("LogFileName", ctypes.c_void_p),
        ("TimeZone", _TIME_ZONE_INFORMATION),
        ("BootTime", ctypes.c_longlong),
        ("PerfFreq", ctypes.c_longlong),
        ("StartTime", ctypes.c_longlong),
        ("ReservedFlags", wintypes.ULONG),
        ("BuffersLost", wintypes.ULONG),
    ]


class _EVENT_TRACE_LOGFILEW(ctypes.Structure):
    """evntrace.h EVENT_TRACE_LOGFILEW. LogFileName stays null: no ETL file."""

    _fields_ = [
        ("LogFileName", wintypes.LPCWSTR),
        ("LoggerName", wintypes.LPCWSTR),
        ("CurrentTime", ctypes.c_longlong),
        ("BuffersRead", wintypes.ULONG),
        ("ProcessTraceMode", wintypes.ULONG),
        ("CurrentEvent", _EVENT_TRACE),
        ("LogfileHeader", _TRACE_LOGFILE_HEADER),
        ("BufferCallback", ctypes.c_void_p),
        ("BufferSize", wintypes.ULONG),
        ("Filled", wintypes.ULONG),
        ("EventsLost", wintypes.ULONG),
        ("EventRecordCallback", ctypes.c_void_p),
        ("IsKernelTrace", wintypes.ULONG),
        ("Context", ctypes.c_void_p),
    ]


def consumer_layout_sizes() -> dict:
    """Structure widths for the running process. Does not call ETW."""
    return {
        "pointer": ctypes.sizeof(ctypes.c_void_p),
        "c_long": ctypes.sizeof(ctypes.c_long),
        "size_t": ctypes.sizeof(ctypes.c_size_t),
        "wnode": ctypes.sizeof(_WNODE_HEADER),
        "properties": ctypes.sizeof(_EVENT_TRACE_PROPERTIES),
        "event_header": ctypes.sizeof(_EVENT_HEADER),
        "event_record": ctypes.sizeof(_EVENT_RECORD),
        "time_zone": ctypes.sizeof(_TIME_ZONE_INFORMATION),
        "extended_item": ctypes.sizeof(_EVENT_HEADER_EXTENDED_DATA_ITEM),
        "event_trace": ctypes.sizeof(_EVENT_TRACE),
        "logfile_header": ctypes.sizeof(_TRACE_LOGFILE_HEADER),
        "logfile": ctypes.sizeof(_EVENT_TRACE_LOGFILEW),
    }


def _field_offset(struct_type, name: str) -> int:
    # This interpreter's ctypes has no offsetof. The field descriptor still
    # carries the byte offset ctypes computed from the SDK field list.
    return int(getattr(struct_type, name).offset)


def abi_field_offsets() -> dict:
    """Field offsets for review. This does not call ETW or load advapi32."""
    return {
        "wnode_guid": _field_offset(_WNODE_HEADER, "Guid"),
        "wnode_client_context": _field_offset(_WNODE_HEADER, "ClientContext"),
        "wnode_flags": _field_offset(_WNODE_HEADER, "Flags"),
        "events_lost": _field_offset(_EVENT_TRACE_PROPERTIES, "EventsLost"),
        "log_buffers_lost": _field_offset(_EVENT_TRACE_PROPERTIES, "LogBuffersLost"),
        "real_time_buffers_lost": _field_offset(_EVENT_TRACE_PROPERTIES, "RealTimeBuffersLost"),
        "event_record_user_context": _field_offset(_EVENT_RECORD, "UserContext"),
        "logfile_buffer_callback": _field_offset(_EVENT_TRACE_LOGFILEW, "BufferCallback"),
        "logfile_event_record_callback": _field_offset(_EVENT_TRACE_LOGFILEW, "EventRecordCallback"),
        "logfile_context": _field_offset(_EVENT_TRACE_LOGFILEW, "Context"),
        "logfile_process_trace_mode": _field_offset(_EVENT_TRACE_LOGFILEW, "ProcessTraceMode"),
    }


class WinEtwApi:
    """Real advapi32 session. Constructing it loads nothing until start_session.

    An existing logger is never stopped. Access denial does not elevate.
    """

    def __init__(self):
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            raise OwnedLaunchUnsupported("windows_pointer_width")
        sizes = consumer_layout_sizes()
        if sizes["c_long"] != 4 or sizes["size_t"] != 8 or sizes["event_header"] != 80:
            raise OwnedLaunchUnsupported("windows_llp64_layout")
        if sizes["event_record"] != 112 or sizes["properties"] != 120 or sizes["wnode"] != 48:
            raise OwnedLaunchUnsupported("windows_llp64_layout")
        offsets = abi_field_offsets()
        if (
            offsets["wnode_guid"] != 24
            or offsets["wnode_client_context"] != 40
            or offsets["wnode_flags"] != 44
            or sizes["event_trace"] != 88
            or sizes["logfile_header"] != 280
            or sizes["logfile"] != 448
            or offsets["logfile_buffer_callback"] != 400
            or offsets["logfile_event_record_callback"] != 424
            or offsets["logfile_context"] != 440
        ):
            raise OwnedLaunchUnsupported("windows_llp64_layout")
        self._library = None
        self._callback = None
        self._buffer_callback = None
        self._logfile = None
        self._logger_name = None
        self._properties_buffer = None
        self._session_name = None

    def start_session(self, request: dict) -> dict:
        global native_session_starts
        native_session_starts += 1
        if type(request) is not dict or request.get("session_name") != SESSION_NAME:
            return {"ok": False, "code": "invalid_session", "handle": None}
        if request.get("session_name") == KERNEL_LOGGER_NAME or request.get("etl_file") is True:
            return {"ok": False, "code": "invalid_session", "handle": None}
        if request.get("stop_existing_session") is True or request.get("privilege_escalation") is True:
            return {"ok": False, "code": "invalid_session", "handle": None}
        library = _load_advapi32()
        self._library = library
        name = SESSION_NAME
        encoded = (name + "\x00").encode("utf-16-le")
        extra = len(encoded)
        total = ctypes.sizeof(_EVENT_TRACE_PROPERTIES) + extra
        buffer = ctypes.create_string_buffer(total)
        props = ctypes.cast(buffer, ctypes.POINTER(_EVENT_TRACE_PROPERTIES)).contents
        props.Wnode.BufferSize = total
        props.Wnode.Flags = WNODE_FLAG_TRACED_GUID
        props.Wnode.ClientContext = CLIENT_CONTEXT_QPC
        # GUID_NULL. System-logger mode selects the session. This is not
        # SystemTraceControlGuid and not the NT Kernel Logger.
        props.BufferSize = BUFFER_SIZE_KB
        props.MinimumBuffers = MINIMUM_BUFFERS
        props.MaximumBuffers = MAXIMUM_BUFFERS
        props.LogFileMode = request["log_file_mode"]
        props.FlushTimer = FLUSH_TIMER_SECONDS
        props.EnableFlags = request["enable_flags"]
        props.LogFileNameOffset = 0
        props.LoggerNameOffset = ctypes.sizeof(_EVENT_TRACE_PROPERTIES)
        handle = ctypes.c_ulonglong(0)
        library.StartTraceW.argtypes = [
            ctypes.POINTER(ctypes.c_ulonglong),
            wintypes.LPCWSTR,
            ctypes.c_void_p,
        ]
        library.StartTraceW.restype = wintypes.ULONG
        code = int(library.StartTraceW(ctypes.byref(handle), name, ctypes.byref(props)))
        if code != 0 or handle.value == 0:
            self._properties_buffer = None
            if code == 183:
                return {"ok": False, "code": "already_exists", "handle": None}
            if code == 5:
                return {"ok": False, "code": "access_denied", "handle": None}
            return {"ok": False, "code": f"start_{code:x}", "handle": None}
        self._properties_buffer = buffer
        self._session_name = name
        return {"ok": True, "code": "ok", "handle": int(handle.value)}

    def open_trace(self, session_name: str, on_event) -> dict:
        if session_name != SESSION_NAME or self._library is None:
            return {"ok": False, "code": "open_trace_failed", "handle": None}
        # Classic OpenTraceW needs the full logfile structure, including the
        # timezone and current-event tails. Those widths are checked when this
        # object is constructed. LogFileName stays null: no ETL file is opened.
        logfile = self._new_logfile(on_event)
        self._library.OpenTraceW.argtypes = [ctypes.c_void_p]
        self._library.OpenTraceW.restype = ctypes.c_ulonglong
        handle = int(self._library.OpenTraceW(ctypes.byref(logfile)))
        invalid = ctypes.c_ulonglong(-1).value
        if handle == 0 or handle == invalid:
            self._drop_callbacks()
            return {"ok": False, "code": "open_trace_failed", "handle": None}
        self._logfile = logfile
        return {"ok": True, "code": "ok", "handle": handle}

    def process_trace(self, trace_handle, on_ready) -> dict:
        on_ready()
        if self._library is None or trace_handle is None:
            return {"ok": False, "code": "process_trace_failed"}
        array = (ctypes.c_ulonglong * 1)(int(trace_handle))
        self._library.ProcessTrace.argtypes = [
            ctypes.POINTER(ctypes.c_ulonglong),
            wintypes.ULONG,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self._library.ProcessTrace.restype = wintypes.ULONG
        code = int(self._library.ProcessTrace(array, 1, None, None))
        if code != 0:
            return {"ok": False, "code": f"process_{code:x}"}
        return {"ok": True, "code": "ok"}

    def stop_session(self, session_handle) -> dict:
        """Stop the handle this object started. The session name is not used."""
        if self._library is None or self._properties_buffer is None or session_handle is None:
            return {"ok": False, "code": "stop_failed", "loss": {}}
        props = ctypes.cast(self._properties_buffer, ctypes.POINTER(_EVENT_TRACE_PROPERTIES)).contents
        self._library.StopTraceW.argtypes = [
            ctypes.c_ulonglong,
            wintypes.LPCWSTR,
            ctypes.c_void_p,
        ]
        self._library.StopTraceW.restype = wintypes.ULONG
        code = int(self._library.StopTraceW(ctypes.c_ulonglong(int(session_handle)), None, ctypes.byref(props)))
        loss = {
            "events_lost": int(props.EventsLost),
            "log_buffers_lost": int(props.LogBuffersLost),
            "real_time_buffers_lost": int(props.RealTimeBuffersLost),
        }
        if code != 0:
            return {"ok": False, "code": f"stop_{code:x}", "loss": loss}
        return {"ok": True, "code": "ok", "loss": loss}

    def close_trace(self, trace_handle) -> None:
        if self._library is None or trace_handle is None:
            self._drop_callbacks()
            return
        self._library.CloseTrace.argtypes = [ctypes.c_ulonglong]
        self._library.CloseTrace.restype = wintypes.ULONG
        self._library.CloseTrace(ctypes.c_ulonglong(int(trace_handle)))
        self._drop_callbacks()

    def close_session(self, session_handle) -> None:
        # StopTraceW releases the logging session. CloseTrace is only for the
        # consumer handle from OpenTrace. Drop the property buffer either way.
        self._properties_buffer = None
        self._session_name = None
        del session_handle

    def _new_logfile(self, on_event):
        # The consumer structure is built only after start_session. A failure
        # before OpenTrace never publishes a callback.
        record_callback = ctypes.WINFUNCTYPE(None, ctypes.POINTER(_EVENT_RECORD))
        buffer_callback = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)

        def _record(pointer):
            try:
                on_event(_record_to_dict(pointer.contents))
            except Exception:
                return

        def _buffer(_logfile):
            return 1

        self._callback = record_callback(_record)
        self._buffer_callback = buffer_callback(_buffer)
        # LogFileName stays null. The callback fields sit after EVENT_TRACE and
        # TRACE_LOGFILE_HEADER, at the offsets abi_field_offsets reports.
        # OpenTraceW is not called from unit tests.
        self._logger_name = SESSION_NAME
        logfile = _EVENT_TRACE_LOGFILEW()
        logfile.LoggerName = self._logger_name
        logfile.ProcessTraceMode = PROCESS_TRACE_MODE_REAL_TIME | PROCESS_TRACE_MODE_EVENT_RECORD
        logfile.EventRecordCallback = ctypes.cast(self._callback, ctypes.c_void_p)
        logfile.BufferCallback = ctypes.cast(self._buffer_callback, ctypes.c_void_p)
        return logfile

    def _drop_callbacks(self) -> None:
        self._callback = None
        self._buffer_callback = None
        self._logfile = None


def _record_to_dict(record) -> dict:
    header = record.EventHeader
    descriptor = header.EventDescriptor
    flags = int(header.Flags)
    processor = int(record.BufferContext.ProcessorIndex)
    if (flags & EVENT_HEADER_FLAG_PROCESSOR_INDEX) == 0:
        processor = processor & 0xFF
    payload = b""
    length = int(record.UserDataLength)
    if record.UserData and 0 < length <= 65536:
        payload = ctypes.string_at(record.UserData, length)
    return {
        "provider": _guid_text(header.ProviderId),
        "version": int(descriptor.Version),
        "opcode": int(descriptor.Opcode),
        "flags": flags,
        "timestamp": int(header.TimeStamp),
        "processor_index": processor,
        "header_pid": int(header.ProcessId),
        "payload": payload,
        "process_start_key_present": _start_key_present(record),
    }


def _guid_text(guid) -> str:
    data4 = bytes(guid.Data4)
    return (
        f"{int(guid.Data1):08x}-{int(guid.Data2):04x}-{int(guid.Data3):04x}-"
        f"{data4[:2].hex()}-{data4[2:].hex()}"
    )


def _start_key_present(record) -> bool:
    count = int(record.ExtendedDataCount)
    if count <= 0 or not record.ExtendedData:
        return False
    # The key value is not copied. Its presence must not identify a generation.
    item_size = ctypes.sizeof(_EVENT_HEADER_EXTENDED_DATA_ITEM)
    for index in range(min(count, 32)):
        address = record.ExtendedData + (index * item_size)
        item = ctypes.cast(address, ctypes.POINTER(_EVENT_HEADER_EXTENDED_DATA_ITEM)).contents
        if int(item.ExtType) == EVENT_HEADER_EXT_TYPE_PROCESS_START_KEY:
            return True
    return False


