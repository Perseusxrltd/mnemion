"""Owned CLI boundary: select fixed telemetry primitives from a private result.

This is deliberately outside the reusable SDK and HTTP/MCP server. Invoking a
generic client does not infer a telemetry owner or a privacy choice.
"""

from __future__ import annotations

from functools import wraps

from .product_telemetry import workflow
from .product_telemetry.catalog import METRICS, control_specification

ORIGINS = control_specification()


def _optional(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            return None

    return call


class ControlMeasurement:
    def __init__(self, measurement: workflow.Workflow, spec: dict, name: str):
        self._measurement = measurement
        self._spec = spec
        self._name = name

    @_optional
    def discard(self) -> None:
        self._measurement.discard()

    @_optional
    def succeeded(self, result: dict) -> None:
        # The server supplies only this fixed metadata. A legacy server, a lost
        # response or an already cached write is not evidence of a new mutation.
        if result.get("idempotency") == "replayed" or (
            self._spec.get("fresh_receipt") and result.get("idempotency") != "new"
        ):
            self._measurement.discard()
            return
        numeric = {}
        family = self._name.split(".", 1)[0]
        size = result.get("response_bytes")
        if family in METRICS["payload_bytes_received"]["families"] and type(size) is int:
            numeric["payload_bytes_received"] = size
        self._measurement.finish(self._spec["completion"], **numeric)

    @_optional
    def failed(self, *, code: str, status: int | None, outcome: str) -> None:
        if self._spec.get("fresh_receipt") and outcome != "not_sent":
            self._measurement.discard()
            return
        reason, result = "other_failure", "failed"
        if status in {401, 403}:
            reason, result = "authorization", "denied"
        elif status in {400, 422} or outcome == "not_sent":
            reason = "invalid_input"
        elif status == 409:
            reason = "conflict"
        elif code == "inference_busy":
            reason, result = "resource_pressure", "deferred"
        elif code == "response_hash_mismatch":
            reason = "integrity_check"
        elif code == "response_deadline":
            reason = "network_timeout"
        elif code == "transport_error":
            reason = "offline"
        if outcome == "unknown" and result == "failed":
            result = "unconfirmed"
        self._measurement.finish(result, reason)


@_optional
def begin(operation: str, request: dict) -> ControlMeasurement | None:
    spec = ORIGINS["operations"].get(operation)
    if spec is None or "exclusion" in spec:
        return None
    name = spec.get("workflow")
    if "variants" in spec:
        # Only the reviewed enum reaches the measurement layer; arbitrary
        # request parameters, content and identities stay in the CLI boundary.
        section, field = spec["selector"]
        selected = request.get(section, {}).get(field)
        name = spec["variants"].get(selected) if type(selected) is str else None
    if name is None:
        return None
    measurement = workflow.begin(name, "headless")
    return ControlMeasurement(measurement, spec, name) if measurement is not None else None
