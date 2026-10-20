"""Bound native inference concurrency before tensor allocations begin."""

from __future__ import annotations

import math
import os
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass

from .errors import ServiceError


@dataclass(eq=False)
class _Lease:
    thread: int
    cooperative_remaining: float
    entered: bool = False
    executing_since: float | None = None
    expired: bool = False


class InferenceGate:
    """One inference at a time, with a bounded queue and a short admission wait.

    A thread-safe model session can still allocate one set of activation tensors
    per caller. Serializing execution makes its memory requirement predictable.
    Saturated callers receive a retryable error instead of an unbounded wait.
    """

    def __init__(self, *, max_queued: int = 16, wait_seconds: float = 2):
        if (
            not isinstance(max_queued, int)
            or isinstance(max_queued, bool)
            or not 0 <= max_queued <= 64
        ):
            raise ValueError("Inference queue size must be an integer from 0 to 64")
        if (
            isinstance(wait_seconds, bool)
            or not isinstance(wait_seconds, (int, float))
            or not math.isfinite(wait_seconds)
            or not 0 <= wait_seconds <= 5
        ):
            raise ValueError("Inference admission wait must be between 0 and 5 seconds")
        self.wait_seconds = wait_seconds
        self.max_queued = max_queued
        self._admitted = threading.BoundedSemaphore(max_queued + 1)
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._waiters: deque[_Lease] = deque()
        self._owner: _Lease | object | None = None
        self._last_used = time.monotonic()
        self._stats = {
            "active": 0,
            "queued": 0,
            "completed": 0,
            "failed": 0,
            "rejected": 0,
            "wait_ms": 0.0,
            "execution_ms": 0.0,
        }

    def snapshot(self) -> dict:
        """Cumulative process-local counters; contains no text or caller labels."""
        with self._lock:
            return {"concurrency": 1, "queue_capacity": self.max_queued, **self._stats}

    @classmethod
    def from_environment(cls) -> "InferenceGate":
        """A bounded, process-wide admission policy for all approved embedding models."""
        return cls(
            max_queued=int(os.environ.get("MNEMION_MODEL_MAX_QUEUED", "16")),
            wait_seconds=float(os.environ.get("MNEMION_MODEL_WAIT_SECONDS", "2")),
        )

    @staticmethod
    def busy() -> ServiceError:
        return ServiceError(503, "inference_busy", "Model capacity is busy; retry shortly.")

    @contextmanager
    def maintenance(self, *, minimum_idle_seconds: float = 0):
        """Nonblocking exclusive access for cache eviction, never preemption."""
        marker = object()
        with self._condition:
            acquired = (
                self._owner is None
                and not self._waiters
                and (
                    minimum_idle_seconds <= 0
                    or time.monotonic() - self._last_used >= minimum_idle_seconds
                )
            )
            if acquired:
                self._owner = marker
        try:
            yield acquired
        finally:
            if acquired:
                with self._condition:
                    self._owner = None
                    self._condition.notify_all()

    def _wait_for_turn(self, lease: _Lease, seconds: float, *, cooperative=False) -> bool:
        """Called with the condition held; retain the operation's admission token."""
        started = time.monotonic()
        deadline = started + seconds
        self._waiters.append(lease)
        self._stats["queued"] += 1
        first_attempt = True
        try:
            while True:
                now = time.monotonic()
                if (
                    self._owner is None
                    and self._waiters[0] is lease
                    and (first_attempt or now < deadline)
                ):
                    self._owner = lease
                    lease.entered = True
                    lease.executing_since = now
                    self._stats["active"] += 1
                    self._last_used = lease.executing_since
                    return True
                remaining = deadline - now
                if remaining <= 0:
                    return False
                first_attempt = False
                self._condition.wait(remaining)
        finally:
            elapsed = time.monotonic() - started
            self._stats["wait_ms"] += elapsed * 1000
            if cooperative:
                lease.cooperative_remaining = max(0, lease.cooperative_remaining - elapsed)
            self._waiters.remove(lease)
            self._stats["queued"] -= 1
            # A cancelled/timed-out head must not strand the next live waiter.
            self._condition.notify_all()

    def _release_execution(self, lease: _Lease) -> None:
        if self._owner is not lease:
            return
        now = time.monotonic()
        self._stats["active"] -= 1
        self._stats["execution_ms"] += (now - lease.executing_since) * 1000
        self._last_used = now
        lease.executing_since = None
        self._owner = None
        self._condition.notify_all()

    def checkpoint(self) -> bool:
        """Yield an admitted operation to existing FIFO waiters at a safe boundary.

        The caller must finish its native iterator and release tokenizer locks
        first. After resumption it must recheck its model and memory admission:
        another model may have evicted its inactive session while it waited.
        """
        with self._condition:
            lease = self._owner
            if not isinstance(lease, _Lease) or lease.thread != threading.get_ident():
                raise RuntimeError("Only the executing inference may yield its gate")
            if not self._waiters:
                return False
            self._release_execution(lease)
            if not self._wait_for_turn(lease, lease.cooperative_remaining, cooperative=True):
                lease.expired = True
                self._stats["rejected"] += 1
                raise self.busy()
            return True

    @contextmanager
    def acquire(self, *, cooperative_wait_seconds: float = 30):
        if (
            isinstance(cooperative_wait_seconds, bool)
            or not isinstance(cooperative_wait_seconds, (int, float))
            or not math.isfinite(cooperative_wait_seconds)
            or not 0 <= cooperative_wait_seconds <= 120
        ):
            raise ValueError("Cooperative inference wait must be between 0 and 120 seconds")
        if not self._admitted.acquire(blocking=False):
            with self._lock:
                self._stats["rejected"] += 1
            raise self.busy()
        lease = _Lease(threading.get_ident(), float(cooperative_wait_seconds))
        failed = True
        try:
            with self._condition:
                if not self._wait_for_turn(lease, self.wait_seconds):
                    self._stats["rejected"] += 1
                    raise self.busy()
            yield
            if lease.expired:
                # Catching a checkpoint timeout must not turn an unowned lease
                # into a successfully completed model operation.
                raise self.busy()
            failed = False
        finally:
            with self._condition:
                # A failed resumption no longer owns execution. Never release
                # the foreground operation that is still running in its place.
                self._release_execution(lease)
                if lease.entered:
                    self._stats["failed" if failed else "completed"] += 1
            self._admitted.release()
