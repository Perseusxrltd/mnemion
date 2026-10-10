"""Service integration tests always use real PostgreSQL and non-owner logins.

Set MNEMION_TEST_ADMIN_DSN to a disposable PostgreSQL instance with pgvector,
or install the development-only pgserver package. No personal profile is read.
"""

from __future__ import annotations

import os
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from mnemion.service.admin import bootstrap_tenant
from mnemion.service.db import Database, Identity, migrate
from mnemion.service.embeddings import EmbeddedChunk, Generation
from mnemion.service.identity import IdentityService
from mnemion.service.memory import MemoryService
from mnemion.service.worker import Worker


class FixtureEmbedder:
    """A deterministic protocol fixture, never a retrieval quality baseline."""

    generation = Generation(
        "fixture-only", 4, {"purpose": "transaction-and-policy-tests", "version": 1}
    )

    def query(self, text):
        values = [
            1.0 + text.lower().count(word) for word in ("postgres", "billing", "garden", "coffee")
        ]
        norm = sum(x * x for x in values) ** 0.5
        return [x / norm for x in values]

    def document(self, text):
        return [EmbeddedChunk(0, len(text), self.query(text))]

    def token_count(self, text):
        return len(text.split())


@pytest.fixture(scope="session")
def pg_bin():
    if value := os.environ.get("MNEMION_PG_BIN"):
        return Path(value)
    if value := shutil.which("pg_dump"):
        return Path(value).parent
    try:
        from pgserver._commands import POSTGRES_BIN_PATH
    except ImportError as exc:
        pytest.fail(f"Recovery tests require PostgreSQL client tools (MNEMION_PG_BIN): {exc}")
    return POSTGRES_BIN_PATH


@pytest.fixture(scope="session")
def postgres(tmp_path_factory):
    server = None
    dsn = os.environ.get("MNEMION_TEST_ADMIN_DSN")
    if not dsn:
        import pgserver

        server = pgserver.get_server(
            tmp_path_factory.mktemp("service-postgres"), cleanup_mode="stop"
        )
        dsn = server.get_uri()
    name = "mnemion_test_" + uuid4().hex
    app_role = "app_" + uuid4().hex
    worker_role = "worker_" + uuid4().hex
    app_password, worker_password = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    test_dsn = make_conninfo(dsn, dbname=name)
    migrate(test_dsn)
    with psycopg.connect(test_dsn) as conn:
        conn.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE mnemion_app").format(
                sql.Identifier(app_role), sql.Literal(app_password)
            )
        )
        conn.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE mnemion_worker").format(
                sql.Identifier(worker_role), sql.Literal(worker_password)
            )
        )
    yield (
        test_dsn,
        make_conninfo(test_dsn, user=app_role, password=app_password),
        make_conninfo(test_dsn, user=worker_role, password=worker_password),
    )
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
        conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(app_role)))
        conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(worker_role)))
    if server:
        server.cleanup()


@dataclass
class Environment:
    admin_dsn: str
    db: Database
    worker_db: Database
    owner: Identity
    token: str
    space: UUID
    memory: MemoryService
    identities: IdentityService
    embedder: FixtureEmbedder
    worker: Worker


@pytest.fixture
def env(postgres):
    admin_dsn, app_dsn, worker_dsn = postgres
    embedder = FixtureEmbedder()
    setup = bootstrap_tenant(
        admin_dsn,
        tenant_name="Test team",
        administrator_name="Owner",
        generation=embedder.generation,
    )
    db, worker_db = Database(app_dsn), Database(worker_dsn, worker=True)
    db.open()
    worker_db.open()
    owner = db.authenticate(setup["api_key"])
    yield Environment(
        admin_dsn,
        db,
        worker_db,
        owner,
        setup["api_key"],
        UUID(setup["space_id"]),
        MemoryService(db, embedder.generation),
        IdentityService(db),
        embedder,
        Worker(worker_db, embedder),
    )
    db.close()
    worker_db.close()
