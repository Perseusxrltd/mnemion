"""Bounded update scheduling across suspend and wall-clock corrections."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time

from . import update_state as state_io
from .update_manifest import ManifestError


def _stamp(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")


def _seconds(value: str) -> float:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        raise ManifestError("Invalid managed update schedule") from None


class UpdateSchedule:
    """Either clock can make a check due; neither can postpone it indefinitely.

    Wall time detects a suspended VM whose monotonic clock stopped. Monotonic
    time handles a wall clock moved backwards. A short monotonic floor prevents
    repeated forward corrections from causing a network request every loop.
    Persist only wall-clock diagnostics, never a reboot-unsafe monotonic value.
    A transport retry count from 0 to 2 may sit beside those diagnostics.
    A missing count is zero. A malformed count grants no further short retries.
    """

    def __init__(self, root: Path, clock=time):
        self.root = root
        self.clock = clock
        self.next_wall = 0.0
        self.next_monotonic = 0.0
        self.not_before = 0.0
        self.record: dict = {}
        self._retries = 0
        self._retries_loaded = False

    def _read_retry_count(self) -> int:
        path = self.root / "schedule.json"
        if not path.exists():
            return 0
        try:
            value = state_io.read(path)
        except ManifestError:
            return 2
        count = value.get("transport_retries", 0)
        if type(count) is int and 0 <= count <= 2:
            return count
        return 2

    @property
    def transport_retries(self) -> int:
        if not self._retries_loaded:
            self._retries = self._read_retry_count()
            self._retries_loaded = True
        return self._retries

    def consume_transport_retry(self) -> int:
        if self.transport_retries < 2:
            self._retries += 1
        return self._retries

    def reset_transport_retries(self) -> None:
        """A completed check ends the episode. Persist that before the process exits."""
        self._retries = 0
        self._retries_loaded = True
        if self.record.pop("transport_retries", None) is not None:
            state_io.write(self.root / "schedule.json", self.record)

    def after(self, delay: float, *, reason: str) -> None:
        retries = self.transport_retries
        wall, monotonic = self.clock.time(), self.clock.monotonic()
        self.next_wall = wall + delay
        self.next_monotonic = monotonic + delay
        self.not_before = monotonic + min(30, delay)
        self.record = {
            "format": 1,
            "next_check_at": _stamp(self.next_wall),
            "scheduled_at": _stamp(wall),
            "delay_seconds": delay,
            "reason": reason,
            "last_attempt_at": self.record.get("last_attempt_at"),
        }
        if retries:
            self.record["transport_retries"] = retries
        state_io.write(self.root / "schedule.json", self.record)

    def due(self) -> bool:
        monotonic = self.clock.monotonic()
        return monotonic >= self.not_before and (
            monotonic >= self.next_monotonic or self.clock.time() >= self.next_wall
        )

    def attempt(self) -> None:
        self.record["last_attempt_at"] = _stamp(self.clock.time())
        state_io.write(self.root / "schedule.json", self.record)


def schedule_status(root: Path, *, enabled: bool, interval: int, last_check: dict | None) -> dict:
    value = state_io.read(root / "schedule.json") if (root / "schedule.json").exists() else None
    next_check, last_attempt, estimated = None, None, False
    if value is not None:
        if value.get("format") != 1 or not isinstance(value.get("next_check_at"), str):
            raise ManifestError("Invalid managed update schedule")
        next_check = _seconds(value["next_check_at"])
        if value.get("last_attempt_at") is not None:
            last_attempt = _stamp(_seconds(value["last_attempt_at"]))
    elif last_check and isinstance(last_check.get("checked_at"), str):
        # Older runtimes did not persist their random deadline. Its latest
        # possible normal deadline is a conservative diagnostic, not a timer.
        next_check = _seconds(last_check["checked_at"]) + interval * 1.1
        estimated = True
    return {
        "next_check_at": _stamp(next_check) if enabled and next_check is not None else None,
        "overdue": time.time() >= next_check if enabled and next_check is not None else False,
        "schedule_estimated": estimated,
        "last_attempt_at": last_attempt,
    }
