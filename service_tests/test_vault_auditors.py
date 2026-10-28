"""Real SQL/HTTP/MCP checks for exact-key, metadata-only vault administration."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from uuid import UUID

from fastapi.testclient import TestClient
import psycopg
import pytest

from mnemion.service.admin import bootstrap_tenant
from mnemion.service.api import create_app
from mnemion.service.errors import ServiceError
from mnemion.service.models import KeyInput
from mnemion.service.vault import VaultService
from mnemion.service.vault_crypto import VaultSettings
from mnemion.service.vault_models import VaultAuditorChange, VaultDelete, VaultPut
from service_tests.test_administration_continuity import authorization
from service_tests.test_mcp_compatibility import call, request
from service_tests.test_secrets_vault import VALUE, allow, create, member, vault as vault


def grant(vault, owner, identity, *, version=0, enabled=True, expires_at=None):
    return vault.auditor(
        owner,
        identity.key_id,
        VaultAuditorChange(expected_version=version, enabled=enabled, expires_at=expires_at),
    )


def denied(function, status=403):
    with pytest.raises(ServiceError) as failure:
        function()
    assert failure.value.status == status


def test_auditor_inspects_metadata_and_deleted_entry_history_without_value_rights(env, vault):
    entry = create(vault, env.owner)
    removed = create(vault, env.owner, name="Removed synthetic credential")
    vault.delete(env.owner, UUID(removed["id"]), VaultDelete(expected_version=1))
    reader, _ = member(env)
    saved = grant(vault, env.owner, reader)
    assert saved["active"] and saved["version"] == 1
    assert vault.status(reader)["audit_access"]
    listed = vault.list(reader)
    assert [row["id"] for row in listed["items"]] == [entry["id"]]
    assert listed["items"][0]["permissions"] == {"read": False, "write": False, "manage": False}
    events = vault.audit_events(reader)
    assert any(
        row["entry_id"] == removed["id"] and row["action"] == "delete" for row in events["items"]
    )
    assert any(
        row["action"] == "auditor" and row["target_key_id"] == str(reader.key_id)
        for row in events["items"]
    )
    public = json.dumps([vault.status(reader), listed, events, saved])
    assert VALUE not in public and '"ciphertext"' not in public and '"nonce"' not in public
    denied(lambda: vault.get(reader, UUID(entry["id"])))
    denied(
        lambda: vault.put(
            reader,
            UUID(entry["id"]),
            VaultPut(expected_version=1, name=entry["name"], value="blocked"),
        )
    )
    denied(lambda: vault.delete(reader, UUID(entry["id"]), VaultDelete(expected_version=1)))
    denied(lambda: vault.grants(reader, UUID(entry["id"])))
    denied(lambda: vault.auditors(reader))
    denied(lambda: grant(vault, reader, reader, version=1))


def test_role_does_not_follow_sibling_keys_or_other_tenants(env, vault):
    entry = create(vault, env.owner)
    reader, _ = member(env)
    sibling = env.identities.create_key(
        env.owner, reader.principal_id, KeyInput(name="Sibling key")
    )
    second = env.db.authenticate(sibling["api_key"])
    other = bootstrap_tenant(
        env.admin_dsn, tenant_name="Separate fixture tenant", administrator_name="Owner"
    )
    outsider = env.db.authenticate(other["api_key"])
    grant(vault, env.owner, reader)
    for identity in (second, outsider):
        assert vault.list(identity)["items"] == []
        denied(lambda: vault.get(identity, UUID(entry["id"])), 404)
    denied(lambda: vault.audit_events(second))
    own_events = vault.audit_events(outsider)["items"]
    assert {row["action"] for row in own_events} == {"list", "get"}
    assert all(
        row["key_id"] == str(outsider.key_id) and row["principal_id"] == str(outsider.principal_id)
        for row in own_events
    )
    assert VALUE not in json.dumps(own_events)
    denied(lambda: grant(vault, env.owner, outsider), 422)
    denied(lambda: grant(vault, outsider, reader), 422)
    assert vault.auditors(env.owner, key_id=reader.key_id)["items"][0]["key_id"] == str(
        reader.key_id
    )


def test_revision_conflicts_revocation_expiry_and_independent_entry_grants(env, vault):
    entry = create(vault, env.owner)
    reader, _ = member(env)
    grant(vault, env.owner, reader)
    denied(lambda: grant(vault, env.owner, reader), 409)
    revoked = grant(vault, env.owner, reader, version=1, enabled=False)
    assert revoked["version"] == 2 and not revoked["active"]
    assert vault.list(reader)["items"] == []
    denied(lambda: vault.audit_events(reader))
    denied(lambda: grant(vault, env.owner, reader), 409)
    allowed = grant(
        vault,
        env.owner,
        reader,
        version=2,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert allowed["active"] and allowed["version"] == 3
    denied(
        lambda: grant(
            vault,
            env.owner,
            reader,
            version=3,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        ),
        422,
    )
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "UPDATE mnemion.vault_auditors SET expires_at=clock_timestamp()-interval '1 second' WHERE tenant_id=%s AND key_id=%s",
            (reader.tenant_id, reader.key_id),
        )
    assert not vault.status(reader)["audit_access"]
    assert vault.list(reader)["items"] == []
    denied(lambda: vault.audit_events(reader))
    allow(vault, env.owner, entry, reader, read=True)
    assert vault.get(reader, UUID(entry["id"]))["value"] == VALUE
    denied(lambda: vault.audit_events(reader))
    assert not vault.auditors(env.owner)["items"][0]["active"]


@pytest.mark.parametrize("retirement", ["key", "key_expiry", "principal"])
def test_stale_identity_cannot_retain_metadata_after_retirement(env, vault, retirement):
    create(vault, env.owner)
    reader, _ = member(env)
    grant(vault, env.owner, reader)
    with psycopg.connect(env.admin_dsn) as conn:
        if retirement == "principal":
            conn.execute(
                "UPDATE mnemion.principals SET disabled_at=clock_timestamp() WHERE tenant_id=%s AND id=%s",
                (reader.tenant_id, reader.principal_id),
            )
        else:
            field = "revoked_at" if retirement == "key" else "expires_at"
            conn.execute(
                f"UPDATE mnemion.api_keys SET {field}=clock_timestamp() WHERE tenant_id=%s AND id=%s",
                (reader.tenant_id, reader.key_id),
            )
    denied(lambda: vault.list(reader), 401)
    denied(lambda: vault.audit_events(reader), 401)
    denied(lambda: grant(vault, env.owner, reader, version=1), 422)
    assert not vault.auditors(env.owner)["items"][0]["active"]
    assert not grant(vault, env.owner, reader, version=1, enabled=False)["enabled"]


def test_simultaneous_grants_accept_one_revision_and_keep_both_audit_outcomes(env, vault):
    reader, _ = member(env)

    def change():
        try:
            return grant(vault, env.owner, reader)["version"]
        except ServiceError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: change(), range(2)))
    assert sorted(results) == [1, 409]
    assert {
        row["outcome"]
        for row in vault.audit_events(env.owner)["items"]
        if row["action"] == "auditor"
    } == {"allowed", "conflict"}


@pytest.mark.parametrize("key", [None, "invalid-synthetic-key"])
def test_metadata_remains_available_for_key_repair_but_host_disable_still_applies(env, vault, key):
    entry = create(vault, env.owner)
    reader, _ = member(env)
    broken = VaultService(env.db, VaultSettings(enabled=True, key=key, mcp_metadata_enabled=True))
    grant(broken, env.owner, reader)
    status = broken.status(reader)
    assert status["metadata_available"] and status["audit_access"] and not status["available"]
    assert status["mcp_metadata_enabled"] and not status["mcp_enabled"]
    assert broken.list(reader)["items"][0]["id"] == entry["id"]
    assert broken.audit_events(reader)["items"]
    denied(lambda: broken.get(reader, UUID(entry["id"])), 503)
    disabled = VaultService(env.db, VaultSettings(mcp_metadata_enabled=True))
    assert not disabled.status(reader)["metadata_available"]
    assert not disabled.status(reader)["audit_access"]
    denied(lambda: disabled.list(reader), 503)
    denied(lambda: disabled.audit_events(reader))
    assert disabled.audit_events(env.owner)["items"]


@pytest.mark.parametrize("profile", ["full", "compact"])
def test_http_and_mcp_grant_inspect_revoke_without_exposing_secret_tools(
    env, vault, monkeypatch, profile
):
    monkeypatch.setenv("MNEMION_MCP_TOOL_PROFILE", profile)
    reader, token = member(env)
    entry = create(vault, env.owner)
    settings = vault.settings.model_copy(update={"mcp_metadata_enabled": True})
    with TestClient(
        create_app(env.db, env.embedder, vault_settings=settings, studio_enabled=False),
        base_url="http://127.0.0.1",
    ) as api:
        listed = request(api, env.token, "tools/list").json()["result"]
        assert not {"vault_get", "vault_put"}.intersection(tool["name"] for tool in listed["tools"])
        response = api.get(
            "/v1/vault/auditors",
            headers=authorization(env.token),
            params={"key_id": str(reader.key_id)},
        )
        assert response.status_code == 200 and response.json()["items"] == []
        command = {
            "action": "write",
            "operation": "vault.auditor",
            "request": {
                "parameters": {"key_id": str(reader.key_id)},
                "body": {"expected_version": 0, "enabled": True},
            },
        }
        saved = call(api, env.token, "mnemion", command)
        assert not saved["isError"], saved
        for operation in ("vault.status", "vault.list", "vault.audit"):
            result = call(api, token, "mnemion", {"action": "read", "operation": operation})
            assert not result["isError"], result
            assert VALUE not in json.dumps(result) and '"ciphertext"' not in json.dumps(result)
        private = call(
            api,
            env.token,
            "mnemion",
            {
                "action": "read",
                "operation": "vault.get",
                "request": {"parameters": {"entry_id": entry["id"]}},
            },
        )
        assert private["isError"] and private["structuredContent"]["code"] == "vault_mcp_disabled"
        escalation = call(api, token, "mnemion", command)
        assert escalation["isError"]
        forbidden_value = api.get(f"/v1/vault/entries/{entry['id']}", headers=authorization(token))
        assert forbidden_value.status_code == 403 and VALUE not in forbidden_value.text
        assert (
            api.get("/v1/vault/audit", headers=authorization(token)).headers["cache-control"]
            == "no-store"
        )
        revoked = api.put(
            f"/v1/vault/auditors/{reader.key_id}",
            headers=authorization(env.token),
            json={"expected_version": 1, "enabled": False},
        )
        assert revoked.status_code == 200 and not revoked.json()["active"]
        assert call(api, token, "mnemion", {"action": "read", "operation": "vault.audit"})[
            "isError"
        ]


def test_audit_key_role_is_not_available_to_indexing_worker(env, vault):
    reader, _ = member(env)
    grant(vault, env.owner, reader)
    for statement in ("SELECT * FROM mnemion.vault_auditors", "SELECT mnemion.vault_auditor()"):
        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege),
            env.worker_db.worker_transaction(env.owner.tenant_id) as conn,
        ):
            conn.execute(statement)
