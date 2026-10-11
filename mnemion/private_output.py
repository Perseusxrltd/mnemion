"""Exclusive owner-only files for agent downloads and newly issued credentials."""

from contextlib import contextmanager
import os
from pathlib import Path
import stat

from .portable_paths import portable_part


@contextmanager
def _windows_private_security(*, inherit: bool = False):
    """Name the creating OS identity, not its possibly elevated default owner."""
    import ctypes as c
    from ctypes import wintypes as w

    advapi = c.WinDLL("advapi32", use_last_error=True)
    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
    kernel.LocalFree.argtypes, kernel.LocalFree.restype = [c.c_void_p], c.c_void_p
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
    advapi.ConvertSidToStringSidW.argtypes = [c.c_void_p, c.POINTER(c.c_void_p)]
    advapi.ConvertSidToStringSidW.restype = w.BOOL
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        w.LPCWSTR,
        w.DWORD,
        c.POINTER(c.c_void_p),
        c.POINTER(w.DWORD),
    ]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = w.BOOL
    token, rendered, security = w.HANDLE(), c.c_void_p(), c.c_void_p()
    try:
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, c.byref(token)):
            raise OSError("Cannot identify the Windows account")
        needed = w.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, c.byref(needed))
        if not 1 <= needed.value <= 65536:
            raise OSError("Cannot identify the Windows account")
        user = c.create_string_buffer(needed.value)
        if not advapi.GetTokenInformation(token, 1, user, needed, c.byref(needed)):
            raise OSError("Cannot identify the Windows account")
        sid = c.cast(user, c.POINTER(c.c_void_p))[0]
        if not advapi.ConvertSidToStringSidW(sid, c.byref(rendered)):
            raise OSError("Cannot identify the Windows account")
        identity = c.wstring_at(rendered)
        flags = "OICI" if inherit else ""
        # Elevated Windows processes often create Administrators-owned files.
        # OW would then depend on a group PostgreSQL deliberately disables.
        descriptor = f"O:{identity}D:P(A;{flags};FA;;;{identity})"
        if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            descriptor, 1, c.byref(security), None
        ):
            raise OSError("Cannot create private Windows security")
        yield security
    finally:
        if security.value:
            kernel.LocalFree(security)
        if rendered.value:
            kernel.LocalFree(rendered)
        if token.value:
            kernel.CloseHandle(token)


def _windows_create_directory(path: Path) -> bool:
    """Atomically create one private level; never change an existing path."""
    import ctypes as c
    from ctypes import wintypes as w

    class SecurityAttributes(c.Structure):
        _fields_ = [("length", w.DWORD), ("descriptor", c.c_void_p), ("inherit", w.BOOL)]

    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.CreateDirectoryW.argtypes = [w.LPCWSTR, c.POINTER(SecurityAttributes)]
    kernel.CreateDirectoryW.restype = w.BOOL
    with _windows_private_security(inherit=True) as security:
        attributes = SecurityAttributes(c.sizeof(SecurityAttributes), security, False)
        if kernel.CreateDirectoryW(str(path), c.byref(attributes)):
            return True
        error = c.get_last_error()
        if error == 183:  # ERROR_ALREADY_EXISTS: the caller must validate it.
            return False
        raise OSError(error, "Windows cannot create this private workspace folder")


def _windows_owner_only_handle(handle: int, *, inherit: bool = False) -> None:
    import ctypes as c
    from ctypes import wintypes as w

    advapi = c.WinDLL("advapi32", use_last_error=True)
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
    with _windows_private_security(inherit=inherit) as security:
        present, defaulted, acl = w.BOOL(), w.BOOL(), c.c_void_p()
        if (
            not advapi.GetSecurityDescriptorDacl(
                security, c.byref(present), c.byref(acl), c.byref(defaulted)
            )
            or not present.value
            or not acl.value
        ):
            raise OSError("Cannot create a private Windows file")
        # Existing directories have already passed the current-user ownership
        # check. Only replace their DACL; never take ownership of another path.
        result = advapi.SetSecurityInfo(handle, 1, 0x80000004, None, None, acl, None)
        if result:
            raise OSError(result, "The filesystem cannot protect the output file")


def _windows_create_file(path: Path) -> int:
    """Create an exclusive file with private ownership before exposing a handle."""
    import ctypes as c
    from ctypes import wintypes as w
    import msvcrt

    class SecurityAttributes(c.Structure):
        _fields_ = [("length", w.DWORD), ("descriptor", c.c_void_p), ("inherit", w.BOOL)]

    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        w.LPCWSTR,
        w.DWORD,
        w.DWORD,
        c.POINTER(SecurityAttributes),
        w.DWORD,
        w.DWORD,
        w.HANDLE,
    ]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
    with _windows_private_security() as security:
        attributes = SecurityAttributes(c.sizeof(SecurityAttributes), security, False)
        # CREATE_NEW refuses existing files and links. FILE_FLAG_OPEN_REPARSE_POINT
        # also prevents following a redirected final component.
        handle = kernel.CreateFileW(
            str(path), 0x40000000, 7, c.byref(attributes), 1, 0x200080, None
        )
        error = c.get_last_error()
    if handle in {None, c.c_void_p(-1).value}:
        raise c.WinError(error)
    try:
        return msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise


@contextmanager
def private_output(path: Path):
    """Reserve a new file before a remote mutation; never replace existing data."""
    path = Path(path).expanduser().absolute()
    if not portable_part(path.name):
        raise ValueError("Choose a regular portable output filename")
    descriptor = (
        _windows_create_file(path)
        if os.name == "nt"
        else os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
    )
    original = os.fstat(descriptor)
    try:
        if not stat.S_ISREG(original.st_mode):
            raise OSError("Choose a regular output file")
        if os.name != "nt":
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


def private_process(command, *, directory: Path, input=None, env=None, timeout=60):
    """Capture a native launcher without waiting for its descendants' pipe EOF.

    The caller supplies an app-owned directory. Windows descendants may keep
    duplicate output handles after their launcher exits, so use private regular
    files with delete sharing instead of subprocess PIPE handles.
    """
    import subprocess
    from uuid import uuid4

    prefix = ".process-" + uuid4().hex
    stdout_path, stderr_path = (Path(directory) / (prefix + ending) for ending in (".out", ".err"))
    with private_output(stdout_path) as stdout, private_output(stderr_path) as stderr:
        result = subprocess.run(
            command,
            input=input,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=stdout,
            stderr=stderr,
            env=env,
            timeout=timeout,
        )

    def captured(path):
        with path.open("rb") as stream:
            content = stream.read(4 * 1024**2 + 1)
        if len(content) > 4 * 1024**2:
            raise OSError("Native process output exceeded its capture limit")
        return content.decode("utf-8", errors="replace")

    try:
        return subprocess.CompletedProcess(
            result.args, result.returncode, captured(stdout_path), captured(stderr_path)
        )
    finally:
        stdout_path.unlink(missing_ok=True)
        stderr_path.unlink(missing_ok=True)
