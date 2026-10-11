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
        assert_restricted_access,
        current_token_user_sid,
        security_descriptor,
    )

    identity = current_token_user_sid()
    root = state.directory(tmp_path / "Local workspace Équipe")
    descriptor = security_descriptor(root)
    assert descriptor.startswith(f"O:{identity}D:P")
    assert descriptor.count("(") == 1 and f"(A;OICI;FA;;;{identity})" in descriptor
    # PostgreSQL creates its own children. They must inherit the private ACL,
    # even when the elevated process's default owner is Administrators.
    data = root / "database"
    data.mkdir()
    record = data / "postgres-file"
    record.write_text("private database fixture")
    inherited = security_descriptor(record).split("D:", 1)[1]
    assert inherited.count("(") == 1 and f";FA;;;{identity})" in inherited
    state.write(root / "state.json", {"ready": True})
    assert json.loads((root / "state.json").read_text()) == {"ready": True}
    assert_restricted_access(root, record, root / "state.json")


@pytest.mark.skipif(os.name != "nt", reason="Windows existing folder ownership")
def test_windows_refuses_existing_foreign_owned_folder_without_taking_ownership(tmp_path):
    from client_tests.windows_acl import security_descriptor

    root = state.directory(tmp_path / "foreign-owner-fixture")
    (root / "retained.txt").write_text("keep existing data")
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$ErrorActionPreference='Stop'; "
            "$identity=[Security.Principal.WindowsIdentity]::GetCurrent(); "
            "$principal=[Security.Principal.WindowsPrincipal]::new($identity); "
            "if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { exit 20 }; "
            "$acl=Get-Acl -LiteralPath $env:MNEMION_ACL_PROBE; "
            "$acl.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')); "
            "Set-Acl -LiteralPath $env:MNEMION_ACL_PROBE -AclObject $acl",
        ],
        env={**os.environ, "MNEMION_ACL_PROBE": str(root)},
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode == 20:
        pytest.skip("Fixture requires an elevated process; native Windows CI runs elevated")
    assert result.returncode == 0, result.stderr
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
