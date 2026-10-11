"""Native Windows ACL checks, including PostgreSQL's restricted-token access."""

from contextlib import contextmanager
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
from uuid import uuid4


class _SidAndAttributes(c.Structure):
    _fields_ = [("sid", c.c_void_p), ("attributes", w.DWORD)]


class _TokenGroups(c.Structure):
    _fields_ = [("count", w.DWORD), ("groups", _SidAndAttributes * 1)]


def _api():
    # Load libraries and resolve every entry point before impersonation: imports
    # may themselves read files outside the private workspace being tested.
    kernel = c.WinDLL("kernel32", use_last_error=True)
    advapi = c.WinDLL("advapi32", use_last_error=True)
    signatures = (
        (kernel.GetCurrentProcess, [], w.HANDLE),
        (kernel.CloseHandle, [w.HANDLE], w.BOOL),
        (kernel.LocalFree, [c.c_void_p], c.c_void_p),
        (
            kernel.CreateFileW,
            [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE],
            w.HANDLE,
        ),
        (
            kernel.ReadFile,
            [w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p],
            w.BOOL,
        ),
        (advapi.OpenProcessToken, [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)], w.BOOL),
        (
            advapi.GetTokenInformation,
            [w.HANDLE, w.DWORD, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)],
            w.BOOL,
        ),
        (advapi.ConvertSidToStringSidW, [c.c_void_p, c.POINTER(c.c_void_p)], w.BOOL),
        (advapi.ConvertStringSidToSidW, [w.LPCWSTR, c.POINTER(c.c_void_p)], w.BOOL),
        (
            advapi.GetNamedSecurityInfoW,
            [
                w.LPCWSTR,
                w.DWORD,
                w.DWORD,
                c.c_void_p,
                c.c_void_p,
                c.c_void_p,
                c.c_void_p,
                c.POINTER(c.c_void_p),
            ],
            w.DWORD,
        ),
        (
            advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW,
            [c.c_void_p, w.DWORD, w.DWORD, c.POINTER(c.c_void_p), c.POINTER(w.DWORD)],
            w.BOOL,
        ),
        (
            advapi.CreateRestrictedToken,
            [
                w.HANDLE,
                w.DWORD,
                w.DWORD,
                c.POINTER(_SidAndAttributes),
                w.DWORD,
                c.c_void_p,
                w.DWORD,
                c.POINTER(_SidAndAttributes),
                c.POINTER(w.HANDLE),
            ],
            w.BOOL,
        ),
        (advapi.ImpersonateLoggedOnUser, [w.HANDLE], w.BOOL),
        (advapi.RevertToSelf, [], w.BOOL),
    )
    for function, arguments, result in signatures:
        function.argtypes, function.restype = arguments, result
    return kernel, advapi


def _token_information(advapi, token, information_class):
    needed = w.DWORD()
    advapi.GetTokenInformation(token, information_class, None, 0, c.byref(needed))
    assert 1 <= needed.value <= 1024 * 1024, "Invalid Windows token information size"
    buffer = c.create_string_buffer(needed.value)
    if not advapi.GetTokenInformation(token, information_class, buffer, needed, c.byref(needed)):
        raise c.WinError(c.get_last_error())
    return buffer


def _sid_string(kernel, advapi, sid):
    rendered = c.c_void_p()
    if not advapi.ConvertSidToStringSidW(sid, c.byref(rendered)):
        raise c.WinError(c.get_last_error())
    try:
        return c.wstring_at(rendered)
    finally:
        kernel.LocalFree(rendered)


def _token_user_sid(kernel, advapi, token):
    user = _token_information(advapi, token, 1)  # TokenUser
    return _sid_string(kernel, advapi, c.cast(user, c.POINTER(c.c_void_p))[0])


def _token_groups(kernel, advapi, token):
    buffer = _token_information(advapi, token, 2)  # TokenGroups
    count = c.cast(buffer, c.POINTER(w.DWORD))[0]
    offset = _TokenGroups.groups.offset
    assert count <= (len(buffer) - offset) // c.sizeof(_SidAndAttributes)
    groups = (_SidAndAttributes * count).from_buffer(buffer, offset)
    return {_sid_string(kernel, advapi, group.sid): group.attributes for group in groups}


def current_token_user_sid() -> str:
    """Return the actual OS account SID, independently of TokenOwner."""
    kernel, advapi = _api()
    token = w.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, c.byref(token)):
        raise c.WinError(c.get_last_error())
    try:
        return _token_user_sid(kernel, advapi, token)
    finally:
        kernel.CloseHandle(token)


def security_descriptor(path: Path) -> str:
    """Return the file's owner and DACL as SDDL for independent assertions."""
    kernel, advapi = _api()
    security, rendered = c.c_void_p(), c.c_void_p()
    try:
        result = advapi.GetNamedSecurityInfoW(
            str(path), 1, 5, None, None, None, None, c.byref(security)
        )  # SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION
        if result:
            raise c.WinError(result)
        if not advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            security, 1, 5, c.byref(rendered), None
        ):
            raise c.WinError(c.get_last_error())
        return c.wstring_at(rendered)
    finally:
        if rendered.value:
            kernel.LocalFree(rendered)
        if security.value:
            kernel.LocalFree(security)


@contextmanager
def restricted_token():
    """Impersonate PostgreSQL's token without administrative group access.

    DISABLE_MAX_PRIVILEGE retains SeChangeNotifyPrivilege, which permits normal
    traversal through runner-owned temporary parents. No restricted SID list is
    added: PostgreSQL disables these groups without adding a second access check.
    """
    kernel, advapi = _api()
    original, restricted = w.HANDLE(), w.HANDLE()
    allocated_sids = []
    impersonating = False
    try:
        # TOKEN_DUPLICATE | TOKEN_QUERY; no elevation or privilege adjustment.
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0xA, c.byref(original)):
            raise c.WinError(c.get_last_error())
        original_groups = _token_groups(kernel, advapi, original)
        identities = ("S-1-5-32-544", "S-1-5-32-547")  # Administrators, Power Users
        disabled = (_SidAndAttributes * len(identities))()
        for index, identity in enumerate(identities):
            sid = c.c_void_p()
            if not advapi.ConvertStringSidToSidW(identity, c.byref(sid)):
                raise c.WinError(c.get_last_error())
            allocated_sids.append(sid)
            disabled[index] = _SidAndAttributes(sid, 0)
        if not advapi.CreateRestrictedToken(
            original, 1, len(disabled), disabled, 0, None, 0, None, c.byref(restricted)
        ):
            raise c.WinError(c.get_last_error())
        assert _token_user_sid(kernel, advapi, restricted) == _token_user_sid(
            kernel, advapi, original
        )
        groups = _token_groups(kernel, advapi, restricted)
        for identity in identities:
            if identity in original_groups:
                assert groups[identity] & 0x10, "Disabled group must be deny-only"
                assert not groups[identity] & 0x4, "Disabled group must not grant access"
        if not advapi.ImpersonateLoggedOnUser(restricted):
            raise c.WinError(c.get_last_error())
        impersonating = True
        yield restricted
    finally:
        try:
            if impersonating and not advapi.RevertToSelf():
                raise c.WinError(c.get_last_error())
        finally:
            for sid in allocated_sids:
                kernel.LocalFree(sid)
            if restricted.value:
                kernel.CloseHandle(restricted)
            if original.value:
                kernel.CloseHandle(original)


def _open(kernel, path, access, *, directory=False):
    handle = kernel.CreateFileW(
        str(path), access, 7, None, 3, 0x02000000 if directory else 0x80, None
    )  # OPEN_EXISTING; FILE_FLAG_BACKUP_SEMANTICS for directory handles
    if handle in {None, c.c_void_p(-1).value}:
        raise c.WinError(c.get_last_error())
    return handle


def _assert_read_execute(kernel, path, expected):
    # An actual open with GENERIC_EXECUTE checks the right required by binaries
    # and DLLs even though the fixture need not contain a valid executable.
    handle = _open(kernel, path, 0xA0000000)  # GENERIC_READ | GENERIC_EXECUTE
    try:
        buffer, count = c.create_string_buffer(len(expected) + 1), w.DWORD()
        if not kernel.ReadFile(handle, buffer, len(buffer), c.byref(count), None):
            raise c.WinError(c.get_last_error())
        assert buffer.raw[: count.value] == expected
    finally:
        kernel.CloseHandle(handle)


def assert_restricted_access(root: Path, inherited_file: Path, private_file: Path) -> None:
    """Prove inherited and explicit user ACLs survive PostgreSQL's restrictions."""
    kernel, _ = _api()
    root, inherited_file, private_file = map(Path, (root, inherited_file, private_file))
    expected = [(path, path.read_bytes()) for path in (inherited_file, private_file)]
    child = root / ("restricted-token-" + uuid4().hex)
    payload = b"created by the restricted PostgreSQL identity"
    try:
        with restricted_token():
            handle = _open(kernel, root, 0x21, directory=True)  # LIST_DIRECTORY | TRAVERSE
            try:
                assert list(root.iterdir()), "The workspace must contain the access fixtures"
            finally:
                kernel.CloseHandle(handle)
            for path, content in expected:
                _assert_read_execute(kernel, path, content)
            descriptor = os.open(child, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_BINARY, 0o600)
            try:
                assert os.write(descriptor, payload) == len(payload)
            finally:
                os.close(descriptor)
            _assert_read_execute(kernel, child, payload)
            child.unlink()
    finally:
        child.unlink(missing_ok=True)
