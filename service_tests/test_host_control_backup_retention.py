"""Real Git compare-and-delete; interrupted retirement keeps its original intent."""

from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

from mnemion import backup_encryption, local_state
from mnemion.host_control import HostControlError, backup
from mnemion.host_control.backup_git import GitDestination, Repository, deliver
from mnemion.service import update_state as state_io


@pytest.fixture
def retained(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    root = local_state.directory(tmp_path / "control")
    value = {
        "host_id": str(uuid4()),
        "service_state": str(local_state.directory(tmp_path / "service")),
    }
    local_state.directory(Path(value["service_state"]) / "updates")
    spec = backup.Configuration(
        destination=GitDestination(local_repository=remote),
        secret_file=tmp_path / "not-used-by-retention.key",
        key_id="a" * 24,
        independent_storage_confirmed=True,
        independent_key_custody_confirmed=True,
        keep_verified_backups=2,
    )
    receipts = []
    local_state.directory(root / "backups")
    for _ in range(4):
        operation_id = str(uuid4())
        target = local_state.directory(root / "backups" / operation_id)
        key = backup_encryption.new_key()
        files = {}
        for kind in ("bundle", "ledger"):
            raw, encrypted = target / (kind + ".raw"), target / (kind + ".encrypted")
            raw.write_bytes(b"retention-fixture" * 100)
            backup_encryption.encrypt_file(raw, encrypted, key, kind=kind)
            raw.unlink()
            files[kind] = encrypted
        receipt = {
            "host_id": value["host_id"],
            "operation_id": operation_id,
            "destination_identity": backup.destination_identity(spec),
            **deliver(
                target,
                spec.destination,
                host_id=value["host_id"],
                operation_id=operation_id,
                files=files,
                maximum=1024**2,
            ),
        }
        state_io.write(target / "receipt.json", receipt)
        receipts.append(receipt)
    state_io.write(root / "backup-index.json", {"backups": receipts})
    return root, value, spec, receipts, remote


def test_backup_retirement_preserves_current_upgrade_backup_and_latest_verified_copies(retained):
    root, value, spec, receipts, _ = retained
    state_io.write(
        Path(value["service_state"]) / "updates/upgrade-journal.json",
        {"host_control": {"backup": {"operation_id": receipts[0]["operation_id"]}}},
    )
    backup.prune(root, value, spec)
    kept = state_io.read(root / "backup-index.json")["backups"]
    assert kept == [receipts[0], *receipts[-2:]]
    assert (root / "backups" / receipts[0]["operation_id"]).is_dir()
    assert not (root / "backups" / receipts[1]["operation_id"]).exists()


def test_lost_retirement_reply_reconciles_absence_without_repeating_delete(retained, monkeypatch):
    root, value, spec, receipts, _ = retained
    original, deleted = Repository.git, []

    def lose_reply(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if args[0] == "push":
            deleted.append(args[-1])
            if len(deleted) == 1:
                raise HostControlError("reply_lost", "Fixture lost the delete reply")
        return result

    monkeypatch.setattr(Repository, "git", lose_reply)
    with pytest.raises(HostControlError, match="lost the delete"):
        backup.prune(root, value, spec)
    assert state_io.read(root / "backup-index.json")["retiring"] == receipts[0]["operation_id"]
    assert (root / "backups" / receipts[0]["operation_id"]).is_dir()
    backup.prune(root, value, spec)
    assert state_io.read(root / "backup-index.json") == {"backups": receipts[-2:]}
    assert deleted.count(":" + receipts[0]["ref"]) == 1


def test_changed_remote_or_local_backup_custody_cannot_be_deleted(retained):
    root, value, spec, receipts, remote = retained
    subprocess.run(
        ["git", "-C", str(remote), "update-ref", receipts[0]["ref"], receipts[1]["commit"]],
        check=True,
    )
    with pytest.raises(HostControlError, match="reference changed"):
        backup.prune(root, value, spec)
    assert state_io.read(root / "backup-index.json") == {"backups": receipts}
    assert all((root / "backups" / item["operation_id"]).is_dir() for item in receipts)
