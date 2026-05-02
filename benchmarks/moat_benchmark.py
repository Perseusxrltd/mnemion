#!/usr/bin/env python3
"""Run Mnemion's deterministic moat benchmark and emit auditable JSON.

This is intentionally separate from raw retrieval benchmarks. It exercises
Mnemion-only behavior: trust lifecycle, cognitive reconstruction, topic
tunnels, and memory-guard quarantine.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mnemion.moat_eval import run_moat_eval


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    modes = result.get("modes", [])
    cases = result.get("cases", {})
    totals = {mode: {"passed": 0, "total": 0, "score": 0.0} for mode in modes}

    for case_list in cases.values():
        for case in case_list:
            passed = case.get("passed", {})
            for mode in modes:
                totals[mode]["total"] += 1
                if passed.get(mode):
                    totals[mode]["passed"] += 1

    for stats in totals.values():
        total = stats["total"]
        stats["score"] = stats["passed"] / total if total else 0.0
    return {"mode_totals": totals}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Mnemion moat benchmark")
    parser.add_argument(
        "--suite",
        default="all",
        choices=["struct", "causal", "forgetting", "security", "all"],
        help="Moat suite to run (default: all)",
    )
    parser.add_argument(
        "--kg-path",
        default=None,
        help="Optional SQLite path for the eval knowledge graph",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional JSON output path",
    )
    args = parser.parse_args()

    result = run_moat_eval(suite=args.suite, kg_path=args.kg_path)
    payload = {
        "benchmark": "mnemion_moat",
        "claim_type": "locally_reproducible_moat_eval",
        "description": (
            "Deterministic trust, cognitive reconstruction, topic tunnel, "
            "and memory-guard cases; not a raw retrieval recall benchmark."
        ),
        "result": result,
        "summary": summarize(result),
    }
    text = json.dumps(payload, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
