"""One closed week of fixed counters, then publication noise. No raw-report pool.

Every well-formed report is admitted. Admission does not look at the other
reports, so inserting one report cannot evict a different one. Clipping happens
inside that report: one denominator tick and one bin in every metric, all in
the single cohort selected by its axis. The released vector holds both axes.
Its L1 change is ``SENSITIVITY``. Independent two-sided geometric noise is
calibrated so that change has likelihood ratio at most 3. Rounding,
suppression, cohort sums and quantile labels are functions of that noisy vector.
"""

from __future__ import annotations

from fractions import Fraction
from math import exp, log
import secrets

from .wire_v3 import (
    ALLOWLIST,
    METRICS,
    OPERATING_SYSTEMS,
    UNLISTED,
    WIRE,
    WireV3Error,
    bucket_bounds,
    decode,
    wire_bins,
)

SENSITIVITY = WIRE["privacy"]["l1_sensitivity"]
NUMERATOR = WIRE["privacy"]["noise"]["continue_numerator"]
DENOMINATOR = WIRE["privacy"]["noise"]["continue_denominator"]
THRESHOLD = WIRE["privacy"]["suppression_noisy_denominator"]
ROUNDING = WIRE["privacy"]["publication_rounding"]
WINDOW_SECONDS = WIRE["reporting"]["window_seconds"]
QUALIFICATION = "mechanism_envelope_not_a_percentile_confidence_interval"
QUANTILE_METHOD = {
    "name": "conservative_cumulative_bounds",
    "simultaneous_coordinate_envelope": True,
    "summed_histograms_use_added_noise": True,
    "single_coordinate_halfwidth_is_not_a_percentile_confidence_interval": True,
}
ADMISSION = {"rule": "every_well_formed_report", "cross_report_eviction": False}
_RADIUS_CACHE: dict[tuple[int, int], int] = {}


def _halfwidth() -> int:
    """Smallest t with P(|Z| > t) <= 0.05 for one noise coordinate.

    This is a tail of the publication noise. It is not a confidence interval
    for a percentile.
    """
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


def _one_coordinate_tail_exceeds(width: int, target_den: int) -> bool:
    """True when P(|Z| > width) > 1/target_den. Exact for one geometric difference."""
    power = width + 1
    left = 2 * target_den * NUMERATOR**power
    right = DENOMINATOR**width * (DENOMINATOR + NUMERATOR)
    return left > right


def _summed_tail_exceeds(parts: int, width: int, target_den: int) -> bool:
    """True when a Chernoff upper bound on P(|S| > width) is still above 1/target_den.

    S is the sum of ``parts`` independent two-sided geometric draws. Each tilt
    gives a valid upper bound, and a grid can only make that bound looser.
    This is not a confidence interval for a percentile.
    """
    alpha = NUMERATOR / DENOMINATOR
    tilt_limit = -log(alpha)
    log_cutoff = -log(target_den)
    lowest = None
    for step in range(1, 48):
        tilt = tilt_limit * step / 48
        positive = 1 - alpha * exp(tilt)
        negative = 1 - alpha * exp(-tilt)
        if positive <= 0 or negative <= 0:
            continue
        log_mgf = 2 * log(1 - alpha) - log(positive) - log(negative)
        bound = log(2) - tilt * (width + 1) + parts * log_mgf
        if lowest is None or bound < lowest:
            lowest = bound
    if lowest is None:
        return True
    return lowest > log_cutoff


def envelope_radius(parts: int, bins: int) -> int:
    """Count radius for a union bound of at most 1/20 over the histogram bins.

    ``parts`` is the number of independent noise draws added into each bin.
    A cohort histogram uses 1 and the exact discrete-Laplace tail. A sum across
    the fixed domain uses one draw per cohort, a Chernoff upper bound on that
    sum, and one extra count so float error cannot shrink the envelope. The
    summed radius can be wider than the exact tail. It is not a confidence
    interval for a population percentile.
    """
    if type(parts) is not int or type(bins) is not int or not 1 <= parts <= 64 or not 1 <= bins <= 256:
        raise WireV3Error
    key = (parts, bins)
    cached = _RADIUS_CACHE.get(key)
    if cached is not None:
        return cached
    target_den = 20 * bins
    if parts == 1:
        radius = 0
        while _one_coordinate_tail_exceeds(radius, target_den):
            radius += 1
            if radius > 100000:
                raise WireV3Error
    else:
        radius = 0
        while _summed_tail_exceeds(parts, radius, target_den):
            radius += 1
            if radius > 1000000:
                raise WireV3Error
        radius += 1
    _RADIUS_CACHE[key] = radius
    return radius


def _domain_cohorts() -> tuple[dict, ...]:
    listed = tuple(sorted(ALLOWLIST, key=lambda item: item["slot"]))
    cohorts = [
        {
            "axis": "release",
            "id": item["id"],
            "slot": item["slot"],
            "major": item["major"],
            "minor": item["minor"],
            "patch": item["patch"],
        }
        for item in listed
    ]
    cohorts.append({"axis": "release", "id": UNLISTED, "slot": len(listed)})
    cohorts.extend({"axis": "os", "id": name, "slot": index} for index, name in enumerate(OPERATING_SYSTEMS))
    return tuple(cohorts)


def _legend_document() -> list[dict]:
    rows = []
    for metric in METRICS:
        if metric["kind"] == "ordered":
            rows.append(
                {
                    "id": metric["id"],
                    "kind": "ordered",
                    "unit": metric["unit"],
                    "upper_bounds": list(metric["upper_bounds"]),
                }
            )
        else:
            rows.append({"id": metric["id"], "kind": "categories"})
    return rows


def _domain_document(cohorts) -> dict:
    releases = []
    unlisted = None
    systems = []
    for row in cohorts:
        if row["axis"] == "release" and "major" in row:
            releases.append(
                {
                    "slot": row["slot"],
                    "major": row["major"],
                    "minor": row["minor"],
                    "patch": row["patch"],
                    "id": row["id"],
                }
            )
        elif row["axis"] == "release":
            unlisted = {"slot": row["slot"], "id": row["id"]}
        else:
            systems.append({"slot": row["slot"], "id": row["id"]})
    return {
        "releases": releases,
        "unlisted_release": unlisted,
        "operating_systems": systems,
        "metric_legend": _legend_document(),
    }


def _cumulative_index(counts: list[int], numerator: int, denominator: int, radius: int) -> int | None:
    """Unique bucket that contains the percentile for every histogram inside the envelope."""
    lower = [max(0, value - radius) for value in counts]
    upper = [value + radius for value in counts]
    weight = denominator - numerator
    found = None
    for index in range(len(counts)):
        before = sum(upper[:index])
        through = sum(lower[: index + 1])
        after = sum(upper[index + 1 :])
        rest = sum(lower[index:])
        always_at_or_before = weight * through >= numerator * after
        always_at_or_after = weight * before < numerator * rest
        if always_at_or_before and always_at_or_after:
            if found is not None:
                return None
            found = index
    return found


def _quantiles(counts: list[int], metric: dict, *, parts: int) -> dict | None:
    if metric["kind"] != "ordered":
        return None
    ordered = list(counts[2:])
    radius = envelope_radius(parts, len(ordered))

    def insufficient() -> dict:
        return {
            "state": "insufficient_precision",
            "qualification": QUALIFICATION,
            "envelope_radius": radius,
            "noise_parts": parts,
        }

    if not ordered or any(type(value) is not int or value < -radius for value in ordered):
        return {"p50": insufficient(), "p95": insufficient()}

    def claim(index: int | None) -> dict:
        if index is None:
            return insufficient()
        return {
            "state": "bucket_bounds",
            **bucket_bounds(metric, index),
            "qualification": QUALIFICATION,
            "envelope_radius": radius,
            "noise_parts": parts,
        }

    return {
        "p50": claim(_cumulative_index(ordered, 1, 2, radius)),
        "p95": claim(_cumulative_index(ordered, 19, 20, radius)),
    }


def _metric_rows(counts_per_metric: list[list[int]], *, quantiles: bool, parts: int, specs: list[dict]) -> list[dict]:
    rows = []
    for metric, counts in zip(specs, counts_per_metric, strict=True):
        item = {"id": metric["id"], "counts": list(counts)}
        if quantiles:
            estimated = _quantiles(counts, metric, parts=parts)
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
        self.cohorts = _domain_cohorts()
        self._widths = tuple(wire_bins(metric) for metric in METRICS)
        self._stride = 1 + sum(self._widths)
        self._counts = [0] * (len(self.cohorts) * self._stride)
        self._total = 0
        self._closed = False

    def contribute(self, packet: bytes) -> bool:
        if self._closed or type(packet) is not bytes:
            return False
        try:
            summary = decode(packet)
        except WireV3Error:
            return False
        release_count = sum(row["axis"] == "release" for row in self.cohorts)
        index = summary.cohort_index if summary.axis == "release" else release_count + summary.cohort_index
        if summary.axis not in {"release", "os"} or not 0 <= index < len(self.cohorts):
            return False
        cohort = self.cohorts[index]
        if cohort["axis"] != summary.axis or cohort["id"] != summary.cohort_id or cohort["slot"] != summary.cohort_index:
            return False
        base = index * self._stride
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
            return _publish(self.week, self.cohorts, self._widths, self._stride, noisy)
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


def _group(rows: list[dict], specs: list[dict]) -> tuple[list[dict], dict | None]:
    small = [row for row in rows if row["denominator"] < THRESHOLD]
    if len(small) < 2:
        return rows, None
    hidden = {row["id"] for row in small}
    visible = [row for row in rows if row["id"] not in hidden]
    return visible, {
        "axis": rows[0]["axis"],
        "ids": [row["id"] for row in small],
        "denominator": sum(row["denominator"] for row in small),
        "metrics": _metric_rows(_sum_metrics([row["metrics"] for row in small]), quantiles=False, parts=1, specs=specs),
        "quantiles": "not_a_single_population",
    }


def _cohort_document(row: dict, specs: list[dict]) -> dict:
    return {
        "axis": row["axis"],
        "id": row["id"],
        "slot": row["slot"],
        "denominator": row["denominator"],
        "metrics": _metric_rows(row["metrics"], quantiles=True, parts=1, specs=specs),
    }


def _publish(week: int, cohorts, widths, stride, noisy: list[int]) -> dict:
    domain = _domain_document(cohorts)
    specs = _checked_legend(domain["metric_legend"])
    sliced = _slice(noisy, cohorts, widths, stride)
    release_rows = [row for row in sliced if row["axis"] == "release"]
    os_rows = [row for row in sliced if row["axis"] == "os"]
    visible_release, release_group = _group(release_rows, specs)
    visible_os, os_group = _group(os_rows, specs)
    groups = [item for item in (release_group, os_group) if item is not None]
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
        "protected_unit": "add_or_remove_one_input_report_including_admission_and_clipping",
        "report_unit": "anonymous_bounded_summary_not_a_person_or_installation",
        "weighting": WIRE["contribution"]["weighting"],
        "admission": dict(ADMISSION),
        "reports_are_not_unique_people": True,
        "noise_uncertainty_is_not": "independent_user_sampling_or_causal_inference",
        "comparisons": "separate_axes_in_one_week_not_a_joined_profile",
        "collector_sees_bounded_summaries": True,
        "window_week": week,
        "window_seconds": WINDOW_SECONDS,
        "domain": domain,
        "quantile_method": dict(QUANTILE_METHOD),
        "global": {
            "label": "sum_of_noisy_full_domain",
            "denominator": sum(row["denominator"] for row in sliced),
            "metrics": _metric_rows(global_metrics, quantiles=True, parts=len(sliced), specs=specs),
        },
        "cohorts": [_cohort_document(row, specs) for row in visible_release + visible_os],
        "suppressed_remainder": None if not groups else {"axes": groups},
        "suppression": {
            "threshold": THRESHOLD,
            "input": "noisy_denominator",
            "singleton_cohorts_remain_published": True,
            "complement_is_explicit_remainder": True,
            "grouped_per_axis": True,
        },
    }
    return validate(report)


def _checked_legend(legend: object) -> list[dict]:
    if type(legend) is not list or len(legend) != len(METRICS):
        raise WireV3Error
    specs = []
    for metric, item in zip(METRICS, legend, strict=True):
        if type(item) is not dict or item.get("id") != metric["id"] or item.get("kind") != metric["kind"]:
            raise WireV3Error
        if metric["kind"] == "ordered":
            bounds = item.get("upper_bounds")
            if (
                set(item) != {"id", "kind", "unit", "upper_bounds"}
                or item.get("unit") != metric["unit"]
                or type(bounds) is not list
                or len(bounds) != len(metric["upper_bounds"])
                or any(type(bound) is not int or not 0 <= bound <= 10**18 for bound in bounds)
                or any(bounds[index] >= bounds[index + 1] for index in range(len(bounds) - 1))
            ):
                raise WireV3Error
            specs.append(
                {"id": metric["id"], "kind": "ordered", "unit": metric["unit"], "upper_bounds": list(bounds)}
            )
        elif set(item) != {"id", "kind"}:
            raise WireV3Error
        else:
            specs.append({"id": metric["id"], "kind": "categories", "categories": list(metric["categories"])})
    return specs


def _checked_domain(domain: object) -> tuple[list[dict], list[dict]]:
    if (
        type(domain) is not dict
        or set(domain) != {"releases", "unlisted_release", "operating_systems", "metric_legend"}
    ):
        raise WireV3Error
    releases = domain["releases"]
    if type(releases) is not list or not 1 <= len(releases) <= WIRE["allowlist_maximum_slots"]:
        raise WireV3Error
    cohorts = []
    seen = set()
    for slot, item in enumerate(releases):
        if type(item) is not dict or set(item) != {"slot", "major", "minor", "patch", "id"}:
            raise WireV3Error
        major, minor, patch = item["major"], item["minor"], item["patch"]
        if any(type(part) is not int or not 0 <= part <= 255 for part in (major, minor, patch)) or item["slot"] != slot:
            raise WireV3Error
        identity = f"{major}.{minor}.{patch}"
        if item["id"] != identity or identity in seen:
            raise WireV3Error
        seen.add(identity)
        cohorts.append(
            {"axis": "release", "id": identity, "slot": slot, "major": major, "minor": minor, "patch": patch}
        )
    unlisted = domain["unlisted_release"]
    if (
        type(unlisted) is not dict
        or set(unlisted) != {"slot", "id"}
        or unlisted["id"] != UNLISTED
        or unlisted["slot"] != len(releases)
    ):
        raise WireV3Error
    cohorts.append({"axis": "release", "id": UNLISTED, "slot": len(releases)})
    systems = domain["operating_systems"]
    if type(systems) is not list or len(systems) != len(OPERATING_SYSTEMS):
        raise WireV3Error
    for slot, (item, name) in enumerate(zip(systems, OPERATING_SYSTEMS, strict=True)):
        if type(item) is not dict or set(item) != {"slot", "id"} or item["slot"] != slot or item["id"] != name:
            raise WireV3Error
        cohorts.append({"axis": "os", "id": name, "slot": slot})
    return cohorts, _checked_legend(domain["metric_legend"])


def _metrics_ok(rows: object, *, quantiles: bool, parts: int, specs: list[dict]) -> bool:
    if type(rows) is not list or len(rows) != len(specs):
        return False
    for metric, row in zip(specs, rows, strict=True):
        counts = row.get("counts") if type(row) is dict else None
        if (
            type(row) is not dict
            or row.get("id") != metric["id"]
            or type(counts) is not list
            or len(counts) != (2 + len(metric["upper_bounds"]) if metric["kind"] == "ordered" else 2 + len(metric["categories"]))
            or any(type(value) is not int for value in counts)
        ):
            return False
        if quantiles and metric["kind"] == "ordered":
            if row.get("quantiles") != _quantiles(counts, metric, parts=parts) or set(row) != {"id", "counts", "quantiles"}:
                return False
        elif set(row) != {"id", "counts"}:
            return False
    return True


def _covers(expected: list[dict], published: list[dict], hidden: list[str]) -> bool:
    pub = list(published)
    hid = list(hidden)
    for row in expected:
        if pub and pub[0]["id"] == row["id"] and pub[0]["slot"] == row["slot"] and pub[0]["axis"] == row["axis"]:
            pub.pop(0)
        elif hid and hid[0] == row["id"]:
            hid.pop(0)
        else:
            return False
    return not pub and not hid


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
        "admission",
        "reports_are_not_unique_people",
        "noise_uncertainty_is_not",
        "comparisons",
        "collector_sees_bounded_summaries",
        "window_week",
        "window_seconds",
        "domain",
        "quantile_method",
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
        or result["schema_version"] != 2
        or result["privacy_model"] != WIRE["privacy_model"]
        or result["v2_local_privacy"] is not False
        or result["epsilon_add_remove_one_report"] != "ln(3)"
        or result["l1_sensitivity"] != SENSITIVITY
        or result["mechanism_halfwidth_95"] != HALFWIDTH
        or result["publication_rounding"] != 1
        or result["protected_unit"] != "add_or_remove_one_input_report_including_admission_and_clipping"
        or result["admission"] != ADMISSION
        or result["reports_are_not_unique_people"] is not True
        or result["noise_uncertainty_is_not"] != "independent_user_sampling_or_causal_inference"
        or result["comparisons"] != "separate_axes_in_one_week_not_a_joined_profile"
        or result["collector_sees_bounded_summaries"] is not True
        or result["quantile_method"] != QUANTILE_METHOD
        or result["window_seconds"] != WINDOW_SECONDS
        or type(result["window_week"]) is not int
        or not 0 <= result["window_week"] <= 1000000
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
            "grouped_per_axis": True,
        }
        or type(overall) is not dict
        or set(overall) != {"label", "denominator", "metrics"}
        or overall["label"] != "sum_of_noisy_full_domain"
        or type(overall["denominator"]) is not int
        or type(result["cohorts"]) is not list
    ):
        raise WireV3Error
    expected, specs = _checked_domain(result["domain"])
    if not _metrics_ok(overall["metrics"], quantiles=True, parts=len(expected), specs=specs):
        raise WireV3Error
    published = result["cohorts"]
    if any(
        type(row) is not dict
        or set(row) != {"axis", "id", "slot", "denominator", "metrics"}
        or row["axis"] not in {"release", "os"}
        or type(row["denominator"]) is not int
        or type(row["slot"]) is not int
        or not _metrics_ok(row["metrics"], quantiles=True, parts=1, specs=specs)
        for row in published
    ):
        raise WireV3Error
    identities = [(row["axis"], row["id"], row["slot"]) for row in published]
    if len(identities) != len(set(identities)):
        raise WireV3Error
    remainder = result["suppressed_remainder"]
    grouped: dict[str, dict] = {}
    if remainder is not None:
        if type(remainder) is not dict or set(remainder) != {"axes"} or type(remainder["axes"]) is not list:
            raise WireV3Error
        axes = remainder["axes"]
        names = []
        for item in axes:
            if (
                type(item) is not dict
                or set(item) != {"axis", "ids", "denominator", "metrics", "quantiles"}
                or item["axis"] not in {"release", "os"}
                or item["quantiles"] != "not_a_single_population"
                or type(item["ids"]) is not list
                or len(item["ids"]) < 2
                or any(type(identity) is not str for identity in item["ids"])
                or type(item["denominator"]) is not int
                or not _metrics_ok(item["metrics"], quantiles=False, parts=1, specs=specs)
            ):
                raise WireV3Error
            names.append(item["axis"])
            grouped[item["axis"]] = item
        if names != [name for name in ("release", "os") if name in names] or len(names) != len(set(names)) or not names:
            raise WireV3Error
    for axis in ("release", "os"):
        expected_axis = [row for row in expected if row["axis"] == axis]
        published_axis = [row for row in published if row["axis"] == axis]
        hidden = grouped[axis]["ids"] if axis in grouped else []
        if not _covers(expected_axis, published_axis, hidden):
            raise WireV3Error
    pieces = list(published) + list(grouped.values())
    if sum(row["denominator"] for row in pieces) != overall["denominator"]:
        raise WireV3Error
    for metric_index, metric in enumerate(overall["metrics"]):
        total = [0] * len(metric["counts"])
        for row in pieces:
            for bucket, value in enumerate(row["metrics"][metric_index]["counts"]):
                total[bucket] += value
        if total != metric["counts"]:
            raise WireV3Error
    return result


def vector_l1(before: list[int], after: list[int]) -> int:
    return sum(abs(left - right) for left, right in zip(before, after, strict=True))
