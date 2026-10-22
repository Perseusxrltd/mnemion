"""A killed launcher cannot release host exclusion while its child still runs."""

import os
from pathlib import Path
import signal
import subprocess
import sys

import psutil
import pytest

from mnemion.service import update_state as state_io
from service_tests.test_supervision import wait_until

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Unix managed host process custody")


def test_running_child_retains_operation_lock_after_its_launcher_is_killed(tmp_path):
    root = state_io.directory(tmp_path / "host-operation")
    child_code = (
        "import os,sys,time; from pathlib import Path; "
        "Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)"
    )
    launcher_code = """
import sys
from pathlib import Path
from mnemion.service import update_state as state_io, service_updates as updates
root=Path(sys.argv[1])
with state_io.lock(root):
    updates._command(
        [sys.executable, "-c", sys.argv[2], str(root/"child.pid")],
        cwd=root, environment=updates._environment(), log=root/"child.log", timeout=40,
    )
"""
    process = subprocess.Popen(
        [sys.executable, "-c", launcher_code, str(root), child_code],
        cwd=Path(__file__).resolve().parents[1],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    child = None
    try:
        wait_until(lambda: (root / "child.pid").exists(), seconds=10)
        child = psutil.Process(int((root / "child.pid").read_text()))
        assert child.ppid() == process.pid
        process.kill()
        assert process.wait(timeout=5) == -signal.SIGKILL
        assert child.is_running()
        with pytest.raises(state_io.OperationBusy):
            with state_io.lock(root):
                pytest.fail("A running managed child lost host-operation custody")
        child.terminate()

        def released():
            try:
                with state_io.lock(root):
                    return True
            except state_io.OperationBusy:
                return False

        assert wait_until(released, seconds=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if child is not None and child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
            child.kill()
