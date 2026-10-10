"""Reject slow or oversized transports before parsing or running an API handler."""

import asyncio
import json

from mnemion.service.api import BodyLimitMiddleware


def request(receive, *, headers=(), timeout=0.03, limit=32):
    messages, delivered = [], []

    async def app(scope, incoming, send):
        delivered.append(await incoming())

    async def send(message):
        messages.append(message)

    asyncio.run(
        BodyLimitMiddleware(app, limit=limit, timeout=timeout)(
            {"type": "http", "headers": headers}, receive, send
        )
    )
    return messages, delivered


def test_declared_oversize_does_not_wait_for_a_body():
    async def receive():
        raise AssertionError("The oversized request must not be read")

    messages, delivered = request(receive, headers=[(b"content-length", b"1000000")])
    assert messages[0]["status"] == 413 and delivered == []


def test_slow_incomplete_body_expires_before_handler_runs():
    calls = 0

    async def receive():
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"type": "http.request", "body": b"a", "more_body": True}
        await asyncio.sleep(1)
        return {"type": "http.request", "body": b"b", "more_body": False}

    messages, delivered = request(receive)
    assert messages[0]["status"] == 408 and delivered == []
    assert json.loads(messages[1]["body"])["error"]["code"] == "body_timeout"


def test_many_small_chunks_are_delivered_once_and_cannot_exceed_the_limit():
    def chunks(count):
        async def receive():
            nonlocal count
            count -= 1
            return {"type": "http.request", "body": b"x", "more_body": count > 0}

        return receive

    messages, delivered = request(chunks(32))
    assert messages == [] and delivered == [
        {"type": "http.request", "body": b"x" * 32, "more_body": False}
    ]
    messages, delivered = request(chunks(33))
    assert messages[0]["status"] == 413 and delivered == []


def test_ambiguous_or_invalid_content_length_is_rejected_before_reading():
    async def receive():
        raise AssertionError("Ambiguous request framing must not be read")

    for headers in [
        [(b"content-length", b"-1")],
        [(b"content-length", b"2"), (b"content-length", b"3")],
    ]:
        messages, delivered = request(receive, headers=headers)
        assert messages[0]["status"] == 400 and delivered == []
