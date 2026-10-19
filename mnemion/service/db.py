"""PostgreSQL connections, transaction-local identity, and checked migrations.

The API and worker use separate, non-owner database logins. Only the explicit
administration command receives migration credentials. Client-supplied tenant
identifiers never enter an authenticated application transaction.
"""

from __future__ import annotations

import hashlib
import secrets
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from importlib.resources import files
from typing import Iterator
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .errors import ServiceError, forbidden, not_found


@dataclass(frozen=True)
class Identity:
    tenant_id: UUID
    principal_id: UUID
    key_id: UUID
    expires_at: float | None = None
    session_id: UUID | None = None


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> tuple[str, str]:
    """256 bits of randomness; the database receives only its digest."""
    token = "mnm_" + secrets.token_urlsafe(32)
    return token, token_hash(token)


def migrate(dsn: str, *, expected: dict[str, str] | None = None) -> list[str]:
    """Apply immutable, checksummed migrations under a database advisory lock."""
    applied = []
    with psycopg.connect(dsn) as conn:
        if expected is not None:
            conn.execute("SET LOCAL lock_timeout='15s'")
            conn.execute("SET LOCAL statement_timeout='10min'")
        conn.execute("SELECT pg_advisory_xact_lock(731293284009)")
        if expected is not None:
            current = dict(
                conn.execute("SELECT name, sha256 FROM mnemion.schema_migrations").fetchall()
            )
            if current != expected:
                raise RuntimeError("Database schema changed after the managed upgrade was planned")
        conn.execute("CREATE SCHEMA IF NOT EXISTS mnemion")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS mnemion.schema_migrations (
                name text PRIMARY KEY, sha256 text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )"""
        )
        resources = files("mnemion.service").joinpath("migrations")
        for path in sorted(resources.iterdir(), key=lambda p: p.name):
            if not path.name.endswith(".sql"):
                continue
            script = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(script.encode("utf-8")).hexdigest()
            previous = conn.execute(
                "SELECT sha256 FROM mnemion.schema_migrations WHERE name=%s", (path.name,)
            ).fetchone()
            if previous:
                if previous[0] != digest:
                    raise RuntimeError(f"Applied migration checksum changed: {path.name}")
                continue
            conn.execute(script)
            conn.execute(
                "INSERT INTO mnemion.schema_migrations(name, sha256) VALUES (%s, %s)",
                (path.name, digest),
            )
            applied.append(path.name)
        conn.execute("REVOKE ALL ON mnemion.schema_migrations FROM mnemion_app, mnemion_worker")
        conn.execute("GRANT SELECT ON mnemion.schema_migrations TO mnemion_app, mnemion_worker")
    return applied


class Database:
    def __init__(self, dsn: str, *, worker: bool = False, max_size: int = 10):
        self.worker = worker
        self._commit_callbacks = ContextVar("mnemion_commit_callbacks", default=None)
        self.pool = ConnectionPool(
            conninfo=dsn,
            min_size=0,
            max_size=max_size,
            timeout=10,
            kwargs={"row_factory": dict_row, "connect_timeout": 5},
            open=False,
            name="mnemion-worker" if worker else "mnemion-api",
        )

    def open(self) -> None:
        self.pool.open()
        try:
            with self.pool.connection() as conn:
                required = "mnemion_worker" if self.worker else "mnemion_app"
                other = "mnemion_app" if self.worker else "mnemion_worker"
                role = conn.execute(
                    """SELECT r.rolsuper OR r.rolbypassrls OR r.rolcreaterole AS privileged,
                              pg_has_role(session_user, n.nspowner, 'member') AS owns_schema,
                              pg_has_role(current_user, %s, 'member') AS allowed,
                              pg_has_role(current_user, %s, 'member') AS mixed
                       FROM pg_roles r CROSS JOIN pg_namespace n
                       WHERE r.rolname=session_user AND n.nspname='mnemion'""",
                    (required, other),
                ).fetchone()
                if not role or role["privileged"] or role["owns_schema"]:
                    raise RuntimeError("Service database login must not own or bypass its schema")
                if not role["allowed"] or role["mixed"]:
                    raise RuntimeError(f"Service database login must belong only to {required}")
                actual = {
                    r["name"]: r["sha256"]
                    for r in conn.execute("SELECT name, sha256 FROM mnemion.schema_migrations")
                }
                expected = {
                    # migrate() applies and hashes universal-newline UTF-8
                    # text. Windows checkouts may package CRLF files; compare
                    # the executed SQL identity, not different on-disk bytes.
                    p.name: hashlib.sha256(
                        p.read_text(encoding="utf-8").encode("utf-8")
                    ).hexdigest()
                    for p in files("mnemion.service").joinpath("migrations").iterdir()
                    if p.name.endswith(".sql")
                }
                if actual != expected:
                    raise RuntimeError("Database migrations do not match this service release")
        except BaseException:
            self.pool.close()
            raise

    def close(self) -> None:
        self.pool.close()

    def authenticate(self, token: str, *, company_policies=()) -> Identity:
        if self.worker or not token.startswith("mnm_") or not 40 <= len(token) <= 200:
            raise ServiceError(401, "unauthorized", "A valid Mnemion API key is required.")
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM mnemion.authenticate(%s)", (token_hash(token),)
            ).fetchone()
            if not row:
                session = conn.execute(
                    "SELECT * FROM mnemion.authenticate_session(%s)", (token_hash(token),)
                ).fetchone()
                if not session and company_policies:
                    session = conn.execute(
                        "SELECT * FROM mnemion.authenticate_company_session(%s,%s)",
                        (token_hash(token), list(company_policies)),
                    ).fetchone()
                if session:
                    return Identity(
                        session["tenant_id"],
                        session["principal_id"],
                        session["key_id"],
                        session["expires_at"].timestamp(),
                        session["session_id"],
                    )
        if not row:
            raise ServiceError(401, "unauthorized", "A valid Mnemion API key is required.")
        return Identity(row["tenant_id"], row["principal_id"], row["key_id"])

    def authenticate_oauth(self, claims) -> Identity:
        """Resolve only fully verified claims from the operator's trusted issuer."""
        if self.worker:
            raise ServiceError(401, "unauthorized", "A valid access token is required.")
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM mnemion.authenticate_oauth(%s,%s,%s)",
                (claims.issuer, claims.subject, claims.client_id),
            ).fetchone()
        if not row or row["tenant_id"] != claims.tenant_id:
            raise ServiceError(
                401, "unauthorized", "A valid, linked Mnemion access token is required."
            )
        return Identity(row["tenant_id"], row["principal_id"], row["key_id"], claims.expires_at)

    @contextmanager
    def transaction(
        self, identity: Identity, *, timeout: float | None = None
    ) -> Iterator[psycopg.Connection]:
        if self.worker:
            raise RuntimeError("Worker connections cannot serve API requests")
        callbacks = []
        with self.pool.connection(timeout=timeout) as conn:
            token = self._commit_callbacks.set((conn, callbacks))
            try:
                with conn.transaction():
                    self._scope(conn, identity.tenant_id, identity.principal_id)
                    # Authentication is rechecked in each new transaction. A request
                    # cannot retain access through a cached Identity after revocation.
                    self._check_identity(conn, identity)
                    yield conn
            finally:
                self._commit_callbacks.reset(token)
        # No filesystem publication happens before COMMIT, or while a pool
        # connection is retained. A failed callback leaves its durable SQL event
        # pending and surfaces a retryable response to the original caller.
        for callback in callbacks:
            callback()

    def after_commit(self, conn, callback) -> None:
        active = self._commit_callbacks.get()
        if active is None or active[0] is not conn:
            raise RuntimeError("An after-commit action requires this authenticated transaction")
        active[1].append(callback)

    @staticmethod
    def _check_identity(conn: psycopg.Connection, identity: Identity) -> None:
        valid = conn.execute(
            """SELECT k.id FROM mnemion.api_keys k JOIN mnemion.principals p
                 ON p.tenant_id=k.tenant_id AND p.id=k.principal_id
               WHERE k.id=%s AND k.principal_id=mnemion.principal()
                 AND k.revoked_at IS NULL AND p.disabled_at IS NULL
                 AND (k.expires_at IS NULL OR k.expires_at > clock_timestamp())
                 AND (%s::double precision IS NULL OR %s > extract(epoch FROM clock_timestamp()))""",
            (identity.key_id, identity.expires_at, identity.expires_at),
        ).fetchone()
        if not valid:
            raise ServiceError(401, "unauthorized", "The API key is no longer valid.")

    @contextmanager
    def administration_transaction(self, identity: Identity) -> Iterator[psycopg.Connection]:
        """Serialize credential changes across service processes for one tenant.

        A request may wait behind its own revocation. Check current credentials
        again after admission; transaction-start time is insufficient for expiry.
        OAuth self-revocation uses the same boundary without requiring an admin.
        """
        with self.transaction(identity) as conn:
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"administrator-access:{identity.tenant_id}",),
            )
            self._check_identity(conn, identity)
            yield conn

    @contextmanager
    def worker_transaction(
        self, tenant_id: UUID, *, timeout: float | None = None
    ) -> Iterator[psycopg.Connection]:
        if not self.worker:
            raise RuntimeError("Application connections cannot run worker transactions")
        with self.pool.connection(timeout=timeout) as conn:
            with conn.transaction():
                self._scope(conn, tenant_id, None)
                yield conn

    @staticmethod
    def _scope(conn: psycopg.Connection, tenant_id: UUID, principal_id: UUID | None) -> None:
        conn.execute(
            """SELECT set_config('mnemion.tenant_id', %s, true),
                      set_config('mnemion.principal_id', %s, true),
                      set_config('statement_timeout', '15000', true),
                      set_config('lock_timeout', '5000', true)""",
            (str(tenant_id), str(principal_id) if principal_id else ""),
        )


def require_space(
    conn: psycopg.Connection, space_id: UUID, level: int = 10, *, writing: bool = False
) -> None:
    if not conn.execute("SELECT mnemion.authorized(%s)", (space_id,)).fetchone()["authorized"]:
        raise not_found()
    if (
        level > 10
        and not conn.execute("SELECT mnemion.authorized(%s, %s)", (space_id, level)).fetchone()[
            "authorized"
        ]
    ):
        raise forbidden()
    if writing:
        from .fences import write_boundary

        tenant = conn.execute("SELECT mnemion.tenant() AS id").fetchone()["id"]
        write_boundary(conn, tenant, space_id)


def require_administrator(conn: psycopg.Connection) -> None:
    if not conn.execute("SELECT mnemion.administrator()").fetchone()["administrator"]:
        raise forbidden()


def resolve_spaces(conn: psycopg.Connection, selection, level: int = 10) -> list[UUID]:
    """Resolve current authorized scopes, including large connector collections."""
    if selection.all_accessible:
        rows = conn.execute(
            """SELECT id FROM mnemion.spaces WHERE mnemion.authorized(id,%s)
                           ORDER BY id LIMIT 10001""",
            (level,),
        ).fetchall()
        if len(rows) > 10000:
            raise ServiceError(
                413,
                "scope_limit",
                "Select explicit spaces for an account with more than 10,000 readable scopes.",
            )
        return [row["id"] for row in rows]
    for space in selection.space_ids:
        require_space(conn, space, level)
    return selection.space_ids
