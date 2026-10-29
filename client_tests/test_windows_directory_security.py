"""Directory checks must not invalidate an unrelated private-file read."""

import ctypes as c
from ctypes import wintypes as w
import os

import pytest

from mnemion import local_state as state, private_output

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows DACL and change time")


def change_time(path):
    # Python 3.13 exposes Windows creation time as st_ctime. Read the native
    # change time used by Electron/Node rather than accidentally testing birth.
    class BasicInfo(c.Structure):
        _fields_ = [
            ("created", c.c_int64),
            ("accessed", c.c_int64),
            ("written", c.c_int64),
            ("changed", c.c_int64),
            ("attributes", w.DWORD),
        ]

    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        w.LPCWSTR,
        w.DWORD,
        w.DWORD,
        c.c_void_p,
        w.DWORD,
        w.DWORD,
        w.HANDLE,
    ]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
    kernel.GetFileInformationByHandleEx.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    kernel.GetFileInformationByHandleEx.restype = w.BOOL
    handle = kernel.CreateFileW(str(path), 0x80, 7, None, 3, 0x00200000, None)
    assert handle not in {None, c.c_void_p(-1).value}
    try:
        value = BasicInfo()
        assert kernel.GetFileInformationByHandleEx(handle, 0, c.byref(value), c.sizeof(value))
        return value.changed
    finally:
        kernel.CloseHandle(handle)


def set_fixture_dacl(path, descriptor, *, protected=True):
    """Change only the synthetic fixture's DACL; retain its verified owner."""
    from client_tests.windows_acl import _api

    kernel, advapi = _api()
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        w.LPCWSTR,
        w.DWORD,
        c.POINTER(c.c_void_p),
        c.c_void_p,
    ]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = w.BOOL
    advapi.GetSecurityDescriptorDacl.argtypes = [
        c.c_void_p,
        c.POINTER(w.BOOL),
        c.POINTER(c.c_void_p),
        c.POINTER(w.BOOL),
    ]
    advapi.GetSecurityDescriptorDacl.restype = w.BOOL
    security, acl, present, defaulted = c.c_void_p(), c.c_void_p(), w.BOOL(), w.BOOL()
    try:
        assert advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            descriptor, 1, c.byref(security), None
        )
        assert advapi.GetSecurityDescriptorDacl(
            security, c.byref(present), c.byref(acl), c.byref(defaulted)
        )
        assert present.value
        flags = (0x80000000 if protected else 0x20000000) | 4
        assert advapi.SetNamedSecurityInfoW(str(path), 1, flags, None, None, acl, None) == 0
    finally:
        if security.value:
            kernel.LocalFree(security)


def test_repeated_private_directory_checks_preserve_child_metadata_and_permissions(tmp_path):
    from client_tests.windows_acl import (
        assert_private_acl,
        assert_restricted_access,
        security_descriptor,
    )

    root = state.directory(tmp_path / "Private workspace Équipe")
    inherited = root / "backup-policy.json"
    inherited.write_text('{"synthetic":true}\n', encoding="utf8")
    explicit = root / "last-ledger.json"
    state.write(explicit, {"synthetic": True})
    before = [
        (path.read_bytes(), change_time(path), security_descriptor(path))
        for path in (inherited, explicit)
    ]
    for _ in range(3):
        state.directory(root)
        assert_private_acl(root, directory=True)
    assert [
        (path.read_bytes(), change_time(path), security_descriptor(path))
        for path in (inherited, explicit)
    ] == before
    assert_private_acl(inherited, inherited=True)
    assert_private_acl(explicit)
    assert_restricted_access(root, inherited, explicit)


@pytest.mark.parametrize(
    "changed", ["additional_reader", "missing_inheritance", "unprotected", "null_dacl"]
)
def test_changed_directory_security_is_inspected_and_restored_before_return(tmp_path, changed):
    from client_tests.windows_acl import assert_private_acl, current_token_user_sid

    root = state.directory(tmp_path / changed)
    child = root / "synthetic.json"
    child.write_text('{"retained":true}\n', encoding="utf8")
    user = current_token_user_sid()
    descriptors = {
        "additional_reader": f"D:P(A;OICI;FA;;;{user})(A;OICI;GR;;;WD)",
        "missing_inheritance": f"D:P(A;;FA;;;{user})",
        "unprotected": f"D:(A;OICI;FA;;;{user})",
        "null_dacl": "D:NO_ACCESS_CONTROL",
    }
    set_fixture_dacl(root, descriptors[changed], protected=changed != "unprotected")
    state.directory(root)
    assert_private_acl(root, directory=True)
    assert_private_acl(child, inherited=True)
    assert child.read_text(encoding="utf8") == '{"retained":true}\n'
    stable = change_time(child)
    state.directory(root)
    assert change_time(child) == stable


def test_failed_dacl_inspection_never_counts_as_a_private_directory(tmp_path, monkeypatch):
    from client_tests.windows_acl import security_descriptor

    root = state.directory(tmp_path / "Cannot inspect")
    child = root / "synthetic.txt"
    child.write_text("retained")
    before = security_descriptor(root), change_time(child)

    def unavailable(*args):
        raise OSError("Synthetic Windows security inspection failure")

    monkeypatch.setattr(private_output, "_windows_same_private_dacl", unavailable)
    with pytest.raises(OSError, match="inspection failure"):
        state.directory(root)
    assert (security_descriptor(root), change_time(child)) == before
    assert child.read_text() == "retained"
