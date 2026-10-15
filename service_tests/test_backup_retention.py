"""Real encrypted copies: reviewed cleanup must preserve recoverable history."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys

import pytest

from mnemion import backup_catalog as catalog, backup_encryption as encryption
from mnemion import backup_retention as retention, local_state as state


@pytest.fixture
def copies(tmp_path):
    root = state.directory(tmp_path / "Private inventory équipe")
    folder = tmp_path / "Cloud copies équipe"
    folder.mkdir()
    workspace = str(uuid4())
    key = encryption.new_key()
    records = []

    def capture(*, ledger_only=False, secret=key):
        operation = uuid4().hex
        receipt = {
            "workspace_id": workspace,
            "operation_id": operation,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        for kind in ("ledger",) if ledger_only else ("snapshot", "ledger"):
            source = tmp_path / (operation + ".input")
            source.write_bytes((kind + " synthetic memory and permissions\n").encode() * 8)
            path = folder / f"{kind}-20261015T000000Z-{operation}.mnemion.enc"
            encryption.encrypt_file(source, path, secret, kind=kind)
            verified = encryption.verify_file(path, secret, expected_kind=kind)
            receipt[kind] = {
                "file": str(path),
                "bytes": verified.encrypted_bytes,
                "sha256": verified.encrypted_sha256,
                "key_id": verified.key_id,
                "authenticated": True,
            }
            source.unlink()
        catalog.register(root, folder, receipt)
        state.write(
            root / "last-ledger.json", {k: v for k, v in receipt.items() if k != "snapshot"}
        )
        if not ledger_only:
            state.write(root / "last-backup.json", receipt)
        records.append(receipt)
        return receipt

    policy = retention.RetentionPolicy(mode="limited", snapshots=2, ledgers=2)
    args = (root, folder, workspace, encryption.key_id(key), policy)
    return SimpleNamespace(
        root=root,
        folder=folder,
        key=key,
        workspace=workspace,
        records=records,
        capture=capture,
        args=args,
        policy=policy,
    )


def paths(record):
    return [Path(record[kind]["file"]) for kind in ("snapshot", "ledger") if kind in record]


def test_keep_all_is_default_and_inventory_never_adopts_unknown_copies(copies):
    for _ in range(4):
        copies.capture()
    unknown = copies.folder / "untracked-backup.mnemion.enc"
    unknown.write_bytes(b"user-owned copy")
    args = (*copies.args[:-1], retention.RetentionPolicy())
    plan = retention.inventory(*args)
    assert plan["tracked_snapshots"] == plan["tracked_ledgers"] == 4
    assert plan["candidate_files"] == 0
    assert all(row["protected"] for row in plan["recent"])
    result = retention.cleanup(*args, expected_plan=plan["plan_token"])
    assert result["deleted_files"] == 0
    assert len(list(copies.folder.iterdir())) == 9
    assert state.read(copies.root / "last-retention.json") == result


def test_limits_keep_paired_ledgers_newest_access_state_and_other_keys(copies, tmp_path):
    for _ in range(5):
        copies.capture()
    protected = copies.records[-2:].copy()
    for _ in range(2):
        protected.append(copies.capture(ledger_only=True))
    other_key = copies.capture(secret=encryption.new_key())
    plan = retention.inventory(*copies.args)
    assert (plan["tracked_snapshots"], plan["tracked_ledgers"], plan["other_key_files"]) == (
        5,
        7,
        2,
    )
    assert plan["candidate_files"] == plan["batch_files"] == 6
    result = retention.cleanup(*copies.args, expected_plan=plan["plan_token"])
    assert result["state"] == "complete" and result["deleted_files"] == 6
    assert result["remaining_candidates"] == 0
    for record in protected:
        for kind in ("snapshot", "ledger"):
            if kind not in record:
                continue
            path = Path(record[kind]["file"])
            destination = tmp_path / (path.stem + ".decrypted")
            encryption.decrypt_file(path, destination, copies.key, expected_kind=kind)
            assert b"synthetic memory and permissions" in destination.read_bytes()
    assert all(path.exists() for path in paths(other_key))
    assert state.read(copies.root / "last-retention.json") == result


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_invalid_retained_point_blocks_all_old_file_removal(copies, damage):
    for _ in range(3):
        copies.capture()
    newest = Path(copies.records[-1]["snapshot"]["file"])
    if damage == "missing":
        newest.unlink()
    else:
        content = bytearray(newest.read_bytes())
        content[-1] ^= 1
        newest.write_bytes(content)
    before = set(copies.folder.iterdir())
    result = retention.cleanup(*copies.args)
    assert result["state"] == "blocked" and result["deleted_files"] == 0
    assert set(copies.folder.iterdir()) == before
    assert state.read(copies.root / "last-retention.json")["state"] == "blocked"


def test_changed_candidate_is_kept_while_other_eligible_files_are_removed(copies):
    for _ in range(4):
        copies.capture()
    changed = Path(copies.records[0]["snapshot"]["file"])
    changed.write_bytes(b"external replacement".ljust(changed.stat().st_size, b"!"))
    before = changed.read_bytes()
    result = retention.cleanup(*copies.args)
    assert (result["state"], result["deleted_files"], result["skipped_files"]) == ("partial", 3, 1)
    assert changed.read_bytes() == before
    assert all(path.exists() for record in copies.records[-2:] for path in paths(record))


def test_cleanup_requires_review_again_after_inventory_changes(copies):
    for _ in range(3):
        copies.capture()
    plan = retention.inventory(*copies.args)
    copies.capture(ledger_only=True)
    before = set(copies.folder.iterdir())
    with pytest.raises(state.LocalSetupError, match="Review the current"):
        retention.cleanup(*copies.args, expected_plan=plan["plan_token"])
    assert set(copies.folder.iterdir()) == before


def test_replaced_cloud_folder_does_not_inherit_removal_authority(copies, tmp_path):
    for _ in range(3):
        copies.capture()
    previous = tmp_path / "Old mounted folder"
    copies.folder.rename(previous)
    copies.folder.mkdir()
    for path in previous.iterdir():
        shutil.copyfile(path, copies.folder / path.name)
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in copies.folder.iterdir()
    }
    plan = retention.inventory(*copies.args)
    assert plan["state"] == "untracked" and plan["candidate_files"] == 0
    assert retention.cleanup(*copies.args)["deleted_files"] == 0
    assert before == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in copies.folder.iterdir()
    }


def test_cancelled_partial_cleanup_records_completed_removals(copies):
    for _ in range(4):
        copies.capture()
    original = set(copies.folder.iterdir())
    with pytest.raises(encryption.EncryptionCancelled):
        retention.cleanup(
            *copies.args, cancelled=lambda: len(set(copies.folder.iterdir())) < len(original)
        )
    recorded = state.read(copies.root / "last-retention.json")
    assert recorded["state"] == "cancelled" and recorded["deleted_files"] == 1
    assert recorded["remaining_candidates"] == 3
    assert all(path.exists() for record in copies.records[-2:] for path in paths(record))


def test_missing_candidates_do_not_starve_later_bounded_batches(copies, monkeypatch):
    for _ in range(4):
        copies.capture()
    monkeypatch.setattr(retention, "BATCH_LIMIT", 2)
    for path in paths(copies.records[0]):
        path.unlink()
    assert retention.cleanup(*copies.args)["skipped_files"] == 2
    second = retention.cleanup(*copies.args)
    assert second["deleted_files"] == 2 and second["remaining_candidates"] == 2
    assert not any(path.exists() for path in paths(copies.records[1]))


def test_invalid_catalog_path_cannot_escape_the_managed_folder(copies, tmp_path):
    for _ in range(3):
        copies.capture()
    foreign = tmp_path / "keep-me"
    foreign.write_bytes(b"unrelated user data")
    with catalog.open_catalog(copies.root) as connection:
        connection.execute("UPDATE copies SET name='../keep-me' WHERE sequence=1")
    before = set(copies.folder.iterdir())
    with pytest.raises(state.LocalSetupError, match="inventory could not be verified"):
        retention.cleanup(*copies.args)
    assert foreign.read_bytes() == b"unrelated user data"
    assert set(copies.folder.iterdir()) == before


def test_one_full_point_never_authorizes_automatic_cleanup(copies):
    copies.capture()
    for _ in range(5):
        copies.capture(ledger_only=True)
    result = retention.cleanup(*copies.args)
    assert result["state"] == "blocked" and result["deleted_files"] == 0
    assert len(list(copies.folder.iterdir())) == 7


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory flush semantics")
def test_successful_removal_is_recorded_when_a_storage_provider_cannot_flush_directories(
    copies, monkeypatch
):
    for _ in range(3):
        copies.capture()
    original = os.fsync
    cloud_identity = copies.folder.stat()

    def sync(descriptor):
        info = os.fstat(descriptor)
        if stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == (
            cloud_identity.st_dev,
            cloud_identity.st_ino,
        ):
            raise OSError("This storage provider cannot flush a directory")
        return original(descriptor)

    monkeypatch.setattr(os, "fsync", sync)
    result = retention.cleanup(*copies.args)
    assert result["deleted_files"] == 2 and result["state"] == "complete"
    assert retention.inventory(*copies.args)["candidate_files"] == 0


def test_cli_reviews_and_prunes_offline_without_a_recovery_key(copies, tmp_path):
    from mnemion import local_backup as backup
    from mnemion.local_workspace import SetupOptions

    state.write(
        copies.root / "configuration.json",
        {
            "format": 1,
            "workspace_id": copies.workspace,
            "database_port": 17893,
            **SetupOptions(workspace_name="Offline inventory", owner_name="Owner").model_dump(),
        },
    )
    selection = tmp_path / "Selected cloud folder"
    selection.mkdir()
    destination = backup._destination(copies.root, str(selection), copies.workspace)
    for _ in range(3):
        record = copies.capture()
        for kind in ("snapshot", "ledger"):
            source = Path(record[kind]["file"])
            target = destination / source.name
            shutil.copyfile(source, target)
            record[kind] = {**record[kind], "file": str(target)}
        catalog.register(copies.root, destination, record)
    options = {
        "workspace_id": copies.workspace,
        "destination": str(selection),
        "key_id": encryption.key_id(copies.key),
        "policy": copies.policy.model_dump(),
    }

    def cli(action, request):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "mnemion.service.cli",
                "local",
                action,
                "--root",
                str(copies.root),
            ],
            input=json.dumps(request) + "\n",
            text=True,
            capture_output=True,
            timeout=30,
        )
        assert copies.key not in result.stdout + result.stderr
        return result

    reviewed = cli("backup-inventory", options)
    assert reviewed.returncode == 0, reviewed.stdout
    plan = json.loads(reviewed.stdout)["receipt"]
    assert plan["candidate_files"] == 2
    wrong = cli("backup-prune", {**options, "plan_token": plan["plan_token"], "confirm": False})
    assert wrong.returncode != 0 and len(list(destination.iterdir())) == 6
    stale = cli("backup-prune", {**options, "plan_token": "f" * 64, "confirm": True})
    assert stale.returncode != 0 and len(list(destination.iterdir())) == 6
    completed = cli("backup-prune", {**options, "plan_token": plan["plan_token"], "confirm": True})
    assert completed.returncode == 0, completed.stdout
    events = [json.loads(line) for line in completed.stdout.splitlines()]
    assert events[-1]["event"] == "backup_retention"
    assert events[-1]["receipt"]["deleted_files"] == 2
    assert len(list(destination.iterdir())) == 4
    wrong_workspace = cli("backup-inventory", {**options, "workspace_id": str(uuid4())})
    assert wrong_workspace.returncode != 0
    assert not (copies.root / "database").exists()


def test_inventory_does_not_create_an_unavailable_managed_folder(tmp_path):
    from mnemion import local_backup as backup
    from mnemion.local_workspace import SetupOptions

    root = state.directory(tmp_path / "Local owner")
    workspace = str(uuid4())
    state.write(
        root / "configuration.json",
        {
            "format": 1,
            "workspace_id": workspace,
            "database_port": 17893,
            **SetupOptions(workspace_name="Owner", owner_name="Owner").model_dump(),
        },
    )
    selection = tmp_path / "Chosen storage"
    selection.mkdir()
    request = backup.BackupInventoryRequest.model_validate_json(
        json.dumps({"workspace_id": workspace, "destination": str(selection), "key_id": "a" * 24})
    )
    result = backup.inspect_inventory(root, request)
    assert result["tracked_snapshots"] == result["tracked_ledgers"] == 0
    assert list(selection.iterdir()) == []
