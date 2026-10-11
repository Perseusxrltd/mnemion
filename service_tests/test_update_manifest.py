"""A server update must authenticate its exact artifacts before any host changes."""

import base64
import copy
import hashlib
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from mnemion.service import update_manifest as manifest


@pytest.fixture
def signed_release():
    key = Ed25519PrivateKey.generate()
    source, wheel = b"source package fixture", b"wheel package fixture"
    payload = {
        "kind": "mnemion-service-update",
        "protocol": 1,
        "channel": "stable",
        "version": "4.0.8",
        "repository": "Perseusxrltd/mnemion",
        "commit": "a" * 40,
        "created_at": "2026-10-11T00:00:00Z",
        "python_versions": ["3.12", "3.13", "3.14"],
        "artifacts": [
            {"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in [
                ("mnemion-4.0.8.tar.gz", source),
                ("mnemion-4.0.8-py3-none-any.whl", wheel),
            ]
        ],
        "lock_sha256": hashlib.sha256(b"locked dependencies").hexdigest(),
        "migrations": {"001_initial.sql": hashlib.sha256(b"schema fixture").hexdigest()},
    }
    return key, payload, source, wheel


def test_verified_release_preserves_identity_and_verifies_each_exact_package(
    signed_release, tmp_path
):
    key, payload, source, wheel = signed_release
    content = manifest.sign_manifest(payload, key.private_bytes_raw())
    checked = manifest.verify_manifest(content, key.public_key().public_bytes_raw())
    assert checked.version == "4.0.8" and checked.is_newer_than("4.0.7")
    assert not checked.is_newer_than("4.0.8") and not checked.is_newer_than("4.0.9")
    for artifact, data in zip(checked.artifacts, [source, wheel], strict=True):
        path = tmp_path / artifact.name
        path.write_bytes(data)
        artifact.verify_file(path)
        path.write_bytes(b"x" * len(data))
        with pytest.raises(manifest.ManifestError, match="digest"):
            artifact.verify_file(path)
        path.write_bytes(data + b"extra")
        with pytest.raises(manifest.ManifestError, match="size"):
            artifact.verify_file(path)
    schema_identity = checked.schema_sha256
    payload["migrations"]["001_initial.sql"] = "0" * 64
    assert checked.schema_sha256 == schema_identity


def test_changed_signed_payload_and_other_publishers_are_rejected(signed_release):
    key, payload, *_ = signed_release
    content = manifest.sign_manifest(payload, key.private_bytes_raw())
    other = Ed25519PrivateKey.generate()
    with pytest.raises(manifest.ManifestError, match="signature"):
        manifest.verify_manifest(content, other.public_key().public_bytes_raw())
    envelope = json.loads(content)
    payload["version"] = "4.0.9"
    envelope["payload"] = base64.b64encode(json.dumps(payload).encode()).decode()
    with pytest.raises(manifest.ManifestError, match="signature"):
        manifest.verify_manifest(json.dumps(envelope).encode(), key.public_key().public_bytes_raw())


def test_a_signature_for_another_protocol_cannot_authorize_service_updates(signed_release):
    key, payload, *_ = signed_release
    data = json.dumps(payload).encode()
    envelope = {
        "payload": base64.b64encode(data).decode(),
        "signature": base64.b64encode(key.sign(data)).decode(),
    }
    with pytest.raises(manifest.ManifestError, match="signature"):
        manifest.verify_manifest(json.dumps(envelope).encode(), key.public_key().public_bytes_raw())


@pytest.mark.parametrize(
    "change",
    [
        {"protocol": True},
        {"channel": "preview"},
        {"version": "4.0.8-rc.1"},
        {"version": "04.0.8"},
        {"repository": "unrelated/project"},
        {"created_at": "2026-99-99T00:00:00Z"},
        {"python_versions": ["3.13", "3.13"]},
        {"migrations": {"../../private.sql": "a" * 64}},
        {"migrations": {"001_initial.sql": "incomplete digest"}},
        {"lock_sha256": "incomplete digest"},
        {"unknown_field": "sentinel-private-metadata"},
    ],
)
def test_invalid_release_contract_never_reaches_signing(signed_release, change):
    key, payload, *_ = signed_release
    payload.update(change)
    with pytest.raises(manifest.ManifestError) as error:
        manifest.sign_manifest(payload, key.private_bytes_raw())
    assert "sentinel-private-metadata" not in str(error.value)


@pytest.mark.parametrize("field,value", [("size", True), ("size", 0), ("name", "../../private")])
def test_invalid_artifacts_are_rejected(signed_release, field, value):
    key, payload, *_ = signed_release
    payload["artifacts"][0][field] = value
    with pytest.raises(manifest.ManifestError):
        manifest.sign_manifest(payload, key.private_bytes_raw())


def test_both_distributions_are_required(signed_release):
    key, payload, *_ = signed_release
    payload["artifacts"][1] = copy.deepcopy(payload["artifacts"][0])
    with pytest.raises(manifest.ManifestError):
        manifest.sign_manifest(payload, key.private_bytes_raw())


def test_duplicate_fields_and_oversized_documents_fail_before_signature_processing():
    for content in (
        b'{"payload":"first","payload":"second","signature":"unused"}',
        b"x" * (manifest.MAX_MANIFEST_BYTES + 1),
    ):
        with pytest.raises(manifest.ManifestError):
            manifest.verify_manifest(content, b"unused")


def test_package_symlinks_are_not_accepted(signed_release, tmp_path):
    key, payload, source, *_ = signed_release
    checked = manifest.verify_manifest(
        manifest.sign_manifest(payload, key.private_bytes_raw()),
        key.public_key().public_bytes_raw(),
    )
    actual = tmp_path / "source"
    actual.write_bytes(source)
    path = tmp_path / checked.artifacts[0].name
    try:
        path.symlink_to(actual)
    except OSError:
        pytest.skip("This host cannot create the test symlink")
    with pytest.raises(manifest.ManifestError, match="symbolic link"):
        checked.artifacts[0].verify_file(path)
