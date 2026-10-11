"""Independent administrators retain access without inheriting private content."""

from uuid import UUID

from fastapi.testclient import TestClient

from mnemion.service.admin import bootstrap_tenant
from mnemion.service.api import create_app
from mnemion.service.models import MemoryInput
from mnemion.version import __version__


def authorization(token):
    return {"Authorization": "Bearer " + token}


def create_identity(api, headers, name, *, kind="human", administrator=False):
    response = api.post(
        "/v1/principals",
        headers=headers,
        json={"name": name, "kind": kind, "administrator": administrator},
    )
    assert response.status_code == 201, response.text
    principal = response.json()
    key = api.post(
        f"/v1/principals/{principal['id']}/keys",
        headers=headers,
        json={"name": "Independent fixture access"},
    )
    assert key.status_code == 201, key.text
    return principal, authorization(key.json()["api_key"])


def test_second_human_admin_can_manage_after_original_identities_are_disabled(env):
    memory = env.memory.save(
        env.owner, env.space, MemoryInput(content="Original owner's private source"), "private"
    )
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False)) as api:
        installer, installer_headers = create_identity(
            api, authorization(env.token), "Installer agent", kind="application", administrator=True
        )
        human, headers = create_identity(
            api, installer_headers, "Independent human administrator", administrator=True
        )
        # Only the new human credential is used from this point onward.
        for identifier in (installer["id"], str(env.owner.principal_id)):
            response = api.post(f"/v1/principals/{identifier}/disable", headers=headers)
            assert response.status_code == 200, response.text
        assert api.get("/v1/me", headers=installer_headers).status_code == 401
        assert api.get("/v1/me", headers=authorization(env.token)).status_code == 401
        me = api.get("/v1/me", headers=headers)
        assert me.status_code == 200 and me.json()["administrator"] is True
        assert me.json()["service_version"] == __version__
        assert api.get("/v1/principals", headers=headers).status_code == 200
        # Organization administration and memory access remain separate.
        path = f"/v1/memories/{memory['memory_id']}"
        assert api.get(path, headers=headers).status_code in {403, 404}
        response = api.put(
            f"/v1/spaces/{env.space}/grants/{human['id']}",
            headers=headers,
            json={"role": "reader"},
        )
        assert response.status_code == 200, response.text
        assert api.get(path, headers=headers).status_code == 200
        member, member_headers = create_identity(
            api, headers, "Restricted replacement assistant", kind="application"
        )
        assert member["administrator"] is False
        assert api.get("/v1/me", headers=member_headers).json()["service_version"] == __version__
        assert api.get("/v1/principals", headers=member_headers).status_code == 403
        denied = api.post(
            "/v1/principals",
            headers=member_headers,
            json={"name": "Attempted administrator", "administrator": True},
        )
        assert denied.status_code == 403


def test_an_organization_admin_cannot_issue_keys_for_another_organization(env):
    other = bootstrap_tenant(
        env.admin_dsn,
        tenant_name="Separate organization",
        administrator_name="Separate owner",
        generation=env.embedder.generation,
    )
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False)) as api:
        admin, headers = create_identity(
            api, authorization(env.token), "Scoped administrator", administrator=True
        )
        people = api.get("/v1/principals", headers=headers).json()["items"]
        assert other["principal_id"] not in {person["id"] for person in people}
        denied = api.post(
            f"/v1/principals/{other['principal_id']}/keys",
            headers=headers,
            json={"name": "Not authorized"},
        )
        assert denied.status_code == 404
        assert env.identities.me(env.db.authenticate(other["api_key"]))["tenant_id"] == str(
            UUID(other["tenant_id"])
        )
