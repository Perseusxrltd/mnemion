"""Current workspace capability discovery without leaking another tenant's setup."""

from uuid import uuid4

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
