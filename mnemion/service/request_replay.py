"""Request-local idempotency metadata, independent of product telemetry.

The first receipt lookup belongs to the enclosing operation. Nested writes must
not replace that result. A mutable request-local value also crosses AnyIO's
worker-thread context copy without mixing concurrent HTTP requests. No request
key, identity, content or history is retained here.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

HEADER = "X-Mnemion-Idempotency"
CAPTURE_STORED_HEADER = "X-Mnemion-Capture-Stored"


@dataclass
class RequestReplay:
    value: str | None = None
    capture_stored_events: int | None = None


_current: ContextVar[RequestReplay | None] = ContextVar("mnemion_request_replay", default=None)


@contextmanager
def request_replay():
    state = RequestReplay()
    token = _current.set(state)
    try:
        yield state
    finally:
        _current.reset(token)


def observed(replayed: bool) -> RequestReplay | None:
    state = _current.get()
    if state is not None and state.value is None and type(replayed) is bool:
        state.value = "replayed" if replayed else "new"
        return state
    return None


def capture_stored(owner: RequestReplay | None, count: int) -> None:
    """Attach a fresh page's effect to its own request, never to nested writes.

    The caller supplies the count from this transaction, not a saved receipt.
    It is response metadata, not a product observation or persistent record.
    """
    if (
        owner is not None
        and owner is _current.get()
        and owner.value == "new"
        and owner.capture_stored_events is None
        and type(count) is int
        and 0 <= count <= 50
    ):
        owner.capture_stored_events = count
