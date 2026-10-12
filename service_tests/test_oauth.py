"""Protocol fixtures plus real PostgreSQL/RLS; not live provider acceptance."""

import asyncio
import json
import time
from dataclasses import replace
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from mnemion.service.admin import bootstrap_tenant
from mnemion.service.api import create_app
from mnemion.service.errors import ServiceError
from mnemion.service.models import GrantInput, KeyInput, MemoryInput, PrincipalInput
from mnemion.service.oauth import (
    MAX_RESPONSE_BYTES,
    OAUTH_SCOPE,
    OAuthSettings,
    OAuthVerifier,
)
from mnemion.service.oauth_api import OAuthBindingInput, OAuthBindings


def settings(**changes):
    return OAuthSettings(
        **{
            "issuer": "https://identity.example.test/realm",
            "introspection_url": "https://identity.example.test/introspect",
            "resource": "https://memory.example.test/mcp",
            "client_id": "resource-server",
            "client_secret": "fixture-secret-never-published",
            "tenant_id": UUID("00000000-0000-4000-8000-000000000001"),
            **changes,
        }
    )


def claims(**changes):
    return {
        "active": True,
        "iss": settings().issuer,
        "aud": settings().resource,
        "sub": "person-immutable-123",
        "client_id": "https://client.example.test/oauth.json",
        "scope": OAUTH_SCOPE,
        "exp": time.time() + 300,
        **changes,
    }


def verifier(result=None, calls=None, *, tenant_id=None):
    def respond(request):
        if calls is not None:
            calls.append(request)
        body = result if result is not None else claims()
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(body).encode()))

    config = settings(**({"tenant_id": tenant_id} if tenant_id else {}))
    return OAuthVerifier(config, transport=httpx.MockTransport(respond))


@pytest.mark.parametrize(
    "field,value",
    [
        ("issuer", "http://identity.example.test"),
        ("issuer", "https://user:password@identity.example.test"),
        ("introspection_url", "https://identity.example.test/?token=secret"),
        ("introspection_url", "https://identity.example.test/#fragment"),
        ("introspection_url", "https://identity.example.test/\nheader"),
        ("introspection_url", 'https://identity.example.test/"quote'),
        ("resource", "https://memory.example.test/arbitrary-path"),
        ("client_secret", ""),
        ("tenant_id", "not-a-UUID"),
    ],
)
def test_configuration_rejects_unsafe_or_ambiguous_values(field, value):
    with pytest.raises(ValueError):
        settings(**{field: value})


def test_configuration_is_opt_in_complete_and_does_not_disclose_secret(tmp_path, monkeypatch):
    for name in ("ISSUER", "INTROSPECTION_URL", "CLIENT_ID", "CLIENT_SECRET_FILE", "TENANT_ID"):
        monkeypatch.delenv("MNEMION_OAUTH_" + name, raising=False)
    assert OAuthSettings.from_environment() is None
    monkeypatch.setenv("MNEMION_OAUTH_ISSUER", settings().issuer)
    with pytest.raises(ValueError, match="OAuth requires"):
        OAuthSettings.from_environment()
    secret_file = tmp_path / "secret"
    secret_file.write_text(settings().client_secret + "\n")
    monkeypatch.setenv("MNEMION_OAUTH_INTROSPECTION_URL", settings().introspection_url)
    monkeypatch.setenv("MNEMION_OAUTH_CLIENT_ID", settings().client_id)
    monkeypatch.setenv("MNEMION_OAUTH_TENANT_ID", str(settings().tenant_id))
    monkeypatch.setenv("MNEMION_OAUTH_CLIENT_SECRET_FILE", str(secret_file))
    monkeypatch.setenv("MNEMION_PUBLIC_URL", "https://memory.example.test/")
    configured = OAuthSettings.from_environment()
    assert configured == settings()
    assert configured.client_secret not in repr(configured)
    secret_file.write_text("x" * 5000)
    with pytest.raises(ValueError):
        OAuthSettings.from_environment()


@pytest.mark.parametrize(
    "changes",
    [
        {"active": False},
        {"active": 1},
        {"active": "true"},
        {"iss": "https://wrong.example.test"},
        {"iss": None},
        {"aud": "https://different-resource.example.test/mcp"},
        {"aud": [settings().resource, 123]},
        {"aud": None},
        {"resource": "https://wrong.example.test/mcp"},
        {"exp": time.time() - 1},
        {"exp": None},
        {"exp": True},
        {"exp": float("nan")},
        {"exp": float("inf")},
        {"exp": 10**1000},
        {"nbf": time.time() + 300},
        {"nbf": "0"},
        {"iat": time.time() + 300},
        {"sub": ""},
        {"sub": "a\nb"},
        {"sub": "x" * 256},
        {"client_id": None},
        {"client_id": " "},
        {"client_id": "x" * 2049},
        {"token_type": "id_token"},
        {"scope": None},
        {"scope": [OAUTH_SCOPE]},
    ],
)
def test_invalid_claims_are_rejected_without_claims_in_error(changes):
    with pytest.raises(ServiceError) as caught:
        verifier().validate(claims(**changes))
    assert caught.value.status == 401
    assert settings().issuer not in str(caught.value)


def test_scope_and_exact_identity_are_checked_and_external_roles_ignored():
    with pytest.raises(ServiceError) as caught:
        verifier().validate(claims(scope="openid unrelated"))
    assert caught.value.status == 403 and caught.value.code == "insufficient_scope"
    validated = verifier().validate(
        claims(
            aud=["other-resource", settings().resource],
            resource=settings().resource,
            scope="openid " + OAUTH_SCOPE,
            token_type="bearer",
            nbf=time.time() - 1,
            tenant_id=str(uuid4()),
            administrator=True,
            roles=["administrator"],
        )
    )
    assert validated.subject == claims()["sub"]
    assert not hasattr(validated, "administrator")
    assert validated.tenant_id == settings().tenant_id


def test_introspection_uses_body_with_no_cache_and_never_sends_a_url_bearer():
    calls = []
    auth = verifier(calls=calls)

    async def check():
        await auth.verify("private-fixture-token")
        await auth.verify("private-fixture-token")

    asyncio.run(check())
    assert len(calls) == 2
    for request in calls:
        assert request.method == "POST" and str(request.url) == settings().introspection_url
        assert request.headers["authorization"].startswith("Basic ")
        assert b"token=private-fixture-token" in request.content
        assert "private-fixture-token" not in str(request.url)


@pytest.mark.parametrize(
    "response",
    [
        lambda: httpx.Response(302, headers={"Location": "https://untrusted.example.test"}),
        lambda: httpx.Response(401, text="private-provider-diagnostic"),
        lambda: httpx.Response(200, headers={"Content-Length": "9" * 5000}),
        lambda: httpx.Response(200, headers={"Content-Encoding": "gzip"}),
        lambda: httpx.Response(200, stream=httpx.ByteStream(b"x" * (MAX_RESPONSE_BYTES + 1))),
        lambda: httpx.Response(200, stream=httpx.ByteStream(b'{"active":true,"active":false}')),
        lambda: httpx.Response(200, stream=httpx.ByteStream(b"private-provider-diagnostic")),
    ],
)
def test_introspection_failures_are_bounded_and_private(response):
    calls = []

    def respond(request):
        calls.append(request)
        return response()

    auth = OAuthVerifier(settings(), transport=httpx.MockTransport(respond))
    with pytest.raises(ServiceError) as caught:
        asyncio.run(auth.verify("private-fixture-token"))
    assert caught.value.status == 503 and len(calls) == 1
    assert "private" not in str(caught.value)


def test_introspection_timeout_fails_closed(monkeypatch):
    real_timeout = asyncio.timeout
    monkeypatch.setattr("mnemion.service.oauth.asyncio.timeout", lambda _: real_timeout(0.01))

    async def delayed(request):
        await asyncio.sleep(1)
        raise AssertionError("Deadline failed")

    auth = OAuthVerifier(settings(), transport=httpx.MockTransport(delayed))
    with pytest.raises(ServiceError) as caught:
        asyncio.run(auth.verify("private-fixture-token"))
    assert caught.value.status == 503


def linked(env, *, client_id=None, principal=None):
    service = OAuthBindings(env.db, settings(tenant_id=env.owner.tenant_id))
    if principal is None:
        person = env.identities.create_principal(
            env.owner, PrincipalInput(name="Person", kind="human")
        )
        principal = UUID(person["id"])
    value = service.create(
        env.owner,
        OAuthBindingInput(
            principal_id=principal,
            name="Hosted connection",
            subject=str(env.owner.tenant_id),
            client_id=client_id or claims()["client_id"],
        ),
    )
    validated = verifier(tenant_id=env.owner.tenant_id).validate(
        claims(sub=str(env.owner.tenant_id), client_id=client_id or claims()["client_id"])
    )
    return env.db.authenticate_oauth(validated), value


def test_oauth_binding_is_immutable_revocable_isolated_and_has_no_implicit_grants(env):
    first, binding = linked(env)
    assert env.identities.spaces(first) == []
    assert "api_key" not in binding
    second, _ = linked(env, client_id="second-client", principal=first.principal_id)
    token = env.identities.create_key(env.owner, first.principal_id, KeyInput(name="Personal API"))
    api_identity = env.db.authenticate(token["api_key"])
    env.identities.grant(env.owner, env.space, first.principal_id, GrantInput(role="reader"))
    assert env.identities.spaces(first)[0]["role"] == "reader"
    with pytest.raises(ServiceError) as write:
        env.memory.save(first, env.space, MemoryInput(content="Forbidden write"), "read-only")
    assert write.value.status == 403
    with pytest.raises(ServiceError) as collision:
        linked(env, principal=env.owner.principal_id)
    assert collision.value.status == 409
    with env.db.transaction(env.owner) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "UPDATE mnemion.oauth_bindings SET principal_id=%s WHERE id=%s",
                (env.owner.principal_id, binding["id"]),
            )
    service = OAuthBindings(env.db, settings(tenant_id=env.owner.tenant_id))
    service.revoke(first, UUID(binding["id"]))
    with pytest.raises(ServiceError) as revoked:
        env.identities.me(first)
    assert revoked.value.status == 401
    assert env.identities.me(second)["principal_id"] == str(first.principal_id)
    assert env.identities.me(api_identity)["principal_id"] == str(first.principal_id)
    with pytest.raises(ServiceError):
        env.db.authenticate_oauth(
            verifier(tenant_id=env.owner.tenant_id).validate(claims(sub=str(env.owner.tenant_id)))
        )
    assert len(service.list(env.owner)) == 2


def test_binding_admin_requirement_tenant_isolation_and_claim_pinning(env):
    identity, binding = linked(env)
    service = OAuthBindings(env.db, settings(tenant_id=env.owner.tenant_id))
    with pytest.raises(ServiceError) as denied:
        service.create(
            identity,
            OAuthBindingInput(
                principal_id=identity.principal_id, name="Bad", subject="other", client_id="other"
            ),
        )
    assert denied.value.status == 403
    other = bootstrap_tenant(
        env.admin_dsn,
        tenant_name="Other",
        administrator_name="Owner",
        generation=env.embedder.generation,
    )
    outsider = env.db.authenticate(other["api_key"])
    assert service.list(outsider) == []
    with pytest.raises(ServiceError) as denied:
        service.revoke(outsider, UUID(binding["id"]))
    assert denied.value.status == 404
    for changes in ({"sub": "somebody-else"}, {"client_id": "another-client"}):
        with pytest.raises(ServiceError) as unknown:
            env.db.authenticate_oauth(
                verifier(tenant_id=env.owner.tenant_id).validate(
                    claims(**{"sub": str(env.owner.tenant_id), **changes})
                )
            )
        assert unknown.value.status == 401
    env.identities.disable_principal(env.owner, identity.principal_id)
    with pytest.raises(ServiceError):
        env.identities.me(identity)
    with pytest.raises(ServiceError):
        env.db.authenticate_oauth(
            verifier(tenant_id=env.owner.tenant_id).validate(claims(sub=str(env.owner.tenant_id)))
        )


def test_each_transaction_rechecks_expiry_grants_and_anchor_revocation(env):
    identity, binding = linked(env)
    env.identities.grant(
        env.owner, env.space, identity.principal_id, GrantInput(role="contributor")
    )
    assert env.identities.me(identity)
    with pytest.raises(ServiceError) as expired:
        env.identities.me(replace(identity, expires_at=time.time() - 1))
    assert expired.value.status == 401
    env.identities.revoke_grant(env.owner, env.space, identity.principal_id)
    assert env.identities.spaces(identity) == []
    env.identities.revoke_key(env.owner, UUID(binding["key_id"]))
    with pytest.raises(ServiceError):
        env.identities.me(identity)


def test_operator_workspace_admission_prevents_another_admin_claiming_external_users(env):
    other = bootstrap_tenant(
        env.admin_dsn,
        tenant_name="Other",
        administrator_name="Other owner",
        generation=env.embedder.generation,
    )
    outsider = env.db.authenticate(other["api_key"])
    bindings = OAuthBindings(env.db, settings(tenant_id=env.owner.tenant_id))
    before = env.identities.keys(outsider)
    with pytest.raises(ServiceError) as denied:
        bindings.create(
            outsider,
            OAuthBindingInput(
                principal_id=outsider.principal_id,
                name="Hijack attempt",
                subject=str(env.owner.tenant_id),
                client_id=claims()["client_id"],
            ),
        )
    assert denied.value.status == 403
    assert env.identities.keys(outsider) == before
    identity, _ = linked(env)
    valid_claims = verifier(tenant_id=env.owner.tenant_id).validate(
        claims(sub=str(env.owner.tenant_id), tenant_id=str(outsider.tenant_id))
    )
    assert env.db.authenticate_oauth(valid_claims).principal_id == identity.principal_id
    changed_policy = verifier(tenant_id=outsider.tenant_id).validate(
        claims(sub=str(env.owner.tenant_id))
    )
    with pytest.raises(ServiceError) as denied:
        env.db.authenticate_oauth(changed_policy)
    assert denied.value.status == 401
    assert env.identities.me(outsider)["tenant_id"] == str(outsider.tenant_id)


def test_http_metadata_challenge_tools_and_api_keys_share_the_same_boundary(env):
    identity, binding = linked(env)
    calls = []
    auth = verifier(
        claims(sub=str(env.owner.tenant_id)), calls=calls, tenant_id=env.owner.tenant_id
    )
    app = create_app(env.db, env.embedder, oauth=auth)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        for path in (
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/mcp",
        ):
            metadata = client.get(path, headers={"Host": "untrusted.example.test"})
            assert metadata.status_code == 200
            assert metadata.json() == settings().metadata()
            assert "untrusted" not in metadata.text
        missing = client.post("/mcp", json={})
        assert missing.status_code == 401
        assert settings().metadata_url in missing.headers["WWW-Authenticate"]
        assert (
            client.get("/v1/me", headers={"Authorization": "Bearer " + env.token}).status_code
            == 200
        )
        assert calls == []
        headers = {"Authorization": "Bearer opaque-fixture-token"}
        me = client.get("/v1/me", headers=headers)
        assert me.status_code == 200 and me.json()["principal_id"] == str(identity.principal_id)
        assert client.get("/v1/spaces", headers=headers).json()["items"] == []
        mcp = client.post(
            "/mcp",
            headers={**headers, "Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert mcp.status_code == 200, mcp.text
        for tool in mcp.json()["result"]["tools"]:
            assert tool["securitySchemes"] == [{"type": "oauth2", "scopes": [OAUTH_SCOPE]}]
            if tool["name"] == "memory_profile":
                assert tool["_meta"]["openai/profile"] is True

        def tool(name, arguments):
            response = client.post(
                "/mcp",
                headers={**headers, "Accept": "application/json, text/event-stream"},
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                },
            )
            assert response.status_code == 200, response.text
            return response.json()["result"]

        profile = tool("memory_profile", {})
        assert not profile["isError"]
        assert profile["structuredContent"] == {
            "id": str(identity.principal_id),
            "name": "Person",
            "nickname": "Test team",
        }
        # A different accepted external token for the same subject retains its
        # Mnemion profile; no token/binding identifier becomes the account ID.
        headers["Authorization"] = "Bearer another-opaque-fixture-token"
        assert tool("memory_profile", {})["structuredContent"] == profile["structuredContent"]
        save_args = {
            "space_id": str(env.space),
            "content": "Scoped OAuth memory",
            "idempotency_key": "oauth-memory",
        }
        denied = tool("memory_save", save_args)
        assert denied["isError"] and denied["structuredContent"]["code"] == "not_found"
        env.identities.grant(
            env.owner, env.space, identity.principal_id, GrantInput(role="contributor")
        )
        saved = tool("memory_save", save_args)
        assert not saved["isError"], saved
        fetched = tool("memory_fetch", {"memory_id": saved["structuredContent"]["memory_id"]})
        assert (
            not fetched["isError"]
            and fetched["structuredContent"]["content"] == "Scoped OAuth memory"
        )
        assert fetched["structuredContent"]["created_by"] == str(identity.principal_id)
        revoked = client.delete(f"/v1/oauth/bindings/{binding['id']}", headers=headers)
        assert revoked.status_code == 200
        assert client.get("/v1/me", headers=headers).status_code == 401
        assert client.post("/mcp", headers=headers, json={}).status_code == 401
        assert "opaque-fixture-token" not in str(revoked.json())


def test_issuer_revocation_between_mcp_admission_and_tool_call_returns_auth_metadata(env):
    linked(env)
    calls = []

    def respond(request):
        calls.append(request)
        # Gateway admission succeeds; the nested tool request must revalidate.
        result = claims(sub=str(env.owner.tenant_id), active=len(calls) == 1)
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(result).encode()))

    auth = OAuthVerifier(
        settings(tenant_id=env.owner.tenant_id), transport=httpx.MockTransport(respond)
    )
    with TestClient(
        create_app(env.db, env.embedder, oauth=auth), base_url="http://127.0.0.1"
    ) as client:
        response = client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer fixture-token",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "memory_spaces", "arguments": {}},
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()["result"]
        assert result["isError"] and len(calls) == 2
        assert settings().metadata_url in result["_meta"]["mcp/www_authenticate"][0]


def test_missing_scope_gets_discoverable_403_on_api_and_mcp(env):
    app = create_app(env.db, env.embedder, oauth=verifier(claims(scope="unrelated")))
    with TestClient(app) as client:
        for method, path in (("GET", "/v1/me"), ("POST", "/mcp")):
            response = client.request(method, path, headers={"Authorization": "Bearer fixture"})
            assert response.status_code == 403
            assert 'error="insufficient_scope"' in response.headers["WWW-Authenticate"]


def test_duplicate_headers_and_bad_local_keys_never_reach_the_issuer(env):
    calls = []
    with TestClient(create_app(env.db, env.embedder, oauth=verifier(calls=calls))) as client:
        for headers in (
            [("Authorization", "Bearer one"), ("Authorization", "Bearer two")],
            {"Authorization": "Bearer mnm_invalid"},
            {"Authorization": "Bearer " + "x" * 4097},
        ):
            assert client.get("/v1/me", headers=headers).status_code == 401
        assert calls == []
