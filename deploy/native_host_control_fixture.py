"""Disposable loopback SSH peer for the installed desktop-client gate.

This prepares a transport/authority fixture, never adopts or starts a memory
host. It can run on Windows to qualify the installed Windows client; it does
not claim Windows managed-host support. Only public enrollment crosses stdin.
"""

import argparse
import asyncio
from contextlib import AsyncExitStack
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

import asyncssh

from mnemion import local_state
from mnemion.private_output import private_output
from mnemion.host_control.protocol import Operator, canonical, parse, timestamp
from mnemion.host_control.server import listen
from mnemion.host_control.store import SCHEMA, Store
from mnemion.host_control.transport import Connection


def fixture_store(root):
    """Seed test rows without calling or relaxing OS-owner host adoption."""
    local_state.directory(root, exist_ok=False)
    service = local_state.directory(root / "absent-memory-service", exist_ok=False)
    authority = local_state.directory(root / "authority", exist_ok=False)
    owner = asyncssh.generate_private_key("ssh-ed25519")
    operator = Operator(
        name="Disposable fixture custodian",
        public_key=owner.export_public_key().decode().strip(),
        role="custodian",
    )
    host_id, operator_id = str(uuid4()), str(uuid4())
    path = authority / "authority.sqlite3"
    with private_output(path):
        pass
    with sqlite3.connect(path) as database:
        database.executescript(SCHEMA)
        database.execute(
            "INSERT INTO host(singleton,id,service_identity,service_state,created_at) VALUES(1,?,?,?,?)",
            (host_id, "native-transport-fixture", str(service), timestamp()),
        )
        Store._insert_operator(database, operator_id, operator)
    return Store(authority), host_id, operator_id


async def serve(root):
    local_state.directory(root, exist_ok=False)
    count = 0
    async with AsyncExitStack() as cleanup:
        while raw := await asyncio.to_thread(sys.stdin.buffer.readline, 8193):
            if len(raw) > 8192:
                raise ValueError("Fixture request exceeds its bound")
            request = json.loads(raw)
            if request == {"action": "close"}:
                return
            if not isinstance(request, dict) or set(request) != {"id", "operator"}:
                raise ValueError("Invalid fixture request")
            request_id = str(request["id"])
            if len(request_id) > 64 or not request_id.isalnum() or count >= 4:
                raise ValueError("Fixture request inventory exceeded")
            operator = Operator.model_validate(request["operator"])
            if operator.role != "operator" or operator.expires_at is not None:
                raise ValueError("The installed fixture grants the operator role only")
            store, host_id, owner_id = fixture_store(root / str(uuid4()))
            now = datetime.now(timezone.utc)
            grant = store.grant(
                owner_id,
                parse(
                    canonical(
                        {
                            "protocol": 1,
                            "host_id": host_id,
                            "request_id": str(uuid4()),
                            "action": "operators.grant",
                            "issued_at": now.isoformat(),
                            "valid_until": (now + timedelta(minutes=10)).isoformat(),
                            "expected_revision": 1,
                            "operator": operator.model_dump(mode="json"),
                        }
                    )
                ),
            )
            key = asyncssh.generate_private_key("ssh-ed25519")
            listener = await cleanup.enter_async_context(
                listen(
                    store,
                    key.export_private_key(),
                    port=0,
                    host_status=lambda: {
                        "running": False,
                        "ready": False,
                        "native_transport_fixture": True,
                        "service_effects_executed": False,
                    },
                )
            )
            connection = Connection(
                host_id=host_id,
                operator_id=grant["operator_id"],
                hostname="127.0.0.1",
                port=listener.get_port(),
                host_key_fingerprint=key.get_fingerprint("sha256"),
                operator_key_fingerprint=grant["fingerprint"],
            )
            count += 1
            print(
                json.dumps({"id": request_id, "connection": connection.model_dump(mode="json")}),
                flush=True,
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    try:
        asyncio.run(serve(args.root))
    except Exception:
        print("The disposable host-control transport fixture failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
