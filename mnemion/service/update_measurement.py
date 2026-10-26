"""Optional host-owned update observations, inside the existing watcher lifetime.

Only the standalone automatic watcher establishes an owner. Remote requests,
manual/library calls and saved update journals cannot establish one. Delivery
uses an already scheduled watch sleep and is closed before update work resumes.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import time

from ..product_telemetry import policy


class Watcher:
    def __init__(self):
        self.last_offer = None

    def opportunity(self, now: float) -> bool:
        # This is an admission limit on existing wakeups, never a new timer.
        if self.last_offer is not None and 0 <= now - self.last_offer < 60:
            return False
        self.last_offer = now
        return True


_owner: ContextVar[Watcher | None] = ContextVar("mnemion_update_measurement", default=None)


def _available() -> bool:
    return policy.COLLECTION_AVAILABLE and policy.COLLECTOR_URL is not None


@contextmanager
def automatic_watcher():
    """Use this host OS account's acknowledged policy, never an operator token."""
    token = _owner.set(Watcher())
    try:
        yield
    finally:
        # No shutdown flush or interpretation of an unfinished update journal.
        _owner.reset(token)


class Attempt:
    def __init__(self, active):
        self.active = active

    def finish(self, outcome: str, reason: str = "none") -> None:
        try:
            self.active.finish(outcome, reason)
        except Exception:
            pass

    def discard(self) -> None:
        try:
            self.active.discard()
        except Exception:
            pass

    def restored_after_failure(self) -> None:
        # Called only after a failed candidate's rollback has fully returned.
        self.finish("failed", "other_failure")


@contextmanager
def operation(action: str):
    """Only a fixed action enters telemetry; operational values stay at the caller."""
    attempt = None
    try:
        if _owner.get() is not None and _available() and type(action) is str:
            from ..product_telemetry import workflow
            from ..product_telemetry.catalog import maintenance_specification

            spec = maintenance_specification()["host_updates"].get(action)
            if spec is not None and "workflow" in spec:
                active = workflow.begin(spec["workflow"], "headless")
                if active is not None:
                    attempt = Attempt(active)
    except Exception:
        pass
    try:
        yield attempt
    except Exception:
        if attempt is not None:
            # A lost reply/evidence write does not prove that the work failed.
            attempt.finish("unconfirmed", "other_failure")
        raise
    except BaseException:
        if attempt is not None:
            attempt.discard()
        raise
    else:
        if attempt is not None:
            attempt.finish("success")


async def _deliver_until(deadline: float, current: dict, clock) -> None:
    import asyncio

    from ..product_telemetry.activity import application_delivery

    async with application_delivery() as owner:
        if owner is not None and clock.monotonic() < deadline:
            owner.offer(current["revision"], current["store_generation"])
            await asyncio.sleep(max(0, deadline - clock.monotonic()))
    # Closing the context cancels and closes the original attempt/socket/gauges.
    # No task is left suspended while synchronous update work holds its lock.


def quiet_wait(seconds: float, *, clock=time) -> None:
    """Fit optional delivery into the wait already chosen by the update watcher.

    Fresh policy/queue reads occur at most once a minute while that watcher is
    already awake. This also lets a later process deliver a still-valid approved
    report, without reconstructing observations from private operational history.
    """
    owner = _owner.get()
    if owner is None or not _available():
        clock.sleep(seconds)
        return
    deadline = clock.monotonic() + seconds
    try:
        if owner.opportunity(clock.monotonic()):
            current = policy.status()
            if current["effective_enabled"]:
                from ..product_telemetry.delivery import DeliveryBudget

                if (
                    DeliveryBudget().eligible(
                        expected_revision=current["revision"],
                        expected_generation=current["store_generation"],
                    )
                    and clock.monotonic() < deadline
                ):
                    import asyncio

                    asyncio.run(_deliver_until(deadline, current, clock))
    except Exception:
        # Optional setup/send errors preserve the original remaining wait.
        pass
    remaining = deadline - clock.monotonic()
    if remaining > 0:
        clock.sleep(remaining)
