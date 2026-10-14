"""Real SDK authorization-code exchange, personal consent and revocable sessions."""

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import secrets
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from fastapi.testclient import TestClient
import psycopg
import pytest

from mnemion.service.api import create_app
from mnemion.service.models import GrantInput, KeyInput, PrincipalInput
from mnemion.service.sign_in import InvitationInput, PasswordInput, SignInService

ORIGIN = "https://memory.example.test"
CALLBACK = "https://agent.example.test/callback"
PASSWORD = "birch lantern cocoa summit calypso"


@pytest.fixture
def hosted(env, monkeypatch):
    monkeypatch.setenv("MNEMION_PUBLIC_URL", ORIGIN)
    monkeypatch.setenv("MNEMION_OAUTH_BUILTIN", "1")
    monkeypatch.setenv("MNEMION_OAUTH_TENANT_ID", str(env.owner.tenant_id))
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute("DELETE FROM mnemion.sign_in_attempts")
        conn.execute("DELETE FROM mnemion.oauth_local_attempts")
    SignInService(env.db).set_password(
        env.owner, PasswordInput(username="owner", password=PASSWORD)
    )
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False), base_url=ORIGIN) as client:
        yield client


def start(client):
    response = client.post(
        "/oauth/register",
        json={
            "client_name": "Fixture agent",
            "redirect_uris": [CALLBACK],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "scope": "mnemion:access",
        },
    )
    assert response.status_code == 201, response.text
    registration = response.json()
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    response = client.get(
        "/oauth/authorize",
        params={
            "client_id": registration["client_id"],
            "redirect_uri": CALLBACK,
            "response_type": "code",
            "scope": "mnemion:access",
            "state": "opaque client state",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": ORIGIN + "/mcp",
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303), response.text
    ticket = parse_qs(urlsplit(response.headers["location"]).fragment)["request"][0]
    response = client.post(
        "/oauth/consent/request", headers={"Origin": ORIGIN}, json={"ticket": ticket}
    )
    assert response.status_code == 200, response.text
    headers = {"Origin": ORIGIN, "X-Mnemion-Consent-CSRF": response.json()["csrf"]}
    return registration, verifier, ticket, headers


def login(client, ticket, headers, username="owner"):
    response = client.post(
        "/oauth/consent/login",
        headers=headers,
        json={
            "ticket": ticket,
            "username": username,
            "password": PASSWORD,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def approve(client, ticket, headers, username="owner"):
    result = login(client, ticket, headers, username)
    response = client.post(
        "/oauth/consent/approve", headers=headers, json={"ticket": ticket, "proof": result["proof"]}
    )
    assert response.status_code == 200, response.text
    parameters = parse_qs(urlsplit(response.json()["redirect"]).query)
    assert parameters["iss"] == [ORIGIN + "/"] and parameters["state"] == ["opaque client state"]
    return parameters["code"][0]


def exchange(client, registration, verifier, code, **changes):
    return client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": registration["client_id"],
            "redirect_uri": CALLBACK,
            "code": code,
            "code_verifier": verifier,
            "resource": ORIGIN + "/mcp",
            **changes,
        },
    )


def bearer(value):
    return {"Authorization": "Bearer " + value}


def test_discovery_personal_consent_exchange_refresh_and_explicit_revocation(hosted, env):
    protected = hosted.get("/.well-known/oauth-protected-resource/mcp").json()
    metadata = hosted.get("/.well-known/oauth-authorization-server").json()
    assert protected["resource"] == ORIGIN + "/mcp"
    assert metadata["issuer"] == ORIGIN + "/" and metadata["code_challenge_methods_supported"] == [
        "S256"
    ]
    registration, verifier, ticket, headers = start(hosted)
    code = approve(hosted, ticket, headers)
    response = exchange(hosted, registration, verifier, code)
    assert response.status_code == 200, response.text
    tokens = response.json()
    assert tokens["access_token"].startswith("mnmo_") and tokens["refresh_token"].startswith(
        "mnmr_"
    )
    who = hosted.get("/v1/me", headers=bearer(tokens["access_token"]))
    assert who.status_code == 200, who.text
    assert who.json()["principal_id"] == str(env.owner.principal_id)
    refreshed = hosted.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": registration["client_id"],
            "refresh_token": tokens["refresh_token"],
            "resource": ORIGIN + "/mcp",
        },
    )
    assert refreshed.status_code == 200, refreshed.text
    current = refreshed.json()
    assert hosted.get("/v1/me", headers=bearer(tokens["access_token"])).status_code == 401
    connections = hosted.get("/v1/oauth/connections", headers=bearer(env.token)).json()[
        "connections"
    ]
    assert len(connections) == 1 and connections[0]["client_id"] == registration["client_id"]
    assert (
        hosted.post(
            "/v1/oauth/connections/" + connections[0]["session_id"] + "/revoke",
            headers=bearer(env.token),
        ).status_code
        == 200
    )
    assert hosted.get("/v1/me", headers=bearer(current["access_token"])).status_code == 401


def refresh(client, registration, credential, **changes):
    return client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": registration["client_id"],
            "refresh_token": credential,
            "resource": ORIGIN + "/mcp",
            **changes,
        },
    )


def test_exchange_requires_original_resource_client_callback_and_pkce(hosted):
    registration, verifier, ticket, headers = start(hosted)
    code = approve(hosted, ticket, headers)
    other, *_ = start(hosted)
    for changes in (
        {"resource": "https://different.example.test/mcp"},
        {"redirect_uri": "https://different.example.test/callback"},
        {"code_verifier": "x" * 43},
        {"client_id": other["client_id"]},
    ):
        response = exchange(hosted, registration, verifier, code, **changes)
        assert response.status_code == 400, response.text
        assert isinstance(response.json()["error"], str)
    accepted = exchange(hosted, registration, verifier, code)
    assert accepted.status_code == 200, accepted.text
    token = accepted.json()["refresh_token"]
    rejected = refresh(hosted, registration, token, resource="https://different.example.test/mcp")
    assert rejected.status_code == 400 and rejected.json()["error"] == "invalid_target"
    assert refresh(hosted, registration, token).status_code == 200


def test_browser_origin_csrf_and_proof_are_bound_to_the_reviewing_browser(hosted):
    _, _, ticket, headers = start(hosted)
    body = {"ticket": ticket, "username": "owner", "password": PASSWORD}
    for changed in (
        {"Origin": "https://unrelated.example.test"},
        {"Origin": ORIGIN},
        {**headers, "Sec-Fetch-Site": "cross-site"},
        {**headers, "X-Mnemion-Consent-CSRF": "x" * 64},
    ):
        assert hosted.post("/oauth/consent/login", headers=changed, json=body).status_code == 403
    reviewed = login(hosted, ticket, headers)
    assert reviewed["permissions"]["name"] == "Owner"
    assert reviewed["permissions"]["workspace_name"] == "Test team"
    with TestClient(hosted.app, base_url=ORIGIN) as second:
        details = second.post(
            "/oauth/consent/request", headers={"Origin": ORIGIN}, json={"ticket": ticket}
        )
        swapped = second.post(
            "/oauth/consent/approve",
            headers={
                "Origin": ORIGIN,
                "X-Mnemion-Consent-CSRF": details.json()["csrf"],
            },
            json={"ticket": ticket, "proof": reviewed["proof"]},
        )
        assert swapped.status_code == 409
    accepted = hosted.post(
        "/oauth/consent/approve",
        headers=headers,
        json={"ticket": ticket, "proof": reviewed["proof"]},
    )
    assert accepted.status_code == 200, accepted.text


def test_permission_changes_require_a_new_review_before_approval_and_exchange(hosted, env):
    registration, verifier, ticket, headers = start(hosted)
    reviewed = login(hosted, ticket, headers)
    env.identities.grant(env.owner, env.space, env.owner.principal_id, GrantInput(role="reader"))
    result = hosted.post(
        "/oauth/consent/approve",
        headers=headers,
        json={"ticket": ticket, "proof": reviewed["proof"]},
    )
    assert result.status_code == 409
    code = approve(hosted, ticket, headers)
    env.identities.grant(
        env.owner, env.space, env.owner.principal_id, GrantInput(role="contributor")
    )
    result = exchange(hosted, registration, verifier, code)
    assert result.status_code == 400 and result.json()["error"] == "invalid_grant"


def test_code_and_refresh_replay_revoke_only_the_compromised_connection(hosted, env):
    registration, verifier, ticket, headers = start(hosted)
    code = approve(hosted, ticket, headers)
    tokens = exchange(hosted, registration, verifier, code).json()
    assert exchange(hosted, registration, verifier, code).status_code == 400
    assert hosted.get("/v1/me", headers=bearer(tokens["access_token"])).status_code == 401
    registration, verifier, ticket, headers = start(hosted)
    tokens = exchange(hosted, registration, verifier, approve(hosted, ticket, headers)).json()
    renewed = refresh(hosted, registration, tokens["refresh_token"])
    assert renewed.status_code == 200, renewed.text
    assert refresh(hosted, registration, tokens["refresh_token"]).status_code == 400
    assert hosted.get("/v1/me", headers=bearer(renewed.json()["access_token"])).status_code == 401
    assert hosted.get("/v1/me", headers=bearer(env.token)).status_code == 200


def test_concurrent_code_redemption_creates_at_most_one_session(hosted, env):
    registration, verifier, ticket, headers = start(hosted)
    code = approve(hosted, ticket, headers)
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(lambda _: exchange(hosted, registration, verifier, code), range(2))
        )
    assert sorted(response.status_code for response in outcomes) == [200, 400]
    connections = hosted.get("/v1/oauth/connections", headers=bearer(env.token)).json()[
        "connections"
    ]
    assert len(connections) == 1 and connections[0]["revoked_at"]


def test_member_connection_keeps_space_authority_and_cannot_revoke_another_person(hosted, env):
    member = env.identities.create_principal(env.owner, PrincipalInput(name="Member", kind="human"))
    member_id = UUID(member["id"])
    key = env.identities.create_key(env.owner, member_id, KeyInput(name="Fixture recovery"))
    identity = env.db.authenticate(key["api_key"])
    env.identities.grant(env.owner, env.space, member_id, GrantInput(role="reader"))
    SignInService(env.db).set_password(
        identity, PasswordInput(username="member", password=PASSWORD)
    )
    owner_reg, verifier, ticket, headers = start(hosted)
    owner_tokens = exchange(hosted, owner_reg, verifier, approve(hosted, ticket, headers)).json()
    registration, verifier, ticket, headers = start(hosted)
    member_tokens = exchange(
        hosted, registration, verifier, approve(hosted, ticket, headers, "member")
    ).json()
    own = hosted.get("/v1/oauth/connections", headers=bearer(member_tokens["access_token"])).json()[
        "connections"
    ]
    assert len(own) == 1 and own[0]["principal_id"] == str(member_id)
    everyone = hosted.get("/v1/oauth/connections", headers=bearer(env.token)).json()["connections"]
    other = next(row for row in everyone if row["principal_id"] != str(member_id))
    assert (
        hosted.post(
            "/v1/oauth/connections/" + other["session_id"] + "/revoke",
            headers=bearer(member_tokens["access_token"]),
        ).status_code
        == 404
    )
    denied = hosted.post(
        "/v1/spaces", headers=bearer(member_tokens["access_token"]), json={"name": "Unauthorized"}
    )
    assert denied.status_code == 403
    assert hosted.get("/v1/me", headers=bearer(owner_tokens["access_token"])).status_code == 200
    assert (
        hosted.post(
            "/v1/oauth/connections/" + own[0]["session_id"] + "/revoke", headers=bearer(env.token)
        ).status_code
        == 200
    )
    assert hosted.get("/v1/me", headers=bearer(member_tokens["access_token"])).status_code == 401


def test_password_reset_invalidates_pending_consent_and_existing_app_tokens(hosted, env):
    registration, verifier, ticket, headers = start(hosted)
    tokens = exchange(hosted, registration, verifier, approve(hosted, ticket, headers)).json()
    _, _, pending, pending_headers = start(hosted)
    reviewed = login(hosted, pending, pending_headers)
    SignInService(env.db).create_invitation(
        env.owner, InvitationInput(principal_id=env.owner.principal_id, purpose="reset")
    )
    assert (
        hosted.post(
            "/oauth/consent/approve",
            headers=pending_headers,
            json={"ticket": pending, "proof": reviewed["proof"]},
        ).status_code
        == 409
    )
    assert hosted.get("/v1/me", headers=bearer(tokens["access_token"])).status_code == 401
    assert refresh(hosted, registration, tokens["refresh_token"]).status_code == 400


def test_cancel_returns_original_state_and_issuer_without_a_code(hosted):
    _, _, ticket, headers = start(hosted)
    response = hosted.post("/oauth/consent/cancel", headers=headers, json={"ticket": ticket})
    assert response.status_code == 200, response.text
    target = urlsplit(response.json()["redirect"])
    fields = parse_qs(target.query)
    assert target.scheme + "://" + target.netloc + target.path == CALLBACK
    assert fields == {
        "error": ["access_denied"],
        "state": ["opaque client state"],
        "iss": [ORIGIN + "/"],
    }
    assert (
        hosted.post(
            "/oauth/consent/request", headers={"Origin": ORIGIN}, json={"ticket": ticket}
        ).status_code
        == 409
    )


def test_registration_and_transport_reject_unsafe_or_ambiguous_inputs(hosted):
    for metadata in (
        {"grant_types": []},
        {"grant_types": ["refresh_token"]},
        {"response_types": []},
        {"response_types": ["token"]},
    ):
        response = hosted.post(
            "/oauth/register",
            json={
                "redirect_uris": [CALLBACK],
                "token_endpoint_auth_method": "none",
                **metadata,
            },
        )
        assert response.status_code == 400, response.text
    for callback in (
        "http://public.example.test/callback",
        "https://user:password@example.test/callback",
        "https://*.example.test/callback",
        CALLBACK + "#fragment",
    ):
        response = hosted.post(
            "/oauth/register",
            json={"redirect_uris": [callback], "token_endpoint_auth_method": "none"},
        )
        assert response.status_code == 400, response.text
    assert (
        hosted.post(
            "/oauth/register",
            json={"redirect_uris": [CALLBACK], "token_endpoint_auth_method": "client_secret_post"},
        ).status_code
        == 400
    )
    duplicate = hosted.post(
        "/oauth/token",
        content="grant_type=refresh_token&client_id=a&client_id=b",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert duplicate.status_code == 400 and duplicate.json()["error"] == "invalid_request"
    oversized = hosted.post(
        "/oauth/register", content=b"x" * 32769, headers={"Content-Type": "application/json"}
    )
    assert oversized.status_code == 413 and oversized.json()["error"] == "invalid_request"
    malformed = hosted.post("/oauth/token", json={"grant_type": "authorization_code"})
    assert malformed.status_code == 415 and malformed.json()["error"] == "invalid_request"


def test_hosted_access_authenticates_real_mcp_discovery_and_rejects_revoked_tokens(hosted, env):
    registration, verifier, ticket, headers = start(hosted)
    tokens = exchange(hosted, registration, verifier, approve(hosted, ticket, headers)).json()
    request_headers = {
        **bearer(tokens["access_token"]),
        "Accept": "application/json, text/event-stream",
    }
    with TestClient(create_app(env.db, env.embedder), base_url=ORIGIN) as gateway:
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        result = gateway.post("/mcp", headers=request_headers, json=request)
        assert result.status_code == 200, result.text
        assert any(tool["name"] == "memory_search" for tool in result.json()["result"]["tools"])
        current = gateway.get("/v1/oauth/connections", headers=bearer(env.token)).json()[
            "connections"
        ][0]
        assert (
            gateway.post(
                "/v1/oauth/connections/" + current["session_id"] + "/revoke",
                headers=bearer(env.token),
            ).status_code
            == 200
        )
        rejected = gateway.post("/mcp", headers=request_headers, json=request)
        assert rejected.status_code == 401
        assert "/.well-known/oauth-protected-resource/mcp" in rejected.headers["WWW-Authenticate"]


def test_disaster_recovery_does_not_reactivate_oauth_tokens_or_pending_consent(
    hosted, env, postgres, pg_bin, tmp_path
):
    from uuid import uuid4
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    from mnemion.service import recovery
    from mnemion.service.db import Database

    registration, verifier, ticket, headers = start(hosted)
    tokens = exchange(hosted, registration, verifier, approve(hosted, ticket, headers)).json()
    _, _, pending, pending_headers = start(hosted)
    reviewed = login(hosted, pending, pending_headers)
    archive, ledger, credentials = (
        tmp_path / name for name in ("oauth.mnemion", "ledger.json", "recovery.json")
    )
    recovery.create_backup(env.admin_dsn, archive, pg_bin=pg_bin)
    recovery.export_ledger(env.admin_dsn, ledger)
    name = "oauth_recovery_" + uuid4().hex
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
        try:
            with TestClient(
                create_app(database, env.embedder, mcp_enabled=False), base_url=ORIGIN
            ) as restored:
                assert (
                    restored.get("/v1/me", headers=bearer(tokens["access_token"])).status_code
                    == 401
                )
                assert refresh(restored, registration, tokens["refresh_token"]).status_code == 400
                restored.cookies.update(hosted.cookies)
                assert (
                    restored.post(
                        "/oauth/consent/approve",
                        headers=pending_headers,
                        json={"ticket": pending, "proof": reviewed["proof"]},
                    ).status_code
                    == 409
                )
        finally:
            database.close()
    finally:
        with psycopg.connect(env.admin_dsn, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
