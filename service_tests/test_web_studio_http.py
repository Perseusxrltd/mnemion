"""Bundled Studio is visible by default without weakening memory authentication."""

import json
import pytest

from fastapi.testclient import TestClient

from client_tests.test_web_studio import make_bundle
from mnemion.service import studio
from mnemion.service.api import create_app
from mnemion.service.cli import main


def installed(monkeypatch, tmp_path):
    package = tmp_path / "site-packages/mnemion"
    monkeypatch.setattr(studio, "__file__", str(package / "service/studio.py"))
    monkeypatch.delenv("MNEMION_STUDIO_DIST", raising=False)
    monkeypatch.delenv("MNEMION_STUDIO_ENABLED", raising=False)
    return package


def test_packaged_studio_serves_routes_and_assets_but_never_private_api(env, tmp_path, monkeypatch):
    package = installed(monkeypatch, tmp_path)
    make_bundle(package / "_studio")
    assert studio.studio_status()["source"] == "bundled"
    assert studio.studio_status()["build_command"] is None
    with TestClient(create_app(env.db, env.embedder)) as client:
        for route in ("/", "/workspace", "/workspace/help", "/help", "/privacy", "/oauth/consent"):
            page = client.get(route)
            assert page.status_code == 200 and 'src="/assets/app.js"' in page.text
            assert "frame-ancestors 'none'" in page.headers["Content-Security-Policy"]
            assert env.token not in page.text
            assert 'name="mnemion-product-telemetry-policy"' in page.text
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/v1/me").status_code == 401
        assert client.get("/v1/missing-route").status_code == 404
        assert client.get("/assets/%2e%2e/release.json").status_code == 404
    monkeypatch.setenv("MNEMION_STUDIO_ENABLED", "0")
    with TestClient(create_app(env.db, env.embedder)) as client:
        assert client.get("/").status_code == 404
        assert client.get("/health/ready").status_code == 200


def test_company_studio_connection_policy_applies_to_all_entry_routes(env, tmp_path, monkeypatch):
    package = installed(monkeypatch, tmp_path)
    make_bundle(package / "_studio")
    monkeypatch.setenv("MNEMION_STUDIO_CONNECT_ORIGINS", '["https://memory.example"]')
    status = studio.studio_status()["browser_connections"]
    assert status == {"profile": "restricted", "origins": ["https://memory.example"]}
    with TestClient(create_app(env.db, env.embedder)) as client:
        for route in ("/", "/workspace", "/workspace/help", "/help", "/privacy", "/oauth/consent"):
            page = client.get(route)
            assert page.status_code == 200
            assert (
                "connect-src 'self' https://memory.example;"
                in page.headers["Content-Security-Policy"]
            )
            assert "https:" not in page.headers["Content-Security-Policy"].replace(
                "https://memory.example", ""
            )
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/v1/me").status_code == 401
    monkeypatch.setenv("MNEMION_STUDIO_CONNECT_ORIGINS", '["https://*.example"]')
    with pytest.raises(ValueError, match="JSON list"):
        create_app(env.db, env.embedder)


def test_browser_telemetry_policy_reads_current_restrictions_without_identity(
    env, tmp_path, monkeypatch
):
    from mnemion.product_telemetry import policy

    package = installed(monkeypatch, tmp_path)
    make_bundle(package / "_studio")
    selected = tmp_path / "company-policy.json"
    monkeypatch.setattr(policy, "company_policy_file", lambda: selected)
    with TestClient(create_app(env.db, env.embedder)) as client:
        page = client.get("/privacy")
        assert "unmanaged" in page.text
        endpoint = "/studio/telemetry-policy"
        response = client.get(endpoint)
        assert response.status_code == 200
        assert response.json() == {
            "state": "unmanaged",
            "enabled": True,
            "metric_groups": list(policy.METRIC_GROUPS),
        }
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert len(response.content) == int(response.headers["Content-Length"]) < 1024
        assert not {"x-request-id", "set-cookie", "etag", "last-modified"} & response.headers.keys()
        selected.write_text(
            json.dumps({"schema_version": 1, "enabled": True, "metric_groups": ["reliability"]})
        )
        narrowed = client.get(endpoint)
        assert narrowed.json() == {
            "state": "restricted",
            "enabled": True,
            "metric_groups": ["reliability"],
        }
        selected.write_text(
            json.dumps({"schema_version": 1, "enabled": False, "metric_groups": []})
        )
        assert client.get(endpoint).json() == {
            "state": "restricted",
            "enabled": False,
            "metric_groups": [],
        }
        selected.write_text('{"private":"PRIVATE_POLICY_SENTINEL"}')
        unreadable = client.get(endpoint)
        assert unreadable.json() == {"state": "unreadable", "enabled": False, "metric_groups": []}
        assert "PRIVATE_POLICY_SENTINEL" not in unreadable.text
        assert client.post(endpoint).status_code == 405
        assert client.get("/v1/me").status_code == 401
    with TestClient(create_app(env.db, env.embedder, studio_enabled=False)) as client:
        assert client.get(endpoint).status_code == 404


def test_unbuilt_source_cli_explains_how_to_enable_studio_without_database(
    monkeypatch, tmp_path, capsys
):
    import uvicorn

    package = installed(monkeypatch, tmp_path)
    root = package.parent
    (root / "studio/frontend").mkdir(parents=True)
    (root / "studio/frontend/package.json").write_text('{"name":"mnemion-studio"}')
    (root / "pyproject.toml").write_text("")
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)
    main(["studio", "status"])
    status = json.loads(capsys.readouterr().out)
    assert not status["available"] and status["build_command"] == "mnemion-service studio build"
    main(["serve"])
    message = json.loads(capsys.readouterr().err)
    assert "mnemion-service studio build" in message["help"]
    main(["serve", "--no-studio"])
    message = json.loads(capsys.readouterr().err)
    assert message["studio"]["source"] == "disabled" and message["help"] is None


@pytest.mark.parametrize("command", ["schema", "agent-schema"])
def test_offline_schema_commands_do_not_require_a_valid_web_build(
    command, tmp_path, monkeypatch, capsys
):
    package = installed(monkeypatch, tmp_path)
    bundle = package / "_studio"
    make_bundle(bundle)
    (bundle / "index.html").write_text("invalidated by a source change")
    with pytest.raises(ValueError):
        studio.resolve_studio()
    output = tmp_path / "contract.json"
    assert main([command, "--output", str(output)]) == 0
    assert isinstance(json.loads(output.read_text()), dict)
    assert "error" not in capsys.readouterr().err
