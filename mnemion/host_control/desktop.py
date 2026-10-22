"""Private, bounded engine pipe for Studio's OS-protected host identities."""

import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4

import asyncssh

from . import HostControlError
from .protocol import MAX_REQUEST, canonical, parse
from .transport import Connection, call


def arguments(parser):
    parser.add_argument("--root", required=True, type=Path)


def execute(raw):
    if not raw or len(raw) > 65536:
        raise HostControlError("invalid_request", "The private host request exceeds its bound.")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Invalid request")
    if value == {"operation": "schema"}:
        from .protocol import REQUEST, ROLES

        return {
            "request": REQUEST.json_schema(),
            "connection": Connection.model_json_schema(),
            "roles": {role: sorted(actions) for role, actions in ROLES.items()},
        }
    if value == {"operation": "keygen"}:
        key = asyncssh.generate_private_key("ssh-ed25519")
        # Only the trusted desktop main process receives this private pipe.
        return {
            "private_key": key.export_private_key().decode("ascii"),
            "public_key": key.export_public_key().decode("ascii").strip(),
            "fingerprint": key.get_fingerprint("sha256"),
        }
    if value.get("operation") not in {"validate", "call", "inspect"} or set(value) != {
        "operation",
        "connection",
        "private_key",
        "request",
    }:
        raise ValueError("Invalid operation")
    if not isinstance(value["private_key"], str) or len(value["private_key"]) > 8192:
        raise ValueError("Invalid key")
    connection = Connection.model_validate(value["connection"])
    request = parse(canonical(value["request"]))
    if len(canonical(value["request"])) > MAX_REQUEST or request.host_id != connection.host_id:
        raise ValueError("Invalid request identity")
    key = asyncssh.import_private_key(value["private_key"].encode("ascii"))
    if (
        key.get_algorithm() != "ssh-ed25519"
        or key.get_fingerprint("sha256") != connection.operator_key_fingerprint
    ):
        raise HostControlError("invalid_operator_key", "This enrollment uses another operator key.")
    if value["operation"] == "validate":
        return {
            "connection": connection.model_dump(mode="json"),
            "request": request.model_dump(mode="json"),
        }
    if value["operation"] == "inspect":
        if request.action not in {"host.status", "operations.get"}:
            raise ValueError("Inspection only accepts a status or receipt lookup")

        async def inspect():
            base = {"protocol": 1, "host_id": str(connection.host_id)}

            async def read(action, **fields):
                selected = parse(
                    canonical({**base, "request_id": str(uuid4()), "action": action, **fields})
                )
                return await call(
                    connection, value["private_key"].encode("ascii"), selected, timeout=20
                )

            status = await read("host.status")
            if not status["ok"]:
                return {"status": status, "history": None, "operation": None}
            history = await read("operations.list", limit=25)
            operation = (
                await call(connection, value["private_key"].encode("ascii"), request, timeout=20)
                if request.action == "operations.get"
                else None
            )
            return {"status": status, "history": history, "operation": operation}

        async def bounded_inspect():
            async with asyncio.timeout(23):
                return await inspect()

        return asyncio.run(bounded_inspect())
    return asyncio.run(call(connection, value["private_key"].encode("ascii"), request, timeout=20))


def dispatch(args):
    try:
        result = execute(sys.stdin.buffer.read(65537))
        print(
            json.dumps({"event": "result", "ok": True, "result": result}, allow_nan=False),
            flush=True,
        )
        return 0
    except Exception as error:
        code = error.code if isinstance(error, HostControlError) else "invalid_request"
        print(json.dumps({"event": "result", "ok": False, "error": code}), flush=True)
        return 2
