"""Real locale changes must preserve memory without weakening archive checks."""

from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
import pytest

from mnemion.archives import verified_archive, write_archive
from mnemion.service import recovery
from mnemion.service.admin import bootstrap_tenant
from mnemion.service.db import Database, migrate
from mnemion.service.memory import MemoryService
from mnemion.service.models import MemoryInput
from mnemion.service.worker import Worker
from service_tests.conftest import FixtureEmbedder


@pytest.fixture
def portable(postgres, pg_bin, tmp_path):
    source, destination = ("locale_" + uuid4().hex for _ in range(2))
    dsn = make_conninfo(postgres[0], dbname=source)
    with psycopg.connect(postgres[0], autocommit=True) as conn:
        conn.execute(
            sql.SQL(
                "CREATE DATABASE {} TEMPLATE template0 LOCALE_PROVIDER libc LOCALE 'C.UTF-8'"
            ).format(sql.Identifier(source))
        )
    try:
        migrate(dsn)
        embedder = FixtureEmbedder()
        account = bootstrap_tenant(
            dsn,
            tenant_name="Portable équipe",
            administrator_name="Owner",
            generation=embedder.generation,
        )
        app = Database(make_conninfo(postgres[1], dbname=source))
        worker = Database(make_conninfo(postgres[2], dbname=source), worker=True)
        app.open()
        worker.open()
        try:
            identity = app.authenticate(account["api_key"])
            memory = MemoryService(app, embedder.generation).save(
                identity,
                UUID(account["space_id"]),
                MemoryInput(
                    content="ÉQUIPE naïve Straße İstanbul Αθήνα 中文 — Postgres memory.",
                    metadata={"source": "Unicode portability", "retained": [1, 2, 3]},
                ),
                uuid4().hex,
            )
            jobs = Worker(worker, embedder)
            while jobs.run_once():
                pass
        finally:
            app.close()
            worker.close()
        archive, ledger, credentials = (
            tmp_path / name for name in ("portable.mnemion", "ledger.json", "owner.json")
        )
        recovery.create_backup(dsn, archive, pg_bin=pg_bin)
        recovery.export_ledger(dsn, ledger)
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            full = recovery.inventory(conn)
            projected = recovery.inventory(conn, version=2)
            revision = conn.execute("SELECT * FROM mnemion.memory_revisions").fetchone()
        yield {
            "source": dsn,
            "destination": destination,
            "target": make_conninfo(postgres[0], dbname=destination),
            "archive": archive,
            "ledger": ledger,
            "credentials": credentials,
            "pg_bin": pg_bin,
            "full": full,
            "projected": projected,
            "revision": revision,
            "memory": memory,
        }
    finally:
        with psycopg.connect(postgres[0], autocommit=True) as conn:
            for name in (destination, source):
                conn.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
                )


def restore(fixture, archive=None, **options):
    return recovery.restore_backup(
        fixture["source"],
        archive or fixture["archive"],
        database_name=fixture["destination"],
        deletion_ledger=fixture["ledger"],
        credentials_output=fixture["credentials"],
        pg_bin=fixture["pg_bin"],
        **options,
    )


def rewrite(fixture, output, change):
    with verified_archive(fixture["archive"], recovery.BACKUP_FORMAT) as (manifest, root):
        change(manifest)
        write_archive(output, {name: root / name for name in manifest["files"]}, manifest)
    return output


def unpublished(fixture):
    assert not fixture["credentials"].exists()
    with psycopg.connect(fixture["source"]) as conn:
        assert not conn.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (fixture["destination"],)
        ).fetchone()
        assert not conn.execute(
            "SELECT 1 FROM pg_database WHERE datname LIKE 'mnemion_restore_%'"
        ).fetchone()


def test_portable_backup_preserves_unicode_revisions_and_embeddings_across_locales(portable):
    with verified_archive(portable["archive"], recovery.BACKUP_FORMAT) as (manifest, _):
        assert manifest["inventory_version"] == 2
        assert manifest["database_locale"] == {
            "collation": "C.UTF-8",
            "ctype": "C.UTF-8",
            "provider": "libc",
        }
    result = restore(portable, database_locale="C")
    assert result["verified_tables"] == len(portable["projected"])
    with psycopg.connect(portable["target"], row_factory=dict_row) as conn:
        actual = conn.execute("SELECT * FROM mnemion.memory_revisions").fetchone()
        assert actual["search_text"] != portable["revision"]["search_text"]
        assert {key: value for key, value in actual.items() if key != "search_text"} == {
            key: value for key, value in portable["revision"].items() if key != "search_text"
        }
        assert conn.execute(
            "SELECT bool_and(search_text=to_tsvector('simple',content)) AS valid FROM mnemion.memory_revisions"
        ).fetchone()["valid"]
        projected = recovery.inventory(conn, version=2)
        assert projected["memory_revisions"] == portable["projected"]["memory_revisions"]
        assert projected["embeddings"] == portable["projected"]["embeddings"]
        assert projected["embeddings"]["count"] > 0
        assert recovery.inventory(conn)["memory_revisions"] != portable["full"]["memory_revisions"]


def test_legacy_backup_still_requires_full_hashes_and_can_select_its_source_locale(
    portable, tmp_path
):
    def legacy(manifest):
        manifest.pop("inventory_version")
        manifest.pop("database_locale")
        manifest["tables"] = portable["full"]

    archive = rewrite(portable, tmp_path / "legacy.mnemion", legacy)
    with pytest.raises(ValueError, match="legacy backup.*--database-locale"):
        restore(portable, archive, database_locale="C")
    unpublished(portable)
    result = restore(portable, archive, database_locale="C.UTF-8")
    assert result["verified_tables"] == len(portable["full"])
    with psycopg.connect(portable["target"], row_factory=dict_row) as conn:
        assert recovery.inventory(conn)["memory_revisions"] == portable["full"]["memory_revisions"]


@pytest.mark.parametrize("version", [0, 3, True, "2"])
def test_unknown_inventory_version_never_creates_a_database(portable, tmp_path, version):
    archive = rewrite(
        portable,
        tmp_path / "unsupported.mnemion",
        lambda manifest: manifest.update(inventory_version=version),
    )
    with pytest.raises(ValueError, match="inventory version"):
        restore(portable, archive)
    unpublished(portable)


def test_portable_inventory_does_not_ignore_changed_memory_hashes(portable, tmp_path):
    def corrupt(manifest):
        manifest["tables"]["memory_revisions"]["sha256"] = "0" * 64

    archive = rewrite(portable, tmp_path / "changed.mnemion", corrupt)
    with pytest.raises(ValueError, match="content hashes do not match"):
        restore(portable, archive, database_locale="C")
    unpublished(portable)


def test_only_the_packaged_generated_index_can_be_excluded(portable):
    with psycopg.connect(portable["source"], row_factory=dict_row) as conn:
        conn.execute(
            "ALTER TABLE mnemion.memory_revisions ALTER COLUMN search_text DROP EXPRESSION"
        )
        with pytest.raises(ValueError, match="packaged generated keyword index"):
            recovery.inventory(conn, version=2)
        assert recovery.inventory(conn)["memory_revisions"] == portable["full"]["memory_revisions"]
