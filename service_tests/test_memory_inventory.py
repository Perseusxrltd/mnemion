"""Bounded inventories retain access checks and the full-fetch compatibility path."""

import json
from uuid import UUID

from fastapi.testclient import TestClient

from mnemion.service.api import create_app
from mnemion.service.models import GrantInput, KeyInput, MemoryInput, PrincipalInput, ReviewInput
from service_tests.test_mcp_compatibility import call


def test_summary_inventory_pages_large_memories_without_content_or_metadata(env):
    command = MemoryInput(
        content="PRIVATE_CONTENT_SENTINEL " + "billing evidence " * 400,
        subject="🧠" * 500,
        metadata={"private_inventory_field": "PRIVATE_METADATA_SENTINEL" * 100},
    )
    saved = [
        env.memory.save(env.owner, env.space, command, f"inventory-{index}") for index in range(101)
    ]
    with TestClient(create_app(env.db, env.embedder), base_url="http://127.0.0.1") as client:
        client.headers["Authorization"] = "Bearer " + env.token
        path = f"/v1/spaces/{env.space}/memories"
        first = client.get(path, params={"summary": True, "limit": 100})
        assert first.status_code == 200, first.text
        page = first.json()
        assert len(page["items"]) == 100 and page["next_cursor"]
        assert len(first.content) < 128 * 1024
        # MCP serializers may escape Unicode. That representation must also fit.
        assert len(json.dumps(page, ensure_ascii=True).encode()) < 128 * 1024
        assert "PRIVATE_" not in first.text
        for item in page["items"]:
            assert not ({"content", "metadata", "evidence"} & item.keys())
            assert item["subject"] == "🧠" * 40 and item["subject_truncated"]
            assert item["created_by"] == str(env.owner.principal_id)
            assert item["recorded_at"] and item["review_state"] == "ordinary"
            assert item["version"] == item["revision_version"] == 1
        second = client.get(
            path, params={"summary": True, "limit": 100, "cursor": page["next_cursor"]}
        )
        assert second.status_code == 200, second.text
        remainder = second.json()
        assert len(remainder["items"]) == 1 and remainder["next_cursor"] is None
        assert {item["memory_id"] for item in page["items"] + remainder["items"]} == {
            item["memory_id"] for item in saved
        }
        fetched = client.get(f"/v1/memories/{saved[0]['memory_id']}")
        assert fetched.status_code == 200
        assert fetched.json()["subject"] == command.subject
        assert fetched.json()["content"] == command.content
        default = client.get(path, params={"limit": 1})
        assert (
            default.status_code == 200 and default.json()["items"][0]["content"] == command.content
        )
        full = call(
            client,
            env.token,
            "mnemion",
            {
                "action": "read",
                "operation": "memories.list",
                "request": {"parameters": {"space_id": str(env.space), "limit": 100}},
            },
        )
        assert full["isError"] and full["structuredContent"]["code"] == "response_too_large"
        compact = call(
            client,
            env.token,
            "mnemion",
            {
                "action": "read",
                "operation": "memories.list",
                "max_response_bytes": 131072,
                "request": {
                    "parameters": {"space_id": str(env.space), "limit": 100, "summary": True}
                },
            },
        )
        assert not compact["isError"], compact
        assert len(compact["structuredContent"]["result"]["items"]) == 100
        assert "PRIVATE_" not in json.dumps(compact)


def test_summary_inventory_rechecks_review_state_source_visibility_and_revocation(env):
    person = env.identities.create_principal(env.owner, PrincipalInput(name="Inventory reviewer"))
    key = env.identities.create_key(env.owner, UUID(person["id"]), KeyInput(name="Inventory"))
    reviewer = env.db.authenticate(key["api_key"])
    env.identities.grant(env.owner, env.space, reviewer.principal_id, GrantInput(role="reviewer"))
    saved = [
        env.memory.save(
            env.owner, env.space, MemoryInput(content=f"Inventory record {i}"), f"s-{i}"
        )
        for i in range(3)
    ]
    env.memory.review(
        env.owner,
        UUID(saved[0]["memory_id"]),
        ReviewInput(expected_version=1, state="quarantined", reason="Review required"),
    )
    with TestClient(create_app(env.db, env.embedder)) as client:
        client.headers["Authorization"] = "Bearer " + key["api_key"]
        path = f"/v1/spaces/{env.space}/memories"
        ordinary = client.get(path, params={"summary": True}).json()["items"]
        assert {row["memory_id"] for row in ordinary} == {row["memory_id"] for row in saved[1:]}
        reviewed = client.get(path, params={"summary": True, "review": True}).json()["items"]
        assert len(reviewed) == 3
        first = client.get(path, params={"summary": True, "limit": 1}).json()
        assert first["next_cursor"]
        env.identities.revoke_grant(env.owner, env.space, reviewer.principal_id)
        assert (
            client.get(path, params={"summary": True, "cursor": first["next_cursor"]}).status_code
            == 404
        )
    # A missing source is never turned into a visible inventory entry.
    with env.db.transaction(env.owner) as conn:
        conn.execute(
            """UPDATE mnemion.sources SET deleted_at=now() WHERE id=(
                SELECT sr.source_id FROM mnemion.memory_revisions r
                JOIN mnemion.source_revisions sr ON sr.tenant_id=r.tenant_id
                  AND sr.space_id=r.space_id AND sr.id=r.source_revision_id
                WHERE r.id=%s)""",
            (UUID(saved[1]["revision_id"]),),
        )
    assert [
        row["memory_id"] for row in env.memory.list(env.owner, env.space, summary=True)["items"]
    ] == [saved[2]["memory_id"]]
