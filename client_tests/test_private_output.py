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


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission verification")
def test_a_filesystem_that_ignores_private_mode_fails_before_receiving_data(tmp_path, monkeypatch):
    original = os.fchmod
    monkeypatch.setattr(os, "fchmod", lambda descriptor, mode: original(descriptor, 0o644))
    path = tmp_path / "must-stay-private.json"
    with pytest.raises(OSError, match="cannot enforce"):
        with private_output(path):
            pytest.fail("Unprotected file became writable by the caller")
    assert not path.exists()
