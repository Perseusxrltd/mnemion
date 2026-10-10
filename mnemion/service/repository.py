"""Common policy-aware database operations used by every public transport."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from .db import Identity, require_space
from .errors import ServiceError, not_found
from .models import json_value


def audit(
    conn: psycopg.Connection,
    identity: Identity,
    action: str,
    resource_id: UUID | str,
    *,
    space_id: UUID | None = None,
    details: dict | None = None,
) -> None:
    event = uuid4()
    details = dict(details or {})
    reason = (
        details.pop("reason", None) if action in {"memory.revised", "memory.reviewed"} else None
    )
    conn.execute(
        """INSERT INTO mnemion.audit_events
             (tenant_id, space_id, id, principal_id, action, resource_id, details)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (
            identity.tenant_id,
            space_id,
            event,
            identity.principal_id,
            action,
            str(resource_id),
            Jsonb(json_value(details)),
        ),
    )
    if reason is not None:
        conn.execute(
            """INSERT INTO mnemion.memory_change_notes(tenant_id,space_id,memory_id,event_id,reason)
               VALUES(%s,%s,%s,%s,%s)""",
            (identity.tenant_id, space_id, resource_id, event, reason),
        )


def idempotency(
    conn: psycopg.Connection, identity: Identity, space: UUID, key: str, payload: dict
) -> tuple[str, dict | None]:
    if not key or len(key) > 200 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ServiceError(
            422, "idempotency_key_required", "Use a 1–200 character Idempotency-Key."
        )
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()
    lock_key = f"{identity.tenant_id}:{space}:{identity.principal_id}:{key}"
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
    previous = conn.execute(
        """SELECT request_hash, response FROM mnemion.idempotency_keys
           WHERE tenant_id=%s AND space_id=%s AND principal_id=%s AND key=%s""",
        (identity.tenant_id, space, identity.principal_id, key),
    ).fetchone()
    if previous and previous["request_hash"] != digest:
        raise ServiceError(
            409, "idempotency_conflict", "This key was used with a different request."
        )
    return digest, previous["response"] if previous else None


def remember_receipt(
    conn: psycopg.Connection, identity: Identity, space: UUID, key: str, digest: str, response: dict
) -> dict:
    response = json_value(response)
    conn.execute(
        """INSERT INTO mnemion.idempotency_keys
             (tenant_id, space_id, principal_id, key, request_hash, response)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (identity.tenant_id, space, identity.principal_id, key, digest, Jsonb(response)),
    )
    return response


def memory_row(
    conn: psycopg.Connection,
    memory_id: UUID,
    *,
    review: bool = False,
    deleted: bool = False,
    lock: bool = False,
) -> dict:
    query = "SELECT * FROM mnemion.memories WHERE id=%s"
    if not deleted:
        query += " AND deleted_at IS NULL"
    if lock:
        query += " FOR UPDATE"
    row = conn.execute(query, (memory_id,)).fetchone()
    if not row:
        raise not_found()
    require_space(conn, row["space_id"], 30 if review else 10)
    if row["review_state"] != "ordinary" and not review:
        raise not_found()
    return row


def hydrate(conn: psycopg.Connection, row: dict, revision_id: UUID | None = None) -> dict:
    revision = conn.execute(
        """SELECT r.*, s.id AS source_id, s.title AS source_title, s.uri AS source_uri,
                  sr.content_hash AS source_hash, sr.media_type,
                  substring(sr.content FROM r.source_start+1 FOR r.source_end-r.source_start)
                      AS source_excerpt
           FROM mnemion.memory_revisions r
           JOIN mnemion.source_revisions sr
             ON sr.tenant_id=r.tenant_id AND sr.space_id=r.space_id AND sr.id=r.source_revision_id
           JOIN mnemion.sources s
             ON s.tenant_id=sr.tenant_id AND s.space_id=sr.space_id AND s.id=sr.source_id
           WHERE r.tenant_id=%s AND r.space_id=%s AND r.memory_id=%s AND r.id=%s
             AND s.deleted_at IS NULL""",
        (row["tenant_id"], row["space_id"], row["id"], revision_id or row["current_revision_id"]),
    ).fetchone()
    if not revision:
        raise not_found()
    return json_value(
        {
            "memory_id": row["id"],
            "space_id": row["space_id"],
            "subject": revision["subject"],
            "kind": revision["kind"],
            "version": row["version"],
            "revision_id": revision["id"],
            "revision_version": revision["version"],
            "content": revision["content"],
            "content_hash": revision["content_hash"],
            "metadata": revision["metadata"],
            "claim_status": revision["claim_status"],
            "review_state": row["review_state"],
            "valid_from": revision["valid_from"],
            "valid_to": revision["valid_to"],
            "recorded_at": revision["recorded_at"],
            "created_by": revision["created_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "evidence": {
                "source_id": revision["source_id"],
                "source_revision_id": revision["source_revision_id"],
                "title": revision["source_title"],
                "uri": revision["source_uri"],
                "media_type": revision["media_type"],
                "content_hash": revision["source_hash"],
                "start": revision["source_start"],
                "end": revision["source_end"],
                "offset_unit": "unicode_codepoints",
                "excerpt": revision["source_excerpt"],
            },
        }
    )
