"""Summarize retained real-renderer observations without replaying any workflow."""

import argparse
import hashlib
import json
from pathlib import Path


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
            }
        )
    baseline = next(row for row in observations if row["variant"] == "unavailable")
    comparisons = []
    for row in observations:
        if row is baseline:
            continue
        initial_types = {item["type"]: item for item in baseline["processes"]}
        unique_types = len(initial_types) == len(baseline["processes"]) and len(
            {item["type"] for item in row["processes"]}
        ) == len(row["processes"])
        comparisons.append(
            {
                "variant": row["variant"],
                "baseline": "unavailable",
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
        "schema_version": 1,
        "input_receipt_sha256": hashlib.sha256(
            (directory / "receipt.json").read_bytes()
        ).hexdigest(),
        "observations": observations,
        "comparisons": comparisons,
        "resource_acceptance": False,
        "limits": [
            "One sequential comparison on development Electron; not installed-platform or stable overhead acceptance.",
            "Working-set sums double-count shared pages; ending growth and sampled-peak growth are different quantities.",
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
