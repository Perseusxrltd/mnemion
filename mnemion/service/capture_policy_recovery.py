"""Immutable policy history in the current custody recovery ledger."""

from datetime import datetime
import re
from uuid import UUID

from psycopg.types.json import Jsonb

from ..capture_policy import CapturePolicy


def versions(state):
    if state["version"] == 2:
        return state["policies"]
    return [
        {
            **{
                key: source.get(key)
                for key in (
                    "tenant_id",
                    "source_id",
                    "capture_mode",
                    "capture_policy",
                    "created_at",
                )
            },
            "policy_version": 1,
            "transition_id": None,
            "request_hash": None,
            "previous_grants": None,
            "affected_grants": None,
        }
        for source in state["sources"]
    ]


def validate(state):
    policies = versions(state)
    if not isinstance(policies, list):
        raise ValueError("Invalid capture policy recovery history")
    sources = {(row["tenant_id"], row["source_id"]): row for row in state["sources"]}
    known, transitions, numbers = {}, set(), {}
    for row in policies:
        if not isinstance(row, dict):
            raise ValueError("Invalid capture policy recovery row")
        source = (row.get("tenant_id"), row.get("source_id"))
        version = row.get("policy_version")
        if source not in sources or type(version) is not int or version < 1:
            raise ValueError("Invalid capture policy recovery identity")
        identity = (*source, version)
        if identity in known:
            raise ValueError("Duplicate capture policy recovery version")
        known[identity] = row
        numbers.setdefault(source, []).append(version)
        if row.get("capture_mode") not in {"messages", "complete"}:
            raise ValueError("Invalid capture policy recovery selection")
        if row.get("capture_policy") is not None:
            policy = CapturePolicy.model_validate(row["capture_policy"])
            if (
                policy.capture_mode != row["capture_mode"]
                or policy.retention != "until_deleted"
                or policy.model_dump(mode="json") != row["capture_policy"]
            ):
                raise ValueError("Invalid capture policy recovery selection")
        created = row.get("created_at")
        if not isinstance(created, str) or datetime.fromisoformat(created).tzinfo is None:
            raise ValueError("Invalid capture policy recovery timestamp")
        if version == 1:
            if any(
                row.get(field) is not None
                for field in ("transition_id", "request_hash", "previous_grants", "affected_grants")
            ):
                raise ValueError("Initial capture policy cannot invent a transition")
        else:
            transition = (source[0], str(UUID(row["transition_id"])))
            if (
                transition in transitions
                or not isinstance(row.get("request_hash"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", row["request_hash"])
                or row.get("previous_grants") not in {"retain", "revoke"}
                or type(row.get("affected_grants")) is not int
                or row["affected_grants"] < 0
            ):
                raise ValueError("Invalid capture policy recovery transition")
            transitions.add(transition)
    for identity, source in sources.items():
        current = source.get("policy_version", 1)
        if (
            type(current) is not int
            or current < 1
            or current > source["version"]
            or (state["version"] == 2 and "policy_version" not in source)
            or (state["version"] == 1 and current != 1)
        ):
            raise ValueError("Invalid current capture policy version")
        ordered = sorted(numbers.get(identity, []))
        if (
            not ordered
            or len(ordered) != current
            or any(value != index for index, value in enumerate(ordered, 1))
        ):
            raise ValueError("The capture policy recovery history is incomplete")
        policy = known[(*identity, current)]
        if source["capture_mode"] != policy["capture_mode"] or source.get(
            "capture_policy"
        ) != policy.get("capture_policy"):
            raise ValueError("The custody ledger changed an immutable source binding")
    for grant in state["grants"]:
        version = grant.get("policy_version", 1)
        if (
            type(version) is not int
            or (state["version"] == 2 and "policy_version" not in grant)
            or (grant["tenant_id"], grant["source_id"], version) not in known
        ):
            raise ValueError("Unknown device capture policy recovery version")


def restore(conn, state):
    for row in versions(state):
        previous = conn.execute(
            "SELECT * FROM mnemion.capture_policy_versions WHERE tenant_id=%s AND source_id=%s AND policy_version=%s",
            (row["tenant_id"], row["source_id"], row["policy_version"]),
        ).fetchone()
        if previous and (
            any(
                previous[field] != row.get(field)
                for field in (
                    "capture_mode",
                    "capture_policy",
                    "request_hash",
                    "previous_grants",
                    "affected_grants",
                )
            )
            or str(previous["transition_id"]) != str(row.get("transition_id"))
        ):
            raise ValueError("The custody ledger changed an immutable capture policy version")
        conn.execute(
            """INSERT INTO mnemion.capture_policy_versions
                 (tenant_id,source_id,policy_version,capture_mode,capture_policy,created_at,
                  transition_id,request_hash,previous_grants,affected_grants)
               SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s
               WHERE EXISTS(SELECT FROM mnemion.capture_sources WHERE tenant_id=%s AND source_id=%s)
               ON CONFLICT(tenant_id,source_id,policy_version) DO NOTHING""",
            (
                row["tenant_id"],
                row["source_id"],
                row["policy_version"],
                row["capture_mode"],
                Jsonb(row["capture_policy"]) if row.get("capture_policy") is not None else None,
                row["created_at"],
                row.get("transition_id"),
                row.get("request_hash"),
                row.get("previous_grants"),
                row.get("affected_grants"),
                row["tenant_id"],
                row["source_id"],
            ),
        )
