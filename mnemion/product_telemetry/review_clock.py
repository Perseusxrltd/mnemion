"""Local inspection lifetime fences; no measurements, transport or policy changes.

Native elapsed time includes suspend. Epochs are local control state, never
outbound identifiers. Windows initialization is an explicit inspection action;
ordinary reads cannot initialize or repair its ephemeral registry marker.
"""

from __future__ import annotations

from pathlib import Path
import re

REVIEW_LIFETIME_MS = 15 * 60 * 1000
MAX_WALL_MS = 86400000000000
MAX_EXACT = 2**53 - 1
_native = None


def _integer(value, maximum=MAX_EXACT):
    return type(value) is int and 0 <= value <= maximum


def review_clock(value):
    if (
        type(value) is not dict
        or set(value) != {"epoch", "elapsed_ms"}
        or type(value["epoch"]) is not str
        or re.fullmatch(r"[0-9a-f]{32}", value["epoch"]) is None
        or value["epoch"] == "0" * 32
        or not _integer(value["elapsed_ms"])
    ):
        raise ValueError("telemetry_review_clock_unavailable")
    return dict(value)


def read_review_clock(*, initialize=False):
    global _native
    if type(initialize) is not bool:
        return None
    try:
        import ctypes

        if _native is None:
            path = Path(__file__).with_name("network-state.node")
            try:
                path.lstat()
            except FileNotFoundError:
                # Source/pip/container installs have no bundled addon. Read the
                # same documented OS clock directly, without a compiler. An
                # existing but invalid helper never triggers this fallback.
                from .review_clock_system import read_system_review_clock

                _native = read_system_review_clock
        if callable(_native):
            return _native(initialize=initialize)
        if _native is None:

            class NativeClock(ctypes.Structure):
                _fields_ = [("elapsed_ms", ctypes.c_uint64), ("epoch", ctypes.c_ubyte * 16)]

            library = ctypes.CDLL(str(path))
            function = library.mnemion_review_clock_v1
            function.argtypes = [ctypes.c_int, ctypes.POINTER(NativeClock)]
            function.restype = ctypes.c_int
            _native = (library, function, NativeClock)
        if not _native:
            return None
        measured = _native[2]()
        if _native[1](int(initialize), ctypes.byref(measured)) != 1:
            return None
        return review_clock(
            {"epoch": bytes(measured.epoch).hex(), "elapsed_ms": measured.elapsed_ms}
        )
    except (OSError, AttributeError):
        _native = False
        return None
    except (ValueError, TypeError):
        return None


def review_lifetime(value):
    if (
        type(value) is not dict
        or set(value) != {"created_ms", "expires_ms", "checked_ms", "clock", "checked_elapsed_ms"}
        or not all(
            _integer(value[key], MAX_WALL_MS) for key in ("created_ms", "expires_ms", "checked_ms")
        )
        or not _integer(value["checked_elapsed_ms"])
        or not 0 < value["expires_ms"] - value["created_ms"] <= REVIEW_LIFETIME_MS
        or not value["created_ms"] <= value["checked_ms"] < value["expires_ms"]
    ):
        raise ValueError("telemetry_review_clock_unavailable")
    clock = review_clock(value["clock"])
    if (
        not 0
        <= value["checked_elapsed_ms"] - clock["elapsed_ms"]
        < value["expires_ms"] - value["created_ms"]
    ):
        raise ValueError("telemetry_review_clock_unavailable")
    return {**value, "clock": clock}


def start_review_lifetime(now, clock, observation_expiry):
    if not _integer(now, MAX_WALL_MS - REVIEW_LIFETIME_MS) or not _integer(
        observation_expiry, MAX_WALL_MS
    ):
        raise ValueError("telemetry_review_clock_unavailable")
    measured = review_clock(clock)
    return review_lifetime(
        {
            "created_ms": now,
            "expires_ms": min(now + REVIEW_LIFETIME_MS, observation_expiry),
            "checked_ms": now,
            "clock": measured,
            "checked_elapsed_ms": measured["elapsed_ms"],
        }
    )


def check_review_lifetime(value, now, clock):
    try:
        lifetime, measured = review_lifetime(value), review_clock(clock)
        if (
            not _integer(now, MAX_WALL_MS)
            or not lifetime["checked_ms"] <= now < lifetime["expires_ms"]
            or measured["epoch"] != lifetime["clock"]["epoch"]
            or measured["elapsed_ms"] < lifetime["checked_elapsed_ms"]
            or measured["elapsed_ms"] - lifetime["clock"]["elapsed_ms"]
            >= lifetime["expires_ms"] - lifetime["created_ms"]
        ):
            return None
        return {**lifetime, "checked_ms": now, "checked_elapsed_ms": measured["elapsed_ms"]}
    except (ValueError, TypeError, OverflowError):
        return None
