"""Agent CLI: discover API operations, validate a request and make one bounded call."""

from __future__ import annotations

import argparse
import asyncio
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
from .private_input import read_private
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


def connection(
    credentials: Path | None, url: str | None, *, require_key: bool = True
) -> tuple[str, str | None]:
    saved = _json(_read(credentials, 16384)) if credentials else {}
    if not isinstance(saved, dict):
        raise ControlError("invalid_credentials", "Use a private credentials JSON object")
    address = (
        url or saved.get("api_url") or os.environ.get("MNEMION_API_URL", "http://127.0.0.1:7892")
    )
    key = saved.get("api_key") or os.environ.get("MNEMION_API_KEY")
    if (key is not None or require_key) and (
        not isinstance(key, str) or not re.fullmatch(r"[\x21-\x7e]{1,4096}", key)
    ):
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
            or "\\" in address
            or any(ord(char) <= 32 or ord(char) >= 127 for char in address)
        ):
            raise ValueError()
    except ValueError:
        raise ControlError(
            "invalid_api_url",
            "Use a public HTTPS API address or loopback HTTP without credentials, query or fragment",
        ) from None
    base = address.rstrip("/")
    if base.endswith(("/v1", "/mcp")):
        base = base.rsplit("/", 1)[0]
    return base, key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mnemion-control", description=__doc__)
    parser.add_argument(
        "--credentials", type=Path, help="Private JSON containing api_url and api_key"
    )
    parser.add_argument("--url", help="API address; otherwise use credentials or MNEMION_API_URL")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "doctor", help="Read-only health, access and MCP checks; outputs a content-free JSON report"
    )
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
        help="New private JSON result file; required for passwords, invitations and issued credentials",
    )
    call.add_argument(
        "--max-response-bytes",
        type=int,
        help="Default: 64 KiB JSON, 2 MB private vault result or 1 GiB streamed download",
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
    measurement = None
    try:
        if args.command == "doctor":
            from .connection_diagnostics import diagnose

            address, key = connection(args.credentials, args.url, require_key=False)
            result = asyncio.run(diagnose(address, key))
            print(json.dumps(result, allow_nan=False))
            return 0 if result["ready"] else 1
        elif args.command == "catalog":
            result = catalog(
                group=args.group, query=args.query, offset=args.offset, limit=args.limit
            )
        elif args.command == "describe":
            result = describe(args.operation)
        else:
            classification = describe(args.operation)
            raw = b"{}"
            if classification["sensitive_input"] and (not args.input or str(args.input) == "-"):
                raise ControlError(
                    "private_input_required",
                    "Use --input with an owner-only credential file; never put passwords or tokens in command arguments or transcripts",
                )
            if args.input:
                raw = (
                    sys.stdin.buffer.read(INPUT_LIMIT + 1)
                    if str(args.input) == "-"
                    else read_private(
                        args.input,
                        maximum=INPUT_LIMIT if args.operation.startswith("vault.") else 65536,
                    )
                    if classification["sensitive_input"]
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
            address, key = connection(
                args.credentials, args.url, require_key=operation["authentication"] == "bearer"
            )
            if operation["authentication"] != "bearer":
                key = None
            destination = args.output or args.result_file
            maximum = (
                args.max_response_bytes
                if args.max_response_bytes is not None
                else DOWNLOAD_LIMIT
                if args.output
                else INPUT_LIMIT
                if args.result_file
                and args.operation.startswith("vault.")
                and operation["sensitive_result"]
                else 65536
            )
            with private_output(destination) if destination else nullcontext(None) as output:
                with Client(address, key, retries=args.retries) as client:
                    try:
                        from . import control_measurement

                        measurement = control_measurement.begin(args.operation, request)
                    except Exception:
                        # A broken optional measurement installation must not
                        # prevent the requested memory or administrative action.
                        measurement = None
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
                        if not isinstance(issued, dict) or (
                            args.operation == "keys.create"
                            and not isinstance(issued.get("api_key"), str)
                        ):
                            raise ControlError(
                                "invalid_response",
                                "The credential response was invalid; inspect account access before retrying",
                                outcome="unknown",
                            )
                        # Newly issued files can be used directly by mnemion-agent,
                        # mnemion-service and this CLI without printing/copying keys.
                        stored = (
                            issued
                            if args.operation.startswith("vault.")
                            else {**issued, "api_url": address}
                        )
                        if args.operation in {
                            "sign_in.login",
                            "sign_in.refresh",
                            "sign_in.accept_invitation",
                            "company.finish",
                        }:
                            from .service.sign_in_api import SessionTokens

                            try:
                                tokens = SessionTokens.model_validate(issued)
                                if (
                                    tokens.persistence != "native"
                                    or not re.fullmatch(
                                        r"mnm_s_[A-Za-z0-9_-]{43}", tokens.access_token
                                    )
                                    or not isinstance(tokens.refresh_token, str)
                                    or not re.fullmatch(
                                        r"mnm_r_[A-Za-z0-9_-]{43}", tokens.refresh_token
                                    )
                                ):
                                    raise ValueError()
                            except ValueError:
                                raise ControlError(
                                    "invalid_response",
                                    "The session response was invalid; sign in again instead of replaying a refresh",
                                    outcome="unknown",
                                ) from None
                            stored = {
                                **tokens.model_dump(mode="json"),
                                "api_key": tokens.access_token,
                                "api_url": address,
                            }
                    output.write((json.dumps(stored, allow_nan=False) + "\n").encode())
                    result = {key: value for key, value in result.items() if key != "result"}
                if destination:
                    result["output_file"] = str(destination.expanduser().absolute())
        print(json.dumps(result, allow_nan=False))
        if measurement is not None:
            measurement.succeeded(result)
        return 0
    except ControlError as error:
        if measurement is not None:
            measurement.failed(code=error.code, status=error.status, outcome=error.outcome)
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
        if measurement is not None:
            measurement.failed(
                code="local_io_error", status=None, outcome="unknown" if dispatched else "not_sent"
            )
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
