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


@dataclass
class RequestReplay:
    value: str | None = None


_current: ContextVar[RequestReplay | None] = ContextVar("mnemion_request_replay", default=None)


@contextmanager
def request_replay():
    state = RequestReplay()
    token = _current.set(state)
    try:
        yield state
    finally:
        _current.reset(token)


def observed(replayed: bool) -> None:
    state = _current.get()
    if state is not None and state.value is None and type(replayed) is bool:
        state.value = "replayed" if replayed else "new"
