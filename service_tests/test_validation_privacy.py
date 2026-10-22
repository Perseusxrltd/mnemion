"""Submitted object names are private too, across HTTP and MCP validation."""

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from mnemion.service.api import create_app
from mnemion.service.mcp_transport import MnemionMCPServer


class ValidationChild(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int


class ValidationBody(BaseModel):
    children: list[ValidationChild]
    numbers: dict[str, int]


def test_http_sensitive_routes_do_not_reflect_extra_property_names_or_values(env, caplog):
    name, value = "PRIVATE_PROPERTY_NAME_漢字", "PRIVATE_PROPERTY_VALUE"
    app = create_app(env.db, env.embedder, mcp_enabled=False, studio_enabled=False)
    with TestClient(app) as client:
        for method, path in [
            ("PUT", f"/v1/vault/entries/{uuid4()}"),
            ("POST", "/v1/vault/export"),
            ("POST", "/v1/vault/import"),
            ("POST", "/v1/vault/keepass/preview"),
            ("POST", "/v1/vault/keepass/export"),
        ]:
            response = client.request(
                method, path, headers={"Authorization": "Bearer " + env.token}, json={name: value}
            )
            assert response.status_code == 422
            assert name not in response.text and value not in response.text
            assert response.json()["error"]["code"] == "invalid_request"
            assert response.json()["request_id"] == response.headers["X-Request-ID"]
            assert response.headers["Cache-Control"] == "no-store"
    assert name not in caplog.text and value not in caplog.text


def test_http_nested_locations_and_many_errors_remain_bounded_and_useful(env):
    app = create_app(env.db, env.embedder, mcp_enabled=False, studio_enabled=False)

    @app.post("/fixture/validation")
    def validate(command: ValidationBody):
        raise AssertionError("Invalid synthetic input must not invoke a handler")

    name, value = "PRIVATE_NESTED_PROPERTY_" + "漢" * 300, "PRIVATE_NESTED_VALUE"
    body = {"children": [{name: value}], "numbers": {name + str(i): value for i in range(100)}}
    with TestClient(app) as client:
        response = client.post("/fixture/validation", json=body)
    assert response.status_code == 422 and len(response.content) < 8192
    assert name not in response.text and value not in response.text
    fields = response.json()["error"]["fields"]
    assert len(fields) <= 20
    assert {"field": "body.children.0.value", "type": "missing"} in fields


def test_mcp_validation_uses_only_registered_schema_property_names(caplog):
    server = MnemionMCPServer("validation-fixture", api_url="https://example.invalid")

    @server.tool()
    def inspect_fixture(payload: ValidationBody) -> dict:
        raise AssertionError("Invalid synthetic input must not invoke a tool")

    name, value = "PRIVATE_MCP_PROPERTY_漢字", "PRIVATE_MCP_VALUE"
    result = asyncio.run(
        server.call_tool(
            "inspect_fixture", {"payload": {"children": [{name: value}], "numbers": {name: value}}}
        )
    )
    assert result.is_error and result.structured_content["code"] == "invalid_arguments"
    assert name not in str(result) and value not in str(result)
    assert name not in caplog.text and value not in caplog.text
