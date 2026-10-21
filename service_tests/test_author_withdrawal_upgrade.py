"""Upgrade the preceding immutable SQL schema without changing workspace data."""

import hashlib
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from deploy.installed_upgrade_probe import InstalledUpgrade
from mnemion.service import db
from mnemion.service.admin import bootstrap_tenant
from mnemion.service.identity import IdentityService
from mnemion.service.memory import MemoryService
from mnemion.service.models import GrantInput, KeyInput, MemoryInput, PrincipalInput
from service_tests.conftest import FixtureEmbedder
from service_tests.legacy_revision_writer import previous_revision


def inventory(dsn):
    with psycopg.connect(dsn) as connection:
        tables = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='mnemion' AND tablename!='schema_migrations' ORDER BY tablename"
        ).fetchall()
        result = {}
        for (table,) in tables:
            # 015 adds a false-by-default session marker to existing keys.
            # Compare every original field, and check that new field below.
            value = (
                sql.SQL("to_jsonb(t) - 'session_key'")
                if table == "api_keys"
                else sql.SQL("to_jsonb(t)")
            )
            if table == "memory_revisions":
                value = sql.SQL("jsonb_build_object('passage_times','{}'::jsonb) || to_jsonb(t)")
            if table in {"tenants", "spaces"}:
                value = sql.SQL("jsonb_build_object('last_index_claim',NULL) || to_jsonb(t)")
            rows = connection.execute(
                sql.SQL("SELECT ({})::text AS value FROM mnemion.{} t ORDER BY value").format(
                    value, sql.Identifier(table)
                )
            ).fetchall()
            result[table] = hashlib.sha256("\n".join(row[0] for row in rows).encode()).hexdigest()
        return result


@pytest.mark.parametrize("previous_count", [13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 26, 27, 28, 29])
def test_previous_schema_upgrade_preserves_keys_grants_and_existing_memory(
    postgres, tmp_path, monkeypatch, previous_count
):
    # Existing migrations are immutable. Package the actual preceding scripts
    # rather than removing constraints or rewriting an applied script.
    previous = tmp_path / "previous-service"
    migrations = previous / "migrations"
    migrations.mkdir(parents=True)
    for path in db.files("mnemion.service").joinpath("migrations").iterdir():
        if path.suffix == ".sql" and int(path.name[:3]) <= previous_count:
            (migrations / path.name).write_bytes(path.read_bytes())
    assert len(list(migrations.iterdir())) == previous_count
    name = "mnemion_author_upgrade_" + uuid4().hex
    admin_dsn, app_dsn, _ = (make_conninfo(dsn, dbname=name) for dsn in postgres)
    with psycopg.connect(postgres[0], autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    database = None
    try:
        embedder = FixtureEmbedder()
        with monkeypatch.context() as legacy:
            legacy.setattr(db, "files", lambda _: previous)
            legacy.setattr(MemoryService, "_revision", previous_revision)
            assert len(db.migrate(admin_dsn)) == previous_count
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
        # Exercise the installed gate's actual row hashing on the supported
        # preceding schemas without constructing or launching an installer.
        probe = object.__new__(InstalledUpgrade)
        monkeypatch.setattr(probe, "database", lambda: SimpleNamespace(dsn=lambda: admin_dsn))
        before_installed = probe.snapshot(legacy_api_keys=True)
        # The current runtime must not admit requests against an old schema.
        rejected = db.Database(app_dsn)
        try:
            with pytest.raises(RuntimeError, match="Database migrations do not match"):
                rejected.open()
        finally:
            rejected.close()
        expected = sorted(
            path.name
            for path in db.files("mnemion.service").joinpath("migrations").iterdir()
            if path.suffix == ".sql" and int(path.name[:3]) > previous_count
        )
        previous_schema = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in migrations.iterdir()
        }
        with pytest.raises(RuntimeError, match="schema changed after"):
            db.migrate(admin_dsn, expected={})
        assert inventory(admin_dsn) == before
        assert db.migrate(admin_dsn, expected=previous_schema) == expected
        assert db.migrate(admin_dsn) == []
        after_installed = probe.snapshot()
        assert after_installed["schema"] != before_installed["schema"]
        assert all(
            after_installed[table] == digest
            for table, digest in before_installed.items()
            if table != "schema"
        )
        # The new NULL default is expected; a non-NULL migration write is not.
        # Both the installed gate and exhaustive inventory must detect it.
        for table in ("tenants", "spaces"):
            with psycopg.connect(admin_dsn) as connection:
                connection.execute(
                    sql.SQL("UPDATE mnemion.{} SET last_index_claim=42").format(
                        sql.Identifier(table)
                    )
                )
            assert probe.snapshot()[table] != before_installed[table]
            assert inventory(admin_dsn)[table] != before[table]
            with psycopg.connect(admin_dsn) as connection:
                connection.execute(
                    sql.SQL("UPDATE mnemion.{} SET last_index_claim=NULL").format(
                        sql.Identifier(table)
                    )
                )
        # An erroneous session-key conversion must still fail the comparison;
        # the candidate's actual marker may never be replaced by a default.
        with psycopg.connect(admin_dsn) as connection:
            connection.execute("UPDATE mnemion.api_keys SET session_key=true")
        assert probe.snapshot()["api_keys"] != before_installed["api_keys"]
        with psycopg.connect(admin_dsn) as connection:
            connection.execute("UPDATE mnemion.api_keys SET session_key=false")
            connection.execute(
                "UPDATE mnemion.memory_revisions SET passage_times=jsonb_build_object('unexpected',true)"
            )
        assert probe.snapshot()["memory_revisions"] != before_installed["memory_revisions"]
        with psycopg.connect(admin_dsn) as connection:
            connection.execute("UPDATE mnemion.memory_revisions SET passage_times='{}'::jsonb")
        after = inventory(admin_dsn)
        assert {table: after[table] for table in before} == before
        added = set(after) - set(before)
        expected_tables = (
            {"company_links", "company_login_requests"} if previous_count < 18 else set()
        )
        if previous_count < 22:
            expected_tables |= {"writeback_settings", "writeback_events"}
        if previous_count < 25:
            expected_tables.add("writeback_backfills")
        if previous_count < 27:
            expected_tables.add("journal_recovery_origins")
        if previous_count < 28:
            expected_tables |= {
                "journal_uploads",
                "journal_upload_files",
                "journal_upload_chunks",
                "journal_upload_events",
                "journal_upload_latest",
                "journal_upload_batches",
            }
        if previous_count < 30:
            expected_tables |= {
                "capture_sources",
                "capture_grants",
                "capture_events",
                "capture_pages",
                "capture_denials",
            }
        if previous_count < 20:
            expected_tables |= {
                "vault_entries",
                "vault_grants",
                "vault_denials",
                "vault_audit_events",
            }
        if previous_count < 17:
            expected_tables.add("recovery_directories")
        if previous_count < 16:
            expected_tables |= {
                "oauth_local_attempts",
                "oauth_local_clients",
                "oauth_local_requests",
                "oauth_local_connections",
            }
        if previous_count < 15:
            expected_tables |= {
                "password_accounts",
                "sign_in_sessions",
                "spent_refresh_tokens",
                "sign_in_invitations",
                "sign_in_attempts",
            }
        assert added == expected_tables
        assert all(after[table] == hashlib.sha256(b"").hexdigest() for table in added)
        with psycopg.connect(admin_dsn) as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM mnemion.api_keys WHERE session_key"
                ).fetchone()[0]
                == 0
            )
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
