"""Canonical, atomic withdrawal of every retained view of a captured fragment."""

import hashlib

from ..capture_identity import canonical_capture_json


def preview(conn, memory):
    row = conn.execute(
        """SELECT e.source_id,e.lineage_id,count(m.id) AS retained_memories
           FROM mnemion.capture_events origin
             JOIN mnemion.capture_events e ON e.tenant_id=origin.tenant_id
               AND e.source_id=origin.source_id AND e.lineage_id=origin.lineage_id
             LEFT JOIN mnemion.memories m ON m.tenant_id=e.tenant_id
               AND m.space_id=e.space_id AND m.id=e.memory_id AND m.deleted_at IS NULL
           WHERE origin.memory_id=%s GROUP BY e.source_id,e.lineage_id""",
        (memory,),
    ).fetchone()
    if not row:
        return None
    return {
        "scope": "conversation_fragment",
        "lineage_id": row["lineage_id"],
        "retained_memories": row["retained_memories"],
        "includes_adjacent_messages": True,
        "includes_revisions_and_projections": True,
    }


def forget_siblings(service, conn, identity, memory):
    """Caller already authorized/locked the requested memory and its source.

    Each sibling uses ordinary deletion jobs, librarian invalidation, recovery
    denials and writeback. The surrounding transaction commits the entire family
    or rolls it back. Page through identities, never retaining source bodies.
    """
    description = preview(conn, memory)
    if description is None:
        return None
    last = None
    while True:
        siblings = conn.execute(
            """SELECT m.id,m.version FROM mnemion.capture_events origin
               JOIN mnemion.capture_events e ON e.tenant_id=origin.tenant_id
                 AND e.source_id=origin.source_id AND e.lineage_id=origin.lineage_id
               JOIN mnemion.memories m ON m.tenant_id=e.tenant_id
                 AND m.space_id=e.space_id AND m.id=e.memory_id
               WHERE origin.memory_id=%s AND m.id<>%s AND m.deleted_at IS NULL
                 AND (%s::uuid IS NULL OR m.id>%s)
               ORDER BY m.id LIMIT 32 FOR UPDATE OF m""",
            (memory, memory, last, last),
        ).fetchall()
        if not siblings:
            return description
        for row in siblings:
            key = (
                "capture-family-forget:"
                + hashlib.sha256(canonical_capture_json([str(memory), str(row["id"])])).hexdigest()
            )
            service.forget_in_transaction(
                conn,
                identity,
                row["id"],
                expected_version=row["version"],
                key=key,
                _capture_family=False,
            )
        last = siblings[-1]["id"]
