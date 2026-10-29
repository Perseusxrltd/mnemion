"""Read a selected file through a verified handle, not a check-then-follow path."""

from __future__ import annotations

from contextlib import contextmanager
import errno
import hashlib
import os
import stat
from pathlib import Path, PurePosixPath

from ..source_codes import ACCESS_WITHHOLD_CODES


# Python maps EACCES/EPERM to PermissionError and ENOENT to FileNotFoundError.
# ELOOP and ESTALE stay plain OSError, so the link/handle category checks errno.
# Diagnostics keep the fixed code only. OS text and host paths never leave here.
_PERMISSION_ERRNOS = {errno.EACCES, errno.EPERM}
_LINK_ERRNOS = {
    number
    for name in ("ELOOP", "ESTALE", "ENOTDIR", "EISDIR", "EMLINK")
    if (number := getattr(errno, name, None)) is not None
}

# These stop the inventory. The service then withholds every item this run
# did not re-read. Ordinary text and size skips are a different contract.
INVENTORY_STOP_CODES = ACCESS_WITHHOLD_CODES


class SourceReadError(ValueError):
    def __init__(self, code, relative=None):
        super().__init__(code)
        self.code = code
        self.relative = relative


def classify_source_os_error(error: OSError) -> str:
    """Map an OS failure to a fixed category. Ignore strerror, filename, and winerror."""
    number = getattr(error, "errno", None)
    if isinstance(error, PermissionError) or number in _PERMISSION_ERRNOS:
        return "source_permission_denied"
    if isinstance(error, FileNotFoundError) or number == errno.ENOENT:
        return "source_disappeared"
    if isinstance(error, (NotADirectoryError, IsADirectoryError)) or number in _LINK_ERRNOS:
        return "source_link_or_handle_changed"
    return "source_io_failed"


def relative_evidence(relative: str | None) -> dict:
    """A source-relative path and its hash, or nothing when the path is not safe to publish."""
    if not isinstance(relative, str):
        return {}
    path = PurePosixPath(relative)
    if (
        not relative
        or len(relative) > 512
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in relative
        or any(ord(character) < 32 for character in relative)
    ):
        return {}
    return {
        "path": relative,
        "path_sha256": hashlib.sha256(relative.encode()).hexdigest(),
    }


def _fail(code: str, relative: str) -> None:
    raise SourceReadError(code, relative=relative)


def _windows_open_unfollowed(path: Path, relative: str) -> int:
    """Open the final component itself. A symlink or junction is not followed."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    info_type = type(
        "FILE_ATTRIBUTE_TAG_INFO",
        (ctypes.Structure,),
        {"_fields_": [("FileAttributes", wintypes.DWORD), ("ReparseTag", wintypes.DWORD)]},
    )
    kernel.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    handle = create(
        str(path),
        0x80000000,
        0x1 | 0x2 | 0x4,
        None,
        3,
        0x00200000,
        None,
    )
    opened = ctypes.cast(handle, ctypes.c_void_p).value
    invalid = ctypes.c_void_p(-1).value
    if not opened or opened == invalid:
        # winerror selects the OSError subclass. Do not attach the host path.
        raise OSError(0, None, None, ctypes.get_last_error())
    info = info_type()
    if not kernel.GetFileInformationByHandleEx(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
        kernel.CloseHandle(handle)
        _fail("source_handle_unverifiable", relative)
    if info.FileAttributes & 0x400:
        kernel.CloseHandle(handle)
        _fail("source_link_or_handle_changed", relative)
    try:
        # A failed conversion leaves the HANDLE with the caller. Close it.
        return msvcrt.open_osfhandle(int(opened), os.O_RDONLY | os.O_BINARY)
    except OSError:
        kernel.CloseHandle(handle)
        raise


def _windows_handle_path(descriptor: int, relative: str) -> Path:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    function = ctypes.WinDLL("kernel32", use_last_error=True).GetFinalPathNameByHandleW
    function.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    function.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(32768)
    length = function(msvcrt.get_osfhandle(descriptor), buffer, len(buffer), 0)
    if not length or length >= len(buffer):
        _fail("source_handle_unverifiable", relative)
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return Path(value)


@contextmanager
def open_selected(root: Path, relative: str):
    """Open a regular selected source without following a redirected component."""
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or ".." in parts or "\\" in relative:
        raise SourceReadError("invalid_source_path")
    descriptor = None
    try:
        if os.name != "nt" and os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"):
            # Directory descriptors keep every path component anchored even if
            # another process replaces a directory with a symlink during a scan.
            directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                for part in parts[:-1]:
                    child = os.open(
                        part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                    )
                    os.close(directory)
                    directory = child
                descriptor = os.open(
                    parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
                )
            finally:
                os.close(directory)
        elif os.name == "nt":
            # FILE_FLAG_OPEN_REPARSE_POINT keeps the final symlink or junction
            # from being followed. The handle is still checked against the root
            # so a parent junction cannot escape after that refusal.
            descriptor = _windows_open_unfollowed(root.joinpath(*parts), relative)
            if not _windows_handle_path(descriptor, relative).is_relative_to(root):
                _fail("source_outside_selected_root", relative)
        else:
            _fail("source_handle_verification_unavailable", relative)
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                _fail("source_is_not_regular_file", relative)
            yield stream
    except OSError as error:
        raise SourceReadError(classify_source_os_error(error), relative=relative) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def read_selected(root: Path, relative: str, maximum: int) -> bytes:
    with open_selected(root, relative) as stream:
        try:
            before = os.fstat(stream.fileno())
            if before.st_size > maximum:
                _fail("source_too_large", relative)
            data = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
            if len(data) > maximum:
                _fail("source_too_large", relative)
            if (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size) != (
                after.st_dev,
                after.st_ino,
                after.st_mtime_ns,
                after.st_size,
            ):
                _fail("source_changed_during_read", relative)
            return data
        except OSError as error:
            raise SourceReadError(classify_source_os_error(error), relative=relative) from None
