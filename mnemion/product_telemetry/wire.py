"""Four-byte, locally randomized categorical reports; no sender or network.

Automatic reports choose a permitted view independently of measurement values.
Only one category contributes to that report. Its wire contains a random
Hadamard column and randomized sign, never the category, count, row, profile or identity.
The randomizer's bound is ln(3), conditional on the permitted view. Reviewed
packets have a fixed body within permitted groups and contribute only to volume.
Participation, policy choice and network metadata require separate controls.
"""

from __future__ import annotations

from copy import deepcopy
from importlib.resources import files
import json
import secrets

from . import CONTRACT
from .catalog import MeasurementError, describe

WIRE = json.loads(files(__package__).joinpath("wire-v2.json").read_text())
VIEWS = tuple(WIRE["views"])
GROUPS = tuple(CONTRACT["metric_groups"])
COHORTS = {view["source"]["cohort"]: view for view in VIEWS if "cohort" in view["source"]}


class WireError(ValueError):
    def __init__(self):
        super().__init__("telemetry_invalid_report")


def specification() -> dict:
    return deepcopy(WIRE)


def view(identifier: int) -> dict:
    if type(identifier) is not int or not 0 <= identifier < len(VIEWS):
        raise WireError
    return VIEWS[identifier]


def _draw(below: int, random_below) -> int:
    result = random_below(below)
    if type(result) is not int or not 0 <= result < below:
        raise WireError
    return result


def encode(identifier: int, category: int, *, reviewed: bool = False, random_below=None) -> bytes:
    selected = view(identifier)
    if (
        type(reviewed) is not bool
        or type(category) is not int
        or not 0 <= category < len(selected["values"])
    ):
        raise WireError
    if reviewed:
        # This report contributes only to volume. No categorical value, random
        # coordinate or sign is needed or allowed in a human-selectable packet.
        return bytes((WIRE["version"], identifier, 0, 2))
    random_below = random_below or secrets.randbelow
    column = _draw(selected["domain"], random_below)
    positive = (category & column).bit_count() % 2 == 0
    # Three of four equally likely outcomes keep the sign. Exact integer
    # arithmetic avoids floating-point probability or exp(epsilon) rounding.
    if _draw(4, random_below) == 3:
        positive = not positive
    return bytes((WIRE["version"], identifier, column, int(positive) | (2 if reviewed else 0)))


def decode(packet: bytes) -> tuple[int, int, int, bool]:
    if type(packet) is not bytes or len(packet) != 4 or packet[0] != WIRE["version"]:
        raise WireError
    selected = view(packet[1])
    if packet[2] >= selected["domain"] or packet[3] not in (0, 1, 2, 3):
        raise WireError
    if packet[3] & 2 and (packet[2] != 0 or packet[3] != 2):
        raise WireError
    return packet[1], packet[2], 1 if packet[3] & 1 else -1, bool(packet[3] & 2)


def _permitted(groups: object) -> tuple:
    if (
        type(groups) not in (list, tuple)
        or not 1 <= len(groups) <= len(GROUPS)
        or any(type(group) is not str or group not in GROUPS for group in groups)
        or len(set(groups)) != len(groups)
    ):
        raise WireError
    return tuple(item for item in VIEWS if item["group"] in groups)


def prepare(
    rows: object,
    *,
    groups: object,
    cohorts: object = None,
    reviewed: bool = False,
    random_below=None,
) -> bytes:
    """Sample already-coarsened local cells, with no operational object input.

    The caller must supply a fresh policy-fenced snapshot and enforce persistent
    shared privacy/wire budgets before an attempt. This pure encoder does neither
    and cannot activate collection. Missing sensors use the unobserved category.
    """
    permitted = _permitted(groups)
    if type(reviewed) is not bool:
        raise WireError
    if type(rows) not in (list, tuple) or not 1 <= len(rows) <= WIRE["maximum_rows"]:
        raise WireError
    if cohorts is None:
        cohorts = {}
    if (
        type(cohorts) is not dict
        or len(cohorts) > len(COHORTS)
        or any(
            type(name) is not str
            or name not in COHORTS
            or type(value) is not str
            or value not in COHORTS[name]["values"]
            for name, value in cohorts.items()
        )
    ):
        raise WireError
    random_below = random_below or secrets.randbelow
    selected = permitted[0]
    if not reviewed:
        position = _draw(sum(item["weight"] for item in permitted), random_below)
        for item in permitted:
            if position < item["weight"]:
                selected = item
                break
            position -= item["weight"]
    source = selected["source"]
    counts = [0] * len(selected["values"])
    seen = set()
    try:
        for row in rows:
            if (
                type(row) not in (tuple, list)
                or len(row) != 2
                or type(row[0]) is not int
                or type(row[1]) is not int
                or not 1 <= row[1] <= WIRE["maximum_cell_count"]
                or row[0] in seen
            ):
                raise WireError
            cell = describe(row[0])
            seen.add(row[0])
            if source.get("metric") != cell["metric"] or selected["group"] != cell["group"]:
                continue
            field = source["field"]
            value = cell["workflow"].split(".", 1)[0] if field == "family" else cell[field]
            index = value + 1 if type(value) is int else selected["values"].index(value)
            if not 1 <= index < len(counts):
                raise WireError
            counts[index] += row[1]
    except (MeasurementError, KeyError, ValueError, TypeError, IndexError):
        raise WireError from None
    category = 0
    if reviewed:
        return encode(selected["id"], 0, reviewed=True)
    if "cohort" in source:
        category = selected["values"].index(cohorts.get(source["cohort"], "unobserved"))
    elif (total := sum(counts)) > 0:
        position = _draw(total, random_below)
        for index, count in enumerate(counts):
            if position < count:
                category = index
                break
            position -= count
    return encode(selected["id"], category, reviewed=reviewed, random_below=random_below)


def preview(packet: bytes) -> dict:
    """An exact packet preview; neither a sender nor a decoded personal value."""
    import base64

    identifier, column, sign, reviewed = decode(packet)
    return {
        "schema_version": WIRE["version"],
        "body_base64": base64.b64encode(packet).decode("ascii"),
        "body_bytes": len(packet),
        "view": view(identifier)["name"],
        "coordinate": column,
        "randomized_sign": None if reviewed else sign,
        "protected_unit": "Fixed body within permitted metric groups; no category is transmitted. Participation and policy choice are not protected."
        if reviewed
        else WIRE["protected_unit"],
        "report_selection": "reviewed" if reviewed else "automatic",
        "aggregation": "coarse_global_volume_only"
        if reviewed
        else "automatic_categorical_estimates",
        "randomization_privacy_loss": None if reviewed else "ln(3)",
        "per_report_privacy_loss": None if reviewed else "ln(3)",
        "privacy_bound_scope": "fixed_body_for_permitted_groups"
        if reviewed
        else "packet_independent_inclusion",
        "participation_or_lifetime_guarantee": False,
    }


def format_example() -> dict:
    """Fixed synthetic bytes, unrelated to any queue, random draw or attempt."""
    return {
        "kind": "synthetic_example",
        "body_encoding": "base64",
        **preview(bytes((WIRE["version"], 0, 7, 0))),
    }
