"""Read a selected file through a verified handle, not a check-then-follow path."""

from __future__ import annotations

import os
import stat
from pathlib import Path, PurePosixPath


class SourceReadError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _windows_handle_path(descriptor: int) -> Path:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    function = ctypes.WinDLL("kernel32", use_last_error=True).GetFinalPathNameByHandleW
    function.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    function.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(32768)
    length = function(msvcrt.get_osfhandle(descriptor), buffer, len(buffer), 0)
    if not length or length >= len(buffer):
        raise SourceReadError("source_handle_unverifiable")
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return Path(value)


def read_selected(root: Path, relative: str, maximum: int) -> bytes:
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
            descriptor = os.open(root.joinpath(*parts), os.O_RDONLY | os.O_BINARY)
            # Windows has no openat/O_NOFOLLOW equivalent in Python. Verify the
            # actual opened handle before reading any bytes, including junctions.
            if not _windows_handle_path(descriptor).is_relative_to(root):
                raise SourceReadError("source_outside_selected_root")
        else:
            raise SourceReadError("source_handle_verification_unavailable")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise SourceReadError("source_is_not_regular_file")
            if before.st_size > maximum:
                raise SourceReadError("source_too_large")
            data = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
            if len(data) > maximum:
                raise SourceReadError("source_too_large")
            if (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size) != (
                after.st_dev,
                after.st_ino,
                after.st_mtime_ns,
                after.st_size,
            ):
                raise SourceReadError("source_changed_during_read")
            return data
    except OSError:
        raise SourceReadError("source_unreadable_or_symlink_changed") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
