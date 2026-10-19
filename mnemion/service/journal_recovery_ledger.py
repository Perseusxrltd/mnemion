"""Preserve later journal holds without treating a ledger as a content backup."""

import re
from datetime import datetime
from uuid import UUID


def capture(conn):
    if not conn.execute(
        "SELECT to_regclass('mnemion.journal_recovery_origins') AS relation"
    ).fetchone()["relation"]:
        return None
    return {
        "version": 1,
        "quarantines": conn.execute("""SELECT
            o.tenant_id,o.space_id,o.origin,o.memory_id,o.source_version,
            o.source_digest,o.source_action,
            (o.locally_modified OR (m.id IS NOT NULL AND
              (m.version IS DISTINCT FROM o.local_version OR m.review_state <>
                CASE WHEN o.source_action='quarantine' THEN 'quarantined' ELSE 'ordinary' END)))
              AS locally_modified,
            greatest(o.updated_at,m.updated_at) AS updated_at
            FROM mnemion.journal_recovery_origins o LEFT JOIN mnemion.memories m
              ON m.tenant_id=o.tenant_id AND m.space_id=o.space_id AND m.id=o.memory_id
            WHERE o.source_action='quarantine' OR
              (m.review_state='quarantined' AND m.deleted_at IS NULL)
            ORDER BY o.tenant_id,o.space_id,o.origin""").fetchall(),
    }


def validate(value, tenants):
    try:
        if (
            not isinstance(value, dict)
            or set(value) != {"version", "quarantines"}
            or type(value["version"]) is not int
            or value["version"] != 1
            or not isinstance(value["quarantines"], list)
            or len(value["quarantines"]) > 1_000_000
        ):
            raise ValueError
        origins, identities = set(), set()
        for row in value["quarantines"]:
            if not isinstance(row, dict) or set(row) != {
                "tenant_id",
                "space_id",
                "origin",
                "memory_id",
                "source_version",
                "source_digest",
                "source_action",
                "locally_modified",
                "updated_at",
            }:
                raise ValueError
            for field in ("tenant_id", "space_id", "memory_id"):
                if str(UUID(row[field])) != row[field]:
                    raise ValueError
            origin = row["origin"].split(":")
            if len(origin) != 3 or any(str(UUID(part)) != part for part in origin):
                raise ValueError
            identity = (row["tenant_id"], row["memory_id"])
            scoped_origin = (row["tenant_id"], row["space_id"], row["origin"])
            if (
                row["tenant_id"] not in tenants
                or identity in identities
                or scoped_origin in origins
                or type(row["source_version"]) is not int
                or not 1 <= row["source_version"] <= 9007199254740991
                or not isinstance(row["source_digest"], str)
                or not re.fullmatch(r"[a-f0-9]{64}", row["source_digest"])
                or row["source_action"] not in {"upsert", "quarantine"}
                or type(row["locally_modified"]) is not bool
                or (row["source_action"] == "upsert" and not row["locally_modified"])
                or datetime.fromisoformat(row["updated_at"]).tzinfo is None
            ):
                raise ValueError
            identities.add(identity)
            origins.add(scoped_origin)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Invalid journal quarantine recovery ledger") from None


def restore(conn, ledger):
    value = ledger.get("journal_recovery_state")
    if value is None:
        if conn.execute("SELECT 1 FROM mnemion.journal_recovery_origins LIMIT 1").fetchone():
            raise ValueError("Journal recovery identities require a current journal-aware ledger")
        return
    tenants = {str(row["id"]) for row in conn.execute("SELECT id FROM mnemion.tenants")}
    for item in value["quarantines"]:
        if item["tenant_id"] not in tenants:
            continue
        tenant, space, memory = item["tenant_id"], item["space_id"], item["memory_id"]
        mapping = conn.execute(
            """SELECT * FROM mnemion.journal_recovery_origins
            WHERE tenant_id=%s AND space_id=%s AND origin=%s""",
            (tenant, space, item["origin"]),
        ).fetchone()
        row = conn.execute(
            "SELECT id,space_id,version,review_state,deleted_at FROM mnemion.memories WHERE tenant_id=%s AND id=%s",
            (tenant, memory),
        ).fetchone()
        collision = conn.execute(
            """SELECT 1 FROM mnemion.journal_recovery_origins WHERE tenant_id=%s
              AND memory_id=%s AND (space_id<>%s OR origin<>%s)""",
            (tenant, memory, space, item["origin"]),
        ).fetchone()
        if (
            collision
            or (row and (str(row["space_id"]) != space or not mapping))
            or (
                mapping
                and (
                    str(mapping["memory_id"]) != memory
                    or mapping["source_version"] > item["source_version"]
                    or (
                        mapping["source_version"] == item["source_version"]
                        and (
                            mapping["source_digest"] != item["source_digest"]
                            or mapping["source_action"] != item["source_action"]
                        )
                    )
                )
            )
        ):
            raise ValueError("Journal quarantine ledger conflicts with restored identities")
        modified = item["locally_modified"] or bool(
            mapping
            and (
                mapping["locally_modified"]
                or (
                    row
                    and (
                        row["version"] != mapping["local_version"]
                        or row["review_state"]
                        != (
                            "quarantined"
                            if mapping["source_action"] == "quarantine"
                            else "ordinary"
                        )
                    )
                )
            )
        )
        local_version = row["version"] if row else None
        if row and row["deleted_at"] is None:
            from .librarian import purge_librarian_dependencies

            purge_librarian_dependencies(conn, tenant, space, memory)
            if row["review_state"] != "quarantined":
                local_version += 1
                conn.execute(
                    """UPDATE mnemion.memories SET review_state='quarantined',version=%s,
                    updated_at=now() WHERE tenant_id=%s AND id=%s""",
                    (local_version, tenant, memory),
                )
        # No positive content, grants, source chunks or missing spaces are created.
        conn.execute(
            """INSERT INTO mnemion.journal_recovery_origins
            (tenant_id,space_id,origin,memory_id,source_version,source_digest,
             source_action,local_version,locally_modified,updated_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(tenant_id,space_id,origin) DO UPDATE SET
              source_version=excluded.source_version,source_digest=excluded.source_digest,
              source_action=excluded.source_action,local_version=excluded.local_version,
              locally_modified=excluded.locally_modified,updated_at=excluded.updated_at""",
            (
                tenant,
                space,
                item["origin"],
                memory,
                item["source_version"],
                item["source_digest"],
                item["source_action"],
                local_version,
                modified,
                item["updated_at"],
            ),
        )
