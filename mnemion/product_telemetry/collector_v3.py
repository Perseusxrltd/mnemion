"""Reference ingress for v3 summaries. Not mounted by the production server.

The process sees a bounded summary long enough to add it to fixed counters,
then drops the bytes. It does not read headers, keep a peer row, or accept a
randomness mode from the request. ``random_below`` is an in-process test hook.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
import time

from .aggregate_v3 import AggregateWindow
from .reporting import reporting_week
from .wire_v3 import PACKET_BYTES, WIRE, WireV3Error


class CollectorV3:
    def __init__(self, publish_closed_window, *, clock=time.time, random_below=None):
        if not callable(publish_closed_window) or (random_below is not None and not callable(random_below)):
            raise TypeError("telemetry_publisher_required")
        self._publish = publish_closed_window
        self._clock = clock
        self._random_below = random_below
        self._publication_failures: list[dict] = []
        self._window = AggregateWindow(reporting_week(clock()))

    @property
    def publication_failures(self) -> list[dict]:
        self._prune_failures()
        return self._publication_failures

    def _prune_failures(self) -> None:
        current = reporting_week(self._clock())
        low = current - WIRE["reporting"]["retained_windows"]
        kept = {}
        for item in self._publication_failures:
            week = item.get("window_week") if type(item) is dict else None
            if type(week) is int and low <= week < current and item.get("state") == "publication_failed":
                kept[week] = {"window_week": week, "state": "publication_failed"}
        self._publication_failures = [kept[week] for week in sorted(kept)]

    def _advance(self) -> bool:
        week = reporting_week(self._clock())
        if week < self._window.week:
            self._window.discard()
            return False
        if week > self._window.week:
            result = self._window.seal(self._random_below) if self._random_below is not None else self._window.seal()
            self._window = AggregateWindow(week)
            prune = getattr(self._publish, "prune", None)
            if callable(prune):
                with suppress(Exception):
                    prune(week)
            if result is not None:
                try:
                    self._publish(result)
                except Exception:
                    week = result.get("window_week") if type(result) is dict else None
                    if type(week) is int:
                        self._record_failure(week)
        return True

    def _record_failure(self, week: int) -> None:
        current = reporting_week(self._clock())
        low = current - WIRE["reporting"]["retained_windows"]
        if type(week) is not int or not low <= week < current:
            self._prune_failures()
            return
        self._prune_failures()
        self._publication_failures = [item for item in self._publication_failures if item["window_week"] != week]
        self._publication_failures.append({"window_week": week, "state": "publication_failed"})
        recorder = getattr(self._publish, "record_publication_failure", None)
        if callable(recorder):
            with suppress(Exception):
                recorder(week)

    async def _boundaries(self):
        while True:
            now = self._clock()
            end = 345600 + (self._window.week + 1) * 604800
            await asyncio.sleep(max(0.05, min(3600, end - now)))
            with suppress(WireV3Error):
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
        if scope.get("path") == "/v3/report" and not scope.get("query_string"):
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
                        if type(chunk) is not bytes or len(body) + len(chunk) > PACKET_BYTES:
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
