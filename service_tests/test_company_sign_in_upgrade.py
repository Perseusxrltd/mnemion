"""Existing personal sessions survive the company-sign-in schema migration."""

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from mnemion.service import api, db
from mnemion.service.admin import bootstrap_tenant
from mnemion.service.hosted_oauth import HostedOAuth, HostedOAuthSettings
from mnemion.service.sign_in import PasswordInput, SignInInput, SignInService
from service_tests.conftest import FixtureEmbedder
from service_tests.test_hosted_oauth import (
    ORIGIN,
    PASSWORD,
    approve,
    bearer,
    exchange,
    login,
    refresh,
    start,
)


class PreviousHostedOAuth(HostedOAuth):
    """Exercise the actual pre-019 SQL, whose entry points had no company policy argument."""

    def _call(self, function, *arguments):
        if function.endswith("_current"):
            function, arguments = function.removesuffix("_current"), arguments[:-1]
        return super()._call(function, *arguments)


@pytest.mark.parametrize("previous_count", [17, 18])
def test_pre_company_upgrade_preserves_existing_password_session(
    postgres, tmp_path, monkeypatch, previous_count
):
    previous = tmp_path / "previous-service"
    migrations = previous / "migrations"
    migrations.mkdir(parents=True)
    for path in db.files("mnemion.service").joinpath("migrations").iterdir():
        if path.suffix == ".sql" and int(path.name[:3]) <= previous_count:
            (migrations / path.name).write_bytes(path.read_bytes())
    name = "mnemion_company_upgrade_" + uuid4().hex
    admin_dsn, app_dsn, _ = (make_conninfo(dsn, dbname=name) for dsn in postgres)
    with psycopg.connect(postgres[0], autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    database = None
    try:
        with monkeypatch.context() as legacy:
            legacy.setattr(db, "files", lambda _: previous)
            assert len(db.migrate(admin_dsn)) == previous_count
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
            password = PASSWORD
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
            if previous_count == 18:
                legacy.setattr(api, "HostedOAuth", PreviousHostedOAuth)
                settings = HostedOAuthSettings.for_workspace(ORIGIN, owner.tenant_id)
                with TestClient(
                    api.create_app(
                        database,
                        FixtureEmbedder(),
                        mcp_enabled=False,
                        hosted_oauth_settings=settings,
                    ),
                    base_url=ORIGIN,
                ) as client:
                    registered, verifier, ticket, headers = start(client)
                    code = approve(client, ticket, headers, username="existing-owner")
                    issued = exchange(client, registered, verifier, code)
                    assert issued.status_code == 200, issued.text
                    oauth_tokens = issued.json()
                    pending_client, pending_verifier, pending_ticket, pending_headers = start(
                        client
                    )
                    pending_review = login(
                        client, pending_ticket, pending_headers, username="existing-owner"
                    )
                with psycopg.connect(admin_dsn) as connection:
                    old_oauth = connection.execute(
                        "SELECT to_jsonb(r) FROM mnemion.oauth_local_requests r ORDER BY id"
                    ).fetchall()
                    old_sessions = connection.execute(
                        "SELECT to_jsonb(s) FROM mnemion.sign_in_sessions s ORDER BY id"
                    ).fetchall()
            database.close()
            database = None
        assert db.migrate(admin_dsn) == (
            ["018_company_sign_in.sql"] if previous_count == 17 else []
        ) + ["019_company_agent_consent.sql", "020_secrets_vault.sql"]
        with psycopg.connect(admin_dsn) as connection:
            after = connection.execute(
                "SELECT to_jsonb(s) FROM mnemion.sign_in_sessions s WHERE id=%s",
                (session["session_id"],),
            ).fetchone()[0]
        assert after == {**before, "company_link_id": None}
        if previous_count == 18:
            with psycopg.connect(admin_dsn) as connection:
                assert connection.execute(
                    "SELECT to_jsonb(r) FROM mnemion.oauth_local_requests r ORDER BY id"
                ).fetchall() == [
                    ({**row[0], "company_link_id": None, "company_expires_at": None},)
                    for row in old_oauth
                ]
                assert (
                    connection.execute(
                        "SELECT to_jsonb(s) FROM mnemion.sign_in_sessions s ORDER BY id"
                    ).fetchall()
                    == old_sessions
                )
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
        if previous_count == 18:
            from urllib.parse import parse_qs, urlsplit

            with TestClient(
                api.create_app(
                    database, FixtureEmbedder(), mcp_enabled=False, hosted_oauth_settings=settings
                ),
                base_url=ORIGIN,
            ) as upgraded:
                assert (
                    upgraded.get("/v1/me", headers=bearer(oauth_tokens["access_token"])).status_code
                    == 200
                )
                assert (
                    refresh(upgraded, registered, oauth_tokens["refresh_token"]).status_code == 200
                )
                upgraded.cookies.update(client.cookies)
                allowed = upgraded.post(
                    "/oauth/consent/approve",
                    headers=pending_headers,
                    json={"ticket": pending_ticket, "proof": pending_review["proof"]},
                )
                assert allowed.status_code == 200, allowed.text
                code = parse_qs(urlsplit(allowed.json()["redirect"]).query)["code"][0]
                assert exchange(upgraded, pending_client, pending_verifier, code).status_code == 200
    finally:
        if database:
            database.close()
        with psycopg.connect(postgres[0], autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )
