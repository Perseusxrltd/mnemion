"""Bounded readiness evidence without process arguments, paths or credentials."""

from .update_manifest import ManifestError


START_BUDGET_SECONDS = 180
STOP_BUDGET_SECONDS = 90


CHECKS = (
    "running",
    "ready",
    "service_ready",
    "http_ready",
    "instance_matches",
    "children_initialized",
)
STATES = frozenset(
    {"STOPPED", "STARTING", "RUNNING", "BACKOFF", "STOPPING", "EXITED", "FATAL", "UNKNOWN"}
)
REASONS = frozenset(
    {"request_timeout", "readiness_timeout", "stop_timeout", "missing_child", "child_failed"}
)
ROLES = ("mnemion-api", "mnemion-worker", "mnemion-updater")


def diagnostics(value):
    """Accept only fixed vocabulary and booleans from a saved failure record."""
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("reason"), str)
        or value["reason"] not in REASONS
    ):
        return None
    result = {"reason": value["reason"]}
    if isinstance(value.get("direction"), str) and value["direction"] in {"start", "stop"}:
        result["direction"] = value["direction"]
    # Historical 60-second startup failures retain their original measured bound.
    if type(value.get("budget_seconds")) is int and value["budget_seconds"] in {
        60,
        START_BUDGET_SECONDS,
        STOP_BUDGET_SECONDS,
    }:
        result["budget_seconds"] = value["budget_seconds"]
    checks = value.get("checks")
    if isinstance(checks, dict):
        result["checks"] = {name: checks[name] for name in CHECKS if type(checks.get(name)) is bool}
    processes = value.get("process_states")
    if isinstance(processes, dict):
        result["process_states"] = {
            name: processes[name]
            for name in ROLES
            if isinstance(processes.get(name), str) and processes[name] in STATES
        }
    if type(value.get("other_children_running")) is bool:
        result["other_children_running"] = value["other_children_running"]
    return result


class ProcessTransitionError(ManifestError):
    def __init__(self, message, *, reason, start, observation=None):
        super().__init__(message)
        observation = observation or {}
        processes = observation.get("processes", [])
        self.diagnostics = diagnostics(
            {
                "reason": reason,
                "direction": "start" if start else "stop",
                "budget_seconds": START_BUDGET_SECONDS if start else STOP_BUDGET_SECONDS,
                "checks": observation,
                "process_states": {
                    item["name"]: item.get("statename") for item in processes if "name" in item
                },
                "other_children_running": (
                    all(
                        item.get("statename") == "RUNNING"
                        for item in processes
                        if item.get("name") not in ROLES
                    )
                    if "processes" in observation
                    else None
                ),
            }
        )
