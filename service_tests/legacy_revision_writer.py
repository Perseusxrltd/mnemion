"""Frozen pre-021 revision writer from the 4.13.0 source.

Only the legacy-schema fixture uses this writer. The candidate must continue
to reject incomplete migrations; current writes always capture chronology.
"""

from __future__ import annotations

from uuid import UUID, uuid4
from psycopg.types.json import Jsonb
from mnemion.service.db import Identity
from mnemion.service.models import MemoryInput
from mnemion.service.errors import not_found
from mnemion.service.memory import _hash


def previous_revision(
    self,
    conn,
    identity: Identity,
    space: UUID,
    memory: UUID,
    version: int,
    command: MemoryInput,
    *,
    evidence_from: UUID | None = None,
) -> UUID:
    source_id, source_revision, revision = uuid4(), uuid4(), uuid4()
    if evidence_from is not None:
        # Reviewed organization changes keep the exact original source and
        # attachments. They cannot manufacture replacement evidence.
        inserted = conn.execute(
            """INSERT INTO mnemion.memory_revisions
                (tenant_id,space_id,id,memory_id,version,content,content_hash,metadata,subject,kind,
                 source_revision_id,source_start,source_end,claim_status,valid_from,valid_to,created_by)
                SELECT tenant_id,space_id,%s,memory_id,%s,content,content_hash,%s,%s,kind,
                       source_revision_id,source_start,source_end,claim_status,valid_from,valid_to,%s
                FROM mnemion.memory_revisions WHERE tenant_id=%s AND space_id=%s AND memory_id=%s AND id=%s
                RETURNING id""",
            (
                revision,
                version,
                Jsonb(command.metadata),
                command.subject,
                identity.principal_id,
                identity.tenant_id,
                space,
                memory,
                evidence_from,
            ),
        ).fetchone()
        if not inserted:
            raise not_found()
        return revision
    source = command.source
    source_content = source.content if source and source.content is not None else command.content
    start = source.start if source else 0
    end = source.end if source and source.end is not None else len(source_content)
    conn.execute(
        """INSERT INTO mnemion.sources(tenant_id, space_id, id, title, uri, created_by)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (
            identity.tenant_id,
            space,
            source_id,
            source.title if source else "Captured evidence",
            source.uri if source else None,
            identity.principal_id,
        ),
    )
    conn.execute(
        """INSERT INTO mnemion.source_revisions
             (tenant_id, space_id, id, source_id, content, content_hash, media_type)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (
            identity.tenant_id,
            space,
            source_revision,
            source_id,
            source_content,
            _hash(source_content),
            source.media_type if source else "text/plain",
        ),
    )
    conn.execute(
        """INSERT INTO mnemion.memory_revisions
             (tenant_id, space_id, id, memory_id, version, content, content_hash, metadata, subject, kind,
              source_revision_id, source_start, source_end, claim_status, valid_from, valid_to, created_by)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            identity.tenant_id,
            space,
            revision,
            memory,
            version,
            command.content,
            _hash(command.content),
            Jsonb(command.metadata),
            command.subject,
            command.kind,
            source_revision,
            start,
            end,
            command.claim_status,
            command.valid_from,
            command.valid_to,
            identity.principal_id,
        ),
    )
    return revision
