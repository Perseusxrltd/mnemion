"""Use an existing service loop; no telemetry worker, timer or CLI keepalive."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
import time

from . import policy
from .cohorts import reviewed_cohorts

_owners: dict[Path, Activity] = {}
_registry_lock = Lock()


def _root(root: Path | None) -> Path:
    return (root if root is not None else policy.default_directory()).absolute()


def offer_recorded(root: Path | None, revision: int, generation: str) -> None:
    """Only fixed private policy stamps cross the thread-pool/loop boundary."""
    with _registry_lock:
        owner = _owners.get(_root(root))
    if owner is not None:
        owner.offer(revision, generation)


def offer_awake(root: Path | None) -> None:
    """Existing work may revisit this owner's prior queue, not create a stamp."""
    with _registry_lock:
        owner = _owners.get(_root(root))
    if owner is not None:
        owner.awake()


class Activity:
    def __init__(self, root: Path, endpoint, conditions, *, prepare=None, cleanup=None):
        from .delivery import DeliveryBudget

        self.root = _root(root)
        self.endpoint = endpoint
        self.prepare = prepare
        self.cleanup = cleanup
        self.budget = DeliveryBudget(self.root, environment=conditions)
        self.loop = asyncio.get_running_loop()
        self._lock = Lock()
        self._scheduled = False
        self._closed = False
        self._next_check = 0.0
        self._task: asyncio.Task | None = None
        self._last_recorded: tuple[int, str] | None = None

    def offer(self, revision: int, generation: str) -> None:
        if type(revision) is not int or not policy.valid_generation(generation):
            return
        with self._lock:
            if self._closed:
                return
            # One immutable stamp identifies committed work, not permission.
            # Keep the latest even when an active attempt coalesces this offer.
            self._last_recorded = (revision, generation)
            self._schedule_locked(revision, generation)

    def awake(self) -> None:
        with self._lock:
            if self._last_recorded is not None:
                self._schedule_locked(*self._last_recorded)

    def _schedule_locked(self, revision: int, generation: str) -> None:
        now = time.monotonic()
        if self._closed or self._scheduled or now < self._next_check:
            return
        self._scheduled = True
        self._next_check = now + 60
        try:
            self.loop.call_soon_threadsafe(self._launch, revision, generation)
        except RuntimeError:
            self._scheduled = False

    def _launch(self, revision: int, generation: str) -> None:
        with self._lock:
            if self._closed:
                self._scheduled = False
                return
            self._task = self.loop.create_task(self._attempt(revision, generation))

    async def _attempt(self, revision: int, generation: str) -> None:
        from .transport import send

        report = None
        try:
            if not policy.COLLECTION_AVAILABLE or not self.endpoint.validate():
                return
            if self.prepare is not None and (
                not self.budget.eligible(expected_revision=revision, expected_generation=generation)
                or not await self.prepare()
            ):
                return
            report = self.budget.reserve(
                expected_revision=revision,
                expected_generation=generation,
                cohorts=reviewed_cohorts(),
            )
            if report is not None:
                await send(self.budget, report, self.endpoint)
        except Exception:
            # No operational exception, identifier or trace becomes analytics.
            pass
        finally:
            if report is not None:
                self.budget.cancel(report)
            if self.cleanup is not None:
                try:
                    self.cleanup()
                except Exception:
                    pass
            with self._lock:
                self._scheduled = False
                self._task = None

    def stop(self):
        with self._lock:
            self._closed = True
            self._last_recorded = None
            task = self._task
        if task is not None:
            task.cancel()
        return task

    async def close(self) -> None:
        task = self.stop()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)


@asynccontextmanager
async def application_delivery(*, root: Path | None = None, can_start=None):
    """Install only inside an existing app lifespan; unavailable builds do nothing."""
    if not policy.COLLECTION_AVAILABLE or policy.COLLECTOR_URL is None:
        yield
        return
    from .endpoint import release_endpoint

    endpoint = release_endpoint()
    if endpoint is None:
        yield
        return
    from .conditions import ServiceConditions

    conditions = ServiceConditions(can_start=can_start)
    owner = Activity(
        _root(root), endpoint, conditions.read, prepare=conditions.prepare, cleanup=conditions.close
    )
    with _registry_lock:
        # Multiple applications may share an installation; only its first live
        # owner is registered, and another lifespan cannot replace it silently.
        installed = owner.root not in _owners
        if installed:
            _owners[owner.root] = owner
    try:
        yield owner if installed else None
    finally:
        with _registry_lock:
            if installed and _owners.get(owner.root) is owner:
                del _owners[owner.root]
        await owner.close()
