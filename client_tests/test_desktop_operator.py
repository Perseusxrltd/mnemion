import asyncio
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import struct
import sys
import tempfile
from uuid import uuid4

import pytest

from mnemion import desktop_operator as control
from mnemion.private_input import read_private


def record(address=None):
    session = str(uuid4())
    return {
        "format": 1,
        "session_id": session,
        "version": "4.5.0",
        "pid": os.getpid(),
        "address": address
        or (
            rf"\\.\pipe\mnemion-operator-{session}-{secrets.token_hex(16)}"
            if sys.platform == "win32"
            else "/tmp/mnemion-operator-abc123/control.sock"
        ),
        "credential": secrets.token_hex(32),
    }


@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_discovery_accepts_only_local_os_pipes(monkeypatch, platform):
    monkeypatch.setattr(control.sys, "platform", platform)
    if platform != "win32":
        # A simulated Unix endpoint needs Unix pathname semantics even when
        # this format-validation test runs on a native Windows interpreter.
        monkeypatch.setattr(control, "Path", PurePosixPath)
    value = record()
    assert control.endpoint(value)["session_id"] == value["session_id"]
    for address in [
        "https://memory.example.invalid/control",
        "127.0.0.1:7892",
        r"\\remote\pipe\mnemion-operator",
        "relative/control.sock",
    ]:
        with pytest.raises(ValueError, match="private local pipe"):
            control.endpoint({**value, "address": address})


def test_live_process_discovery_is_never_overwritten_even_without_a_responsive_pipe(tmp_path):
    directory = tmp_path.resolve() / "mnemion-desktop-control"
    original = record()
    control.publish_request(
        json.dumps({"directory": str(directory), "endpoint": original}).encode()
    )
    before = read_private(directory / "endpoint.json")
    with pytest.raises(ValueError, match="already owns"):
        control.publish_request(
            json.dumps({"directory": str(directory), "endpoint": record()}).encode()
        )
    assert read_private(directory / "endpoint.json") == before


def test_dead_process_discovery_is_replaced_with_a_new_private_session(tmp_path, monkeypatch):
    directory = tmp_path.resolve() / "mnemion-desktop-control"
    control.publish_request(
        json.dumps({"directory": str(directory), "endpoint": record()}).encode()
    )
    monkeypatch.setattr(control, "_process_alive", lambda _: False)
    replacement = record()
    result = control.publish_request(
        json.dumps({"directory": str(directory), "endpoint": replacement}).encode()
    )
    assert result["protected"]
    assert (
        json.loads(read_private(directory / "endpoint.json"))["session_id"]
        == replacement["session_id"]
    )


@pytest.mark.skipif(
    sys.platform == "win32", reason="The native desktop gate exercises the real Windows pipe"
)
def test_partial_response_timeout_disconnects_the_operator_client():
    async def scenario(path):
        disconnected = asyncio.Event()

        async def peer(reader, writer):
            try:
                length = struct.unpack("!I", await reader.readexactly(4))[0]
                await reader.readexactly(length)
                writer.write(struct.pack("!I", 100))
                await writer.drain()
                assert await reader.read() == b""
                disconnected.set()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_unix_server(peer, path)
        async with server:
            with pytest.raises(asyncio.TimeoutError):
                await control.call(
                    record(str(path)), control.request_document({"action": "status"}), 0.1
                )
            await asyncio.wait_for(disconnected.wait(), 2)

    with tempfile.TemporaryDirectory(
        prefix="mnmo-", dir=Path(tempfile.gettempdir()).resolve()
    ) as temporary:
        asyncio.run(scenario(Path(temporary) / "control.sock"))


@pytest.mark.skipif(
    sys.platform == "win32", reason="The native desktop gate exercises the real Windows pipe"
)
def test_response_must_match_the_request_and_desktop_session():
    async def scenario(path):
        async def peer(reader, writer):
            try:
                length = struct.unpack("!I", await reader.readexactly(4))[0]
                request = json.loads(await reader.readexactly(length))
                body = json.dumps(
                    {
                        "protocol": 1,
                        "session_id": str(uuid4()),
                        "request_id": request["request_id"],
                        "ok": True,
                        "result": {},
                    }
                ).encode()
                writer.write(struct.pack("!I", len(body)) + body)
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_unix_server(peer, path)
        async with server:
            with pytest.raises(ValueError, match="did not match"):
                await control.call(
                    record(str(path)), control.request_document({"action": "status"}), 2
                )

    with tempfile.TemporaryDirectory(
        prefix="mnmo-", dir=Path(tempfile.gettempdir()).resolve()
    ) as temporary:
        asyncio.run(scenario(Path(temporary) / "control.sock"))
