"""Tests for Studio backend cross-origin guardrails."""

import io
import zipfile

from fastapi.testclient import TestClient

from studio.backend import main as studio_main
from studio.backend.main import STUDIO_TOKEN_HEADER, app


class FakeCollection:
    def get(self, **kwargs):
        return {
            "ids": ["drawer_one"],
            "documents": ["Studio Obsidian export content."],
            "metadatas": [{"wing": "project", "room": "notes", "trust_status": "current"}],
        }


def _preflight(origin: str, method: str = "POST"):
    client = TestClient(app)
    return client.options(
        "/api/drawer",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
        },
    )


def test_cors_allows_vite_dev_origin():
    response = _preflight("http://localhost:5173")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rejects_unexpected_localhost_port():
    response = _preflight("http://localhost:9999")

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_allows_electron_file_origin():
    response = _preflight("file://")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "file://"


def test_mutating_request_requires_token_when_configured(monkeypatch):
    monkeypatch.setenv("MNEMION_STUDIO_TOKEN", "secret-token")
    client = TestClient(app)

    response = client.post("/api/drawer", json={})

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


def test_mutating_request_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("MNEMION_STUDIO_TOKEN", "secret-token")
    client = TestClient(app)

    response = client.post(
        "/api/drawer",
        json={},
        headers={STUDIO_TOKEN_HEADER: "wrong-token"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


def test_mutating_request_with_valid_token_reaches_endpoint_validation(monkeypatch):
    monkeypatch.setenv("MNEMION_STUDIO_TOKEN", "secret-token")
    client = TestClient(app)

    response = client.post(
        "/api/drawer",
        json={},
        headers={STUDIO_TOKEN_HEADER: "secret-token"},
    )

    assert response.status_code == 422


def test_read_only_request_does_not_require_token(monkeypatch):
    monkeypatch.setenv("MNEMION_STUDIO_TOKEN", "secret-token")
    client = TestClient(app)

    response = client.get("/api/docs")

    assert response.status_code == 200


def test_cors_preflight_does_not_require_token(monkeypatch):
    monkeypatch.setenv("MNEMION_STUDIO_TOKEN", "secret-token")

    response = _preflight("http://localhost:5173")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_obsidian_status_endpoint_returns_status(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    monkeypatch.setattr(studio_main, "_obsidian_vault_path", lambda: vault, raising=False)
    monkeypatch.setattr(
        studio_main,
        "obsidian_vault_status",
        lambda path: {"vault_path": str(path), "exists": False, "registered": False},
        raising=False,
    )
    client = TestClient(app)

    response = client.get("/api/obsidian/status")

    assert response.status_code == 200
    assert response.json()["vault_path"] == str(vault)


def test_obsidian_sync_endpoint_requires_valid_token_and_calls_renderer(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    calls = []
    monkeypatch.setenv("MNEMION_STUDIO_TOKEN", "secret-token")
    monkeypatch.setattr(studio_main, "_obsidian_vault_path", lambda: vault, raising=False)
    monkeypatch.setattr(
        studio_main, "_obsidian_kg_path", lambda: tmp_path / "kg.sqlite3", raising=False
    )
    monkeypatch.setattr(studio_main, "_get_collection", lambda: FakeCollection())
    monkeypatch.setattr(
        studio_main,
        "obsidian_sync_vault",
        lambda vault_path, collection, kg_db_path: (
            calls.append((vault_path, collection, kg_db_path))
            or {"status": "synced", "vault_path": str(vault_path)}
        ),
        raising=False,
    )
    client = TestClient(app)

    forbidden = client.post("/api/obsidian/sync")
    allowed = client.post(
        "/api/obsidian/sync",
        headers={STUDIO_TOKEN_HEADER: "secret-token"},
    )

    assert forbidden.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "synced"
    assert calls and calls[0][0] == vault


def test_obsidian_open_endpoint_uses_open_helper(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    calls = []
    monkeypatch.setenv("MNEMION_STUDIO_TOKEN", "secret-token")
    monkeypatch.setattr(studio_main, "_obsidian_vault_path", lambda: vault, raising=False)
    monkeypatch.setattr(
        studio_main,
        "obsidian_register_vault",
        lambda path: calls.append(("register", path)) or {"registered": True},
        raising=False,
    )
    monkeypatch.setattr(
        studio_main,
        "obsidian_open_vault",
        lambda path: (
            calls.append(("open", path))
            or {"opened": True, "vault_path": str(path), "uri": "obsidian://open"}
        ),
        raising=False,
    )
    client = TestClient(app)

    response = client.post(
        "/api/obsidian/open",
        headers={STUDIO_TOKEN_HEADER: "secret-token"},
    )

    assert response.status_code == 200
    assert response.json()["opened"] is True
    assert calls == [("register", vault), ("open", vault)]


def test_export_vault_zip_uses_managed_obsidian_renderer(monkeypatch, tmp_path):
    monkeypatch.setattr(studio_main, "_get_collection", lambda: FakeCollection())
    monkeypatch.setattr(
        studio_main, "_obsidian_kg_path", lambda: tmp_path / "kg.sqlite3", raising=False
    )
    client = TestClient(app)

    response = client.get("/api/export/vault")

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        names = set(zf.namelist())
        assert "Mnemion.md" in names
        assert ".mnemion-obsidian-manifest.json" in names
        assert any(name.endswith(".md") and "drawer_one" in name for name in names)


def test_source_status_endpoint_returns_stats(monkeypatch, tmp_path):
    monkeypatch.setattr(
        studio_main,
        "SourceStore",
        lambda: type("FakeSourceStore", (), {"stats": lambda self: {"sources": 1}})(),
        raising=False,
    )
    client = TestClient(app)

    response = client.get("/api/sources/status")

    assert response.status_code == 200
    assert response.json()["sources"] == 1


def test_wiki_context_pack_endpoint_uses_token_guard(monkeypatch):
    monkeypatch.setenv("MNEMION_STUDIO_TOKEN", "secret-token")
    monkeypatch.setattr(
        studio_main,
        "build_wiki_context_pack",
        lambda **kwargs: {"query": kwargs["query"], "wiki_pages": []},
        raising=False,
    )
    client = TestClient(app)

    forbidden = client.post("/api/wiki/context-pack", json={"query": "hybrid retrieval"})
    allowed = client.post(
        "/api/wiki/context-pack",
        json={"query": "hybrid retrieval"},
        headers={STUDIO_TOKEN_HEADER: "secret-token"},
    )

    assert forbidden.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["query"] == "hybrid retrieval"
