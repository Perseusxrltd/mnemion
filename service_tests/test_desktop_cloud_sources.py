"""Private cloud enrollment and real memory-service access, with provider fixtures."""

import base64
import json
import os
from urllib.parse import parse_qs
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pydantic import ValidationError

from mnemion import desktop_sources as desktop
from mnemion.desktop_provider_credentials import DRIVE_SCOPE, GOOGLE_TOKEN_URL, credential
from mnemion.service.api import create_app
from mnemion.service.connector_models import BindingInput, ConnectorInput
from mnemion.service.connectors import ConnectorService
from mnemion.service.errors import ServiceError
from mnemion.service.models import KeyInput, PrincipalInput
from service_tests.test_clients import running as serve


def google_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, {
        "type": "service_account",
        "private_key_id": "disposable-fixture-key",
        "client_email": "fixture@selected-project.iam.gserviceaccount.com",
        "token_uri": GOOGLE_TOKEN_URL,
        "private_key": key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
    }


def test_google_assertion_is_read_only_signed_fixed_destination_and_renewed():
    key, settings = google_key()
    clock, calls = [1000], []

    def provider(request):
        assert str(request.url) == GOOGLE_TOKEN_URL and request.method == "POST"
        payload = parse_qs(request.content.decode())
        assert payload["grant_type"] == ["urn:ietf:params:oauth:grant-type:jwt-bearer"]
        parts = payload["assertion"][0].split(".")
        key.public_key().verify(
            base64.urlsafe_b64decode(parts[2] + "==="),
            ".".join(parts[:2]).encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + "==="))
        assert claims == {
            "iss": settings["client_email"],
            "scope": DRIVE_SCOPE,
            "aud": GOOGLE_TOKEN_URL,
            "iat": clock[0],
            "exp": clock[0] + 3600,
        }
        calls.append(claims)
        return httpx.Response(
            200,
            json={
                "access_token": "temporary-provider-token-" + str(len(calls)),
                "expires_in": 3600,
            },
        )

    # Extra downloaded metadata never authorizes user impersonation.
    saved = json.dumps({**settings, "subject": "must-not-be-impersonated@example.invalid"})
    token = credential(
        "gdrive", saved, transport=httpx.MockTransport(provider), now=lambda: clock[0]
    )
    assert calls == []  # Parsing a key cannot contact a provider.
    first = token.read()
    clock[0] += 100
    assert token.read() == first and len(calls) == 1
    clock[0] += 3500
    assert token.read() != first and len(calls) == 2
    assert settings["private_key"] not in repr(token)


def test_provider_keys_reject_retargeting_bad_json_and_oversized_input():
    _, settings = google_key()
    for value in (
        json.dumps({**settings, "token_uri": "https://unrelated.invalid/token"}),
        json.dumps({**settings, "universe_domain": "unrelated.invalid"}),
        '{"type":"service_account","type":"different"}',
        json.dumps({**settings, "private_key": "private-invalid-key-fixture"}),
        "private-overlong-" * 1000,
    ):
        with pytest.raises(ValueError) as caught:
            credential("gdrive", value)
        assert "private-invalid-key-fixture" not in str(caught.value)
        assert settings["private_key"] not in str(caught.value)
    for value in ("short", "private-key with space", "private-key-with-newline\n"):
        with pytest.raises(ValueError):
            credential("slack", value)


@pytest.mark.parametrize("provider", ["slack", "gdrive"])
def test_cloud_sources_require_separate_sealed_credentials_and_keep_file_compatibility(
    tmp_path, provider
):
    selection = (
        {"slack": {"team_id": "T123", "channels": ["C123"]}}
        if provider == "slack"
        else {"gdrive": {"file_ids": ["selected-file"]}}
    )
    source = desktop.Source(
        **{name: uuid4() for name in ("id", "tenant_id", "principal_id", "connector_id")},
        endpoint="https://memory.example.invalid",
        name="Selected cloud source",
        provider=provider,
        members=[],
        publish_to_mapped_members=True,
        **selection,
    )
    public = source.model_dump(mode="json", exclude_none=True)
    sealed = base64.b64encode(os.urandom(128)).decode()
    with pytest.raises(ValidationError):
        desktop.store(tmp_path / "private", "not-configured", [{**public, "sealed_key": sealed}])
    saved = desktop.store(
        tmp_path / "private",
        "not-configured",
        [{**public, "sealed_key": sealed, "sealed_provider": sealed}],
    )
    assert desktop.load(tmp_path / "private").sources[0].provider == provider
    with pytest.raises(ValidationError):
        desktop.store(
            tmp_path / "private",
            saved["revision"],
            [{**public, "sealed_key": sealed, "provider_credential": "must-not-be-saved"}],
        )
    with pytest.raises(ValidationError):
        desktop.Source(**{**public, "path": str(tmp_path / "unrelated")})


@pytest.mark.parametrize("provider", ["slack", "gdrive"])
def test_cloud_capture_keeps_actual_provider_memberships_and_private_credentials(
    env, tmp_path, monkeypatch, provider
):
    bridge = ConnectorService(env.memory)
    actor = env.identities.create_principal(env.owner, PrincipalInput(name="Cloud source"))
    key = env.identities.create_key(env.owner, UUID(actor["id"]), KeyInput(name="Cloud fixture"))
    operator = env.db.authenticate(key["api_key"])
    reader = env.identities.create_principal(env.owner, PrincipalInput(name="Reader", kind="human"))
    reader_key = env.identities.create_key(env.owner, UUID(reader["id"]), KeyInput(name="Reader"))
    reader_identity = env.db.authenticate(reader_key["api_key"])
    forged = env.identities.create_principal(env.owner, PrincipalInput(name="Unpermitted reader"))
    forged_key = env.identities.create_key(env.owner, UUID(forged["id"]), KeyInput(name="Reader"))
    forged_identity = env.db.authenticate(forged_key["api_key"])
    connector = bridge.create(
        env.owner,
        ConnectorInput(
            name="Cloud source",
            provider=provider,
            principal_id=operator.principal_id,
            access_mode="provider",
        ),
    )
    connector_id = UUID(connector["id"])
    member = "slack-user:U123" if provider == "slack" else "google-user:P123"
    for external, principal in [(member, reader), ("forged", forged)]:
        bridge.binding(
            env.owner,
            connector_id,
            BindingInput(external_id=external, principal_id=UUID(principal["id"])),
        )
    body = "The company selected a shared, permission-aware memory system."
    state = {"member": True, "calls": [], "grants": 0}
    _, google = google_key()
    raw = "private-slack-provider-fixture" if provider == "slack" else json.dumps(google)

    def upstream(request):
        state["calls"].append(request.url.path)
        if str(request.url) == GOOGLE_TOKEN_URL:
            assert request.method == "POST"
            state["grants"] += 1
            return httpx.Response(
                200, json={"access_token": "temporary-drive-access-fixture", "expires_in": 3600}
            )
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer " + (
            raw if provider == "slack" else "temporary-drive-access-fixture"
        )
        if provider == "slack":
            method = request.url.path.removeprefix("/api/")
            values = {
                "auth.test": {"ok": True, "team_id": "T123", "url": "https://fixture.slack.com/"},
                "conversations.info": {"ok": True, "channel": {"id": "C123", "name": "selected"}},
                "conversations.members": {
                    "ok": True,
                    "members": ["U123"] if state["member"] else [],
                },
                "conversations.history": {
                    "ok": True,
                    "messages": [{"ts": "1000.000001", "text": body}],
                },
            }
            assert method in values
            return httpx.Response(200, json=values[method])
        path = request.url.path.removeprefix("/drive/v3/")
        if path == "about":
            return httpx.Response(200, json={"user": {"permissionId": "service-account"}})
        if path == "files/selected-file/permissions":
            return httpx.Response(
                200,
                json={
                    "permissions": [{"id": "P123", "type": "user", "role": "reader"}]
                    if state["member"]
                    else []
                },
            )
        assert path == "files/selected-file"
        if request.url.params.get("alt") == "media":
            return httpx.Response(200, content=body.encode())
        return httpx.Response(
            200,
            json={
                "id": "selected-file",
                "name": "decision.md",
                "mimeType": "text/plain",
                "version": "1",
                "webViewLink": "https://drive.google.com/file/d/selected-file",
            },
        )

    original = desktop.cloud_adapter

    def adapter(source, value):
        result = original(source, value)
        result.http.client.close()
        result.http.client = httpx.Client(
            base_url="https://slack.com/api/"
            if provider == "slack"
            else "https://www.googleapis.com/drive/v3/",
            transport=httpx.MockTransport(upstream),
        )
        if provider == "gdrive":
            result.http.token._transport = httpx.MockTransport(upstream)
        return result

    monkeypatch.setattr(desktop, "cloud_adapter", adapter)
    monkeypatch.setenv("MNEMION_DESKTOP_PROVIDER_UNUSED", "must-not-be-used")
    selection = (
        {"slack": {"team_id": "T123", "channels": ["C123"]}}
        if provider == "slack"
        else {"gdrive": {"file_ids": ["selected-file"]}}
    )
    with serve(create_app(env.db, env.embedder)) as endpoint:
        source = desktop.Source(
            id=uuid4(),
            endpoint=endpoint,
            tenant_id=env.owner.tenant_id,
            connector_id=connector_id,
            principal_id=operator.principal_id,
            name="Cloud source",
            provider=provider,
            members=["forged"],
            publish_to_mapped_members=True,
            **selection,
        )
        request = {
            "operation": "verify",
            "source": source.model_dump(mode="json", exclude_none=True),
            "credential": key["api_key"],
            "provider_credential": raw,
        }
        root = tmp_path / "private"
        verified = desktop.perform(root, request)
        assert verified == request["source"]
        assert raw not in json.dumps(verified) and key["api_key"] not in json.dumps(verified)
        assert bridge.scopes(operator, connector_id)["items"] == []
        assert not any("history" in call or "/files/" in call for call in state["calls"])
        first = desktop.perform(root, {**request, "operation": "scan"})
        assert first["completed"] and first["changed"] == 1
        scope = bridge.scopes(operator, connector_id)["items"][0]
        items = env.memory.list(reader_identity, UUID(scope["space_id"]))["items"]
        assert len(items) == 1 and items[0]["content"] == body
        memory_id = UUID(items[0]["memory_id"])
        with pytest.raises(ServiceError):
            env.memory.fetch(forged_identity, memory_id)
        assert raw not in json.dumps(first) and body not in json.dumps(first)
        state["member"] = False
        next_scan = desktop.perform(root, {**request, "operation": "scan"})
        assert next_scan["completed"]
        with pytest.raises(ServiceError):
            env.memory.fetch(reader_identity, memory_id)
        with pytest.raises(desktop.local_state.LocalSetupError):
            desktop.perform(root, {**request, "credential": env.token})
