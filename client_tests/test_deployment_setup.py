"""The portable setup tool never overwrites secrets or exposes them in output."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess

import pytest


@pytest.fixture
def setup_tool():
    path = Path(__file__).resolve().parents[1] / "deploy" / "manage.py"
    spec = importlib.util.spec_from_file_location("deployment_setup_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prepare_preserves_credentials_and_does_not_print_them(setup_tool, tmp_path, capsys):
    state = tmp_path / "private state"
    args = ["init", "--prepare-only", "--state-dir", str(state), "--tenant", "Fixture team"]
    assert setup_tool.main(args) == 0
    secret = (state / "database.password").read_text().strip()
    original = (state / "deployment.json").read_bytes()
    assert len(secret) >= 48
    assert setup_tool.main(args) == 0
    assert (state / "database.password").read_text().strip() == secret
    assert (state / "deployment.json").read_bytes() == original
    assert secret not in capsys.readouterr().out
    if os.name != "nt":
        assert state.stat().st_mode & 0o777 == 0o700
        assert (state / "database.password").stat().st_mode & 0o777 == 0o600


def test_remote_plaintext_setup_rejected_before_secret_created(setup_tool, tmp_path):
    assert (
        setup_tool.main(
            [
                "init",
                "--prepare-only",
                "--state-dir",
                str(tmp_path),
                "--public-url",
                "http://company.example",
            ]
        )
        == 1
    )
    assert not (tmp_path / "database.password").exists()


def test_restore_command_checks_local_inputs_before_stopping_any_service(
    setup_tool, tmp_path, monkeypatch
):
    assert setup_tool.main(["init", "--prepare-only", "--state-dir", str(tmp_path)]) == 0
    calls = []
    monkeypatch.setattr(setup_tool, "compose", lambda *args, **kwargs: calls.append(args))
    args = ["adopt-restored", "--state-dir", str(tmp_path), "--database", "recovered"]
    assert setup_tool.main([*args, "--recovery-file", "../outside.json"]) == 1
    assert setup_tool.main([*args, "--recovery-file", "missing.json"]) == 1
    assert calls == []


@pytest.mark.skipif(os.name != "nt", reason="Checks native Windows directory ACLs")
def test_windows_private_state_removes_existing_explicit_world_grant(setup_tool, tmp_path):
    folder = tmp_path / "private"
    folder.mkdir()
    subprocess.run(
        ["icacls", str(folder), "/grant", "*S-1-1-0:(OI)(CI)R"], check=True, capture_output=True
    )
    setup_tool.private_directory(folder)
    script = """$ErrorActionPreference='Stop'
$acl = [System.IO.Directory]::GetAccessControl($env:MNEMION_ACL_FIXTURE, [System.Security.AccessControl.AccessControlSections]::Access)
$entries = $acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]) | ForEach-Object {
  $_.IdentityReference.Value
}
ConvertTo-Json -InputObject @($entries)
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env={**os.environ, "MNEMION_ACL_FIXTURE": str(folder)},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    entries = json.loads(result.stdout)
    assert len(entries) == 2
    assert "S-1-1-0" not in entries
    assert "S-1-5-18" in entries
