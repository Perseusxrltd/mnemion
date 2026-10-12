"""Process birth records that remain stable across Linux realtime clock changes."""

from __future__ import annotations

from pathlib import Path
import re
import sys


def _read(path: Path, maximum: int) -> bytes:
    with path.open("rb") as stream:
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise ValueError("Process identity exceeded its size limit")
    return value


def _start_ticks(value: bytes, pid: int) -> int:
    # comm is parenthesized and can itself contain spaces, parentheses or
    # newlines. Everything after its final delimiter is a kernel stat field.
    if not value.startswith(f"{pid} (".encode()):
        raise ValueError("Process identity does not match its PID")
    _, separator, suffix = value.rpartition(b") ")
    fields = suffix.split()
    if not separator or len(fields) < 20 or not re.fullmatch(rb"[0-9]{1,20}", fields[19]):
        raise ValueError("Process start counter is unavailable")
    ticks = int(fields[19])  # /proc/PID/stat field 22; state is suffix field 0.
    if ticks >= 2**64:
        raise ValueError("Invalid process start counter")
    return ticks


def capture(process) -> dict:
    pid = process.pid
    if type(pid) is not int or not 0 < pid < 2**32:
        raise ValueError("Invalid process identity PID")
    if sys.platform == "linux":
        boot = _read(Path("/proc/sys/kernel/random/boot_id"), 64).strip().decode("ascii")
        if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", boot):
            raise ValueError("The kernel boot identity is unavailable")
        ticks = _start_ticks(_read(Path(f"/proc/{pid}/stat"), 16384), pid)
        # Linux's epoch create_time adds a derived boot epoch to this counter.
        # That epoch can move after a clock correction or a suspended VM resumes.
        return {"format": 1, "kind": "linux-start", "pid": pid, "boot": boot, "ticks": ticks}
    created = process.create_time()
    if type(created) not in (int, float) or not 0 < created < 2**63:
        raise ValueError("Process creation time is unavailable")
    return {"format": 1, "kind": "creation-time", "pid": pid, "created": created}


def matches(saved, process) -> bool:
    if not isinstance(saved, dict):
        return False
    current = capture(process)
    return saved.keys() == current.keys() and all(
        type(saved[key]) is type(value) and saved[key] == value for key, value in current.items()
    )


def matches_record(record: dict, process, *, legacy_field: str) -> bool:
    """Older records retain their exact epoch comparison; never widen tolerance."""
    created = record.get(legacy_field)
    if type(created) not in (int, float) or not 0 < created < 2**63:
        return False
    if "process_identity" in record:
        return matches(record["process_identity"], process)
    return created == process.create_time()
