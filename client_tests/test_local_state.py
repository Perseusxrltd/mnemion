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
def test_windows_workspace_protects_new_database_files_with_inherited_owner_access(tmp_path):
    root = state.directory(tmp_path / "Local workspace Équipe")
    # PostgreSQL creates its own children. They must inherit the private ACL.
    data = root / "database"
    data.mkdir()
    record = data / "postgres-file"
    record.write_text("private database fixture")
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$a=Get-Acl -LiteralPath $env:MNEMION_ACL_PROBE; $a.Sddl",
        ],
        env={**os.environ, "MNEMION_ACL_PROBE": str(record)},
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    dacl = result.stdout.strip().split("D:", 1)[1]
    assert dacl.count("(") == 1 and ";FA;;;OW)" in dacl
    state.write(root / "state.json", {"ready": True})
    assert json.loads((root / "state.json").read_text()) == {"ready": True}
