"""Summarize retained real-renderer observations without replaying any workflow."""

import argparse
import hashlib
import json
from pathlib import Path


def aligned_rss_growth(baseline, current):
    """Compare the same phases, not maxima that can occur at different times."""
    before = {row["name"]: row for row in baseline}
    after = {row["name"]: row for row in current}
    if len(before) != len(baseline) or len(after) != len(current):
        raise ValueError("Duplicate workload phases cannot be aligned")
    if not baseline or not current or baseline[0]["name"] != current[0]["name"]:
        raise ValueError("Aligned comparisons require the same initial workload phase")
    phases = [row["name"] for row in baseline if row["name"] in after]
    roles = {row["type"] for row in baseline[0]["processes"]} & {
        row["type"] for row in current[0]["processes"]
    }
    rows, ambiguous = [], []
    for role in sorted(roles):
        starts = [
            [row for row in sample["processes"] if row["type"] == role]
            for sample in (baseline[0], current[0])
        ]
        if any(len(values) != 1 for values in starts):
            ambiguous.append(role)
            continue
        base_start, current_start = starts[0][0], starts[1][0]
        observations = []
        for phase in phases:
            selected = [
                [row for row in sample["processes"] if row["type"] == role]
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
                "type": role,
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
    observations = []
    for result in receipt["results"]:
        first, last = result["samples"][0], result["samples"][-1]
        initial = {row["pid"]: row for row in first["processes"]}
        rows = []
        for pid, start in initial.items():
            samples = [
                row
                for sample in result["samples"]
                for row in sample["processes"]
                if row["pid"] == pid
            ]
            end = samples[-1]
            present_at_end = any(row["pid"] == pid for row in last["processes"])
            cpu = None
            if present_at_end and start["cpu_ms"] is not None and end["cpu_ms"] is not None:
                cpu = end["cpu_ms"] - start["cpu_ms"]
            rows.append(
                {
                    "type": start["type"],
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
        initial_types = {item["type"]: item for item in baseline["processes"]}
        unique_types = len(initial_types) == len(baseline["processes"]) and len(
            {item["type"] for item in row["processes"]}
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
                        "difference_ending_rss_growth_bytes": item["ending_rss_growth_bytes"]
                        - initial_types[item["type"]]["ending_rss_growth_bytes"],
                        "difference_sampled_peak_rss_growth_bytes": item[
                            "sampled_peak_rss_growth_bytes"
                        ]
                        - initial_types[item["type"]]["sampled_peak_rss_growth_bytes"],
                    }
                    for item in row["processes"]
                    if item["type"] in initial_types
                ]
                if unique_types
                else [],
            }
        )
    return {
        "schema_version": 2,
        "input_receipt_sha256": hashlib.sha256(
            (directory / "receipt.json").read_bytes()
        ).hexdigest(),
        "observations": observations,
        "comparisons": comparisons,
        "resource_acceptance": False,
        "limits": [
            "Fixed source-app comparisons; attribution uses two counterbalanced triplets. Neither mode is installed-platform or stable overhead acceptance.",
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
