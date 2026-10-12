"""Upgrade the preceding immutable SQL schema without changing workspace data."""

import hashlib
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from mnemion.service import db
from mnemion.service.admin import bootstrap_tenant
from mnemion.service.identity import IdentityService
from mnemion.service.memory import MemoryService
from mnemion.service.models import GrantInput, KeyInput, MemoryInput, PrincipalInput
from service_tests.conftest import FixtureEmbedder


def inventory(dsn):
    with psycopg.connect(dsn) as connection:
        tables = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='mnemion' AND tablename!='schema_migrations' ORDER BY tablename"
        ).fetchall()
        result = {}
        for (table,) in tables:
            rows = connection.execute(
                sql.SQL(
                    "SELECT row_to_json(t)::text AS value FROM mnemion.{} t ORDER BY value"
                ).format(sql.Identifier(table))
            ).fetchall()
            result[table] = hashlib.sha256("\n".join(row[0] for row in rows).encode()).hexdigest()
        return result


def test_previous_schema_upgrade_preserves_keys_grants_and_existing_memory(
    postgres, tmp_path, monkeypatch
):
    # Existing migrations are immutable. Package the actual preceding thirteen
    # scripts, rather than removing constraints or rewriting an applied script.
    previous = tmp_path / "previous-service"
    migrations = previous / "migrations"
    migrations.mkdir(parents=True)
    for path in db.files("mnemion.service").joinpath("migrations").iterdir():
        if path.suffix == ".sql" and path.name < "014_author_withdrawal.sql":
            (migrations / path.name).write_bytes(path.read_bytes())
    assert len(list(migrations.iterdir())) == 13
    name = "mnemion_author_upgrade_" + uuid4().hex
    admin_dsn, app_dsn, _ = (make_conninfo(dsn, dbname=name) for dsn in postgres)
    with psycopg.connect(postgres[0], autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    database = None
    try:
        embedder = FixtureEmbedder()
        with monkeypatch.context() as legacy:
            legacy.setattr(db, "files", lambda _: previous)
            assert len(db.migrate(admin_dsn)) == 13
            setup = bootstrap_tenant(
                admin_dsn,
                tenant_name="Previous workspace",
                administrator_name="Owner",
                generation=embedder.generation,
            )
            database = db.Database(app_dsn)
            database.open()
            owner = database.authenticate(setup["api_key"])
            identities = IdentityService(database)
            principal = identities.create_principal(owner, PrincipalInput(name="Restricted author"))
            key = identities.create_key(owner, UUID(principal["id"]), KeyInput(name="Existing key"))
            space = UUID(setup["space_id"])
            identities.grant(owner, space, UUID(principal["id"]), GrantInput(role="contributor"))
            author = database.authenticate(key["api_key"])
            memory = MemoryService(database, embedder.generation)
            saved = memory.save(
                author, space, MemoryInput(content="Retained ordinary note"), "before-upgrade"
            )
            database.close()
            database = None
        before = inventory(admin_dsn)
        # The current runtime must not admit the new permission on an old
        # schema lacking atomic derived-data erasure.
        rejected = db.Database(app_dsn)
        try:
            with pytest.raises(RuntimeError, match="Database migrations do not match"):
                rejected.open()
        finally:
            rejected.close()
        assert db.migrate(admin_dsn) == ["014_author_withdrawal.sql"]
        assert db.migrate(admin_dsn) == []
        assert inventory(admin_dsn) == before
        database = db.Database(app_dsn)
        database.open()
        assert database.authenticate(setup["api_key"]) == owner
        assert database.authenticate(key["api_key"]) == author
        memory = MemoryService(database, embedder.generation)
        identifier = UUID(saved["memory_id"])
        assert memory.fetch(author, identifier)["can_forget"] is True
        assert memory.forget(author, identifier, expected_version=1, key="after-upgrade")["deleted"]
    finally:
        if database:
            database.close()
        with psycopg.connect(postgres[0], autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )
