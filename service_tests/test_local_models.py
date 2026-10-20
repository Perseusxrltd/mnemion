"""Private model enrollment, real loopback HTTP and database-backed space consent."""

import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from mnemion import local_models as models, local_state as state
from mnemion.local_workspace import SetupOptions, registry_for
from mnemion.service.api import create_app
from mnemion.service.errors import ServiceError
from mnemion.service.librarian_models import LibrarianSettingsInput
from mnemion.service.model_registry import ModelRegistry

SECRET = "model-setup-test-only-never-a-live-key"


@pytest.fixture(autouse=True)
def no_external_configuration(monkeypatch):
    for key in ("MNEMION_EMBEDDING_CONFIG", "MNEMION_LIBRARIAN_CONFIG"):
        monkeypatch.delenv(key, raising=False)


def workspace(tmp_path):
    root = state.directory(tmp_path / "Model Équipe")
    settings = {
        "format": 1,
        "workspace_id": str(uuid4()),
        "created_at": "2026-10-20T00:00:00Z",
        **SetupOptions(workspace_name="Model setup", owner_name="Owner").model_dump(),
        "database_port": 17893,
    }
    state.write(root / "configuration.json", settings)
    state.write(root / "credentials.json", {"fixture": "existing identity retained"})
    return root, settings


def definition(kind="embedding", endpoint="http://127.0.0.1:9/v1/embeddings", **changes):
    return {
        "kind": kind,
        "profile": {
            "id": kind,
            "label": "Disposable model",
            "protocol": "openai",
            "endpoint": endpoint,
            "model": "fixture-model",
            "revision": "fixture-immutable-v1",
            **({"dimensions": 2} if kind == "embedding" else {}),
            **changes,
        },
    }


def saving(settings, provider=None, **changes):
    value = {
        "workspace_id": settings["workspace_id"],
        "expected_revision": "not-configured",
        "action": "save",
        "provider": provider or definition(),
        "api_key": SECRET,
        **changes,
    }
    if value["action"] != "save":
        value.pop("provider", None)
        value.pop("api_key", None)
    return models.ModelsChange.model_validate_json(json.dumps(value))


def test_private_profiles_preserve_identity_and_refuse_stale_or_retargeted_keys(tmp_path):
    root, settings = workspace(tmp_path)
    originals = {
        name: (root / name).read_bytes() for name in ("configuration.json", "credentials.json")
    }
    view = models.configure(root, saving(settings))
    assert view["state"] == "configured" and view["providers"][0]["has_api_key"]
    assert SECRET not in json.dumps(view) and SECRET not in repr(saving(settings))
    assert state.read(root / "model-providers.json")["providers"][0]["api_key"] == SECRET
    if os.name != "nt":
        assert (root / "model-providers.json").stat().st_mode & 0o077 == 0
    for command in (
        saving(settings),
        saving({**settings, "workspace_id": str(uuid4())}, expected_revision=view["revision"]),
    ):
        with pytest.raises(state.LocalSetupError, match="changed|current"):
            models.configure(root, command)
    retargeted = definition(endpoint="https://different-provider.invalid/v1/embeddings")
    with pytest.raises(state.LocalSetupError, match="key for the new provider"):
        models.configure(
            root, saving(settings, retargeted, expected_revision=view["revision"], api_key=None)
        )
    renamed = models.configure(
        root,
        saving(
            settings, definition(label="Renamed"), expected_revision=view["revision"], api_key=None
        ),
    )
    assert (
        renamed["providers"][0]["has_api_key"]
        and renamed["providers"][0]["fingerprint"] == view["providers"][0]["fingerprint"]
    )
    updated = models.configure(
        root,
        saving(
            settings,
            retargeted,
            expected_revision=renamed["revision"],
            api_key=None,
            clear_api_key=True,
        ),
    )
    assert not updated["providers"][0]["has_api_key"]
    removed = models.configure(
        root,
        saving(
            settings,
            action="remove",
            kind="embedding",
            profile_id="embedding",
            expected_revision=updated["revision"],
        ),
    )
    assert removed["providers"] == [] and SECRET not in (root / "model-providers.json").read_text()
    for name, before in originals.items():
        assert (root / name).read_bytes() == before


def test_damaged_settings_are_preserved_and_builtin_models_still_load(tmp_path):
    root, settings = workspace(tmp_path)
    bad = b'{"credential":"private-damaged-model-fixture",broken'
    state.write(root / "model-providers.json", {})
    (root / "model-providers.json").write_bytes(bad)
    view = models.inspection(root, settings["workspace_id"])
    assert view["state"] == "configuration_error" and "private-damaged" not in json.dumps(view)
    registry = registry_for(root, settings)
    assert set(registry.profiles) == {"e5-small", "bge-small-en"}
    assert models.librarian_registry(root, settings["workspace_id"]).providers == {}
    registry.close()
    fixed = models.configure(
        root, saving(settings, action="reset", expected_revision=view["revision"])
    )
    assert fixed["state"] == "not_configured"
    copies = [
        p
        for p in root.rglob("*")
        if p.is_file() and p.name != "model-providers.json" and p.read_bytes() == bad
    ]
    assert len(copies) == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"endpoint": "https://user:private-url-fixture@provider.invalid/v1/embeddings"},
        {"endpoint": "http://cloud.invalid/v1/embeddings"},
        {"api_key_env": "UNREVIEWED_EXISTING_KEY"},
        {"id": "e5-small"},
    ],
)
def test_private_cli_rejects_unsafe_profiles_without_echoing_values(tmp_path, patch):
    root, settings = workspace(tmp_path)
    payload = {
        "workspace_id": settings["workspace_id"],
        "expected_revision": "not-configured",
        "action": "save",
        "provider": definition(**patch),
        "api_key": SECRET,
    }
    result = subprocess.run(
        [sys.executable, "-m", "mnemion.service.cli", "local", "models", "--root", str(root)],
        input=json.dumps(payload) + "\n",
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert (
        SECRET not in result.stdout + result.stderr
        and "private-url-fixture" not in result.stdout + result.stderr
    )
    assert not (root / "model-providers.json").exists()


@pytest.fixture
def endpoint_server():
    calls = []
    hold, arrived, release = threading.Event(), threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(
                {"path": self.path, "key": self.headers.get("Authorization"), "body": body}
            )
            if hold.is_set():
                arrived.set()
                release.wait(5)
            if self.path.endswith("embeddings"):
                reply = {
                    "model": body["model"],
                    "data": [
                        {"index": i, "embedding": [3.0, 4.0]} for i, _ in enumerate(body["input"])
                    ],
                }
            elif self.path.endswith("embed"):
                reply = {"model": body["model"], "embeddings": [[3.0, 4.0] for _ in body["input"]]}
            else:
                message = {"role": "assistant", "content": '{"proposals":[]}'}
                reply = (
                    {
                        "model": body["model"],
                        "done": True,
                        "done_reason": "stop",
                        "message": message,
                        "eval_count": 4,
                    }
                    if self.path.endswith("/api/chat")
                    else {
                        "model": body["model"],
                        "choices": [{"finish_reason": "stop", "message": message}],
                        "usage": {"completion_tokens": 4},
                    }
                )
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls, hold, arrived, release
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("protocol", ["openai", "ollama"])
def test_real_http_profiles_load_private_credentials_without_calling_on_save(
    tmp_path, endpoint_server, protocol
):
    root, settings = workspace(tmp_path)
    origin, calls, *_ = endpoint_server
    embedding_path = "/api/embed" if protocol == "ollama" else "/v1/embeddings"
    librarian_path = "/api/chat" if protocol == "ollama" else "/v1/chat/completions"
    first = models.configure(
        root, saving(settings, definition(endpoint=origin + embedding_path, protocol=protocol))
    )
    models.configure(
        root,
        saving(
            settings,
            definition("librarian", origin + librarian_path, protocol=protocol),
            expected_revision=first["revision"],
        ),
    )
    registry = registry_for(root, settings)
    librarian = models.librarian_registry(root, settings["workspace_id"])
    try:
        assert calls == []
        assert registry.default is registry.profiles[settings["embedding_profile"]]
        assert registry.profile("embedding").query("Café 漢字") == pytest.approx([0.6, 0.8])
        result = librarian.get("librarian").generate(
            [{"memory_id": str(uuid4()), "content": "Private local fixture."}],
            "organize",
            reserve=lambda usage: None,
            live=lambda: True,
        )
        assert result.output.proposals == []
        assert len(calls) == 2 and all(call["key"] == "Bearer " + SECRET for call in calls)
        assert [call["path"] for call in calls] == [embedding_path, librarian_path]
        assert SECRET not in json.dumps(registry.describe()) and SECRET not in json.dumps(
            librarian.get("librarian").profile.describe()
        )
    finally:
        registry.close()
        librarian.close()


def test_real_service_lists_profiles_but_enrollment_does_not_enable_cloud_processing(env, tmp_path):
    root, settings = workspace(tmp_path)
    first = models.configure(
        root, saving(settings, definition(endpoint="https://unused-provider.invalid/v1/embeddings"))
    )
    models.configure(
        root,
        saving(
            settings,
            definition("librarian", "https://unused-provider.invalid/v1/chat/completions"),
            expected_revision=first["revision"],
        ),
    )
    registry = ModelRegistry(
        env.embedder,
        {
            "fixture": env.embedder,
            **models.embedding_providers(root, settings["workspace_id"], root / "models"),
        },
    )
    librarian = models.librarian_registry(root, settings["workspace_id"])
    with TestClient(
        create_app(database=env.db, registry=registry, librarian_registry=librarian)
    ) as client:
        headers = {"Authorization": "Bearer " + env.token}
        base = f"/v1/spaces/{env.space}"
        for path, identifier, field in [
            ("/embedding", "embedding", "profiles"),
            ("/librarian/models", "librarian", "items"),
        ]:
            response = client.get(base + path, headers=headers)
            assert response.status_code == 200 and any(
                item["id"] == identifier for item in response.json()[field]
            )
            assert SECRET not in response.text
        current = client.get(base + "/librarian", headers=headers).json()
        assert not current["enabled"] and current["profile_id"] is None
        denied = client.put(
            base + "/librarian",
            headers=headers,
            json=LibrarianSettingsInput(
                expected_version=current["version"], profile_id="librarian"
            ).model_dump(),
        )
        assert (
            denied.status_code == 422
            and denied.json()["error"]["code"] == "network_approval_required"
        )
        assert client.post("/v1/model-providers", headers=headers, json={}).status_code == 404
        assert registry.profile("embedding").snapshot()["requests"] == 0
    registry.close()


def test_explicit_host_environment_profiles_are_not_overwritten(tmp_path, monkeypatch):
    root, settings = workspace(tmp_path)
    monkeypatch.setenv("MNEMION_LIBRARIAN_CONFIG", str(tmp_path / "operator-managed.json"))
    view = models.inspection(root, settings["workspace_id"])
    assert view["state"] == "external" and not view["repairable"]
    with pytest.raises(state.LocalSetupError, match="environment configuration"):
        models.configure(root, saving(settings))
    assert not (root / "model-providers.json").exists()


def test_shared_inference_honors_the_approved_endpoint_queue_limit(tmp_path, endpoint_server):
    root, settings = workspace(tmp_path)
    origin, calls, hold, arrived, release = endpoint_server
    models.configure(
        root, saving(settings, definition(endpoint=origin + "/v1/embeddings", max_queued=0))
    )
    registry = registry_for(root, settings)
    model = registry.profile("embedding")
    hold.set()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(model.query, "First bounded request")
            try:
                assert arrived.wait(3)
                with pytest.raises(ServiceError) as rejected:
                    model.query("Second request must not reach the provider")
                assert rejected.value.code == "inference_busy"
                assert len(calls) == 1
            finally:
                release.set()
            assert first.result(timeout=3) == pytest.approx([0.6, 0.8])
        assert registry.inference_gate.snapshot()["active"] == 0
    finally:
        release.set()
        registry.close()
