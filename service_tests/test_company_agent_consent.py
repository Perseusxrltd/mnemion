"""Company identities authorize assistants through real SQL and the MCP OAuth handlers."""

from dataclasses import replace
from datetime import datetime, timezone
import secrets
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from mnemion.service import recovery
from mnemion.service.api import create_app
from mnemion.service.company_identity import CompanyIdentity
from mnemion.service.db import Database, new_token, token_hash
from mnemion.service.hosted_oauth import HostedOAuthSettings
from mnemion.service.models import GrantInput, PrincipalInput
from mnemion.service.sign_in import PasswordInput, SignInService
from service_tests.test_company_sign_in import (
    ORIGIN,
    company as company,
    finish as studio_finish,
    linked,
    signing_key as signing_key,
    start as studio_start,
)
from service_tests.test_hosted_oauth import PASSWORD, bearer, exchange, login, refresh, start


@pytest.fixture
def company_hosted(company, env):
    with psycopg.connect(env.admin_dsn) as connection:
        connection.execute("DELETE FROM mnemion.sign_in_attempts")
        connection.execute("DELETE FROM mnemion.oauth_local_attempts")
    with TestClient(
        create_app(
            env.db,
            env.embedder,
            mcp_enabled=False,
            hosted_oauth_settings=HostedOAuthSettings.for_workspace(ORIGIN, env.owner.tenant_id),
            company_identity=company.identity,
        ),
        base_url=ORIGIN,
    ) as client:
        yield client


def begin(client, company, ticket, headers):
    response = client.post(
        "/oauth/consent/company/start",
        headers=headers,
        json={"ticket": ticket, "provider_id": company.provider.id},
    )
    assert response.status_code == 200, response.text
    flow = response.json()
    code = secrets.token_urlsafe(24)
    company.codes[code] = parse_qs(urlsplit(flow["authorization_url"]).query)
    return {
        "ticket": ticket,
        "state": flow["state"],
        "code_verifier": flow["code_verifier"],
        "code": code,
    }


def reviewed(client, company):
    registration, verifier, ticket, headers = start(client)
    flow = begin(client, company, ticket, headers)
    response = client.post("/oauth/consent/company/finish", headers=headers, json=flow)
    assert response.status_code == 200, response.text
    return SimpleNamespace(
        registration=registration,
        verifier=verifier,
        ticket=ticket,
        headers=headers,
        review=response.json(),
        flow=flow,
    )


def approve(client, attempt):
    return client.post(
        "/oauth/consent/approve",
        headers=attempt.headers,
        json={"ticket": attempt.ticket, "proof": attempt.review["proof"]},
    )


def redeem(client, attempt):
    response = approve(client, attempt)
    assert response.status_code == 200, response.text
    attempt.code = parse_qs(urlsplit(response.json()["redirect"]).query)["code"][0]
    return exchange(client, attempt.registration, attempt.verifier, attempt.code)


def test_passwordless_company_consent_preserves_studio_cookies_and_obeys_expiry(
    company_hosted, company, env
):
    link = linked(company, env)
    studio = studio_finish(company, studio_start(company, env, transport="browser", remember=True))
    assert studio.status_code == 200, studio.text
    original_cookies = dict(company.client.cookies)
    assert original_cookies
    company_hosted.cookies.update(company.client.cookies)
    attempt = reviewed(company_hosted, company)
    assert attempt.review["authentication"] == "company"
    assert attempt.review["permissions"]["principal_id"] == str(env.owner.principal_id)
    assert all(
        company_hosted.cookies.get(name) == value for name, value in original_cookies.items()
    )
    with psycopg.connect(env.admin_dsn) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM mnemion.password_accounts WHERE tenant_id=%s",
                (env.owner.tenant_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM mnemion.sign_in_sessions WHERE tenant_id=%s",
                (env.owner.tenant_id,),
            ).fetchone()[0]
            == 1
        )
    response = redeem(company_hosted, attempt)
    assert response.status_code == 200, response.text
    tokens = response.json()
    assert company_hosted.get("/v1/me", headers=bearer(tokens["access_token"])).status_code == 200
    with psycopg.connect(env.admin_dsn) as connection:
        row = connection.execute(
            "SELECT s.expires_at,s.company_link_id FROM mnemion.sign_in_sessions s WHERE access_hash=%s",
            (token_hash(tokens["access_token"]),),
        ).fetchone()
    assert row[0] == datetime.fromisoformat(attempt.review["expires_at"])
    assert row[1] == UUID(link["id"])
    remaining = (row[0] - datetime.now(timezone.utc)).total_seconds()
    assert company.provider.session_seconds - 60 < remaining <= company.provider.session_seconds
    changed = refresh(company_hosted, attempt.registration, tokens["refresh_token"])
    assert changed.status_code == 200, changed.text
    assert company_hosted.get("/v1/me", headers=bearer(tokens["access_token"])).status_code == 401
    with psycopg.connect(env.admin_dsn) as connection:
        assert (
            connection.execute(
                "SELECT expires_at FROM mnemion.sign_in_sessions WHERE access_hash=%s",
                (token_hash(changed.json()["access_token"]),),
            ).fetchone()[0]
            == row[0]
        )
    assert (
        company.client.delete(
            "/v1/sign-in/company/links/" + link["id"], headers=bearer(env.token)
        ).status_code
        == 200
    )
    assert (
        company_hosted.get("/v1/me", headers=bearer(changed.json()["access_token"])).status_code
        == 401
    )
    assert (
        refresh(company_hosted, attempt.registration, changed.json()["refresh_token"]).status_code
        == 400
    )
    assert company_hosted.get("/v1/me", headers=bearer(env.token)).status_code == 200


def test_unknown_company_identity_cannot_enroll_through_consent(company_hosted, company, env):
    _, _, ticket, headers = start(company_hosted)
    company.claims = {"email_verified": True, "email": "owner@example.test", "roles": ["admin"]}
    response = company_hosted.post(
        "/oauth/consent/company/finish",
        headers=headers,
        json=begin(company_hosted, company, ticket, headers),
    )
    assert response.status_code == 401
    with psycopg.connect(env.admin_dsn) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM mnemion.company_links WHERE tenant_id=%s",
                (env.owner.tenant_id,),
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize("mismatch", ["ticket", "browser", "studio", "native"])
def test_company_login_is_bound_to_its_consent_request_browser_and_purpose(
    company_hosted, company, env, mismatch
):
    linked(company, env)
    _, _, ticket, headers = start(company_hosted)
    flow = begin(company_hosted, company, ticket, headers)
    if mismatch == "ticket":
        _, _, changed, changed_headers = start(company_hosted)
        response = company_hosted.post(
            "/oauth/consent/company/finish",
            headers=changed_headers,
            json={**flow, "ticket": changed},
        )
    elif mismatch == "browser":
        company_hosted.cookies.clear()
        request = company_hosted.post(
            "/oauth/consent/request", headers={"Origin": ORIGIN}, json={"ticket": ticket}
        )
        response = company_hosted.post(
            "/oauth/consent/company/finish",
            headers={"Origin": ORIGIN, "X-Mnemion-Consent-CSRF": request.json()["csrf"]},
            json=flow,
        )
    elif mismatch == "studio":
        response = company_hosted.post(
            "/v1/sign-in/company/finish",
            headers={"Origin": ORIGIN},
            json={
                key: value
                for key, value in {**flow, "transport": "browser"}.items()
                if key != "ticket"
            },
        )
    else:
        response = company_hosted.post(
            "/oauth/consent/company/finish", headers=headers, json={**flow, "transport": "native"}
        )
    assert response.status_code in {401, 422}, response.text
    assert company.calls == []  # Reject mismatched handoffs before exchanging a provider code.
    with psycopg.connect(env.admin_dsn) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM mnemion.sign_in_sessions WHERE tenant_id=%s",
                (env.owner.tenant_id,),
            ).fetchone()[0]
            == 0
        )


def test_consent_company_start_and_finish_require_origin_and_csrf(company_hosted, company, env):
    linked(company, env)
    _, _, ticket, headers = start(company_hosted)
    flow = begin(company_hosted, company, ticket, headers)
    for changed in (
        {"Origin": ORIGIN},
        {**headers, "Origin": "https://unrelated.example.test"},
        {**headers, "Sec-Fetch-Site": "cross-site"},
    ):
        for path, body in (
            ("start", {"ticket": ticket, "provider_id": "company"}),
            ("finish", flow),
        ):
            assert (
                company_hosted.post(
                    "/oauth/consent/company/" + path, headers=changed, json=body
                ).status_code
                == 403
            )
    # Rejected CSRF does not consume the legitimate attempt.
    assert (
        company_hosted.post("/oauth/consent/company/finish", headers=headers, json=flow).status_code
        == 200
    )
    assert (
        company_hosted.post("/oauth/consent/company/finish", headers=headers, json=flow).status_code
        == 401
    )


@pytest.mark.parametrize("stage", ["review", "exchange", "access"])
@pytest.mark.parametrize("change", ["revoked", "disabled", "policy", "expired"])
def test_current_company_authority_is_required_throughout_consent_and_token_use(
    company_hosted, company, env, stage, change
):
    link = linked(company, env)
    attempt = reviewed(company_hosted, company)
    tokens = None
    if stage == "exchange":
        response = approve(company_hosted, attempt)
        assert response.status_code == 200
        code = parse_qs(urlsplit(response.json()["redirect"]).query)["code"][0]
    elif stage == "access":
        response = redeem(company_hosted, attempt)
        assert response.status_code == 200, response.text
        tokens = response.json()
    with psycopg.connect(env.admin_dsn) as connection:
        if change == "revoked":
            connection.execute(
                "UPDATE mnemion.company_links SET revoked_at=clock_timestamp() WHERE id=%s",
                (link["id"],),
            )
        elif change == "disabled":
            connection.execute(
                "UPDATE mnemion.principals SET disabled_at=clock_timestamp() WHERE tenant_id=%s AND id=%s",
                (env.owner.tenant_id, env.owner.principal_id),
            )
        elif change == "policy":
            connection.execute(
                "UPDATE mnemion.company_links SET policy_hash=%s WHERE id=%s",
                ("0" * 64, link["id"]),
            )
        elif tokens:
            connection.execute(
                "UPDATE mnemion.sign_in_sessions SET access_expires_at=now()-interval '1 second', expires_at=now()-interval '1 second' WHERE access_hash=%s",
                (token_hash(tokens["access_token"]),),
            )
        else:
            connection.execute(
                "UPDATE mnemion.oauth_local_requests SET company_expires_at=clock_timestamp()-interval '1 second' WHERE ticket_hash=%s",
                (token_hash(attempt.ticket),),
            )
    if stage == "review":
        assert approve(company_hosted, attempt).status_code == 409
    elif stage == "exchange":
        assert (
            exchange(company_hosted, attempt.registration, attempt.verifier, code).status_code
            == 400
        )
    else:
        assert (
            company_hosted.get("/v1/me", headers=bearer(tokens["access_token"])).status_code == 401
        )
        assert (
            refresh(company_hosted, attempt.registration, tokens["refresh_token"]).status_code
            == 400
        )


@pytest.mark.parametrize("stage", ["review", "exchange"])
def test_changed_space_permissions_require_new_company_consent(company_hosted, company, env, stage):
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Company reader", kind="human")
    )
    linked(company, env, UUID(person["id"]))
    env.identities.grant(env.owner, env.space, UUID(person["id"]), GrantInput(role="reader"))
    attempt = reviewed(company_hosted, company)
    if stage == "exchange":
        response = approve(company_hosted, attempt)
        assert response.status_code == 200
        code = parse_qs(urlsplit(response.json()["redirect"]).query)["code"][0]
    env.identities.grant(env.owner, env.space, UUID(person["id"]), GrantInput(role="contributor"))
    if stage == "review":
        assert approve(company_hosted, attempt).status_code == 409
    else:
        assert (
            exchange(company_hosted, attempt.registration, attempt.verifier, code).status_code
            == 400
        )


def test_company_member_tokens_and_reuse_keep_other_connections_safe(company_hosted, company, env):
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Company reader", kind="human")
    )
    linked(company, env, UUID(person["id"]))
    env.identities.grant(env.owner, env.space, UUID(person["id"]), GrantInput(role="reader"))
    first = reviewed(company_hosted, company)
    assert first.review["permissions"]["administrator"] is False
    one = redeem(company_hosted, first).json()
    second = reviewed(company_hosted, company)
    two = redeem(company_hosted, second).json()
    assert (
        company_hosted.post(
            "/v1/spaces", json={"name": "Forbidden"}, headers=bearer(two["access_token"])
        ).status_code
        == 403
    )
    assert (
        company_hosted.get("/v1/spaces", headers=bearer(two["access_token"])).json()["items"][0][
            "role"
        ]
        == "reader"
    )
    assert (
        exchange(company_hosted, first.registration, first.verifier, first.code).status_code == 400
    )
    assert company_hosted.get("/v1/me", headers=bearer(one["access_token"])).status_code == 401
    assert company_hosted.get("/v1/me", headers=bearer(two["access_token"])).status_code == 200
    rotated = refresh(company_hosted, second.registration, two["refresh_token"])
    assert rotated.status_code == 200
    assert refresh(company_hosted, second.registration, two["refresh_token"]).status_code == 400
    assert (
        company_hosted.get("/v1/me", headers=bearer(rotated.json()["access_token"])).status_code
        == 401
    )


def test_switching_to_password_clears_company_authorization_and_legacy_helpers_stay_personal(
    company_hosted, company, env
):
    link = linked(company, env)
    SignInService(env.db).set_password(
        env.owner, PasswordInput(username="owner", password=PASSWORD)
    )
    attempt = reviewed(company_hosted, company)
    # Even deliberately equal UUID versions cannot route company access through a personal helper.
    with psycopg.connect(env.admin_dsn) as connection:
        connection.execute(
            "UPDATE mnemion.password_accounts SET version=(SELECT version FROM mnemion.company_links WHERE id=%s) WHERE tenant_id=%s AND principal_id=%s",
            (link["id"], env.owner.tenant_id, env.owner.principal_id),
        )
    with env.db.pool.connection() as connection:
        legacy = connection.execute(
            "SELECT mnemion.local_oauth_consent(%s,%s,%s,%s,%s,%s)",
            (
                token_hash(attempt.ticket),
                ORIGIN + "/",
                ORIGIN + "/mcp",
                token_hash(attempt.review["proof"]),
                token_hash(company_hosted.cookies.get("__Host-mnemion-oauth-browser")),
                token_hash("legacy-code"),
            ),
        ).fetchone()
        assert next(iter(legacy.values())) is None
    approved = redeem(company_hosted, attempt)
    assert approved.status_code == 200, approved.text
    with env.db.pool.connection() as connection:
        for kind, token in (
            ("access", approved.json()["access_token"]),
            ("refresh", approved.json()["refresh_token"]),
        ):
            assert (
                next(
                    iter(
                        connection.execute(
                            "SELECT mnemion.local_oauth_token(%s,%s,%s,%s)",
                            (token_hash(token), kind, ORIGIN + "/", ORIGIN + "/mcp"),
                        )
                        .fetchone()
                        .values()
                    )
                )
                is None
            )
        _, anchor = new_token()
        assert (
            next(
                iter(
                    connection.execute(
                        "SELECT mnemion.local_oauth_exchange(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            token_hash(attempt.code),
                            attempt.registration["client_id"],
                            ORIGIN + "/",
                            ORIGIN + "/mcp",
                            uuid4(),
                            uuid4(),
                            anchor,
                            token_hash("access"),
                            token_hash("refresh"),
                            "Legacy attempt",
                        ),
                    )
                    .fetchone()
                    .values()
                )
            )
            is None
        )
    # Choosing a password after company review deliberately replaces that review.
    switched = reviewed(company_hosted, company)
    password_review = login(company_hosted, switched.ticket, switched.headers)
    assert password_review["authentication"] == "password"
    with psycopg.connect(env.admin_dsn) as connection:
        assert connection.execute(
            "SELECT company_link_id,company_expires_at FROM mnemion.oauth_local_requests WHERE ticket_hash=%s",
            (token_hash(switched.ticket),),
        ).fetchone() == (None, None)
    assert approve(company_hosted, switched).status_code == 409
    switched.review = password_review
    assert (
        company.client.delete(
            "/v1/sign-in/company/links/" + link["id"], headers=bearer(env.token)
        ).status_code
        == 200
    )
    password_tokens = redeem(company_hosted, switched)
    assert password_tokens.status_code == 200, password_tokens.text


def test_removed_host_provider_rejects_existing_company_agent_tokens(company_hosted, company, env):
    linked(company, env)
    attempt = reviewed(company_hosted, company)
    tokens = redeem(company_hosted, attempt).json()
    for configuration in (
        CompanyIdentity([]),
        CompanyIdentity([replace(company.provider, session_seconds=900)]),
    ):
        with TestClient(
            create_app(
                env.db,
                env.embedder,
                mcp_enabled=False,
                hosted_oauth_settings=HostedOAuthSettings.for_workspace(
                    ORIGIN, env.owner.tenant_id
                ),
                company_identity=configuration,
            ),
            base_url=ORIGIN,
        ) as changed:
            assert changed.get("/v1/me", headers=bearer(tokens["access_token"])).status_code == 401
            assert (
                refresh(changed, attempt.registration, tokens["refresh_token"]).status_code == 400
            )


def test_recovery_cannot_restore_company_agent_authority_or_pending_consent(
    company_hosted, company, env, postgres, pg_bin, tmp_path
):
    linked(company, env)
    attempt = reviewed(company_hosted, company)
    issued = redeem(company_hosted, attempt)
    assert issued.status_code == 200
    tokens = issued.json()
    pending = reviewed(company_hosted, company)
    _, _, ticket, headers = start(company_hosted)
    unfinished = begin(company_hosted, company, ticket, headers)
    archive, ledger, credentials = (
        tmp_path / name for name in ("company-oauth.mnemion", "ledger.json", "recovery.json")
    )
    recovery.create_backup(env.admin_dsn, archive, pg_bin=pg_bin)
    recovery.export_ledger(env.admin_dsn, ledger)
    name = "company_oauth_recovery_" + uuid4().hex
    database = None
    try:
        recovery.restore_backup(
            env.admin_dsn,
            archive,
            database_name=name,
            deletion_ledger=ledger,
            credentials_output=credentials,
            pg_bin=pg_bin,
        )
        database = Database(make_conninfo(postgres[1], dbname=name))
        database.open()
        with TestClient(
            create_app(
                database,
                env.embedder,
                mcp_enabled=False,
                hosted_oauth_settings=HostedOAuthSettings.for_workspace(
                    ORIGIN, env.owner.tenant_id
                ),
                company_identity=company.identity,
            ),
            base_url=ORIGIN,
        ) as restored:
            restored.cookies.update(company_hosted.cookies)
            assert restored.get("/v1/me", headers=bearer(tokens["access_token"])).status_code == 401
            assert (
                refresh(restored, attempt.registration, tokens["refresh_token"]).status_code == 400
            )
            assert approve(restored, pending).status_code == 409
            assert (
                restored.post(
                    "/oauth/consent/company/finish", headers=headers, json=unfinished
                ).status_code
                == 409
            )
    finally:
        if database:
            database.close()
        with psycopg.connect(env.admin_dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
