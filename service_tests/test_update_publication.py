"""Service publication binds artifacts, dependency lock, migrations and publisher."""

import base64
from datetime import datetime, timezone
import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from deploy.service_update_manifest import (
    signed_document,
    signing_key_from_environment,
    verify_document,
    write_document,
)
from mnemion.service.update_manifest import ManifestError, verify_manifest
from service_tests.update_fixture import package_inputs as inputs


def test_publication_binds_the_actual_release_inputs(tmp_path):
    artifacts = inputs(tmp_path)
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes_raw()
    content = signed_document(
        tmp_path,
        artifacts,
        "a" * 40,
        key.private_bytes_raw(),
        public,
        created_at=datetime(2026, 10, 11, tzinfo=timezone.utc),
    )
    release = verify_manifest(content, public)
    assert release.commit == "a" * 40
    assert release.created_at == "2026-10-11T00:00:00Z"
    assert release.lock_sha256 == hashlib.sha256((tmp_path / "uv.lock").read_bytes()).hexdigest()
    for artifact in release.artifacts:
        artifact.verify_file(artifacts / artifact.name)
    path = artifacts / "service-update.json"
    write_document(path, content)
    assert verify_manifest(path.read_bytes(), public) == release
    assert verify_document(tmp_path, artifacts, public_key=public) == release
    with pytest.raises(FileExistsError):
        write_document(path, content)


def test_mismatched_release_secret_is_rejected_before_publication(tmp_path):
    artifacts = inputs(tmp_path)
    key = Ed25519PrivateKey.generate()
    other = Ed25519PrivateKey.generate()
    with pytest.raises(ManifestError, match="signature"):
        signed_document(
            tmp_path,
            artifacts,
            "a" * 40,
            key.private_bytes_raw(),
            other.public_key().public_bytes_raw(),
        )
    assert not (artifacts / "service-update.json").exists()


def test_packages_from_another_checkout_cannot_be_signed(tmp_path):
    artifacts = inputs(tmp_path)
    key = Ed25519PrivateKey.generate()
    (tmp_path / "mnemion/version.py").write_text('__version__ = "changed checkout"\n')
    with pytest.raises(ManifestError, match="reviewed checkout"):
        signed_document(
            tmp_path,
            artifacts,
            "a" * 40,
            key.private_bytes_raw(),
            key.public_key().public_bytes_raw(),
        )


def test_release_verification_rejects_a_changed_artifact_after_signing(tmp_path):
    artifacts = inputs(tmp_path)
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes_raw()
    content = signed_document(tmp_path, artifacts, "a" * 40, key.private_bytes_raw(), public)
    write_document(artifacts / "service-update.json", content)
    wheel = artifacts / "mnemion-4.0.8-py3-none-any.whl"
    wheel.write_bytes(b"x" * wheel.stat().st_size)
    with pytest.raises(ManifestError, match="differs"):
        verify_document(tmp_path, artifacts, public_key=public)


def test_signing_secret_is_read_only_from_the_designated_environment(monkeypatch, capsys):
    key = Ed25519PrivateKey.generate().private_bytes_raw()
    monkeypatch.setenv("MNEMION_SERVICE_UPDATE_PRIVATE_KEY", base64.b64encode(key).decode())
    assert signing_key_from_environment() == key
    monkeypatch.setenv("MNEMION_SERVICE_UPDATE_PRIVATE_KEY", "sentinel-private-invalid")
    with pytest.raises(ManifestError) as error:
        signing_key_from_environment()
    assert "sentinel-private-invalid" not in str(error.value)
    assert not capsys.readouterr().out


def test_empty_or_missing_release_inputs_cannot_be_signed(tmp_path):
    artifacts = inputs(tmp_path)
    key = Ed25519PrivateKey.generate()
    (artifacts / "mnemion-4.0.8.tar.gz").write_bytes(b"")
    with pytest.raises(ManifestError, match="bounded regular"):
        signed_document(
            tmp_path,
            artifacts,
            "a" * 40,
            key.private_bytes_raw(),
            key.public_key().public_bytes_raw(),
        )
