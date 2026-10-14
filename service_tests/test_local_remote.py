"""Operator isolation, public-route evidence and local access during an outage."""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
import pytest

from mnemion import local_remote as remote, local_state as state
from mnemion.local_workspace import SetupOptions
from mnemion.service.api import create_app
from mnemion.service.hosted_oauth import HostedOAuthSettings

ORIGIN = "https://memory.example.test"
TOKEN = "fixture-provider-authtoken-kept-only-in-private-state"


def workspace(tmp_path):
    root = state.directory(tmp_path / "Workspace Équipe")
    settings = {
        "format": 1,
        "workspace_id": str(uuid4()),
        "created_at": "2026-10-14T00:00:00Z",
        **SetupOptions(workspace_name="Shared memories", owner_name="Owner").model_dump(),
        "database_port": 17893,
    }
    state.write(root / "configuration.json", settings)
    state.write(root / "credentials.json", {"fixture": "preserve the existing identity"})
    return root, settings


def change(settings, **values):
    return remote.RemoteChange.model_validate_json(
        json.dumps(
            {
                "workspace_id": settings["workspace_id"],
                "expected_revision": "not-configured",
                "mode": "ngrok",
                "public_url": ORIGIN,
                "ngrok_authtoken": TOKEN,
                **values,
            }
        )
    )


def test_private_token_and_workspace_survive_reconfiguration_without_entering_status(tmp_path):
    root, settings = workspace(tmp_path)
    original = {
        name: (root / name).read_bytes() for name in ("configuration.json", "credentials.json")
    }
    saved = remote.configure(root, change(settings))
    assert saved["has_ngrok_authtoken"] and TOKEN not in json.dumps(saved)
    assert state.read(root / "remote-access.json")["ngrok_authtoken"] == TOKEN
    view = remote.inspection(root, settings["workspace_id"])
    assert view["state"] == "unchecked" and TOKEN not in json.dumps(view)
    if os.name != "nt":
        assert (root / "remote-access.json").stat().st_mode & 0o077 == 0
    updated = remote.configure(
        root, change(settings, expected_revision=saved["revision"], ngrok_authtoken=None)
    )
    assert updated["has_ngrok_authtoken"]
    disabled = remote.configure(
        root,
        change(
            settings, expected_revision=updated["revision"], mode="disabled", ngrok_authtoken=None
        ),
    )
    assert disabled["public_url"] is None and not disabled["has_ngrok_authtoken"]
    assert TOKEN not in (root / "remote-access.json").read_text()
    for name, content in original.items():
        assert (root / name).read_bytes() == content


def test_stale_revision_wrong_workspace_and_interrupted_replacement_keep_previous_settings(
    tmp_path, monkeypatch
):
    root, settings = workspace(tmp_path)
    saved = remote.configure(root, change(settings))
    previous = (root / "remote-access.json").read_bytes()
    for command in (
        change(settings),
        change(settings, workspace_id=str(uuid4()), expected_revision=saved["revision"]),
    ):
        with pytest.raises(state.LocalSetupError, match="workspace|settings"):
            remote.configure(root, command)
        assert (root / "remote-access.json").read_bytes() == previous

    def interrupted(*args):
        raise OSError("simulated interrupted atomic replacement")

    monkeypatch.setattr(os, "replace", interrupted)
    with pytest.raises(OSError):
        remote.configure(
            root, change(settings, expected_revision=saved["revision"], mode="disabled")
        )
    assert (root / "remote-access.json").read_bytes() == previous


def test_damaged_settings_fail_closed_and_can_be_repaired_without_losing_original_bytes(tmp_path):
    root, settings = workspace(tmp_path)
    remote.configure(root, change(settings))
    damaged = b'{"ngrok_authtoken":"' + TOKEN.encode()
    (root / "remote-access.json").write_bytes(damaged)
    view = remote.inspection(root, settings["workspace_id"])
    assert view["state"] == "configuration_error" and view["repairable"]
    assert TOKEN not in json.dumps(view)
    access = remote.RemoteAccess(root, settings, str(uuid4()), lambda event: None)
    assert access.public_url is None and access.oauth is None
    remote.configure(root, change(settings, expected_revision=view["revision"], mode="disabled"))
    copies = list((root / "recovery").glob("remote-*.bin"))
    assert len(copies) == 1 and copies[0].read_bytes() == damaged
    assert remote.inspection(root, settings["workspace_id"])["state"] == "disabled"


def test_operator_cli_accepts_private_stdin_but_never_a_running_workspace(tmp_path):
    root, settings = workspace(tmp_path)
    args = [sys.executable, "-m", "mnemion.service.cli", "local", "remote", "--root", str(root)]
    payload = change(settings).model_dump(mode="json")
    payload["ngrok_authtoken"] = TOKEN
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    with state.lock(root):
        refused = subprocess.run(
            args,
            input=json.dumps(payload),
            env=environment,
            text=True,
            capture_output=True,
            timeout=20,
        )
    assert refused.returncode != 0
    assert json.loads(refused.stdout)["code"] == "workspace_busy"
    assert not (root / "remote-access.json").exists()
    accepted = subprocess.run(
        args, input=json.dumps(payload), env=environment, text=True, capture_output=True, timeout=20
    )
    assert accepted.returncode == 0, accepted.stdout
    assert json.loads(accepted.stdout)["remote_access"]["has_ngrok_authtoken"]
    assert TOKEN not in accepted.stdout + accepted.stderr + refused.stdout + refused.stderr


@pytest.mark.parametrize(
    "url",
    [
        "http://memory.example.test",
        "https://user:secret@memory.example.test",
        "https://memory.example.test/other",
        "https://memory.example.test/?credential=secret",
        "https://memory.example.test/#secret",
    ],
)
def test_operator_rejects_ambiguous_or_credential_bearing_origins(tmp_path, url):
    _, settings = workspace(tmp_path)
    with pytest.raises(ValueError):
        change(settings, public_url=url)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://[0:0:0:0:0:0:0:1]:443/mcp", "https://[::1]"),
        ("https://127.1:443", "https://127.0.0.1"),
        ("https://MEMORY.example.test:443/mcp/", ORIGIN),
    ],
)
def test_operator_origin_remains_browser_compatible_after_save_and_reload(tmp_path, url, expected):
    root, settings = workspace(tmp_path)
    saved = remote.configure(
        root, change(settings, mode="proxy", public_url=url, ngrok_authtoken=None)
    )
    assert saved["public_url"] == expected
    assert remote.inspection(root, settings["workspace_id"])["public_url"] == expected
    access = remote.RemoteAccess(root, settings, str(uuid4()), lambda event: None)
    assert access.oauth.origin == expected
    assert access.oauth.resource == expected + "/mcp"


def test_route_probe_is_current_process_bound_and_never_sends_a_memory_key(env, tmp_path):
    root, settings = workspace(tmp_path)
    remote.configure(root, change(settings, mode="proxy", ngrok_authtoken=None))
    access = remote.RemoteAccess(root, settings, str(env.owner.tenant_id), lambda event: None)
    app = create_app(env.db, env.embedder, mcp_enabled=False, hosted_oauth_settings=access.oauth)
    access.attach(app)
    observed = []

    class ObservedTransport(httpx.ASGITransport):
        async def handle_async_request(self, request):
            observed.append(request)
            return await super().handle_async_request(request)

    access.transport = ObservedTransport(app=app)
    with TestClient(app) as client:
        asyncio.run(access.probe())
        assert len(observed) == 1
        assert "authorization" not in observed[0].headers
        assert TOKEN not in str(observed[0].headers) + str(observed[0].url)
        another = remote.RemoteAccess(
            root, settings, str(env.owner.tenant_id), lambda event: None, transport=access.transport
        )
        with pytest.raises(ValueError, match="does not reach"):
            asyncio.run(another.probe())
        assert client.get("/v1/me").status_code == 401
        assert (
            client.get("/v1/me", headers={"Authorization": "Bearer " + env.token}).status_code
            == 200
        )


@pytest.mark.parametrize("kind", ["redirect", "oversized", "compressed", "wrong"])
def test_remote_probe_refuses_redirects_unbounded_responses_and_incorrect_evidence(tmp_path, kind):
    root, settings = workspace(tmp_path)
    remote.configure(root, change(settings, mode="proxy", ngrok_authtoken=None))
    calls = []

    async def response(request):
        calls.append(request)
        if kind == "redirect":
            return httpx.Response(302, headers={"location": "https://other.example.test"})
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip"} if kind == "compressed" else {},
            stream=httpx.ByteStream(b"x" * 4096 if kind == "oversized" else b"{}"),
        )

    access = remote.RemoteAccess(
        root, settings, str(uuid4()), lambda event: None, transport=httpx.MockTransport(response)
    )
    with pytest.raises(ValueError):
        asyncio.run(access.probe())
    assert len(calls) == 1 and "authorization" not in calls[0].headers


def test_provider_failure_is_bounded_and_does_not_remove_local_api_access(
    env, tmp_path, monkeypatch
):
    root, settings = workspace(tmp_path)
    remote.configure(root, change(settings))
    events = []
    access = remote.RemoteAccess(root, settings, str(env.owner.tenant_id), events.append)

    async def refused():
        raise RuntimeError("ERR_NGROK_108 private detail " + TOKEN)

    monkeypatch.setattr(access, "connect", refused)

    async def outage():
        task = asyncio.create_task(access.run())
        await asyncio.sleep(0)
        view = remote.inspection(root, settings["workspace_id"])
        assert view["state"] == "unavailable" and view["provider_code"] == "ERR_NGROK_108"
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    with TestClient(
        create_app(env.db, env.embedder, mcp_enabled=False, hosted_oauth_settings=access.oauth)
    ) as client:
        asyncio.run(outage())
        assert (
            client.get("/v1/me", headers={"Authorization": "Bearer " + env.token}).status_code
            == 200
        )
    assert TOKEN not in json.dumps(events)
    assert events[-1]["remote_access"]["state"] == "stopped"


def test_stale_process_or_configuration_status_cannot_claim_reachability(tmp_path):
    root, settings = workspace(tmp_path)
    saved = remote.configure(root, change(settings))
    access = remote.RemoteAccess(root, settings, str(uuid4()), lambda event: None)
    access.report("online", "Verified fixture route")
    assert remote.inspection(root, settings["workspace_id"])["state"] == "online"
    record = state.read(root / "runtime-remote.json")
    record["sampled_at"] -= 60
    state.write(root / "runtime-remote.json", record)
    assert remote.inspection(root, settings["workspace_id"])["state"] == "unchecked"
    access.report("online", "Verified fixture route")
    record = state.read(root / "runtime-remote.json")
    record["process_identity"]["pid"] += 1
    state.write(root / "runtime-remote.json", record)
    assert remote.inspection(root, settings["workspace_id"])["state"] == "unchecked"
    access.report("online", "Verified fixture route")
    remote.configure(root, change(settings, expected_revision=saved["revision"], mode="disabled"))
    assert remote.inspection(root, settings["workspace_id"])["state"] == "disabled"


def test_explicit_host_configuration_controls_personal_consent_browser_login_and_invitation_urls(
    env, monkeypatch
):
    monkeypatch.delenv("MNEMION_PUBLIC_URL", raising=False)
    monkeypatch.delenv("MNEMION_OAUTH_BUILTIN", raising=False)
    settings = HostedOAuthSettings.for_workspace(ORIGIN, env.owner.tenant_id)
    app = create_app(env.db, env.embedder, mcp_enabled=False, hosted_oauth_settings=settings)
    with TestClient(app, base_url=ORIGIN) as client:
        person = client.post(
            "/v1/principals",
            headers={"Authorization": "Bearer " + env.token},
            json={"name": "Remote teammate", "kind": "human"},
        )
        assert person.status_code == 201, person.text
        assert client.get("/v1/sign-in/configuration").json()["public_origin"] == ORIGIN
        assert (
            client.get("/.well-known/oauth-protected-resource/mcp").json()["resource"]
            == ORIGIN + "/mcp"
        )
        invitation = client.post(
            "/v1/sign-in/invitations",
            headers={"Authorization": "Bearer " + env.token},
            json={"principal_id": person.json()["id"]},
        )
        assert invitation.status_code == 201, invitation.text
        assert invitation.json()["invitation_url"].startswith(ORIGIN + "/workspace#invitation=")
    assert "MNEMION_PUBLIC_URL" not in os.environ and "MNEMION_OAUTH_BUILTIN" not in os.environ


def test_sdk_session_is_owned_and_cannot_pool_an_existing_endpoint(tmp_path, monkeypatch):
    import ngrok

    root, settings = workspace(tmp_path)
    remote.configure(root, change(settings))
    calls = []

    class Session:
        def client_info(self, *args):
            return self

        def authtoken(self, token):
            assert token == TOKEN
            return self

        async def connect(self):
            return self

        def http_endpoint(self):
            return self

        def domain(self, value):
            calls.append(("domain", value))
            return self

        def scheme(self, value):
            calls.append(("scheme", value))
            return self

        def pooling_enabled(self, value):
            calls.append(("pooling", value))
            return self

        async def listen_and_forward(self, value):
            calls.append(("target", value))
            return SimpleNamespace(url=lambda: ORIGIN)

        async def close(self):
            calls.append(("closed", True))

    monkeypatch.setattr(ngrok, "SessionBuilder", Session)
    access = remote.RemoteAccess(root, settings, str(uuid4()), lambda event: None)

    async def connection():
        await access.connect()
        await access.disconnect()
        await access.disconnect()

    asyncio.run(connection())
    assert calls == [
        ("domain", "memory.example.test"),
        ("scheme", "https"),
        ("pooling", False),
        ("target", "http://127.0.0.1:7892"),
        ("closed", True),
    ]


def test_manual_check_request_is_revision_bound_and_coalesced_without_a_network_call(tmp_path):
    root, settings = workspace(tmp_path)
    saved = remote.configure(root, change(settings))
    access = remote.RemoteAccess(root, settings, str(uuid4()), lambda event: None)
    command = remote.RemoteCheck.model_validate_json(
        json.dumps(
            {"workspace_id": settings["workspace_id"], "expected_revision": saved["revision"]}
        )
    )
    remote.request_check(root, command)
    first = access.request_id()
    assert first and first != access._last_request
    remote.request_check(root, command)
    assert access.request_id() != first
    with pytest.raises(state.LocalSetupError, match="settings changed"):
        remote.request_check(
            root, command.model_copy(update={"expected_revision": "not-configured"})
        )
    assert TOKEN not in (root / "remote-check.json").read_text()
    access._last_attempt = -remote.MINIMUM_CHECK_INTERVAL_SECONDS
    asyncio.run(asyncio.wait_for(access.pause(900), timeout=1))
