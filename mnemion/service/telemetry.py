"""Bounded, best-effort numeric telemetry. Canonical writes never wait for it."""

from __future__ import annotations

import bisect
import logging
import math
import threading
import time
from datetime import datetime, timezone
from uuid import UUID

from psycopg.types.json import Jsonb

from .db import Database, Identity

logger = logging.getLogger(__name__)

# Every duration lands in exactly one non-cumulative bin; last bin is unbounded.
LATENCY_BOUNDS_MS = [
    1,
    2,
    5,
    10,
    25,
    50,
    100,
    250,
    500,
    1000,
    2500,
    5000,
    10000,
    15000,
    30000,
    60000,
    300000,
]
STAGES = {"recall", "context", "index", "purge", "librarian", "evaluation"}
MODES = {"none", "lexical", "semantic", "hybrid"}
ORIGINS = {"interactive", "evaluation", "background"}
COUNTERS = (
    "input_bytes",
    "output_bytes",
    "input_tokens",
    "output_tokens",
    "records",
    "chunks",
    "empty_results",
    "fallbacks",
    "incomplete_index",
)


def percentile_bound(histogram: list[int], percentile: float) -> float | None:
    """Return the containing bucket's upper bound, never an invented exact p95."""
    total = sum(histogram)
    if not total:
        return None
    target = math.ceil(total * percentile)
    cumulative = 0
    for index, count in enumerate(histogram):
        cumulative += count
        if cumulative >= target:
            return LATENCY_BOUNDS_MS[index] if index < len(LATENCY_BOUNDS_MS) else None
    return None


class Telemetry:
    def __init__(self, database: Database, *, max_series: int = 1024, interval: float = 10):
        if not 1 <= max_series <= 4096 or not 1 <= interval <= 60:
            raise ValueError("Telemetry capacity or flush interval is outside the supported range")
        self.db = database
        self.max_series = max_series
        self.interval = interval
        self._lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self._buffer: dict[tuple, tuple[Identity | UUID, dict]] = {}
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None
        self._dropped = 0
        self._persisted = 0
        self._last_flush: str | None = None
        self.started_at = datetime.now(timezone.utc).isoformat()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "scope": "this_process",
                "started_at": self.started_at,
                "buffered_series": len(self._buffer),
                "series_capacity": self.max_series,
                "dropped_samples": self._dropped,
                "persisted_samples": self._persisted,
                "last_flush_at": self._last_flush,
                "flush_interval_seconds": self.interval,
                "retention_days": 31,
                "collection": "best_effort_numeric_aggregates",
            }

    def record(
        self,
        identity: Identity | UUID,
        space: UUID | None,
        *,
        stage: str,
        duration_ms: float,
        mode: str = "none",
        origin: str = "interactive",
        generation: str = "none",
        failed: bool = False,
        **counters: int,
    ) -> None:
        """No I/O or unbounded labels. Overflow drops diagnostics, not memory."""
        if (
            stage not in STAGES
            or mode not in MODES
            or origin not in ORIGINS
            or not 1 <= len(generation) <= 64
            or not math.isfinite(duration_ms)
            or duration_ms < 0
            or set(counters) - set(COUNTERS)
            or any(not isinstance(v, int) or v < 0 or v > 10**12 for v in counters.values())
        ):
            raise ValueError("Invalid numeric telemetry sample")
        bucket = datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat()
        tenant = identity.tenant_id if isinstance(identity, Identity) else identity
        # Keep the authenticating identity in the in-memory key so revoked callers
        # cannot lend their authorization to someone else's buffered samples.
        key = (identity, space, bucket, stage, mode, origin, generation)
        with self._lock:
            if key not in self._buffer:
                if len(self._buffer) >= self.max_series:
                    self._dropped += 1
                    return
                self._buffer[key] = (
                    identity,
                    {
                        "tenant_id": str(tenant),
                        "space_id": str(space) if space else None,
                        "bucket": bucket,
                        "stage": stage,
                        "mode": mode,
                        "origin": origin,
                        "generation_id": generation,
                        "calls": 0,
                        "failures": 0,
                        "duration_ms": 0,
                        "duration_max_ms": 0,
                        "latency_histogram": [0] * (len(LATENCY_BOUNDS_MS) + 1),
                        **dict.fromkeys(COUNTERS, 0),
                    },
                )
            row = self._buffer[key][1]
            row["calls"] += 1
            row["failures"] += int(failed)
            row["duration_ms"] += duration_ms
            row["duration_max_ms"] = max(row["duration_max_ms"], duration_ms)
            row["latency_histogram"][bisect.bisect_left(LATENCY_BOUNDS_MS, duration_ms)] += 1
            for field, value in counters.items():
                row[field] += value

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="mnemion-metrics", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stopped.wait(self.interval):
            self.flush()
        self.flush()

    def stop(self) -> None:
        self._stopped.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        # The daemon attempts a final bounded flush. Shutdown does not wait for a
        # stalled database indefinitely; canonical evidence is independent.

    def flush(self) -> None:
        if not self._flush_lock.acquire(blocking=False):
            return
        try:
            with self._lock:
                batch, self._buffer = self._buffer, {}
            if not batch:
                return
            grouped: dict[Identity | UUID, list[dict]] = {}
            for identity, row in batch.values():
                grouped.setdefault(identity, []).append(row)
            started = time.monotonic()
            for identity, rows in grouped.items():
                count = sum(row["calls"] for row in rows)
                if time.monotonic() - started >= (1 if self._stopped.is_set() else 5):
                    with self._lock:
                        self._dropped += count
                    continue
                try:
                    transaction = (
                        self.db.worker_transaction(identity, timeout=1)
                        if self.db.worker
                        else self.db.transaction(identity, timeout=1)
                    )
                    with transaction as conn:
                        conn.execute("SET LOCAL statement_timeout='2000'")
                        conn.execute("SET LOCAL lock_timeout='250'")
                        for row in rows:
                            if self.db.worker:
                                self._worker_record(conn, row)
                            else:
                                conn.execute("SELECT mnemion.record_metric(%s)", (Jsonb(row),))
                    with self._lock:
                        self._persisted += count
                        self._last_flush = datetime.now(timezone.utc).isoformat()
                except Exception as exc:
                    with self._lock:
                        self._dropped += count
                    logger.warning("Numeric telemetry batch dropped (%s)", type(exc).__name__)
            try:
                with self.db.pool.connection(timeout=1) as conn:
                    conn.execute("SET LOCAL statement_timeout='2000'")
                    conn.execute("SELECT mnemion.expire_metrics()")
            except Exception:
                logger.warning("Numeric telemetry expiry deferred")
        finally:
            self._flush_lock.release()

    @staticmethod
    def _worker_record(conn, row):
        # Same fixed schema and merge semantics, under the worker's tenant RLS.
        conn.execute(
            """INSERT INTO mnemion.metric_buckets
               SELECT * FROM jsonb_populate_record(NULL::mnemion.metric_buckets,%s)
               ON CONFLICT (tenant_id,space_id,bucket,stage,mode,origin,generation_id)
               DO UPDATE SET calls=metric_buckets.calls+excluded.calls,
               failures=metric_buckets.failures+excluded.failures,
               duration_ms=metric_buckets.duration_ms+excluded.duration_ms,
               duration_max_ms=greatest(metric_buckets.duration_max_ms,excluded.duration_max_ms),
               latency_histogram=mnemion.add_histogram(metric_buckets.latency_histogram,excluded.latency_histogram),
               input_bytes=metric_buckets.input_bytes+excluded.input_bytes,
               output_bytes=metric_buckets.output_bytes+excluded.output_bytes,
               input_tokens=metric_buckets.input_tokens+excluded.input_tokens,
               output_tokens=metric_buckets.output_tokens+excluded.output_tokens,
               records=metric_buckets.records+excluded.records,
               chunks=metric_buckets.chunks+excluded.chunks,
               empty_results=metric_buckets.empty_results+excluded.empty_results,
               fallbacks=metric_buckets.fallbacks+excluded.fallbacks,
               incomplete_index=metric_buckets.incomplete_index+excluded.incomplete_index""",
            (Jsonb(row),),
        )
