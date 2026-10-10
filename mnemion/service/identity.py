"""Space and credential administration with no implicit content access."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from .db import Database, Identity, new_token, require_administrator, require_space
from .errors import ServiceError, not_found
from .models import GrantInput, KeyInput, PrincipalInput, SpaceInput, json_value
from .repository import audit


class IdentityService:
    def __init__(self, database: Database):
        self.db = database

    def me(self, identity: Identity) -> dict:
        with self.db.transaction(identity) as conn:
            row = conn.execute(
                """SELECT p.id AS principal_id, p.tenant_id, p.name, p.kind, p.administrator,
                          t.name AS tenant_name
                   FROM mnemion.principals p JOIN mnemion.tenants t ON t.id=p.tenant_id
                   WHERE p.id=%s""",
                (identity.principal_id,),
            ).fetchone()
            return json_value(row)

    def spaces(self, identity: Identity) -> list[dict]:
        with self.db.transaction(identity) as conn:
            return json_value(
                conn.execute(
                    """SELECT s.id, s.name, s.description, s.created_at, g.role
                       FROM mnemion.spaces s LEFT JOIN mnemion.space_grants g
                         ON g.tenant_id=s.tenant_id AND g.space_id=s.id AND g.principal_id=%s
                       ORDER BY s.created_at, s.id LIMIT 1000""",
                    (identity.principal_id,),
                ).fetchall()
            )

    def create_space(self, identity: Identity, command: SpaceInput) -> dict:
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            space = uuid4()
            row = conn.execute(
                """INSERT INTO mnemion.spaces(tenant_id, id, name, description)
                   VALUES (%s, %s, %s, %s) RETURNING id, name, description, created_at""",
                (identity.tenant_id, space, command.name, command.description),
            ).fetchone()
            conn.execute(
                """INSERT INTO mnemion.space_grants(tenant_id, space_id, principal_id, role)
                   VALUES (%s, %s, %s, 'administrator')""",
                (identity.tenant_id, space, identity.principal_id),
            )
            audit(conn, identity, "space.created", space, space_id=space)
            return {**json_value(row), "role": "administrator"}

    def space(self, identity: Identity, space: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            row = conn.execute(
                """SELECT s.id,s.name,s.description,s.created_at,g.role FROM mnemion.spaces s
                LEFT JOIN mnemion.space_grants g ON g.tenant_id=s.tenant_id AND g.space_id=s.id AND g.principal_id=%s
                WHERE s.id=%s""",
                (identity.principal_id, space),
            ).fetchone()
            if not row:
                raise not_found()
            return json_value(row)

    def principals(self, identity: Identity) -> list[dict]:
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            return json_value(
                conn.execute(
                    """SELECT id, name, kind, administrator, disabled_at, created_at
                       FROM mnemion.principals ORDER BY created_at, id LIMIT 1000"""
                ).fetchall()
            )

    def create_principal(self, identity: Identity, command: PrincipalInput) -> dict:
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            row = conn.execute(
                """INSERT INTO mnemion.principals(tenant_id, id, name, kind, administrator)
                   VALUES (%s, %s, %s, %s, %s)
                   RETURNING id, name, kind, administrator, disabled_at, created_at""",
                (identity.tenant_id, uuid4(), command.name, command.kind, command.administrator),
            ).fetchone()
            audit(conn, identity, "principal.created", row["id"])
            return json_value(row)

    def disable_principal(self, identity: Identity, principal: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            if principal == identity.principal_id:
                raise ServiceError(
                    409, "self_disable", "Use another administrator to disable yourself."
                )
            row = conn.execute(
                """UPDATE mnemion.principals SET disabled_at=coalesce(disabled_at, now())
                   WHERE tenant_id=%s AND id=%s RETURNING id, disabled_at""",
                (identity.tenant_id, principal),
            ).fetchone()
            if not row:
                raise not_found()
            audit(conn, identity, "principal.disabled", principal)
            return json_value(row)

    def create_key(self, identity: Identity, principal: UUID, command: KeyInput) -> dict:
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            if not conn.execute(
                "SELECT id FROM mnemion.principals WHERE id=%s AND disabled_at IS NULL",
                (principal,),
            ).fetchone():
                raise not_found()
            if command.expires_at and command.expires_at <= datetime.now(timezone.utc):
                raise ServiceError(422, "invalid_expiry", "Key expiry must be in the future.")
            token, digest = new_token()
            row = conn.execute(
                """INSERT INTO mnemion.api_keys
                     (tenant_id, id, principal_id, name, token_hash, prefix, expires_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING id, principal_id, name, prefix, expires_at, revoked_at, created_at""",
                (
                    identity.tenant_id,
                    uuid4(),
                    principal,
                    command.name,
                    digest,
                    token[:12],
                    command.expires_at,
                ),
            ).fetchone()
            audit(conn, identity, "key.created", row["id"], details={"principal_id": principal})
            return {**json_value(row), "api_key": token}

    def keys(self, identity: Identity) -> list[dict]:
        with self.db.transaction(identity) as conn:
            return json_value(
                conn.execute(
                    """SELECT id, principal_id, name, prefix, expires_at, revoked_at, created_at
                       FROM mnemion.api_keys ORDER BY created_at, id LIMIT 1000"""
                ).fetchall()
            )

    def revoke_key(self, identity: Identity, key: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            row = conn.execute(
                """UPDATE mnemion.api_keys SET revoked_at=coalesce(revoked_at, now())
                   WHERE id=%s RETURNING id, revoked_at""",
                (key,),
            ).fetchone()
            if not row:
                raise not_found()
            audit(conn, identity, "key.revoked", key)
            return json_value(row)

    def grant(self, identity: Identity, space: UUID, principal: UUID, command: GrantInput) -> dict:
        with self.db.transaction(identity) as conn:
            # Organization administrators can grant without reading space contents.
            admin = conn.execute("SELECT mnemion.administrator()").fetchone()["administrator"]
            if not admin:
                require_space(conn, space, 40)
            if not conn.execute("SELECT id FROM mnemion.spaces WHERE id=%s", (space,)).fetchone():
                raise not_found()
            # Space admins cannot enumerate organization identities. A principal
            # must be selected by an organization admin for the initial release.
            require_administrator(conn)
            if conn.execute("SELECT mnemion.managed_scope(%s) AS managed", (space,)).fetchone()[
                "managed"
            ]:
                raise ServiceError(
                    409,
                    "connector_managed_scope",
                    "Manage source access through connector identity mappings.",
                )
            if not conn.execute(
                "SELECT id FROM mnemion.principals WHERE id=%s AND disabled_at IS NULL",
                (principal,),
            ).fetchone():
                raise not_found()
            conn.execute(
                """INSERT INTO mnemion.space_grants(tenant_id, space_id, principal_id, role)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (tenant_id, space_id, principal_id) DO UPDATE SET role=excluded.role""",
                (identity.tenant_id, space, principal, command.role),
            )
            audit(
                conn,
                identity,
                "grant.updated",
                principal,
                space_id=space,
                details={"role": command.role},
            )
            return {"space_id": str(space), "principal_id": str(principal), "role": command.role}

    def revoke_grant(self, identity: Identity, space: UUID, principal: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            if conn.execute("SELECT mnemion.managed_scope(%s) AS managed", (space,)).fetchone()[
                "managed"
            ]:
                raise ServiceError(
                    409,
                    "connector_managed_scope",
                    "Remove the connector identity mapping to revoke source access.",
                )
            if not conn.execute("SELECT id FROM mnemion.spaces WHERE id=%s", (space,)).fetchone():
                raise not_found()
            conn.execute(
                "DELETE FROM mnemion.space_grants WHERE space_id=%s AND principal_id=%s",
                (space, principal),
            )
            audit(conn, identity, "grant.revoked", principal, space_id=space)
            return {"space_id": str(space), "principal_id": str(principal), "revoked": True}

    def grants(self, identity: Identity, space: UUID) -> list[dict]:
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            if not conn.execute("SELECT id FROM mnemion.spaces WHERE id=%s", (space,)).fetchone():
                raise not_found()
            return json_value(
                conn.execute(
                    """SELECT g.principal_id, p.name, p.kind, g.role, g.created_at
                       FROM mnemion.space_grants g JOIN mnemion.principals p
                         ON p.tenant_id=g.tenant_id AND p.id=g.principal_id
                       WHERE g.space_id=%s ORDER BY p.name, p.id LIMIT 1000""",
                    (space,),
                ).fetchall()
            )
