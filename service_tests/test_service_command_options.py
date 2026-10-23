"""Deferred service command options run with the full service dependencies."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("command", "option"),
    [
        (["journal"], "enroll"),
        (["recovery-kit"], "--output"),
        (["local"], "--database-runtime"),
        (["desktop-control"], "--timeout"),
        (["desktop-source"], "--root"),
        (["connect"], "--config"),
        (["desktop-agent"], "--root"),
        (["desktop-host"], "--root"),
        (["agent-package"], "--provider"),
        (["supervise"], "--state-dir"),
        (["updates"], "--state-dir"),
        (["host-control", "adopt"], "--approve-network"),
        (["host"], "snapshot"),
    ],
)
def test_deferred_command_help_preserves_its_options(command, option):
    result = subprocess.run(
        [sys.executable, "-m", "mnemion.service.cli", *command, "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert option in result.stdout


def test_native_host_schema_is_still_dispatched_without_workspace_credentials():
    result = subprocess.run(
        [sys.executable, "-m", "mnemion.service.cli", "host-control", "schema"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert set(value) == {"request", "connection", "local_owner_recovery", "roles"}
    assert "service.stop" in value["roles"]["custodian"]
    assert "service.stop" not in value["roles"]["observer"]
