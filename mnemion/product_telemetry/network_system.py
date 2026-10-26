"""Compiler-free Windows cost hints, with the same fixed flags as the C helper.

Only Windows' local, documented connectivity hint is read. No COM, interface
enumeration, network request, persistent task or identifier enters this module.
Other source-install platforms retain unknown cost until they have a packaged
helper or an explicit connection choice. This is admission, not a measurement.
"""

from __future__ import annotations

import sys

_reader = None


def _windows_reader():
    import ctypes

    class ConnectivityHint(ctypes.Structure):
        # Windows SDK nldef.h: two 32-bit enums, then three BOOLEAN bytes.
        _fields_ = [
            ("level", ctypes.c_uint32),
            ("cost", ctypes.c_uint32),
            ("approaching", ctypes.c_ubyte),
            ("over", ctypes.c_ubyte),
            ("roaming", ctypes.c_ubyte),
        ]

    # Never search the working directory or PATH for a system library. Older
    # Windows versions without this API stay unknown, without a COM fallback.
    library = ctypes.WinDLL("iphlpapi.dll", winmode=0x800)
    function = library.GetNetworkConnectivityHint
    function.argtypes = [ctypes.POINTER(ConnectivityHint)]
    function.restype = ctypes.c_uint32

    def read():
        hint = ConnectivityHint()
        result = function(ctypes.byref(hint))
        if result == 1222:  # ERROR_NO_NETWORK: an observed offline veto.
            return 12
        if result != 0:
            return 0
        value = 8
        if hint.cost in (2, 3) or hint.approaching or hint.over or hint.roaming:
            value |= 2
        elif hint.cost == 1:
            value |= 1
        if hint.cost > 3 or hint.level != 3:
            value |= 4
        return value

    # Retain the library for the cached callable's entire lifetime.
    return library, read


def read_system_network_state() -> int:
    global _reader
    if sys.platform != "win32":
        return 0
    try:
        if _reader is None:
            _reader = _windows_reader()
        return _reader[1]() if _reader else 0
    except (OSError, AttributeError):
        _reader = False
        return 0
