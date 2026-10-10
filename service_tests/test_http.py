from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from mnemion.service.api import create_app
from mnemion.service.models import KeyInput, PrincipalInput


def test_http_save_search_citation_correction_and_forget(env):
    with TestClient(create_app(env.db, env.embedder)) as client:
        auth = {"Authorization": "Bearer " + env.token}
        assert client.get("/health/ready").status_code == 200
        assert client.get("/v1/me").status_code == 401
        saved = client.post(
            f"/v1/spaces/{env.space}/memories",
            headers={**auth, "Idempotency-Key": "http-save"},
            json={"content": "Billing uses Postgres"},
        )
        assert saved.status_code == 202, saved.text
        memory = saved.json()["memory_id"]
        operations = client.get(f"/v1/spaces/{env.space}/operations?state=accepted", headers=auth)
        assert (
            operations.status_code == 200 and operations.json()["items"][0]["memory_id"] == memory
        )
        result = client.post(
            "/v1/recall",
            headers=auth,
            json={"query": "billing", "space_ids": [str(env.space)], "mode": "lexical"},
        )
        assert result.status_code == 200, result.text
        assert result.json()["hits"][0]["memory_id"] == memory
        source_id = result.json()["hits"][0]["evidence"]["source_revision_id"]
        assert (
            client.get(f"/v1/sources/{source_id}", headers=auth).json()["content"]
            == "Billing uses Postgres"
        )
        revision = client.post(
            f"/v1/memories/{memory}/revisions",
            headers={**auth, "Idempotency-Key": "http-revise"},
            json={
                "content": "Billing uses Postgres replicas",
                "expected_version": 1,
                "reason": "Replicas added",
            },
        )
        assert revision.status_code == 202, revision.text
        deleted = client.delete(
            f"/v1/memories/{memory}?expected_version=2",
            headers={**auth, "Idempotency-Key": "http-delete"},
        )
        assert deleted.status_code == 202, deleted.text
        assert client.get(f"/v1/memories/{memory}", headers=auth).status_code == 404
        assert client.get(f"/v1/sources/{source_id}", headers=auth).status_code == 404
        assert "X-Request-ID" in result.headers
        assert result.headers["Cache-Control"] == "no-store"
        assert result.json()["request_id"] == result.headers["X-Request-ID"]
        schema = client.get("/openapi.json").json()
        assert "security" in schema["paths"]["/v1/recall"]["post"]
        assert schema["paths"]["/v1/recall"]["post"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"].endswith("/Recall")


def test_http_payload_validation_and_inaccessible_metadata(env):
    principal = env.identities.create_principal(env.owner, PrincipalInput(name="No access"))
    key = env.identities.create_key(env.owner, UUID(principal["id"]), KeyInput(name="Unscoped"))
    with TestClient(create_app(env.db, env.embedder)) as client:
        auth = {"Authorization": "Bearer " + key["api_key"]}
        assert client.get(f"/v1/spaces/{env.space}/memories", headers=auth).status_code == 404
        assert client.get(f"/v1/spaces/{env.space}/status", headers=auth).status_code == 404
        assert client.get(f"/v1/spaces/{env.space}/operations", headers=auth).status_code == 404
        assert client.get(f"/v1/operations/{uuid4()}", headers=auth).status_code == 404
        assert (
            client.post(
                "/v1/recall", headers=auth, json={"query": "guess", "space_ids": [str(env.space)]}
            ).status_code
            == 404
        )
        owner = {"Authorization": "Bearer " + env.token, "Idempotency-Key": "invalid"}
        body = {"content": "Cannot select tenant", "tenant_id": str(uuid4())}
        invalid = client.post(f"/v1/spaces/{env.space}/memories", headers=owner, json=body)
        assert invalid.status_code == 422 and invalid.json()["error"]["code"] == "invalid_request"
        assert body["content"] not in invalid.text and body["tenant_id"] not in invalid.text
        assert (
            client.post(
                f"/v1/spaces/{env.space}/memories", headers=owner, content=b"x" * 2_000_001
            ).status_code
            == 413
        )
        assert (
            client.post(
                f"/v1/spaces/{env.space}/memories",
                headers=owner,
                json={"content": "Null\u0000byte"},
            ).status_code
            == 422
        )
