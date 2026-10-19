"""Shared authority boundary for reviewed copies of external memory content."""

from .db import require_administrator, require_space
from .errors import ServiceError
from .fences import exclusive_boundary


def authorize(conn, identity, space, *, code):
    require_administrator(conn)
    require_space(conn, space, 40)
    exclusive_boundary(conn, identity.tenant_id, space)
    require_space(conn, space, 40, writing=True)
    if (
        conn.execute(
            "SELECT 1 FROM mnemion.space_grants WHERE space_id=%s AND principal_id<>%s",
            (space, identity.principal_id),
        ).fetchone()
        or conn.execute(
            "SELECT 1 FROM mnemion.connector_scopes WHERE space_id=%s", (space,)
        ).fetchone()
        or conn.execute(
            "SELECT 1 FROM mnemion.writeback_settings WHERE space_id=%s", (space,)
        ).fetchone()
    ):
        raise ServiceError(
            409,
            code,
            "Choose a private native space with only your administrator grant and no Git publication. Share or publish it separately after reconciliation.",
        )
