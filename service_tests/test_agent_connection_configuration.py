"""Current workspace capability discovery without leaking another tenant's setup."""

import base64
from io import BytesIO
import json
from uuid import uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from mnemion.service.api import create_app
from service_tests.test_oauth import verifier


@pytest.mark.parametrize("mode", ["disabled", "personal", "external"])
@pytest.mark.parametrize("gateway", [True, False])
def test_agent_connection_mode_requires_authentication_and_reports_actual_gateway(
    env, monkeypatch, mode, gateway
):
    for name in ("ISSUER", "INTROSPECTION_URL", "CLIENT_ID", "CLIENT_SECRET_FILE", "TENANT_ID"):
        monkeypatch.delenv("MNEMION_OAUTH_" + name, raising=False)
    monkeypatch.setenv("MNEMION_OAUTH_BUILTIN", "1" if mode == "personal" else "0")
    monkeypatch.setenv("MNEMION_PUBLIC_URL", "https://memory.example.test")
    if mode == "personal":
        monkeypatch.setenv("MNEMION_OAUTH_TENANT_ID", str(env.owner.tenant_id))
    external = verifier(tenant_id=env.owner.tenant_id) if mode == "external" else None
    app = create_app(env.db, env.embedder, mcp_enabled=gateway, oauth=external)
    with TestClient(app) as client:
        assert client.get("/v1/oauth/configuration").status_code == 401
        assert (
            client.post("/v1/oauth/agent-package", json={"provider": "openai"}).status_code == 401
        )
        response = client.get(
            "/v1/oauth/configuration", headers={"Authorization": "Bearer " + env.token}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == mode and data["mcp_enabled"] is gateway
        assert set(data) == {"mode", "mcp_enabled", "resource", "issuer"}
        assert data["resource"] == (
            None if mode == "disabled" else "https://memory.example.test/mcp"
        )
        assert data["issuer"] == (
            "https://memory.example.test/"
            if mode == "personal"
            else "https://identity.example.test/realm"
            if mode == "external"
            else None
        )
        package = client.post(
            "/v1/oauth/agent-package",
            headers={"Authorization": "Bearer " + env.token},
            json={"provider": "openai"},
        )
        assert package.status_code == (200 if mode != "disabled" and gateway else 409)
        if package.status_code == 200:
            assert package.headers["cache-control"] == "no-store"
            with ZipFile(BytesIO(base64.b64decode(package.json()["content_base64"]))) as archive:
                card = json.loads(archive.read("connection.json"))
                assert card["mcp_url"] == data["resource"]
                assert card["author"] == "Perseus XR"
                assert all(
                    env.token.encode() not in archive.read(name) for name in archive.namelist()
                )


@pytest.mark.parametrize("mode", ["personal", "external"])
def test_other_workspace_cannot_discover_selected_tenant_oauth_configuration(
    env, monkeypatch, mode
):
    other = uuid4()
    monkeypatch.setenv("MNEMION_OAUTH_BUILTIN", "1" if mode == "personal" else "0")
    monkeypatch.setenv("MNEMION_PUBLIC_URL", "https://private-tenant.example.test")
    monkeypatch.setenv("MNEMION_OAUTH_TENANT_ID", str(other))
    external = verifier(tenant_id=other) if mode == "external" else None
    with TestClient(create_app(env.db, env.embedder, oauth=external)) as client:
        response = client.get(
            "/v1/oauth/configuration", headers={"Authorization": "Bearer " + env.token}
        )
        assert response.status_code == 200
        assert response.json() == {
            "mode": "disabled",
            "mcp_enabled": True,
            "resource": None,
            "issuer": None,
        }
        package = client.post(
            "/v1/oauth/agent-package",
            headers={"Authorization": "Bearer " + env.token},
            json={"provider": "openai"},
        )
        assert package.status_code == 409 and "private-tenant" not in package.text


def test_nonadministrator_can_export_without_receiving_or_creating_credentials(env, monkeypatch):
    from uuid import UUID
    from mnemion.service.models import KeyInput, PrincipalInput

    monkeypatch.setenv("MNEMION_PUBLIC_URL", "https://memory.example.test")
    monkeypatch.setenv("MNEMION_OAUTH_BUILTIN", "1")
    monkeypatch.setenv("MNEMION_OAUTH_TENANT_ID", str(env.owner.tenant_id))
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Connection download fixture")
    )
    key = env.identities.create_key(
        env.owner, UUID(person["id"]), KeyInput(name="Download fixture")
    )
    with env.db.transaction(env.owner) as conn:
        before = conn.execute("SELECT count(*) AS n FROM mnemion.api_keys").fetchone()["n"]
    with TestClient(create_app(env.db, env.embedder)) as client:
        response = client.post(
            "/v1/oauth/agent-package",
            headers={"Authorization": "Bearer " + key["api_key"]},
            json={"provider": "hermes"},
        )
        assert response.status_code == 200
        assert response.json()["contains_credentials"] is False
    with env.db.transaction(env.owner) as conn:
        assert conn.execute("SELECT count(*) AS n FROM mnemion.api_keys").fetchone()["n"] == before
