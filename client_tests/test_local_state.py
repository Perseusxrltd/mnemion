"""Local setup state must survive interruption without exposing operator secrets."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from mnemion import local_state as state


def test_interrupted_replacement_preserves_existing_private_state(tmp_path, monkeypatch):
    root = state.directory(tmp_path / "Workspace Équipe")
    path = root / "credentials.json"
    state.write(path, {"credential": "original"}, replace=False)
    before = path.read_bytes()

    def fail(*args):
        raise OSError("simulated atomic replacement failure")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        state.write(path, {"credential": "replacement"})
    assert state.read(path) == {"credential": "original"}
    assert path.read_bytes() == before
    assert [p.name for p in root.iterdir()] == ["credentials.json"]


def test_local_state_rejects_linked_or_oversized_records(tmp_path):
    root = state.directory(tmp_path / "workspace")
    path = root / "state.json"
    state.write(path, {"private": True})
    with pytest.raises(FileExistsError):
        state.write(path, {"private": False}, replace=False)
    os.link(path, root / "alias.json")
    with pytest.raises(state.LocalSetupError, match="without links"):
        state.read(path)
    (root / "alias.json").unlink()
    path.write_bytes(b" " * (state.MAX_RECORD_BYTES + 1))
    with pytest.raises(state.LocalSetupError, match="could not be read"):
        state.read(path)


def test_local_operator_lock_is_exclusive_across_processes_and_released(tmp_path):
    root = state.directory(tmp_path / "workspace")
    program = (
        "import sys; from pathlib import Path; from mnemion.local_state import lock,LocalSetupError\n"
        "try:\n with lock(Path(sys.argv[1])): pass\n"
        "except LocalSetupError as e: sys.exit(23 if e.code=='workspace_busy' else 24)\n"
    )
    command = [sys.executable, "-c", program, str(root)]
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    with state.lock(root):
        assert (
            subprocess.run(command, env=environment, capture_output=True, timeout=10).returncode
            == 23
        )
    assert subprocess.run(command, env=environment, capture_output=True, timeout=10).returncode == 0


@pytest.mark.parametrize("interrupted", [False, True])
def test_private_staging_is_owned_before_use_and_removed_after_exit(tmp_path, interrupted):
    root = state.directory(tmp_path / "Private backups Équipe")

    def capture():
        with state.temporary_directory(prefix="capture-", dir=root) as staging:
            # Native backup code must be able to validate the folder immediately,
            # including when Windows' default owner would be Administrators.
            assert state.directory(staging) == staging
            if os.name == "nt":
                from client_tests.windows_acl import assert_private_acl, assert_restricted_access

                assert_private_acl(staging, directory=True)
            else:
                assert staging.stat().st_uid == os.getuid()
                assert staging.stat().st_mode & 0o077 == 0
            state.write(staging / "ledger.json", {"private": True})
            dump = staging / "database.dump"
            dump.write_bytes(b"private database fixture")
            if os.name == "nt":
                assert_private_acl(dump, inherited=True)
                assert_restricted_access(staging, dump, staging / "ledger.json")
            if interrupted:
                raise RuntimeError("Interrupted capture")

    if interrupted:
        with pytest.raises(RuntimeError, match="Interrupted capture"):
            capture()
    else:
        capture()
    assert list(root.iterdir()) == []


def test_private_staging_never_adopts_an_existing_directory(tmp_path, monkeypatch):
    from uuid import UUID

    identifier = UUID("bd0a7b14-a7dd-4d13-8278-ae30bd8fddf1")
    existing = state.directory(tmp_path / ("capture-" + identifier.hex))
    retained = existing / "retained.txt"
    retained.write_text("Existing user data")
    monkeypatch.setattr(state, "uuid4", lambda: identifier)
    with pytest.raises(FileExistsError):
        with state.temporary_directory(prefix="capture-", dir=tmp_path):
            pytest.fail("Existing directory was adopted")
    assert retained.read_text() == "Existing user data"
    with pytest.raises(FileExistsError):
        state.directory(existing, exist_ok=False)
    assert retained.read_text() == "Existing user data"


def test_private_staging_does_not_delete_a_replacement_directory(tmp_path):
    moved = tmp_path / "retained-original"
    with pytest.raises(state.LocalSetupError, match="staging folder changed"):
        with state.temporary_directory(dir=tmp_path) as staging:
            (staging / "original.txt").write_text("Original data")
            staging.rename(moved)
            state.directory(staging, exist_ok=False)
            (staging / "replacement.txt").write_text("Replacement data")
    assert (staging / "replacement.txt").read_text() == "Replacement data"
    assert (moved / "original.txt").read_text() == "Original data"


@pytest.mark.skipif(os.name == "nt", reason="POSIX ownership and private directory modes")
def test_shared_or_redirected_state_folder_is_refused(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    with pytest.raises(state.LocalSetupError, match="private"):
        state.directory(shared)
    private = state.directory(tmp_path / "private")
    redirected = tmp_path / "redirected"
    redirected.symlink_to(private, target_is_directory=True)
    with pytest.raises(state.LocalSetupError, match="redirected"):
        state.directory(redirected / "nested")


@pytest.mark.skipif(os.name != "nt", reason="Native Windows inherited directory ACLs")
def test_windows_workspace_and_secrets_survive_removal_of_administrator_access(tmp_path):
    from client_tests.windows_acl import (
        assert_private_acl,
        assert_restricted_access,
    )

    root = state.directory(tmp_path / "Local workspace Équipe")
    assert_private_acl(root, directory=True)
    # PostgreSQL creates its own children. They must inherit the private ACL,
    # even when the elevated process's default owner is Administrators.
    data = root / "database"
    data.mkdir()
    record = data / "postgres-file"
    record.write_text("private database fixture")
    assert_private_acl(record, inherited=True)
    state.write(root / "state.json", {"ready": True})
    assert json.loads((root / "state.json").read_text()) == {"ready": True}
    assert_restricted_access(root, record, root / "state.json")


@pytest.mark.skipif(os.name != "nt", reason="Windows existing folder ownership")
def test_windows_refuses_existing_foreign_owned_folder_without_taking_ownership(tmp_path):
    from client_tests.windows_acl import make_administrators_owned, security_descriptor

    root = state.directory(tmp_path / "foreign-owner-fixture")
    (root / "retained.txt").write_text("keep existing data")
    if not make_administrators_owned(root):
        pytest.skip("Fixture requires an elevated process; native Windows CI runs elevated")
    before = security_descriptor(root)
    with pytest.raises(state.LocalSetupError, match="owned by your OS account"):
        state.directory(root)
    assert security_descriptor(root) == before
    assert (root / "retained.txt").read_text() == "keep existing data"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction rejection")
def test_windows_refuses_redirected_workspace_parent(tmp_path):
    root = state.directory(tmp_path / "retained-folder")
    junction = tmp_path / "redirected-folder"
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$ErrorActionPreference='Stop'; New-Item -ItemType Junction "
            "-Path $env:MNEMION_ACL_LINK -Target $env:MNEMION_ACL_TARGET | Out-Null",
        ],
        env={**os.environ, "MNEMION_ACL_LINK": str(junction), "MNEMION_ACL_TARGET": str(root)},
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    try:
        with pytest.raises(state.LocalSetupError, match="redirected"):
            state.directory(junction / "nested")
        assert not (root / "nested").exists()
    finally:
        junction.rmdir()


@pytest.mark.skipif(os.name == "nt", reason="POSIX system temporary-directory symlink")
def test_native_database_probe_resolves_the_system_temporary_alias(tmp_path, monkeypatch):
    from deploy.probe_native_postgres import private_probe_directory

    actual = tmp_path / "system temporary directory"
    actual.mkdir(mode=0o700)
    alias = tmp_path / "system temporary alias"
    alias.symlink_to(actual, target_is_directory=True)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(alias))
    with private_probe_directory() as root:
        assert root.parent == actual
        assert root.is_dir()
        assert root.stat().st_mode & 0o077 == 0
    assert not root.exists()
