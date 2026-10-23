"""Qualify a frozen key-only host client before packaging long desktop journeys.

The loopback peer is disposable, contains no memory service and executes no
service effects. Generated private key material only crosses the engine pipe.
"""

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import uuid4

import asyncssh

from deploy.native_host_control_fixture import fixture_store
from mnemion import local_state
from mnemion.host_control.protocol import canonical, parse
from mnemion.host_control.server import listen
from mnemion.host_control.transport import Connection


async def probe(binary: Path, root: Path):
    async def engine(value):
        process = await asyncio.create_subprocess_exec(
            str(binary),
            "desktop-host",
            "--root",
            str(root / "unused-desktop-profile"),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(canonical(value)), 30)
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        if len(stdout) > 512 * 1024:
            raise ValueError("The frozen host client exceeded its response budget")
        try:
            result = json.loads(stdout)
        except (ValueError, UnicodeDecodeError):
            raise ValueError("The frozen host client returned no bounded JSON reply") from None
        if not isinstance(result, dict) or result.get("event") != "result":
            raise ValueError("The frozen host client returned an invalid envelope")
        return process.returncode, result

    code, generated = await engine({"operation": "keygen"})
    if code or generated.get("ok") is not True:
        raise ValueError("The frozen host client could not create its own operator key")
    key = generated["result"]
    store, host_id, owner_id = fixture_store(root / "peer")
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
                    "valid_until": (now + timedelta(minutes=5)).isoformat(),
                    "expected_revision": 1,
                    "operator": {
                        "name": "Disposable frozen-engine operator",
                        "public_key": key["public_key"],
                        "role": "operator",
                    },
                }
            )
        ),
    )
    host_key = asyncssh.generate_private_key("ssh-ed25519")
    async with listen(
        store,
        host_key.export_private_key(),
        port=0,
        host_status=lambda: {"running": False, "ready": False, "frozen_client_fixture": True},
    ) as listener:
        connection = Connection(
            host_id=host_id,
            operator_id=grant["operator_id"],
            hostname="127.0.0.1",
            port=listener.get_port(),
            host_key_fingerprint=host_key.get_fingerprint("sha256"),
            operator_key_fingerprint=grant["fingerprint"],
        )
        value = {
            "operation": "inspect",
            "connection": connection.model_dump(mode="json"),
            "private_key": key["private_key"],
            "request": {
                "protocol": 1,
                "host_id": host_id,
                "request_id": str(uuid4()),
                "action": "host.status",
            },
        }
        code, inspected = await engine(value)
        if code or inspected.get("ok") is not True:
            # Only public error codes may leave the private engine pipe.
            error = inspected.get("error")
            suffix = error if isinstance(error, str) and error.isidentifier() else "invalid_reply"
            raise ValueError(f"The frozen host client failed its pinned SSH inspection: {suffix}")
        result = inspected["result"]
        if (
            not result["status"]["ok"]
            or not result["history"]["ok"]
            or result["status"]["result"]["operator"]["role"] != "operator"
            or result["status"]["result"]["service"]["running"]
        ):
            raise ValueError("The frozen host client did not inspect the expected offline peer")
        value["connection"]["host_key_fingerprint"] = asyncssh.generate_private_key(
            "ssh-ed25519"
        ).get_fingerprint("sha256")
        code, refused = await engine(value)
        if (
            code != 2
            or refused.get("ok") is not False
            or refused.get("error") != "host_identity_changed"
        ):
            raise ValueError("The frozen host client did not reject a changed host identity")
    return {
        "pinned_inspection": True,
        "changed_identity_refused": True,
        "service_effects_executed": False,
    }


def run(binary: Path):
    with local_state.temporary_directory(prefix="mnemion-frozen-host-client-") as temporary:
        return asyncio.run(probe(binary.resolve(), temporary))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.engine)))


if __name__ == "__main__":
    main()
