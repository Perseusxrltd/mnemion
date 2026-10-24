"""Offline private-stdin telemetry controls; usable without a running desktop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import policy


def arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, help="Private installation telemetry folder")


def execute(root: Path | None, request: object) -> dict:
    if not isinstance(request, dict) or type(request.get("action")) is not str:
        raise policy.PolicyError("telemetry_invalid_request")
    action = request["action"]
    if action in {"status", "schema", "preview"}:
        if set(request) != {"action"}:
            raise policy.PolicyError("telemetry_invalid_request")
        if action == "schema":
            return {
                "protocol": 1,
                "actions": {
                    "status": {"mutation": False, "fields": []},
                    "schema": {"mutation": False, "fields": []},
                    "preview": {"mutation": False, "fields": []},
                    "configure": {
                        "mutation": True,
                        "fields": ["enabled", "expected_revision", "disclosure_version"],
                    },
                },
                "disclosure": policy.disclosure(),
            }
        return policy.preview(root) if action == "preview" else policy.status(root)
    if action == "configure":
        return policy.configure(
            root, {key: value for key, value in request.items() if key != "action"}
        )
    raise policy.PolicyError("telemetry_invalid_request")


def dispatch(args: argparse.Namespace) -> int:
    try:
        raw = sys.stdin.buffer.readline(policy.MAX_DOCUMENT_BYTES + 1)
        if len(raw) > policy.MAX_DOCUMENT_BYTES:
            raise policy.PolicyError("telemetry_invalid_request")
        request = json.loads(raw)
        result = execute(args.root, request)
        print(json.dumps({"event": "result", "ok": True, "result": result}, separators=(",", ":")))
        return 0
    except (ValueError, OSError, RecursionError) as error:
        code = error.code if isinstance(error, policy.PolicyError) else "telemetry_invalid_request"
        print(json.dumps({"event": "result", "ok": False, "error": code}, separators=(",", ":")))
        return 2
