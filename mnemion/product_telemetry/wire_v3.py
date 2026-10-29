"""Fixed v3 summaries for a trusted collector. This is not v2's local randomizer.

A packet carries one cohort axis and one clipped, normalized tick per catalog
metric. It has no room for a second axis, a hardware id, or a test-mode flag.
Publication noise is applied later, to the closed-week vector, not here.
"""

from __future__ import annotations

from importlib.resources import files
import json
import secrets

from . import CONTRACT
from .catalog import MeasurementError, describe, observation

WIRE = json.loads(files(__package__).joinpath("wire-v3.json").read_text())
METRICS = tuple(WIRE["metrics"])
METRIC_BY_ID = {metric["id"]: metric for metric in METRICS}
GROUPS = tuple(CONTRACT["metric_groups"])
OPERATING_SYSTEMS = tuple(WIRE["operating_systems"])
ALLOWLIST = tuple(WIRE["release_allowlist"])
UNLISTED = WIRE["unlisted_release_id"]
PACKET_BYTES = WIRE["packet_bytes"]
CLIP = WIRE["contribution"]["clip_per_bucket"]
MAX_OBSERVATIONS = WIRE["contribution"]["maximum_observations"]
AXIS = WIRE["axis_byte"]


class WireV3Error(ValueError):
    def __init__(self):
        super().__init__("telemetry_invalid_v3_report")


def _measurement_bins(metric: dict) -> int:
    if metric["kind"] == "ordered":
        return len(metric["upper_bounds"])
    return len(metric["categories"])


def wire_bins(metric: dict) -> int:
    return 2 + _measurement_bins(metric)


def _check_contract() -> None:
    privacy = WIRE["privacy"]
    numerator = privacy["noise"]["continue_numerator"]
    denominator = privacy["noise"]["continue_denominator"]
    sensitivity = privacy["l1_sensitivity"]
    slots = [item["slot"] for item in ALLOWLIST]
    if (
        WIRE["version"] != 3
        or WIRE["not_v2_local_randomization"] is not True
        or privacy["epsilon"] != "ln(3)"
        or sensitivity != len(METRICS) + 1
        or PACKET_BYTES != 6 + len(METRICS)
        or len(METRIC_BY_ID) != len(METRICS)
        or WIRE["state_bins"] != ["group_disabled", "sensor_missing"]
        or OPERATING_SYSTEMS != ("windows", "macos", "linux", "other")
        or not 1 <= len(ALLOWLIST) <= WIRE["allowlist_maximum_slots"]
        or slots != list(range(len(ALLOWLIST)))
        or len({(item["major"], item["minor"], item["patch"]) for item in ALLOWLIST}) != len(ALLOWLIST)
        or any(metric["group"] not in GROUPS or metric["wire_index_origin"] != 2 for metric in METRICS)
        or any(wire_bins(metric) > 256 for metric in METRICS)
        or type(numerator) is not int
        or type(denominator) is not int
        or not 0 < numerator < denominator
        or denominator**sensitivity > 3 * numerator**sensitivity
        or WIRE["client_budget"]["maximum_attempts_per_rolling_week"] != 7
        or WIRE["client_budget"]["minimum_attempt_spacing_seconds"] != 86400
        or WIRE["client_budget"]["maximum_packet_bytes"] > WIRE["client_budget"]["within_attempt_reservation_bytes"]
        or WIRE["client_budget"]["within_daily_wire_bytes"] != CONTRACT["limits"]["wire_bytes_per_day"]
        or WIRE["statements"]["reports_are_not_unique_people"] is not True
    ):
        raise WireV3Error


_check_contract()
RELEASE_BY_COORDINATE = {
    (item["major"], item["minor"], item["patch"]): item for item in ALLOWLIST
}
RELEASE_BY_SLOT = {item["slot"]: item for item in ALLOWLIST}


class Summary:
    """One bounded packet after allowlist mapping. Not an installation record."""

    __slots__ = ("axis", "cohort_id", "cohort_index", "buckets")

    def __init__(self, axis: str, cohort_id: str, cohort_index: int, buckets: tuple[int, ...]):
        self.axis = axis
        self.cohort_id = cohort_id
        self.cohort_index = cohort_index
        self.buckets = buckets


def axis_for_week(week: int) -> str:
    """Public week parity. It does not read a measurement or a client identity."""
    if type(week) is not int or not 0 <= week <= 1000000:
        raise WireV3Error
    return WIRE["axis_rule"]["even_week"] if week % 2 == 0 else WIRE["axis_rule"]["odd_week"]


def bucket_label(metric: dict, index: int) -> str:
    if index == 0:
        return "group_disabled"
    if index == 1:
        return "sensor_missing"
    slot = index - 2
    if metric["kind"] == "categories":
        return metric["categories"][slot]
    bounds = metric["upper_bounds"]
    if slot == 0:
        return f"0-{bounds[0]}"
    if slot == len(bounds) - 1:
        return f">{bounds[slot - 1]}"
    return f"{bounds[slot - 1] + 1}-{bounds[slot]}"


def bucket_bounds(metric: dict, measurement_index: int) -> dict:
    """Inclusive catalog edges for one ordered bucket. The last bucket is open."""
    bounds = metric["upper_bounds"]
    unit = metric["unit"]
    if measurement_index == 0:
        return {"lower_inclusive": 0, "upper_inclusive": bounds[0], "unit": unit}
    if measurement_index == len(bounds) - 1:
        return {"lower_exclusive": bounds[measurement_index - 1], "upper_inclusive": None, "unit": unit}
    return {
        "lower_exclusive": bounds[measurement_index - 1],
        "upper_inclusive": bounds[measurement_index],
        "unit": unit,
    }


def _draw(total: int, random_below) -> int:
    value = random_below(total)
    if type(value) is not int or not 0 <= value < total:
        raise WireV3Error
    return value


def _weights(metric: dict) -> list[int]:
    return [0] * _measurement_bins(metric)


def _add(weights: dict[str, list[int]], metric_id: str, key: object) -> None:
    metric = METRIC_BY_ID[metric_id]
    if metric["kind"] == "ordered":
        if type(key) is not int or not 0 <= key < len(metric["upper_bounds"]):
            raise WireV3Error
        index = key
    else:
        try:
            index = metric["categories"].index(key)
        except ValueError:
            raise WireV3Error from None
    row = weights[metric_id]
    row[index] = min(CLIP, row[index] + 1)


def _choose(weights: list[int], random_below) -> int:
    total = sum(weights)
    if total <= 0:
        raise WireV3Error
    if weights.count(0) == len(weights) - 1:
        return weights.index(next(weight for weight in weights if weight))
    position = _draw(total, random_below)
    for index, weight in enumerate(weights):
        if position < weight:
            return index
        position -= weight
    raise WireV3Error


def summarize(
    observations: object,
    *,
    groups: object,
    axis: str,
    release: tuple[int, int, int] | None = None,
    operating_system: str | None = None,
    random_below=None,
) -> bytes:
    """Clip and normalize local observations into one fixed packet.

    Each enabled metric contributes weight 1. Disabled groups and missing
    sensors use explicit bins, not a fabricated zero. The draw is the defined
    weighting of a clipped histogram, not the publication privacy mechanism.
    ``random_below`` exists for tests; a packet cannot select it.
    """
    if (
        type(groups) not in (list, tuple)
        or not 1 <= len(groups) <= len(GROUPS)
        or any(type(group) is not str or group not in GROUPS for group in groups)
        or len(set(groups)) != len(groups)
        or axis not in AXIS
    ):
        raise WireV3Error
    if type(observations) not in (list, tuple) or not 1 <= len(observations) <= MAX_OBSERVATIONS:
        raise WireV3Error
    permitted = set(groups)
    weights = {metric["id"]: _weights(metric) for metric in METRICS}
    saw_outcome = False
    try:
        for item in observations:
            _contribution, cells = observation(item)
            for cell in cells:
                described = describe(cell)
                metric_id = described["metric"]
                if metric_id == "submissions":
                    if "usage" not in permitted:
                        continue
                    workflow = described["workflow"]
                    _add(weights, "feature_family", workflow.split(".", 1)[0])
                    _add(weights, "feature", workflow)
                    continue
                if metric_id == "outcomes":
                    if "usage" not in permitted:
                        continue
                    saw_outcome = True
                    _add(weights, "outcome", described["bucket"])
                    continue
                if metric_id == "reasons":
                    if "reliability" not in permitted:
                        continue
                    _add(weights, "reason", described["bucket"])
                    continue
                spec = METRIC_BY_ID[metric_id]
                if spec["group"] not in permitted:
                    continue
                _add(weights, metric_id, described["bucket"])
    except (MeasurementError, KeyError, WireV3Error):
        raise WireV3Error from None
    random_below = random_below or secrets.randbelow
    indexes = []
    for metric in METRICS:
        if metric["group"] not in permitted:
            indexes.append(0)
            continue
        row = weights[metric["id"]]
        if metric["id"] == "reason":
            if not saw_outcome and sum(row) == 0:
                indexes.append(1)
            elif sum(row) == 0:
                indexes.append(2)
            else:
                indexes.append(2 + _choose(row, random_below))
            continue
        indexes.append(1 if sum(row) == 0 else 2 + _choose(row, random_below))
    return encode(axis, indexes, release=release, operating_system=operating_system)


def encode(
    axis: str,
    buckets: list[int] | tuple[int, ...],
    *,
    release: tuple[int, int, int] | None = None,
    operating_system: str | None = None,
) -> bytes:
    if (
        axis not in AXIS
        or type(buckets) not in (list, tuple)
        or len(buckets) != len(METRICS)
        or any(type(value) is not int or not 0 <= value < wire_bins(metric) for value, metric in zip(buckets, METRICS))
    ):
        raise WireV3Error
    packet = bytearray(PACKET_BYTES)
    packet[0] = WIRE["version_byte"]
    packet[1] = AXIS[axis]
    if axis == "release":
        if (
            type(release) is not tuple
            or len(release) != 3
            or any(type(part) is not int or not 0 <= part <= 255 for part in release)
        ):
            raise WireV3Error
        packet[2], packet[3], packet[4] = release
    else:
        if type(operating_system) is not str or operating_system not in OPERATING_SYSTEMS:
            raise WireV3Error
        packet[2] = OPERATING_SYSTEMS.index(operating_system)
    packet[6:] = buckets
    return bytes(packet)


def decode(packet: bytes) -> Summary:
    if type(packet) is not bytes or len(packet) != PACKET_BYTES or packet[0] != WIRE["version_byte"]:
        raise WireV3Error
    if packet[5] != WIRE["reserved_cohort_byte"] or len(packet) != 6 + len(METRICS):
        raise WireV3Error
    buckets = tuple(packet[6:])
    for value, metric in zip(buckets, METRICS, strict=True):
        if value >= wire_bins(metric):
            raise WireV3Error
    if packet[1] == AXIS["release"]:
        item = RELEASE_BY_COORDINATE.get((packet[2], packet[3], packet[4]))
        if item is None:
            return Summary("release", UNLISTED, len(ALLOWLIST), buckets)
        return Summary("release", item["id"], item["slot"], buckets)
    if packet[1] == AXIS["os"]:
        if packet[3] != 0 or packet[4] != 0 or packet[2] >= len(OPERATING_SYSTEMS):
            raise WireV3Error
        return Summary("os", OPERATING_SYSTEMS[packet[2]], packet[2], buckets)
    raise WireV3Error


def release_slot(major: int, minor: int, patch: int) -> int | None:
    """Stable public coordinate. Unknown tuples stay unlisted; packets cannot add slots."""
    if any(type(part) is not int or not 0 <= part <= 255 for part in (major, minor, patch)):
        raise WireV3Error
    item = RELEASE_BY_COORDINATE.get((major, minor, patch))
    return None if item is None else item["slot"]
