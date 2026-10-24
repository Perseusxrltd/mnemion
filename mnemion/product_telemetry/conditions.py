"""Current local admission gauges; nothing here is an outbound measurement."""

from __future__ import annotations

import time


class ServiceConditions:
    def __init__(self, *, can_start=None, metering=None):
        self.can_start = can_start
        self.metering = metering
        self._previous = None
        self._sampled_at = float("-inf")
        self._constrained = True

    def read(self) -> dict:
        try:
            import psutil
            from mnemion.service.memory_budget import sample_memory

            now = time.monotonic()
            if now - self._sampled_at >= 0.25:
                cpu = psutil.cpu_times()._asdict()
                total = sum(
                    value for name, value in cpu.items() if name not in {"guest", "guest_nice"}
                )
                idle = cpu["idle"]
                prior = self._previous
                memory = sample_memory()
                online = any(
                    info.isup
                    for name, info in psutil.net_if_stats().items()
                    if name.lower() not in {"lo", "lo0", "loopback pseudo-interface 1"}
                )
                self._constrained = (
                    not prior
                    or now - prior[0] > 120
                    or total <= prior[1]
                    or idle < prior[2]
                    or (idle - prior[2]) / (total - prior[1]) < 0.2
                    or not memory.complete
                    or memory.available < 128 * 1024 * 1024
                    or not online
                    or (self.can_start is not None and self.can_start() is not True)
                )
                self._previous = (now, total, idle)
                self._sampled_at = now
            # Absence of an OS metering capability stays explicitly unknown.
            return {
                "network": self.metering() if self.metering else "unknown",
                "constrained": bool(self._constrained),
            }
        except Exception:
            return {"network": "unknown", "constrained": True}
