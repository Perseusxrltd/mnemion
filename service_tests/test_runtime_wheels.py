"""Signed dependency fixtures cover policy only; native CI executes real wheels."""

import hashlib
import json
import stat
from types import SimpleNamespace
import zipfile

import pytest

from mnemion.service import runtime_wheels as wheels
from mnemion.service.update_manifest import Artifact, ManifestError, validate_payload
from deploy.service_update_manifest import payload as release_payload
from service_tests.update_fixture import package_inputs

VERSION = "50.0.2"
NAME = f"cryptography-{VERSION}-cp311-abi3-macosx_11_0_x86_64.whl"
PREFIX = f"cryptography-{VERSION}.dist-info/"


@pytest.fixture
def native_wheel(tmp_path):
    lock = tmp_path / "uv.lock"
    lock.write_text(
        '[[package]]\nname="cryptography"\nversion="50.0.2"\n'
        'sdist={hash="sha256:' + "a" * 64 + '"}\n'
    )
    provenance = {
        "format": 1,
        "cryptography_version": VERSION,
        "cryptography_source_sha256": "a" * 64,
        "openssl_version": "3.5.9",
        "openssl_source_sha256": "b" * 64,
        "static_openssl": True,
        "target": "macosx_11_0_x86_64",
    }
    members = {
        "cryptography/__init__.py": b"# protocol fixture, never imported\n",
        "cryptography/hazmat/bindings/_rust.abi3.so": b"protocol fixture, not executable",
        PREFIX + "METADATA": b"Metadata-Version: 2.4\nName: cryptography\nVersion: 50.0.2\n\n",
        PREFIX
        + "WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: cp311-abi3-macosx_11_0_x86_64\n\n",
        PREFIX + "licenses/LICENSE.OpenSSL": b"license fixture",
        PREFIX + "mnemion-build.json": json.dumps(provenance).encode(),
    }
    path = tmp_path / NAME

    def build(extra=()):
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in members.items():
                archive.writestr(name, content)
            for name, content in extra:
                archive.writestr(name, content)
        return Artifact(NAME, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())

    return SimpleNamespace(path=path, lock=lock, members=members, build=build)


def test_native_dependency_matches_lock_and_preserves_signed_bytes(native_wheel):
    fixture = native_wheel
    artifact = fixture.build()
    inventory = wheels.inspect_wheel(fixture.path, artifact, fixture.lock)
    assert len(inventory) == len(fixture.members)
    fixture.path.write_bytes(b"x" * artifact.size)
    with pytest.raises(ManifestError, match="digest"):
        wheels.inspect_wheel(fixture.path, artifact, fixture.lock)


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "mnemion/replace.py",
        "surprise.pth",
        "cryptography-50.0.2.data/scripts/surprise",
    ],
)
def test_native_dependency_cannot_install_outside_its_package(native_wheel, name):
    artifact = native_wheel.build([(name, b"unexpected")])
    with pytest.raises(ManifestError, match="path"):
        wheels.inspect_wheel(native_wheel.path, artifact, native_wheel.lock)


def test_native_dependency_rejects_links_and_duplicate_members(native_wheel):
    name = "cryptography/escape"
    entry = zipfile.ZipInfo(name)
    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
    artifact = native_wheel.build([(entry, b"/outside")])
    with pytest.raises(ManifestError, match="link"):
        wheels.inspect_wheel(native_wheel.path, artifact, native_wheel.lock)
    with pytest.warns(UserWarning, match="Duplicate name"):
        artifact = native_wheel.build([("cryptography/__init__.py", b"replacement")])
    with pytest.raises(ManifestError, match="path"):
        wheels.inspect_wheel(native_wheel.path, artifact, native_wheel.lock)


@pytest.mark.parametrize(
    "field,value",
    [
        ("cryptography_version", "49.0.0"),
        ("cryptography_source_sha256", "c" * 64),
        ("static_openssl", False),
        ("target", "macosx_11_0_arm64"),
        ("openssl_source_sha256", "missing"),
    ],
)
def test_native_dependency_provenance_is_required(native_wheel, field, value):
    name = PREFIX + "mnemion-build.json"
    provenance = json.loads(native_wheel.members[name])
    provenance[field] = value
    native_wheel.members[name] = json.dumps(provenance).encode()
    artifact = native_wheel.build()
    with pytest.raises(ManifestError, match="provenance"):
        wheels.inspect_wheel(native_wheel.path, artifact, native_wheel.lock)


def test_native_dependency_cannot_override_another_locked_version(native_wheel):
    artifact = native_wheel.build()
    native_wheel.lock.write_text(native_wheel.lock.read_text().replace("50.0.2", "49.0.0"))
    with pytest.raises(ManifestError, match="dependency lock"):
        wheels.inspect_wheel(native_wheel.path, artifact, native_wheel.lock)


def test_native_dependency_metadata_and_abi_must_match(native_wheel):
    native_wheel.members[PREFIX + "METADATA"] = b"Name: another-package\nVersion: 50.0.2\n\n"
    artifact = native_wheel.build()
    with pytest.raises(ManifestError, match="metadata"):
        wheels.inspect_wheel(native_wheel.path, artifact, native_wheel.lock)
    native_wheel.members[PREFIX + "METADATA"] = b"Name: cryptography\nVersion: 50.0.2\n\n"
    native_wheel.members[PREFIX + "WHEEL"] = (
        b"Root-Is-Purelib: false\nTag: cp312-cp312-macosx_11_0_x86_64\n\n"
    )
    artifact = native_wheel.build()
    with pytest.raises(ManifestError, match="tags"):
        wheels.inspect_wheel(native_wheel.path, artifact, native_wheel.lock)


def test_only_intel_mac_hosts_use_the_signed_native_dependency(monkeypatch, native_wheel):
    artifact = native_wheel.build()
    release = SimpleNamespace(runtime_wheels=(artifact,))
    monkeypatch.setattr(wheels.platform, "system", lambda: "Linux")
    monkeypatch.setattr(wheels.platform, "machine", lambda: "x86_64")
    assert wheels.selected_wheels(release) == ()
    monkeypatch.setattr(wheels.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(wheels.platform, "mac_ver", lambda: ("15.7", (), ""))
    assert wheels.selected_wheels(release) == (artifact,)
    with pytest.raises(ManifestError, match="lacks"):
        wheels.selected_wheels(SimpleNamespace(runtime_wheels=()))
    monkeypatch.setattr(wheels.platform, "machine", lambda: "arm64")
    assert wheels.selected_wheels(release) == ()


def test_native_dependency_is_rechecked_before_runtime_handoff(monkeypatch, native_wheel, tmp_path):
    artifact = native_wheel.build()
    release = SimpleNamespace(
        runtime_wheels=(artifact,),
        lock_sha256=hashlib.sha256(native_wheel.lock.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(wheels, "selected_wheels", lambda value: value.runtime_wheels)
    package = tmp_path / "site-packages/mnemion"
    package.mkdir(parents=True)
    for name, content in native_wheel.members.items():
        if name.startswith("cryptography/"):
            destination = package.parent / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
    wheels.verify_installed(tmp_path, release, package, native_wheel.lock)
    library = package.parent / "cryptography/hazmat/bindings/_rust.abi3.so"
    library.write_bytes(b"changed installed library")
    with pytest.raises(ManifestError, match="differs"):
        wheels.verify_installed(tmp_path, release, package, native_wheel.lock)
    native_wheel.lock.write_text("changed lock")
    with pytest.raises(ManifestError, match="lock changed"):
        wheels.verify_installed(tmp_path, release, package, native_wheel.lock)


def test_manifest_authenticates_only_supported_native_wheel_names(tmp_path):
    payload = release_payload(tmp_path, package_inputs(tmp_path), "a" * 40)
    payload["runtime_wheels"] = [{"name": NAME, "size": 20, "sha256": "a" * 64}]
    release = validate_payload(payload)
    assert release.runtime_wheels == (Artifact(NAME, 20, "a" * 64),)
    for name in [
        "../" + NAME,
        NAME.replace("x86_64", "arm64"),
        NAME.replace("cryptography", "other"),
    ]:
        payload["runtime_wheels"][0]["name"] = name
        with pytest.raises(ManifestError, match="Unsupported"):
            validate_payload(payload)
    payload["runtime_wheels"][0]["name"] = NAME
    payload["runtime_wheels"][0]["size"] = True
    with pytest.raises(ManifestError, match="size"):
        validate_payload(payload)
