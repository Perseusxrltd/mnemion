"""Summarize retained real-renderer observations without replaying any workflow."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from mnemion.product_telemetry.wire_v3 import PACKET_BYTES

HISTORICAL_PACKET_BYTES = 4
HISTORICAL_WIRE_PATH = "/v1/report"
V3_WIRE_PATH = "/v3/report"


def process_role(row):
    return row.get("role", row["type"])


LINUX_FIELDS = ("VmRSS", "VmHWM", "RssAnon", "RssFile", "RssShmem")
HEAP_FIELDS = ("total_heap_size", "total_physical_size", "used_heap_size", "malloced_memory")
PHASE_MEMORY_FIELDS = LINUX_FIELDS + HEAP_FIELDS
PHASE_MEMORY_CHECKPOINTS = (
    "before_workspace_connect",
    "workspace_connected",
    "first_memory_cycle_and_delivery",
    "8_memory_cycles",
    "16_memory_cycles",
    "32_memory_cycles",
    "64_memory_cycles",
    "96_memory_cycles",
    "128_memory_cycles",
)


def counter_value(value):
    """Null stays unavailable. A boolean or other type is not a measurement."""
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError("Phase-memory counters must be non-negative integers or null")
    return value


def sample_counters(sample):
    row = sample.get("phase_memory") if isinstance(sample, dict) else None
    if (
        not isinstance(row, dict)
        or set(row) != {"linux", "heap"}
        or not isinstance(row.get("linux"), dict)
        or not isinstance(row.get("heap"), dict)
        or set(row["linux"]) != set(LINUX_FIELDS)
        or set(row["heap"]) != set(HEAP_FIELDS)
    ):
        raise ValueError("Phase-memory sample is missing its fixed counters")
    return {
        name: counter_value(row["linux"][name] if name in LINUX_FIELDS else row["heap"][name])
        for name in PHASE_MEMORY_FIELDS
    }


WIRE_FIELDS = ("wire_version", "packet_bytes", "wire_path")
REVIEW_CHUNK_BOUND = 8


def explicit_wire_contract(row):
    """Return a complete contract, or None when the row has no wire metadata."""
    if not isinstance(row, dict):
        raise ValueError("Telemetry wire metadata must be on an object")
    present = [key for key in WIRE_FIELDS if key in row]
    if not present:
        return None
    if len(present) != len(WIRE_FIELDS):
        raise ValueError("Telemetry wire metadata must be complete or absent")
    version, packet, path = (row[key] for key in WIRE_FIELDS)
    if type(version) is not int or version not in (2, 3):
        raise ValueError("Telemetry wire version must be historical v2 or v3")
    expected = (
        (2, HISTORICAL_PACKET_BYTES, HISTORICAL_WIRE_PATH)
        if version == 2
        else (3, PACKET_BYTES, V3_WIRE_PATH)
    )
    if (version, packet, path) != expected:
        raise ValueError("Telemetry wire metadata conflicts with its declared version")
    return {
        "wire_version": version,
        "wire_label": "historical-v2" if version == 2 else "v3",
        "wire_path": path,
        "packet_bytes": packet,
    }


def describe_diagnostic_wire(receipt):
    """Label a receipt. Missing metadata is historical v2, never an implied v3 run."""
    if not isinstance(receipt, dict):
        raise ValueError("Telemetry wire metadata must be on an object")
    receipt_wire = explicit_wire_contract(receipt)
    results = receipt.get("results") or []
    if not isinstance(results, list):
        raise ValueError("Telemetry results must be a list")
    case_wires = []
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("Telemetry results must be objects")
        case_wires.append(explicit_wire_contract(result))
    if receipt_wire is None:
        if any(case is not None for case in case_wires):
            raise ValueError("Historical v2 receipts cannot carry explicit wire metadata")
        return explicit_wire_contract(
            {
                "wire_version": 2,
                "packet_bytes": HISTORICAL_PACKET_BYTES,
                "wire_path": HISTORICAL_WIRE_PATH,
            }
        )
    if any(case != receipt_wire for case in case_wires):
        raise ValueError("Each diagnostic case must identify the same wire contract as its receipt")
    return receipt_wire


def absorb_reviewed_chunk(captured, chunks_kept, chunk):
    """Stop and clear a review body once it leaves the 25-byte, 8-chunk contract."""
    chunks_kept += 1
    if (
        captured is None
        or type(chunk) is not bytes
        or chunks_kept > REVIEW_CHUNK_BOUND
        or len(captured) + len(chunk) > PACKET_BYTES
    ):
        if captured is not None:
            captured.clear()
        return None, chunks_kept
    captured.extend(chunk)
    return captured, chunks_kept


def retain_reviewed_packet(chunks, *, review):
    """Hex of one exact synthetic v3 packet. Anything else, including a prefix, is dropped."""
    if not review:
        return None
    body = bytearray()
    for chunk in chunks:
        if type(chunk) is not bytes or len(body) + len(chunk) > PACKET_BYTES:
            return None
        body.extend(chunk)
    if len(body) != PACKET_BYTES:
        return None
    encoded = bytes(body).hex()
    body.clear()
    return encoded


def verify_phase_memory(result, *, required=False):
    """Reject unlabelled counters. Valid absence is None, not a failed check."""
    samples = result.get("samples") if isinstance(result, dict) else None
    carried = result.get("phase_memory") is True or any(
        isinstance(sample, dict) and "phase_memory" in sample for sample in samples or []
    )
    if not required:
        if carried:
            raise ValueError("Unprofiled results cannot carry phase-memory counters")
        return None
    if result.get("phase_memory") is not True or result.get("comparison") is not True:
        raise ValueError("Phase-memory comparison is missing its explicit result flag")
    if (result.get("allocation") or {}).get("enabled") is not False:
        raise ValueError("Phase-memory comparison cannot enable allocation attribution")
    if not isinstance(samples, list) or [sample.get("name") for sample in samples] != list(
        PHASE_MEMORY_CHECKPOINTS
    ):
        raise ValueError("Phase-memory comparison requires the nine declared checkpoints")
    for sample in samples:
        sample_counters(sample)
    return True


def aligned_phase_memory(baseline, current):
    """Match the same checkpoints. Null is unavailable, not a zero cost."""
    if len({row["name"] for row in baseline}) != len(baseline) or len(
        {row["name"] for row in current}
    ) != len(current):
        raise ValueError("Duplicate workload phases cannot be aligned")
    if not baseline or not current or baseline[0]["name"] != current[0]["name"]:
        raise ValueError("Aligned comparisons require the same initial workload phase")
    before = {row["name"]: sample_counters(row) for row in baseline}
    after = {row["name"]: sample_counters(row) for row in current}
    base_start, current_start = before[baseline[0]["name"]], after[current[0]["name"]]
    phases = []
    for row in baseline:
        name = row["name"]
        if name not in after:
            continue
        difference = {}
        for field in PHASE_MEMORY_FIELDS:
            values = (
                after[name][field],
                current_start[field],
                before[name][field],
                base_start[field],
            )
            difference[field] = (
                None
                if any(value is None for value in values)
                else values[0] - values[1] - values[2] + values[3]
            )
        phases.append({"phase": name, "difference_growth_bytes": difference})
    return {
        "phases": phases,
        "unmatched_phases": sorted(set(before) ^ set(after)),
        "scope": (
            "Main-process checkpoint counters only. Null is unavailable, not zero. "
            "Not a working-set replacement, a callsite attribution, or resource acceptance."
        ),
    }


def verify_setup_controls(result, *, required=False):
    """Require real native settings replies, separately from memory API success."""
    controls = result.get("setup_controls")
    if controls is None and not required:
        return False
    condition = result.get("condition", result.get("variant"))
    if (
        condition not in {"unavailable", "opted_out", "enabled"}
        or not isinstance(controls, dict)
        or set(controls)
        != {
            "schema_version",
            "attempts",
            "completed",
            "failed",
            "in_flight",
            "overflow",
            "replies",
        }
        or type(controls["schema_version"]) is not int
        or controls["schema_version"] != 1
        or controls["overflow"] is not False
        or any(
            type(controls[name]) is not int or not 0 <= controls[name] <= 16
            for name in ("attempts", "completed", "failed", "in_flight")
        )
        or controls["failed"] != 0
        or controls["in_flight"] != 0
        or not isinstance(controls["replies"], list)
        or controls["attempts"] != controls["completed"]
        or controls["completed"] != len(controls["replies"])
        or (controls["attempts"] == 0) != (condition == "unavailable")
    ):
        raise ValueError("Native setup control evidence is missing, failed or unfinished")
    expected = {
        "schema_version": 1,
        "user_enabled": condition == "enabled",
        "effective_enabled": condition == "enabled",
        "collection_available": True,
        "storage": "ready",
        "reason": "enabled" if condition == "enabled" else "user_disabled",
        "connection_mode": "unmetered",
        # Opt-out revokes acknowledgment as well as permission. Requiring a
        # retained acknowledgment would reject the actual privacy policy.
        "disclosure_acknowledged": condition == "enabled",
        "store_generation_valid": True,
    }
    for reply in controls["replies"]:
        if (
            not isinstance(reply, dict)
            or set(reply) != set(expected)
            or any(
                type(reply[name]) is not type(value) or reply[name] != value
                for name, value in expected.items()
            )
        ):
            raise ValueError("Native setup control did not confirm the declared privacy state")
    return True


def verify_process_ownership(samples, *, required=False):
    """Cross-check recorded owners against every process row, not a success flag."""
    if not samples or not any("ownership" in sample for sample in samples):
        if required:
            raise ValueError("Resource comparison requires actual app process ownership")
        return False
    original = None
    for sample in samples:
        owner = sample.get("ownership", {})
        pair = (owner.get("main_pid"), owner.get("renderer_pid"))
        processes = sample["processes"]
        pids = [row["pid"] for row in processes]
        main = [row for row in processes if row["type"] == "Browser"]
        renderers = [row for row in processes if row["type"] == "Tab"]
        if (
            owner.get("schema_version") != 1
            or owner.get("valid") is not True
            or owner.get("app_windows") != 1
            or owner.get("all_windows") != 1
            or owner.get("devtools_present") is not False
            or owner.get("renderer_processes") != 1
            or any(type(pid) is not int or pid <= 0 for pid in pair)
            or pair[0] == pair[1]
            or len(set(pids)) != len(pids)
            or len(main) != 1
            or len(renderers) != 1
            or (main[0]["pid"], renderers[0]["pid"]) != pair
            or main[0].get("role") != "app_main"
            or renderers[0].get("role") != "app_renderer"
            or (original is not None and pair != original)
        ):
            raise ValueError("App process ownership is missing, ambiguous or changed")
        original = pair
    return True


def aligned_rss_growth(baseline, current):
    """Compare the same phases, not maxima that can occur at different times."""
    before = {row["name"]: row for row in baseline}
    after = {row["name"]: row for row in current}
    if len(before) != len(baseline) or len(after) != len(current):
        raise ValueError("Duplicate workload phases cannot be aligned")
    if not baseline or not current or baseline[0]["name"] != current[0]["name"]:
        raise ValueError("Aligned comparisons require the same initial workload phase")
    phases = [row["name"] for row in baseline if row["name"] in after]
    role_sets = [
        {process_role(row) for row in sample["processes"]} for sample in (baseline[0], current[0])
    ]
    roles = role_sets[0] & role_sets[1]
    rows, ambiguous = [], []
    for role in sorted(roles):
        starts = [
            [row for row in sample["processes"] if process_role(row) == role]
            for sample in (baseline[0], current[0])
        ]
        if any(len(values) != 1 for values in starts):
            ambiguous.append(role)
            continue
        base_start, current_start = starts[0][0], starts[1][0]
        observations = []
        for phase in phases:
            selected = [
                [row for row in sample["processes"] if process_role(row) == role]
                for sample in (before[phase], after[phase])
            ]
            if any(len(values) != 1 for values in selected):
                continue
            base_row, current_row = selected[0][0], selected[1][0]
            if base_row["pid"] != base_start["pid"] or current_row["pid"] != current_start["pid"]:
                continue
            observations.append(
                {
                    "phase": phase,
                    "difference_rss_growth_bytes": (
                        current_row["working_set_bytes"]
                        - current_start["working_set_bytes"]
                        - base_row["working_set_bytes"]
                        + base_start["working_set_bytes"]
                    ),
                }
            )
        rows.append(
            {
                "type": base_start["type"],
                "role": role,
                "phases": observations,
                "maximum_matched_growth_difference_bytes": max(
                    (row["difference_rss_growth_bytes"] for row in observations), default=None
                ),
                "all_phases_matched": len(observations) == len(baseline) == len(current),
            }
        )
    return {
        "processes": rows,
        "ambiguous_initial_types": ambiguous,
        "unmatched_initial_roles": sorted(role_sets[0] ^ role_sets[1]),
        "unmatched_phases": sorted(set(before) ^ set(after)),
        "scope": "Matched sampled growth only; not an unsampled peak or a causal telemetry allocation.",
    }


def allocation_windows(result):
    allocation = result.get("allocation", {})
    if not allocation.get("enabled"):
        return []
    samples = {row["name"]: row for row in allocation["samples"]}
    pairs = [
        (
            "telemetry_imports",
            "bootstrap.before_telemetry_imports",
            "bootstrap.after_telemetry_imports",
        ),
        *[
            (name, name + ".before", name + ".after")
            for name in (
                "sqlite.open",
                "sqlite.close",
                "network_cost.start",
                "conditions.prepare",
                "delivery.reserve",
            )
        ],
        ("transport", "transport.before_connect", "transport.after_close"),
    ]
    rows = []
    for name, before, after in pairs:
        if before not in samples or after not in samples:
            continue
        start, end = samples[before], samples[after]
        residency = {}
        for key in ("VmRSS", "VmHWM", "RssAnon", "RssFile", "RssShmem"):
            values = start.get("linux", {}).get(key), end.get("linux", {}).get(key)
            residency[key] = (
                values[1] - values[0] if all(isinstance(value, int) for value in values) else None
            )
        rows.append(
            {
                "name": name,
                "elapsed_ms": end["monotonic_ms"] - start["monotonic_ms"],
                "process_memory_changes": {
                    key: end["main"][key] - start["main"][key]
                    for key in ("rss", "heapTotal", "heapUsed", "external", "arrayBuffers")
                },
                "linux_residency_changes": residency,
                "scope": "Profiled first-call window, possibly overlapping other work; not isolated component cost.",
            }
        )
    return rows


_OWNED_PHASE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,80}\Z")
_IDENTITY = re.compile(r"[0-9]{1,10}:[0-9]{1,20}\Z")
_FRACTION = re.compile(r"[0-9]{1,6}\.[0-9]{6}\Z")
_OWNED_ACTIVE = {
    "measuring",
    "before-workspace-connect",
    "workspace-connected",
    "first-memory-cycle-and-delivery",
}
_OWNED_INACTIVE = {"starting", "finished", "closed", "failed"}
# Terminal markers carry the verified cumulative count. Starting does not.
_TERMINAL = {"finished", "closed", "failed"}
# A transient service gets a clean environment. These are the runner
# tool and home values the fixture needs. Tokens and the rest of the
# job environment are not copied.
_SERVICE_ENV = (
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "PATH",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USER",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_RUNTIME_DIR",
)
# Names the installed desktop session may keep. Tokens are not in this list.
# A transient service starts from a clean environment, so an omitted name is absent.
_DESKTOP_ENV = (
    "CI",
    "RUNNER_OS",
    "RUNNER_ARCH",
    "RUNNER_TEMP",
    "DBUS_SESSION_BUS_ADDRESS",
    "DISPLAY",
    "XAUTHORITY",
    "GNOME_KEYRING_CONTROL",
    "MNEMION_ENGINE_PYTHON",
    "MNEMION_BUILD_PYTHON",
    "MNEMION_POSTGRES_ARCHIVES",
    "MNEMION_ENGINE_ARCHIVES",
    "MNEMION_ENGINE_ARCHIVES_INACTIVE",
    "MNEMION_OWNED_LAUNCH_PYTHON",
    "MNEMION_TELEMETRY_INSTALLED_RESOURCE",
    "MNEMION_TELEMETRY_FIXTURE_ENDPOINT",
    "MNEMION_TELEMETRY_FIXTURE_SPACE",
    "MNEMION_TELEMETRY_FIXTURE_KEY",
    "MNEMION_TELEMETRY_RESOURCE_MANIFEST",
    "MNEMION_TELEMETRY_RESOURCE_PROBE",
    "MNEMION_TELEMETRY_RESOURCE_ADMISSION",
)
INSTALLED_DESKTOP_ENV = _SERVICE_ENV + _DESKTOP_ENV


class OwnedPhaseCursor:
    def __init__(self):
        self.seen = None
        self.completed = 0
        self.completed_known = False
        self.have_lower_bound = False
        self.rejected = None
        self.marker_failed = False
        self.observation_failure = None
        self.terminal_seen = False


def owned_counterbalance(attribution: bool, comparison: bool) -> bool:
    """The existing six-launch order. Review and the three-case journey stay outside it."""
    return bool(attribution or comparison) and not (attribution and comparison)


def renderer_launch_cases(
    *, attribution: bool, comparison: bool, review_journey: bool
) -> list[tuple]:
    """The existing launch order. Comparison is one triplet and its reverse."""
    triplet = [
        ("unavailable", False, False),
        ("opted_out", True, False),
        ("enabled", True, True),
    ]
    if review_journey:
        return [("review", "review", True, True, 1)]
    if attribution or comparison:
        return [
            (f"r{replicate}-{label}", label, available, enabled, replicate)
            for replicate, order in [(1, triplet), (2, list(reversed(triplet)))]
            for label, available, enabled in order
        ]
    return [(label, label, available, enabled, 1) for label, available, enabled in triplet]


def resource_counterbalance_cases() -> list[dict]:
    """Installed packages for the same six launches. Unavailable is a separate build."""
    cases = []
    for label, condition, available, enabled, replicate in renderer_launch_cases(
        attribution=False, comparison=True, review_journey=False
    ):
        cases.append(
            {
                "label": label,
                "condition": condition,
                "available": available,
                "enabled": enabled,
                "replicate": replicate,
                "package": "inactive" if available is False else "active",
            }
        )
    return cases


def owned_controller_argv(application: Path) -> list[str]:
    """The compiled-source controller. Not a new benchmark and not the installed app."""
    return ["node", str(application / "probe-telemetry-renderer.mjs")]


def owned_phase_from_marker(
    phase: object, completed: int, reported: int | None = None
) -> tuple[str, bool, int] | None:
    """One phase from an owned progress snapshot or a legacy monitor.json.

    Startup and close stay inactive. The measuring interval, including the
    existing connection work and the 128 memory cycles, stays active. An
    unknown label is ignored. A missing cycle count is not filled in.
    A terminal marker may carry the verified cumulative total. That total
    replaces the last checkpoint. Its absence leaves the last checkpoint.
    """
    if type(phase) is not str or type(completed) is not int or completed < 0:
        return None
    name = phase.replace("_", "-")
    if not _OWNED_PHASE.fullmatch(name):
        return None
    count = completed
    if name in _OWNED_INACTIVE:
        active = False
        if name in _TERMINAL and type(reported) is int and 0 <= reported <= 128:
            count = reported
    elif name in _OWNED_ACTIVE:
        active = True
        if name == "first-memory-cycle-and-delivery":
            count = 1
    elif name.endswith("-memory-cycles"):
        head = name[: -len("-memory-cycles")]
        if not head.isdigit():
            return None
        count = int(head)
        if not 0 < count <= 128:
            return None
        active = True
    else:
        return None
    return name, active, count


def observation_failure_code(error: BaseException) -> str:
    """A bounded code. Exception text, paths and fixture data stay out."""
    if not isinstance(error, BaseException):
        return "observation_failed"
    code = getattr(error, "code", None)
    if type(code) is not str:
        code = type(error).__name__
    if _SAFE_TOKEN.fullmatch(code):
        return code
    return "observation_failed"


def apply_owned_marker(launch, marker: object, cursor: OwnedPhaseCursor) -> None:
    """Apply one marker only after accounting accepts it.

    A failed mark does not advance the cursor and is not retried. An in-flight
    terminal keeps the verified lower bound and records that the total is unknown.
    """
    if type(marker) is not dict:
        return
    reported = marker.get("completed")
    known_flag = marker.get("completed_known")
    uncertain = known_flag is False
    usable = type(reported) is int and 0 <= reported <= 128
    phase_reported = reported if known_flag is True and usable else None
    decided = owned_phase_from_marker(marker.get("phase"), cursor.completed, phase_reported)
    if decided is None:
        return
    name, active, count = decided
    if name == cursor.rejected:
        return
    if uncertain and usable:
        if not cursor.have_lower_bound:
            count = reported
        else:
            count = cursor.completed
    if name == cursor.seen:
        if name in _TERMINAL and known_flag is not True:
            cursor.completed_known = False
            cursor.terminal_seen = True
        elif known_flag is False and cursor.have_lower_bound:
            cursor.completed_known = False
        return
    try:
        launch.mark_phase(name, canonical_operations_completed=count, active=active)
    except Exception as error:
        cursor.rejected = name
        cursor.marker_failed = True
        cursor.completed_known = False
        if cursor.observation_failure is None:
            cursor.observation_failure = observation_failure_code(error)
        return
    cursor.seen = name
    cursor.completed = count
    if name in _TERMINAL and known_flag is True and usable:
        cursor.completed_known = True
        cursor.have_lower_bound = True
        cursor.terminal_seen = True
    elif name in _TERMINAL:
        cursor.completed_known = False
        cursor.terminal_seen = True
        if usable or cursor.have_lower_bound:
            cursor.have_lower_bound = True
    elif name.endswith("-memory-cycles") or name == "first-memory-cycle-and-delivery":
        cursor.completed_known = known_flag is not False
        cursor.have_lower_bound = True
    else:
        cursor.completed_known = False


def close_owned_progress(cursor) -> None:
    """A checkpoint is a lower bound until a terminal marker establishes the total."""
    if getattr(cursor, "terminal_seen", False) is not True:
        cursor.completed_known = False


_MARKER_READ_LIMIT = 65536
_SNAPSHOT_BYTES = 1024
_SNAPSHOT_LIMIT = 64
_PROGRESS_DIR = "owned-progress"


def _reparse_or_link(info) -> bool:
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0) or 0
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & flag)


def _snapshot_sequence(name: str, suffix: str) -> int | None:
    """padStart names only: two ASCII digits, 01 through 64."""
    if len(name) != len(suffix) + 2 or not name.endswith(suffix):
        return None
    stem = name[:2]
    if stem[0] < "0" or stem[0] > "9" or stem[1] < "0" or stem[1] > "9":
        return None
    sequence = int(stem)
    if sequence < 1 or sequence > _SNAPSHOT_LIMIT:
        return None
    return sequence


def read_bounded_text(path: Path, *, limit: int = _MARKER_READ_LIMIT) -> str:
    """UTF-8 text, at most 64 KiB."""
    if type(limit) is not int or not 1 <= limit <= _MARKER_READ_LIMIT:
        raise ValueError("marker read bound")
    file = Path(path)
    try:
        info = file.lstat()
    except OSError:
        raise OSError(0, "marker unreadable") from None
    if _reparse_or_link(info) or not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise OSError(0, "marker unreadable")
    try:
        with file.open("rb") as stream:
            raw = stream.read(limit + 1)
    except OSError:
        raise OSError(0, "marker unreadable") from None
    if len(raw) > limit:
        raise OSError(0, "marker unreadable")
    return raw.decode("utf-8")


def _legacy_marker(path: Path) -> dict | None:
    try:
        value = json.loads(read_bounded_text(path))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if type(value) is dict else None


def _committed_snapshot(directory: Path) -> dict | None:
    committed: list[tuple[int, Path]] = []
    try:
        with os.scandir(directory) as entries:
            seen = 0
            for entry in entries:
                seen += 1
                if seen > _SNAPSHOT_LIMIT:
                    return None
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    return None
                if _reparse_or_link(info) or not stat.S_ISREG(info.st_mode):
                    return None
                sequence = _snapshot_sequence(entry.name, ".json")
                if sequence is not None:
                    committed.append((sequence, directory / entry.name))
                    continue
                if _snapshot_sequence(entry.name, ".json.tmp") is not None:
                    continue
                return None
    except OSError:
        return None
    if not committed:
        return None
    committed.sort(key=lambda item: item[0])
    sequences = [item[0] for item in committed]
    if sequences != list(range(1, sequences[-1] + 1)):
        return None
    try:
        raw = read_bounded_text(committed[-1][1], limit=_SNAPSHOT_BYTES)
    except (OSError, UnicodeError, ValueError):
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if type(value) is dict else None


def read_owned_marker(root: Path) -> dict | None:
    """Highest committed snapshot, or a legacy monitor.json when that directory is absent."""
    progress = Path(root) / _PROGRESS_DIR
    try:
        info = progress.lstat()
    except FileNotFoundError:
        return _legacy_marker(Path(root) / "monitor.json")
    except OSError:
        return None
    if _reparse_or_link(info) or not stat.S_ISDIR(info.st_mode):
        return None
    try:
        return _committed_snapshot(progress)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None


def owned_unsupported_report(code: str) -> dict:
    """No child was started. Missing counters stay null."""
    return {
        "qualification": "unqualified",
        "resource_acceptance": False,
        "honest_unsupported": code,
        "launched": False,
        "lifetime_cpu_microseconds": None,
        "active_cpu_microseconds": None,
        "active_wall_microseconds": None,
        "identities_missing": None,
        "missing_recorded_as_zero": False,
        "coverage": {"status": "unsupported", "cpu_lifetime_complete": None},
        "unavailable_counters": ["lifetime_cpu_microseconds", "active_cpu_microseconds"],
        "cleanup": {"ok": None, "failure": None, "retried": False},
        "phases": [],
    }


def _absolute_tool(value: object) -> bool:
    return type(value) is str and value.startswith("/") and "\x00" not in value


def _service_text(value: object) -> bool:
    """Reject expansions and line breaks. A normal path or PATH stays."""
    return (
        type(value) is str
        and value != ""
        and not any(character in value for character in "\n\r\x00%$`")
    )


def owned_delegate_identity_ok(returncode: object, stdout: object, euid: object) -> bool:
    """The harmless probe printed the original non-root uid and nothing else."""
    if type(returncode) is not int or type(stdout) is not str or type(euid) is not int:
        return False
    if returncode != 0 or euid <= 0:
        return False
    return stdout.strip() == str(euid)


def owned_scope_command(
    command: list[str],
    *,
    requested: bool,
    systemd: str | None,
    sudo: str | None,
    euid: int,
    egid: int,
    cwd: str,
    environ: dict,
    probe_accepted: bool | None,
    env_names: tuple[str, ...] | None = None,
) -> tuple[list[str], str]:
    """Wrap a counterbalance in one transient service, or leave it unchanged.

    The service keeps the caller's uid, gid, working directory, and tool/home
    environment. It is not a root scope. Nothing here writes a host cgroup
    controller. A rejected probe returns the original command.
    """
    if not requested:
        return list(command), "not_requested"
    if not _absolute_tool(systemd):
        return list(command), "direct_systemd_missing"
    if type(euid) is not int or type(egid) is not int or euid <= 0 or egid <= 0:
        return list(command), "direct_non_root_required"
    if not _absolute_tool(sudo):
        return list(command), "direct_sudo_missing"
    if not _service_text(cwd) or not cwd.startswith("/"):
        return list(command), "direct_identity_unavailable"
    if type(environ) is not dict:
        return list(command), "direct_identity_unavailable"
    names = _SERVICE_ENV if env_names is None else env_names
    if type(names) is not tuple or any(
        type(name) is not str or not name.isidentifier() for name in names
    ):
        return list(command), "direct_identity_unavailable"
    selected = []
    for name in names:
        if name not in environ:
            continue
        value = environ[name]
        # Dispatch sends an empty string when the diagnostic is off. Only explicit
        # 1 is the opt-in. Any other value stays off and must not reject the delegate.
        if name == "MNEMION_TELEMETRY_RESOURCE_ADMISSION" and value != "1":
            continue
        if not _service_text(value):
            return list(command), "direct_identity_unavailable"
        selected.append(f"--setenv={name}={value}")
    if "PATH" not in environ or "HOME" not in environ:
        return list(command), "direct_identity_unavailable"
    if not command or not _absolute_tool(command[0]):
        return list(command), "direct_tool_path_missing"
    if probe_accepted is False:
        return list(command), "direct_service_unavailable"
    prefix = [
        sudo,
        "-n",
        systemd,
        "--quiet",
        "--collect",
        "--pipe",
        "--service-type=exec",
        "-p",
        "Delegate=yes",
        "-p",
        f"User={euid}",
        "-p",
        f"Group={egid}",
        "-p",
        f"WorkingDirectory={cwd}",
        *selected,
        "--",
    ]
    return prefix + list(command), "systemd_service_delegate"


def _token(value: object) -> str | None:
    if type(value) is str and _SAFE_TOKEN.fullmatch(value):
        return value
    return None


_STARTUP_FAILURE_CATEGORIES = frozenset(
    {
        "isolated_profile",
        "invalid_resource_config",
        "invalid_hosting_config",
        "non_loopback_destination",
        "session_connection",
        "workspace_bridge",
        "workspace_handle",
        "memory_client",
        "not_packaged",
        "memory_save",
        "memory_fetch",
        "memory_recall",
        "workload_incomplete",
        "delivery_settlement",
        "private_evidence",
        "disposable_profile",
        "unclassified",
    }
)


def _startup_failure_category(report: dict) -> str | None:
    """Allowlisted class only. A raw error string is never copied."""
    if _token(report.get("failure_stage")) != "startup-error":
        return None
    category = report.get("failure_category")
    if type(category) is str and category in _STARTUP_FAILURE_CATEGORIES:
        return category
    return None


def _count(value: object, limit: int = 2**62) -> int | None:
    if type(value) is int and 0 <= value <= limit:
        return value
    return None


def _flag(value: object) -> bool | None:
    if type(value) is bool:
        return value
    return None


def _optional_count(value: object, limit: int = 2**62) -> int | None:
    if value is None:
        return None
    return _count(value, limit)


def _bounded_number(value: object, low: float, high: float) -> float | None:
    if type(value) is bool or type(value) not in (int, float):
        return None
    number = float(value)
    if not low < number <= high:
        return None
    return number


def _ledger_row(row: object) -> dict | None:
    if type(row) is not dict:
        return None
    pid = row.get("pid")
    creation = row.get("creation")
    if type(pid) is not int or not 0 < pid < 2**32:
        return None
    if type(creation) is not str or not creation.isdigit() or len(creation) > 20:
        return None
    identity = f"{pid}:{creation}"
    if row.get("identity") != identity:
        return None
    return {
        "pid": pid,
        "creation": creation,
        "identity": identity,
        "peak_working_set_bytes": _optional_count(row.get("peak_working_set_bytes")),
        "first_working_set_bytes": _optional_count(row.get("first_working_set_bytes")),
        "last_working_set_bytes": _optional_count(row.get("last_working_set_bytes")),
        "kernel_high_water_while_observed": row.get("kernel_high_water_while_observed") is True,
    }


def _coverage(value: object) -> dict:
    source = value if type(value) is dict else {}
    copied = {
        key: _token(source.get(key))
        for key in ("platform", "status", "rss_high_water", "process_lifetime_count")
    }
    for key in (
        "cpu_lifetime_complete",
        "cpu_includes_exited_descendants",
        "sampled_pid_cpu_is_complete",
        "rss_high_water_covers_unseen_exited_processes",
        "cgroup_memory_peak_is_per_process_rss",
    ):
        copied[key] = _flag(source.get(key))
    return copied


def _numeric_object(value: object, ints: tuple[str, ...], flags: tuple[str, ...]) -> dict | None:
    if type(value) is not dict:
        return None
    copied = {key: _optional_count(value.get(key)) for key in ints}
    copied.update({key: _flag(value.get(key)) for key in flags})
    return copied


def _rows(value: object) -> list:
    return value if type(value) is list else []


def _has_count(value: dict | None) -> bool:
    return type(value) is dict and any(type(item) is int for item in value.values())


def _has_value(value: dict | None) -> bool:
    return type(value) is dict and any(item is not None for item in value.values())


def _absent_owned_launch(*, withheld: bool = False) -> dict:
    report = {
        "present": False,
        "launched": None,
        "resource_acceptance": False,
        "qualification": "unqualified",
        "missing_recorded_as_zero": False,
    }
    if withheld:
        report["private_content_withheld"] = True
    return report


def retain_owned_launch(report: object) -> dict:
    """Copy allowlisted accounting fields. A null stays null. Acceptance stays false.

    Missing, empty, withheld, and unrecognized records are not a launched workload.
    Launch is true for an explicit true flag or validated process evidence only.
    Metadata without that evidence stays present and leaves launch unknown.
    """
    if type(report) is not dict:
        return _absent_owned_launch()
    if report.get("private_content_withheld") is True:
        return _absent_owned_launch(withheld=True)
    coverage = _coverage(report.get("coverage"))
    cleanup_raw = report.get("cleanup") if type(report.get("cleanup")) is dict else None
    phases = []
    for phase in _rows(report.get("phases")):
        if type(phase) is not dict or _token(phase.get("name")) is None:
            continue
        phases.append(
            {
                "name": phase["name"],
                "active": _flag(phase.get("active")),
                "cpu_microseconds": _optional_count(phase.get("cpu_microseconds")),
                "start_offset_ns": _optional_count(phase.get("start_offset_ns")),
                "end_offset_ns": _optional_count(phase.get("end_offset_ns")),
                "canonical_operations_at_start": _optional_count(
                    phase.get("canonical_operations_at_start"), 1_000_000
                ),
                "canonical_operations_at_end": _optional_count(
                    phase.get("canonical_operations_at_end"), 1_000_000
                ),
            }
        )
        if len(phases) >= 64:
            break
    unavailable = report.get("unavailable_counters")
    if type(unavailable) is list:
        unavailable = [_token(name) for name in unavailable if _token(name)][:32]
    else:
        unavailable = None
    cleanup_ok = None if cleanup_raw is None else _flag(cleanup_raw.get("ok"))
    failure = None if cleanup_raw is None else _token(cleanup_raw.get("failure"))
    cold_raw = report.get("cold_start") if type(report.get("cold_start")) is dict else {}
    processes = []
    for row in _rows(cold_raw.get("processes")):
        if type(row) is not dict or not _IDENTITY.fullmatch(str(row.get("identity") or "")):
            continue
        working = row.get("working_set_bytes")
        if type(working) is not int or working < 0:
            continue
        processes.append({"identity": row["identity"], "working_set_bytes": working})
        if len(processes) >= 512:
            break
    ledger = []
    for row in _rows(report.get("ledger")):
        copied = _ledger_row(row)
        if copied is None:
            continue
        ledger.append(copied)
        if len(ledger) >= 512:
            break
    bounds_raw = report.get("bounds") if type(report.get("bounds")) is dict else {}
    fraction = report.get("active_core_fraction")
    fraction_ok = fraction if type(fraction) is str and _FRACTION.fullmatch(fraction) else None
    known = report.get("canonical_operations_known")
    lifetime = _optional_count(report.get("lifetime_cpu_microseconds"))
    active_cpu = _optional_count(report.get("active_cpu_microseconds"))
    active_wall = _optional_count(report.get("active_wall_microseconds"))
    platform_method = _token(report.get("platform_method"))
    identities_missing = _optional_count(report.get("identities_missing"))
    canonical = _optional_count(report.get("canonical_operations_completed"), 1_000_000)
    observation_error = _token(report.get("observation_error"))
    marker_applied = False if report.get("marker_applied") is False else None
    observer = _flag(report.get("observer_in_measured_group"))
    terminated = None if cleanup_raw is None else _flag(cleanup_raw.get("terminated_owned_group"))
    sampled_peaks = _numeric_object(
        report.get("sampled_peaks"),
        ("sum_working_set_bytes",),
        (
            "sum_double_counts_shared",
            "not_a_budget_measurement",
            "sampled_pid_cpu_is_complete",
        ),
    )
    kernel = _numeric_object(
        report.get("kernel"),
        (
            "total_user_100ns",
            "total_kernel_100ns",
            "total_processes",
            "active_processes",
            "processes_no_longer_active",
            "terminated_by_limit",
            "peak_process_commit_bytes",
            "peak_job_commit_bytes",
            "cpu_usage_usec",
            "cgroup_memory_peak_bytes",
            "wait4_direct_child_cpu_microseconds",
        ),
        (
            "commit_counters_are_working_set",
            "cpu_usage_includes_descendant_cgroups",
            "cgroup_memory_peak_is_per_process_rss",
            "includes_only_reaped_descendants",
            "footprint_used_as_rss",
        ),
    )
    unsupported = _token(report.get("honest_unsupported"))
    explicit_launch = _flag(report.get("launched"))
    lifetime_cap = _bounded_number(bounds_raw.get("lifetime_seconds_cap"), 0, 120)
    timed_out = _flag(bounds_raw.get("timed_out"))
    sample_seconds = _bounded_number(bounds_raw.get("sample_seconds"), 0, 1)
    sample_truncated = _flag(bounds_raw.get("sample_truncated"))
    sample_error = _token(bounds_raw.get("sample_error"))
    subtracted = _flag(cold_raw.get("subtracted"))
    ledger_truncated = _flag(report.get("ledger_truncated"))
    retried_true = cleanup_raw is not None and cleanup_raw.get("retried") is True
    # A phase name, coverage flag, platform token, or cold-start kind is metadata.
    # It keeps the record present, and it does not prove the workload launched.
    process_evidence = any(
        (
            bool(ledger),
            bool(processes),
            lifetime is not None,
            active_cpu is not None,
            active_wall is not None,
            identities_missing is not None,
            fraction_ok is not None,
            _has_count(sampled_peaks),
            _has_count(kernel),
        )
    )
    independent = any(
        (
            process_evidence,
            platform_method is not None,
            any(value is not None for value in coverage.values()),
            bool(phases),
            cold_raw.get("kind") == "first_observed_absolute",
            subtracted is not None,
            canonical is not None,
            type(known) is bool,
            bool(unavailable),
            failure is not None,
            cleanup_ok is True,
            terminated is not None,
            retried_true,
            observer is not None,
            observation_error is not None,
            marker_applied is False,
            unsupported is not None,
            ledger_truncated is not None,
            _has_value(sampled_peaks),
            _has_value(kernel),
            any(
                value is not None
                for value in (
                    lifetime_cap,
                    timed_out,
                    sample_seconds,
                    sample_truncated,
                    sample_error,
                )
            ),
        )
    )
    # publicOwnedReport writes present:false plus default nulls for an absent file.
    # Those defaults, including an explicit false launch flag, are not new evidence.
    if report.get("present") is False and not independent:
        return _absent_owned_launch()
    if unsupported is not None or explicit_launch is False:
        launched = False
    elif explicit_launch is True:
        launched = True
    elif process_evidence:
        launched = True
    else:
        launched = None
    present = independent or explicit_launch is not None or unsupported is not None
    if present:
        ready = report.get("hosting_ready")
        hosting_ready = ready if type(ready) is bool else None
        exit_code = report.get("root_exit_code")
        root_exit_code = exit_code if type(exit_code) is int else None
        failure_stage = _token(report.get("failure_stage"))
        failure_category = _startup_failure_category(report)
    else:
        hosting_ready = None
        root_exit_code = None
        failure_stage = None
        failure_category = None
    return {
        "present": present,
        "launched": launched,
        "hosting_ready": hosting_ready,
        "root_exit_code": root_exit_code,
        "failure_stage": failure_stage,
        "failure_category": failure_category,
        "honest_unsupported": unsupported,
        "resource_acceptance": False,
        "qualification": "unqualified",
        "coverage_status": coverage.get("status"),
        "cpu_lifetime_complete": coverage.get("cpu_lifetime_complete"),
        "lifetime_cpu_microseconds": lifetime,
        "active_cpu_microseconds": active_cpu,
        "active_wall_microseconds": active_wall,
        "active_core_fraction": fraction_ok,
        "identities_missing": identities_missing,
        "unavailable_counters": unavailable,
        "observer_in_measured_group": observer,
        "cleanup_ok": cleanup_ok,
        "cleanup_failure": failure,
        "phases": phases,
        "missing_recorded_as_zero": False,
        "platform_method": platform_method,
        "canonical_operations_completed": canonical,
        "canonical_operations_known": known if type(known) is bool else None,
        "observation_error": observation_error,
        "marker_applied": marker_applied,
        "coverage": coverage,
        "cold_start": {
            "kind": "first_observed_absolute"
            if cold_raw.get("kind") == "first_observed_absolute"
            else None,
            "subtracted": subtracted,
            "processes": processes,
        },
        "ledger": ledger,
        "ledger_truncated": ledger_truncated,
        "sampled_peaks": sampled_peaks,
        "kernel": kernel,
        "cleanup": {
            "ok": cleanup_ok,
            "failure": failure,
            "retried": retried_true,
            "terminated_owned_group": terminated,
        },
        "bounds": {
            "lifetime_seconds_cap": lifetime_cap,
            "timed_out": timed_out,
            "sample_seconds": sample_seconds,
            "sample_truncated": sample_truncated,
            "sample_error": sample_error,
        },
        "budget": {
            "additional_rss_bytes_per_process": 8_388_608,
            "cpu_one_core_fraction": 0.005,
            "status": "UNACCEPTED",
            "compared": False,
        },
    }


def summarize(directory: Path) -> dict:
    receipt = json.loads((directory / "receipt.json").read_text())
    wire = describe_diagnostic_wire(receipt)
    phase_memory = receipt.get("phase_memory", False)
    if phase_memory is None:
        phase_memory = False
    if type(phase_memory) is not bool:
        raise ValueError("Phase-memory flag must be boolean")
    if phase_memory and (
        receipt.get("comparison") is not True
        or receipt.get("attribution") is not False
        or receipt.get("review_journey") is not False
    ):
        raise ValueError("Phase-memory counters require an unattributed comparison")
    if receipt.get("comparison") is True:
        order = [
            "r1-unavailable",
            "r1-opted_out",
            "r1-enabled",
            "r2-enabled",
            "r2-opted_out",
            "r2-unavailable",
        ]
        if (
            receipt.get("attribution") is not False
            or receipt.get("review_journey") is not False
            or receipt.get("declared_case_order") != order
            or [result["variant"] for result in receipt["results"]] != order
        ):
            kind = "Phase-memory comparison" if phase_memory else "Unprofiled comparison"
            raise ValueError(f"{kind} requires the complete declared six-case order")
    observations = []
    for result in receipt["results"]:
        setup = verify_setup_controls(
            result, required=receipt.get("setup_controls_required") is True
        )
        ownership = verify_process_ownership(
            result["samples"], required=receipt.get("comparison") is True
        )
        if receipt.get("comparison") is True and (
            result.get("comparison") is not True
            or result.get("devtools_auto_open") is not False
            or result.get("process_ownership_verified") is not True
            or result.get("allocation", {}).get("enabled") is not False
        ):
            kind = "Phase-memory comparison" if phase_memory else "An unprofiled comparison"
            raise ValueError(f"{kind} must retain its declared controls")
        verify_phase_memory(result, required=phase_memory)
        first, last = result["samples"][0], result["samples"][-1]
        initial = {row["pid"]: row for row in first["processes"]}
        observed = {}
        for sample in result["samples"]:
            for row in sample["processes"]:
                observed.setdefault(row["pid"], row)
        rows = []
        for pid, start in observed.items():
            samples = [
                row
                for sample in result["samples"]
                for row in sample["processes"]
                if row["pid"] == pid
            ]
            end = samples[-1]
            present_at_end = any(row["pid"] == pid for row in last["processes"])
            cpu = None
            if (
                pid in initial
                and present_at_end
                and start["cpu_ms"] is not None
                and end["cpu_ms"] is not None
            ):
                cpu = end["cpu_ms"] - start["cpu_ms"]
                if cpu < 0:
                    cpu = None
            rows.append(
                {
                    "type": start["type"],
                    "role": process_role(start),
                    "present_at_start": pid in initial,
                    "present_at_end": present_at_end,
                    "cpu_ms": cpu,
                    "ending_rss_growth_bytes": end["working_set_bytes"]
                    - start["working_set_bytes"],
                    "sampled_peak_rss_growth_bytes": max(
                        row["working_set_bytes"] for row in samples
                    )
                    - start["working_set_bytes"],
                }
            )
        external = json.loads((directory / f"{result['variant']}-processes.json").read_text())
        owned_path = directory / f"{result['variant']}-owned-launch.json"
        owned_report = None
        if owned_path.is_file():
            try:
                owned_report = json.loads(owned_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                owned_report = None
        observations.append(
            {
                "variant": result["variant"],
                "condition": result.get("condition", result["variant"]),
                "replicate": result.get("replicate", 1),
                "elapsed_ms": result["elapsed_ms"],
                "electron_cpu_ms": sum(row["cpu_ms"] for row in rows)
                if all(row["cpu_ms"] is not None for row in rows)
                else None,
                "processes": rows,
                "process_ownership_verified": ownership,
                "setup_controls_verified": setup,
                "new_electron_processes_seen": len(set(observed) - set(initial)),
                "new_electron_processes_at_end": len(
                    [row for row in last["processes"] if row["pid"] not in initial]
                ),
                "external_sample_count": len(external),
                "external_observed_processes": len(
                    {
                        (row["pid"], row["created"])
                        for sample in external
                        for row in sample["processes"]
                    }
                ),
                "owned_launch": retain_owned_launch(owned_report),
                "first_activation_windows": allocation_windows(result),
                "attribution_calls": result.get("allocation", {}).get("calls", {}),
            }
        )
    originals = {row["variant"]: row for row in receipt["results"]}
    comparisons = []
    for row in observations:
        if row["condition"] == "unavailable":
            continue
        baselines = [
            item
            for item in observations
            if item["condition"] == "unavailable" and item["replicate"] == row["replicate"]
        ]
        if len(baselines) != 1:
            raise ValueError("Each comparison requires one baseline from the same replicate")
        baseline = baselines[0]
        initial_types = {process_role(item): item for item in baseline["processes"]}
        unique_types = len(initial_types) == len(baseline["processes"]) and len(
            {process_role(item) for item in row["processes"]}
        ) == len(row["processes"])
        comparisons.append(
            {
                "variant": row["variant"],
                "baseline": baseline["variant"],
                "replicate": row["replicate"],
                "aligned_rss_growth": aligned_rss_growth(
                    originals[baseline["variant"]]["samples"], originals[row["variant"]]["samples"]
                ),
                **(
                    {
                        "aligned_phase_memory": aligned_phase_memory(
                            originals[baseline["variant"]]["samples"],
                            originals[row["variant"]]["samples"],
                        )
                    }
                    if phase_memory
                    else {}
                ),
                "difference_electron_cpu_ms": row["electron_cpu_ms"] - baseline["electron_cpu_ms"]
                if row["electron_cpu_ms"] is not None and baseline["electron_cpu_ms"] is not None
                else None,
                "difference_cpu_percent_one_core_over_baseline_elapsed": 100
                * (row["electron_cpu_ms"] - baseline["electron_cpu_ms"])
                / baseline["elapsed_ms"]
                if row["electron_cpu_ms"] is not None and baseline["electron_cpu_ms"] is not None
                else None,
                "processes": [
                    {
                        "type": item["type"],
                        "role": process_role(item),
                        "difference_ending_rss_growth_bytes": item["ending_rss_growth_bytes"]
                        - initial_types[process_role(item)]["ending_rss_growth_bytes"],
                        "difference_sampled_peak_rss_growth_bytes": item[
                            "sampled_peak_rss_growth_bytes"
                        ]
                        - initial_types[process_role(item)]["sampled_peak_rss_growth_bytes"],
                        "difference_cpu_ms": item["cpu_ms"]
                        - initial_types[process_role(item)]["cpu_ms"]
                        if item["cpu_ms"] is not None
                        and initial_types[process_role(item)]["cpu_ms"] is not None
                        else None,
                        "difference_cpu_percent_one_core_over_baseline_elapsed": 100
                        * (item["cpu_ms"] - initial_types[process_role(item)]["cpu_ms"])
                        / baseline["elapsed_ms"]
                        if item["cpu_ms"] is not None
                        and initial_types[process_role(item)]["cpu_ms"] is not None
                        else None,
                    }
                    for item in row["processes"]
                    if process_role(item) in initial_types
                    and item["present_at_start"]
                    and initial_types[process_role(item)]["present_at_start"]
                ]
                if unique_types
                else [],
            }
        )
    return {
        "schema_version": 3,
        "wire_version": wire["wire_version"],
        "wire_label": wire["wire_label"],
        "wire_path": wire["wire_path"],
        "packet_bytes": wire["packet_bytes"],
        "input_receipt_sha256": hashlib.sha256(
            (directory / "receipt.json").read_bytes()
        ).hexdigest(),
        "observations": observations,
        "comparisons": comparisons,
        "resource_acceptance": False,
        "phase_memory": phase_memory,
        "limits": [
            "Fixed source-app observations; comparison and attribution each use two counterbalanced triplets. Neither mode is installed-platform or stable overhead acceptance.",
            "New comparison receipts require stable app main/renderer identities with no extra renderer or debugger. Older receipts retain their original ambiguity.",
            "Working-set sums double-count shared pages; ending growth and sampled-peak growth are different quantities.",
            "Difference of per-run maxima and maximum matched-phase difference are distinct; neither captures unsampled peaks.",
            "First-call windows can overlap other work, and attribution instrumentation changes allocation and timing. Profiled CPU is not qualification.",
            "Electron CPU comparisons cover processes present at both boundaries; external helpers are sampled separately.",
            "100 ms external sampling can miss short-lived children; negative differences are variance, not savings.",
            *(
                [
                    "Owned-launch figures are the adapter's group counters for the compiled source controller. Null stays null. Partial coverage is not a zero or a pass. They do not replace Electron sample CPU and they are not app-overhead acceptance."
                ]
                if any(row.get("owned_launch", {}).get("present") is True for row in observations)
                else []
            ),
            *(
                [
                    "Phase-memory counters are an opt-in main-process diagnostic on a comparison run. Null is unavailable, not zero. They do not replace working-set RSS and do not pass the 2 MiB or 0.5 percent gates."
                ]
                if phase_memory
                else []
            ),
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(args.directory)
    with args.output.open("x") as destination:
        json.dump(report, destination, indent=2)
        destination.write("\n")
    print(json.dumps({"output": str(args.output), "resource_acceptance": False}))
