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
    storage = WIRE["storage"]
    slots = [item["slot"] for item in ALLOWLIST]
    report_bytes = storage["maximum_report_bytes"]
    database_bytes = storage["maximum_database_bytes"]
    page_size = storage["page_size"]
    if (
        WIRE["version"] != 3
        or WIRE["not_v2_local_randomization"] is not True
        or privacy["epsilon"] != "ln(3)"
        or privacy["unit"] != "add_or_remove_one_input_report_including_admission_and_clipping"
        or sensitivity != len(METRICS) + 1
        or PACKET_BYTES != 6 + len(METRICS)
        or len(METRIC_BY_ID) != len(METRICS)
        or WIRE["state_bins"] != ["group_disabled", "sensor_missing"]
        or OPERATING_SYSTEMS != ("windows", "macos", "linux", "other")
        or WIRE["axis_rule"]
        != {
            "name": "per_report_secure_coin",
            "choices": ["release", "os"],
            "reads_report_contents": False,
            "source": "summary_path_secrets_randbelow",
            "both_axes_in_one_window": True,
            "joined_release_by_os_profile": False,
        }
        or WIRE["admission"]["cross_report_eviction"] is not False
        or WIRE["admission"]["rule"] != "every_well_formed_report"
        or "maximum_reports_per_window" in WIRE["reporting"]
        or WIRE["reporting"]["schema_version"] != 2
        or not 1 <= len(ALLOWLIST) <= WIRE["allowlist_maximum_slots"]
        or slots != list(range(len(ALLOWLIST)))
        or len({(item["major"], item["minor"], item["patch"]) for item in ALLOWLIST})
        != len(ALLOWLIST)
        or any(
            metric["group"] not in GROUPS or metric["wire_index_origin"] != 2 for metric in METRICS
        )
        or any(wire_bins(metric) > 256 for metric in METRICS)
        or type(numerator) is not int
        or type(denominator) is not int
        or not 0 < numerator < denominator
        or denominator**sensitivity > 3 * numerator**sensitivity
        or WIRE["client_budget"]["maximum_attempts_per_rolling_week"] != 7
        or WIRE["client_budget"]["minimum_attempt_spacing_seconds"] != 86400
        or WIRE["client_budget"]["maximum_packet_bytes"]
        > WIRE["client_budget"]["within_attempt_reservation_bytes"]
        or WIRE["client_budget"]["within_daily_wire_bytes"]
        != CONTRACT["limits"]["wire_bytes_per_day"]
        or WIRE["statements"]["reports_are_not_unique_people"] is not True
        or WIRE["statements"]["do_not_join_release_and_os"] is not True
        or type(report_bytes) is not int
        or type(database_bytes) is not int
        or type(page_size) is not int
        or page_size != 4096
        or report_bytes <= storage["reviewed_one_axis_32_release_bytes"]
        or database_bytes <= WIRE["reporting"]["retained_windows"] * report_bytes
        or database_bytes % page_size != 0
    ):
        raise WireV3Error


_check_contract()
RELEASE_BY_COORDINATE = {(item["major"], item["minor"], item["patch"]): item for item in ALLOWLIST}
RELEASE_BY_SLOT = {item["slot"]: item for item in ALLOWLIST}


def _quiet_indexes() -> tuple[int, int]:
    outcome = METRIC_BY_ID["outcome"]["categories"]
    reason = METRIC_BY_ID["reason"]["categories"]
    if not reason or reason[0] != "no_failure":
        raise WireV3Error
    try:
        return outcome.index("success"), outcome.index("accepted")
    except ValueError:
        raise WireV3Error from None


QUIET_SUCCESS, QUIET_ACCEPTED = _quiet_indexes()


class Summary:
    """One bounded packet after allowlist mapping. Not an installation record."""

    __slots__ = ("axis", "cohort_id", "cohort_index", "buckets")

    def __init__(self, axis: str, cohort_id: str, cohort_index: int, buckets: tuple[int, ...]):
        self.axis = axis
        self.cohort_id = cohort_id
        self.cohort_index = cohort_index
        self.buckets = buckets


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
        return {
            "lower_exclusive": bounds[measurement_index - 1],
            "upper_inclusive": None,
            "unit": unit,
        }
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


def _add(weights: dict[str, list[int]], metric_id: str, key: object, count: int) -> None:
    metric = METRIC_BY_ID[metric_id]
    if type(count) is not int or count < 1:
        raise WireV3Error
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
    row[index] = min(CLIP, row[index] + count)


def _blank() -> dict[str, list[int]]:
    return {metric["id"]: _weights(metric) for metric in METRICS}


def _permitted_groups(groups: object) -> set[str]:
    if (
        type(groups) not in (list, tuple)
        or not 1 <= len(groups) <= len(GROUPS)
        or any(type(group) is not str or group not in GROUPS for group in groups)
        or len(set(groups)) != len(groups)
    ):
        raise WireV3Error
    return set(groups)


def _coordinates(release: object, operating_system: object) -> None:
    if (
        type(release) is not tuple
        or len(release) != 3
        or any(type(part) is not int or not 0 <= part <= 255 for part in release)
        or type(operating_system) is not str
        or operating_system not in OPERATING_SYSTEMS
    ):
        raise WireV3Error


def _apply(weights: dict[str, list[int]], described: dict, count: int, permitted: set[str]) -> None:
    metric_id = described["metric"]
    if metric_id == "submissions":
        if "usage" not in permitted:
            return
        workflow = described["workflow"]
        family = workflow.split(".", 1)[0]
        _add(weights, "feature_family", family, count)
        _add(weights, "feature", workflow, count)
        return
    if metric_id == "outcomes":
        if "usage" not in permitted:
            return
        _add(weights, "outcome", described["bucket"], count)
        return
    if metric_id == "reasons":
        if "reliability" not in permitted:
            return
        _add(weights, "reason", described["bucket"], count)
        return
    spec = METRIC_BY_ID[metric_id]
    if spec["group"] not in permitted:
        return
    _add(weights, metric_id, described["bucket"], count)


def _reason_index(weights: dict[str, list[int]], random_below) -> int:
    """Choose one reason tick without treating a missing reason as no failure.

    Success and accepted support ``no_failure`` because the catalog forbids a
    failure reason on those outcomes. Every other outcome stays unresolved
    until a reason cell is present. The unresolved residual competes as
    ``sensor_missing``. It is not written into ``no_failure``.
    """
    outcome = weights["outcome"]
    explicit = weights["reason"]
    quiet = outcome[QUIET_SUCCESS] + outcome[QUIET_ACCEPTED]
    unresolved = sum(outcome) - quiet
    no_failure = min(CLIP, quiet)
    known = list(explicit)
    known[0] = min(CLIP, known[0] + no_failure)
    unknown = unresolved - sum(explicit)
    if unknown < 0:
        unknown = 0
    known_mass = sum(known)
    if known_mass == 0:
        return 1
    if unknown == 0:
        return 2 + _choose(known, random_below)
    position = _draw(known_mass + unknown, random_below)
    if position < unknown:
        return 1
    position -= unknown
    for index, weight in enumerate(known):
        if position < weight:
            return 2 + index
        position -= weight
    raise WireV3Error


def _indexes(weights: dict[str, list[int]], permitted: set[str], random_below) -> list[int]:
    indexes = []
    for metric in METRICS:
        if metric["group"] not in permitted:
            indexes.append(0)
            continue
        if metric["id"] == "reason":
            indexes.append(_reason_index(weights, random_below))
            continue
        row = weights[metric["id"]]
        indexes.append(1 if sum(row) == 0 else 2 + _choose(row, random_below))
    return indexes


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
    release: tuple[int, int, int],
    operating_system: str,
    random_below=None,
) -> bytes:
    """Clip and normalize local observations into one fixed packet.

    The first draw chooses release or coarse OS with equal probability. It does
    not read the observations, and the packet keeps only the chosen marginal.
    Each enabled metric then contributes one tick. Disabled groups and missing
    sensors use explicit bins, not a fabricated zero. Later draws weight a
    clipped histogram. They are not the publication privacy mechanism.
    ``random_below`` exists for tests; a packet cannot select it.
    """
    random_below = random_below or secrets.randbelow
    axis = "release" if _draw(2, random_below) == 0 else "os"
    permitted = _permitted_groups(groups)
    _coordinates(release, operating_system)
    if type(observations) not in (list, tuple) or not 1 <= len(observations) <= MAX_OBSERVATIONS:
        raise WireV3Error
    weights = _blank()
    try:
        for item in observations:
            _contribution, cells = observation(item)
            for cell in cells:
                _apply(weights, describe(cell), 1, permitted)
    except (MeasurementError, KeyError, WireV3Error):
        raise WireV3Error from None
    indexes = _indexes(weights, permitted, random_below)
    return encode(axis, indexes, release=release, operating_system=operating_system)


def prepare(
    rows: object,
    *,
    groups: object,
    release: tuple[int, int, int],
    operating_system: str,
    random_below=None,
) -> bytes:
    """Clip bounded ``(cell, count)`` rows into the same packet as ``summarize``.

    The rows are the pending snapshot already reserved by the Python, Electron
    and browser clients. Each count is added once and clipped per bucket. This
    does not expand a count into repeated observations or rebuild a raw event.
    The release-or-OS coin is drawn before any row is read. Publication noise
    is not applied here.
    """
    random_below = random_below or secrets.randbelow
    axis = "release" if _draw(2, random_below) == 0 else "os"
    permitted = _permitted_groups(groups)
    _coordinates(release, operating_system)
    if type(rows) not in (list, tuple) or not 1 <= len(rows) <= MAX_OBSERVATIONS:
        raise WireV3Error
    weights = _blank()
    seen: set[int] = set()
    try:
        for row in rows:
            if (
                type(row) not in (tuple, list)
                or len(row) != 2
                or type(row[0]) is not int
                or type(row[1]) is not int
                or not 0 <= row[0] <= 65535
                or not 1 <= row[1] <= CLIP
                or row[0] in seen
            ):
                raise WireV3Error
            seen.add(row[0])
            _apply(weights, describe(row[0]), row[1], permitted)
    except (MeasurementError, KeyError, WireV3Error):
        raise WireV3Error from None
    indexes = _indexes(weights, permitted, random_below)
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
        or any(
            type(value) is not int or not 0 <= value < wire_bins(metric)
            for value, metric in zip(buckets, METRICS)
        )
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
    if (
        type(packet) is not bytes
        or len(packet) != PACKET_BYTES
        or packet[0] != WIRE["version_byte"]
    ):
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


def packet_matches_groups(packet: bytes, groups: object) -> bool:
    """Every permitted group is present and every other group stays disabled."""
    permitted = _permitted_groups(groups)
    summary = decode(packet)
    return all(
        (bucket == 0) != (metric["group"] in permitted)
        for metric, bucket in zip(METRICS, summary.buckets, strict=True)
    )


def groups_remain_permitted(prepared: object, current: object) -> bool:
    """A later company restriction cannot send a group that was encoded."""
    try:
        allowed = _permitted_groups(prepared)
    except WireV3Error:
        return False
    if type(current) not in (list, tuple) or any(type(group) is not str for group in current):
        return False
    return allowed <= set(current)


def preview(packet: bytes, *, reviewed: bool = False) -> dict:
    """Exact bytes of one bounded summary. Not a locally randomized v2 body."""
    import base64

    summary = decode(packet)
    return {
        "schema_version": WIRE["version"],
        "body_base64": base64.b64encode(packet).decode("ascii"),
        "body_bytes": len(packet),
        "view": "bounded_summary",
        "coordinate": summary.cohort_index,
        "randomized_sign": None,
        "protected_unit": (
            "Bounded summary of permitted metrics. The collector can read this "
            "summary. Publication noise is added to the closed week, not on this "
            "installation. Counts are not unique people."
        ),
        "report_selection": "reviewed" if reviewed else "automatic",
        "aggregation": "bounded_summary_publication_noise",
        "randomization_privacy_loss": None,
        "per_report_privacy_loss": None,
        "privacy_bound_scope": "publication_closed_week",
        "participation_or_lifetime_guarantee": False,
    }


def format_example() -> dict:
    """Fixed synthetic bytes. Not a queue, a draw, or a sent report."""
    packet = encode("release", [1] * len(METRICS), release=(4, 46, 53))
    return {"kind": "synthetic_example", "body_encoding": "base64", **preview(packet)}


def release_slot(major: int, minor: int, patch: int) -> int | None:
    """Stable public coordinate. Unknown tuples stay unlisted; packets cannot add slots."""
    if any(type(part) is not int or not 0 <= part <= 255 for part in (major, minor, patch)):
        raise WireV3Error
    item = RELEASE_BY_COORDINATE.get((major, minor, patch))
    return None if item is None else item["slot"]
