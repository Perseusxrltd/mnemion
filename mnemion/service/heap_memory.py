"""Best-effort return of already freed model allocations to the operating system."""

import ctypes
from functools import lru_cache
import sys


@lru_cache(maxsize=1)
def _glibc_trim():
    if sys.platform != "linux":
        return None
    try:
        # Resolve only the running process's allocator. Do not load a guessed
        # library, call glibc-only functions on musl, or trim live working sets.
        allocator = ctypes.CDLL(None)
        getattr(allocator, "gnu_get_libc_version")
        trim = allocator.malloc_trim
        trim.argtypes = [ctypes.c_size_t]
        trim.restype = ctypes.c_int
        return trim
    except (AttributeError, OSError):
        return None


def release_unused_heap() -> bool | None:
    """Ask glibc to release free pages; None means this hint is unavailable."""
    trim = _glibc_trim()
    if trim is None:
        return None
    try:
        return bool(trim(0))
    except OSError:
        # Optional allocator support must never prevent ordinary model cleanup.
        return None
