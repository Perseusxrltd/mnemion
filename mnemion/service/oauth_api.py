"""Administrator-managed external identities; no automatic provisioning or roles."""

from typing import Annotated
from uuid import UUID, uuid4

import psycopg
from fastapi import Depends
from pydantic import Field, field_validator

from .administration import retain_administrator_access
from .db import Identity, new_token, require_administrator
from .errors import ServiceError, forbidden, not_found
from .models import Command, json_value
from .oauth import binding_hash
from .repository import audit


class OAuthBindingInput(Command):
    principal_id: UUID
    name: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=255)
    client_id: str = Field(min_length=1, max_length=2048)

    @field_validator("subject", "client_id")
    @classmethod
    def valid_identity(cls, value):
        if not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("OAuth identities must be nonempty and contain no control characters")
        return value


class OAuthBindings:
    def __init__(self, database, settings=None):
        self.db = database
        self.settings = settings

    def list(self, identity: Identity):
        with self.db.transaction(identity) as conn:
            return json_value(
                conn.execute(
                    """SELECT b.id,b.principal_id,b.key_id,b.issuer,b.subject,b.client_id,
                          k.name,k.expires_at,k.revoked_at,b.created_at
                   FROM mnemion.oauth_bindings b JOIN mnemion.api_keys k
                     ON k.tenant_id=b.tenant_id AND k.id=b.key_id
                   ORDER BY b.created_at,b.id LIMIT 1000"""
                ).fetchall()
            )

    def create(self, identity: Identity, command: OAuthBindingInput):
        with self.db.administration_transaction(identity) as conn:
            require_administrator(conn)
            if self.settings is None:
                raise ServiceError(
                    409, "oauth_disabled", "The host operator has not enabled OAuth."
                )
            # Tenant administrators cannot claim another organization's issuer
            # identities. This admission policy belongs to the host operator.
            if identity.tenant_id != self.settings.tenant_id:
                raise forbidden()
            if not command.subject.strip() or not command.client_id.strip():
                raise ServiceError(
                    422, "invalid_binding", "Subject and client ID must be nonempty."
                )
            if not conn.execute(
                "SELECT id FROM mnemion.principals WHERE id=%s AND disabled_at IS NULL",
                (command.principal_id,),
            ).fetchone():
                raise not_found()
            # Never disclose a usable API key for this connection. Its anchor is
            # separately revocable with the existing key APIs and recovery tools.
            _, digest = new_token()
            key, binding = uuid4(), uuid4()
            conn.execute(
                """INSERT INTO mnemion.api_keys
                   (tenant_id,id,principal_id,name,token_hash,prefix)
                   VALUES (%s,%s,%s,%s,%s,'oauth')""",
                (identity.tenant_id, key, command.principal_id, command.name, digest),
            )
            try:
                conn.execute(
                    """INSERT INTO mnemion.oauth_bindings
                       (id,tenant_id,principal_id,key_id,issuer,subject,client_id,identity_hash)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        binding,
                        identity.tenant_id,
                        command.principal_id,
                        key,
                        self.settings.issuer,
                        command.subject,
                        command.client_id,
                        binding_hash(self.settings.issuer, command.subject, command.client_id),
                    ),
                )
            except psycopg.errors.UniqueViolation:
                raise ServiceError(
                    409,
                    "oauth_binding_exists",
                    "This OAuth identity is already bound and cannot be reassigned.",
                ) from None
            audit(
                conn,
                identity,
                "oauth.bound",
                binding,
                details={"principal_id": command.principal_id, "key_id": key},
            )
            return {
                "id": str(binding),
                "principal_id": str(command.principal_id),
                "key_id": str(key),
            }

    def revoke(self, identity: Identity, binding_id: UUID):
        with self.db.administration_transaction(identity) as conn:
            # Owners may revoke their own connection, even without org-admin
            # authority. RLS prevents discovering or revoking someone else's.
            row = conn.execute(
                """SELECT b.key_id,b.principal_id,
                          p.administrator AND p.disabled_at IS NULL AND k.revoked_at IS NULL
                          AND (k.expires_at IS NULL OR k.expires_at > clock_timestamp())
                          AS active_administrator_access
                   FROM mnemion.oauth_bindings b JOIN mnemion.api_keys k
                     ON k.tenant_id=b.tenant_id AND k.id=b.key_id
                   JOIN mnemion.principals p ON p.tenant_id=b.tenant_id AND p.id=b.principal_id
                   WHERE b.id=%s""",
                (binding_id,),
            ).fetchone()
            if row is None:
                raise not_found()
            if row["principal_id"] != identity.principal_id:
                require_administrator(conn)
            # api_keys WITH CHECK restricts updates to administrators, so use a
            # narrowly checked function for self-revocation as well.
            result = conn.execute(
                "SELECT * FROM mnemion.revoke_oauth(%s)", (binding_id,)
            ).fetchone()
            if row["active_administrator_access"]:
                retain_administrator_access(conn)
            audit(conn, identity, "oauth.revoked", binding_id)
            return json_value(result)


def attach_oauth(app, database, authenticated, settings):
    service = OAuthBindings(database, settings)
    Auth = Annotated[Identity, Depends(authenticated)]

    @app.get("/v1/oauth/bindings", tags=["Identity"], response_model=dict)
    def bindings(identity: Auth):
        """List your connections; administrators can list their organization's connections."""
        return {"items": service.list(identity)}

    @app.post("/v1/oauth/bindings", tags=["Identity"], status_code=201, response_model=dict)
    def create_binding(command: OAuthBindingInput, identity: Auth):
        """Bind a verified issuer subject and client to an existing principal; grants are unchanged."""
        return service.create(identity, command)

    @app.delete("/v1/oauth/bindings/{binding_id}", tags=["Identity"], response_model=dict)
    def revoke_binding(binding_id: UUID, identity: Auth):
        """Permanently revoke one connection without changing the person's other credentials."""
        return service.revoke(identity, binding_id)
