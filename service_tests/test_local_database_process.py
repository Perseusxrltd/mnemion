"""A database daemon must not keep its launcher capture or timeout open."""

import json
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import psutil
import pytest

from mnemion.local_database import LocalDatabase
from mnemion.local_state import LocalSetupError, directory


@pytest.fixture
def database(tmp_path, monkeypatch):
    root = directory(tmp_path / "workspace")
    value = LocalDatabase(root, tmp_path / "runtime", {}, {})
    # Exercise the production launcher with a portable process fixture; no
    # installed database or personal workspace is read or changed.
    monkeypatch.setattr(value, "tool", lambda _: Path(sys.executable))
    return value


def descendant_launcher(database, *, wait):
    pid_file = database.root / "fixture-process.json"
    marker = "mnemion-process-fixture-" + uuid4().hex
    script = "\n".join(
        [
            "import json, subprocess, sys, time",
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)', sys.argv[2]])",
            "with open(sys.argv[1], 'w') as stream: json.dump({'pid': child.pid}, stream)",
            "print('launcher finished', flush=True)",
            "time.sleep(20)" if wait else "",
        ]
    )
    return pid_file, marker, ["-c", script, str(pid_file), marker]


def stop_descendant(pid_file, marker):
    if not pid_file.exists():
        return
    try:
        process = psutil.Process(json.loads(pid_file.read_text())["pid"])
        # Never signal a process that does not match this disposable child.
        assert marker in process.cmdline()
        process.terminate()
        try:
            process.wait(timeout=3)
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    except psutil.NoSuchProcess:
        pass


def test_launcher_returns_while_descendant_still_owns_standard_handles(database):
    pid_file, marker, arguments = descendant_launcher(database, wait=False)
    started = time.monotonic()
    try:
        result = database.run("pg_ctl", arguments, timeout=2)
        assert isinstance(result, subprocess.CompletedProcess)
        assert result.returncode == 0 and "launcher finished" in result.stdout
        assert time.monotonic() - started < 5
        assert psutil.Process(json.loads(pid_file.read_text())["pid"]).is_running()
    finally:
        stop_descendant(pid_file, marker)


def test_launcher_timeout_does_not_wait_for_a_descendants_pipe_eof(database):
    pid_file, marker, arguments = descendant_launcher(database, wait=True)
    started = time.monotonic()
    try:
        with pytest.raises(LocalSetupError) as failure:
            database.run("pg_ctl", arguments, timeout=1)
        assert failure.value.code == "database_tool"
        assert "launcher finished" not in str(failure.value)
        assert time.monotonic() - started < 5
        assert psutil.Process(json.loads(pid_file.read_text())["pid"]).is_running()
    finally:
        stop_descendant(pid_file, marker)


def test_database_tool_failure_stays_private_and_status_exit_codes_remain_available(database):
    arguments = [
        "-c",
        "import sys; print('fixture private database diagnostic', file=sys.stderr); sys.exit(3)",
    ]
    with pytest.raises(LocalSetupError) as failure:
        database.run("pg_ctl", arguments)
    assert failure.value.code == "database_tool"
    assert "fixture private" not in str(failure.value)
    assert database.run("pg_ctl", arguments, check=False).returncode == 3
