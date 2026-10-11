"""Private, crash-durable state for the app's local operator, never an HTTP API."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
from uuid import uuid4

from .private_output import private_output

MAX_RECORD_BYTES = 256 * 1024


class LocalSetupError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _regular(path: Path, *, directory: bool = False) -> os.stat_result:
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or (not directory and info.st_nlink != 1)
    ):
        raise LocalSetupError("unsafe_location", "Use an ordinary local folder without links.")
    if os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise LocalSetupError(
            "private_location", "This workspace must be private to your OS account."
        )
    return info


def _windows_directory(path: Path) -> None:
    import ctypes as c
    from ctypes import wintypes as w

    from .private_output import _windows_owner_only_handle

    class FileAttributeTagInfo(c.Structure):
        _fields_ = [("attributes", w.DWORD), ("reparse_tag", w.DWORD)]

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
    kernel.GetFileInformationByHandleEx.argtypes = [
        w.HANDLE,
        c.c_int,
        c.c_void_p,
        w.DWORD,
    ]
    kernel.GetFileInformationByHandleEx.restype = w.BOOL
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.LocalFree.argtypes, kernel.LocalFree.restype = [c.c_void_p], c.c_void_p
    advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
    advapi.GetTokenInformation.argtypes = [
        w.HANDLE,
        w.DWORD,
        c.c_void_p,
        w.DWORD,
        c.POINTER(w.DWORD),
    ]
    advapi.GetSecurityInfo.argtypes = [
        w.HANDLE,
        w.DWORD,
        w.DWORD,
        c.POINTER(c.c_void_p),
        c.c_void_p,
        c.c_void_p,
        c.c_void_p,
        c.POINTER(c.c_void_p),
    ]
    advapi.GetSecurityInfo.restype = w.DWORD
    advapi.EqualSid.argtypes, advapi.EqualSid.restype = [c.c_void_p, c.c_void_p], w.BOOL
    # Refuse a leaf rename while validating and protecting the opened object.
    handle = kernel.CreateFileW(str(path), 0x60000, 3, None, 3, 0x02200000, None)
    if handle in {None, c.c_void_p(-1).value}:
        raise LocalSetupError("private_location", "Windows cannot protect this workspace folder.")
    token, security, owner = w.HANDLE(), c.c_void_p(), c.c_void_p()
    try:
        attributes = FileAttributeTagInfo()
        if not kernel.GetFileInformationByHandleEx(
            handle, 9, c.byref(attributes), c.sizeof(attributes)
        ):
            raise OSError("Cannot check the workspace folder")
        if attributes.attributes & 0x400 or not attributes.attributes & 0x10:
            raise LocalSetupError("unsafe_location", "Use an ordinary local folder without links.")
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, c.byref(token)):
            raise OSError("Cannot check the folder owner")
        needed = w.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, c.byref(needed))
        if not 1 <= needed.value <= 65536:
            raise OSError("Cannot check the folder owner")
        user = c.create_string_buffer(needed.value)
        if not advapi.GetTokenInformation(token, 1, user, needed, c.byref(needed)):
            raise OSError("Cannot check the folder owner")
        if advapi.GetSecurityInfo(
            handle, 1, 1, c.byref(owner), None, None, None, c.byref(security)
        ):
            raise OSError("Cannot check the folder owner")
        if not advapi.EqualSid(owner, c.cast(user, c.POINTER(c.c_void_p))[0]):
            raise LocalSetupError("private_location", "Choose a folder owned by your OS account.")
        _windows_owner_only_handle(handle, inherit=True)
    finally:
        if security.value:
            kernel.LocalFree(security)
        if token.value:
            kernel.CloseHandle(token)
        kernel.CloseHandle(handle)


def directory(path: Path) -> Path:
    """Create one app-owned level; its parent must already exist."""
    path = Path(path).absolute()
    # Refuse symlink/junction parents, including cloud redirection of app data.
    for parent in (path, *path.parents):
        if parent.exists() and (
            parent.is_symlink() or getattr(parent.lstat(), "st_file_attributes", 0) & 0x400
        ):
            raise LocalSetupError(
                "unsafe_location", "Choose a local folder without redirected parents."
            )
    if os.name == "nt":
        from .private_output import _windows_create_directory

        _windows_create_directory(path)
    else:
        path.mkdir(mode=0o700, exist_ok=True)
    _regular(path, directory=True)
    if os.name == "nt":
        _windows_directory(path)
    return path


def read(path: Path) -> dict:
    try:
        before = _regular(path)
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (info.st_dev, info.st_ino) != (
                before.st_dev,
                before.st_ino,
            ) or info.st_size > MAX_RECORD_BYTES:
                raise ValueError("Changed or oversized record")
            content = stream.read(MAX_RECORD_BYTES + 1)
        if len(content) > MAX_RECORD_BYTES:
            raise ValueError("Oversized record")
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError("Invalid record")
        return value
    except FileNotFoundError:
        raise
    except (OSError, ValueError, RecursionError):
        raise LocalSetupError(
            "damaged_state", "The saved setup could not be read. Your data has been retained."
        ) from None


def write(path: Path, value: dict, *, replace: bool = True) -> None:
    directory(path.parent)
    if path.exists() or path.is_symlink():
        read(path)
        if not replace:
            raise FileExistsError("The setup record already exists")
    content = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False).encode() + b"\n"
    if len(content) > MAX_RECORD_BYTES:
        raise LocalSetupError("state_limit", "The setup record exceeds its storage limit.")
    temporary = path.parent / (".local-state-" + uuid4().hex)
    try:
        with private_output(temporary) as stream:
            stream.write(content)
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
            temporary.unlink()
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def lock(root: Path):
    directory(root)
    path = root / "operator.lock"
    try:
        with private_output(path) as stream:
            stream.write(b"0")
    except FileExistsError:
        pass
    before = _regular(path)
    descriptor = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "r+b") as stream:
        info = os.fstat(stream.fileno())
        if (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino):
            raise LocalSetupError("unsafe_location", "The workspace lock changed during setup.")
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            raise LocalSetupError(
                "workspace_busy",
                "This workspace is already running in another app or operator session.",
            ) from None
        yield
