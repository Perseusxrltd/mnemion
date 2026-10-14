"""Storage retention respects operator files and every recovery runtime."""

import base64
import copy
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from deploy.service_update_manifest import payload
from mnemion.service import update_cleanup as cleanup
from mnemion.service import update_state as state_io
from mnemion.service.update_manifest import ManifestError, sign_manifest
from service_tests.update_fixture import package_inputs

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Unix managed update storage")


def test_only_three_unchanged_indexed_backups_are_retained(tmp_path):
    root = state_io.directory(tmp_path / "updates")
    backups = state_io.directory(root / "backups")
    unrelated = backups / "operator-export.zip"
    unrelated.write_bytes(b"operator data")
    names = [f"pre-update-4.0.7-to-4.0.8-{index:032x}.zip" for index in range(5)]
    for name in names:
        path = backups / name
        path.write_bytes(b"verified fixture")
        path.chmod(0o600)
        cleanup.retain_backup(root, name)
    assert {p.name for p in backups.iterdir()} == {*names[-3:], unrelated.name}
    assert len(state_io.read(root / "backup-index.json")["backups"]) == 3
    with pytest.raises(ManifestError, match="name"):
        cleanup.retain_backup(root, "../operator-export.zip")


def test_replaced_backup_is_never_deleted_or_followed(tmp_path):
    root = state_io.directory(tmp_path / "updates")
    backups = state_io.directory(root / "backups")
    outside = tmp_path / "outside"
    outside.write_bytes(b"keep me")
    first = backups / f"pre-update-4.0.7-to-4.0.8-{'a' * 32}.zip"
    first.write_bytes(b"verified fixture")
    first.chmod(0o600)
    cleanup.retain_backup(root, first.name)
    first.unlink()
    first.symlink_to(outside)
    for index in range(3):
        path = backups / f"pre-update-4.0.8-to-4.0.9-{index:032x}.zip"
        path.write_bytes(b"verified fixture")
        path.chmod(0o600)
        cleanup.retain_backup(root, path.name)
    assert first.is_symlink() and outside.read_bytes() == b"keep me"


@pytest.mark.parametrize("journal", ["journal.json", "upgrade-journal.json"])
def test_signed_runtime_cleanup_keeps_active_previous_pending_and_journal(tmp_path, journal):
    root = state_io.directory(tmp_path / "updates")
    releases = state_io.directory(root / "releases")
    publisher = tmp_path / "publisher"
    artifacts = package_inputs(publisher)
    value = payload(publisher, artifacts, "a" * 40)
    key = Ed25519PrivateKey.generate()
    slots = []
    for patch in range(8, 14):
        document = copy.deepcopy(value)
        document["version"] = f"4.0.{patch}"
        for artifact in document["artifacts"]:
            artifact["name"] = artifact["name"].replace("4.0.8", document["version"])
        slot = state_io.directory(releases / f"4.0.{patch}-{'a' * 12}")
        envelope = sign_manifest(document, key.private_bytes_raw())
        state_io.write(slot / "envelope.json", {"envelope": base64.b64encode(envelope).decode()})
        slots.append(slot)
    state_io.write(root / "active.json", {"slot": slots[1].name})
    state_io.write(root / "previous.json", {"slot": slots[0].name})
    state_io.write(
        root / journal,
        {"previous": {"slot": slots[2].name}, "candidate": {"slot": slots[3].name}},
    )
    untrusted = state_io.directory(releases / f"4.0.14-{'b' * 12}")
    state_io.write(untrusted / "envelope.json", {"envelope": "unsigned"})
    foreign = state_io.directory(releases / "operator-files")
    outside = state_io.directory(tmp_path / "operator-runtime")
    linked = releases / f"4.0.15-{'b' * 12}"
    linked.symlink_to(outside, target_is_directory=True)
    assert (
        cleanup.retain_runtimes(root, key.public_key().public_bytes_raw(), pending=slots[4].name)
        == 1
    )
    assert all(path.exists() for path in slots[:5])
    assert not slots[5].exists()
    assert untrusted.exists() and foreign.exists() and linked.is_symlink() and outside.exists()


def test_pending_upgrade_backup_survives_retention(tmp_path):
    root = state_io.directory(tmp_path / "updates")
    backups = state_io.directory(root / "backups")
    names = [f"pre-update-4.1.7-to-4.2.4-{index:032x}.zip" for index in range(5)]
    state_io.write(root / "upgrade-journal.json", {"backup": names[0]})
    for name in names:
        path = backups / name
        path.write_bytes(b"verified fixture")
        path.chmod(0o600)
        cleanup.retain_backup(root, name)
    assert {path.name for path in backups.iterdir()} == {names[0], *names[-2:]}


@pytest.mark.parametrize("existed", [True, False])
def test_failed_adoption_cleans_only_its_new_private_installation(tmp_path, existed):
    state = tmp_path / "state"
    if existed:
        state_io.directory(state)
    outside = tmp_path / "credentials.json"
    state_io.write(outside, {"input": "preserve"})
    with pytest.raises(RuntimeError, match="preflight"):
        with state_io.adoption(state):
            state_io.write(state / "copied-credentials.json", {"input": "temporary"})
            raise RuntimeError("preflight failed")
    assert outside.exists()
    assert state.exists() == existed
    if existed:
        assert list(state.iterdir()) == []
