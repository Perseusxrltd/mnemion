"""Small ASGI ingress adapter, not a configured or deployed collection service.

The TLS terminator and server must be separately qualified with identifying
logs/headers disabled. This adapter never inspects request headers or peer data,
retains a request, emits diagnostics, or exposes live/filterable aggregates.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
import time

from .reporting import AggregateWindow, reporting_week
from .wire import WireError


class Collector:
    def __init__(self, publish_closed_window, *, clock=time.time):
        if not callable(publish_closed_window):
            raise TypeError("telemetry_publisher_required")
        self._publish = publish_closed_window
        self._clock = clock
        self._window = AggregateWindow(reporting_week(clock()))

    def _advance(self) -> bool:
        week = reporting_week(self._clock())
        if week < self._window.week:
            self._window.discard()
            return False
        if week > self._window.week:
            result = self._window.seal()
            self._window = AggregateWindow(week)
            # The standard publisher expires closed reports even when this
            # window had too few observations to produce a new result.
            prune = getattr(self._publish, "prune", None)
            if callable(prune):
                with suppress(Exception):
                    prune(week)
            if result is not None:
                try:
                    self._publish(result)
                except Exception:
                    # A failed aggregate publication is dropped, never a raw
                    # request backlog or a source of identifying diagnostics.
                    pass
        return True

    async def _boundaries(self):
        # This is the collector's clock, not a new client wake or sender. Hourly
        # checks also notice wall-clock changes; normal boundaries wake exactly
        # once to erase/close the old week, even if no new request arrives.
        while True:
            now = self._clock()
            end = 345600 + (self._window.week + 1) * 604800
            await asyncio.sleep(max(0.05, min(3600, end - now)))
            with suppress(WireError):
                self._advance()

    async def _lifespan(self, receive, send):
        task = None
        try:
            while True:
                event = await receive()
                if event["type"] == "lifespan.startup":
                    if task is None:
                        task = asyncio.create_task(self._boundaries())
                    await send({"type": "lifespan.startup.complete"})
                elif event["type"] == "lifespan.shutdown":
                    if task is not None:
                        task.cancel()
                        with suppress(asyncio.CancelledError):
                            await task
                    self._window.discard()
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        finally:
            if task is not None:
                task.cancel()
            self._window.discard()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return
        if scope["type"] != "http":
            raise RuntimeError("telemetry_http_only")
        status = 404
        if scope.get("path") == "/v1/report" and not scope.get("query_string"):
            if scope.get("method") == "OPTIONS":
                status = 204
            elif scope.get("method") == "POST":
                status = 400
                body = bytearray()
                deadline = time.monotonic() + 5
                try:
                    for _ in range(8):
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        event = await asyncio.wait_for(receive(), remaining)
                        if event.get("type") == "http.disconnect":
                            return
                        if event.get("type") != "http.request":
                            break
                        chunk = event.get("body", b"")
                        if type(chunk) is not bytes or len(body) + len(chunk) > 4:
                            break
                        body.extend(chunk)
                        if not event.get("more_body", False):
                            if self._advance() and self._window.contribute(bytes(body)):
                                status = 204
                            break
                except Exception:
                    pass
                finally:
                    body.clear()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-length", b"0"),
                    (b"cache-control", b"no-store"),
                    (b"access-control-allow-origin", b"*"),
                    (b"access-control-allow-methods", b"POST, OPTIONS"),
                    (b"access-control-allow-headers", b"content-type"),
                    (b"x-content-type-options", b"nosniff"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b""})
