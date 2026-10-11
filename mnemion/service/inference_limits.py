"""Bound native inference concurrency before tensor allocations begin."""

from __future__ import annotations

import math
import os
import threading
import time
from contextlib import contextmanager

from .errors import ServiceError


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
        self._executing = threading.BoundedSemaphore(1)
        self._lock = threading.Lock()
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
    def maintenance(self):
        """Nonblocking exclusive access for cache eviction, never preemption."""
        acquired = self._executing.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                self._executing.release()

    @contextmanager
    def acquire(self):
        if not self._admitted.acquire(blocking=False):
            with self._lock:
                self._stats["rejected"] += 1
            raise self.busy()
        started = time.monotonic()
        executing = False
        failed = True
        with self._lock:
            self._stats["queued"] += 1
        try:
            executing = self._executing.acquire(timeout=self.wait_seconds)
            with self._lock:
                self._stats["queued"] -= 1
                self._stats["wait_ms"] += (time.monotonic() - started) * 1000
                self._stats["active"] += int(executing)
            if not executing:
                with self._lock:
                    self._stats["rejected"] += 1
                raise self.busy()
            started = time.monotonic()
            yield
            failed = False
        finally:
            if executing:
                with self._lock:
                    self._stats["active"] -= 1
                    self._stats["failed" if failed else "completed"] += 1
                    self._stats["execution_ms"] += (time.monotonic() - started) * 1000
                self._executing.release()
            self._admitted.release()
