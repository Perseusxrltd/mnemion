"""Private same-account desktop control over an OS pipe, never the memory API."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
import json
import os
from pathlib import Path
import re
import struct
import sys
from uuid import UUID, uuid4

from . import local_state as state
from .private_input import read_private
from .private_output import private_output

MAX_REQUEST = 16 * 1024
MAX_RESPONSE = 256 * 1024
ENDPOINT_FILE = "endpoint.json"


def default_directory() -> Path:
    override = os.environ.get("MNEMION_STUDIO_USER_DATA")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "mnemion-desktop-control"


def _uuid(value: object) -> bool:
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except ValueError:
        return False


def endpoint(value: object) -> dict:
    fields = {"format", "session_id", "version", "pid", "address", "credential"}
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or type(value["format"]) is not int
        or value["format"] != 1
        or not _uuid(value["session_id"])
        or not isinstance(value["version"], str)
        or not re.fullmatch(r"\d{1,6}\.\d{1,6}\.\d{1,6}", value["version"])
        or type(value["pid"]) is not int
        or not 1 <= value["pid"] <= 2**32 - 1
        or not isinstance(value["credential"], str)
        or not re.fullmatch(r"[a-f0-9]{64}", value["credential"])
        or not isinstance(value["address"], str)
    ):
        raise ValueError("The desktop control record is invalid. Restart Mnemion Studio.")
    address = value["address"]
    if sys.platform == "win32":
        valid = re.fullmatch(r"\\\\\.\\pipe\\mnemion-operator-[a-f0-9-]{36}-[a-f0-9]{32}", address)
    else:
        valid = (
            Path(address).is_absolute()
            and len(os.fsencode(address)) < 104
            and Path(address).name == "control.sock"
            and re.fullmatch(r"mnemion-operator-[A-Za-z0-9]{6}", Path(address).parent.name)
        )
    if not valid:
        raise ValueError(
            "Use the desktop's private local pipe. Network addresses are not accepted."
        )
    return value


def _read_endpoint(directory: Path) -> dict:
    # The native writer uses the existing owner-only ACL implementation on Windows.
    # Reads verify actual ownership/permissions without silently repairing them.
    return endpoint(json.loads(read_private(directory / ENDPOINT_FILE, maximum=4096)))


def _process_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    # os.kill is not a harmless existence check on Windows.
    import ctypes as c
    from ctypes import wintypes as w

    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
    kernel.GetExitCodeProcess.argtypes = [w.HANDLE, c.POINTER(w.DWORD)]
    kernel.GetExitCodeProcess.restype = w.BOOL
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return c.get_last_error() not in {87, 1168}
    try:
        code = w.DWORD()
        return not kernel.GetExitCodeProcess(handle, c.byref(code)) or code.value == 259
    finally:
        kernel.CloseHandle(handle)


def request_document(value: object) -> dict:
    if not isinstance(value, dict) or set(value) - {
        "action",
        "request_id",
        "expected_workspace_id",
        "input",
    }:
        raise ValueError("Use an action, optional request_id, expected_workspace_id and input.")
    if not isinstance(value.get("action"), str) or not re.fullmatch(
        r"[a-z][a-z.-]{0,63}", value["action"]
    ):
        raise ValueError("Choose a documented desktop operation.")
    if "request_id" in value and not _uuid(value["request_id"]):
        raise ValueError("Use a UUID request_id.")
    if (
        "expected_workspace_id" in value
        and value["expected_workspace_id"] is not None
        and not _uuid(value["expected_workspace_id"])
    ):
        raise ValueError("Use the workspace identity returned by desktop status.")
    if not isinstance(value.get("input", {}), dict):
        raise ValueError("Operation input must be a JSON object.")
    return {
        **value,
        "request_id": value.get("request_id", str(uuid4())),
        "input": value.get("input", {}),
    }


async def call(record: dict, request: dict, timeout: float) -> dict:
    """One bounded exchange; disconnect cancels an operation's owned backup work."""

    async def exchange() -> dict:
        writer = None
        try:
            if sys.platform == "win32":
                loop = asyncio.get_running_loop()
                reader = asyncio.StreamReader(limit=MAX_RESPONSE + 4)
                protocol = asyncio.StreamReaderProtocol(reader)
                transport, _ = await loop.create_pipe_connection(
                    lambda: protocol, record["address"]
                )
                writer = asyncio.StreamWriter(transport, protocol, reader, loop)
            else:
                reader, writer = await asyncio.open_unix_connection(
                    record["address"], limit=MAX_RESPONSE + 4
                )
            body = json.dumps(
                {
                    "protocol": 1,
                    "session_id": record["session_id"],
                    "credential": record["credential"],
                    **request,
                },
                separators=(",", ":"),
            ).encode()
            if len(body) > MAX_REQUEST:
                raise ValueError("The desktop request exceeds 16 KiB.")
            writer.write(struct.pack("!I", len(body)) + body)
            await writer.drain()
            length = struct.unpack("!I", await reader.readexactly(4))[0]
            if not 1 <= length <= MAX_RESPONSE:
                raise ValueError("The desktop returned an oversized response.")
            result = json.loads(await reader.readexactly(length))
            if (
                not isinstance(result, dict)
                or result.get("protocol") != 1
                or result.get("session_id") != record["session_id"]
                or result.get("request_id") != request["request_id"]
                or type(result.get("ok")) is not bool
            ):
                raise ValueError("The desktop response did not match this request.")
            return result
        finally:
            if writer is not None:
                writer.close()
                try:
                    await asyncio.wait_for(writer.wait_closed(), 2)
                except (OSError, asyncio.TimeoutError):
                    pass

    return await asyncio.wait_for(exchange(), timeout)


def publish_request(raw: bytes) -> dict:
    """Native helper: publish discovery with the existing cross-platform private writer."""
    if len(raw) > MAX_REQUEST:
        raise ValueError("The desktop control record is too large.")
    value = json.loads(raw)
    if (
        not isinstance(value, dict)
        or set(value) != {"directory", "endpoint"}
        or not isinstance(value["directory"], str)
    ):
        raise ValueError("Use a private desktop control directory and endpoint.")
    directory = Path(value["directory"])
    if not directory.is_absolute() or directory.name != "mnemion-desktop-control":
        raise ValueError("Use the desktop's own control directory.")
    record = endpoint(value["endpoint"])
    directory = state.directory(directory)
    path = directory / ENDPOINT_FILE
    if path.exists():
        previous = _read_endpoint(directory)
        if _process_alive(previous["pid"]):
            raise ValueError(
                "A desktop already owns this control directory. Use its running instance."
            )
    state.write(path, record)
    # Fail the publication if the resulting actual ACL is not private.
    checked = _read_endpoint(directory)
    if checked != record:
        raise ValueError("Desktop control discovery changed during publication.")
    return {"format": 1, "session_id": record["session_id"], "protected": True}


def arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--control-directory",
        type=Path,
        default=None,
        help="Private desktop discovery directory; defaults to this OS account",
    )
    parser.add_argument(
        "--timeout", type=int, default=1800, help="Seconds to wait, from 1 to 14400"
    )
    parser.add_argument(
        "--result-file", type=Path, help="Create an owner-only JSON result instead of printing it"
    )


def dispatch(args: argparse.Namespace) -> int:
    try:
        if not 1 <= args.timeout <= 14400:
            raise ValueError("Use a timeout from 1 to 14400 seconds.")
        raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise ValueError("The desktop request exceeds 16 KiB.")
        request = request_document(json.loads(raw))
        if request["action"] in {"backup.key", "local.vault-key"} and not args.result_file:
            raise ValueError("Recovery keys require an owner-only result file.")
        with ExitStack() as stack:
            destination = (
                stack.enter_context(private_output(args.result_file)) if args.result_file else None
            )
            record = _read_endpoint(args.control_directory or default_directory())
            result = asyncio.run(call(record, request, args.timeout))
            if destination is not None:
                destination.write(json.dumps(result, ensure_ascii=True).encode() + b"\n")
    except (OSError, ValueError, RecursionError, asyncio.TimeoutError, asyncio.IncompleteReadError):
        # Private input, paths and credentials never become a raw traceback.
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "desktop_control_unavailable",
                    "message": "Desktop control could not complete. Start Mnemion Studio under this OS account, check the private control directory and request, then refresh status before retrying a change.",
                }
            )
        )
        return 1
    if args.result_file:
        print(
            json.dumps(
                {"ok": result["ok"], "request_id": result["request_id"], "result_saved": True}
            )
        )
    else:
        print(json.dumps(result, ensure_ascii=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    arguments(parser)
    raise SystemExit(dispatch(parser.parse_args()))
