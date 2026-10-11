"""Reject damaged, mismatched or unsafe archives before installing any code."""

import tarfile

import pytest

from deploy.service_update_manifest import payload
from mnemion.service.update_manifest import ManifestError, validate_payload
from mnemion.service import update_packages as packages
from service_tests.update_fixture import package_inputs, rebuild_packages


def release(root, artifacts):
    return validate_payload(payload(root, artifacts, "a" * 40))


def test_source_and_wheel_are_inspected_without_importing_candidate_code(tmp_path):
    artifacts = package_inputs(tmp_path)
    candidate = release(tmp_path, artifacts)
    with packages.inspected_packages(artifacts, candidate) as source:
        assert source != tmp_path
        assert (source / "uv.lock").read_bytes() == b"fixture locked dependencies"
        temporary = source
    assert not temporary.exists()
    destination = tmp_path / "staged"
    packages.copy_inspected_source(artifacts, candidate, destination)
    assert (destination / "mnemion/version.py").is_file()
    with pytest.raises(ManifestError, match="already exists"):
        packages.copy_inspected_source(artifacts, candidate, destination)
    assert (destination / "mnemion/version.py").is_file()


@pytest.mark.parametrize(
    "name,kind",
    [
        ("mnemion-4.0.8/../../outside", tarfile.REGTYPE),
        ("mnemion-4.0.8/mnemion/link", tarfile.SYMTYPE),
        ("mnemion-4.0.8/mnemion/pipe", tarfile.FIFOTYPE),
        ("mnemion-4.0.8/mnemion/version.py", tarfile.REGTYPE),
        ("mnemion-4.0.9/unrelated", tarfile.REGTYPE),
        ("mnemion-4.0.8/drive:C", tarfile.REGTYPE),
    ],
)
def test_unsafe_source_entries_never_reach_staging(tmp_path, name, kind):
    artifacts = package_inputs(tmp_path)
    rebuild_packages(tmp_path, artifacts, extra_source=[(name, b"invalid", kind)])
    candidate = release(tmp_path, artifacts)
    with pytest.raises(ManifestError):
        packages.copy_inspected_source(artifacts, candidate, tmp_path / "staged")
    assert not (tmp_path / "staged").exists()
    assert not list(tmp_path.glob("mnemion-service-review-*"))


def test_rejects_different_service_code_in_wheel(tmp_path):
    artifacts = package_inputs(tmp_path)
    rebuild_packages(
        tmp_path,
        artifacts,
        extra_wheel=[("mnemion/injected.py", b"raise RuntimeError('must not execute')")],
    )
    candidate = release(tmp_path, artifacts)
    with pytest.raises(ManifestError, match="different service code"):
        with packages.inspected_packages(artifacts, candidate):
            pytest.fail("Mismatched code was accepted")


@pytest.mark.parametrize("field", ["lock_sha256", "migrations"])
def test_signed_schema_and_dependency_lock_must_match_archive(tmp_path, field):
    artifacts = package_inputs(tmp_path)
    value = payload(tmp_path, artifacts, "a" * 40)
    if field == "lock_sha256":
        value[field] = "0" * 64
    else:
        value[field]["001_initial.sql"] = "0" * 64
    with pytest.raises(ManifestError, match="signed"):
        with packages.inspected_packages(artifacts, validate_payload(value)):
            pytest.fail("Changed schema/lock was accepted")


def test_expansion_budget_rejects_compressed_package_before_activation(tmp_path, monkeypatch):
    artifacts = package_inputs(tmp_path)
    monkeypatch.setattr(packages, "MAX_EXPANDED_BYTES", 10)
    with pytest.raises(ManifestError, match="size budget"):
        with packages.inspected_packages(artifacts, release(tmp_path, artifacts)):
            pytest.fail("Oversized package was accepted")


def test_byte_tampering_fails_before_archive_parser(tmp_path, monkeypatch):
    artifacts = package_inputs(tmp_path)
    candidate = release(tmp_path, artifacts)
    package = artifacts / "mnemion-4.0.8.tar.gz"
    package.write_bytes(b"x" * package.stat().st_size)
    monkeypatch.setattr(packages, "_source", lambda *args: pytest.fail("Unverified bytes parsed"))
    with pytest.raises(ManifestError, match="digest"):
        with packages.inspected_packages(artifacts, candidate):
            pytest.fail("Tampered package was accepted")
