"""Explicit OS-account report controls, independent of any running workspace.

Inspection never grants collection permission, reads performance gauges or
spends delivery allowance. Only a later eligible owner can claim approved bytes.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import secrets
import sqlite3
import time

from . import aggregate, policy, review, review_storage, wire
from .review_clock import check_review_lifetime, read_review_clock, start_review_lifetime

DAY_MS = 86400000


def _now_ms():
    return time.time_ns() // 1000000


def context(preference, company):
    if not aggregate._permitted(
        preference, company, preference["revision"], preference["store_generation"]
    ):
        return None
    from .catalog import specification
    from .endpoint import release_address

    return review.review_context(
        {
            "stamp": {
                "revision": preference["revision"],
                "store_generation": preference["store_generation"],
            },
            "groups": company["metric_groups"],
            "binding": {
                "disclosure_version": policy.DISCLOSURE_VERSION,
                "wire_version": wire.specification()["version"],
                "catalog_version": specification()["version"],
                "destination": policy.COLLECTOR_URL,
                "route_address": release_address(),
            },
        }
    )


def checked(state, preference, company, now):
    if state["report"] is None:
        return state
    result = review.check_review(state, context(preference, company), now, read_review_clock())
    if result["report"] is not None:
        # Exact structural decoding is separate from bounded storage parsing.
        try:
            identifier, _, _, reviewed = wire.decode(bytes(result["report"]["packet"]))
            expected = next(
                (view["id"] for view in wire.VIEWS if view["group"] in result["report"]["groups"]),
                None,
            )
            if not reviewed or identifier != expected:
                return review.clear_review(result)
        except (ValueError, TypeError):
            return review.clear_review(result)
    return result


def current_metadata(metadata, preference, company, now):
    """The claimed packet's original review expiry also fences final handoff."""
    expected = context(preference, company)
    if (
        expected is None
        or {key: metadata[key] for key in ("stamp", "groups", "binding")} != expected
    ):
        return None
    lifetime = check_review_lifetime(metadata["lifetime"], now, read_review_clock())
    return {**metadata, "lifetime": lifetime} if lifetime else None


def _result(root, state, message, *, reveal=False, policy_path=None):
    report = state["report"]
    return {
        "schema_version": 1,
        "status": policy.status(root, policy_path=policy_path),
        "review": {
            "mode": state["mode"],
            "token": state["token"],
            "outcome": state["outcome"],
            "report_available": report is not None,
            "expires_ms": report["lifetime"]["expires_ms"] if report else None,
            "created_ms": report["lifetime"]["created_ms"] if report else None,
        },
        "packet": wire.preview(bytes(report["packet"])) if reveal and report else None,
        "message": message,
        "interactive_privacy_qualified": False,
    }


def status(root: Path | None = None, *, policy_path: Path | None = None):
    """Body-free snapshot; no creation, repair, migration or clock initialization."""
    root = root if root is not None else policy.default_directory()
    state, message = review.fresh_review(), "not_initialized"
    try:
        policy._root_safe(root)
        if policy._file_safe(root / policy.DATABASE_NAME):
            with closing(policy._connect(root / policy.DATABASE_NAME, readonly=True)) as connection:
                connection.execute("BEGIN")
                policy._preferences(connection)
                if connection.execute("PRAGMA user_version").fetchone()[0] < 6:
                    message = "upgrade_required"
                else:
                    state = review_storage.read(connection)
                    message = "stored_snapshot" if state["report"] else state["outcome"]
    except (OSError, sqlite3.Error, ValueError, OverflowError):
        # Unknown state cannot advertise automatic delivery or a usable token.
        return {
            **_result(root, review.fresh_review(), "unavailable", policy_path=policy_path),
            "review": None,
        }
    return _result(root, state, message, policy_path=policy_path)


def _request(action, value):
    fields = {"expected_revision", "expected_generation", "expected_review_token"}
    if action == "review_mode":
        fields.add("mode")
    if (
        action not in ("review_mode", "inspect_report", "approve_report", "discard_report")
        or type(value) is not dict
        or set(value) != fields
        or type(value["expected_revision"]) is not int
        or not 0 <= value["expected_revision"] < 2147483647
        or (
            value["expected_generation"] is not None
            and not policy.valid_generation(value["expected_generation"])
        )
        or (
            value["expected_review_token"] is not None
            and not policy.valid_generation(value["expected_review_token"])
        )
        or (action == "review_mode" and value["mode"] not in ("automatic", "review"))
    ):
        raise policy.PolicyError("telemetry_invalid_review")


def _budget_ready(connection, now):
    from .delivery import (
        _state,
        DAY_MS,
        WEEK_MS,
        MAX_CLOCK_MS,
        MAX_ATTEMPTS,
        RESERVED_BYTES,
        DAILY_BYTES,
        JITTER_MS,
    )

    if type(now) is not int or not 0 <= now <= MAX_CLOCK_MS - DAY_MS - JITTER_MS:
        return False
    state, spent = _state(connection)
    recent = [row for row in spent if row[1] > now - WEEK_MS]
    return (
        now >= state[0]
        and now >= state[1]
        and not (state[2] and now < state[3])
        and len(recent) < MAX_ATTEMPTS
        and sum(cost for _, at, cost in recent if at > now - DAY_MS) + RESERVED_BYTES <= DAILY_BYTES
    )


def execute(root: Path | None, action: str, request: dict, *, policy_path: Path | None = None):
    _request(action, request)
    root = root if root is not None else policy.default_directory()
    try:
        created = policy._initialize(root) if action == "review_mode" else False
        policy._root_safe(root)
        if not policy._file_safe(root / policy.DATABASE_NAME):
            return status(root, policy_path=policy_path)
        with closing(policy._connect(root / policy.DATABASE_NAME)) as connection:
            connection.execute("PRAGMA busy_timeout=250")
            connection.execute("BEGIN IMMEDIATE")
            preference = policy._preferences(connection)
            if request["expected_revision"] != preference["revision"] or request[
                "expected_generation"
            ] != (None if created else preference["store_generation"]):
                raise policy.PolicyError("telemetry_choice_changed")
            policy._queue_schema(connection)
            state = review_storage.read(connection)
            if request["expected_review_token"] != state["token"]:
                raise policy.PolicyError("telemetry_review_changed")
            message, reveal, cancel = state["outcome"], False, False
            if action == "review_mode":
                if request["mode"] != state["mode"]:
                    state = {
                        "version": 1,
                        "mode": request["mode"],
                        "token": secrets.token_hex(16),
                        "outcome": "paused" if request["mode"] == "review" else "inactive",
                        "report": None,
                    }
                    cancel = True
                message = state["outcome"]
            elif action == "discard_report":
                if state["mode"] != "review":
                    raise policy.PolicyError("telemetry_review_not_paused")
                state = {**review.clear_review(state, "discarded"), "token": secrets.token_hex(16)}
                message, cancel = "discarded", True
            else:
                if state["mode"] != "review":
                    raise policy.PolicyError("telemetry_review_not_paused")
                now, company = _now_ms(), policy.company_policy(policy_path)
                if state["report"] is not None:
                    state = checked(state, preference, company, now)
                    if action == "approve_report" and state["report"] is not None:
                        state = {**state, "outcome": "approved"}
                    message, reveal = state["outcome"], action == "inspect_report"
                elif action == "approve_report":
                    message = "no_report"
                elif (current := context(preference, company)) is None:
                    message = "collection_not_permitted"
                elif not policy.transport_available():
                    message = "transport_unavailable"
                elif not _budget_ready(connection, now):
                    message = "delivery_not_ready"
                else:
                    aggregate._prune(connection, now // DAY_MS, company["metric_groups"])
                    rows = connection.execute(
                        "SELECT cell, count, window_day FROM pending LIMIT 513"
                    ).fetchall()
                    if not rows:
                        message = "no_observations"
                    else:
                        clock = read_review_clock(initialize=True)
                        lifetime = start_review_lifetime(
                            now, clock, (min(row[2] for row in rows) + 2) * DAY_MS
                        )
                        packet = wire.prepare(
                            [(row[0], row[1]) for row in rows],
                            groups=company["metric_groups"],
                            reviewed=True,
                        )
                        state = {
                            "version": 1,
                            "mode": "review",
                            "token": secrets.token_hex(16),
                            "outcome": "held",
                            "report": {**current, "packet": list(packet), "lifetime": lifetime},
                        }
                        # Consume only the staged snapshot. Producer allowances
                        # remain; later observations enter a fresh pending batch.
                        connection.execute("DELETE FROM pending")
                        message, reveal = "held", True
            review_storage.write(connection, state)
            if cancel:
                connection.execute(
                    "UPDATE delivery_state SET lease_token=NULL, lease_deadline_ms=0 WHERE singleton=1"
                )
            connection.commit()
        return _result(root, state, message, reveal=reveal, policy_path=policy_path)
    except sqlite3.OperationalError as error:
        if getattr(error, "sqlite_errorcode", None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            raise policy.PolicyError("telemetry_busy") from None
        raise policy.PolicyError("telemetry_review_unavailable") from None
    except policy.PolicyError:
        raise
    except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
        raise policy.PolicyError("telemetry_review_unavailable") from None
