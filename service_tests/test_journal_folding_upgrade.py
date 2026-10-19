"""Migration 023 preserves an approved 4.15 publisher without enabling filing."""

from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from mnemion.service import db
from mnemion.service.admin import bootstrap_tenant
from service_tests.conftest import FixtureEmbedder


def test_existing_journal_policy_keeps_every_field_and_filing_stays_disabled(
    postgres, tmp_path, monkeypatch
):
    previous = tmp_path / "previous-service"
    scripts = previous / "migrations"
    scripts.mkdir(parents=True)
    expected_migrations = []
    for path in db.files("mnemion.service").joinpath("migrations").iterdir():
        if path.suffix == ".sql" and int(path.name[:3]) <= 22:
            (scripts / path.name).write_bytes(path.read_bytes())
        elif path.suffix == ".sql":
            expected_migrations.append(path.name)
    name = "mnemion_journal_upgrade_" + uuid4().hex
    admin_dsn = make_conninfo(postgres[0], dbname=name)
    with psycopg.connect(postgres[0], autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        with monkeypatch.context() as old:
            old.setattr(db, "files", lambda _: previous)
            assert len(db.migrate(admin_dsn)) == 22
            setup = bootstrap_tenant(
                admin_dsn,
                tenant_name="Existing journal team",
                administrator_name="Owner",
                generation=FixtureEmbedder.generation,
            )
            with psycopg.connect(admin_dsn) as conn:
                tenant = conn.execute(
                    "SELECT tenant_id FROM mnemion.spaces WHERE id=%s", (UUID(setup["space_id"]),)
                ).fetchone()[0]
                principal, key = conn.execute(
                    "SELECT principal_id,id FROM mnemion.api_keys WHERE tenant_id=%s", (tenant,)
                ).fetchone()
                conn.execute(
                    """INSERT INTO mnemion.writeback_settings
                       (tenant_id,space_id,destination_id,fingerprint,publisher_id,key_id,created_by,
                        interval_seconds,last_error,last_entries,last_bytes)
                       VALUES (%s,%s,'existing-destination',%s,%s,%s,%s,900,'prior_delivery_pending',12,1234)""",
                    (tenant, UUID(setup["space_id"]), "a" * 64, principal, key, principal),
                )
                before = conn.execute(
                    "SELECT to_jsonb(s) FROM mnemion.writeback_settings s"
                ).fetchone()[0]
        assert db.migrate(admin_dsn) == sorted(expected_migrations)
        assert db.migrate(admin_dsn) == []
        defaults = {
            "fold_enabled": False,
            "fold_after_hours": 24,
            "fold_interval_seconds": 3600,
            **{
                key: None
                for key in ("next_fold_at", "last_fold_at", "last_fold_commit", "last_fold_error")
            },
            **{
                key: 0
                for key in (
                    "last_fold_notes",
                    "last_fold_archived_files",
                    "last_fold_pending_notes",
                    "last_fold_pending_files",
                    "last_fold_read_bytes",
                    "last_fold_written_bytes",
                )
            },
        }
        with psycopg.connect(admin_dsn) as conn:
            after = conn.execute("SELECT to_jsonb(s) FROM mnemion.writeback_settings s").fetchone()[
                0
            ]
            assert after == {**before, **defaults}
            assert not conn.execute(
                "SELECT * FROM mnemion.claim_journal_fold(%s)", (["a" * 64],)
            ).fetchone()
            assert not conn.execute("SELECT * FROM mnemion.writeback_backfills").fetchone()
    finally:
        with psycopg.connect(postgres[0], autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
