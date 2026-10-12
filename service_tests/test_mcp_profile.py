"""A hosted client's account label is derived from current credentials only."""

import json
from uuid import UUID

import jsonschema
import psycopg
from fastapi.testclient import TestClient

from mnemion.service.admin import bootstrap_tenant
from mnemion.service.api import create_app
from mnemion.service.models import KeyInput, PrincipalInput


def request(client, token, method="tools/call", params=None):
    return client.post(
        "/mcp",
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params if params is not None else {"name": "memory_profile", "arguments": {}},
        },
    )


def profile(client, token):
    response = request(client, token)
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert not result["isError"], result
    value = result["structuredContent"]
    assert set(value) == {"id", "name", "nickname"}
    assert UUID(value["id"]).version == 4
    assert len(result["content"]) == 1
    assert json.loads(result["content"][0]["text"]) == value
    return value


def test_profile_metadata_identity_and_revocation_without_content_access(env):
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Same display name", kind="human")
    )
    principal = UUID(person["id"])
    first = env.identities.create_key(env.owner, principal, KeyInput(name="First device"))
    second = env.identities.create_key(env.owner, principal, KeyInput(name="Other device"))
    assert env.identities.spaces(env.db.authenticate(first["api_key"])) == []
    with TestClient(create_app(env.db, env.embedder), base_url="http://127.0.0.1") as client:
        listing = request(client, first["api_key"], "tools/list", {}).json()["result"]["tools"]
        designated = [tool for tool in listing if tool.get("_meta", {}).get("openai/profile")]
        assert len(designated) == 1
        tool = designated[0]
        assert tool["name"] == "memory_profile"
        assert tool["_meta"]["openai/profile"] is True
        assert tool["inputSchema"]["properties"] == {}
        assert tool["annotations"]["readOnlyHint"] is True
        assert tool["annotations"]["destructiveHint"] is False
        assert tool["annotations"]["openWorldHint"] is False
        assert tool["outputSchema"]["additionalProperties"] is False
        original = profile(client, first["api_key"])
        jsonschema.validate(original, tool["outputSchema"])
        assert original == {
            "id": str(principal),
            "name": "Same display name",
            "nickname": "Test team",
        }
        assert profile(client, second["api_key"]) == original
        # Rename storage fixtures without changing the immutable identity.
        with psycopg.connect(env.admin_dsn) as conn:
            conn.execute(
                "UPDATE mnemion.principals SET name='Renamed person' WHERE id=%s", (principal,)
            )
            conn.execute(
                "UPDATE mnemion.tenants SET name='Renamed team' WHERE id=%s", (env.owner.tenant_id,)
            )
        renamed = profile(client, second["api_key"])
        assert renamed == {
            "id": str(principal),
            "name": "Renamed person",
            "nickname": "Renamed team",
        }
        env.identities.revoke_key(env.owner, UUID(first["id"]))
        denied = request(client, first["api_key"])
        assert denied.status_code == 401 and "result" not in denied.json()
        assert profile(client, second["api_key"]) == renamed
        env.identities.disable_principal(env.owner, principal)
        assert request(client, second["api_key"]).status_code == 401
        replacement = env.identities.create_principal(
            env.owner, PrincipalInput(name="Renamed person", kind="human")
        )
        replacement_key = env.identities.create_key(
            env.owner, UUID(replacement["id"]), KeyInput(name="Replacement access")
        )
        assert profile(client, replacement_key["api_key"])["id"] != renamed["id"]


def test_two_workspaces_with_the_same_names_have_distinct_profiles(env):
    other = bootstrap_tenant(
        env.admin_dsn,
        tenant_name="Test team",
        administrator_name="Owner",
        generation=env.embedder.generation,
    )
    with TestClient(create_app(env.db, env.embedder), base_url="http://127.0.0.1") as client:
        first = profile(client, env.token)
        second = profile(client, other["api_key"])
        assert first["name"] == second["name"] == "Owner"
        assert first["nickname"] == second["nickname"] == "Test team"
        assert first["id"] != second["id"]
        assert first["id"] == str(env.owner.principal_id)
        assert second["id"] == other["principal_id"]
        assert request(client, "mnm_" + "invalid" * 8).status_code == 401
