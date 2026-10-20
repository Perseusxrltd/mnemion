import os
import stat

import pytest

from mnemion.private_output import private_output


def test_private_output_preserves_existing_files_and_removes_failed_downloads(tmp_path):
    path = tmp_path / "Équipe agent result.json"
    with private_output(path) as output:
        output.write(b"private result")
    assert path.read_bytes() == b"private result"
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        with private_output(path):
            pass
    assert path.read_bytes() == b"private result"
    failed = tmp_path / "failed.json"
    with pytest.raises(RuntimeError):
        with private_output(failed) as output:
            output.write(b"partial result")
            raise RuntimeError("Interrupted")
    assert not failed.exists()
    for name in ("CON", "key.json:stream"):
        with pytest.raises(ValueError):
            with private_output(tmp_path / name):
                pass


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL verification")
def test_windows_output_has_current_user_owner_and_private_dacl_before_write(tmp_path):
    from client_tests.windows_acl import assert_private_acl

    path = tmp_path / "private.json"
    with private_output(path) as output:
        # The handle is returned only after atomic owner/DACL creation, before
        # any credentials or downloaded bytes are supplied by the caller.
        assert_private_acl(path)
        output.write(b"owner can reopen this file")
    assert path.read_bytes() == b"owner can reopen this file"


@pytest.mark.skipif(os.name != "nt", reason="Native Windows agent configuration custody")
def test_windows_agent_setup_protects_backup_and_replacement_before_writing(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from pathlib import Path

    from client_tests.windows_acl import assert_private_acl
    from mnemion import agent_setup

    target = tmp_path / "Agent settings Équipe.json"
    original = b'{"provider":{"credential":"private-test-value"},"mcpServers":{}}'
    target.write_bytes(original)
    observed = []

    @contextmanager
    def observed_output(path):
        with private_output(path) as output:
            # Existing agent settings may contain other providers' secrets.
            # Both copies must be private before the first byte is supplied.
            assert_private_acl(path)
            assert path.stat().st_size == 0
            observed.append(path)
            yield output

    monkeypatch.setattr(agent_setup, "private_output", observed_output)
    result = agent_setup.apply(agent_setup.plan("cursor", target, tmp_path / "private.json"))
    backup = Path(result["backup"])
    assert len(observed) == 2
    assert backup.read_bytes() == original
    assert b"private-test-value" in target.read_bytes()
    assert_private_acl(backup)
    assert_private_acl(target)
    assert not list(tmp_path.glob(".mnemion-agent-*"))


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission verification")
def test_a_filesystem_that_ignores_private_mode_fails_before_receiving_data(tmp_path, monkeypatch):
    original = os.fchmod
    monkeypatch.setattr(os, "fchmod", lambda descriptor, mode: original(descriptor, 0o644))
    path = tmp_path / "must-stay-private.json"
    with pytest.raises(OSError, match="cannot enforce"):
        with private_output(path):
            pytest.fail("Unprotected file became writable by the caller")
    assert not path.exists()


def test_private_process_returns_while_a_descendant_retains_output_handles(tmp_path):
    from pathlib import Path
    import sys
    import time

    from mnemion.private_output import private_process

    ready, release, exited = (tmp_path / name for name in ("ready", "release", "exited"))
    child = (
        "from pathlib import Path; import sys,time\n"
        "ready,release,exited=map(Path,sys.argv[1:])\n"
        "ready.touch(); deadline=time.monotonic()+15\n"
        "while not release.exists() and time.monotonic()<deadline: time.sleep(0.01)\n"
        "exited.touch()\n"
    )
    launcher = (
        "from pathlib import Path; import subprocess,sys,time\n"
        "subprocess.Popen([sys.executable,'-c',sys.argv[1],*sys.argv[2:]],close_fds=False)\n"
        "deadline=time.monotonic()+5\n"
        "while not Path(sys.argv[2]).exists() and time.monotonic()<deadline: time.sleep(0.01)\n"
        "print('launcher finished',flush=True); print('launcher diagnostic',file=sys.stderr,flush=True)\n"
    )
    try:
        result = private_process(
            [sys.executable, "-c", launcher, child, str(ready), str(release), str(exited)],
            directory=tmp_path,
            timeout=5,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "launcher finished"
        assert result.stderr.strip() == "launcher diagnostic"
        assert ready.exists() and not exited.exists()
    finally:
        release.touch()
        deadline = time.monotonic() + 5
        while ready.exists() and not exited.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
    assert exited.exists()
    assert not list(Path(tmp_path).glob(".process-*"))


def test_private_process_keeps_timeout_cleanup_bounded(tmp_path):
    import subprocess
    import sys

    from mnemion.private_output import private_process

    with pytest.raises(subprocess.TimeoutExpired):
        private_process(
            [sys.executable, "-c", "import time; time.sleep(10)"], directory=tmp_path, timeout=0.2
        )
    assert not list(tmp_path.glob(".process-*"))


def test_private_process_bounds_captured_output(tmp_path):
    import sys

    from mnemion.private_output import private_process

    with pytest.raises(OSError, match="capture limit"):
        private_process(
            [sys.executable, "-c", "import sys; sys.stdout.write('x'*(4*1024**2+1))"],
            directory=tmp_path,
            timeout=5,
        )
    assert not list(tmp_path.glob(".process-*"))
