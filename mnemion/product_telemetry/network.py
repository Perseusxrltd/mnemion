"""Fixed OS admission flags, sampled only within an already awake attempt."""

from __future__ import annotations

import asyncio
import math
from pathlib import Path
import time

_native = None


def native_state() -> int:
    """Use the release-owned C ABI, or the supported compiler-free OS reader."""
    global _native
    if _native is None:
        try:
            path = Path(__file__).with_name("network-state.node")
            try:
                path.lstat()
            except FileNotFoundError:
                # Only absence permits the direct system path. A present
                # broken helper is never bypassed by a different detector.
                from .network_system import read_system_network_state

                _native = read_system_network_state
            if _native is None:
                import ctypes

                library = ctypes.CDLL(str(path))
                function = library.mnemion_network_state_v1
                function.argtypes = []
                function.restype = ctypes.c_uint32
                _native = (library, function)
        except (OSError, AttributeError):
            _native = False
    return _native() if callable(_native) else _native[1]() if _native else 0


def network_flags(value) -> dict:
    if type(value) is not int or value not in (0, 8, 9, 10, 12, 13, 14):
        return {"network": "unknown", "constrained": True, "observed": False}
    return {
        "network": "metered" if value & 2 else "unmetered" if value & 1 else "unknown",
        "constrained": bool(value & 4),
        "observed": bool(value & 8),
    }


class NativeNetworkConditions:
    """One existing loop/executor owns the probe; no periodic or idle worker.

    Closing an attempt invalidates its result, not the OS call already running.
    A following attempt cannot queue another probe until that call has returned.
    """

    def __init__(self, *, probe=native_state, now=time.monotonic):
        self._probe = probe
        self._now = now
        self._active = False
        self._generation = 0
        self._sampled_at = float("-inf")
        self._attempted_at = float("-inf")
        self._value = network_flags(0)
        self._pending = None

    def _refresh(self):
        if self._pending is not None or not self._active:
            return self._pending
        generation = self._generation
        started = self._now()
        self._attempted_at = started

        def measure():
            # An occupied executor may not start this until after cancellation.
            return self._probe() if self._active and self._generation == generation else 0

        pending = asyncio.get_running_loop().run_in_executor(None, measure)
        self._pending = pending

        def completed(future):
            if self._pending is future:
                self._pending = None
            try:
                value = network_flags(future.result())
            except (Exception, asyncio.CancelledError):
                value = {**self._value, "constrained": True}
            if not self._active or self._generation != generation:
                return
            # Losing an OS capability cannot erase a known metered/limited path.
            if value["observed"] or (
                not self._value["constrained"] and self._value["network"] != "metered"
            ):
                self._value = value
            self._sampled_at = started

        pending.add_done_callback(completed)
        return pending

    async def start(self) -> bool:
        self._active = True
        self._generation += 1
        self._sampled_at = self._attempted_at = float("-inf")
        generation = self._generation
        try:
            async with asyncio.timeout(1):
                # Shielding preserves the pending call when the owner cancels.
                if self._pending is not None:
                    await asyncio.shield(self._pending)
                if self._active and self._generation == generation:
                    await asyncio.shield(self._refresh())
            return (
                self._active and self._generation == generation and math.isfinite(self._sampled_at)
            )
        except TimeoutError:
            self.close()
            return False
        except asyncio.CancelledError:
            self.close()
            raise
        except Exception:
            self.close()
            return False

    def read(self) -> dict:
        now = self._now()
        if not self._active or not math.isfinite(now):
            return {"network": "unknown", "constrained": True}
        if now - self._attempted_at >= 0.25:
            self._refresh()
        if now < self._sampled_at or now - self._sampled_at >= 1:
            return {
                "network": "metered" if self._value["network"] == "metered" else "unknown",
                "constrained": True,
            }
        return {key: self._value[key] for key in ("network", "constrained")}

    def close(self) -> None:
        self._active = False
        self._generation += 1
        self._sampled_at = float("-inf")
