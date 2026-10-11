"""Portable process gauges and effective Linux cgroup limits; no model launch."""

from __future__ import annotations

import os
import platform
from pathlib import Path
import time


def cgroup_limits() -> dict:
    """Walk this cgroup's ancestors; a child may inherit its effective cap."""
    result = {
        "memory_limit_bytes": None,
        "cpu_limit_cores": None,
        "memory_current_bytes": None,
        "memory_available_bytes": None,
        "swap_limit_bytes": None,
    }
    if platform.system() != "Linux":
        return result
    try:
        line = next(
            row
            for row in Path("/proc/self/cgroup").read_text().splitlines()
            if row.startswith("0::")
        )
        root = Path("/sys/fs/cgroup")
        path = root / line.removeprefix("0::").lstrip("/")
        if ".." in path.parts or not path.is_dir():
            return result
        try:
            result["memory_current_bytes"] = int((path / "memory.current").read_text())
        except (OSError, ValueError):
            pass
        for node in [path, *(p for p in path.parents if p == root or root in p.parents)]:
            # A parent limit is shared with siblings. The child's usage alone
            # cannot tell us how much of that parent budget remains available.
            try:
                available = max(
                    0,
                    int((node / "memory.max").read_text())
                    - int((node / "memory.current").read_text()),
                )
                prior = result["memory_available_bytes"]
                result["memory_available_bytes"] = (
                    min(prior, available) if prior is not None else available
                )
            except (OSError, ValueError):
                pass
            for field, filename in (
                ("memory_limit_bytes", "memory.max"),
                ("swap_limit_bytes", "memory.swap.max"),
            ):
                try:
                    value = int((node / filename).read_text())
                    result[field] = (
                        min(value, result[field]) if result[field] is not None else value
                    )
                except (OSError, ValueError):
                    pass
            try:
                quota, period = (node / "cpu.max").read_text().split()
                value = int(quota) / int(period)
                result["cpu_limit_cores"] = (
                    min(value, result["cpu_limit_cores"]) if result["cpu_limit_cores"] else value
                )
            except (OSError, ValueError, ZeroDivisionError):
                pass
    except (OSError, StopIteration):
        pass
    return result


def process_resources() -> dict:
    import psutil

    try:
        process = psutil.Process()
        with process.oneshot():
            memory = process.memory_info()
            cpu = process.cpu_times()
            data = {
                "available": True,
                "platform": platform.system(),
                "architecture": platform.machine(),
                "rss_bytes": memory.rss,
                "virtual_bytes": memory.vms,
                "cpu_seconds": cpu.user + cpu.system,
                "uptime_seconds": max(0, time.time() - process.create_time()),
                "threads": process.num_threads(),
                "logical_cpus": os.cpu_count(),
                **cgroup_limits(),
            }
        # This reports cumulative CPU time, not an unreliable first-call 0%.
        # The UI can compute delta CPU seconds / delta wall time between samples.
        return data
    except (psutil.Error, OSError):
        return {"available": False, "reason": "Process resource counters are unavailable."}
