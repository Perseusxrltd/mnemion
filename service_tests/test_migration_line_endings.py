"""The packaged migration check must hash the same SQL text that was applied."""

from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from mnemion.service import db


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_fresh_and_existing_databases_accept_packaged_line_endings_and_reject_changes(
    postgres, tmp_path, monkeypatch, newline
):
    resources = tmp_path / "packaged-service"
    migrations = resources / "migrations"
    migrations.mkdir(parents=True)
    for source in db.files("mnemion.service").joinpath("migrations").iterdir():
        if source.name.endswith(".sql"):
            (migrations / source.name).write_bytes(
                source.read_text(encoding="utf-8").replace("\n", newline).encode("utf-8")
            )
    monkeypatch.setattr(db, "files", lambda package: resources)
    name = "mnemion_endings_" + uuid4().hex
    admin, app, worker = (make_conninfo(dsn, dbname=name) for dsn in postgres)
    with psycopg.connect(postgres[0], autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        assert db.migrate(admin)
        assert db.migrate(admin) == []
        for dsn, is_worker in ((app, False), (worker, True)):
            database = db.Database(dsn, worker=is_worker)
            try:
                database.open()
            finally:
                database.close()
        # Moving the same release between checkout/package line endings must
        # preserve the applied identity, while a real script change still fails.
        for path in migrations.iterdir():
            path.write_bytes(path.read_text(encoding="utf-8").encode("utf-8"))
        assert db.migrate(admin) == []
        changed = sorted(migrations.iterdir())[0]
        changed.write_bytes(changed.read_bytes() + b"\n-- Actual changed migration\n")
        with pytest.raises(RuntimeError, match="Applied migration checksum changed"):
            db.migrate(admin)
        database = db.Database(app)
        try:
            with pytest.raises(RuntimeError, match="Database migrations do not match"):
                database.open()
        finally:
            database.close()
    finally:
        with psycopg.connect(postgres[0], autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )
