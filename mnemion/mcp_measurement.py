"""Local stdio ownership, outside the numeric encoder and reusable SDK.

HTTP gateways never call this boundary. Only fixed receipt metadata is observed;
credentials, requests, responses and exception text stay with the tool caller.
"""

from importlib.resources import files
import json

from . import control_measurement
from .product_telemetry import workflow

try:
    ORIGINS = json.loads(
        files("mnemion.product_telemetry").joinpath("mcp-origins.json").read_text()
    )
except (OSError, ValueError):
    ORIGINS = {"gateway": {}, "legacy": {}}


def _begin(tool, *, legacy=False, operation=None, request=None):
    try:
        spec = ORIGINS["legacy" if legacy else "gateway"].get(tool)
        if not spec or "exclusion" in spec:
            return None
        if spec.get("control"):
            return control_measurement.begin(operation, request or {})
        active = workflow.begin(spec["workflow"], "headless")
        return (
            control_measurement.ControlMeasurement(active, spec, spec["workflow"])
            if active
            else None
        )
    except Exception:
        return None


def invoke(client, tool, action, *, operation=None, request=None):
    """Observe one owned invocation; a new API client belongs to this call only."""
    measurement = _begin(tool, operation=operation, request=request)
    if measurement is None:
        return action()
    receipt = [None]
    installed = []

    def sending(_request):
        receipt[0] = None

    def received(response):
        try:
            value = response.headers.get("X-Mnemion-Idempotency")
            receipt[0] = value if value in {"new", "replayed"} else None
        except Exception:
            receipt[0] = None

    try:
        # Never read a body, URL, credential or request ID to observe a receipt.
        # Generic SDK instances are unchanged; this client is scoped to one tool.
        if operation is None:
            try:
                for name, callback in (("request", sending), ("response", received)):
                    hooks = client._http.event_hooks[name]
                    hooks.append(callback)
                    installed.append((hooks, callback))
            except Exception:
                measurement.discard()
        try:
            result = action()
        except Exception as error:
            from .agent_control import ControlError
            from .sdk import MnemionError

            if isinstance(error, (ControlError, MnemionError)):
                measurement.failed(
                    code=error.code,
                    status=error.status,
                    outcome=error.outcome if isinstance(error, ControlError) else "received",
                )
            else:
                measurement.failed(code="unclassified", status=None, outcome="unknown")
            raise
        measurement.succeeded(result if operation is not None else {"idempotency": receipt[0]})
        return result
    finally:
        for hooks, callback in installed:
            try:
                hooks.remove(callback)
            except (ValueError, AttributeError):
                pass


def invoke_legacy(tool, action):
    """The old stdio loop owns this action; imported handlers do not."""
    measurement = _begin(tool, legacy=True)
    try:
        result = action()
    except Exception:
        if measurement:
            measurement.failed(code="unclassified", status=None, outcome="received")
        raise
    if measurement:
        if isinstance(result, dict) and ("error" in result or result.get("success") is False):
            measurement.failed(code="unclassified", status=None, outcome="received")
        else:
            measurement.succeeded({})
    return result
