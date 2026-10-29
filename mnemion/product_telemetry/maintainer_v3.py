"""Maintainer export of closed v3 weeks. Not a local privacy-settings page.

The command reads an already sealed publisher store. It does not enable
collection, contact a provider, or treat report ticks as people.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

from .aggregate_v3 import validate
from .publication_v3 import ReportStore
from .utility_v3 import modelled_utility
from .wire_v3 import METRIC_BY_ID, WireV3Error, bucket_label


def honest_summary(reports: list[dict], publication_failures: list[dict] | None = None) -> dict:
    failures = [] if publication_failures is None else publication_failures
    if any(
        type(item) is not dict or set(item) != {"window_week", "state"} or item["state"] != "publication_failed"
        or type(item["window_week"]) is not int
        for item in failures
    ):
        raise WireV3Error
    return {
        "surface": "maintainer_export",
        "ordinary_privacy_settings_contain_fleet_data": False,
        "reports_are_not_unique_people": True,
        "noise_is_not_independent_user_or_causal_inference": True,
        "v2_local_privacy": False,
        "collection_available": False,
        "destination": None,
        "report_count": len(reports),
        "publication_failures": failures,
        "limitations": modelled_utility()["limitations"],
    }


def _export_spec(report: dict, metric_id: str) -> dict:
    saved = next(item for item in report["domain"]["metric_legend"] if item["id"] == metric_id)
    compiled = METRIC_BY_ID[metric_id]
    if saved["kind"] == "ordered":
        return {**compiled, "upper_bounds": saved["upper_bounds"], "unit": saved["unit"]}
    return compiled


def _rows(report: dict) -> list[dict]:
    rows = []

    def emit(scope: str, axis: str, cohort_id: str, metrics: list[dict], state: str):
        for metric in metrics:
            spec = _export_spec(report, metric["id"])
            for index, count in enumerate(metric["counts"]):
                rows.append(
                    {
                        "week": report["window_week"],
                        "scope": scope,
                        "axis": axis,
                        "cohort_id": cohort_id,
                        "metric": metric["id"],
                        "bucket": bucket_label(spec, index),
                        "noisy_count": count,
                        "publication_state": state,
                    }
                )

    emit("global", "full_domain", "", report["global"]["metrics"], "noisy_full_domain_sum")
    for cohort in report["cohorts"]:
        emit("cohort", cohort["axis"], cohort["id"], cohort["metrics"], "published_noisy_cohort")
    remainder = report["suppressed_remainder"]
    if remainder is not None:
        for axis_row in remainder["axes"]:
            emit(
                "remainder",
                axis_row["axis"],
                "+".join(axis_row["ids"]),
                axis_row["metrics"],
                "combined_suppressed_cohorts",
            )
    return rows


def render(reports: list[dict], export_format: str, publication_failures: list[dict] | None = None) -> str:
    checked = [validate(report) for report in reports]
    summary = honest_summary(checked, publication_failures)
    if export_format == "json":
        return json.dumps({"summary": summary, "reports": checked}, indent=2, allow_nan=False)
    if export_format != "csv":
        raise WireV3Error
    buffer = io.StringIO()
    summary_writer = csv.DictWriter(
        buffer,
        fieldnames=(
            "record",
            "ordinary_privacy_settings_contain_fleet_data",
            "reports_are_not_unique_people",
            "noise_is_not_independent_user_or_causal_inference",
            "report_count",
            "publication_failure_weeks",
        ),
    )
    summary_writer.writeheader()
    summary_writer.writerow(
        {
            "record": "summary",
            "ordinary_privacy_settings_contain_fleet_data": False,
            "reports_are_not_unique_people": True,
            "noise_is_not_independent_user_or_causal_inference": True,
            "report_count": summary["report_count"],
            "publication_failure_weeks": "+".join(str(item["window_week"]) for item in summary["publication_failures"]),
        }
    )
    buffer.write("\n")
    rows = [row for report in checked for row in _rows(report)]
    writer = csv.DictWriter(
        buffer,
        fieldnames=("week", "scope", "axis", "cohort_id", "metric", "bucket", "noisy_count", "publication_state"),
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export sealed v3 telemetry reports or the utility model")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--format", choices=("json", "csv"))
    parser.add_argument("--utility", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.utility:
            if args.state is not None or args.format not in (None, "json"):
                raise WireV3Error
            print(json.dumps(modelled_utility(), indent=2, allow_nan=False))
            return 0
        if args.state is None or not args.state.is_absolute() or args.format is None:
            raise WireV3Error
        store = ReportStore(args.state)
        print(render(store.reports(), args.format, store.publication_failures()))
        return 0
    except (OSError, ValueError, WireV3Error):
        print(json.dumps({"ok": False, "error": "telemetry_v3_export_rejected"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
