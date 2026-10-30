"""Allowlisted first-attempt outcome for one opted-in resource launch.

The stage is kept when a guard is missing or unreadable. This is not a budget result.
"""

from __future__ import annotations

RESOURCE_ADMISSION = "MNEMION_TELEMETRY_RESOURCE_ADMISSION"
_NETWORKS = {"unknown", "metered", "unmetered"}
_REASONS = {
    "allowed",
    "clock",
    "network_not_allowed",
    "network_constrained",
    "offline",
    "cpu_busy",
    "cpu_unobserved",
    "memory",
    "thermal",
    "read_failed",
}
_OUTCOMES = {
    "unknown",
    "release_unavailable",
    "eligible_refused",
    "prepare_refused",
    "aborted",
    "reserve_refused",
    "reserved",
}
_SAMPLED = {"prepare_refused", "aborted", "reserve_refused", "reserved"}


def admission_diagnostic_enabled(environ: object) -> bool:
    """True only for the explicit resource-fixture opt-in. Delivery diagnostics do not count."""
    if type(environ) is not dict:
        return False
    return environ.get(RESOURCE_ADMISSION) == "1"


def unknown_admission_outcome() -> dict:
    return {"schema_version": 1, "outcome": "unknown", "guard": None}


def _version_one(value: object) -> bool:
    """JSON true is a bool, and bool is an int. Only a real integer 1 is a version."""
    return type(value) is int and value == 1


def _choice(value: object, allowed: set[str]) -> str | None:
    """Membership on a list or object throws. Require the scalar before the set."""
    if type(value) is not str or value not in allowed:
        return None
    return value


def _guard(value: object) -> dict | None:
    if type(value) is not dict:
        return None
    if not _version_one(value.get("schema_version")) or type(value.get("constrained")) is not bool:
        return None
    network = _choice(value.get("network"), _NETWORKS)
    reason = _choice(value.get("reason"), _REASONS)
    if network is None or reason is None:
        return None
    return {
        "schema_version": 1,
        "network": network,
        "constrained": value["constrained"],
        "reason": reason,
    }


def sanitize_admission_outcome(value: object) -> dict | None:
    if type(value) is not dict:
        return None
    outcome = _choice(value.get("outcome"), _OUTCOMES)
    if not _version_one(value.get("schema_version")) or outcome is None:
        return None
    return {
        "schema_version": 1,
        "outcome": outcome,
        "guard": _guard(value.get("guard")) if outcome in _SAMPLED else None,
    }


def public_admission_fields(app: object, raw: object) -> dict:
    """Keep one sanitized outcome when either receipt says the launch opted in."""
    diagnostic = (type(app) is dict and app.get("admission_diagnostic") is True) or (
        type(raw) is dict and raw.get("admission_diagnostic") is True
    )
    if not diagnostic:
        return {}
    outcome = sanitize_admission_outcome(
        app.get("admission_outcome") if type(app) is dict else None
    )
    return {
        "admission_diagnostic": True,
        "admission_outcome": outcome if outcome is not None else unknown_admission_outcome(),
    }
