"""Actual HTTP cookies, CSRF, tenant binding and private credential responses."""

from fastapi.testclient import TestClient
import psycopg
import pytest

from mnemion.service.admin import bootstrap_tenant
from mnemion.service.api import create_app
from mnemion.service.models import PrincipalInput
from mnemion.service.sign_in import PasswordInput, SignInService
from mnemion.service.sign_in_api import BrowserPolicy, cookie_names

PASSWORD = "birch lantern cocoa summit calypso"
ORIGIN = "https://memory.example.test"


@pytest.fixture
def service(env, monkeypatch):
    monkeypatch.setenv("MNEMION_PUBLIC_URL", ORIGIN)
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute("DELETE FROM mnemion.sign_in_attempts")
    service = SignInService(env.db)
    service.set_password(env.owner, PasswordInput(username="owner", password=PASSWORD))
    return service


def login_data(env, *, browser=False, remember=False, workspace=None):
    return {
        "workspace_id": str(workspace or env.owner.tenant_id),
        "username": "owner",
        "password": PASSWORD,
        "device_name": "HTTP test device",
        "transport": "browser" if browser else "native",
        "remember": remember,
    }


def auth(token):
    return {"Authorization": "Bearer " + token}


def test_native_http_sign_in_refresh_and_sign_out(env, service):
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False), base_url=ORIGIN) as client:
        response = client.post("/v1/sign-in/login", json=login_data(env))
        assert response.status_code == 200
        tokens = response.json()
        assert tokens["persistence"] == "native" and tokens["refresh_token"]
        assert not response.headers.get_list("set-cookie")
        assert client.get("/v1/me", headers=auth(tokens["access_token"])).json()[
            "principal_id"
        ] == str(env.owner.principal_id)
        renewed = client.post(
            "/v1/sign-in/refresh",
            json={
                "workspace_id": str(env.owner.tenant_id),
                "transport": "native",
                "refresh_token": tokens["refresh_token"],
            },
        )
        assert renewed.status_code == 200
        assert renewed.json()["session_id"] == tokens["session_id"]
        assert client.get("/v1/me", headers=auth(tokens["access_token"])).status_code == 401
        ended = client.post(
            "/v1/sign-in/logout",
            json={
                "workspace_id": str(env.owner.tenant_id),
                "transport": "native",
                "refresh_token": renewed.json()["refresh_token"],
            },
        )
        assert ended.status_code == 200
        assert client.get("/v1/me", headers=auth(renewed.json()["access_token"])).status_code == 401
        assert client.get("/v1/me", headers=auth(env.token)).status_code == 200


def test_remembered_browser_cookie_refresh_and_logout_require_origin_and_csrf(env, service):
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False), base_url=ORIGIN) as client:
        response = client.post(
            "/v1/sign-in/login",
            headers={"Origin": ORIGIN},
            json=login_data(env, browser=True, remember=True),
        )
        assert response.status_code == 200
        tokens = response.json()
        assert tokens["persistence"] == "cookie" and tokens["refresh_token"] is None
        name, csrf_name = cookie_names(env.owner.tenant_id)
        previous = client.cookies.get(name)
        assert previous and client.cookies.get(csrf_name) == tokens["csrf_token"]
        issuing = [h for h in response.headers.get_list("set-cookie") if "Max-Age=0" not in h]
        assert len(issuing) == 2
        assert all(
            "Secure" in h and "SameSite=strict" in h and "Path=/" in h and "Domain=" not in h
            for h in issuing
        )
        assert "HttpOnly" in next(h for h in issuing if h.startswith(name + "="))
        body = {"workspace_id": str(env.owner.tenant_id), "transport": "browser"}
        for headers in (
            {},
            {"Origin": "https://wrong.example.test", "X-Mnemion-CSRF": tokens["csrf_token"]},
            {"Origin": ORIGIN},
            {"Origin": ORIGIN, "X-Mnemion-CSRF": "invalid"},
        ):
            denied = client.post("/v1/sign-in/refresh", headers=headers, json=body)
            assert denied.status_code == 403
            assert client.cookies.get(name) == previous
        headers = {"Origin": ORIGIN, "X-Mnemion-CSRF": tokens["csrf_token"]}
        refreshed = client.post("/v1/sign-in/refresh", headers=headers, json=body)
        assert refreshed.status_code == 200
        assert client.cookies.get(name) != previous
        assert refreshed.json()["refresh_token"] is None
        assert client.post("/v1/sign-in/logout", headers=headers, json=body).status_code == 200
        assert not client.cookies.get(name) and not client.cookies.get(csrf_name)
        assert (
            client.get("/v1/me", headers=auth(refreshed.json()["access_token"])).status_code == 401
        )


def test_two_workspaces_on_one_origin_retain_separate_browser_sessions(env, service):
    other = bootstrap_tenant(
        env.admin_dsn,
        tenant_name="Separate organization",
        administrator_name="Owner",
        generation=env.embedder.generation,
    )
    owner = env.db.authenticate(other["api_key"])
    service.set_password(owner, PasswordInput(username="owner", password=PASSWORD))
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False), base_url=ORIGIN) as client:
        first = client.post(
            "/v1/sign-in/login",
            headers={"Origin": ORIGIN},
            json=login_data(env, browser=True, remember=True),
        ).json()
        second = client.post(
            "/v1/sign-in/login",
            headers={"Origin": ORIGIN},
            json=login_data(env, browser=True, remember=True, workspace=owner.tenant_id),
        ).json()
        assert first["principal_id"] != second["principal_id"]
        assert client.cookies.get(cookie_names(env.owner.tenant_id)[0])
        assert client.cookies.get(cookie_names(owner.tenant_id)[0])
        for tokens in (first, second):
            refreshed = client.post(
                "/v1/sign-in/refresh",
                headers={"Origin": ORIGIN, "X-Mnemion-CSRF": tokens["csrf_token"]},
                json={"workspace_id": tokens["tenant_id"], "transport": "browser"},
            )
            assert refreshed.status_code == 200
            assert refreshed.json()["tenant_id"] == tokens["tenant_id"]
            assert refreshed.json()["principal_id"] == tokens["principal_id"]


def test_refresh_workspace_substitution_cannot_change_or_revoke_the_original_identity(env, service):
    other = bootstrap_tenant(
        env.admin_dsn,
        tenant_name="Separate",
        administrator_name="Owner",
        generation=env.embedder.generation,
    )
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False), base_url=ORIGIN) as client:
        tokens = client.post("/v1/sign-in/login", json=login_data(env)).json()
        wrong = client.post(
            "/v1/sign-in/refresh",
            json={
                "workspace_id": other["tenant_id"],
                "transport": "native",
                "refresh_token": tokens["refresh_token"],
            },
        )
        assert wrong.status_code == 401
        assert client.get("/v1/me", headers=auth(tokens["access_token"])).status_code == 200
        assert (
            client.post(
                "/v1/sign-in/refresh",
                json={
                    "workspace_id": str(env.owner.tenant_id),
                    "transport": "native",
                    "refresh_token": tokens["refresh_token"],
                },
            ).status_code
            == 200
        )


@pytest.mark.parametrize("remember", [False, True])
@pytest.mark.parametrize("public_url", [None, "http://127.0.0.1:7892/mcp"])
def test_loopback_browser_keeps_credentials_in_memory_without_insecure_cookies(
    env, service, monkeypatch, remember, public_url
):
    if public_url:
        monkeypatch.setenv("MNEMION_PUBLIC_URL", public_url)
    else:
        monkeypatch.delenv("MNEMION_PUBLIC_URL")
    origin = "http://127.0.0.1:7892"
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False), base_url=origin) as client:
        configuration = client.get("/v1/sign-in/configuration").json()
        assert configuration["browser_sign_in"] and not configuration["remember_browser"]
        response = client.post(
            "/v1/sign-in/login",
            headers={"Origin": origin},
            json=login_data(env, browser=True, remember=remember),
        )
        assert response.status_code == 200
        tokens = response.json()
        assert tokens["persistence"] == "memory" and tokens["refresh_token"]
        assert not client.cookies
        refreshed = client.post(
            "/v1/sign-in/refresh",
            headers={"Origin": origin, "X-Mnemion-CSRF": tokens["csrf_token"]},
            json={
                "workspace_id": tokens["tenant_id"],
                "transport": "browser",
                "refresh_token": tokens["refresh_token"],
            },
        )
        assert refreshed.status_code == 200 and refreshed.json()["persistence"] == "memory"


def test_sign_in_preserves_configured_public_origin_compatibility():
    assert BrowserPolicy("http://[::1]:7892/mcp").public_origin == "http://[::1]:7892"
    assert BrowserPolicy("http://localhost:80").public_origin == "http://localhost"
    assert (
        BrowserPolicy("https://mémoire.example/mcp").public_origin
        == "https://xn--mmoire-bva.example"
    )
    for invalid in (
        "http://remote.example",
        "http://localhost@remote.example",
        "http://localhost:0",
        "http://localhost/other",
        "http://localhost?next=elsewhere",
        "http://localhost\n",
    ):
        with pytest.raises(ValueError):
            BrowserPolicy(invalid)


def test_native_mode_cannot_be_used_by_cross_origin_browser_requests(env, service):
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False), base_url=ORIGIN) as client:
        response = client.post(
            "/v1/sign-in/login",
            headers={"Origin": "https://untrusted.example"},
            json=login_data(env),
        )
        assert response.status_code == 403 and PASSWORD not in response.text


def test_public_url_is_operator_configured_and_normalized(env, service, monkeypatch):
    monkeypatch.delenv("MNEMION_PUBLIC_URL")
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False), base_url=ORIGIN) as client:
        assert not client.get("/v1/sign-in/configuration").json()["browser_sign_in"]
        assert (
            client.post(
                "/v1/sign-in/login", headers={"Origin": ORIGIN}, json=login_data(env, browser=True)
            ).status_code
            == 409
        )
    monkeypatch.setenv("MNEMION_PUBLIC_URL", "https://MEMORY.example.test:443/mcp")
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False), base_url=ORIGIN) as client:
        assert client.get("/v1/sign-in/configuration").json()["public_origin"] == ORIGIN
        assert (
            client.post(
                "/v1/sign-in/login", headers={"Origin": ORIGIN}, json=login_data(env, browser=True)
            ).status_code
            == 200
        )


def test_invitation_urls_keep_the_secret_out_of_paths_and_queries(env, service):
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Invite recipient", kind="human")
    )
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False), base_url=ORIGIN) as client:
        invitation = client.post(
            "/v1/sign-in/invitations", headers=auth(env.token), json={"principal_id": person["id"]}
        )
        assert invitation.status_code == 201
        data = invitation.json()
        assert data["invitation_url"] == f"{ORIGIN}/workspace#invitation={data['invitation_token']}"
        preview = client.post(
            "/v1/sign-in/invitations/preview", json={"invitation": data["invitation_token"]}
        )
        assert preview.status_code == 200 and preview.json()["principal_id"] == person["id"]
        accepted = client.post(
            "/v1/sign-in/invitations/accept",
            json={
                "invitation": data["invitation_token"],
                "username": "recipient",
                "password": PASSWORD,
                "transport": "native",
                "device_name": "Accepted device",
            },
        )
        assert accepted.status_code == 200
        assert accepted.json()["principal_id"] == person["id"]
        assert (
            client.get("/v1/me", headers=auth(accepted.json()["access_token"])).json()[
                "administrator"
            ]
            is False
        )


def test_request_validation_does_not_echo_passwords_or_private_invitation_secrets(env, service):
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False), base_url=ORIGIN) as client:
        data = login_data(env)
        data["password"] = "private-password-marker-" * 20
        response = client.post("/v1/sign-in/login", json=data)
        assert response.status_code == 422 and "private-password-marker" not in response.text


def test_stale_tab_cannot_refresh_or_sign_out_a_different_browser_session(env, service):
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False), base_url=ORIGIN) as client:
        first = client.post(
            "/v1/sign-in/login",
            headers={"Origin": ORIGIN},
            json=login_data(env, browser=True, remember=True),
        ).json()
        second = client.post(
            "/v1/sign-in/login",
            headers={"Origin": ORIGIN},
            json=login_data(env, browser=True, remember=True),
        ).json()
        headers = {"Origin": ORIGIN, "X-Mnemion-CSRF": second["csrf_token"]}
        body = {
            "workspace_id": str(env.owner.tenant_id),
            "session_id": first["session_id"],
            "transport": "browser",
        }
        name, csrf_name = cookie_names(env.owner.tenant_id)
        cookie = client.cookies.get(name)
        assert client.post("/v1/sign-in/refresh", headers=headers, json=body).status_code == 401
        stale_logout = client.post("/v1/sign-in/logout", headers=headers, json=body)
        assert stale_logout.status_code == 200 and stale_logout.json()["signed_out"] is False
        assert not stale_logout.headers.get_list("set-cookie")
        assert client.cookies.get(name) == cookie
        assert client.cookies.get(csrf_name) == second["csrf_token"]
        assert client.get("/v1/me", headers=auth(second["access_token"])).status_code == 200
        body["session_id"] = second["session_id"]
        renewed = client.post("/v1/sign-in/refresh", headers=headers, json=body)
        assert renewed.status_code == 200 and renewed.json()["rotation"] == second["rotation"] + 1


def test_account_and_session_routes_require_authentication(env, service):
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False), base_url=ORIGIN) as client:
        for path in ("account", "sessions", "invitations"):
            assert client.get("/v1/sign-in/" + path).status_code == 401
            assert client.get("/v1/sign-in/" + path, headers=auth(env.token)).status_code == 200
        response = client.put(
            "/v1/sign-in/account",
            headers=auth(env.token),
            json={
                "username": "owner",
                "current_password": PASSWORD,
                "password": "harbour comet mitten glacier tapestry",
            },
        )
        assert response.status_code == 200 and response.json()["sessions_revoked"]
