"""One closed week of fixed counters, then publication noise. No raw-report pool.

Adding or removing one decoded report changes the released vector by at most
``SENSITIVITY`` in L1: one denominator tick and one bin in every metric, all
inside one cohort. Independent two-sided geometric noise is calibrated so that
change has likelihood ratio at most 3. Rounding, suppression, cohort sums and
quantile labels are functions of that noisy vector.
"""

from __future__ import annotations

from fractions import Fraction
import secrets

from .wire_v3 import (
    ALLOWLIST,
    METRICS,
    OPERATING_SYSTEMS,
    UNLISTED,
    WIRE,
    Summary,
    WireV3Error,
    axis_for_week,
    bucket_bounds,
    decode,
    wire_bins,
)

SENSITIVITY = WIRE["privacy"]["l1_sensitivity"]
NUMERATOR = WIRE["privacy"]["noise"]["continue_numerator"]
DENOMINATOR = WIRE["privacy"]["noise"]["continue_denominator"]
THRESHOLD = WIRE["privacy"]["suppression_noisy_denominator"]
ROUNDING = WIRE["privacy"]["publication_rounding"]
MAX_REPORTS = WIRE["reporting"]["maximum_reports_per_window"]
WINDOW_SECONDS = WIRE["reporting"]["window_seconds"]


def _halfwidth() -> int:
    """Smallest t with P(|Z| > t) <= 0.05 for one noise coordinate."""
    decay = Fraction(NUMERATOR, DENOMINATOR)
    center = (1 - decay) / (1 + decay)
    mass = center
    width = 0
    while 1 - mass > Fraction(1, 20):
        width += 1
        mass += 2 * center * decay**width
    return width


HALFWIDTH = _halfwidth()


def _geometric(random_below) -> int:
    drawn = 0
    while True:
        value = random_below(DENOMINATOR)
        if type(value) is not int or not 0 <= value < DENOMINATOR:
            raise WireV3Error
        if value >= NUMERATOR:
            return drawn
        drawn += 1


def discrete_laplace(random_below) -> int:
    """Z = G1 - G2. A unit shift multiplies the likelihood by at most DENOMINATOR/NUMERATOR."""
    return _geometric(random_below) - _geometric(random_below)


def epsilon_holds() -> bool:
    """Exact integer form of (denominator/numerator) ** sensitivity <= 3."""
    return DENOMINATOR**SENSITIVITY <= 3 * NUMERATOR**SENSITIVITY


def round_protected(value: int) -> int:
    """Round only a noisy coordinate. Quantum 1 leaves the integer unchanged."""
    if type(value) is not int or type(ROUNDING) is not int or ROUNDING != 1:
        raise WireV3Error
    return value


def _cohorts(axis: str) -> tuple[dict, ...]:
    if axis == "release":
        listed = tuple(
            {"axis": "release", "id": item["id"], "slot": item["slot"]}
            for item in sorted(ALLOWLIST, key=lambda item: item["slot"])
        )
        return listed + ({"axis": "release", "id": UNLISTED, "slot": len(ALLOWLIST)},)
    if axis == "os":
        return tuple({"axis": "os", "id": name, "slot": index} for index, name in enumerate(OPERATING_SYSTEMS))
    raise WireV3Error


def _quantiles(counts: list[int], metric: dict) -> dict | None:
    if metric["kind"] != "ordered":
        return None
    ordered = counts[2:]
    if not ordered:
        return {"p50": {"state": "insufficient_precision"}, "p95": {"state": "insufficient_precision"}}
    peak = max(ordered)
    winners = [index for index, value in enumerate(ordered) if value == peak]
    others = [value for index, value in enumerate(ordered) if index not in winners]
    supported = (
        len(winners) == 1
        and peak >= 2 * HALFWIDTH
        and all(abs(value) <= HALFWIDTH for value in others)
    )
    if not supported:
        return {"p50": {"state": "insufficient_precision"}, "p95": {"state": "insufficient_precision"}}
    claim = {
        "state": "bucket_bounds",
        **bucket_bounds(metric, winners[0]),
        "note": "same_supported_bucket_not_an_exact_quantile",
    }
    return {"p50": dict(claim), "p95": dict(claim)}


def _metric_rows(counts_per_metric: list[list[int]], *, quantiles: bool) -> list[dict]:
    rows = []
    for metric, counts in zip(METRICS, counts_per_metric, strict=True):
        item = {"id": metric["id"], "counts": list(counts)}
        if quantiles:
            estimated = _quantiles(counts, metric)
            if estimated is not None:
                item["quantiles"] = estimated
        rows.append(item)
    return rows


def _sum_metrics(parts: list[list[list[int]]]) -> list[list[int]]:
    return [
        [sum(part[metric][bucket] for part in parts) for bucket in range(len(part_row))]
        for metric, part_row in enumerate(parts[0])
    ]


class AggregateWindow:
    """Fixed counters for one week. Sealing erases them; nothing else is retained."""

    def __init__(self, week: int):
        if type(week) is not int or not 0 <= week <= 1000000:
            raise WireV3Error
        self.week = week
        self.axis = axis_for_week(week)
        self.cohorts = _cohorts(self.axis)
        self._widths = tuple(wire_bins(metric) for metric in METRICS)
        self._stride = 1 + sum(self._widths)
        self._counts = [0] * (len(self.cohorts) * self._stride)
        self._total = 0
        self._closed = False

    def contribute(self, packet: bytes) -> bool:
        if self._closed or self._total >= MAX_REPORTS or type(packet) is not bytes:
            return False
        try:
            summary = decode(packet)
        except WireV3Error:
            return False
        if summary.axis != self.axis or not 0 <= summary.cohort_index < len(self.cohorts):
            return False
        if self.cohorts[summary.cohort_index]["id"] != summary.cohort_id:
            return False
        base = summary.cohort_index * self._stride
        self._counts[base] += 1
        offset = 1
        for bucket, width in zip(summary.buckets, self._widths, strict=True):
            self._counts[base + offset + bucket] += 1
            offset += width
        self._total += 1
        return True

    def discard(self) -> None:
        self._closed = True
        self._total = 0
        for index in range(len(self._counts)):
            self._counts[index] = 0

    def seal(self, random_below=None) -> dict | None:
        if self._closed:
            return None
        self._closed = True
        try:
            if not epsilon_holds():
                return None
            random_below = random_below or secrets.randbelow
            noisy = [round_protected(value + discrete_laplace(random_below)) for value in self._counts]
            return _publish(self.week, self.axis, self.cohorts, self._widths, self._stride, noisy)
        finally:
            self.discard()


def _slice(noisy: list[int], cohorts, widths, stride) -> list[dict]:
    rows = []
    for index, cohort in enumerate(cohorts):
        base = index * stride
        offset = 1
        metrics = []
        for width in widths:
            metrics.append(noisy[base + offset : base + offset + width])
            offset += width
        rows.append({**cohort, "denominator": noisy[base], "metrics": metrics})
    return rows


def _publish(week: int, axis: str, cohorts, widths, stride, noisy: list[int]) -> dict:
    sliced = _slice(noisy, cohorts, widths, stride)
    small = [index for index, row in enumerate(sliced) if row["denominator"] < THRESHOLD]
    # One suppressed cohort would be recoverable as global minus the rest.
    # Leave singletons published. Group two or more and publish that sum.
    if len(small) >= 2:
        hidden = [sliced[index] for index in small]
        visible = [row for index, row in enumerate(sliced) if index not in small]
        remainder = {
            "ids": [row["id"] for row in hidden],
            "denominator": sum(row["denominator"] for row in hidden),
            "metrics": _metric_rows(_sum_metrics([row["metrics"] for row in hidden]), quantiles=False),
            "quantiles": "not_a_single_population",
        }
    else:
        visible = sliced
        remainder = None
    global_metrics = _sum_metrics([row["metrics"] for row in sliced])
    report = {
        "schema_name": WIRE["reporting"]["schema_name"],
        "schema_version": WIRE["reporting"]["schema_version"],
        "privacy_model": WIRE["privacy_model"],
        "v2_local_privacy": False,
        "epsilon_add_remove_one_report": "ln(3)",
        "l1_sensitivity": SENSITIVITY,
        "noise": {
            "distribution": "difference_of_two_geometrics",
            "continue_numerator": NUMERATOR,
            "continue_denominator": DENOMINATOR,
        },
        "mechanism_halfwidth_95": HALFWIDTH,
        "publication_rounding": ROUNDING,
        "protected_unit": "add_or_remove_one_bounded_report",
        "report_unit": "anonymous_bounded_summary_not_a_person_or_installation",
        "weighting": WIRE["contribution"]["weighting"],
        "reports_are_not_unique_people": True,
        "noise_uncertainty_is_not": "independent_user_sampling_or_causal_inference",
        "comparisons": "descriptive_within_one_week_partition",
        "collector_sees_bounded_summaries": True,
        "window_week": week,
        "window_seconds": WINDOW_SECONDS,
        "cohort_axis": axis,
        "other_axis_published": False,
        "global": {
            "label": "sum_of_noisy_partition",
            "denominator": sum(row["denominator"] for row in sliced),
            "metrics": _metric_rows(global_metrics, quantiles=True),
        },
        "cohorts": [
            {
                "axis": row["axis"],
                "id": row["id"],
                "slot": row["slot"],
                "denominator": row["denominator"],
                "metrics": _metric_rows(row["metrics"], quantiles=True),
            }
            for row in visible
        ],
        "suppressed_remainder": remainder,
        "suppression": {
            "threshold": THRESHOLD,
            "input": "noisy_denominator",
            "singleton_cohorts_remain_published": True,
            "complement_is_explicit_remainder": True,
        },
    }
    return validate(report)


def _bounds(item: dict) -> bool:
    unit = item.get("unit")
    upper = item.get("upper_inclusive")
    if type(unit) is not str or unit == "" or "lower_inclusive" in item and "lower_exclusive" in item:
        return False
    if "lower_inclusive" in item:
        lower = item["lower_inclusive"]
        if type(lower) is not int or lower != 0 or type(upper) is not int or upper < 0:
            return False
    elif "lower_exclusive" in item:
        lower = item["lower_exclusive"]
        if type(lower) is not int or lower < 0:
            return False
        if upper is not None and (type(upper) is not int or upper < lower):
            return False
    else:
        return False
    allowed = {"state", "unit", "note", "lower_inclusive", "lower_exclusive", "upper_inclusive"}
    return set(item) <= allowed and item.get("note") == "same_supported_bucket_not_an_exact_quantile"


def _quantiles_ok(value: object, metric: dict) -> bool:
    if metric["kind"] != "ordered":
        return False
    if (
        type(value) is not dict
        or set(value) != {"p50", "p95"}
        or any(type(item) is not dict or item.get("state") not in {"insufficient_precision", "bucket_bounds"} for item in value.values())
    ):
        return False
    for item in value.values():
        if item["state"] == "insufficient_precision":
            if set(item) != {"state"}:
                return False
        elif not _bounds(item):
            return False
    return True


def _metrics_ok(rows: object, *, quantiles: bool) -> bool:
    if type(rows) is not list or len(rows) != len(METRICS):
        return False
    for metric, row in zip(METRICS, rows, strict=True):
        counts = row.get("counts") if type(row) is dict else None
        if (
            type(row) is not dict
            or row.get("id") != metric["id"]
            or type(counts) is not list
            or len(counts) != wire_bins(metric)
            or any(type(value) is not int for value in counts)
        ):
            return False
        if quantiles and metric["kind"] == "ordered":
            if not _quantiles_ok(row.get("quantiles"), metric) or set(row) != {"id", "counts", "quantiles"}:
                return False
        elif set(row) != {"id", "counts"}:
            return False
    return True


def validate(result: object) -> dict:
    if type(result) is not dict:
        raise WireV3Error
    required = {
        "schema_name",
        "schema_version",
        "privacy_model",
        "v2_local_privacy",
        "epsilon_add_remove_one_report",
        "l1_sensitivity",
        "noise",
        "mechanism_halfwidth_95",
        "publication_rounding",
        "protected_unit",
        "report_unit",
        "weighting",
        "reports_are_not_unique_people",
        "noise_uncertainty_is_not",
        "comparisons",
        "collector_sees_bounded_summaries",
        "window_week",
        "window_seconds",
        "cohort_axis",
        "other_axis_published",
        "global",
        "cohorts",
        "suppressed_remainder",
        "suppression",
    }
    noise = result.get("noise")
    suppression = result.get("suppression")
    overall = result.get("global")
    if (
        set(result) != required
        or result["schema_name"] != "aggregate-v3"
        or result["schema_version"] != 1
        or result["privacy_model"] != WIRE["privacy_model"]
        or result["v2_local_privacy"] is not False
        or result["epsilon_add_remove_one_report"] != "ln(3)"
        or result["l1_sensitivity"] != SENSITIVITY
        or result["mechanism_halfwidth_95"] != HALFWIDTH
        or result["publication_rounding"] != 1
        or result["reports_are_not_unique_people"] is not True
        or result["noise_uncertainty_is_not"] != "independent_user_sampling_or_causal_inference"
        or result["collector_sees_bounded_summaries"] is not True
        or result["other_axis_published"] is not False
        or result["window_seconds"] != WINDOW_SECONDS
        or type(result["window_week"]) is not int
        or not 0 <= result["window_week"] <= 1000000
        or result["cohort_axis"] != axis_for_week(result["window_week"])
        or type(noise) is not dict
        or noise != {
            "distribution": "difference_of_two_geometrics",
            "continue_numerator": NUMERATOR,
            "continue_denominator": DENOMINATOR,
        }
        or type(suppression) is not dict
        or suppression != {
            "threshold": THRESHOLD,
            "input": "noisy_denominator",
            "singleton_cohorts_remain_published": True,
            "complement_is_explicit_remainder": True,
        }
        or type(overall) is not dict
        or set(overall) != {"label", "denominator", "metrics"}
        or overall["label"] != "sum_of_noisy_partition"
        or type(overall["denominator"]) is not int
        or not _metrics_ok(overall["metrics"], quantiles=True)
        or type(result["cohorts"]) is not list
    ):
        raise WireV3Error
    expected = _cohorts(result["cohort_axis"])
    published = result["cohorts"]
    remainder = result["suppressed_remainder"]
    if any(
        type(row) is not dict
        or set(row) != {"axis", "id", "slot", "denominator", "metrics"}
        or row["axis"] != result["cohort_axis"]
        or type(row["denominator"]) is not int
        or type(row["slot"]) is not int
        or not _metrics_ok(row["metrics"], quantiles=True)
        for row in published
    ):
        raise WireV3Error
    identities = [(row["id"], row["slot"]) for row in published]
    if len(identities) != len(set(identities)):
        raise WireV3Error
    known = {(row["id"], row["slot"]) for row in expected}
    if any(identity not in known for identity in identities):
        raise WireV3Error
    missing = [row for row in expected if (row["id"], row["slot"]) not in set(identities)]
    if remainder is None:
        if missing:
            raise WireV3Error
        if sum(row["denominator"] for row in published) != overall["denominator"]:
            raise WireV3Error
        for metric_index, metric in enumerate(overall["metrics"]):
            total = [0] * len(metric["counts"])
            for row in published:
                for bucket, value in enumerate(row["metrics"][metric_index]["counts"]):
                    total[bucket] += value
            if total != metric["counts"]:
                raise WireV3Error
    else:
        if (
            type(remainder) is not dict
            or set(remainder) != {"ids", "denominator", "metrics", "quantiles"}
            or remainder["quantiles"] != "not_a_single_population"
            or type(remainder["ids"]) is not list
            or len(remainder["ids"]) < 2
            or remainder["ids"] != [row["id"] for row in missing]
            or type(remainder["denominator"]) is not int
            or not _metrics_ok(remainder["metrics"], quantiles=False)
        ):
            raise WireV3Error
        visible = sum(row["denominator"] for row in published) + remainder["denominator"]
        if visible != overall["denominator"]:
            raise WireV3Error
        for metric_index, metric in enumerate(overall["metrics"]):
            total = [0] * len(metric["counts"])
            for row in published:
                for bucket, value in enumerate(row["metrics"][metric_index]["counts"]):
                    total[bucket] += value
            for bucket, value in enumerate(remainder["metrics"][metric_index]["counts"]):
                total[bucket] += value
            if total != metric["counts"]:
                raise WireV3Error
    return result


def vector_l1(before: list[int], after: list[int]) -> int:
    return sum(abs(left - right) for left, right in zip(before, after, strict=True))
