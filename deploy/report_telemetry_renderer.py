"""Summarize retained real-renderer observations without replaying any workflow."""

import argparse
import hashlib
import json
from pathlib import Path


def process_role(row):
    return row.get("role", row["type"])


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
        "disclosure_acknowledged": True,
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


def summarize(directory: Path) -> dict:
    receipt = json.loads((directory / "receipt.json").read_text())
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
            raise ValueError("Unprofiled comparison requires the complete declared six-case order")
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
            raise ValueError("An unprofiled comparison must retain its declared controls")
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
        "input_receipt_sha256": hashlib.sha256(
            (directory / "receipt.json").read_bytes()
        ).hexdigest(),
        "observations": observations,
        "comparisons": comparisons,
        "resource_acceptance": False,
        "limits": [
            "Fixed source-app observations; comparison and attribution each use two counterbalanced triplets. Neither mode is installed-platform or stable overhead acceptance.",
            "New comparison receipts require stable app main/renderer identities with no extra renderer or debugger. Older receipts retain their original ambiguity.",
            "Working-set sums double-count shared pages; ending growth and sampled-peak growth are different quantities.",
            "Difference of per-run maxima and maximum matched-phase difference are distinct; neither captures unsampled peaks.",
            "First-call windows can overlap other work, and attribution instrumentation changes allocation and timing. Profiled CPU is not qualification.",
            "Electron CPU comparisons cover processes present at both boundaries; external helpers are sampled separately.",
            "100 ms external sampling can miss short-lived children; negative differences are variance, not savings.",
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
