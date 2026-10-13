"""Credential files must be private before an agent can send their contents."""

import os
import subprocess

import pytest

from mnemion.private_input import read_private
from mnemion.private_output import private_output


def test_private_credentials_round_trip_without_changing_permissions(tmp_path):
    path = tmp_path / "Équipe credentials.json"
    with private_output(path) as stream:
        stream.write(b'{"password":"synthetic private fixture"}')
    before = path.stat()
    assert read_private(path) == b'{"password":"synthetic private fixture"}'
    after = path.stat()
    assert (before.st_mode, before.st_ino, before.st_size) == (
        after.st_mode,
        after.st_ino,
        after.st_size,
    )


def test_linked_and_oversized_private_credentials_are_refused(tmp_path):
    path = tmp_path / "credentials.json"
    with private_output(path) as stream:
        stream.write(b"x" * 100)
    with pytest.raises(OSError):
        read_private(path, maximum=99)
    alias = tmp_path / "alias.json"
    os.link(path, alias)
    with pytest.raises(OSError):
        read_private(path)
    assert path.read_bytes() == b"x" * 100
    with pytest.raises((OSError, PermissionError)):
        read_private(tmp_path)


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes and links")
def test_shared_linked_and_fifo_credentials_are_not_opened_as_private_data(tmp_path):
    path = tmp_path / "shared.json"
    path.write_bytes(b"private fixture")
    path.chmod(0o644)
    with pytest.raises(OSError):
        read_private(path)
    assert path.stat().st_mode & 0o077 == 0o044
    path.chmod(0o600)
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(OSError):
        read_private(link)
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo, 0o600)
    with pytest.raises(OSError):
        read_private(fifo)


@pytest.mark.skipif(os.name != "nt", reason="Native Windows ACL boundaries")
def test_windows_shared_credential_acl_is_rejected_without_repair(tmp_path):
    from client_tests.windows_acl import security_descriptor

    path = tmp_path / "shared.json"
    with private_output(path) as stream:
        stream.write(b"synthetic private fixture")
    subprocess.run(
        ["icacls", str(path), "/grant", "*S-1-5-32-545:R"],
        check=True,
        capture_output=True,
        timeout=10,
    )
    before = security_descriptor(path)
    with pytest.raises(OSError):
        read_private(path)
    assert security_descriptor(path) == before


@pytest.mark.skipif(os.name != "nt", reason="Native Windows owner boundaries")
def test_windows_foreign_owned_credential_is_rejected_without_taking_ownership(tmp_path):
    from client_tests.windows_acl import make_administrators_owned, security_descriptor

    path = tmp_path / "foreign-owner.json"
    with private_output(path) as stream:
        stream.write(b"synthetic private fixture")
    if not make_administrators_owned(path):
        pytest.skip("Requires an elevated Windows fixture")
    before = security_descriptor(path)
    with pytest.raises(OSError):
        read_private(path)
    assert security_descriptor(path) == before
