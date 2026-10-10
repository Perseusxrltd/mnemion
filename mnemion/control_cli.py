"""Agent CLI: discover API operations, validate a request and make one bounded call."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urlsplit

from .agent_control import (
    ControlError,
    DOWNLOAD_LIMIT,
    INPUT_LIMIT,
    catalog,
    describe,
    execute,
    prepare,
)
from .private_output import private_output
from .sdk import Client


def _json(data: bytes):
    def invalid(_):
        raise ValueError("Use finite JSON values")

    try:
        return json.loads(data, parse_constant=invalid)
    except (ValueError, UnicodeError, RecursionError):
        raise ControlError("invalid_json", "Use a valid finite JSON document") from None


def _read(path: Path, maximum: int) -> bytes:
    descriptor = os.open(
        path.expanduser(), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise ControlError("invalid_file", "Use a bounded regular input file")
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise ControlError("input_too_large", "The input exceeds the supported size")
    return value


def connection(credentials: Path | None, url: str | None) -> tuple[str, str]:
    saved = _json(_read(credentials, 16384)) if credentials else {}
    if not isinstance(saved, dict):
        raise ControlError("invalid_credentials", "Use a private credentials JSON object")
    address = (
        url or saved.get("api_url") or os.environ.get("MNEMION_API_URL", "http://127.0.0.1:7892")
    )
    key = saved.get("api_key") or os.environ.get("MNEMION_API_KEY")
    if not isinstance(key, str) or not re.fullmatch(r"[\x21-\x7e]{1,4096}", key):
        raise ControlError(
            "missing_credentials",
            "Set MNEMION_API_KEY or use --credentials; never put keys in command arguments",
        )
    try:
        if not isinstance(address, str) or len(address) > 2048:
            raise ValueError()
        parsed = urlsplit(address)
        parsed.port
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or (
                parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            )
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(ord(char) <= 32 or ord(char) >= 127 for char in address)
        ):
            raise ValueError()
    except ValueError:
        raise ControlError(
            "invalid_api_url",
            "Use a public HTTPS API address or loopback HTTP without credentials, query or fragment",
        ) from None
    return address.rstrip("/").removesuffix("/v1"), key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mnemion-control", description=__doc__)
    parser.add_argument(
        "--credentials", type=Path, help="Private JSON containing api_url and api_key"
    )
    parser.add_argument("--url", help="API address; otherwise use credentials or MNEMION_API_URL")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser(
        "catalog", help="Discover installed operations without a connection"
    )
    listing.add_argument("--group")
    listing.add_argument("--query")
    listing.add_argument("--offset", type=int, default=0)
    listing.add_argument("--limit", type=int, default=20)
    detail = commands.add_parser(
        "describe", help="Get one operation's complete input/output schema"
    )
    detail.add_argument("operation")
    call = commands.add_parser("call", help="Validate and execute one named API operation")
    call.add_argument("operation")
    call.add_argument("--input", type=Path, help="JSON envelope file; use - for standard input")
    call.add_argument(
        "--output", type=Path, help="New private file for a binary/download operation"
    )
    call.add_argument(
        "--result-file",
        type=Path,
        help="New private JSON result file; required when creating API keys",
    )
    call.add_argument(
        "--max-response-bytes", type=int, help="Default: 64 KiB JSON or 1 GiB streamed download"
    )
    call.add_argument(
        "--retries",
        type=int,
        choices=range(6),
        default=2,
        help="Retries of reads or explicitly idempotent writes only",
    )
    args = parser.parse_args(argv)
    dispatched = False
    try:
        if args.command == "catalog":
            result = catalog(
                group=args.group, query=args.query, offset=args.offset, limit=args.limit
            )
        elif args.command == "describe":
            result = describe(args.operation)
        else:
            raw = b"{}"
            if args.input:
                raw = (
                    sys.stdin.buffer.read(INPUT_LIMIT + 1)
                    if str(args.input) == "-"
                    else _read(args.input, INPUT_LIMIT)
                )
            if len(raw) > INPUT_LIMIT:
                raise ControlError("input_too_large", "The request exceeds the 2 MB API limit")
            request = _json(raw)
            operation, _ = prepare(args.operation, request)
            if operation["download"] != bool(args.output) or (args.output and args.result_file):
                raise ControlError(
                    "invalid_output",
                    "Use --output only for downloads and --result-file only for JSON results",
                )
            if operation["sensitive_result"] and not args.result_file:
                raise ControlError(
                    "private_result_required",
                    "This operation requires --result-file; newly issued credentials are never printed",
                )
            address, key = connection(args.credentials, args.url)
            destination = args.output or args.result_file
            maximum = (
                args.max_response_bytes
                if args.max_response_bytes is not None
                else (DOWNLOAD_LIMIT if args.output else 65536)
            )
            with private_output(destination) if destination else nullcontext(None) as output:
                with Client(address, key, retries=args.retries) as client:
                    dispatched = True
                    result = execute(
                        client,
                        args.operation,
                        request,
                        max_response_bytes=maximum,
                        output=output if args.output else None,
                    )
                if args.result_file:
                    stored = result
                    if operation["sensitive_result"]:
                        issued = result["result"]
                        if not isinstance(issued, dict) or not isinstance(
                            issued.get("api_key"), str
                        ):
                            raise ControlError(
                                "invalid_response",
                                "The key response was invalid; inspect issued keys before retrying",
                                outcome="unknown",
                            )
                        # Newly issued files can be used directly by mnemion-agent,
                        # mnemion-service and this CLI without printing/copying keys.
                        stored = {**issued, "api_url": address}
                    output.write((json.dumps(stored, allow_nan=False) + "\n").encode())
                    result = {key: value for key, value in result.items() if key != "result"}
                if destination:
                    result["output_file"] = str(destination.expanduser().absolute())
        print(json.dumps(result, allow_nan=False))
        return 0
    except ControlError as error:
        result = {
            "error": {
                "code": error.code,
                "message": str(error),
                "status": error.status,
                "outcome": error.outcome,
                "retryable": error.retryable,
                "retry_after_seconds": error.retry_after,
            },
            "request_id": error.request_id,
        }
    except (OSError, ValueError):
        result = {
            "error": {
                "code": "local_io_error",
                "message": "The local input, connection or output could not be used; existing files are never replaced",
                "outcome": "unknown" if dispatched else "not_sent",
            }
        }
    print(json.dumps(result))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
