"""Portable bounded inspection state. No clocks, entropy, storage or transport."""

from __future__ import annotations

import json
import re

from .review_clock import check_review_lifetime, review_lifetime
from .wire_v3 import PACKET_BYTES

GROUPS = ("usage", "reliability", "performance", "resources")
OUTCOMES = (
    "inactive",
    "paused",
    "held",
    "approved",
    "consumed",
    "discarded",
    "invalidated",
    "expired",
)


def _invalid():
    return ValueError("telemetry_review_unavailable")


def _integer(value, maximum):
    return type(value) is int and 0 <= value <= maximum


def _token(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def fresh_review():
    return {"version": 1, "mode": "automatic", "token": None, "outcome": "inactive", "report": None}


def review_context(value):
    if type(value) is not dict or set(value) != {"stamp", "groups", "binding"}:
        raise _invalid()
    stamp, groups, binding = value["stamp"], value["groups"], value["binding"]
    if (
        type(stamp) is not dict
        or set(stamp) != {"revision", "store_generation"}
        or not _integer(stamp["revision"], 2147483646)
        or not _token(stamp["store_generation"])
        or type(groups) is not list
        or not 0 < len(groups) <= 4
        or any(type(group) is not str or group not in GROUPS for group in groups)
        or len(set(groups)) != len(groups)
    ):
        raise _invalid()
    if (
        type(binding) is not dict
        or set(binding)
        != {"disclosure_version", "wire_version", "catalog_version", "destination", "route_address"}
        or not _integer(binding["disclosure_version"], 1000000)
        or not _integer(binding["wire_version"], 255)
        or not _integer(binding["catalog_version"], 1000000)
        or type(binding["destination"]) is not str
        or len(binding["destination"]) > 512
        or re.fullmatch(r"https://[^\s/?#@]+/v3/report", binding["destination"]) is None
        or (
            binding["route_address"] is not None
            and (
                type(binding["route_address"]) is not str
                or len(binding["route_address"]) > 45
                or re.fullmatch(r"[0-9a-f:.]+", binding["route_address"]) is None
            )
        )
    ):
        raise _invalid()
    return {
        "stamp": dict(stamp),
        "groups": [group for group in GROUPS if group in groups],
        "binding": dict(binding),
    }


def review_state(value):
    if (
        type(value) is not dict
        or set(value) != {"version", "mode", "token", "outcome", "report"}
        or type(value["version"]) is not int
        or value["version"] != 1
        or value["mode"] not in ("automatic", "review")
        or value["outcome"] not in OUTCOMES
        or (value["token"] is not None and not _token(value["token"]))
        or (value["mode"] == "automatic" and value["outcome"] != "inactive")
        or (
            value["mode"] == "review"
            and (value["outcome"] == "inactive" or not _token(value["token"]))
        )
    ):
        raise _invalid()
    live = value["outcome"] in ("held", "approved")
    if live != (value["report"] is not None):
        raise _invalid()
    report = None
    if live:
        raw = value["report"]
        if (
            type(raw) is not dict
            or set(raw) != {"packet", "stamp", "groups", "binding", "lifetime"}
            or type(raw["packet"]) is not list
            or len(raw["packet"]) != PACKET_BYTES
            or any(not _integer(byte, 255) for byte in raw["packet"])
        ):
            raise _invalid()
        context = review_context({key: raw[key] for key in ("stamp", "groups", "binding")})
        report = {
            **context,
            "packet": list(raw["packet"]),
            "lifetime": review_lifetime(raw["lifetime"]),
        }
    return {**value, "report": report}


def salvage_stale_review(raw):
    """Invalidate one valid stored v2 manual approval.

    A valid automatic review has a null report and needs no salvage. An
    invalid automatic state is not recovered into permission to send. A
    malformed manual review stays unreadable. Consent and company policy
    are not touched.
    """
    if type(raw) is not str or len(raw) > 4096:
        return None
    try:
        value = json.loads(raw)
    except (ValueError, TypeError, RecursionError, OverflowError):
        return None
    if (
        type(value) is not dict
        or set(value) != {"version", "mode", "token", "outcome", "report"}
        or value.get("version") != 1
        or value.get("mode") != "review"
        or value.get("outcome") not in ("held", "approved")
        or not _token(value.get("token"))
        or not _legacy_manual_report(value.get("report"))
    ):
        return None
    return {
        "version": 1,
        "mode": "review",
        "token": value["token"],
        "outcome": "invalidated",
        "report": None,
    }


def _legacy_manual_report(report):
    """A structurally valid old manual review, not a four-byte fragment."""
    if type(report) is not dict or set(report) != {
        "packet",
        "stamp",
        "groups",
        "binding",
        "lifetime",
    }:
        return False
    packet = report["packet"]
    stamp, groups, binding = report["stamp"], report["groups"], report["binding"]
    destination = binding.get("destination") if type(binding) is dict else None
    legacy = type(binding) is dict and (
        binding.get("wire_version") == 2
        or (type(destination) is str and destination.endswith("/v1/report"))
    )
    route = binding.get("route_address") if type(binding) is dict else None
    if (
        not legacy
        or type(packet) is not list
        or len(packet) != 4
        or any(not _integer(byte, 255) for byte in packet)
        or type(stamp) is not dict
        or set(stamp) != {"revision", "store_generation"}
        or not _integer(stamp["revision"], 2147483646)
        or not _token(stamp["store_generation"])
        or type(groups) is not list
        or not 0 < len(groups) <= 4
        or any(type(group) is not str or group not in GROUPS for group in groups)
        or len(set(groups)) != len(groups)
        or set(binding)
        != {
            "disclosure_version",
            "wire_version",
            "catalog_version",
            "destination",
            "route_address",
        }
        or not _integer(binding["disclosure_version"], 1000000)
        or not _integer(binding["wire_version"], 255)
        or not _integer(binding["catalog_version"], 1000000)
        or type(destination) is not str
        or len(destination) > 512
        or (
            route is not None
            and (
                type(route) is not str
                or len(route) > 45
                or re.fullmatch(r"[0-9a-f:.]+", route) is None
            )
        )
    ):
        return False
    try:
        review_lifetime(report["lifetime"])
    except (ValueError, TypeError, OverflowError):
        return False
    return True


def parse_review(raw):
    if type(raw) is not str or len(raw) > 4096:
        raise _invalid()
    try:
        return review_state(json.loads(raw))
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise _invalid() from None


def serialize_review(value):
    raw = json.dumps(review_state(value), separators=(",", ":"))
    if len(raw) > 4096:
        raise _invalid()
    return raw


def clear_review(value, outcome="invalidated"):
    if outcome not in ("consumed", "discarded", "invalidated", "expired"):
        raise _invalid()
    return {
        **value,
        "outcome": "inactive" if value["mode"] == "automatic" else outcome,
        "report": None,
    }


def check_review(value, context, now, clock):
    state = review_state(value)
    report = state["report"]
    if report is None:
        return state
    try:
        expected = review_context(context)
        if review_context({key: report[key] for key in ("stamp", "groups", "binding")}) != expected:
            return clear_review(state)
        lifetime = check_review_lifetime(report["lifetime"], now, clock)
        return (
            {**state, "report": {**report, "lifetime": lifetime}}
            if lifetime
            else clear_review(state, "expired")
        )
    except (ValueError, TypeError, OverflowError):
        return clear_review(state)
