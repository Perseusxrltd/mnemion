"""Transaction-scoped writer boundaries for migration, cutover, and rollback."""

from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from .db import Database
from .errors import ServiceError
from .models import json_value


def shared_boundary(conn, tenant: UUID, space: UUID) -> None:
    conn.execute(
        "SELECT pg_advisory_xact_lock_shared(hashtextextended(%s, 0))",
        (f"mnemion-write:{tenant}:{space}",),
    )


def write_boundary(conn, tenant: UUID, space: UUID) -> None:
    shared_boundary(conn, tenant, space)
    if conn.execute(
        "SELECT 1 FROM mnemion.space_fences WHERE tenant_id=%s AND space_id=%s",
        (tenant, space),
    ).fetchone():
        raise ServiceError(409, "space_paused", "This space is paused for migration or recovery.")


def exclusive_boundary(conn, tenant: UUID, space: UUID) -> None:
    conn.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"mnemion-write:{tenant}:{space}",),
    )


def pause_space(dsn: str, tenant: UUID, space: UUID, *, reason: str) -> dict:
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        Database._scope(conn, tenant, None)
        exclusive_boundary(conn, tenant, space)
        conn.execute(
            """INSERT INTO mnemion.space_fences(tenant_id,space_id,token,reason)
               VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (tenant, space, uuid4(), reason),
        )
        row = conn.execute(
            "SELECT space_id,token,reason,created_at FROM mnemion.space_fences WHERE tenant_id=%s AND space_id=%s",
            (tenant, space),
        ).fetchone()
        return json_value(row)


def resume_space(dsn: str, tenant: UUID, space: UUID, token: UUID) -> dict:
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        exclusive_boundary(conn, tenant, space)
        row = conn.execute(
            "SELECT state FROM mnemion.legacy_profiles WHERE tenant_id=%s AND space_id=%s",
            (tenant, space),
        ).fetchone()
        if row and row["state"] == "importing":
            raise ValueError("Complete the final legacy import before opening this space")
        changed = conn.execute(
            "DELETE FROM mnemion.space_fences WHERE tenant_id=%s AND space_id=%s AND token=%s RETURNING space_id",
            (tenant, space, token),
        ).fetchone()
        if not changed:
            raise ValueError("The pause token does not match this space")
        return {"space_id": str(space), "paused": False}
