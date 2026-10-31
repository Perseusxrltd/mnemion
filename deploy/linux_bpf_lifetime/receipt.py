"""Fixed-size receipt validator for the Linux lifetime diagnostic.

The numeric contract is lifetime_receipt.h and lifetime_abi.h. This module
recomputes admission, census, scenario and coverage. known_fixture_births is
not an input to those verdicts. resource_acceptance and
budget_comparison_allowed stay false.
"""

from __future__ import annotations

import ctypes
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_ABI = (_ROOT / "lifetime_abi.h").read_text(encoding="utf-8")
_HEADER = (_ROOT / "lifetime_receipt.h").read_text(encoding="utf-8")

_DEFINE = re.compile(r"#define\s+(LIFETIME_[A-Z0-9_]+)\s+(0x[0-9A-Fa-f]+|[0-9]+)u?\b")
_FIELD = re.compile(
    r"(uint8_t|uint32_t|uint64_t|struct lifetime_summary)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?;"
)


def _defines(text: str) -> dict[str, int]:
    found = {}
    for line in text.splitlines():
        match = _DEFINE.match(line.strip())
        if match:
            found[match.group(1)] = int(match.group(2), 0)
    return found


CONST = _defines(_ABI)
CONST.update(_defines(_HEADER))


def _array(name: str) -> list[int]:
    match = re.search(rf"static const uint32_t {name}\[\] = \{{([^}}]+)\}};", _HEADER)
    if match is None:
        raise RuntimeError(name)
    return [CONST[item] for item in re.findall(r"LIFETIME_[A-Z0-9_]+", match.group(1))]


CENSUS_CTRS = _array("LIFETIME_CENSUS_CTRS")
INFO_CTRS = _array("LIFETIME_INFO_CTRS")


def _struct_fields(name: str) -> list[tuple[str, str, int | None]]:
    match = re.search(rf"struct {name} \{{(.*?)\n\}}", _HEADER, re.S)
    if match is None:
        raise RuntimeError(name)
    fields = []
    for raw in match.group(1).splitlines():
        line = raw.split("//")[0].strip()
        if not line:
            continue
        found = _FIELD.match(line)
        if found is None:
            raise RuntimeError("unparsed receipt field: " + line)
        count = int(found.group(3)) if found.group(3) else None
        fields.append((found.group(1), found.group(2), count))
    return fields


def _ctype(kind: str, count: int | None, summary: type | None) -> type:
    base = {
        "uint8_t": ctypes.c_uint8,
        "uint32_t": ctypes.c_uint32,
        "uint64_t": ctypes.c_uint64,
        "struct lifetime_summary": summary,
    }[kind]
    if count is not None:
        return base * count
    return base


def _structure(name: str, fields: list[tuple[str, str, int | None]], summary: type | None) -> type:
    class Packed(ctypes.LittleEndianStructure):
        _pack_ = 1
        _fields_ = [(field, _ctype(kind, count, summary)) for kind, field, count in fields]

    Packed.__name__ = name
    return Packed


Summary = _structure("lifetime_summary", _struct_fields("lifetime_summary"), None)
Receipt = _structure("lifetime_receipt", _struct_fields("lifetime_receipt"), Summary)


def page_size_ok(page_size: int) -> bool:
    return 4096 <= page_size <= 65536 and (page_size & (page_size - 1)) == 0


def pages_to_bytes(pages: int, page_size: int) -> int | None:
    if not page_size_ok(page_size):
        return None
    if pages < 0 or pages > (2**64 - 1) // page_size:
        return None
    return pages * page_size


def _counter(receipt: Receipt, name: str) -> int:
    return int(receipt.counters[CONST[name]])


def admission_failure(receipt: Receipt) -> int:
    caps_ok = (receipt.cap_bpf and receipt.cap_perfmon) or receipt.cap_sys_admin
    if receipt.arch not in (CONST["LIFETIME_ARCH_X86_64"], CONST["LIFETIME_ARCH_AARCH64"]):
        return CONST["LIFETIME_REASON_ARCH"]
    if not receipt.page_size_ok or not page_size_ok(int(receipt.page_size)):
        return CONST["LIFETIME_REASON_PAGE_SIZE"]
    if not receipt.btf_ok:
        return CONST["LIFETIME_REASON_BTF"]
    if not receipt.prototype_ok:
        return CONST["LIFETIME_REASON_PROTOTYPE"]
    if not receipt.config_taskstats or not receipt.config_cgroups:
        return CONST["LIFETIME_REASON_CONFIG"]
    if not caps_ok:
        return CONST["LIFETIME_REASON_PRIVILEGE"]
    if receipt.lockdown_blocks:
        return CONST["LIFETIME_REASON_LOCKDOWN"]
    if not receipt.recursion_field_ok:
        return CONST["LIFETIME_REASON_RECURSION_FIELD"]
    allowed_clear = (CONST["LIFETIME_CLEAR_ABSENT"], CONST["LIFETIME_CLEAR_ATTACHED"])
    if receipt.clear_refs_state not in allowed_clear:
        return CONST["LIFETIME_REASON_CLEAR_REFS"]
    if not receipt.cgroup_ok:
        return CONST["LIFETIME_REASON_CGROUP"]
    if not receipt.cgroup_kill_ok:
        return CONST["LIFETIME_REASON_CGROUP_KILL"]
    if not receipt.populated_ok:
        return CONST["LIFETIME_REASON_POPULATED"]
    if not receipt.clone3_ok or not receipt.direct_launch_ok:
        return CONST["LIFETIME_REASON_DIRECT_LAUNCH"]
    if not receipt.cpu_stat_ok:
        return CONST["LIFETIME_REASON_CPU_STAT"]
    if not receipt.links_verified:
        return CONST["LIFETIME_REASON_LINK"]
    if receipt.launch_path != CONST["LIFETIME_LAUNCH_CLONE3"]:
        return CONST["LIFETIME_REASON_LAUNCH_PATH"]
    if receipt.containment != CONST["LIFETIME_CONTAIN_CGROUP_KILL"] or not receipt.containment_ok:
        return CONST["LIFETIME_REASON_CONTAINMENT"]
    if not receipt.enabled_after_validation:
        return CONST["LIFETIME_REASON_ATTACH"]
    return CONST["LIFETIME_REASON_NONE"]


def _summary_bytes_match(receipt: Receipt, summary: Summary) -> bool:
    converted = pages_to_bytes(int(summary.maxrss_pages), int(receipt.page_size))
    return converted is not None and converted == int(summary.maxrss_bytes)


def census_failure(receipt: Receipt) -> int:
    counters = receipt.counters
    if not receipt.fixture_launched or not receipt.collection_enabled:
        return CONST["LIFETIME_REASON_CENSUS"]
    if receipt.collector_death:
        return CONST["LIFETIME_REASON_COLLECTOR_DEATH"]
    if receipt.observation_failed:
        return CONST["LIFETIME_REASON_CENSUS"]
    if receipt.migration_outside or counters[CONST["LIFETIME_CTR_MIGRATION_EVENTS"]]:
        return CONST["LIFETIME_REASON_MIGRATION"]
    if receipt.detach_or_loss or counters[CONST["LIFETIME_CTR_DETACH_EVENTS"]]:
        return CONST["LIFETIME_REASON_DETACH"]
    if receipt.possible_peak_reset or counters[CONST["LIFETIME_CTR_RESET_EVENTS"]]:
        return CONST["LIFETIME_REASON_RESET"]
    if (
        not receipt.recursion_field_ok
        or not receipt.recursion_final_ok
        or counters[CONST["LIFETIME_CTR_RECURSION_MISS_DELTA"]]
    ):
        return CONST["LIFETIME_REASON_MISS"]
    if receipt.byte_overflow or counters[CONST["LIFETIME_CTR_BYTE_OVERFLOW"]]:
        return CONST["LIFETIME_REASON_BYTES"]
    if receipt.active_tasks or receipt.active_groups:
        return CONST["LIFETIME_REASON_CENSUS"]
    if not receipt.cpu_aggregate_ok or not receipt.page_size_ok or not page_size_ok(int(receipt.page_size)):
        return CONST["LIFETIME_REASON_CENSUS"]
    if (
        counters[CONST["LIFETIME_CTR_TASK_OVERFLOW"]]
        or counters[CONST["LIFETIME_CTR_GROUP_OVERFLOW"]]
        or counters[CONST["LIFETIME_CTR_COMPLETED_OVERFLOW"]]
        or counters[CONST["LIFETIME_CTR_COOKIE_OVERFLOW"]]
    ):
        return CONST["LIFETIME_REASON_OVERFLOW"]
    allow = [0] * CONST["LIFETIME_CTR_COUNT"]
    for index in CENSUS_CTRS + INFO_CTRS:
        allow[index] = 1
    for index in range(CONST["LIFETIME_CTR_COUNT"]):
        if not allow[index] and counters[index]:
            return CONST["LIFETIME_REASON_MAP"]
    births = int(counters[CONST["LIFETIME_CTR_BIRTHS"]])
    exits = int(counters[CONST["LIFETIME_CTR_TASK_EXITS"]])
    group_births = int(counters[CONST["LIFETIME_CTR_GROUP_BIRTHS"]])
    group_finals = int(counters[CONST["LIFETIME_CTR_GROUP_FINALS"]])
    if births < 1 or births != exits:
        return CONST["LIFETIME_REASON_CENSUS"]
    if group_births < 1 or group_births != group_finals:
        return CONST["LIFETIME_REASON_CENSUS"]
    if int(receipt.summary_count) != births + group_finals:
        return CONST["LIFETIME_REASON_CENSUS"]
    if int(receipt.summary_count) > CONST["LIFETIME_SUMMARY_SLOTS"]:
        return CONST["LIFETIME_REASON_CENSUS"]
    tasks = 0
    groups = 0
    for index in range(int(receipt.summary_count)):
        summary = receipt.summaries[index]
        if int(summary.cookie) == 0:
            return CONST["LIFETIME_REASON_CENSUS"]
        if summary.overflow:
            return CONST["LIFETIME_REASON_BYTES"]
        if not _summary_bytes_match(receipt, summary):
            return CONST["LIFETIME_REASON_BYTES"]
        if summary.kind == CONST["LIFETIME_KIND_TASK"]:
            tasks += 1
            if int(summary.group_cookie) == 0:
                return CONST["LIFETIME_REASON_CENSUS"]
            if summary.category not in (
                CONST["LIFETIME_CATEGORY_PROCESS"],
                CONST["LIFETIME_CATEGORY_THREAD"],
                CONST["LIFETIME_CATEGORY_IO_THREAD"],
            ):
                return CONST["LIFETIME_REASON_CENSUS"]
        elif summary.kind == CONST["LIFETIME_KIND_GROUP"]:
            groups += 1
            if summary.category != 0 or int(summary.cookie) != int(summary.group_cookie):
                return CONST["LIFETIME_REASON_CENSUS"]
        else:
            return CONST["LIFETIME_REASON_CENSUS"]
    if tasks != births or groups != group_finals:
        return CONST["LIFETIME_REASON_CENSUS"]
    for index in range(int(receipt.summary_count), CONST["LIFETIME_SUMMARY_SLOTS"]):
        summary = receipt.summaries[index]
        if any(
            (
                summary.kind,
                summary.category,
                summary.exec_seen,
                summary.overflow,
                summary.cookie,
                summary.group_cookie,
                summary.creator_cookie,
                summary.maxrss_pages,
                summary.maxrss_bytes,
            )
        ):
            return CONST["LIFETIME_REASON_CENSUS"]
    return CONST["LIFETIME_REASON_NONE"]


def cover_mode(mode: int) -> bool:
    return CONST["LIFETIME_MODE_DIRECT"] <= mode <= CONST["LIFETIME_MODE_IO_URING"]


def scenario_ok(receipt: Receipt) -> bool:
    if receipt.collector_death or receipt.path_unsupported or receipt.observation_failed:
        return False
    if census_failure(receipt) != CONST["LIFETIME_REASON_NONE"]:
        return False
    if not cover_mode(int(receipt.mode)):
        return False
    births = _counter(receipt, "LIFETIME_CTR_BIRTHS")
    groups = _counter(receipt, "LIFETIME_CTR_GROUP_BIRTHS")
    process = thread = thread_exec = process_exec = peak = False
    for index in range(int(receipt.summary_count)):
        summary = receipt.summaries[index]
        if summary.kind == CONST["LIFETIME_KIND_GROUP"] and int(summary.maxrss_pages) > 0:
            peak = True
        if summary.kind != CONST["LIFETIME_KIND_TASK"]:
            continue
        if summary.category == CONST["LIFETIME_CATEGORY_PROCESS"]:
            process = True
            if summary.exec_seen:
                process_exec = True
        elif summary.category == CONST["LIFETIME_CATEGORY_THREAD"]:
            thread = True
            if summary.exec_seen:
                thread_exec = True
    mode = int(receipt.mode)
    if mode == CONST["LIFETIME_MODE_DIRECT"]:
        return process
    if mode == CONST["LIFETIME_MODE_NESTED"]:
        return births >= 3 and groups >= 3
    if mode == CONST["LIFETIME_MODE_ORPHAN"]:
        return births >= 2 and groups >= 2
    if mode == CONST["LIFETIME_MODE_THREAD"]:
        return thread and births >= 2
    if mode == CONST["LIFETIME_MODE_ALLOC"]:
        return peak
    if mode == CONST["LIFETIME_MODE_PRE_EXEC"]:
        return process_exec
    if mode == CONST["LIFETIME_MODE_NONLEADER_EXEC"]:
        return thread_exec and process
    if mode == CONST["LIFETIME_MODE_IO_URING"]:
        return bool(receipt.io_thread_seen)
    return False


def note_io_threads(receipt: Receipt) -> None:
    receipt.io_thread_seen = 0
    limit = min(int(receipt.summary_count), CONST["LIFETIME_SUMMARY_SLOTS"])
    for index in range(limit):
        summary = receipt.summaries[index]
        if (
            summary.kind == CONST["LIFETIME_KIND_TASK"]
            and summary.category == CONST["LIFETIME_CATEGORY_IO_THREAD"]
        ):
            receipt.io_thread_seen = 1


def apply_verdict(receipt: Receipt) -> None:
    receipt.resource_acceptance = 0
    receipt.budget_comparison_allowed = 0
    receipt.containment_scope = CONST["LIFETIME_SCOPE_NO_EXTERNAL_MIGRATION"]
    receipt.work_interval_ms = CONST["LIFETIME_WORK_MS"]
    receipt.cleanup_interval_ms = CONST["LIFETIME_CLEANUP_MS"]
    receipt.magic = CONST["LIFETIME_RECEIPT_MAGIC"]
    receipt.version = CONST["LIFETIME_RECEIPT_VERSION"]
    receipt.size = ctypes.sizeof(Receipt)
    note_io_threads(receipt)
    admission = admission_failure(receipt)
    receipt.support_admitted = int(admission == CONST["LIFETIME_REASON_NONE"])
    if not receipt.support_admitted:
        receipt.census_clean = 0
        receipt.scenario_qualified = 0
        receipt.coverage_pass = 0
        if receipt.reason == CONST["LIFETIME_REASON_NONE"]:
            receipt.reason = admission
        return
    if not receipt.fixture_launched or not receipt.collection_enabled:
        receipt.census_clean = 0
        receipt.scenario_qualified = 0
        receipt.coverage_pass = 0
        return
    census = census_failure(receipt)
    receipt.census_clean = int(census == CONST["LIFETIME_REASON_NONE"])
    receipt.scenario_qualified = int(scenario_ok(receipt))
    receipt.coverage_pass = int(
        receipt.census_clean
        and receipt.scenario_qualified
        and not receipt.path_unsupported
        and not receipt.collector_death
        and cover_mode(int(receipt.mode))
    )
    if not receipt.coverage_pass and receipt.reason == CONST["LIFETIME_REASON_NONE"]:
        if census != CONST["LIFETIME_REASON_NONE"]:
            receipt.reason = census
        elif receipt.collector_death:
            receipt.reason = CONST["LIFETIME_REASON_COLLECTOR_DEATH"]
        elif receipt.path_unsupported:
            receipt.reason = CONST["LIFETIME_REASON_UNSUPPORTED"]
        elif not receipt.scenario_qualified:
            receipt.reason = CONST["LIFETIME_REASON_SCENARIO"]


def mode_exit_ok(receipt: Receipt) -> bool:
    cleanup = receipt.cleanup_attempted and receipt.cleanup_pass
    overflow = any(
        (
            receipt.counters[CONST["LIFETIME_CTR_TASK_OVERFLOW"]],
            receipt.counters[CONST["LIFETIME_CTR_GROUP_OVERFLOW"]],
            receipt.counters[CONST["LIFETIME_CTR_COMPLETED_OVERFLOW"]],
            receipt.counters[CONST["LIFETIME_CTR_COOKIE_OVERFLOW"]],
        )
    )
    if not cleanup or receipt.resource_acceptance or receipt.budget_comparison_allowed:
        return False
    mode = int(receipt.mode)
    if mode == CONST["LIFETIME_MODE_ADMIT"]:
        return bool(receipt.support_admitted and not receipt.fixture_launched and not receipt.coverage_pass)
    if mode == CONST["LIFETIME_MODE_CAPACITY"]:
        return bool(not receipt.coverage_pass and overflow and not receipt.collector_death)
    if mode == CONST["LIFETIME_MODE_RESET"]:
        return bool(not receipt.coverage_pass and receipt.possible_peak_reset and not receipt.collector_death)
    if mode == CONST["LIFETIME_MODE_COLLECTOR_DEATH"]:
        return bool(not receipt.coverage_pass and receipt.collector_death and receipt.observation_failed)
    if mode == CONST["LIFETIME_MODE_IO_URING"]:
        if receipt.path_unsupported:
            return bool(receipt.fixture_launched and not receipt.coverage_pass and not receipt.scenario_qualified)
        return bool(receipt.coverage_pass and receipt.io_thread_seen)
    if not cover_mode(mode):
        return False
    return bool(receipt.coverage_pass and not receipt.collector_death)


def owned_group_peak_bytes(receipt: Receipt) -> int | None:
    peak = None
    limit = min(int(receipt.summary_count), CONST["LIFETIME_SUMMARY_SLOTS"])
    for index in range(limit):
        summary = receipt.summaries[index]
        if summary.kind != CONST["LIFETIME_KIND_GROUP"]:
            continue
        if summary.overflow:
            return None
        value = int(summary.maxrss_bytes)
        peak = value if peak is None else max(peak, value)
    return peak


def pack_receipt(receipt: Receipt) -> bytes:
    return bytes(receipt)


def _load(blob: bytes) -> Receipt:
    return Receipt.from_buffer_copy(blob)


def validate_receipt(blob: bytes) -> dict:
    errors = []
    if len(blob) != ctypes.sizeof(Receipt):
        return _verdict(False, ["short"], None)
    raw = _load(blob)
    if int(raw.magic) != CONST["LIFETIME_RECEIPT_MAGIC"]:
        errors.append("magic")
    if int(raw.version) != CONST["LIFETIME_RECEIPT_VERSION"]:
        errors.append("version")
    if int(raw.size) != CONST["LIFETIME_RECEIPT_BYTES"] or int(raw.size) != ctypes.sizeof(Receipt):
        errors.append("size")
    if raw.resource_acceptance != 0:
        errors.append("resource_acceptance")
    if raw.budget_comparison_allowed != 0:
        errors.append("budget_comparison_allowed")
    if int(raw.work_interval_ms) != CONST["LIFETIME_WORK_MS"]:
        errors.append("work_interval")
    if int(raw.cleanup_interval_ms) != CONST["LIFETIME_CLEANUP_MS"]:
        errors.append("cleanup_interval")
    derived = _load(blob)
    apply_verdict(derived)
    for name in (
        "support_admitted",
        "census_clean",
        "scenario_qualified",
        "coverage_pass",
        "reason",
        "containment_scope",
        "io_thread_seen",
    ):
        if getattr(raw, name) != getattr(derived, name):
            errors.append(name + "_mismatch")
    return _verdict(not errors, errors, raw)


def _verdict(ok: bool, errors: list[str], raw: Receipt | None) -> dict:
    return {
        "ok": ok,
        "errors": errors,
        "support_admitted": None if raw is None else int(raw.support_admitted),
        "coverage_pass": None if raw is None else int(raw.coverage_pass),
        "cleanup_pass": None if raw is None else int(raw.cleanup_pass),
        "census_clean": None if raw is None else int(raw.census_clean),
        "resource_acceptance": None if raw is None else int(raw.resource_acceptance),
        "budget_comparison_allowed": None if raw is None else int(raw.budget_comparison_allowed),
    }


def fill(receipt: Receipt, values: dict) -> Receipt:
    for key, value in values.items():
        if key == "counters":
            for index, item in value.items():
                receipt.counters[int(index)] = int(item)
        elif key == "summaries":
            for index, item in enumerate(value):
                summary = Summary()
                for field, field_value in item.items():
                    setattr(summary, field, field_value)
                receipt.summaries[index] = summary
        else:
            setattr(receipt, key, value)
    return receipt


def admitted_probe(**overrides) -> dict:
    probe = {
        "arch": CONST["LIFETIME_ARCH_X86_64"],
        "page_size": 4096,
        "page_size_ok": 1,
        "btf_ok": 1,
        "prototype_ok": 1,
        "config_taskstats": 1,
        "config_cgroups": 1,
        "cap_bpf": 1,
        "cap_perfmon": 1,
        "cap_sys_admin": 0,
        "lockdown_blocks": 0,
        "recursion_field_ok": 1,
        "clear_refs_state": CONST["LIFETIME_CLEAR_ABSENT"],
        "cgroup_ok": 1,
        "cgroup_kill_ok": 1,
        "populated_ok": 1,
        "clone3_ok": 1,
        "direct_launch_ok": 1,
        "cpu_stat_ok": 1,
        "links_verified": 1,
        "launch_path": CONST["LIFETIME_LAUNCH_CLONE3"],
        "containment": CONST["LIFETIME_CONTAIN_CGROUP_KILL"],
        "containment_ok": 1,
        "enabled_after_validation": 1,
    }
    probe.update(overrides)
    return probe


def assess_admission(probe: dict) -> dict:
    receipt = fill(Receipt(), probe)
    reason = admission_failure(receipt)
    return {
        "launch_allowed": reason == CONST["LIFETIME_REASON_NONE"],
        "reason": reason,
    }


def _task(cookie: int, group: int, category: int, pages: int = 0, exec_seen: int = 0) -> dict:
    return {
        "kind": CONST["LIFETIME_KIND_TASK"],
        "category": category,
        "exec_seen": exec_seen,
        "overflow": 0,
        "cookie": cookie,
        "group_cookie": group,
        "creator_cookie": 0,
        "maxrss_pages": pages,
        "maxrss_bytes": pages * 4096,
    }


def _group(cookie: int, pages: int = 0) -> dict:
    return {
        "kind": CONST["LIFETIME_KIND_GROUP"],
        "category": 0,
        "exec_seen": 0,
        "overflow": 0,
        "cookie": cookie,
        "group_cookie": cookie,
        "creator_cookie": 0,
        "maxrss_pages": pages,
        "maxrss_bytes": pages * 4096,
    }


def raw_direct() -> Receipt:
    receipt = fill(Receipt(), admitted_probe())
    fill(
        receipt,
        {
            "mode": CONST["LIFETIME_MODE_DIRECT"],
            "fixture_launched": 1,
            "collection_enabled": 1,
            "cpu_aggregate_ok": 1,
            "recursion_final_ok": 1,
            "cleanup_attempted": 1,
            "cleanup_pass": 1,
            "summary_count": 2,
            "summaries": [_task(1, 1, CONST["LIFETIME_CATEGORY_PROCESS"]), _group(1)],
            "counters": {
                CONST["LIFETIME_CTR_BIRTHS"]: 1,
                CONST["LIFETIME_CTR_TASK_EXITS"]: 1,
                CONST["LIFETIME_CTR_GROUP_BIRTHS"]: 1,
                CONST["LIFETIME_CTR_GROUP_FINALS"]: 1,
            },
        },
    )
    return receipt


def assess_observation(obs: dict) -> dict:
    receipt = raw_direct()
    fill(receipt, obs)
    receipt.reason = obs.get("reason", 0)
    apply_verdict(receipt)
    return {
        "support_admitted": int(receipt.support_admitted),
        "census_clean": int(receipt.census_clean),
        "scenario_qualified": int(receipt.scenario_qualified),
        "coverage_pass": int(receipt.coverage_pass),
        "reason": int(receipt.reason),
        "io_thread_seen": int(receipt.io_thread_seen),
        "cleanup_pass": int(receipt.cleanup_pass),
        "resource_acceptance": int(receipt.resource_acceptance),
        "budget_comparison_allowed": int(receipt.budget_comparison_allowed),
    }
