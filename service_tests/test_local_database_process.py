"""A database daemon must not keep its launcher capture or timeout open."""

import json
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import psutil
import pytest

from mnemion.local_database import LocalDatabase, _data_argument, _same_path
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


def test_database_process_identity_accepts_equivalent_paths_without_accepting_neighbors(tmp_path):
    data = directory(tmp_path / "Workspace Équipe")
    other = directory(tmp_path / "Workspace Équipe other")
    alias = str(data.parent / ".." / data.parent.name / data.name)
    for arguments in (
        ["postgres", "-D", alias],
        ["postgres", "-D" + alias],
        ["postgres", "--pgdata=" + alias],
    ):
        assert _data_argument(arguments, data)
    for arguments in (
        ["postgres", "-D", str(other), "--unrelated", str(data)],
        ["postgres", "--unrelated", str(data)],
        ["postgres", "-D", str(data), "-D", str(other)],
        ["postgres", "-D", data.name],
        ["postgres", "-D"],
    ):
        assert not _data_argument(arguments, data)
    assert not _same_path(other, data)
    assert not _same_path(tmp_path / "absent", data)


def test_database_process_executable_must_be_the_bundled_file(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "postgres.exe").write_bytes(b"fixture")
    (second / "postgres.exe").write_bytes(b"fixture")
    assert _same_path(first / ".." / "first" / "postgres.exe", first / "postgres.exe")
    assert not _same_path(second / "postgres.exe", first / "postgres.exe")


@pytest.mark.skipif(sys.platform != "win32", reason="Actual Windows file aliases")
def test_windows_database_identity_accepts_slashes_case_and_short_paths(tmp_path):
    import ctypes
    from ctypes import wintypes

    data = directory(tmp_path / "Private Workspace Équipe with spaces")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetShortPathNameW.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(32768)
    length = kernel.GetShortPathNameW(str(data), buffer, len(buffer))
    assert 0 < length < len(buffer)
    # NTFS may disable generation of new 8.3 names. The API's returned alias,
    # case-insensitive spelling and slash form must still identify this folder.
    for spelling in (str(data).swapcase(), data.as_posix(), buffer.value):
        assert _data_argument(["postgres.exe", "-D", spelling], data)
