"""Compiler-free access to the same OS review clocks as the packaged helper.

Used only when that helper is absent, never to override its unavailable result.
These private clocks do not grant networking permission or produce measurements.
No process, worker, guessed boot timestamp or persistent clock file is needed.
"""

from __future__ import annotations

from functools import lru_cache
import os
import re
import sys
import time


def _epoch(value):
    if not re.fullmatch(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value):
        raise ValueError("telemetry_review_clock_unavailable")
    return value.replace(b"-", b"").decode("ascii").lower()


def _linux(initialize):
    descriptor = os.open(
        "/proc/sys/kernel/random/boot_id", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    )
    try:
        value = os.read(descriptor, 64)
    finally:
        os.close(descriptor)
    if len(value) != 37 or value[-1:] != b"\n":
        return None
    return {
        "epoch": _epoch(value[:36]),
        "elapsed_ms": time.clock_gettime_ns(time.CLOCK_BOOTTIME) // 1000000,
    }


def _macos_reader():
    import ctypes

    library = ctypes.CDLL("/usr/lib/libSystem.B.dylib")

    class Timebase(ctypes.Structure):
        _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]

    sysctl = library.sysctlbyname
    sysctl.argtypes = [
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    sysctl.restype = ctypes.c_int
    timebase = library.mach_timebase_info
    timebase.argtypes = [ctypes.POINTER(Timebase)]
    timebase.restype = ctypes.c_int
    continuous = library.mach_continuous_time
    continuous.argtypes = []
    continuous.restype = ctypes.c_uint64

    def read(initialize):
        epoch = ctypes.create_string_buffer(64)
        length, scale = ctypes.c_size_t(64), Timebase()
        if (
            sysctl(b"kern.bootsessionuuid", epoch, ctypes.byref(length), None, 0) != 0
            or length.value != 37
            or epoch.raw[36:37] != b"\0"
            or timebase(ctypes.byref(scale)) != 0
            or not scale.numer
            or not scale.denom
        ):
            return None
        return {
            "epoch": _epoch(epoch.raw[:36]),
            "elapsed_ms": continuous() * scale.numer // scale.denom // 1000000,
        }

    return read


def _windows_reader():
    import ctypes
    from ctypes import wintypes

    # LOAD_LIBRARY_SEARCH_SYSTEM32 avoids the current directory and PATH.
    registry = ctypes.WinDLL("advapi32.dll", winmode=0x800)
    kernel = ctypes.WinDLL("kernelbase.dll", winmode=0x800)
    random = ctypes.WinDLL("bcrypt.dll", winmode=0x800)
    handle_pointer = ctypes.POINTER(wintypes.HKEY)
    dword_pointer = ctypes.POINTER(wintypes.DWORD)
    open_key = registry.RegOpenKeyExW
    open_key.argtypes = [
        wintypes.HKEY,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        handle_pointer,
    ]
    open_key.restype = wintypes.LONG
    create_key = registry.RegCreateKeyExW
    create_key.argtypes = [
        wintypes.HKEY,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        handle_pointer,
        dword_pointer,
    ]
    create_key.restype = wintypes.LONG
    query = registry.RegQueryValueExW
    query.argtypes = [
        wintypes.HKEY,
        wintypes.LPCWSTR,
        dword_pointer,
        dword_pointer,
        ctypes.c_void_p,
        dword_pointer,
    ]
    query.restype = wintypes.LONG
    write = registry.RegSetValueExW
    write.argtypes = [
        wintypes.HKEY,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    write.restype = wintypes.LONG
    close = registry.RegCloseKey
    close.argtypes, close.restype = [wintypes.HKEY], wintypes.LONG
    rng = random.BCryptGenRandom
    rng.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
    rng.restype = wintypes.LONG
    interrupt = kernel.QueryInterruptTime
    interrupt.argtypes, interrupt.restype = [ctypes.POINTER(ctypes.c_uint64)], None
    current_user = wintypes.HKEY(ctypes.c_ssize_t(-2147483647).value)
    path = "Software\\PerseusXR\\Mnemion\\ReviewClockV1"

    def read(initialize):
        key, disposition = wintypes.HKEY(), wintypes.DWORD()
        # Explicit actions alone create the REG_OPTION_VOLATILE key or Epoch.
        opened = (
            create_key(
                current_user,
                path,
                0,
                None,
                1,
                0x103,
                None,
                ctypes.byref(key),
                ctypes.byref(disposition),
            )
            if initialize
            else open_key(current_user, path, 0, 0x101, ctypes.byref(key))
        )
        if opened != 0:
            return None
        epoch, kind, length = (ctypes.c_ubyte * 16)(), wintypes.DWORD(), wintypes.DWORD(16)
        try:
            found = query(key, "Epoch", None, ctypes.byref(kind), epoch, ctypes.byref(length))
            ready = found == 0 and kind.value == 3 and length.value == 16
            if (
                initialize and found == 2
            ):  # ERROR_FILE_NOT_FOUND only; never repair a malformed value.
                ready = rng(None, epoch, 16, 2) >= 0 and write(key, "Epoch", 0, 3, epoch, 16) == 0
            if not ready or not any(epoch):
                return None
        finally:
            close(key)
        elapsed = ctypes.c_uint64()
        interrupt(ctypes.byref(elapsed))
        return {"epoch": bytes(epoch).hex(), "elapsed_ms": elapsed.value // 10000}

    return read


@lru_cache(maxsize=1)
def _reader():
    if sys.platform == "linux":
        return _linux
    if sys.platform == "darwin":
        return _macos_reader()
    if sys.platform == "win32":
        return _windows_reader()
    return None


def read_system_review_clock(*, initialize=False):
    if type(initialize) is not bool:
        return None
    try:
        from .review_clock import review_clock

        read = _reader()
        return review_clock(read(initialize)) if read else None
    except (OSError, AttributeError, ValueError, TypeError, OverflowError):
        return None
