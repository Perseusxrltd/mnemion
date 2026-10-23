"""Real Git/SSH encrypted backup readback and unknown delivery acknowledgements."""

import hashlib
import json
import subprocess
import threading
from uuid import uuid4

import pytest

from mnemion import backup_encryption, local_state
from mnemion.host_control import HostControlError
from mnemion.host_control.backup_git import (
    BackupTransferError,
    CHUNK,
    GitDestination,
    Repository,
    _disk_usage,
    deliver,
    verify,
)
from mnemion.host_control import backup_git
from mnemion.journal.format import JournalError
from service_tests.test_journal_ssh import ssh_repository as ssh_repository, ssh_root as ssh_root


def encrypted_files(root):
    key = backup_encryption.new_key()
    files = {}
    for kind, size in (("bundle", CHUNK + 1024), ("ledger", 1024)):
        raw = root / (kind + ".raw")
        raw.write_bytes(b"private-memory-canary-" + b"z" * size)
        path = root / (kind + ".encrypted")
        backup_encryption.encrypt_file(raw, path, key, kind=kind)
        files[kind] = path
    return files


def test_local_git_readback_does_not_claim_independent_storage(tmp_path):
    remote = tmp_path / "repository.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    destination = GitDestination(local_repository=remote)
    root = local_state.directory(tmp_path / "work")
    files = encrypted_files(root)
    host, operation = str(uuid4()), str(uuid4())
    receipt = deliver(
        root, destination, host_id=host, operation_id=operation, files=files, maximum=32 * 1024**2
    )
    assert receipt["remote_readback_verified"] and receipt["remote_storage"] is False
    assert (
        receipt["files"]["bundle"]["sha256"]
        == hashlib.sha256(files["bundle"].read_bytes()).hexdigest()
    )
    assert not list(root.glob("backup-git-*"))
    assert verify(
        root,
        destination,
        host_id=host,
        operation_id=operation,
        commit=receipt["commit"],
        manifest_sha256=receipt["manifest_sha256"],
        files=receipt["files"],
        maximum=32 * 1024**2,
    )["remote_readback_verified"]
    with pytest.raises(HostControlError):
        verify(
            root,
            destination,
            host_id=host,
            operation_id=operation,
            commit=receipt["commit"],
            manifest_sha256="0" * 64,
            files=receipt["files"],
            maximum=32 * 1024**2,
        )


def test_real_pinned_ssh_lost_push_reply_is_verified_without_repeating_push(
    ssh_repository, tmp_path, monkeypatch
):
    configured, bare, _, _ = ssh_repository
    destination = GitDestination(remote=configured.remote, ssh=configured.ssh)
    root = local_state.directory(tmp_path / "work")
    files = encrypted_files(root)
    original, pushes = Repository.git, []

    def lose_reply(self, *args, **kwargs):
        output = original(self, *args, **kwargs)
        if args[0] == "push":
            pushes.append(args)
            raise HostControlError("reply_lost", "Fixture lost the push acknowledgement.")
        return output

    monkeypatch.setattr(Repository, "git", lose_reply)
    monkeypatch.setenv("GIT_SSH_COMMAND", "unreviewed-command")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/unreviewed/agent")
    host, operation = str(uuid4()), str(uuid4())
    receipt = deliver(
        root, destination, host_id=host, operation_id=operation, files=files, maximum=32 * 1024**2
    )
    assert receipt["remote_storage"] and receipt["remote_readback_verified"]
    assert len(pushes) == 1
    # Only encrypted parts and a digest manifest are published. The server is
    # a disposable local SSH fixture, not evidence of production cloud custody.
    objects = subprocess.run(
        ["git", "-C", str(bare), "ls-tree", "--name-only", receipt["commit"]],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert set(objects) == {
        "bundle-0000.enc",
        "bundle-0001.enc",
        "ledger-0000.enc",
        "manifest.json",
    }
    assert (
        "private-memory-canary"
        not in subprocess.run(
            ["git", "-C", str(bare), "show", receipt["commit"] + ":manifest.json"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )


def test_revoked_backup_deploy_key_cannot_create_a_success_receipt(ssh_repository, tmp_path):
    configured, _, _, authorized = ssh_repository
    destination = GitDestination(remote=configured.remote, ssh=configured.ssh)
    root = local_state.directory(tmp_path / "work")
    files = encrypted_files(root)
    authorized.write_text("")
    with pytest.raises(ValueError):
        deliver(
            root,
            destination,
            host_id=uuid4(),
            operation_id=uuid4(),
            files=files,
            maximum=32 * 1024**2,
        )
    assert not list(root.glob("backup-git-*"))
    assert all(path.exists() for path in files.values())


def test_disk_budget_refuses_links_and_oversized_storage(tmp_path):
    root = local_state.directory(tmp_path / "work")
    path = root / "oversized"
    path.write_bytes(b"x" * 1025)
    with pytest.raises(HostControlError, match="disk budget"):
        _disk_usage(root, 1024)
    path.unlink()
    outside = tmp_path / "outside"
    outside.write_text("Preserve this file.")
    path.symlink_to(outside)
    with pytest.raises(HostControlError, match="storage"):
        _disk_usage(root, 1024)
    assert outside.read_text() == "Preserve this file."


def test_failed_push_retains_exact_delivery_identity_and_safe_diagnostic(tmp_path, monkeypatch):
    remote = tmp_path / "repository.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    destination = GitDestination(local_repository=remote)
    root = local_state.directory(tmp_path / "work")
    files = encrypted_files(root)
    original = backup_git.run
    pushes = []

    def timeout(args, **kwargs):
        if "push" in args:
            pushes.append(args)
            raise JournalError("journal_program_interrupted")
        return original(args, **kwargs)

    monkeypatch.setattr(backup_git, "run", timeout)
    host, operation = str(uuid4()), str(uuid4())
    with pytest.raises(BackupTransferError) as error:
        deliver(
            root,
            destination,
            host_id=host,
            operation_id=operation,
            files=files,
            maximum=32 * 1024**2,
        )
    assert len(pushes) == 1
    assert error.value.diagnostic() == {"stage": "push", "reason": "deadline", "exit_code": None}
    intent = json.loads((root / "delivery-intent.json").read_text())
    assert intent["operation_id"] == operation and intent["host_id"] == host
    assert (
        intent["manifest_sha256"]
        == hashlib.sha256(backup_git.canonical(intent["manifest"])).hexdigest()
    )
    for kind, path in files.items():
        assert intent["manifest"]["files"][kind] == {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    progress = json.loads((root / "transfer-progress.json").read_text())
    assert progress["state"] == "failed" and progress["diagnostic"] == error.value.diagnostic()
    assert "private-memory-canary" not in json.dumps({"intent": intent, "progress": progress})
    assert not list(root.glob("backup-git-*"))
    refs = subprocess.check_output(["git", "-C", str(remote), "for-each-ref"])
    assert not refs


def test_git_failure_diagnostic_does_not_forward_stderr_or_exception_values(tmp_path, monkeypatch):
    root = local_state.directory(tmp_path / "work")
    destination = GitDestination(local_repository=tmp_path / "missing-private-repository")
    repo = Repository(root / "read", destination, budget=1024**2)
    with pytest.raises(BackupTransferError) as error:
        repo.head("refs/heads/missing")
    assert error.value.diagnostic() == {
        "stage": "ls-remote",
        "reason": "git_exit",
        "exit_code": 128,
    }

    def fail(*_, **__):
        raise JournalError("private credential and path must never be returned")

    monkeypatch.setattr(backup_git, "run", fail)
    with pytest.raises(BackupTransferError) as error:
        repo.head("refs/heads/missing")
    assert error.value.diagnostic() == {
        "stage": "ls-remote",
        "reason": "process_io",
        "exit_code": None,
    }
    assert "credential" not in str(error.value) and "private" not in json.dumps(
        error.value.diagnostic()
    )


def test_final_storage_check_retains_its_failure_category(tmp_path, monkeypatch):
    destination = GitDestination(local_repository=tmp_path / "destination.git")
    repo = Repository(tmp_path / "work", destination, budget=1024**2)
    check = backup_git._disk_usage

    # A short Git command can finish between background storage samples. Its
    # mandatory final check must still identify capacity, not credentials.
    def final_check(root, maximum):
        return check(root, maximum) if threading.current_thread() is threading.main_thread() else 0

    monkeypatch.setattr(backup_git, "_disk_usage", final_check)
    repo.budget = 1
    with pytest.raises(BackupTransferError) as error:
        repo.git("rev-parse", "--is-bare-repository")
    assert error.value.diagnostic() == {
        "stage": "rev-parse",
        "reason": "storage_guard",
        "exit_code": 0,
    }
