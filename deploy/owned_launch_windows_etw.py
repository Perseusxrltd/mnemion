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

The owned root binds only when one opcode-1 birth FILETIME equals the retained
creation. A different FILETIME stays unproven. Unequal Start and End
UniqueProcessKey values are not joined. A terminal counter counts only inside
that paired lifetime. Callback storage stays alive until the consumer thread
is confirmed finished. There is no separate cleanup process.

Native ETW is not invoked by tests. WinEtwApi is constructed only by an
explicit caller after review. AdapterOwnership takes a library loader and
is the offline stand-in.
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
_COUNT_SATURATION = 65535
# winerror.h ERROR_CTX_CLOSE_PENDING. CloseTrace can return this while
# ProcessTrace is still inside the callback.
ERROR_CTX_CLOSE_PENDING = 7007
BRIDGE_RECORD_CONVERSION = "record_conversion"
_COUNTER_UINT32S = 4
_COUNTER_SIZETS = 11
_PEAK_WORKING_SET_INDEX = 1
_LIFE_UINT32S = 4

_METHOD = "windows_etw_process_counter"
_PRODUCTION_METHOD = "windows_job_before_resume"

# Fixed diagnostic vocabulary. Unknown note_gap strings fold into external_gap.
# The set is the memory bound; counts saturate instead of storing one string
# per callback.
_GAP_REASONS = frozenset(
    {
        "session_not_started",
        "session_exists_not_stopped",
        "access_denied",
        "open_trace_failed",
        "consumer_not_ready",
        "launch_identity_missing",
        "job_active_processes",
        "retained_records_exceeded",
        "callbacks_exceeded",
        "callback_failed",
        "parser_failed",
        "deadline_exceeded",
        "stop_failed",
        "drain_failed",
        "stop_or_drain_failed",
        "equal_time",
        "reused_pid",
        "root_unobserved",
        "root_ambiguous",
        "ambiguous_parent",
        "exit_missing",
        "terminal_counter_missing",
        "terminal_counter_unqualified",
        "job_census_unavailable",
        "census_births",
        "census_exits",
        "census_terminal_counters",
        "events_lost",
        "log_buffers_lost",
        "real_time_buffers_lost",
        "root_binding_unproven",
        "exit_key_mismatch",
        "terminal_counter_unproven",
        "record_conversion_failed",
        "close_failed",
        "close_pending",
        "consumer_still_live",
        "session_still_owned",
        "session_release_failed",
        "session_already_attempted",
        "external_gap",
    }
)

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

    Arrival order is not a key. Equal timestamps stay unresolved. The root
    binds only to one birth whose FILETIME equals the retained creation.
    An End joins a Start only when UniqueProcessKey matches. A terminal
    counter counts only strictly inside that paired lifetime.
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


def _same_process_key(birth: dict, end: dict) -> bool:
    # The key is a reusable kernel object address. It does not merge two
    # generations. Unequal values do reject a Start/End join.
    return birth.get("unique_process_key") == end.get("unique_process_key")


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
            mismatched = []
            for end in pid_ends:
                stamp = end["timestamp"]
                on_boundary = stamp == birth["timestamp"] or (
                    next_stamp is not None and stamp == next_stamp
                )
                in_window = stamp > birth["timestamp"] and (
                    next_stamp is None or stamp < next_stamp
                )
                if not on_boundary and not in_window:
                    continue
                if not _same_process_key(birth, end):
                    mismatched.append(end)
                    continue
                if on_boundary:
                    boundary.append(end)
                else:
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
            elif mismatched:
                # The End was observed, but it is not this Start. Leaving end
                # empty and exit_ambiguous false would keep the PID interval
                # open and admit a later child. The edge is unqualified.
                exit_ambiguous = True
                gaps.append("exit_key_mismatch")
                ambiguities.append(
                    {
                        "kind": "exit_key_mismatch",
                        "pid": pid,
                        "timestamp": birth["timestamp"],
                        "candidates": len(mismatched),
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
    exact = [item for item in clear if item["birth"]["timestamp"] == root_creation]
    # Totals and time proximity are not a generation binding. One exact
    # FILETIME match is the only retained-creation bind. Exact equality is
    # still not proof that ETW's clock matches GetProcessTimes.
    if len(exact) == 1:
        return exact[0], len(candidates) > 1
    if len(exact) > 1:
        gaps.append("root_ambiguous")
        gaps.append("equal_time")
        ambiguities.append(
            {
                "kind": "root_pid_reuse",
                "pid": root_pid,
                "candidates": len(candidates),
                "exact_creation_matches": len(exact),
            }
        )
        return None, False
    if len(candidates) == 1:
        gaps.append("root_binding_unproven")
        ambiguities.append(
            {
                "kind": "root_binding_unproven",
                "pid": root_pid,
                "candidates": 1,
            }
        )
        return None, False
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
        end = generation["end"]
        generation["counter"] = None
        if end is None:
            # A counter before the next observed Start is not a terminal join
            # when this generation has no paired End.
            generation["counter_state"] = "unproven"
            gaps.append("terminal_counter_unproven")
            continue
        end_stamp = end["timestamp"]
        later = [
            item["birth"]["timestamp"]
            for item in generations
            if item["birth"]["pid"] == pid and item["birth"]["timestamp"] > start
        ]
        next_stamp = min(later) if later else None
        window = []
        boundary = []
        post_end = []
        for counter in counters:
            if counter["pid"] != pid:
                continue
            stamp = counter["timestamp"]
            if next_stamp is not None and stamp > next_stamp:
                continue
            at_boundary = stamp == start or stamp == end_stamp or (
                next_stamp is not None and stamp == next_stamp
            )
            inside = stamp > start and stamp < end_stamp and (
                next_stamp is None or stamp < next_stamp
            )
            if at_boundary:
                boundary.append(counter)
            elif inside:
                window.append(counter)
            elif stamp > end_stamp:
                post_end.append(counter)
        if len(window) == 1 and not boundary:
            generation["counter"] = window[0]
            generation["counter_state"] = "opcode32"
            continue
        if window or boundary:
            generation["counter_state"] = "unqualified"
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
            continue
        if post_end:
            generation["counter_state"] = "unproven"
            gaps.append("terminal_counter_unproven")
            continue
        generation["counter_state"] = "missing"
        gaps.append("terminal_counter_missing")


def _identity(generation: dict, root: dict | None, root_creation: int | None) -> str:
    pid = generation["birth"]["pid"]
    birth_stamp = generation["birth"]["timestamp"]
    if generation is root and type(root_creation) is int and birth_stamp == root_creation:
        return f"{pid}:{root_creation}"
    return f"{pid}:etw:{birth_stamp}"


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
            "close_ok": session.get("close_ok") is True,
            "consumer_finished": session.get("consumer_finished") is True,
            "session_released": session.get("session_released") is True,
            "callbacks_released": session.get("callbacks_released") is True,
            "stopped_existing_logger": False,
            "privilege_escalated": False,
            # No helper process is started. This is an observation, not a boundary.
            "isolated_cleanup_process": False,
        },
        "limits": {
            "max_retained_events": session.get("retain_limit", MAX_RETAINED_EVENTS),
            "max_callbacks": session.get("callback_limit", MAX_CALLBACKS),
            "max_owned": MAX_LEDGER,
            "retained_records": session.get("retained_records"),
            "callbacks": session.get("callbacks"),
            "gap_counts": dict(session.get("gap_counts") or {}),
        },
    }


def interpret_close_trace(code: int) -> dict:
    """Map a CloseTrace ULONG to success, pending, or failure.

    0 is success. ERROR_CTX_CLOSE_PENDING (7007) means the consumer can still
    run the callback. Every other code is a failed close. The raw code is not
    copied into the result.
    """
    if type(code) is not int:
        return {"ok": False, "code": "close_failed", "pending": False}
    if code == 0:
        return {"ok": True, "code": "ok", "pending": False}
    if code == ERROR_CTX_CLOSE_PENDING:
        return {"ok": False, "code": "close_pending", "pending": True}
    return {"ok": False, "code": "close_failed", "pending": False}


def bridge_event(convert, deliver) -> None:
    """Convert one record and hand it to the observer.

    A conversion failure delivers only the fixed ``record_conversion``
    diagnostic. The exception text and the payload are not copied. A failure
    inside deliver is left for the caller so a ctypes callback can contain it.
    """
    try:
        event = convert()
    except Exception:
        deliver({"bridge_diagnostic": BRIDGE_RECORD_CONVERSION})
        return
    deliver(event)


class EtwLifetimeObserver:
    """Collect numeric process events, then resolve them after cleanup.

    Callback and logfile objects stay referenced until the consumer thread
    is confirmed finished. Successful stop and close are not repeated.
    A failed stop keeps the owned session. There is no helper process and
    no name-based stop of an existing logger.
    """

    def __init__(
        self,
        api,
        *,
        ready_seconds: float = 2.0,
        drain_seconds: float = 5.0,
        callback_limit: int | None = None,
        retain_limit: int | None = None,
    ):
        if type(ready_seconds) not in (int, float) or type(drain_seconds) not in (int, float):
            raise OwnedLaunchError("invalid_bound")
        if ready_seconds <= 0 or drain_seconds <= 0:
            raise OwnedLaunchError("invalid_bound")
        self._api = api
        self._ready_seconds = float(ready_seconds)
        self._drain_seconds = float(drain_seconds)
        self._callback_limit = self._bounded_cap(callback_limit, MAX_CALLBACKS)
        self._retain_limit = self._bounded_cap(retain_limit, MAX_RETAINED_EVENTS)
        self._lock = threading.RLock()
        self._events: list[dict] = []
        self._gap_counts: dict[str, int] = {}
        self._callbacks = 0
        self._callback_live = False
        self._callbacks_released = False
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
        self._stop_result = None
        self._close_result = None
        self._session_released = False
        self._start_attempted = False
        self._control_handle = None
        self._acquired_trace = None

    @staticmethod
    def _bounded_cap(value: int | None, ceiling: int) -> int:
        if value is None:
            return ceiling
        if type(value) is not int or not 1 <= value <= ceiling:
            raise OwnedLaunchError("invalid_bound")
        return value

    @property
    def callback_live(self) -> bool:
        return self._callback_live

    @property
    def request(self) -> dict:
        return dict(self._request)

    def start_before_root(self) -> bool:
        # One attempt. A second call is refused before the API is touched,
        # including after an open failure or a failed stop.
        if self._start_attempted or self._started or self._closed:
            self._note_gap("session_not_started")
            return False
        self._start_attempted = True
        started = self._api.start_session(self._request)
        if type(started) is not dict or started.get("ok") is not True:
            code = None if type(started) is not dict else started.get("code")
            if code == "already_exists":
                self._note_gap("session_exists_not_stopped")
            elif code == "access_denied":
                self._note_gap("access_denied")
            elif code == "session_already_attempted":
                self._note_gap("session_already_attempted")
            else:
                self._note_gap("session_not_started")
            return False
        handle = started.get("handle")
        if type(handle) is not int or handle <= 0:
            self._note_gap("session_not_started")
            return False
        self._control_handle = handle
        self._session = handle
        opened = self._api.open_trace(self._request["session_name"], self._on_event)
        if type(opened) is not dict or opened.get("ok") is not True:
            self._note_gap("open_trace_failed")
            self._stop_owned_session()
            return False
        trace = opened.get("handle")
        if type(trace) is not int or trace <= 0:
            self._note_gap("open_trace_failed")
            self._stop_owned_session()
            return False
        self._trace = trace
        self._acquired_trace = trace
        self._callback_live = True
        self._thread = threading.Thread(target=self._consume, name="mnemion-etw-consume")
        self._thread.start()
        if not self._ready.wait(self._ready_seconds):
            self._note_gap("consumer_not_ready")
            self._stop_owned_session()
            self._join_consumer(self._drain_seconds)
            return False
        self._started = True
        return True

    def bind_root(self, pid: int, creation: int) -> None:
        if type(pid) is not int or type(creation) is not int or not 0 < pid < 2**32 or creation < 0:
            self._note_gap("launch_identity_missing")
            return
        self._root_pid = pid
        self._root_creation = creation

    def note_gap(self, code: str) -> None:
        self._note_gap(code)

    def _note_gap(self, code: str) -> None:
        if type(code) is not str or code not in _GAP_REASONS:
            code = "external_gap"
        with self._lock:
            count = self._gap_counts.get(code, 0)
            if count < _COUNT_SATURATION:
                self._gap_counts[code] = count + 1

    def _gap_snapshot(self) -> tuple[list[str], dict[str, int]]:
        with self._lock:
            return sorted(self._gap_counts), dict(self._gap_counts)

    def finish(self, snapshot: dict | None) -> dict:
        if self._report is not None:
            return self._report
        self._finished = True
        cleanup = self._cleanup()
        with self._lock:
            retained = list(self._events)
            callbacks = self._callbacks
        resolved = resolve_owned(retained, self._root_pid, self._root_creation)
        for code in resolved["gaps"]:
            self._note_gap(code)
        if len(resolved["rows"]) > MAX_LEDGER:
            self._note_gap("retained_records_exceeded")
            resolved = dict(resolved)
            resolved["rows"] = []
            resolved["births"] = 0
            resolved["exits"] = 0
            resolved["terminal_counters"] = 0
            resolved["gaps"] = list(resolved["gaps"]) + ["retained_records_exceeded"]
        reasons, gap_counts = self._gap_snapshot()
        session = {
            "gaps": reasons,
            "gap_counts": gap_counts,
            "loss": cleanup["loss"],
            "started": self._started,
            "stop_ok": cleanup["stop_ok"],
            "drain_ok": cleanup["drain_ok"],
            "close_ok": cleanup["close_ok"],
            "consumer_finished": cleanup["consumer_finished"],
            "session_released": cleanup["session_released"],
            "callbacks_released": cleanup["callbacks_released"],
            "retained_records": len(retained),
            "callbacks": callbacks,
            "callback_limit": self._callback_limit,
            "retain_limit": self._retain_limit,
        }
        self._report = reconcile(resolved, snapshot, session)
        self._closed = True
        return self._report

    def close(self) -> None:
        # A cached report is not rebuilt and a successful stop is not repeated.
        # Callbacks drop only when the consumer thread is already finished.
        if self._report is None:
            self.finish(None)
            return
        self._drop_callbacks_if_consumer_dead()
        self._closed = True

    def recovery_state(self) -> dict:
        """Local owner record. This is not copied into the resource report.

        Session, trace, and callback ownership are separate. A released
        session can still leave a trace handle or a live callback. There is
        no separate cleanup process. A later native run has to be supervised
        outside this process, on a disposable runner.
        """
        stop_ok = type(self._stop_result) is dict and self._stop_result.get("ok") is True
        close_ok = type(self._close_result) is dict and self._close_result.get("ok") is True
        close_pending = (
            type(self._close_result) is dict and self._close_result.get("pending") is True
        )
        session_outstanding = (
            self._control_handle is not None and self._session_released is not True
        )
        trace_outstanding = self._acquired_trace is not None and close_ok is not True
        callback_outstanding = self._callbacks_released is not True and (
            self._callback_live or self._thread is not None
        )
        return {
            "start_attempted": self._start_attempted,
            "control_handle": self._control_handle,
            "trace_handle": self._acquired_trace,
            "stop_ok": stop_ok,
            "close_ok": close_ok,
            "close_pending": close_pending,
            "session_released": self._session_released,
            "callbacks_released": self._callbacks_released,
            "consumer_finished": not self._consumer_alive(),
            "session_outstanding": session_outstanding,
            "trace_outstanding": trace_outstanding,
            "callback_outstanding": callback_outstanding,
            "recoverable": session_outstanding or trace_outstanding or callback_outstanding,
            "isolated_cleanup_process": False,
        }

    def retry_failed_close(self, handle=None) -> dict:
        """Close the acquired trace again after the consumer thread has stopped.

        A successful or pending close is not submitted again. A failed close
        keeps the handle and can be retried. A foreign handle is refused
        before the API is called.
        """
        if self._consumer_alive():
            return {"ok": False, "code": "consumer_still_live", "pending": False}
        known = self._acquired_trace
        supplied = known if handle is None else handle
        if type(supplied) is not int or supplied != known or known is None:
            return {"ok": False, "code": "unknown_handle", "pending": False}
        if type(self._close_result) is dict and self._close_result.get("pending") is True:
            self._close_result = {"ok": True, "code": "ok", "pending": False}
            self._trace = None
            return {"ok": True, "code": "ok", "pending": False}
        if type(self._close_result) is dict and self._close_result.get("ok") is True:
            return {"ok": True, "code": "already_closed", "pending": False}
        return self._close_trace_once()

    def release_finished_consumer(self) -> bool:
        """Join the consumer, then drop callbacks only if it has stopped.

        This does not start a helper process, does not stop a logger by name,
        and does not rewrite a report that was already finalized. Returning
        true requires the trace close itself to be successful. Callback
        release alone does not recover a failed close. A pending close is not
        submitted again.
        """
        self._join_consumer(self._drain_seconds)
        if self._consumer_alive():
            return False
        close_ok = type(self._close_result) is dict and self._close_result.get("ok") is True
        if type(self._close_result) is dict and self._close_result.get("pending") is True:
            self._close_result = {"ok": True, "code": "ok", "pending": False}
            self._trace = None
            close_ok = True
        elif close_ok is not True and self._acquired_trace is not None:
            result = self._close_trace_once()
            close_ok = type(result) is dict and result.get("ok") is True
        released = self._drop_callbacks_if_consumer_dead()
        return bool(released and close_ok)

    def _consume(self) -> None:
        try:
            self._process_result = self._api.process_trace(self._trace, self._ready.set)
        except Exception:
            self._note_gap("callback_failed")
            self._ready.set()
        finally:
            self._ready.set()

    def _on_event(self, record: dict) -> None:
        if type(record) is dict and record.get("bridge_diagnostic") == BRIDGE_RECORD_CONVERSION:
            with self._lock:
                if self._callbacks < _COUNT_SATURATION:
                    self._callbacks += 1
            self._note_gap("record_conversion_failed")
            return
        try:
            self._accept(record)
        except Exception:
            self._note_gap("callback_failed")

    def _accept(self, record: dict) -> None:
        with self._lock:
            if self._callbacks < _COUNT_SATURATION:
                self._callbacks += 1
            if self._callbacks > self._callback_limit:
                self._note_gap("callbacks_exceeded")
                return
            if len(self._events) >= self._retain_limit:
                self._note_gap("retained_records_exceeded")
                return
        decoded = decode_record(record)
        if decoded.get("disposition") == "ignore":
            return
        if decoded.get("disposition") != "event":
            self._note_gap("parser_failed")
            return
        kept = dict(decoded)
        kept.pop("disposition", None)
        with self._lock:
            if len(self._events) >= self._retain_limit:
                self._note_gap("retained_records_exceeded")
                return
            self._events.append(kept)

    def _cleanup(self) -> dict:
        empty_loss = {
            "events_lost": None,
            "log_buffers_lost": None,
            "real_time_buffers_lost": None,
        }
        if self._session is None and not self._started and self._thread is None:
            return {
                "stop_ok": False,
                "drain_ok": False,
                "loss": empty_loss,
                "close_ok": True,
                "consumer_finished": True,
                "session_released": False,
                "callbacks_released": not self._callback_live,
            }
        stopped = self._stop_owned_session()
        stop_ok = type(stopped) is dict and stopped.get("ok") is True
        loss = stopped.get("loss") if type(stopped) is dict else None
        if type(loss) is not dict:
            loss = dict(empty_loss)
        joined = self._join_consumer(self._drain_seconds)
        if not joined:
            self._note_gap("deadline_exceeded")
        close_result = self._close_trace_once()
        if not joined:
            joined = self._join_consumer(self._drain_seconds)
        close_ok = close_result.get("ok") is True
        if close_result.get("pending") is True:
            self._note_gap("close_pending")
        elif not close_ok:
            self._note_gap("close_failed")
        consumer_finished = not self._consumer_alive()
        if consumer_finished:
            self._drop_callbacks_if_consumer_dead()
        else:
            self._note_gap("consumer_still_live")
        if stop_ok:
            session_released = self._release_session()
        else:
            self._note_gap("stop_failed")
            self._note_gap("session_still_owned")
            session_released = False
        if self._thread is None:
            process_ok = True
        else:
            process_ok = (
                type(self._process_result) is dict and self._process_result.get("ok") is True
            )
        drain_ok = bool(joined and process_ok and stop_ok and close_ok and consumer_finished)
        if not drain_ok and (self._started or self._thread is not None):
            self._note_gap("drain_failed")
        return {
            "stop_ok": stop_ok,
            "drain_ok": drain_ok,
            "loss": loss,
            "close_ok": close_ok,
            "consumer_finished": consumer_finished,
            "session_released": session_released,
            "callbacks_released": self._callbacks_released,
        }

    def _stop_owned_session(self) -> dict:
        handle = self._session if self._session is not None else self._control_handle
        if (
            self._stop_result is not None
            and self._stop_result.get("ok") is True
            and handle == self._control_handle
        ):
            return self._stop_result
        if type(handle) is not int or handle != self._control_handle or self._api is None:
            return {"ok": False, "code": "unknown_handle", "loss": {}}
        try:
            result = self._api.stop_session(handle)
        except Exception:
            result = {"ok": False, "code": "stop_failed", "loss": {}}
        if type(result) is not dict:
            result = {"ok": False, "code": "stop_failed", "loss": {}}
        if result.get("ok") is True and handle == self._control_handle:
            self._stop_result = result
        return result

    def _join_consumer(self, seconds: float) -> bool:
        thread = self._thread
        if thread is None:
            return True
        if not thread.is_alive() and thread.ident is None:
            return True
        thread.join(seconds)
        return not thread.is_alive()

    def _consumer_alive(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def _close_trace_once(self) -> dict:
        # The consumer handle is not the control handle. Identity is the
        # handle acquired at open, kept even after a successful close clears
        # the live trace slot.
        known = self._acquired_trace
        current = self._trace
        cached = self._close_result
        if type(cached) is dict and (cached.get("ok") is True or cached.get("pending") is True):
            if known is None or (current is not None and current != known):
                return {"ok": False, "code": "unknown_handle", "pending": False}
            return dict(cached)
        handle = current if current is not None else known
        if known is None or handle != known or self._api is None:
            if known is None and handle is None and self._control_handle is None and self._thread is None:
                result = {"ok": True, "code": "no_trace", "pending": False}
                self._close_result = result
                return dict(result)
            if known is None and handle is None:
                result = {"ok": True, "code": "no_trace", "pending": False}
                self._close_result = result
                return dict(result)
            return {"ok": False, "code": "unknown_handle", "pending": False}
        try:
            result = self._api.close_trace(known)
        except Exception:
            result = {"ok": False, "code": "close_failed", "pending": False}
        if type(result) is not dict:
            result = {"ok": False, "code": "close_failed", "pending": False}
        if result.get("code") == "unknown_handle":
            return {"ok": False, "code": "unknown_handle", "pending": False}
        pending = result.get("pending") is True or result.get("code") == "close_pending"
        ok = result.get("ok") is True and not pending
        normalized = {
            "ok": ok,
            "code": "close_pending" if pending else ("ok" if ok else "close_failed"),
            "pending": pending,
        }
        # A hard failure is not cached, so the same trace handle can be closed
        # again after the consumer is confirmed finished.
        if ok or pending:
            self._close_result = normalized
        if ok:
            self._trace = None
        return normalized

    def _release_session(self) -> bool:
        if self._session_released:
            return True
        if self._stop_result is None or self._stop_result.get("ok") is not True:
            self._note_gap("session_still_owned")
            return False
        handle = self._session
        if handle is None:
            self._session_released = True
            return True
        if self._api is None:
            self._note_gap("session_release_failed")
            return False
        try:
            result = self._api.close_session(handle)
        except Exception:
            self._note_gap("session_release_failed")
            return False
        if type(result) is dict and result.get("ok") is not True:
            if result.get("code") == "session_still_owned":
                self._note_gap("session_still_owned")
            else:
                self._note_gap("session_release_failed")
            return False
        self._session = None
        self._session_released = True
        return True

    def _drop_callbacks_if_consumer_dead(self) -> bool:
        # Callback storage belongs to the consumer that acquired the trace.
        # A refused wrapper has no trace and no thread; that absence is not
        # permission to release another live consumer.
        if self._acquired_trace is None:
            return False
        if self._consumer_alive():
            return False
        if self._callbacks_released:
            return True
        release = getattr(self._api, "release_callbacks", None)
        if release is not None:
            try:
                outcome = release(self._acquired_trace)
            except Exception:
                self._note_gap("callback_failed")
                return False
            if outcome is False:
                return False
        self._callback_live = False
        self._callbacks_released = True
        return True


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
        retain = getattr(api, "retain_recovery", None)
        if retain is not None:
            retain(observer.recovery_state())


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


class LocalCleanupOwner:
    """Private recovery for handles this process already acquired.

    The resource receipt does not carry this object. There is no separate
    cleanup process.
    """

    def __init__(self, api, state):
        if type(state) is not dict:
            state = {}
        control = state.get("control_handle")
        trace = state.get("trace_handle")
        if type(control) is not int or control <= 0:
            control = None
        if type(trace) is not int or trace <= 0:
            trace = None
        self._api = api
        self._state = {
            "control_handle": control,
            "trace_handle": trace,
            "stop_ok": state.get("stop_ok") is True,
            "close_ok": state.get("close_ok") is True,
            "close_pending": state.get("close_pending") is True,
            "session_released": state.get("session_released") is True,
            "callbacks_released": state.get("callbacks_released") is True,
            "session_outstanding": state.get("session_outstanding") is True,
            "trace_outstanding": state.get("trace_outstanding") is True,
            "callback_outstanding": state.get("callback_outstanding") is True,
            "consumer_completed": False,
            "recoverable": state.get("recoverable") is True,
            "isolated_cleanup_process": False,
        }

    def snapshot(self) -> dict:
        self._refresh()
        return dict(self._state)

    def retry_stop(self, handle) -> dict:
        known = self._state["control_handle"]
        if type(handle) is not int or handle != known or known is None:
            return {"ok": False, "code": "unknown_handle", "loss": {}}
        if self._state["stop_ok"]:
            return {"ok": True, "code": "already_stopped", "loss": {}}
        result = self._api.stop_session(handle)
        if type(result) is not dict:
            return {"ok": False, "code": "stop_failed", "loss": {}}
        if result.get("ok") is True:
            self._state["stop_ok"] = True
            if self._state["session_released"] is not True:
                self._state["session_outstanding"] = True
            self._refresh()
        return result

    def retry_close(self, handle) -> dict:
        known = self._state["trace_handle"]
        if type(handle) is not int or handle != known or known is None:
            return {"ok": False, "code": "unknown_handle", "pending": False}
        if self._state["close_pending"] is True:
            # Pending CloseTrace is already with the original consumer.
            # Completing it after that consumer exits must not submit it again.
            if self._complete_pending_close_if_consumer_done():
                self._refresh()
                return {"ok": True, "code": "ok", "pending": False}
            return {"ok": False, "code": "close_pending", "pending": True}
        if self._state["close_ok"]:
            return {"ok": True, "code": "already_closed", "pending": False}
        result = self._api.close_trace(handle)
        if type(result) is not dict:
            return {"ok": False, "code": "close_failed", "pending": False}
        if result.get("pending") is True:
            self._state["close_pending"] = True
            self._state["close_ok"] = False
            self._state["trace_outstanding"] = True
            self._refresh()
            return result
        if result.get("ok") is True:
            self._state["close_ok"] = True
            self._state["close_pending"] = False
            self._state["trace_outstanding"] = False
            self._refresh()
        return result

    def _complete_pending_close_if_consumer_done(self) -> bool:
        trace = self._state["trace_handle"]
        if type(trace) is not int or self._state["close_pending"] is not True:
            return False
        note = getattr(self._api, "note_consumer_close_completed", None)
        if note is None or note(trace) is not True:
            return False
        release = getattr(self._api, "release_callbacks", None)
        if release is not None and release(trace) is False:
            return False
        self._state["close_pending"] = False
        self._state["close_ok"] = True
        self._state["trace_outstanding"] = False
        self._state["consumer_completed"] = True
        self._state["callbacks_released"] = True
        self._state["callback_outstanding"] = False
        return True

    def _live_view(self):
        view = getattr(self._api, "ownership_view", None)
        if view is None:
            return None
        found = view()
        if type(found) is not dict:
            return None
        return found

    def _refresh(self) -> None:
        self._complete_pending_close_if_consumer_done()
        view = self._live_view()
        control = self._state["control_handle"]
        trace = self._state["trace_handle"]
        if view is not None and control is not None and view.get("control_handle") == control:
            if view.get("stop_ok") is True:
                self._state["stop_ok"] = True
            if view.get("session_released") is True:
                self._state["session_released"] = True
                self._state["session_outstanding"] = False
        if view is not None and trace is not None and view.get("trace_handle") == trace:
            self._state["consumer_completed"] = view.get("consumer_completed") is True
            if view.get("close_ok") is True and view.get("close_pending") is not True:
                self._state["close_ok"] = True
                self._state["close_pending"] = False
                self._state["trace_outstanding"] = False
            if view.get("callbacks_released") is True and view.get("consumer_completed") is True:
                self._state["callbacks_released"] = True
                self._state["callback_outstanding"] = False
            elif (
                view.get("consumer_completed") is not True
                and self._state["callbacks_released"] is not True
            ):
                self._state["callback_outstanding"] = True
        if self._state["close_ok"] is True:
            self._state["close_pending"] = False
            self._state["trace_outstanding"] = False
        self._state["recoverable"] = bool(
            self._state["session_outstanding"]
            or self._state["trace_outstanding"]
            or self._state["callback_outstanding"]
        )
        self._state["isolated_cleanup_process"] = False


class AdapterOwnership:
    """One session's control and consumer handles.

    The loader runs only after the one-shot guard. Tests pass a fake loader.
    This class does not load advapi32 by itself.
    """

    def __init__(self, load_library):
        self._load_library = load_library
        self._library = None
        self._callback = None
        self._buffer_callback = None
        self._logfile = None
        self._logger_name = None
        self._properties_buffer = None
        self._session_name = None
        self._stop_result = None
        self._close_result = None
        self._start_attempted = False
        self._open_attempted = False
        self._control_handle = None
        self._consumer_handle = None
        self._consumer_completed = False
        self._session_released = False
        self.private_owner = None

    def _session_accepts_open(self) -> bool:
        """True only for a control session this object started and has not stopped."""
        if self._library is None:
            return False
        if type(self._control_handle) is not int or self._control_handle <= 0:
            return False
        if self._session_released is True:
            return False
        if type(self._stop_result) is dict and self._stop_result.get("ok") is True:
            return False
        return True

    def _consumer_handle_usable(self, trace_handle) -> bool:
        if type(trace_handle) is not int or trace_handle <= 0:
            return False
        if trace_handle != self._consumer_handle or self._consumer_handle is None:
            return False
        if self._library is None or self._consumer_completed is True:
            return False
        if type(self._close_result) is dict and (
            self._close_result.get("ok") is True or self._close_result.get("pending") is True
        ):
            return False
        return True

    def start_session(self, request: dict) -> dict:
        if self._start_attempted:
            return {"ok": False, "code": "session_already_attempted", "handle": None}
        if type(request) is not dict or request.get("session_name") != SESSION_NAME:
            return {"ok": False, "code": "invalid_session", "handle": None}
        if request.get("session_name") == KERNEL_LOGGER_NAME or request.get("etl_file") is True:
            return {"ok": False, "code": "invalid_session", "handle": None}
        if request.get("stop_existing_session") is True or request.get("privilege_escalation") is True:
            return {"ok": False, "code": "invalid_session", "handle": None}
        self._start_attempted = True
        global native_session_starts
        native_session_starts += 1
        library = self._load_library()
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
            if code == 183:
                return {"ok": False, "code": "already_exists", "handle": None}
            if code == 5:
                return {"ok": False, "code": "access_denied", "handle": None}
            return {"ok": False, "code": f"start_{code:x}", "handle": None}
        self._properties_buffer = buffer
        self._session_name = name
        self._control_handle = int(handle.value)
        return {"ok": True, "code": "ok", "handle": self._control_handle}

    def open_trace(self, session_name: str, on_event) -> dict:
        if self._open_attempted or self._callback is not None or self._consumer_handle is not None:
            return {"ok": False, "code": "open_already_attempted", "handle": None}
        # Failed or stopped StartTrace must refuse before callbacks, the
        # library, or OpenTrace. A loaded DLL is not an owned session.
        if session_name != SESSION_NAME or not self._session_accepts_open():
            return {"ok": False, "code": "open_trace_failed", "handle": None}
        self._open_attempted = True
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
        self._consumer_handle = handle
        return {"ok": True, "code": "ok", "handle": handle}

    def process_trace(self, trace_handle, on_ready) -> dict:
        # Ready is the consumer's signal that ProcessTrace is about to run.
        # A foreign or null handle must not signal it and must not reach the call.
        if not self._consumer_handle_usable(trace_handle):
            return {"ok": False, "code": "process_trace_failed"}
        on_ready()
        array = (ctypes.c_ulonglong * 1)(int(trace_handle))
        self._library.ProcessTrace.argtypes = [
            ctypes.POINTER(ctypes.c_ulonglong),
            wintypes.ULONG,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self._library.ProcessTrace.restype = wintypes.ULONG
        try:
            code = int(self._library.ProcessTrace(array, 1, None, None))
        finally:
            self._consumer_completed = True
        if code != 0:
            return {"ok": False, "code": f"process_{code:x}"}
        return {"ok": True, "code": "ok"}

    def stop_session(self, session_handle) -> dict:
        """Stop the handle this object started. The session name is not used.

        A successful stop is remembered for this control handle only. The
        handle is checked before that cache and before StopTraceW. A failed
        stop keeps the property buffer. Another handle is not stopped.
        """
        if (
            type(session_handle) is not int
            or session_handle != self._control_handle
            or self._control_handle is None
        ):
            return {"ok": False, "code": "unknown_handle", "loss": {}}
        if self._stop_result is not None and self._stop_result.get("ok") is True:
            return {
                "ok": True,
                "code": "already_stopped",
                "loss": dict(self._stop_result["loss"]),
            }
        if self._library is None or self._properties_buffer is None:
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
        self._stop_result = {"ok": True, "code": "ok", "loss": loss}
        return {"ok": True, "code": "ok", "loss": dict(loss)}

    def close_trace(self, trace_handle) -> dict:
        """Close the consumer handle and return the CloseTrace result.

        Callbacks are not dropped here. ERROR_CTX_CLOSE_PENDING means
        ProcessTrace may still invoke them. release_callbacks is separate
        and only safe after the consumer thread is confirmed finished.
        Success and pending are not submitted again. A hard failure is not
        cached. The acquired consumer handle is checked before the cache and
        before CloseTrace.
        """
        if (
            type(trace_handle) is not int
            or trace_handle != self._consumer_handle
            or self._consumer_handle is None
        ):
            return {"ok": False, "code": "unknown_handle", "pending": False}
        if self._close_result is not None and (
            self._close_result.get("ok") is True or self._close_result.get("pending") is True
        ):
            return dict(self._close_result)
        if self._library is None:
            return {"ok": False, "code": "close_failed", "pending": False}
        self._library.CloseTrace.argtypes = [ctypes.c_ulonglong]
        self._library.CloseTrace.restype = wintypes.ULONG
        code = int(self._library.CloseTrace(ctypes.c_ulonglong(int(trace_handle))))
        result = interpret_close_trace(code)
        if result.get("ok") is True or result.get("pending") is True:
            self._close_result = dict(result)
        return dict(result)

    def retain_recovery(self, state) -> None:
        """Remember the first outstanding owner. Not a receipt field.

        A refused or empty wrapper has no acquired handle. It must not replace
        an outstanding owner, and a foreign handle is not adopted.
        """
        if type(state) is not dict:
            return
        control = state.get("control_handle")
        trace = state.get("trace_handle")
        control_known = type(control) is int and control > 0
        trace_known = type(trace) is int and trace > 0
        if control_known and control != self._control_handle:
            return
        if trace_known and trace != self._consumer_handle:
            return
        if not control_known and not trace_known:
            return
        if self.private_owner is not None:
            return
        self.private_owner = LocalCleanupOwner(self, state)

    def release_callbacks(self, trace_handle=None) -> bool:
        """Drop callbacks only for the consumer that acquired this trace.

        The consumer must already have finished. A new observer with no thread
        does not pass that consumer's handle and cannot clear its storage.
        """
        if (
            type(trace_handle) is not int
            or trace_handle != self._consumer_handle
            or self._consumer_handle is None
            or self._consumer_completed is not True
        ):
            return False
        self._drop_callbacks()
        return True

    def note_consumer_close_completed(self, trace_handle) -> bool:
        """Mark a pending CloseTrace complete after that consumer has exited.

        CloseTrace is not called again.
        """
        if (
            type(trace_handle) is not int
            or trace_handle != self._consumer_handle
            or self._consumer_handle is None
            or self._consumer_completed is not True
        ):
            return False
        close = self._close_result
        if type(close) is not dict:
            return False
        if close.get("ok") is True and close.get("pending") is not True:
            return True
        if close.get("pending") is True:
            self._close_result = {"ok": True, "code": "ok", "pending": False}
            return True
        return False

    def ownership_view(self) -> dict:
        """Live ownership of this acquisition. Not a resource receipt."""
        stop_ok = type(self._stop_result) is dict and self._stop_result.get("ok") is True
        close = self._close_result if type(self._close_result) is dict else {}
        callbacks_released = (
            self._consumer_completed is True
            and self._consumer_handle is not None
            and self._callback is None
            and self._buffer_callback is None
            and self._logfile is None
        )
        return {
            "control_handle": self._control_handle,
            "trace_handle": self._consumer_handle,
            "stop_ok": stop_ok,
            "close_ok": close.get("ok") is True and close.get("pending") is not True,
            "close_pending": close.get("pending") is True,
            "session_released": self._session_released is True,
            "callbacks_released": callbacks_released,
            "consumer_completed": self._consumer_completed is True,
        }

    def close_session(self, session_handle) -> dict:
        """Drop the owned property buffer only after this object's stop succeeded.

        A failed stop keeps the buffer. The control handle is checked before
        the buffer is dropped. This does not call StopTraceW and does not
        address a logger by name.
        """
        if (
            type(session_handle) is not int
            or session_handle != self._control_handle
            or self._control_handle is None
        ):
            return {"ok": False, "code": "unknown_handle"}
        if self._stop_result is None or self._stop_result.get("ok") is not True:
            return {"ok": False, "code": "session_still_owned"}
        if self._session_released:
            return {"ok": True, "code": "ok"}
        self._properties_buffer = None
        self._session_name = None
        self._session_released = True
        return {"ok": True, "code": "ok"}

    def _new_logfile(self, on_event):
        # A second open must not build a replacement callback pair.
        if self._callback is not None or self._buffer_callback is not None:
            return self._logfile
        # The consumer structure is built only after start_session. A failure
        # before OpenTrace never publishes a callback.
        record_callback = ctypes.WINFUNCTYPE(None, ctypes.POINTER(_EVENT_RECORD))
        buffer_callback = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)

        def _record(pointer):
            def convert():
                return _record_to_dict(pointer.contents)

            def deliver(event):
                on_event(event)

            try:
                bridge_event(convert, deliver)
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


class WinEtwApi(AdapterOwnership):
    """Real advapi32 session. Constructing it loads nothing until start_session.

    An existing logger is never stopped. Access denial does not elevate.
    Offline tests construct AdapterOwnership with a fake loader instead.
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
        AdapterOwnership.__init__(self, _load_advapi32)


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


