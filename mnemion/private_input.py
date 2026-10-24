"""Bounded credential input, opened and checked before any network mutation."""

from __future__ import annotations

import os
from pathlib import Path
import stat

_MESSAGE = (
    "Use a bounded credential file owned by and readable only by your OS account, without links"
)


def _windows_open(path: Path, *, directory: bool = False, check_only: bool = False) -> int | None:
    """Inspect the opened file's actual owner and ACL without changing them."""
    import ctypes as c
    from ctypes import wintypes as w
    import msvcrt

    class Attributes(c.Structure):
        _fields_ = [("attributes", w.DWORD), ("tag", w.DWORD)]

    class ACL(c.Structure):
        _fields_ = [
            ("revision", w.BYTE),
            ("reserved", w.BYTE),
            ("size", w.WORD),
            ("count", w.WORD),
            ("reserved2", w.WORD),
        ]

    class ACE(c.Structure):
        _fields_ = [("kind", w.BYTE), ("flags", w.BYTE), ("size", w.WORD)]

    kernel = c.WinDLL("kernel32", use_last_error=True)
    advapi = c.WinDLL("advapi32", use_last_error=True)
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
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.LocalFree.argtypes, kernel.LocalFree.restype = [c.c_void_p], c.c_void_p
    kernel.GetFileInformationByHandleEx.argtypes = [
        w.HANDLE,
        c.c_int,
        c.c_void_p,
        w.DWORD,
    ]
    kernel.GetFileInformationByHandleEx.restype = w.BOOL
    advapi.GetSecurityInfo.argtypes = [
        w.HANDLE,
        w.DWORD,
        w.DWORD,
        c.POINTER(c.c_void_p),
        c.c_void_p,
        c.POINTER(c.c_void_p),
        c.c_void_p,
        c.POINTER(c.c_void_p),
    ]
    advapi.GetSecurityInfo.restype = w.DWORD
    advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
    advapi.OpenProcessToken.restype = w.BOOL
    advapi.GetTokenInformation.argtypes = [
        w.HANDLE,
        w.DWORD,
        c.c_void_p,
        w.DWORD,
        c.POINTER(w.DWORD),
    ]
    advapi.GetTokenInformation.restype = w.BOOL
    advapi.EqualSid.argtypes, advapi.EqualSid.restype = [c.c_void_p, c.c_void_p], w.BOOL
    advapi.GetAce.argtypes = [c.c_void_p, w.DWORD, c.POINTER(c.c_void_p)]
    advapi.GetAce.restype = w.BOOL
    advapi.IsValidSid.argtypes, advapi.IsValidSid.restype = [c.c_void_p], w.BOOL
    # Credential reads hold a read-only sharing handle. A metadata-only check
    # permits an existing SQLite writer and never reads, creates or changes data.
    handle = kernel.CreateFileW(
        str(path),
        0x20000 if check_only else 0x80020000,
        3 if check_only else 1,
        None,
        3,
        0x02200000 if directory else 0x00200000,
        None,
    )
    if handle in {None, c.c_void_p(-1).value}:
        raise OSError(_MESSAGE)
    token, security, owner, dacl = w.HANDLE(), c.c_void_p(), c.c_void_p(), c.c_void_p()
    try:
        attributes = Attributes()
        if not kernel.GetFileInformationByHandleEx(
            handle, 9, c.byref(attributes), c.sizeof(attributes)
        ) or (attributes.attributes & 0x400 or bool(attributes.attributes & 0x10) != directory):
            raise OSError(_MESSAGE)
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, c.byref(token)):
            raise OSError(_MESSAGE)
        needed = w.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, c.byref(needed))
        if not 1 <= needed.value <= 65536:
            raise OSError(_MESSAGE)
        user = c.create_string_buffer(needed.value)
        if not advapi.GetTokenInformation(token, 1, user, needed, c.byref(needed)):
            raise OSError(_MESSAGE)
        user_sid = c.cast(user, c.POINTER(c.c_void_p))[0]
        if (
            advapi.GetSecurityInfo(
                handle, 1, 5, c.byref(owner), None, c.byref(dacl), None, c.byref(security)
            )
            or not owner.value
            or not dacl.value
            or not advapi.EqualSid(owner, user_sid)
        ):
            raise OSError(_MESSAGE)
        acl = c.cast(dacl, c.POINTER(ACL)).contents
        if not 1 <= acl.count <= 1024:
            raise OSError(_MESSAGE)
        for index in range(acl.count):
            pointer = c.c_void_p()
            if not advapi.GetAce(dacl, index, c.byref(pointer)):
                raise OSError(_MESSAGE)
            ace = c.cast(pointer, c.POINTER(ACE)).contents
            if not directory and ace.flags & 0x08:
                # INHERIT_ONLY cannot grant access to this file; a directory
                # must also keep any newly created journal private.
                continue
            if ace.kind == 1:  # An ordinary deny ACE grants no access.
                continue
            # Reject other identities and unreviewed object/callback ACE types.
            if ace.kind != 0 or ace.size < 12:
                raise OSError(_MESSAGE)
            sid = c.c_void_p(pointer.value + 8)
            if not advapi.IsValidSid(sid) or not advapi.EqualSid(sid, user_sid):
                raise OSError(_MESSAGE)
        if check_only:
            return None
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        handle = None
        return descriptor
    finally:
        if security.value:
            kernel.LocalFree(security)
        if token.value:
            kernel.CloseHandle(token)
        if handle is not None:
            kernel.CloseHandle(handle)


def check_private_path(path: Path, *, directory: bool = False) -> None:
    """Non-mutating ownership check for an existing private directory or file."""
    info = path.lstat()
    if (
        not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or getattr(info, "st_file_attributes", 0) & 0x400
        or (not directory and info.st_nlink != 1)
        or (os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 0o077))
    ):
        raise OSError(_MESSAGE)
    if os.name == "nt":
        _windows_open(path, directory=directory, check_only=True)


def read_private(path: Path, *, maximum: int = 65536) -> bytes:
    """Read an existing owner-only regular file; never repair or expose it."""
    if type(maximum) is not int or not 1 <= maximum <= 2 * 1024 * 1024:
        raise ValueError("Use a supported credential input size")
    path = Path(path).expanduser().absolute()
    descriptor = (
        _windows_open(path)
        if os.name == "nt"
        else os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
    )
    if descriptor is None:
        raise OSError(_MESSAGE)
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_size > maximum
            or (os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 0o077))
        ):
            raise OSError(_MESSAGE)
        value = source.read(maximum + 1)
        if len(value) > maximum:
            raise OSError(_MESSAGE)
        return value
