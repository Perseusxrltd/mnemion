"""Actionable source diagnosis keeps the existing operator and tenant boundaries."""

import json
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from mnemion.sdk import Client
from mnemion.connectors.runner import sync
from mnemion.service.admin import bootstrap_tenant
from mnemion.service.api import create_app
from mnemion.service.connector_models import ConnectorInput, ScopeInput, utc_now
from mnemion.service.errors import ServiceError
from mnemion.service.models import GrantInput
from service_tests.test_clients import running
from service_tests.test_connectors import connected as connected
from service_tests.test_mcp_compatibility import call
from service_tests.test_source_health import text_source as text_source


def test_tenant_and_operator_diagnostics_do_not_grant_controls_to_space_admins(env, connected):
    service, connector, space, operator, identities = connected
    service.suspend(env.owner, space, "operator_paused")
    env.identities.grant(
        env.owner, env.space, identities["reader"][0].principal_id, GrantInput(role="administrator")
    )
    before = service.scopes(env.owner, connector)
    with TestClient(create_app(env.db, env.embedder), base_url="http://127.0.0.1") as client:
        client.headers["Authorization"] = "Bearer " + env.token
        health = client.get("/v1/health/sources", params={"details": True}).json()
        # A tenant administrator need not have an explicit content grant to find
        # a broken managed source. The original personal counts remain personal.
        assert health["unavailable_scopes"] == 0
        diagnostic = health["diagnostics"]
        assert diagnostic["visibility"] == "tenant"
        item = diagnostic["items"][0]
        assert item["space_id"] == str(space) and item["connector_id"] == str(connector)
        assert item["operator_id"] == str(operator.principal_id)
        assert set(item["reasons"]) == {"operator_paused", "permissions_expired"}
        assert item["recovery"] == "resume_source" and item["can_resume"]
        assert not item["can_request_sync"]
        assert "Private channel" not in json.dumps(health)
        assert "channel:C_PRIVATE" not in json.dumps(health)
        mcp = call(
            client,
            env.token,
            "mnemion",
            {
                "action": "read",
                "operation": "health.sources",
                "request": {"parameters": {"details": True}},
            },
        )
        assert not mcp["isError"], mcp
        assert mcp["structuredContent"]["result"]["diagnostics"] == diagnostic
        for name in ("reader", "reviewer", "outsider"):
            client.headers["Authorization"] = "Bearer " + identities[name][1]
            reply = client.get("/v1/health/sources", params={"details": True})
            assert reply.status_code == 200
            assert reply.json()["diagnostics"] == {
                "visibility": "unavailable",
                "items": [],
                "next_cursor": None,
            }
            assert all(
                str(value) not in reply.text for value in (space, connector, operator.principal_id)
            )
        client.headers["Authorization"] = "Bearer " + identities["connector"][1]
        operator_view = client.get("/v1/health/sources", params={"details": True}).json()[
            "diagnostics"
        ]
        assert operator_view["visibility"] == "owned"
        assert operator_view["items"][0]["space_id"] == str(space)
        assert not operator_view["items"][0]["can_resume"]
    assert service.scopes(env.owner, connector) == before
    with pytest.raises(ServiceError) as rejected:
        service.resume(operator, space)
    assert rejected.value.status == 403


def test_diagnostics_page_only_visible_affected_sources_and_preserve_sdk_shape(env, connected):
    service, connector, space, operator, identities = connected
    affected = {str(space)}
    service.suspend(env.owner, space, "access_lost")
    for index in range(4):
        scoped = service.refresh_scope(
            operator,
            connector,
            ScopeInput(
                external_id=f"private:source-{index}",
                name=f"Private label {index}",
                members=[],
                observed_at=utc_now(),
            ),
        )
        if index != 3:
            service.suspend(env.owner, UUID(scoped["space_id"]), "provider_unavailable")
            affected.add(scoped["space_id"])
    # Another registered operator owns an affected source in the same tenant.
    other_operator = identities["outsider"][0]
    other = service.create(
        env.owner,
        ConnectorInput(
            name="Other private connector", provider="git", principal_id=other_operator.principal_id
        ),
    )
    other_scope = service.refresh_scope(
        other_operator,
        UUID(other["id"]),
        ScopeInput(
            external_id="other:private",
            name="Other private source",
            members=[],
            observed_at=utc_now(),
        ),
    )
    service.suspend(env.owner, UUID(other_scope["space_id"]), "operator_paused")
    with running(create_app(env.db, env.embedder, studio_enabled=False)) as url:
        with Client(url, identities["connector"][1]) as client:
            collected, after = [], None
            while True:
                result = client.source_health(details=True, after=after, limit=2)
                assert result.diagnostics.visibility == "owned"
                collected.extend(item.space_id for item in result.diagnostics.items)
                after = result.diagnostics.next_cursor
                if after is None:
                    break
            assert len(collected) == len(affected) and set(collected) == affected
            assert other_scope["space_id"] not in collected
            assert client.source_health().diagnostics is None
        with Client(url, env.token) as admin:
            assert {
                item.space_id for item in admin.source_health(details=True).diagnostics.items
            } == affected | {other_scope["space_id"]}
        tenant = bootstrap_tenant(
            env.admin_dsn,
            tenant_name="Other company",
            administrator_name="Other owner",
            generation=env.embedder.generation,
        )
        with Client(url, tenant["api_key"]) as other_admin:
            isolated = other_admin.source_health(details=True)
            assert isolated.diagnostics.visibility == "tenant" and not isolated.diagnostics.items
    with TestClient(create_app(env.db, env.embedder, studio_enabled=False)) as client:
        client.headers["Authorization"] = "Bearer " + env.token
        assert (
            client.get("/v1/health/sources", params={"details": True, "limit": 101}).status_code
            == 422
        )
        assert (
            client.get(
                "/v1/health/sources", params={"details": True, "after": "invalid"}
            ).status_code
            == 422
        )


def test_incomplete_inventory_diagnostics_omit_file_names_and_clear_after_repair(env, text_source):
    service, connector, people, config = text_source
    path = config.provider.path / "PRIVATE_FILE_NAME_SENTINEL.md"
    path.write_bytes(b"\xff")
    with running(create_app(env.db, env.embedder, studio_enabled=False)) as url:
        with Client(url, people["capture"][1]) as client:
            assert not sync(config, client=client)["completed"]
            result = service.health(env.owner, details=True)
            item = result["diagnostics"]["items"][0]
            assert item["connector_id"] == str(connector)
            assert item["reasons"] == ["inventory_incomplete"]
            assert item["skipped_documents"] == 1 and item["recovery"] == "repair_source_files"
            assert item["can_request_sync"] and not item["can_resume"]
            assert "PRIVATE_" not in json.dumps(result) and str(
                config.provider.path
            ) not in json.dumps(result)
            path.write_text("Current Postgres evidence", encoding="utf-8")
            assert sync(config, client=client)["completed"]
            assert service.health(env.owner, details=True)["diagnostics"]["items"] == []


def test_resume_diagnosis_requires_fresh_provider_permissions_and_hides_raw_reasons(env, connected):
    service, connector, space, operator, identities = connected
    service.suspend(env.owner, space, "operator_paused")
    service.resume(env.owner, space)
    item = service.health(env.owner, details=True)["diagnostics"]["items"][0]
    assert item["recovery"] == "request_source_sync" and item["can_request_sync"]
    assert not item["can_resume"] and not item["operator_paused"]
    assert set(item["reasons"]) == {"permissions_expired", "provider_unavailable"}
    # This is a disposable fixture mutation, never a deployed policy change.
    with psycopg.connect(env.admin_dsn) as admin:
        admin.execute(
            "UPDATE mnemion.connector_scopes SET suspension_reason=%s WHERE tenant_id=%s AND space_id=%s",
            ("PRIVATE_REASON_SENTINEL /private/path", env.owner.tenant_id, space),
        )
    private = service.health(env.owner, details=True)
    assert "PRIVATE_" not in json.dumps(private)
    assert "permissions_recheck_required" in private["diagnostics"]["items"][0]["reasons"]
    assert service.health(identities["reader"][0])["unavailable_scopes"] == 1
    service.refresh_scope(
        operator,
        connector,
        ScopeInput(
            external_id="channel:C_PRIVATE",
            name="Private channel",
            members=["U_reader", "U_reviewer"],
            observed_at=utc_now(),
        ),
    )
    assert service.health(env.owner, details=True)["diagnostics"]["items"] == []
    assert service.health(identities["reader"][0])["unavailable_scopes"] == 0


@pytest.mark.parametrize(
    "reason",
    ["connector_disabled", "connector_identity_disabled", "connector_identity_not_dedicated"],
)
def test_disabled_or_unsafe_source_identity_requires_tenant_repair(env, connected, reason):
    service, connector, space, operator, identities = connected
    if reason == "connector_disabled":
        service.disable(env.owner, connector)
    else:
        with psycopg.connect(env.admin_dsn) as admin:
            if reason == "connector_identity_disabled":
                admin.execute(
                    "UPDATE mnemion.principals SET disabled_at=now() WHERE tenant_id=%s AND id=%s",
                    (env.owner.tenant_id, operator.principal_id),
                )
            else:
                admin.execute(
                    "UPDATE mnemion.principals SET administrator=true WHERE tenant_id=%s AND id=%s",
                    (env.owner.tenant_id, operator.principal_id),
                )
    item = service.health(env.owner, details=True)["diagnostics"]["items"][0]
    assert item["space_id"] == str(space) and reason in item["reasons"]
    assert not item["can_resume"] and not item["can_request_sync"]
    assert item["recovery"] == (
        "enable_connector" if reason == "connector_disabled" else "restore_connector_identity"
    )
    assert service.health(identities["reader"][0], details=True)["diagnostics"]["items"] == []
