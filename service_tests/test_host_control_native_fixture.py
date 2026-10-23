"""The installed-client peer uses real SSH/authority without a service worker."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import sys
from uuid import uuid4

import asyncssh
import pytest

from mnemion.host_control.protocol import canonical, parse
from mnemion.host_control.transport import Connection, call


def test_node_native_peer_enrolls_public_keys_and_retains_queued_work(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("The native desktop gate supplies Node")
    source = Path(__file__).resolve().parents[1]
    helper = source / "studio/electron/scripts/host-control-fixture.mjs"
    script = """
      const {hostControlFixture} = await import(process.argv[1]);
      const peer = hostControlFixture(JSON.parse(process.argv[2]));
      try {
        console.log(JSON.stringify(await peer.enroll(JSON.parse(process.argv[3]))));
        await new Promise(resolve => { process.stdin.once('data', resolve); process.stdin.once('end', resolve) });
      } finally { await peer.close() }
    """

    async def exercise():
        key = asyncssh.generate_private_key("ssh-ed25519")
        peer = await asyncio.create_subprocess_exec(
            node,
            "--input-type=module",
            "-e",
            script,
            helper.as_uri(),
            json.dumps(
                {"python": sys.executable, "root": str(tmp_path / "peer"), "cwd": str(source)}
            ),
            json.dumps(
                {
                    "name": "Actual native client fixture",
                    "public_key": key.export_public_key().decode().strip(),
                    "role": "operator",
                    "expires_at": None,
                }
            ),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=source,
        )
        try:
            line = await asyncio.wait_for(peer.stdout.readline(), 20)
            connection = Connection.model_validate_json(line)

            def request(action, **fields):
                now = datetime.now(timezone.utc)
                return parse(
                    canonical(
                        {
                            "protocol": 1,
                            "host_id": str(connection.host_id),
                            "request_id": str(uuid4()),
                            "action": action,
                            **(
                                {
                                    "issued_at": now.isoformat(),
                                    "valid_until": (now + timedelta(minutes=5)).isoformat(),
                                }
                                if action == "service.stop"
                                else {}
                            ),
                            **fields,
                        }
                    )
                )

            async def send(value):
                return await call(connection, key.export_private_key(), value, timeout=5)

            status = await send(request("host.status"))
            assert status["ok"] and status["result"]["operator"]["role"] == "operator"
            assert status["result"]["service"]["native_transport_fixture"]
            assert not status["result"]["service"]["running"]
            stop = request("service.stop", approve_service_interruption=True)
            accepted = await send(stop)
            assert accepted["ok"] and accepted["result"]["phase"] == "queued"
            inspected = await send(request("operations.get", operation_id=str(stop.request_id)))
            assert inspected["ok"] and inspected["result"]["phase"] == "queued"
            denied = await send(request("operators.list"))
            assert not denied["ok"] and denied["error"]["code"] == "host_access_denied"
            assert b"PRIVATE KEY" not in line
        finally:
            peer.stdin.write(b"close\n")
            await peer.stdin.drain()
            peer.stdin.close()
            try:
                await asyncio.wait_for(peer.wait(), 10)
            except TimeoutError:
                peer.kill()
                await peer.wait()
        assert peer.returncode == 0

    asyncio.run(exercise())
