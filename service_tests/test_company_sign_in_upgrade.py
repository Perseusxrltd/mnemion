"""Existing personal sessions survive the company-sign-in schema migration."""

from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from mnemion.service import db
from mnemion.service.admin import bootstrap_tenant
from mnemion.service.sign_in import PasswordInput, SignInInput, SignInService
from service_tests.conftest import FixtureEmbedder


def test_pre_company_upgrade_preserves_existing_password_session(postgres, tmp_path, monkeypatch):
    previous = tmp_path / "previous-service"
    migrations = previous / "migrations"
    migrations.mkdir(parents=True)
    for path in db.files("mnemion.service").joinpath("migrations").iterdir():
        if path.suffix == ".sql" and int(path.name[:3]) <= 17:
            (migrations / path.name).write_bytes(path.read_bytes())
    name = "mnemion_company_upgrade_" + uuid4().hex
    admin_dsn, app_dsn, _ = (make_conninfo(dsn, dbname=name) for dsn in postgres)
    with psycopg.connect(postgres[0], autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    database = None
    try:
        with monkeypatch.context() as legacy:
            legacy.setattr(db, "files", lambda _: previous)
            assert len(db.migrate(admin_dsn)) == 17
            setup = bootstrap_tenant(
                admin_dsn,
                tenant_name="Existing company",
                administrator_name="Existing owner",
                generation=FixtureEmbedder.generation,
            )
            database = db.Database(app_dsn)
            database.open()
            owner = database.authenticate(setup["api_key"])
            sign_in = SignInService(database)
            password = "harbour beacon meadow copper compass"
            sign_in.set_password(owner, PasswordInput(username="existing-owner", password=password))
            session = sign_in.sign_in(
                SignInInput(
                    workspace_id=owner.tenant_id,
                    username="existing-owner",
                    password=password,
                    device_name="Existing device",
                    transport="native",
                )
            )
            with psycopg.connect(admin_dsn) as connection:
                before = connection.execute(
                    "SELECT to_jsonb(s) FROM mnemion.sign_in_sessions s WHERE id=%s",
                    (session["session_id"],),
                ).fetchone()[0]
            database.close()
            database = None
        assert db.migrate(admin_dsn) == ["018_company_sign_in.sql"]
        with psycopg.connect(admin_dsn) as connection:
            after = connection.execute(
                "SELECT to_jsonb(s) FROM mnemion.sign_in_sessions s WHERE id=%s",
                (session["session_id"],),
            ).fetchone()[0]
        assert after == {**before, "company_link_id": None}
        database = db.Database(app_dsn)
        database.open()
        assert database.authenticate(setup["api_key"]) == owner
        assert database.authenticate(session["access_token"]).principal_id == owner.principal_id
        refreshed = SignInService(database).refresh(
            session["refresh_token"],
            transport="native",
            workspace=owner.tenant_id,
            session=UUID(session["session_id"]),
        )
        assert refreshed["session_id"] == session["session_id"]
        assert refreshed["authentication"] == "password"
        assert refreshed["expires_at"] == session["expires_at"]
        assert database.authenticate(refreshed["access_token"]).principal_id == owner.principal_id
    finally:
        if database:
            database.close()
        with psycopg.connect(postgres[0], autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )
