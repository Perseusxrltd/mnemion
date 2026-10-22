"""Custody policy, device revocations and negative lineage recovery state."""

import re
from datetime import datetime
from uuid import UUID

from psycopg.types.json import Jsonb

from ..capture_policy import CapturePolicy
from . import capture_policy_recovery, capture_retention_recovery


def capture(conn):
    return {
        "version": 3,
        "sources": conn.execute(
            "SELECT * FROM mnemion.capture_sources ORDER BY tenant_id,source_id"
        ).fetchall(),
        "grants": conn.execute(
            "SELECT * FROM mnemion.capture_grants ORDER BY tenant_id,grant_id"
        ).fetchall(),
        "denials": conn.execute(
            "SELECT * FROM mnemion.capture_denials ORDER BY tenant_id,source_id,lineage_id"
        ).fetchall(),
        "policies": conn.execute(
            "SELECT * FROM mnemion.capture_policy_versions ORDER BY tenant_id,source_id,policy_version"
        ).fetchall(),
        "expiries": capture_retention_recovery.capture(conn),
    }


def validate(state, tenants):
    if (
        not isinstance(state, dict)
        or state.get("version") not in {1, 2, 3}
        or set(state)
        != {"version", "sources", "grants", "denials"}
        | ({"policies"} if state.get("version") in {2, 3} else set())
        | ({"expiries"} if state.get("version") == 3 else set())
    ):
        raise ValueError("Invalid capture custody recovery ledger")
    known_sources, known_grants, known_spaces, known_denials = set(), set(), set(), set()
    for name, identifiers in (
        ("sources", ("source_id", "connector_id", "space_id")),
        ("grants", ("source_id", "grant_id", "device_key_id")),
        ("denials", ("source_id",)),
    ):
        if not isinstance(state[name], list):
            raise ValueError("Invalid capture custody recovery rows")
        for row in state[name]:
            if not isinstance(row, dict) or str(UUID(row["tenant_id"])) not in tenants:
                raise ValueError("Invalid capture custody tenant")
            for field in identifiers:
                UUID(row[field])
            identity = (row["tenant_id"], row["source_id"])
            if name == "sources":
                if type(row.get("version")) is not int or row["version"] < 1:
                    raise ValueError("Invalid capture custody source version")
                space = (row["tenant_id"], row["space_id"])
                if identity in known_sources or space in known_spaces:
                    raise ValueError("Duplicate capture custody source or space")
                known_sources.add(identity)
                known_spaces.add(space)
            elif identity not in known_sources:
                raise ValueError("Unknown capture custody source")
            if name == "grants":
                grant = (row["tenant_id"], row["grant_id"])
                if grant in known_grants:
                    raise ValueError("Duplicate capture custody grant")
                known_grants.add(grant)
            for field in ("forgotten_at",) if name == "denials" else ("created_at", "revoked_at"):
                value = row[field]
                if value is None and field == "revoked_at":
                    continue
                if not isinstance(value, str) or datetime.fromisoformat(value).tzinfo is None:
                    raise ValueError("Invalid capture custody timestamp")
            if name == "sources":
                if (
                    row.get("capture_mode") not in {"messages", "complete"}
                    or not isinstance(row.get("namespace"), str)
                    or not 1 <= len(row["namespace"]) <= 400
                ):
                    raise ValueError("Invalid capture custody selection")
                policy = row.get("capture_policy")
                if policy is not None:
                    approved = CapturePolicy.model_validate(policy)
                    if (
                        approved.capture_mode != row["capture_mode"]
                        or not approved.keeps_accepted
                        or approved.model_dump(mode="json") != policy
                    ):
                        raise ValueError("Invalid capture custody policy")
                if not isinstance(row.get("name"), str) or not 1 <= len(row["name"]) <= 200:
                    raise ValueError("Invalid capture custody name")
                if (
                    not isinstance(row.get("members"), list)
                    or len(row["members"]) > 128
                    or any(
                        not isinstance(member, str)
                        or not 1 <= len(member) <= 512
                        or any(ord(c) < 32 for c in member)
                        for member in row["members"]
                    )
                ):
                    raise ValueError("Invalid capture custody members")
                if len(set(row["members"])) != len(row["members"]):
                    raise ValueError("Duplicate capture custody members")
            if name == "denials":
                if not isinstance(row.get("lineage_id"), str) or not re.fullmatch(
                    r"[a-f0-9]{64}", row["lineage_id"]
                ):
                    raise ValueError("Invalid capture custody denial")
                denial = (*identity, row["lineage_id"])
                if denial in known_denials:
                    raise ValueError("Duplicate capture custody denial")
                known_denials.add(denial)
    capture_policy_recovery.validate(state)
    capture_retention_recovery.validate(state)


def restore(conn, state):
    if state is None:
        if conn.execute("SELECT 1 FROM mnemion.capture_sources LIMIT 1").fetchone():
            raise ValueError(
                "Obtain a current custody-aware recovery ledger before restoring capture sources"
            )
        return
    capture_policy_recovery.validate(state)
    capture_retention_recovery.validate(state)
    # A device absent from the current ledger cannot regain an older grant.
    conn.execute("UPDATE mnemion.capture_grants SET revoked_at=coalesce(revoked_at,now())")
    conn.execute("UPDATE mnemion.capture_sources SET revoked_at=coalesce(revoked_at,now())")
    for row in state["sources"]:
        if not conn.execute(
            "SELECT 1 FROM mnemion.connectors WHERE tenant_id=%s AND id=%s",
            (row["tenant_id"], row["connector_id"]),
        ).fetchone():
            continue
        previous = conn.execute(
            "SELECT * FROM mnemion.capture_sources WHERE tenant_id=%s AND source_id=%s",
            (row["tenant_id"], row["source_id"]),
        ).fetchone()
        if previous and (
            any(
                str(previous[field]) != str(row[field])
                for field in ("connector_id", "space_id", "namespace")
            )
            or previous["policy_version"] > row.get("policy_version", 1)
        ):
            raise ValueError("The custody ledger changed an immutable source binding")
        if (
            not previous
            and conn.execute(
                "SELECT 1 FROM mnemion.spaces WHERE tenant_id=%s AND id=%s",
                (row["tenant_id"], row["space_id"]),
            ).fetchone()
        ):
            raise ValueError("The custody ledger space belongs to a different source")
        conn.execute(
            "INSERT INTO mnemion.spaces(tenant_id,id,name,description) VALUES(%s,%s,%s,'Recovered consented capture custody') ON CONFLICT DO NOTHING",
            (row["tenant_id"], row["space_id"], row["name"]),
        )
        conn.execute(
            """INSERT INTO mnemion.capture_sources(tenant_id,source_id,connector_id,space_id,namespace,name,members,capture_mode,revoked_at,version,capture_policy,policy_version)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,source_id) DO UPDATE
               SET members=excluded.members,name=excluded.name,revoked_at=excluded.revoked_at,version=excluded.version,
                   capture_mode=excluded.capture_mode,capture_policy=excluded.capture_policy,policy_version=excluded.policy_version""",
            tuple(
                row[key]
                for key in (
                    "tenant_id",
                    "source_id",
                    "connector_id",
                    "space_id",
                    "namespace",
                    "name",
                    "members",
                    "capture_mode",
                    "revoked_at",
                    "version",
                )
            )
            + (
                Jsonb(row["capture_policy"]) if row.get("capture_policy") is not None else None,
                row.get("policy_version", 1),
            ),
        )
    capture_policy_recovery.restore(conn, state)
    capture_retention_recovery.restore(conn, state)
    for row in state["grants"]:
        previous = conn.execute(
            "SELECT * FROM mnemion.capture_grants WHERE tenant_id=%s AND grant_id=%s",
            (row["tenant_id"], row["grant_id"]),
        ).fetchone()
        if previous and (
            any(str(previous[field]) != str(row[field]) for field in ("source_id", "device_key_id"))
            or previous["policy_version"] != row.get("policy_version", 1)
        ):
            raise ValueError("The custody ledger changed an immutable device binding")
        conn.execute(
            """INSERT INTO mnemion.capture_grants(tenant_id,grant_id,source_id,device_key_id,revoked_at,policy_version)
               SELECT %s,%s,%s,%s,%s,%s WHERE EXISTS(SELECT FROM mnemion.capture_sources WHERE tenant_id=%s AND source_id=%s)
                 AND EXISTS(SELECT FROM mnemion.api_keys WHERE tenant_id=%s AND id=%s)
               ON CONFLICT(tenant_id,grant_id) DO UPDATE SET revoked_at=excluded.revoked_at""",
            (
                row["tenant_id"],
                row["grant_id"],
                row["source_id"],
                row["device_key_id"],
                row["revoked_at"],
                row.get("policy_version", 1),
                row["tenant_id"],
                row["source_id"],
                row["tenant_id"],
                row["device_key_id"],
            ),
        )
    for row in state["denials"]:
        conn.execute(
            """INSERT INTO mnemion.capture_denials(tenant_id,source_id,lineage_id,forgotten_at)
               SELECT %s,%s,%s,%s WHERE EXISTS(SELECT FROM mnemion.capture_sources WHERE tenant_id=%s AND source_id=%s)
               ON CONFLICT DO NOTHING""",
            (
                row["tenant_id"],
                row["source_id"],
                row["lineage_id"],
                row["forgotten_at"],
                row["tenant_id"],
                row["source_id"],
            ),
        )
