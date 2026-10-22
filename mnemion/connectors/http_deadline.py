"""One provider budget, including repeated reads on direct and proxy sockets.

HTTPX's read timeout alone restarts on every socket read. The pinned HTTPX 0.28
transport hook retains its normal TLS/environment-proxy configuration and wraps
only the HTTPcore network backend. No background thread or request survives a
timeout. OS resolver and filesystem calls cannot be preempted by a socket timer;
their elapsed time is checked before subsequent work.
"""

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable

import httpcore
import httpx


class DeadlineExpired(TimeoutError):
    pass


@dataclass
class Budget:
    expires: float
    clock: Callable[[], float]

    def timeout(self, requested=None):
        remaining = self.expires - self.clock()
        if remaining <= 0:
            raise DeadlineExpired("Provider request budget exhausted")
        return remaining if requested is None else min(requested, remaining)


current_budget: ContextVar[Budget | None] = ContextVar("provider_http_budget", default=None)


def _timeout(requested=None):
    budget = current_budget.get()
    return budget.timeout(requested) if budget is not None else requested


class DeadlineStream(httpcore.NetworkStream):
    def __init__(self, stream):
        self.stream = stream

    def read(self, max_bytes, timeout=None):
        result = self.stream.read(max_bytes, timeout=_timeout(timeout))
        _timeout()
        return result

    def write(self, buffer, timeout=None):
        self.stream.write(buffer, timeout=_timeout(timeout))
        _timeout()

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        stream = self.stream.start_tls(
            ssl_context, server_hostname=server_hostname, timeout=_timeout(timeout)
        )
        try:
            _timeout()
        except DeadlineExpired:
            stream.close()
            raise
        return DeadlineStream(stream)

    def get_extra_info(self, info):
        return self.stream.get_extra_info(info)

    def close(self):
        self.stream.close()


class DeadlineBackend(httpcore.NetworkBackend):
    def __init__(self, backend):
        self.backend = backend

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        stream = self.backend.connect_tcp(
            host,
            port,
            timeout=_timeout(timeout),
            local_address=local_address,
            socket_options=socket_options,
        )
        return self._connected(stream)

    def connect_unix_socket(self, path, timeout=None, socket_options=None):
        stream = self.backend.connect_unix_socket(
            path, timeout=_timeout(timeout), socket_options=socket_options
        )
        return self._connected(stream)

    @staticmethod
    def _connected(stream):
        try:
            _timeout()
        except DeadlineExpired:
            stream.close()
            raise
        return DeadlineStream(stream)

    def sleep(self, seconds):
        self.backend.sleep(_timeout(seconds))
        _timeout()


def _bounded_transport(transport):
    # These two adapter hooks are covered by real direct/proxy HTTP tests and
    # the locked dependency matrix. Fail visibly if a dependency changes them.
    pool = getattr(transport, "_pool", None)
    backend = getattr(pool, "_network_backend", None)
    if not isinstance(backend, httpcore.NetworkBackend):
        raise RuntimeError("Provider HTTP transport no longer supports bounded requests")
    pool._network_backend = DeadlineBackend(backend)
    return transport


class DeadlineClient(httpx.Client):
    def _init_transport(self, *args, **kwargs):
        return _bounded_transport(super()._init_transport(*args, **kwargs))

    def _init_proxy_transport(self, *args, **kwargs):
        return _bounded_transport(super()._init_proxy_transport(*args, **kwargs))
