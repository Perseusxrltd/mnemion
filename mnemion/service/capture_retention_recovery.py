"""Preserve approved family deadlines and apply them before publishing a restore."""

from datetime import UTC, datetime, timedelta
import re
from uuid import UUID


def capture(conn):
    return conn.execute(
        """SELECT tenant_id,source_id,lineage_id,policy_version,first_accepted_at,expires_at
           FROM mnemion.capture_expiries ORDER BY tenant_id,source_id,lineage_id"""
    ).fetchall()


def validate(state):
    from .capture_policy_recovery import versions

    policies = {
        (row["tenant_id"], row["source_id"], row["policy_version"]): row for row in versions(state)
    }
    if state["version"] < 3:
        if any(
            (row.get("capture_policy") or {}).get("retention") == "expire_after"
            for row in policies.values()
        ):
            raise ValueError("An expiry-aware custody ledger is required")
        return
    if not isinstance(state["expiries"], list):
        raise ValueError("Invalid capture expiry recovery rows")
    known = set()
    for row in state["expiries"]:
        if not isinstance(row, dict) or set(row) != {
            "tenant_id",
            "source_id",
            "lineage_id",
            "policy_version",
            "first_accepted_at",
            "expires_at",
        }:
            raise ValueError("Invalid capture expiry recovery row")
        identity = (row["tenant_id"], row["source_id"], row["lineage_id"])
        if (
            identity in known
            or type(row["policy_version"]) is not int
            or not isinstance(row["lineage_id"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", row["lineage_id"])
        ):
            raise ValueError("Invalid capture expiry recovery identity")
        known.add(identity)
        version = policies.get((row["tenant_id"], row["source_id"], row["policy_version"]))
        policy = (version or {}).get("capture_policy") or {}
        if (
            not version
            or not version.get("approved_by")
            or policy.get("retention") != "expire_after"
            or policy.get("expiry_scope") != "captured_fragment_family"
        ):
            raise ValueError("Capture expiry requires its approved policy")
        stamps = []
        for name in ("first_accepted_at", "expires_at"):
            value = row[name]
            if not isinstance(value, str):
                raise ValueError("Invalid capture expiry recovery timestamp")
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                raise ValueError("Invalid capture expiry recovery timestamp")
            stamps.append(parsed.astimezone(UTC))
        if stamps[1] - stamps[0] != timedelta(days=policy["retention_days"]):
            raise ValueError("Capture expiry does not match its approved lifetime")


def restore(conn, state):
    rows = state.get("expiries", [])
    known = {(UUID(row["tenant_id"]), UUID(row["source_id"]), row["lineage_id"]) for row in rows}
    for previous in capture(conn):
        if (previous["tenant_id"], previous["source_id"], previous["lineage_id"]) not in known:
            raise ValueError("Obtain a current complete expiry-aware custody ledger")
    for row in rows:
        conn.execute(
            """INSERT INTO mnemion.capture_expiries
                 (tenant_id,source_id,lineage_id,policy_version,first_accepted_at,expires_at)
               SELECT %s,%s,%s,%s,%s,%s WHERE EXISTS(
                 SELECT FROM mnemion.capture_policy_versions WHERE tenant_id=%s AND source_id=%s AND policy_version=%s)
               ON CONFLICT(tenant_id,source_id,lineage_id) DO UPDATE
                 SET policy_version=excluded.policy_version,first_accepted_at=excluded.first_accepted_at,
                     expires_at=excluded.expires_at
                 WHERE capture_expiries.state<>'expired' AND excluded.expires_at<capture_expiries.expires_at""",
            tuple(
                row[key]
                for key in (
                    "tenant_id",
                    "source_id",
                    "lineage_id",
                    "policy_version",
                    "first_accepted_at",
                    "expires_at",
                )
            )
            + (row["tenant_id"], row["source_id"], row["policy_version"]),
        )
    # Snapshot-side expiring events may never lose their deadline, even if the
    # supplied ledger was edited or predates the backup.
    if conn.execute(
        """SELECT 1 FROM mnemion.capture_events e JOIN mnemion.capture_policy_versions p
             ON p.tenant_id=e.tenant_id AND p.source_id=e.source_id AND p.policy_version=e.policy_version
           WHERE e.memory_id IS NOT NULL AND p.capture_policy->>'retention'='expire_after'
             AND NOT EXISTS(SELECT FROM mnemion.capture_expiries x WHERE x.tenant_id=e.tenant_id
               AND x.source_id=e.source_id AND x.lineage_id=e.lineage_id) LIMIT 1"""
    ).fetchone():
        raise ValueError("The capture expiry recovery ledger is incomplete")
    # A lease belongs to the old process. Preserve its deadline, not its lock.
    if rows:
        conn.execute(
            """UPDATE mnemion.capture_expiries SET state='pending',lease_id=NULL,lease_until=NULL,
               available_at=now(),attempts=0,error_code=NULL WHERE state='leased'"""
        )


def reconcile(conn, apply_deletions):
    """No restored due/denied family becomes readable while awaiting a worker."""
    applied = 0
    while True:
        conn.execute(
            """INSERT INTO mnemion.capture_denials(tenant_id,source_id,lineage_id,forgotten_at)
               SELECT tenant_id,source_id,lineage_id,expires_at FROM mnemion.capture_expiries
               WHERE expires_at<=clock_timestamp() ON CONFLICT DO NOTHING"""
        )
        rows = conn.execute(
            """SELECT e.tenant_id,e.space_id,e.memory_id,d.forgotten_at AS requested_at
           FROM mnemion.capture_denials d JOIN mnemion.capture_events e USING(tenant_id,source_id,lineage_id)
           JOIN mnemion.memories m ON m.tenant_id=e.tenant_id AND m.space_id=e.space_id AND m.id=e.memory_id
           WHERE m.deleted_at IS NULL OR m.current_revision_id IS NOT NULL
           ORDER BY e.tenant_id,e.source_id,e.event_id LIMIT 256"""
        ).fetchall()
        if not rows:
            break
        from .models import json_value

        applied += apply_deletions(conn, {"deletions": json_value(rows)})
    conn.execute(
        """UPDATE mnemion.capture_expiries x SET state='expired',lease_id=NULL,lease_until=NULL,
           completed_at=coalesce(completed_at,clock_timestamp()),error_code=NULL,attempts=0
           WHERE expires_at<=clock_timestamp() AND state<>'expired'
             AND EXISTS(SELECT FROM mnemion.capture_denials d WHERE d.tenant_id=x.tenant_id
               AND d.source_id=x.source_id AND d.lineage_id=x.lineage_id)
             AND NOT EXISTS(SELECT FROM mnemion.capture_events e JOIN mnemion.memories m
               ON m.tenant_id=e.tenant_id AND m.space_id=e.space_id AND m.id=e.memory_id
               WHERE e.tenant_id=x.tenant_id AND e.source_id=x.source_id AND e.lineage_id=x.lineage_id
                 AND (m.deleted_at IS NULL OR m.current_revision_id IS NOT NULL))"""
    )
    return applied
