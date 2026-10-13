"""Cooperative, live RAM admission for native models and background work.

This is a working-set target, not an OS reservation or an RSS kill limit. An
in-flight native call finishes before caches can be released. Canonical writes,
lexical retrieval and deletion do not require a loaded embedding model.
"""

from __future__ import annotations

from dataclasses import dataclass
import gc
import threading
import time
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import ServiceError
from .heap_memory import release_unused_heap
from .resources import cgroup_limits

MIB = 1024**2
GIB = 1024**3


class MemoryOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    mode: Literal["auto", "manual"] = "auto"
    limit_mib: int | None = Field(default=None, ge=256, le=1048576)

    @model_validator(mode="after")
    def selected_limit(self):
        if (self.mode == "manual") != (self.limit_mib is not None):
            raise ValueError("Manual mode needs a limit; automatic mode must not retain one")
        return self


@dataclass(frozen=True)
class MemorySample:
    total: int
    available: int
    engine: int
    database: int = 0
    desktop: int = 0
    os_limit: int | None = None
    complete: bool = True

    @property
    def used(self) -> int:
        return self.engine + self.database + self.desktop


def sample_memory(
    *, database_identity: tuple[int, float] | None = None, desktop_bytes: int = 0
) -> MemorySample:
    """Sample only this service and its explicitly identified database tree.

    RSS includes shared mappings and is deliberately conservative when summed.
    A reused PID is never included as part of the owned database.
    """
    import psutil

    memory = psutil.virtual_memory()
    limits = cgroup_limits()
    total = min(memory.total, limits["memory_limit_bytes"] or memory.total)
    remaining = limits["memory_available_bytes"]
    available = min(memory.available, remaining) if remaining is not None else memory.available
    process = psutil.Process()
    engine = process.memory_info().rss
    database = 0
    complete = True
    if database_identity:
        try:
            root = psutil.Process(database_identity[0])
            if root.create_time() != database_identity[1]:
                complete = False
            else:
                for child in [root, *root.children(recursive=True)]:
                    try:
                        database += child.memory_info().rss
                    except psutil.NoSuchProcess:
                        pass
                    except psutil.Error:
                        complete = False
        except psutil.Error:
            complete = False
    return MemorySample(
        total=total,
        available=max(0, available),
        engine=engine,
        database=database,
        desktop=max(0, desktop_bytes),
        os_limit=limits["memory_limit_bytes"],
        complete=complete,
    )


def working_target(options: MemoryOptions, sample: MemorySample) -> tuple[int, int]:
    """Preserve OS headroom; own RSS is added back to avoid feedback shrinkage."""
    reserve = min(2 * GIB, max(256 * MIB, sample.total // 8))
    requested = (
        min(4 * GIB, sample.total // 4) if options.mode == "auto" else options.limit_mib * MIB
    )
    capacity = max(0, min(sample.total - reserve, sample.available + sample.used - reserve))
    # Downward rounding never silently gives a user more than their request.
    return max(0, min(requested, capacity) // (16 * MIB) * (16 * MIB)), reserve


def model_requirements(model) -> tuple[int, int]:
    """Conservative starting budgets for the two pinned CPU implementations.

    Measurements and OS pressure still control admission after loading. These
    estimates do not promise to fit every architecture or document batch.
    """
    if "multilingual-e5-small" in model.generation.model:
        return 1024 * MIB, 512 * MIB
    return 512 * MIB, 192 * MIB


class MemoryBudget:
    def __init__(
        self,
        options: MemoryOptions | None = None,
        *,
        sample: Callable[[], MemorySample] = sample_memory,
        revision: str = "default",
    ):
        self._options = options or MemoryOptions()
        self._sample = sample
        self._revision = revision
        self._lock = threading.RLock()
        self._cached: MemorySample | None = None
        self._sample_at = 0.0
        self._registry = None
        self._policy_error = False
        self._rejected = 0
        self._evictions = 0

    def attach(self, registry) -> None:
        self._registry = registry
        registry.memory_budget = self
        for model in registry._by_generation.values():
            if hasattr(model, "_unload"):
                model._memory_budget = self

    def configure(self, options: MemoryOptions, revision: str) -> None:
        with self._lock:
            self._options, self._revision = options, revision
            self._policy_error = False
            self._sample_at = 0

    def policy_unavailable(self) -> None:
        # Retain the last valid cap, and stop admitting work until the operator
        # repairs a damaged policy. Never silently reset a manual cap to auto.
        with self._lock:
            self._policy_error = True

    def _measurement(self, *, refresh=False) -> MemorySample:
        with self._lock:
            if refresh or self._cached is None or time.monotonic() - self._sample_at >= 1:
                try:
                    self._cached = self._sample()
                except (OSError, RuntimeError):
                    if self._cached is None:
                        self._cached = MemorySample(0, 0, 0, complete=False)
                    else:
                        from dataclasses import replace

                        self._cached = replace(self._cached, complete=False)
                self._sample_at = time.monotonic()
            return self._cached

    def snapshot(self, *, refresh=False) -> dict:
        with self._lock:
            sample = self._measurement(refresh=refresh)
            target, reserve = working_target(self._options, sample)
            free = max(0, target - sample.used)
            blocked = (
                self._policy_error
                or not sample.complete
                or sample.available < reserve
                or free < 48 * MIB
            )
            reason = (
                "policy_unavailable"
                if self._policy_error
                else "measurement_unavailable"
                if not sample.complete
                else "system_pressure"
                if sample.available < reserve
                else "working_set_over_budget"
                if free < 48 * MIB
                else None
            )
            minimum = 0
            if self._registry:
                minimum, _ = model_requirements(self._registry.default)
                minimum += sample.desktop
            model_paused = blocked or bool(minimum and target < minimum)
            return {
                "mode": self._options.mode,
                "requested_limit_mib": self._options.limit_mib,
                "revision": self._revision,
                "target_bytes": target,
                "used_bytes": sample.used,
                "engine_bytes": sample.engine,
                "database_bytes": sample.database,
                "desktop_bytes": sample.desktop,
                "effective_hardware_bytes": sample.total,
                "available_hardware_bytes": sample.available,
                "system_reserve_bytes": reserve,
                "os_memory_limit_bytes": sample.os_limit,
                "measurement_complete": sample.complete,
                "measurement": "sum_of_process_resident_sets",
                "scope": "local_engine_database_and_reported_desktop",
                "enforcement": "cooperative",
                "state": "paused"
                if model_paused
                else "constrained"
                if free < 256 * MIB
                else "normal",
                "reason": reason or ("model_exceeds_budget" if model_paused else None),
                "background_paused": blocked,
                "indexing_paused": model_paused,
                "minimum_model_budget_bytes": minimum,
                "batch_size": 1
                if free < 128 * MIB
                else 4
                if free < 256 * MIB
                else 8
                if free < 512 * MIB
                else 16,
                "rejected_inferences": self._rejected,
                "model_evictions": self._evictions,
            }

    def can_start_background(self) -> bool:
        return not self.snapshot()["background_paused"]

    def can_schedule(self, model) -> bool:
        view = self.snapshot()
        minimum, _ = model_requirements(model)
        return (
            not view["background_paused"]
            and view["target_bytes"] >= minimum + view["desktop_bytes"]
        )

    def can_infer(self, model) -> bool:
        view = self.snapshot()
        minimum, incremental = model_requirements(model)
        required = minimum + view["desktop_bytes"]
        # A model already in RAM only needs bounded activation headroom.
        additional = 48 * MIB if model._model is not None else incremental + 64 * MIB
        return (
            not view["background_paused"]
            and view["target_bytes"] >= required
            and view["used_bytes"] + additional <= view["target_bytes"]
        )

    def _release(self, models) -> None:
        released = 0
        for model in models:
            if hasattr(model, "_unload") and model._model is not None:
                model._unload()
                released += 1
        if released:
            gc.collect()
            release_unused_heap()
            with self._lock:
                self._evictions += released
                self._sample_at = 0

    def admit(self, model) -> None:
        """Called only while holding the registry's exclusive inference gate."""
        if self.can_infer(model):
            return
        if self._registry:
            self._release(
                other for other in self._registry._by_generation.values() if other is not model
            )
        if not self.can_infer(model):
            with self._lock:
                self._rejected += 1
            raise ServiceError(
                503,
                "inference_memory_budget",
                "Model work is paused by the host RAM budget. Use lexical search, wait for memory to free up, or ask the host operator to adjust the budget.",
            )

    def batch_size(self, model) -> int:
        self.admit(model)
        return self.snapshot()["batch_size"]

    def trim(self) -> bool:
        """Release idle models on pressure; never race an active native call."""
        if not self._registry:
            return False
        view = self.snapshot(refresh=True)
        if not view["background_paused"] and all(
            self.can_infer(model)
            for model in self._registry._by_generation.values()
            if hasattr(model, "_unload") and model._model is not None
        ):
            return False
        with self._registry.inference_gate.maintenance() as acquired:
            if not acquired:
                return False
            self._release(self._registry._by_generation.values())
            return True
