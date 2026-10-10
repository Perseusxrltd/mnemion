"""Exclusive owner-only files for agent downloads and newly issued credentials."""

from contextlib import contextmanager
import os
from pathlib import Path
import stat

from .portable_paths import portable_part


def _windows_owner_only(descriptor: int) -> None:
    import ctypes as c
    from ctypes import wintypes as w
    import msvcrt

    advapi = c.WinDLL("advapi32", use_last_error=True)
    kernel = c.WinDLL("kernel32", use_last_error=True)
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        w.LPCWSTR,
        w.DWORD,
        c.POINTER(c.c_void_p),
        c.POINTER(w.DWORD),
    ]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = w.BOOL
    advapi.GetSecurityDescriptorDacl.argtypes = [
        c.c_void_p,
        c.POINTER(w.BOOL),
        c.POINTER(c.c_void_p),
        c.POINTER(w.BOOL),
    ]
    advapi.GetSecurityDescriptorDacl.restype = w.BOOL
    advapi.SetSecurityInfo.argtypes = [
        w.HANDLE,
        w.DWORD,
        w.DWORD,
        c.c_void_p,
        c.c_void_p,
        c.c_void_p,
        c.c_void_p,
    ]
    advapi.SetSecurityInfo.restype = w.DWORD
    kernel.LocalFree.argtypes, kernel.LocalFree.restype = [c.c_void_p], c.c_void_p
    kernel.ReOpenFile.argtypes = [w.HANDLE, w.DWORD, w.DWORD, w.DWORD]
    kernel.ReOpenFile.restype = w.HANDLE
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
    security = c.c_void_p()
    security_handle = None
    # A protected DACL grants full access only to the new file's owner. Apply it
    # through the open handle before any secret arrives, never through a shell.
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        "D:P(A;;FA;;;OW)", 1, c.byref(security), None
    ):
        raise OSError("Cannot create a private Windows file")
    try:
        present, defaulted, acl = w.BOOL(), w.BOOL(), c.c_void_p()
        if (
            not advapi.GetSecurityDescriptorDacl(
                security, c.byref(present), c.byref(acl), c.byref(defaulted)
            )
            or not present.value
            or not acl.value
        ):
            raise OSError("Cannot create a private Windows file")
        # CRT file handles do not include WRITE_DAC. Reopen the same kernel file
        # object with that access, preserving identity even if a parent moves.
        security_handle = kernel.ReOpenFile(msvcrt.get_osfhandle(descriptor), 0x60000, 7, 0)
        if security_handle in {None, c.c_void_p(-1).value}:
            raise OSError("Cannot protect the Windows output file")
        result = advapi.SetSecurityInfo(security_handle, 1, 0x80000004, None, None, acl, None)
        if result:
            raise OSError(result, "The filesystem cannot protect the output file")
    finally:
        if security_handle not in {None, c.c_void_p(-1).value}:
            kernel.CloseHandle(security_handle)
        kernel.LocalFree(security)


@contextmanager
def private_output(path: Path):
    """Reserve a new file before a remote mutation; never replace existing data."""
    path = Path(path).expanduser().absolute()
    if not portable_part(path.name):
        raise ValueError("Choose a regular portable output filename")
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    original = os.fstat(descriptor)
    try:
        if not stat.S_ISREG(original.st_mode):
            raise OSError("Choose a regular output file")
        if os.name == "nt":
            _windows_owner_only(descriptor)
        else:
            os.fchmod(descriptor, 0o600)
            if stat.S_IMODE(os.fstat(descriptor).st_mode) & 0o077:
                raise OSError("The filesystem cannot enforce private output permissions")
        with os.fdopen(descriptor, "wb") as output:
            descriptor = None
            yield output
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        try:
            current = path.lstat()
            if (original.st_dev, original.st_ino) == (current.st_dev, current.st_ino):
                path.unlink()
        except FileNotFoundError:
            pass
        raise
