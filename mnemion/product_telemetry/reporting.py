"""Bounded volatile aggregation and one fixed view of a closed reporting week.

There are no requests, identifiers, raw bodies, arbitrary filters or per-client
rows here. Local randomization protects a selected category, not participation.
Report ranges describe unverified contributions, never distinct users/devices.
"""

from __future__ import annotations

from array import array
import math

from .wire import VIEWS, WIRE, WireError, decode


def _transform(values: array) -> list[int]:
    """Walsh-Hadamard sums without a dense matrix or scientific runtime."""
    result = list(values)
    stride = 1
    while stride < len(result):
        for start in range(0, len(result), stride * 2):
            for offset in range(stride):
                left, right = start + offset, start + offset + stride
                a, b = result[left], result[right]
                result[left], result[right] = a + b, a - b
        stride *= 2
    return result


def _range(count: int) -> dict:
    lower = 1 << (count.bit_length() - 1)
    return {"minimum": lower, "maximum_exclusive": lower * 2}


class AggregateWindow:
    """One in-memory window; sealing clears every accumulator exactly once."""

    def __init__(self, week: int):
        if type(week) is not int or not 0 <= week <= 1000000:
            raise WireError
        self.week = week
        self._counts = array("q", [0]) * len(VIEWS)
        self._sums = tuple(array("q", [0]) * view["domain"] for view in VIEWS)
        self._total = 0
        self._closed = False

    @property
    def storage_bytes(self) -> int:
        return self._counts.itemsize * len(self._counts) + sum(
            item.itemsize * len(item) for item in self._sums
        )

    def contribute(self, packet: bytes) -> bool:
        if self._closed or self._total >= WIRE["reporting"]["maximum_reports_per_window"]:
            return False
        try:
            identifier, coordinate, sign = decode(packet)
        except WireError:
            return False
        self._sums[identifier][coordinate] += sign
        self._counts[identifier] += 1
        self._total += 1
        return True

    def discard(self) -> None:
        self._closed = True
        self._total = 0
        for index in range(len(self._counts)):
            self._counts[index] = 0
        for sums in self._sums:
            for index in range(len(sums)):
                sums[index] = 0

    def seal(self) -> dict | None:
        if self._closed:
            return None
        self._closed = True
        options = WIRE["reporting"]
        minimum = options["minimum_reports_per_view"]
        result = None
        try:
            if self._total < options["minimum_reports_per_window"]:
                return None
            views = []
            categories = sum(len(view["values"]) for view in VIEWS)
            log_bound = math.log(2 * categories / options["simultaneous_error_probability"])
            for view, count, sums in zip(VIEWS, self._counts, self._sums, strict=True):
                item = {
                    "view": view["name"],
                    "unit": view.get("unit", "categorical_observation"),
                    "state": "insufficient_reports",
                    "report_range": None,
                    "estimates": None,
                }
                if count >= minimum:
                    bounds = _range(count)
                    # A simultaneous Hoeffding bound across every released
                    # category, using the lower public count bucket. This is
                    # conservative and avoids exposing an exact report count.
                    radius = math.sqrt(2 * log_bound / bounds["minimum"]) / 0.5
                    transformed = _transform(sums)
                    estimates = []
                    inconsistent = False
                    for name, coordinate_sum in zip(view["values"], transformed):
                        estimate = coordinate_sum / (count * 0.5)
                        lower, upper = max(0.0, estimate - radius), min(1.0, estimate + radius)
                        if lower > 1 or upper < 0:
                            inconsistent = True
                        # A rare/noisy cell has no published point value or
                        # hidden residual. No exact total normalizes the view.
                        reliable = lower > 0 and lower <= 1 and upper >= lower
                        estimates.append(
                            {
                                "value": name,
                                "state": "estimated" if reliable else "insufficient_precision",
                                "fraction": round(min(1.0, max(0.0, estimate)), 4)
                                if reliable
                                else None,
                                "interval": [
                                    math.floor(lower * 10000) / 10000,
                                    math.ceil(upper * 10000) / 10000,
                                ]
                                if reliable
                                else None,
                            }
                        )
                    item.update(
                        state="inconsistent_reports" if inconsistent else "estimated",
                        report_range=bounds,
                        estimates=None if inconsistent else estimates,
                    )
                views.append(item)
            result = {
                "schema_version": options["schema_version"],
                "window_week": self.week,
                "window_seconds": options["window_seconds"],
                # Fixed closed-week contribution volume, never a person/device
                # count. No exact total or per-view residual is published.
                "report_range": _range(self._total),
                "report_unit": "unverified_anonymous_report_not_a_user_or_device",
                "sampling": "one_count_weighted_local_category_in_an_independently_chosen_permitted_view",
                "confidence": 1 - options["simultaneous_error_probability"],
                "confidence_assumptions": "independent_randomization_by_conforming_senders_not_authenticated_clients_or_poisoning_resistance",
                "privacy_loss_per_report": "ln(3)",
                "participation_or_lifetime_guarantee": False,
                "views": views,
            }
            return result
        finally:
            self.discard()


def reporting_week(timestamp: float) -> int:
    if type(timestamp) not in (int, float) or not math.isfinite(timestamp):
        raise WireError
    # Unix week zero begins Monday 5 January 1970. Only a coarse server-owned
    # window survives; client wall clocks and event timestamps never enter it.
    week = int((timestamp - 345600) // WIRE["reporting"]["window_seconds"])
    if not 0 <= week <= 1000000:
        raise WireError
    return week
