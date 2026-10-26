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
    if action in {"status", "schema", "preview", "review_status"}:
        if set(request) != {"action"}:
            raise policy.PolicyError("telemetry_invalid_request")
        if action == "schema":
            from .catalog import (
                control_specification,
                coverage_specification,
                origin_specification,
                specification,
            )
            from .wire import specification as wire_specification

            return {
                "protocol": 1,
                "actions": {
                    "status": {"mutation": False, "fields": []},
                    "schema": {"mutation": False, "fields": []},
                    "preview": {"mutation": False, "fields": []},
                    "review_status": {"mutation": False, "fields": []},
                    **{
                        name: {
                            "mutation": True,
                            "fields": [
                                "expected_revision",
                                "expected_generation",
                                "expected_review_token",
                            ]
                            + (["mode"] if name == "review_mode" else []),
                        }
                        for name in (
                            "review_mode",
                            "inspect_report",
                            "approve_report",
                            "discard_report",
                        )
                    },
                    "configure": {
                        "mutation": True,
                        "fields": [
                            "enabled",
                            "expected_revision",
                            "expected_generation",
                            "disclosure_version",
                            "connection_mode",
                        ],
                        "connection_modes": list(policy.CONNECTION_MODES),
                    },
                },
                "disclosure": policy.disclosure(),
                "measurement_catalog": specification(),
                "owned_control_coverage": control_specification(),
                "owned_origin_coverage": origin_specification(),
                "workflow_coverage": coverage_specification(),
                "transport_available": policy.transport_available(),
                "transport_catalog": wire_specification(),
                "report_review": {
                    "modes": ["automatic", "review"],
                    "maximum_lifetime_seconds": 900,
                    "requires_collection_permission": True,
                    "approval_sends_immediately": False,
                    "expiry_resumes_automatic_delivery": False,
                    "interactive_privacy_qualified": False,
                },
            }
        if action == "review_status":
            from .inspection import status

            return status(root)
        return policy.preview(root) if action == "preview" else policy.status(root)
    if action == "configure":
        return policy.configure(
            root, {key: value for key, value in request.items() if key != "action"}
        )
    if action in {"review_mode", "inspect_report", "approve_report", "discard_report"}:
        from .inspection import execute

        return execute(
            root, action, {key: value for key, value in request.items() if key != "action"}
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
