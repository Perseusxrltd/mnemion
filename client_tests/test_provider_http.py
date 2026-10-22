"""Provider byte and time limits include streaming and retry behavior."""

import gzip
import threading
import time
import tracemalloc
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest

from mnemion.connectors.http import ProviderHTTP
from mnemion.connectors.providers import ProviderError


class Chunks(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    def __iter__(self):
        yield from self.chunks


def provider(handler, **options):
    return ProviderHTTP(
        "https://provider.invalid",
        SimpleNamespace(read=lambda: "synthetic-provider-token"),
        transport=httpx.MockTransport(handler),
        **options,
    )


def test_response_limit_rejects_oversized_chunk_before_copying_it():
    # Allocate the incoming transport chunk before measurement: the connector
    # must reject it without allocating another multi-megabyte buffer.
    chunk = b"x" * (2 * 1024 * 1024)
    client = provider(lambda request: httpx.Response(200, stream=Chunks([chunk])))
    try:
        tracemalloc.start()
        with pytest.raises(ProviderError, match="provider_response_too_large"):
            client.get("/oversized", maximum=4096, binary=True)
        _, peak = tracemalloc.get_traced_memory()
        assert peak < 256 * 1024
    finally:
        tracemalloc.stop()
        client.close()


def test_provider_does_not_implicitly_expand_encoded_body():
    def handle(request):
        assert request.headers["Accept-Encoding"] == "identity"
        return httpx.Response(
            200,
            headers={"Content-Encoding": "gzip"},
            stream=Chunks([gzip.compress(b"{}")]),
        )

    client = provider(handle)
    try:
        with pytest.raises(ProviderError, match="invalid_provider_response"):
            client.get("/encoded")
    finally:
        client.close()


class Clock:
    now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_progress_and_token_reads_do_not_reset_the_shared_budget():
    clock = Clock()
    received = []

    def fragments():
        for number in range(20):
            clock.sleep(0.3)
            received.append(number)
            yield b"x"

    client = provider(
        lambda request: httpx.Response(200, stream=Chunks(fragments())),
        clock=clock,
        total_timeout=1,
    )
    try:
        with pytest.raises(ProviderError, match="provider_unavailable"):
            client.get("/progress", binary=True)
        assert len(received) == 4

        client.token = SimpleNamespace(read=lambda: clock.sleep(2) or "rotated-fixture")
        with pytest.raises(ProviderError, match="provider_unavailable"):
            client.get("/token-delay", binary=True)
        assert len(received) == 4
    finally:
        client.close()


def test_retries_close_streams_and_share_one_time_budget():
    clock, requests, closed = Clock(), [], []

    class ResponseBody(Chunks):
        def close(self):
            closed.append(True)

    def respond(request):
        requests.append(request)
        clock.sleep(1)
        return httpx.Response(429, headers={"Retry-After": "2"}, stream=ResponseBody([]))

    def wait(seconds):
        assert closed
        clock.sleep(seconds)

    client = provider(respond, clock=clock, sleep=wait, total_timeout=5)
    try:
        with pytest.raises(ProviderError, match="provider_unavailable"):
            client.get("/rate-limit")
        assert len(requests) == len(closed) == 2
        assert clock.now == 4
    finally:
        client.close()


def test_allowed_response_at_exact_byte_limit_and_access_failure_semantics():
    response = httpx.Response(200, stream=Chunks([b"{", b"}"]))
    client = provider(lambda request: response)
    try:
        assert client.get("/limit", maximum=2) == {}
    finally:
        client.close()
    for status in (401, 403, 404, 410):
        client = provider(lambda request: httpx.Response(status))
        try:
            with pytest.raises(ProviderError) as caught:
                client.get("/lost")
            assert caught.value.code == "provider_access_lost" and caught.value.access_lost
        finally:
            client.close()


def test_socket_budget_is_refreshed_for_each_read_and_reused_connection():
    from mnemion.connectors.http_deadline import Budget, DeadlineStream, current_budget

    clock, timeouts = Clock(), []

    def read(size, *, timeout):
        timeouts.append(timeout)
        clock.sleep(0.4)
        return b"x"

    stream = DeadlineStream(SimpleNamespace(read=read))
    reset = current_budget.set(Budget(1, clock))
    try:
        assert stream.read(1, timeout=30) == b"x"
        assert stream.read(1, timeout=30) == b"x"
        assert timeouts == [1, 0.6]
    finally:
        current_budget.reset(reset)
    # A pooled connection follows the next operation, not its original expiry.
    reset = current_budget.set(Budget(clock.now + 2, clock))
    try:
        assert stream.read(1, timeout=30) == b"x"
        assert timeouts[-1] == pytest.approx(2)
    finally:
        current_budget.reset(reset)


@pytest.fixture
def local_provider():
    observed = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            observed.append(self.path)
            if self.path.endswith("/fast"):
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
                return
            self.send_response(200)
            self.send_header("Content-Length", "3")
            self.end_headers()
            try:
                self.wfile.write(b"x")
                self.wfile.flush()
                time.sleep(0.18)
                self.wfile.write(b"x")
                self.wfile.flush()
                time.sleep(1)
                self.wfile.write(b"x")
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", observed
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("proxy", [False, True])
def test_real_direct_and_environment_proxy_reads_stop_and_recover(
    monkeypatch, local_provider, proxy
):
    address, observed = local_provider
    for name in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.upper(), raising=False)
    if proxy:
        monkeypatch.setenv("HTTP_PROXY", address)
    client = ProviderHTTP(
        "http://provider.invalid" if proxy else address,
        SimpleNamespace(read=lambda: "synthetic-fixture"),
        total_timeout=0.3,
    )
    try:
        started = time.monotonic()
        with pytest.raises(ProviderError, match="provider_unavailable"):
            client.get("/slow", binary=True)
        assert time.monotonic() - started < 0.9
        assert client.get("/fast") == {}
        assert observed == (
            ["http://provider.invalid/slow", "http://provider.invalid/fast"]
            if proxy
            else ["/slow", "/fast"]
        )
    finally:
        client.close()
