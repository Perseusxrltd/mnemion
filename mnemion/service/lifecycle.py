"""Content erasure shared by the worker and isolated disaster recovery."""

from uuid import UUID


def purge_memory(conn, tenant: UUID, space: UUID, memory: UUID) -> None:
    """Caller holds the deleted memory's row lock and an authorized transaction."""
    from .evaluations import purge_evaluation_dependencies
    from .librarian import purge_librarian_dependencies

    purge_evaluation_dependencies(conn, tenant, space, memory)
    purge_librarian_dependencies(conn, tenant, space, memory)
    scope = (tenant, space, memory)
    conn.execute(
        "DELETE FROM mnemion.connector_proposals WHERE tenant_id=%s AND space_id=%s AND memory_id=%s",
        scope,
    )
    conn.execute(
        "DELETE FROM mnemion.memory_change_notes WHERE tenant_id=%s AND space_id=%s AND memory_id=%s",
        scope,
    )
    sources = conn.execute(
        """SELECT DISTINCT sr.source_id FROM mnemion.source_revisions sr
           JOIN mnemion.memory_revisions r ON r.tenant_id=sr.tenant_id
             AND r.space_id=sr.space_id AND r.source_revision_id=sr.id
           WHERE r.tenant_id=%s AND r.space_id=%s AND r.memory_id=%s""",
        scope,
    ).fetchall()
    conn.execute(
        """DELETE FROM mnemion.embeddings WHERE (tenant_id, space_id, revision_id) IN
           (SELECT tenant_id, space_id, id FROM mnemion.memory_revisions
            WHERE tenant_id=%s AND space_id=%s AND memory_id=%s)""",
        scope,
    )
    conn.execute(
        """UPDATE mnemion.jobs SET revision_id=NULL WHERE (tenant_id, space_id, revision_id) IN
           (SELECT tenant_id, space_id, id FROM mnemion.memory_revisions
            WHERE tenant_id=%s AND space_id=%s AND memory_id=%s)""",
        scope,
    )
    conn.execute(
        """UPDATE mnemion.memories SET current_revision_id=NULL, subject=NULL
           WHERE tenant_id=%s AND space_id=%s AND id=%s""",
        scope,
    )
    conn.execute(
        "DELETE FROM mnemion.memory_revisions WHERE tenant_id=%s AND space_id=%s AND memory_id=%s",
        scope,
    )
    for source in sources:
        conn.execute(
            """DELETE FROM mnemion.source_revisions sr WHERE tenant_id=%s AND space_id=%s
                 AND source_id=%s AND NOT EXISTS
               (SELECT FROM mnemion.memory_revisions r WHERE r.tenant_id=sr.tenant_id
                AND r.space_id=sr.space_id AND r.source_revision_id=sr.id)""",
            (tenant, space, source["source_id"]),
        )
        conn.execute(
            """DELETE FROM mnemion.sources s WHERE tenant_id=%s AND space_id=%s AND id=%s
               AND NOT EXISTS (SELECT FROM mnemion.source_revisions sr
                WHERE sr.tenant_id=s.tenant_id AND sr.space_id=s.space_id AND sr.source_id=s.id)""",
            (tenant, space, source["source_id"]),
        )
    conn.execute(
        """UPDATE mnemion.deletion_receipts SET purged_at=coalesce(purged_at, now())
           WHERE tenant_id=%s AND space_id=%s AND memory_id=%s""",
        scope,
    )
