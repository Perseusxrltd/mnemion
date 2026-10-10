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
def test_windows_output_has_a_protected_owner_only_dacl(tmp_path):
    import ctypes as c
    from ctypes import wintypes as w

    path = tmp_path / "private.json"
    with private_output(path) as output:
        output.write(b"owner can reopen this file")
    assert path.read_bytes() == b"owner can reopen this file"
    advapi, kernel = c.WinDLL("advapi32"), c.WinDLL("kernel32")
    advapi.GetNamedSecurityInfoW.argtypes = [
        w.LPCWSTR,
        w.DWORD,
        w.DWORD,
        c.c_void_p,
        c.c_void_p,
        c.c_void_p,
        c.c_void_p,
        c.POINTER(c.c_void_p),
    ]
    advapi.GetNamedSecurityInfoW.restype = w.DWORD
    advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        c.c_void_p,
        w.DWORD,
        w.DWORD,
        c.POINTER(c.c_void_p),
        c.c_void_p,
    ]
    advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = w.BOOL
    kernel.LocalFree.argtypes, kernel.LocalFree.restype = [c.c_void_p], c.c_void_p
    security, rendered = c.c_void_p(), c.c_void_p()
    try:
        assert (
            advapi.GetNamedSecurityInfoW(str(path), 1, 4, None, None, None, None, c.byref(security))
            == 0
        )
        assert advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            security, 1, 4, c.byref(rendered), None
        )
        dacl = c.wstring_at(rendered)
        assert dacl.startswith("D:P") and dacl.count("(") == 1 and "(A;;FA;;;OW)" in dacl
    finally:
        if rendered:
            kernel.LocalFree(rendered)
        if security:
            kernel.LocalFree(security)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission verification")
def test_a_filesystem_that_ignores_private_mode_fails_before_receiving_data(tmp_path, monkeypatch):
    original = os.fchmod
    monkeypatch.setattr(os, "fchmod", lambda descriptor, mode: original(descriptor, 0o644))
    path = tmp_path / "must-stay-private.json"
    with pytest.raises(OSError, match="cannot enforce"):
        with private_output(path):
            pytest.fail("Unprotected file became writable by the caller")
    assert not path.exists()
