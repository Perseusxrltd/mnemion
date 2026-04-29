"""Tests for Studio backend cross-origin guardrails."""

from fastapi.testclient import TestClient

from studio.backend.main import STUDIO_TOKEN_HEADER, app


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


def test_status_exposes_vector_disabled_health(monkeypatch):
    from studio.backend import main

    monkeypatch.setattr(
        main,
        "hnsw_capacity_status",
        lambda *_args, **_kwargs: {
            "status": "diverged",
            "sqlite_count": 2501,
            "hnsw_count": 1,
            "divergence": 2500,
            "diverged": True,
            "message": "repair needed",
        },
    )
    monkeypatch.setattr(
        main,
        "sqlite_metadata_summary",
        lambda *_args, **_kwargs: {
            "total_drawers": 2501,
            "wing_count": 1,
            "room_count": 1,
            "wings": {"ops": 2501},
            "rooms": {"repair": 2501},
            "metadata_unavailable": False,
            "metadata_message": "from sqlite",
        },
    )
    client = TestClient(app)

    response = client.get("/api/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["vector_disabled"] is True
    assert payload["health"]["status"] == "diverged"
    assert payload["wing_count"] == 1
    assert payload["wings"] == {"ops": 2501}
    assert payload["repair_command"] == "mnemion repair --mode rebuild"


def test_status_recomputes_health_and_does_not_reuse_stale_divergence(monkeypatch):
    from studio.backend import main

    states = [
        {
            "status": "diverged",
            "sqlite_count": 3,
            "hnsw_count": 1,
            "divergence": 2,
            "diverged": True,
            "message": "repair needed",
        },
        {
            "status": "ok",
            "sqlite_count": 3,
            "hnsw_count": 3,
            "divergence": 0,
            "diverged": False,
            "message": "ok",
        },
    ]

    def next_health(*_args, **_kwargs):
        return (
            states.pop(0)
            if states
            else {
                "status": "ok",
                "sqlite_count": 3,
                "hnsw_count": 3,
                "divergence": 0,
                "diverged": False,
                "message": "ok",
            }
        )

    class FakeCollection:
        def count(self):
            return 3

        def get(self, **kwargs):
            return {
                "ids": ["a", "b", "c"],
                "metadatas": [
                    {"wing": "ops", "room": "repair"},
                    {"wing": "ops", "room": "repair"},
                    {"wing": "notes", "room": "planning"},
                ],
            }

    class FakeClient:
        def get_collection(self, _name):
            return FakeCollection()

    monkeypatch.setattr(main, "hnsw_capacity_status", next_health)
    monkeypatch.setattr(main, "make_persistent_client", lambda *_args, **_kwargs: FakeClient())
    monkeypatch.setattr(main, "_collection", None)
    monkeypatch.setattr(main, "_chroma_client", None)
    client = TestClient(app)

    first = client.get("/api/status").json()
    second = client.get("/api/status").json()

    assert first["vector_disabled"] is True
    assert second["vector_disabled"] is False
    assert second["health"]["status"] == "ok"
    assert second["wing_count"] == 2
