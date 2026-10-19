"""Operator setup errors remain actionable without echoing submitted secrets."""

import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from mnemion.connectors import runner
from mnemion.connectors.config import ConnectorConfig
from mnemion.service.api import create_app
from mnemion.service.connector_models import ConnectorInput


def configuration(tmp_path):
    return {
        "service_url": "http://127.0.0.1",
        "service_token": {"env": "UNUSED_FIXTURE_TOKEN"},
        "connector_id": str(uuid4()),
        "provider": {
            "type": "filesystem",
            "path": str(tmp_path),
            "name": "Fixture source",
            "scope_id": "fixture",
            "members": [],
            "publish_to_mapped_members": True,
        },
    }


@pytest.mark.parametrize("provider", ["provider", "published"])
def test_access_mode_cannot_be_mistaken_for_provider_at_registration(env, provider):
    with TestClient(create_app(env.db, env.embedder, studio_enabled=False)) as client:
        response = client.post(
            "/v1/connectors",
            headers={"Authorization": "Bearer " + env.token},
            json={
                "name": "synthetic-private-name",
                "provider": provider,
                "principal_id": str(uuid4()),
            },
        )
    assert response.status_code == 422
    assert "access_mode" in response.json()["error"]["message"]
    assert "filesystem" in response.json()["error"]["message"]
    assert "synthetic-private-name" not in response.text
    assert (
        ConnectorInput(name="Custom source", provider="company-crm", principal_id=uuid4()).provider
        == "company-crm"
    )


@pytest.mark.parametrize(
    "problem,code",
    [
        ({"provider": "published"}, "connector_provider_mismatch"),
        ({"access_mode": "provider"}, "connector_access_mode_mismatch"),
        ({"disabled_at": "2026-01-01T00:00:00Z"}, "connector_identity_unavailable"),
    ],
)
def test_runner_stops_before_source_access_with_a_fixed_setup_diagnostic(tmp_path, problem, code):
    config = ConnectorConfig.model_validate(configuration(tmp_path))

    class Source:
        access_mode = "published"

        def scopes(self):
            raise AssertionError("Misconfigured runners must not read source contents")

    class Service:
        def request(self, method, path):
            assert method == "GET" and path == "/v1/connectors"
            return {
                "items": [
                    {
                        "id": str(config.connector_id),
                        "provider": "filesystem",
                        "access_mode": "published",
                        "disabled_at": None,
                        **problem,
                    }
                ]
            }

    with pytest.raises(runner.ConnectorConfigurationError) as caught:
        runner._scan(config, adapter=Source(), client=Service())
    assert caught.value.code == code
    assert str(caught.value) == runner.ConnectorConfigurationError.MESSAGES[code]


def test_cli_token_reference_hint_does_not_expose_a_pasted_credential(tmp_path, capsys):
    config = configuration(tmp_path)
    config["service_token"] = "synthetic-pasted-token-never-returned"
    path = tmp_path / "connector.json"
    path.write_text(json.dumps(config))
    assert runner.main(["--config", str(path)]) == 2
    captured = capsys.readouterr()
    report = json.loads(captured.err)
    assert report["error"] == "invalid_config"
    assert report["hints"][0]["field"] == "service_token"
    assert "file" in report["hints"][0]["message"] and "env" in report["hints"][0]["message"]
    assert config["service_token"] not in captured.err + captured.out
