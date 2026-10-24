"""Four-byte, locally randomized categorical reports; no sender or network.

The reviewed view is sampled independently of measurement values. Only one
category contributes to a report. The wire contains its random Hadamard column
and randomized sign, never the category, count, row, cohort profile or identity.
The per-report bound is ln(3), conditional on the permitted view. Participation,
policy choice, repeated reports and network metadata require separate controls.
"""

from __future__ import annotations

from copy import deepcopy
from importlib.resources import files
import json
import secrets

from . import CONTRACT
from .catalog import MeasurementError, describe

WIRE = json.loads(files(__package__).joinpath("wire-v1.json").read_text())
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


def encode(identifier: int, category: int, *, random_below=None) -> bytes:
    selected = view(identifier)
    if type(category) is not int or not 0 <= category < len(selected["values"]):
        raise WireError
    random_below = random_below or secrets.randbelow
    column = _draw(selected["domain"], random_below)
    positive = (category & column).bit_count() % 2 == 0
    # Three of four equally likely outcomes keep the sign. Exact integer
    # arithmetic avoids floating-point probability or exp(epsilon) rounding.
    if _draw(4, random_below) == 3:
        positive = not positive
    return bytes((WIRE["version"], identifier, column, int(positive)))


def decode(packet: bytes) -> tuple[int, int, int]:
    if type(packet) is not bytes or len(packet) != 4 or packet[0] != WIRE["version"]:
        raise WireError
    selected = view(packet[1])
    if packet[2] >= selected["domain"] or packet[3] not in (0, 1):
        raise WireError
    return packet[1], packet[2], 1 if packet[3] else -1


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
    random_below=None,
) -> bytes:
    """Sample already-coarsened local cells, with no operational object input.

    The caller must supply a fresh policy-fenced snapshot and enforce persistent
    shared privacy/wire budgets before an attempt. This pure encoder does neither
    and cannot activate collection. Missing sensors use the unobserved category.
    """
    permitted = _permitted(groups)
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
    position = _draw(sum(item["weight"] for item in permitted), random_below)
    selected = permitted[-1]
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
    if "cohort" in source:
        category = selected["values"].index(cohorts.get(source["cohort"], "unobserved"))
    elif (total := sum(counts)) > 0:
        position = _draw(total, random_below)
        for index, count in enumerate(counts):
            if position < count:
                category = index
                break
            position -= count
    return encode(selected["id"], category, random_below=random_below)


def preview(packet: bytes) -> dict:
    """An exact packet preview; neither a sender nor a decoded personal value."""
    import base64

    identifier, column, sign = decode(packet)
    return {
        "schema_version": WIRE["version"],
        "body_base64": base64.b64encode(packet).decode("ascii"),
        "body_bytes": len(packet),
        "view": view(identifier)["name"],
        "coordinate": column,
        "randomized_sign": sign,
        "protected_unit": WIRE["protected_unit"],
        "per_report_privacy_loss": "ln(3)",
        "participation_or_lifetime_guarantee": False,
    }
