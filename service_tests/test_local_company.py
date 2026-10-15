"""Private provider setup, current-host binding and real service admission."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
import httpx
import pytest

from mnemion import local_company as company, local_remote, local_state as state
from mnemion.local_workspace import SetupOptions
from mnemion.service.api import create_app

ORIGIN = "https://memory.example.test"
ISSUER = "https://identity.example.test/company"
SECRET = "private-client-secret-fixture-never-returned"


def workspace(tmp_path):
    root = state.directory(tmp_path / "Company Équipe")
    settings = {
        "format": 1,
        "workspace_id": str(uuid4()),
        "created_at": "2026-10-15T00:00:00Z",
        **SetupOptions(workspace_name="Company memory", owner_name="Owner").model_dump(),
        "database_port": 17893,
    }
    state.write(root / "configuration.json", settings)
    state.write(root / "credentials.json", {"fixture": "existing credentials remain unchanged"})
    remote = local_remote.configure(
        root,
        local_remote.RemoteChange.model_validate_json(
            json.dumps(
                {
                    "workspace_id": settings["workspace_id"],
                    "expected_revision": "not-configured",
                    "mode": "proxy",
                    "public_url": ORIGIN,
                }
            )
        ),
    )
    return root, settings, remote


def provider(**changes):
    return {
        "id": "company",
        "name": "Company account",
        "issuer": ISSUER,
        "authorization_url": ISSUER + "/authorize",
        "token_url": ISSUER + "/token",
        "jwks_url": ISSUER + "/keys",
        "client_id": "mnemion-client",
        "session_seconds": 28800,
        **changes,
    }


def request(settings, remote, **changes):
    return {
        "workspace_id": settings["workspace_id"],
        "expected_revision": "not-configured",
        "expected_remote_revision": remote["revision"],
        **changes,
    }


def saving(settings, remote, **changes):
    # Explicit overrides also support remove/reset without carrying save-only fields.
    values = request(settings, remote, action="save", provider=provider(), client_secret=SECRET)
    values.update(changes)
    if values["action"] != "save":
        values.pop("provider", None)
        values.pop("client_secret", None)
    return company.CompanyChange.model_validate_json(json.dumps(values))


def test_private_company_setup_preserves_identity_and_never_returns_saved_secret(tmp_path):
    root, settings, remote = workspace(tmp_path)
    original = {
        name: (root / name).read_bytes()
        for name in ("configuration.json", "credentials.json", "remote-access.json")
    }
    view = company.configure(root, saving(settings, remote))
    assert view["state"] == "configured" and view["callback_uri"] == ORIGIN + "/company/callback"
    assert view["providers"][0]["has_client_secret"]
    assert SECRET not in json.dumps(view) and SECRET not in json.dumps(
        company.inspection(root, settings["workspace_id"])
    )
    assert state.read(root / "company-access.json")["providers"][0]["client_secret"] == SECRET
    if os.name != "nt":
        assert (root / "company-access.json").stat().st_mode & 0o077 == 0
    for name, content in original.items():
        assert (root / name).read_bytes() == content
    updated = company.configure(
        root,
        saving(
            settings,
            remote,
            expected_revision=view["revision"],
            client_secret=None,
            provider=provider(name="Work account"),
        ),
    )
    assert updated["providers"][0]["has_client_secret"]
    removed = company.configure(
        root,
        saving(
            settings,
            remote,
            expected_revision=updated["revision"],
            action="remove",
            provider_id="company",
        ),
    )
    assert removed["state"] == "disabled" and removed["providers"] == []
    assert SECRET not in (root / "company-access.json").read_text()


def test_local_instance_and_service_tenant_are_kept_distinct(env, tmp_path):
    root, settings, remote = workspace(tmp_path)
    company.configure(root, saving(settings, remote))
    assert settings["workspace_id"] != str(env.owner.tenant_id)
    identity = company.identity(
        root, settings["workspace_id"], tenant_id=str(env.owner.tenant_id), public_url=ORIGIN
    )
    assert identity.provider(env.owner.tenant_id, "company").client_secret == SECRET
    with TestClient(
        create_app(env.db, env.embedder, public_url=ORIGIN, company_identity=identity),
        base_url=ORIGIN,
    ) as client:
        response = client.get(
            "/v1/sign-in/company/configuration", params={"workspace_id": str(env.owner.tenant_id)}
        )
        assert response.status_code == 200
        assert response.json()["providers"][0]["id"] == "company"
        assert SECRET not in response.text and "client_id" not in response.text
        other = client.get(
            "/v1/sign-in/company/configuration", params={"workspace_id": settings["workspace_id"]}
        )
        assert other.status_code == 200 and other.json()["providers"] == []
        assert (
            client.post(
                "/v1/sign-in/company/provider-setup",
                json={},
                headers={"Authorization": "Bearer " + env.token},
            ).status_code
            == 404
        )


def test_existing_explicit_environment_configuration_is_preserved_and_not_silently_replaced(
    tmp_path, monkeypatch
):
    root, settings, remote = workspace(tmp_path)
    tenant = str(uuid4())
    path = tmp_path / "existing-provider.json"
    path.write_text(json.dumps([{**provider(), "workspace_id": tenant}]))
    monkeypatch.setenv("MNEMION_COMPANY_SIGN_IN_FILE", str(path))
    identity = company.identity(root, settings["workspace_id"], tenant_id=tenant, public_url=ORIGIN)
    assert len(identity.providers) == 1
    view = company.inspection(root, settings["workspace_id"])
    assert view["state"] == "external" and not view["repairable"]
    with pytest.raises(state.LocalSetupError, match="environment"):
        company.configure(root, saving(settings, remote))
    assert not (root / "company-access.json").exists()


def test_stale_company_or_remote_revision_and_wrong_host_do_not_replace_settings(tmp_path):
    root, settings, remote = workspace(tmp_path)
    view = company.configure(root, saving(settings, remote))
    original = (root / "company-access.json").read_bytes()
    for fields in (
        {},
        {"expected_revision": view["revision"], "expected_remote_revision": str(uuid4())},
        {"expected_revision": view["revision"], "workspace_id": str(uuid4())},
    ):
        with pytest.raises(state.LocalSetupError, match="settings|workspace"):
            company.configure(root, saving(settings, remote, **fields))
        assert (root / "company-access.json").read_bytes() == original


def test_saved_secret_requires_explicit_review_before_sending_to_changed_provider(tmp_path):
    root, settings, remote = workspace(tmp_path)
    view = company.configure(root, saving(settings, remote))
    original = (root / "company-access.json").read_bytes()
    for field, value in (
        ("token_url", "https://another.example.test/token"),
        ("client_id", "different-client"),
        ("issuer", "https://another.example.test"),
    ):
        with pytest.raises(state.LocalSetupError, match="secret"):
            company.configure(
                root,
                saving(
                    settings,
                    remote,
                    expected_revision=view["revision"],
                    client_secret=None,
                    provider=provider(**{field: value}),
                ),
            )
        assert (root / "company-access.json").read_bytes() == original
    view = company.configure(
        root,
        saving(
            settings,
            remote,
            expected_revision=view["revision"],
            client_secret=None,
            clear_client_secret=True,
            provider=provider(client_id="public-client"),
        ),
    )
    assert (
        not view["providers"][0]["has_client_secret"]
        and SECRET not in (root / "company-access.json").read_text()
    )


def test_label_and_secret_rotation_keep_policy_but_changed_session_reapproves_identity(tmp_path):
    root, settings, remote = workspace(tmp_path)
    tenant = str(uuid4())
    view = company.configure(root, saving(settings, remote))
    first = company.identity(
        root, settings["workspace_id"], tenant_id=tenant, public_url=ORIGIN
    ).policies
    view = company.configure(
        root,
        saving(
            settings,
            remote,
            expected_revision=view["revision"],
            client_secret="rotated-private-client-secret",
            provider=provider(name="Renamed"),
        ),
    )
    assert (
        company.identity(
            root, settings["workspace_id"], tenant_id=tenant, public_url=ORIGIN
        ).policies
        == first
    )
    company.configure(
        root,
        saving(
            settings,
            remote,
            expected_revision=view["revision"],
            provider=provider(session_seconds=3600),
        ),
    )
    assert (
        company.identity(
            root, settings["workspace_id"], tenant_id=tenant, public_url=ORIGIN
        ).policies
        != first
    )


def test_atomic_failure_retains_previous_configuration(tmp_path, monkeypatch):
    root, settings, remote = workspace(tmp_path)
    view = company.configure(root, saving(settings, remote))
    previous = (root / "company-access.json").read_bytes()

    def interrupted(*args):
        raise OSError("simulated interrupted replacement")

    monkeypatch.setattr(os, "replace", interrupted)
    with pytest.raises(OSError):
        company.configure(
            root,
            saving(
                settings,
                remote,
                expected_revision=view["revision"],
                provider=provider(name="Changed"),
            ),
        )
    assert (root / "company-access.json").read_bytes() == previous


@pytest.mark.parametrize("damage", ["json", "ca", "workspace"])
def test_damaged_settings_disable_company_only_and_explicit_reset_retains_evidence(
    tmp_path, damage
):
    root, settings, remote = workspace(tmp_path)
    company.configure(root, saving(settings, remote))
    value = state.read(root / "company-access.json")
    if damage == "ca":
        value["ca_pem"] = "not-a-certificate"
    if damage == "workspace":
        value["workspace_id"] = str(uuid4())
    damaged = b'{"providers":' if damage == "json" else json.dumps(value).encode()
    (root / "company-access.json").write_bytes(damaged)
    view = company.inspection(root, settings["workspace_id"])
    assert view["state"] == "configuration_error" and view["repairable"]
    assert not company.identity(
        root, settings["workspace_id"], tenant_id=str(uuid4()), public_url=ORIGIN
    ).providers
    with pytest.raises(state.LocalSetupError, match="Reset"):
        company.configure(root, saving(settings, remote, expected_revision=view["revision"]))
    reset = company.configure(
        root, saving(settings, remote, expected_revision=view["revision"], action="reset")
    )
    assert reset["state"] == "disabled"
    assert next((root / "recovery").glob("company-*.bin")).read_bytes() == damaged
    assert SECRET not in json.dumps(view) + json.dumps(reset)


def test_remote_disabled_retains_provider_setup_without_breaking_local_access(tmp_path):
    root, settings, remote = workspace(tmp_path)
    company.configure(root, saving(settings, remote))
    local_remote.configure(
        root,
        local_remote.RemoteChange.model_validate_json(
            json.dumps(
                {
                    "workspace_id": settings["workspace_id"],
                    "expected_revision": remote["revision"],
                    "mode": "disabled",
                }
            )
        ),
    )
    view = company.inspection(root, settings["workspace_id"])
    assert (
        view["state"] == "needs_remote"
        and view["callback_uri"] is None
        and len(view["providers"]) == 1
    )
    assert not company.identity(
        root, settings["workspace_id"], tenant_id=str(uuid4()), public_url=None
    ).providers


def test_cli_private_input_and_running_host_exclusion(tmp_path):
    root, settings, remote = workspace(tmp_path)
    args = [sys.executable, "-m", "mnemion.service.cli", "local", "company", "--root", str(root)]
    payload = request(settings, remote, action="save", provider=provider(), client_secret=SECRET)
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    with state.lock(root):
        refused = subprocess.run(
            args,
            input=json.dumps(payload),
            env=environment,
            text=True,
            capture_output=True,
            timeout=25,
        )
    assert refused.returncode != 0 and json.loads(refused.stdout)["code"] == "workspace_busy"
    assert not (root / "company-access.json").exists()
    accepted = subprocess.run(
        args, input=json.dumps(payload), env=environment, text=True, capture_output=True, timeout=25
    )
    assert accepted.returncode == 0
    assert json.loads(accepted.stdout)["company_access"]["providers"][0]["has_client_secret"]
    assert SECRET not in accepted.stdout + accepted.stderr + refused.stdout + refused.stderr


@pytest.fixture(scope="module")
def certificate():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Local company fixture CA")])
    now = datetime.now(timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
        .decode()
    )


def test_private_certificate_trust_is_validated_retained_and_explicitly_removed(
    tmp_path, certificate
):
    root, settings, remote = workspace(tmp_path)
    view = company.configure(root, saving(settings, remote, ca_pem=certificate))
    assert view["has_custom_ca"] and "BEGIN CERTIFICATE" not in json.dumps(view)
    identity = company.identity(
        root, settings["workspace_id"], tenant_id=str(uuid4()), public_url=ORIGIN
    )
    assert (
        isinstance(identity.tls, ssl.SSLContext)
        and identity.tls.verify_mode == ssl.CERT_REQUIRED
        and identity.tls.check_hostname
    )
    view = company.configure(
        root, saving(settings, remote, expected_revision=view["revision"], client_secret=None)
    )
    assert view["has_custom_ca"]
    view = company.configure(
        root,
        saving(
            settings, remote, expected_revision=view["revision"], client_secret=None, ca_pem=None
        ),
    )
    assert not view["has_custom_ca"]
    for invalid in ("not-a-certificate", certificate + "\n-----BEGIN PRIVATE KEY-----", "x" * 8193):
        with pytest.raises(ValueError):
            saving(settings, remote, ca_pem=invalid)


def metadata(**values):
    return {
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "/authorize",
        "token_endpoint": ISSUER + "/token",
        "jwks_uri": ISSUER + "/keys",
        "response_types_supported": ["code"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "code_challenge_methods_supported": ["S256"],
        **values,
    }


def test_discovery_is_credential_free_exact_issuer_bound_and_does_not_save(tmp_path):
    root, settings, remote = workspace(tmp_path)
    view = company.configure(root, saving(settings, remote))
    original = (root / "company-access.json").read_bytes()
    seen = []

    def peer(request):
        seen.append(request)
        assert (
            request.method == "GET"
            and str(request.url) == ISSUER + "/.well-known/openid-configuration"
        )
        assert (
            not request.content
            and "authorization" not in request.headers
            and "cookie" not in request.headers
        )
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(metadata()).encode()))

    result = asyncio.run(
        company.discover(
            root,
            company.CompanyDiscovery.model_validate_json(
                json.dumps(
                    request(settings, remote, expected_revision=view["revision"], issuer=ISSUER)
                )
            ),
            transport=httpx.MockTransport(peer),
        )
    )
    assert (
        result["issuer"] == ISSUER and result["token_url"] == ISSUER + "/token" and len(seen) == 1
    )
    assert (
        SECRET not in json.dumps(result) and (root / "company-access.json").read_bytes() == original
    )


@pytest.mark.parametrize(
    "fault",
    [
        "redirect",
        "too_large",
        "compressed",
        "issuer",
        "algorithm",
        "pkce",
        "plaintext",
        "json",
        "query",
        "shape",
        "auth",
    ],
)
def test_invalid_discovery_is_bounded_and_cannot_publish_provider_error_details(tmp_path, fault):
    root, settings, remote = workspace(tmp_path)
    seen = []

    def peer(request):
        seen.append(request)
        values = metadata()
        if fault == "issuer":
            values["issuer"] = "https://another.example.test"
        if fault == "algorithm":
            values["id_token_signing_alg_values_supported"] = ["none"]
        if fault == "pkce":
            values["code_challenge_methods_supported"] = ["plain"]
        if fault == "shape":
            values["scopes_supported"] = "openid"
        if fault == "auth":
            values["token_endpoint_auth_methods_supported"] = ["client_secret_post"]
        if fault == "plaintext":
            values["token_endpoint"] = "http://identity.example.test/token"
        if fault == "query":
            values["token_endpoint"] += "?private=" + SECRET
        if fault == "redirect":
            return httpx.Response(
                302, headers={"Location": "https://another.example.test/" + SECRET}
            )
        body = (
            "x" * 65537
            if fault == "too_large"
            else "{" + SECRET
            if fault == "json"
            else json.dumps(values)
        ).encode()
        return httpx.Response(
            200,
            stream=httpx.ByteStream(body),
            headers={"Content-Encoding": "gzip"} if fault == "compressed" else {},
        )

    with pytest.raises(state.LocalSetupError) as failed:
        asyncio.run(
            company.discover(
                root,
                company.CompanyDiscovery.model_validate_json(
                    json.dumps(request(settings, remote, issuer=ISSUER))
                ),
                transport=httpx.MockTransport(peer),
            )
        )
    assert (
        failed.value.code == "company_discovery_failed"
        and SECRET not in str(failed.value)
        and len(seen) == 1
    )
    assert not (root / "company-access.json").exists()
