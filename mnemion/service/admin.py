"""Explicit database-owner setup; never imported into an HTTP route."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .db import new_token
from .embeddings import DEFAULT_GENERATION, Generation


def register_generation(conn: psycopg.Connection, generation: Generation) -> None:
    conn.execute(
        """INSERT INTO mnemion.embedding_generations(id, model, configuration, dimensions)
           VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
        (generation.id, generation.model, Jsonb(generation.configuration), generation.dimensions),
    )


def bootstrap_tenant(
    dsn: str,
    *,
    tenant_name: str,
    administrator_name: str,
    space_name: str = "Private memory",
    generation: Generation = DEFAULT_GENERATION,
    credentials_sink: Callable[[dict], None] | None = None,
) -> dict:
    """Create a tenant and one private space; return its one-time owner key.

    New application credentials receive no space access until explicitly granted.
    An organization administrator likewise needs a space grant to read content.
    """
    for value in (tenant_name, administrator_name, space_name):
        if not 1 <= len(value.strip()) <= 200:
            raise ValueError("Names must contain 1–200 characters")
    tenant, principal, space, key = [uuid4() for _ in range(4)]
    token, digest = new_token()
    result = {
        "tenant_id": str(tenant),
        "principal_id": str(principal),
        "space_id": str(space),
        "key_id": str(key),
        "api_key": token,
        "generation_id": generation.id,
    }
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        register_generation(conn, generation)
        conn.execute("INSERT INTO mnemion.tenants(id, name) VALUES (%s, %s)", (tenant, tenant_name))
        conn.execute(
            """INSERT INTO mnemion.principals(tenant_id, id, name, kind, administrator)
               VALUES (%s, %s, %s, 'human', true)""",
            (tenant, principal, administrator_name),
        )
        conn.execute(
            "INSERT INTO mnemion.spaces(tenant_id, id, name) VALUES (%s, %s, %s)",
            (tenant, space, space_name),
        )
        conn.execute(
            """INSERT INTO mnemion.space_grants(tenant_id, space_id, principal_id, role)
               VALUES (%s, %s, %s, 'administrator')""",
            (tenant, space, principal),
        )
        conn.execute(
            """INSERT INTO mnemion.api_keys
                 (tenant_id, id, principal_id, name, token_hash, prefix)
               VALUES (%s, %s, %s, 'Bootstrap owner', %s, %s)""",
            (tenant, key, principal, digest, token[:12]),
        )
        conn.execute(
            """INSERT INTO mnemion.audit_events
                 (tenant_id, id, principal_id, action, resource_id)
               VALUES (%s, %s, %s, 'tenant.created', %s)""",
            (tenant, uuid4(), principal, str(tenant)),
        )
        # Persist the one-time secret before committing its hash. A disk failure
        # rolls back setup instead of leaving an inaccessible organization.
        if credentials_sink is not None:
            credentials_sink(result)
    return result
