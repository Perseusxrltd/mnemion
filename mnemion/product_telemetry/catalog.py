"""Fixed aggregate cells shared with the app; never accept operational objects.

Cell numbers are catalog coordinates, not record or installation identities.
Only coarse numeric buckets enter the queue. The catalog is small and decoded
arithmetically instead of allocating a large cross-product of metadata objects.
"""

from __future__ import annotations

from bisect import bisect_left
from copy import deepcopy
from importlib.resources import files
import json
import math

CATALOG = json.loads(files(__package__).joinpath("catalog.json").read_text())
SURFACES = tuple(CATALOG["surfaces"])
WORKFLOWS = tuple(
    f"{family}.{operation}"
    for family, operations in CATALOG["workflows"].items()
    for operation in operations
)
WORKFLOW_IDS = {name: index for index, name in enumerate(WORKFLOWS)}
OUTCOMES = tuple(CATALOG["outcomes"])
REASONS = tuple(CATALOG["reasons"])
METRICS = CATALOG["metrics"]
RESOURCE_METRICS = CATALOG["resource_metrics"]
SURFACE_STRIDE = 128
WORKFLOW_STRIDE = len(SURFACES) * SURFACE_STRIDE
RESOURCE_BASE = 61440
MAX_PRIMITIVE = 2**53 - 1


class MeasurementError(ValueError):
    def __init__(self):
        super().__init__("telemetry_invalid_measurement")


def specification() -> dict:
    return deepcopy(CATALOG)


def control_specification() -> dict:
    """Reviewed owned CLI coverage, including every explicit exclusion."""
    return json.loads(files(__package__).joinpath("control-origins.json").read_text())


def _metric_slots() -> tuple:
    offset = 1 + len(OUTCOMES) + len(REASONS)
    slots = []
    for name, spec in METRICS.items():
        slots.append((name, offset, spec))
        offset += len(spec["upper_bounds"])
    assert offset <= SURFACE_STRIDE
    assert len(WORKFLOWS) * WORKFLOW_STRIDE <= RESOURCE_BASE
    return tuple(slots)


SLOTS = _metric_slots()


def bucket(value: object, upper_bounds: list[int]) -> int:
    # bool is an int subclass in Python and must not become a numeric sensor.
    if (
        type(value) not in (int, float)
        or not 0 <= value <= MAX_PRIMITIVE
        or not math.isfinite(value)
    ):
        raise MeasurementError
    return min(bisect_left(upper_bounds, value), len(upper_bounds) - 1)


def observation(value: object) -> tuple[int, tuple[int, ...]]:
    """Return one bounded contribution key and cells, dropping exact primitives.

    The caller must own the disclosed workflow. This validator does not infer
    ownership from credentials, API paths, audit rows or server responses.
    """
    if type(value) is not dict or type(value.get("kind")) is not str:
        raise MeasurementError
    if value["kind"] == "resource":
        if set(value) != {"kind", "metric", "value"} or type(value["metric"]) is not str:
            raise MeasurementError
        if value["metric"] not in RESOURCE_METRICS:
            raise MeasurementError
        index = tuple(RESOURCE_METRICS).index(value["metric"])
        spec = RESOURCE_METRICS[value["metric"]]
        return 512 + index, (
            RESOURCE_BASE + index * 16 + bucket(value["value"], spec["upper_bounds"]),
        )
    if value["kind"] not in {"submission", "outcome"}:
        raise MeasurementError
    if (
        type(value.get("workflow")) is not str
        or value["workflow"] not in WORKFLOW_IDS
        or type(value.get("surface")) is not str
        or value["surface"] not in SURFACES
    ):
        raise MeasurementError
    contribution = WORKFLOW_IDS[value["workflow"]] * len(SURFACES) + SURFACES.index(
        value["surface"]
    )
    base = contribution * SURFACE_STRIDE
    if value["kind"] == "submission":
        if set(value) != {"kind", "workflow", "surface"}:
            raise MeasurementError
        return contribution, (base,)
    if (
        set(value) - {"kind", "workflow", "surface", "outcome", "reason", *METRICS}
        or type(value.get("outcome")) is not str
        or value["outcome"] not in OUTCOMES
        or type(value.get("reason", "none")) is not str
        or value.get("reason", "none") not in REASONS
    ):
        raise MeasurementError
    reason = value.get("reason", "none")
    if reason != "none" and value["outcome"] in {"success", "accepted"}:
        raise MeasurementError
    cells = [base + 1 + OUTCOMES.index(value["outcome"])]
    if reason != "none":
        cells.append(base + 1 + len(OUTCOMES) + REASONS.index(reason))
    family = value["workflow"].split(".", 1)[0]
    for name, offset, spec in SLOTS:
        if name not in value:
            continue
        if spec["families"] != "all" and family not in spec["families"]:
            raise MeasurementError
        cells.append(base + offset + bucket(value[name], spec["upper_bounds"]))
    if len(cells) > CATALOG["limits"]["cells_per_observation"]:
        raise MeasurementError
    return contribution, tuple(cells)


def describe(cell: int) -> dict:
    if type(cell) is not int or not 0 <= cell <= 65535:
        raise MeasurementError
    if cell >= RESOURCE_BASE:
        index, offset = divmod(cell - RESOURCE_BASE, 16)
        if index >= len(RESOURCE_METRICS):
            raise MeasurementError
        name, spec = tuple(RESOURCE_METRICS.items())[index]
        if offset >= len(spec["upper_bounds"]):
            raise MeasurementError
        return {"metric": name, "group": spec["group"], "bucket": offset, "unit": spec["unit"]}
    workflow, within = divmod(cell, WORKFLOW_STRIDE)
    surface, offset = divmod(within, SURFACE_STRIDE)
    if workflow >= len(WORKFLOWS):
        raise MeasurementError
    context = {"workflow": WORKFLOWS[workflow], "surface": SURFACES[surface]}
    if offset == 0:
        return {**context, "metric": "submissions", "group": "usage"}
    if 1 <= offset <= len(OUTCOMES):
        return {**context, "metric": "outcomes", "group": "usage", "bucket": OUTCOMES[offset - 1]}
    reason = offset - 1 - len(OUTCOMES)
    if 0 <= reason < len(REASONS):
        if reason == 0:
            raise MeasurementError  # No redundant 'none' failure observations.
        return {**context, "metric": "reasons", "group": "reliability", "bucket": REASONS[reason]}
    family = WORKFLOWS[workflow].split(".", 1)[0]
    for name, start, spec in SLOTS:
        if start <= offset < start + len(spec["upper_bounds"]):
            if spec["families"] != "all" and family not in spec["families"]:
                raise MeasurementError
            return {
                **context,
                "metric": name,
                "group": spec["group"],
                "bucket": offset - start,
                "unit": spec["unit"],
            }
    raise MeasurementError
