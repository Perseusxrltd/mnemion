"""Real database/session checks with a signed, deterministic OIDC protocol peer."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import secrets
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
import httpx
import jwt
import psycopg
import pytest

from mnemion.service.api import create_app
from mnemion.service.company_identity import CompanyIdentity, CompanyProvider, challenge
from mnemion.service.company_sign_in import CompanyFinish, CompanySignIn, CompanyStart
from mnemion.service.errors import ServiceError
from mnemion.service.models import GrantInput, PrincipalInput
from mnemion.service.sign_in import InvitationInput, SignInService

ORIGIN = "https://memory.example.test"
ISSUER = "https://identity.example.test/realms/company"
CALLBACK = "http://127.0.0.1:45123/mnemion-company/" + "x" * 43


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def company(env, signing_key):
    provider = CompanyProvider(
        env.owner.tenant_id,
        "company",
        "Company account",
        ISSUER,
        ISSUER + "/authorize",
        ISSUER + "/token",
        ISSUER + "/keys",
        "mnemion-desktop",
    )
    state = SimpleNamespace(
        provider=provider, codes={}, claims={}, calls=[], subject="stable-person-123"
    )
    public_key = jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
    public_key["kid"] = "fixture-key"

    def peer(request):
        state.calls.append((request.method, str(request.url)))
        if str(request.url) == provider.jwks_url:
            result = {"keys": [public_key]}
        else:
            assert str(request.url) == provider.token_url and request.method == "POST"
            form = parse_qs(request.content.decode())
            flow = state.codes[form["code"][0]]
            assert challenge(form["code_verifier"][0]) == flow["code_challenge"][0]
            assert form["redirect_uri"] == [ORIGIN + "/company/callback"]
            claims = {
                "iss": provider.issuer,
                "aud": provider.client_id,
                "sub": state.subject,
                "exp": int(time.time()) + 300,
                "iat": int(time.time()),
                "nonce": flow["nonce"][0],
            }
            claims.update(state.claims)
            result = {
                "id_token": jwt.encode(
                    claims, signing_key, algorithm="RS256", headers={"kid": "fixture-key"}
                )
            }
        return httpx.Response(
            200,
            stream=httpx.ByteStream(json.dumps(result).encode()),
            headers={"Content-Type": "application/json"},
        )

    state.identity = CompanyIdentity([provider], transport=httpx.MockTransport(peer))
    state.service = CompanySignIn(env.db, state.identity, ORIGIN)
    with TestClient(
        create_app(
            env.db,
            env.embedder,
            mcp_enabled=False,
            public_url=ORIGIN,
            company_identity=state.identity,
        ),
        base_url=ORIGIN,
    ) as client:
        state.client = client
        yield state


def bearer(token):
    return {"Authorization": "Bearer " + token}


def linked(company, env, person=None):
    response = company.client.post(
        "/v1/sign-in/company/links",
        headers=bearer(env.token),
        json={
            "principal_id": str(person or env.owner.principal_id),
            "provider_id": "company",
            "subject": company.subject,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def start(company, env, **options):
    transport = options.get("transport", "native")
    command = {
        "workspace_id": str(env.owner.tenant_id),
        "provider_id": "company",
        "device_name": "Company fixture",
        "transport": transport,
        **({"callback_uri": CALLBACK} if transport == "native" else {}),
        **options,
    }
    response = company.client.post(
        "/v1/sign-in/company/start",
        json=command,
        headers={"Origin": ORIGIN} if transport == "browser" else {},
    )
    assert response.status_code == 200, response.text
    flow = response.json()
    query = parse_qs(urlsplit(flow["authorization_url"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == [challenge(flow["code_verifier"])]
    assert query["scope"] == ["openid"]
    code = secrets.token_urlsafe(24)
    company.codes[code] = query
    return {
        "state": flow["state"],
        "code_verifier": flow["code_verifier"],
        "code": code,
        "transport": transport,
    }


def finish(company, flow):
    return company.client.post(
        "/v1/sign-in/company/finish",
        json=flow,
        headers={"Origin": ORIGIN} if flow["transport"] == "browser" else {},
    )


def test_explicit_company_login_session_refresh_revocation_and_pinning(company, env):
    link = linked(company, env)
    flow = start(company, env)
    response = finish(company, flow)
    assert response.status_code == 200, response.text
    session = response.json()
    assert (
        session["principal_id"] == str(env.owner.principal_id)
        and session["persistence"] == "native"
    )
    assert company.client.get("/v1/me", headers=bearer(session["access_token"])).status_code == 200
    with pytest.raises(ServiceError):
        env.db.authenticate(session["access_token"])
    identity = env.db.authenticate(
        session["access_token"], company_policies=company.identity.policies
    )
    assert finish(company, flow).status_code == 401
    with psycopg.connect(env.admin_dsn) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.password_accounts WHERE tenant_id=%s",
                (env.owner.tenant_id,),
            ).fetchone()[0]
            == 0
        )
    refreshed = company.client.post(
        "/v1/sign-in/refresh",
        json={
            "workspace_id": session["tenant_id"],
            "session_id": session["session_id"],
            "transport": "native",
            "refresh_token": session["refresh_token"],
        },
    )
    assert refreshed.status_code == 200, refreshed.text
    advanced = refreshed.json()
    assert (
        advanced["session_id"] == session["session_id"]
        and advanced["expires_at"] == session["expires_at"]
    )
    assert company.client.get("/v1/me", headers=bearer(session["access_token"])).status_code == 401
    assert (
        company.client.delete(
            "/v1/sign-in/company/links/" + link["id"], headers=bearer(advanced["access_token"])
        ).status_code
        == 200
    )
    assert company.client.get("/v1/me", headers=bearer(advanced["access_token"])).status_code == 401
    with pytest.raises(ServiceError), env.db.transaction(identity):
        pass
    assert company.client.get("/v1/me", headers=bearer(env.token)).status_code == 200


def test_unknown_company_identity_never_auto_provisions_from_email_or_roles(company, env):
    company.claims = {
        "email": "administrator@example.test",
        "email_verified": True,
        "roles": ["admin"],
    }
    assert finish(company, start(company, env)).status_code == 401
    assert (
        company.client.get("/v1/sign-in/company/links", headers=bearer(env.token)).json()["items"]
        == []
    )


def test_invitation_creates_company_access_with_exact_existing_grants(company, env):
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Invited employee", kind="human")
    )
    person_id = UUID(person["id"])
    env.identities.grant(env.owner, env.space, person_id, GrantInput(role="reader"))
    invitation = SignInService(env.db).create_invitation(
        env.owner, InvitationInput(principal_id=person_id)
    )
    flow = start(company, env, invitation=invitation["invitation_token"])
    response = finish(company, flow)
    assert response.status_code == 200, response.text
    tokens = response.json()
    assert tokens["principal_id"] == person["id"]
    assert (
        company.client.get("/v1/spaces", headers=bearer(tokens["access_token"])).json()["items"][0][
            "role"
        ]
        == "reader"
    )
    assert (
        company.client.post(
            "/v1/spaces", headers=bearer(tokens["access_token"]), json={"name": "Unauthorized"}
        ).status_code
        == 403
    )
    assert (
        company.client.post(
            "/v1/sign-in/company/start",
            json={
                "workspace_id": str(env.owner.tenant_id),
                "provider_id": "company",
                "device_name": "Reuse",
                "transport": "native",
                "callback_uri": CALLBACK,
                "invitation": invitation["invitation_token"],
            },
        ).status_code
        == 401
    )


def test_invitation_grants_are_rechecked_after_provider_login(company, env):
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Changed employee", kind="human")
    )
    person_id = UUID(person["id"])
    invitation = SignInService(env.db).create_invitation(
        env.owner, InvitationInput(principal_id=person_id)
    )
    flow = start(company, env, invitation=invitation["invitation_token"])
    env.identities.grant(env.owner, env.space, person_id, GrantInput(role="reader"))
    assert finish(company, flow).status_code == 401
    assert (
        company.client.get("/v1/sign-in/company/links", headers=bearer(env.token)).json()["items"]
        == []
    )


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://wrong.example.test"},
        {"aud": "another-client"},
        {"nonce": "different-browser"},
        {"exp": 1},
        {"iat": int(time.time()) + 3600},
        {"iat": int(time.time()) - 3600},
        {"sub": ""},
        {"azp": "other-client"},
        {"aud": ["mnemion-desktop", "other-client"]},
        {"at_hash": "unverified"},
        {"exp": True},
        {"nbf": int(time.time()) + 3600},
    ],
)
def test_invalid_oidc_assertions_fail_closed(company, env, claims):
    linked(company, env)
    company.claims = claims
    assert finish(company, start(company, env)).status_code == 401


def test_wrong_verifier_does_not_claim_the_request_and_callback_is_bound(company, env):
    linked(company, env)
    flow = start(company, env)
    assert finish(company, {**flow, "code_verifier": "z" * 43}).status_code == 401
    response = company.client.get(
        "/company/callback",
        params={"state": flow["state"], "code": flow["code"], "iss": ISSUER},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert (
        response.headers["location"].startswith(CALLBACK + "?")
        and response.headers["referrer-policy"] == "no-referrer"
    )
    assert finish(company, flow).status_code == 200


def test_browser_origin_protection_and_remembered_cookie(company, env):
    linked(company, env)
    flow = start(company, env, transport="browser", remember=True)
    assert company.client.post("/v1/sign-in/company/finish", json=flow).status_code == 403
    assert (
        company.client.post(
            "/v1/sign-in/company/finish",
            json=flow,
            headers={"Origin": "https://foreign.example.test"},
        ).status_code
        == 403
    )
    callback = company.client.get(
        "/company/callback", params={"state": flow["state"], "code": flow["code"]}
    )
    assert (
        callback.status_code == 200
        and "frame-ancestors 'none'" in callback.headers["content-security-policy"]
    )
    tokens = finish(company, flow).json()
    assert tokens["persistence"] == "cookie" and tokens["refresh_token"] is None
    csrf = tokens["csrf_token"]
    refreshed = company.client.post(
        "/v1/sign-in/refresh",
        headers={"Origin": ORIGIN, "X-Mnemion-CSRF": csrf},
        json={
            "workspace_id": tokens["tenant_id"],
            "session_id": tokens["session_id"],
            "transport": "browser",
        },
    )
    assert refreshed.status_code == 200, refreshed.text


def test_refresh_reuse_revokes_company_session_family(company, env):
    linked(company, env)
    tokens = finish(company, start(company, env)).json()
    command = {
        "workspace_id": tokens["tenant_id"],
        "session_id": tokens["session_id"],
        "transport": "native",
        "refresh_token": tokens["refresh_token"],
    }
    assert company.client.post("/v1/sign-in/refresh", json=command).status_code == 200
    assert company.client.post("/v1/sign-in/refresh", json=command).status_code == 401
    rows = company.client.get("/v1/sign-in/sessions", headers=bearer(env.token)).json()["items"]
    assert next(row for row in rows if row["id"] == tokens["session_id"])["revoked_at"] is not None


def test_link_cannot_be_reassigned_or_authorized_by_another_policy(company, env):
    linked(company, env)
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Different person", kind="human")
    )
    response = company.client.post(
        "/v1/sign-in/company/links",
        headers=bearer(env.token),
        json={"principal_id": person["id"], "provider_id": "company", "subject": company.subject},
    )
    assert response.status_code == 409
    tokens = finish(company, start(company, env)).json()
    changed = replace(company.provider, client_id="different-company-client")
    with pytest.raises(ServiceError):
        env.db.authenticate(tokens["access_token"], company_policies=(changed.policy_hash,))
    with pytest.raises(ServiceError):
        SignInService(env.db).refresh(
            tokens["refresh_token"], transport="native", workspace=env.owner.tenant_id
        )


def test_concurrent_invitation_can_create_only_one_company_session(company, env):
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Concurrent employee", kind="human")
    )
    invitation = SignInService(env.db).create_invitation(
        env.owner, InvitationInput(principal_id=UUID(person["id"]))
    )
    flows = [
        CompanyFinish(**start(company, env, invitation=invitation["invitation_token"]))
        for _ in range(2)
    ]
    for flow in flows:
        company.service.claim(flow)

    def accept(flow):
        try:
            return company.service.issue(flow, company.provider, company.subject)
        except ServiceError:
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(accept, flows))
    assert sum(result is not None for result in results) == 1


@pytest.mark.parametrize(
    "callback",
    [
        "https://elsewhere.example.test/callback",
        "http://localhost:45123/mnemion-company/" + "x" * 43,
        "http://127.0.0.1:45123/mnemion-company/" + "x" * 43 + "?destination=remote",
        "file:///tmp/callback",
    ],
)
def test_native_callback_rejects_remote_and_ambiguous_destinations(env, callback):
    with pytest.raises(ValueError):
        CompanyStart(
            workspace_id=env.owner.tenant_id,
            provider_id="company",
            device_name="Native",
            transport="native",
            callback_uri=callback,
        )
