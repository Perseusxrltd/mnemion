"""The service CLI keeps its command contract without unrelated startup work."""

from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("command", [[], ["serve"], ["worker"], ["models"], ["backup"]])
def test_basic_help_does_not_initialize_clients_models_or_recovery(command):
    program = """
import importlib.abc
import sys

class UnrelatedImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        roots = ('asyncssh', 'fastapi', 'mcp', 'onnxruntime', 'torch',
                 'mnemion.local_workspace', 'mnemion.host_control',
                 'mnemion.service.recovery_kit', 'mnemion.service.model_registry')
        if any(fullname == root or fullname.startswith(root + '.') for root in roots):
            raise AssertionError('Unrelated service startup import: ' + fullname)

sys.meta_path.insert(0, UnrelatedImports())
from mnemion.service.cli import main
main(sys.argv[1:])
"""
    result = subprocess.run(
        [sys.executable, "-c", program, *command, "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "usage: mnemion-service" in result.stdout
    if not command:
        assert all(name in result.stdout for name in ("host-control", "local", "recovery-kit"))
