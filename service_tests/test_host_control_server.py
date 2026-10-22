"""Real production SSH listener: authority, protocol bounds and lost replies."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
import os
import struct
import threading
from uuid import uuid4

import asyncssh
import pytest

from mnemion.host_control import HostControlError, server as server_module
from mnemion.host_control.protocol import MAX_REQUEST, Operator, canonical, parse
from mnemion.host_control.server import listen
from mnemion.host_control.store import Store
from mnemion.host_control.transport import COMMAND, Connection, call

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Managed hosts require Unix")


def request(connection, action="host.status", **fields):
    now = datetime.now(timezone.utc)
    lifetime = (
        {}
        if action in {"host.status", "operators.list", "operations.get", "operations.list"}
        else {
            "issued_at": now.isoformat(),
            "valid_until": (now + timedelta(minutes=30)).isoformat(),
        }
    )
    return parse(
        canonical(
            {
                "protocol": 1,
                "host_id": str(connection.host_id),
                "request_id": str(uuid4()),
                "action": action,
                **lifetime,
                **fields,
            }
        )
    )


@asynccontextmanager
async def host(tmp_path):
    host_key = asyncssh.generate_private_key("ssh-ed25519")
    operator_key = asyncssh.generate_private_key("ssh-ed25519")
    service = tmp_path / "managed-service"
    service.mkdir(mode=0o700)
    store, ids = Store.adopt(
        tmp_path / "host-control",
        service,
        "isolated-service",
        Operator(
            name="Independent owner",
            role="custodian",
            public_key=operator_key.export_public_key().decode().strip(),
        ),
    )
    async with listen(store, host_key.export_private_key("openssh"), port=0) as listener:
        connection = Connection(
            **{name: ids[name] for name in ("host_id", "operator_id")},
            hostname="127.0.0.1",
            port=listener.get_port(),
            host_key_fingerprint=host_key.get_fingerprint("sha256"),
            operator_key_fingerprint=operator_key.get_fingerprint("sha256"),
        )
        yield store, connection, host_key, operator_key


def ssh(connection, host_key, operator_key):
    return asyncssh.connect(
        connection.hostname,
        port=connection.port,
        username="mnemion",
        config=None,
        known_hosts=([host_key.convert_to_public()], [], []),
        client_keys=[operator_key],
        agent_path=None,
        encoding=None,
    )


def frame(request):
    raw = canonical(request.model_dump(mode="json"))
    return struct.pack("!I", len(raw)) + raw


def test_production_listener_authenticates_without_the_memory_api(tmp_path):
    async def exercise():
        async with host(tmp_path) as (_, connection, _, key):
            result = await call(connection, key.export_private_key("openssh"), request(connection))
            assert result["ok"]
            assert result["result"]["operator"]["role"] == "custodian"
            assert result["result"]["operator"]["id"] == str(connection.operator_id)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "operation", ["shell", "command", "pty", "sftp", "forward", "reverse_forward"]
)
def test_production_listener_refuses_shell_files_and_forwarding(tmp_path, operation):
    async def exercise():
        async with host(tmp_path) as (_, connection, host_key, key):
            reached = asyncio.Event()

            async def target(reader, writer):
                reached.set()
                writer.close()
                await writer.wait_closed()

            async with await asyncio.start_server(target, "127.0.0.1", 0) as endpoint:
                port = endpoint.sockets[0].getsockname()[1]
                async with ssh(connection, host_key, key) as connected:
                    expected = (
                        asyncssh.ChannelListenError
                        if operation == "reverse_forward"
                        else asyncssh.Error
                    )
                    with pytest.raises(expected):
                        if operation == "shell":
                            await connected.create_process()
                        elif operation == "command":
                            await connected.create_process("unrequested-command")
                        elif operation == "pty":
                            await connected.create_process(COMMAND, term_type="xterm")
                        elif operation == "sftp":
                            await connected.start_sftp_client()
                        elif operation == "forward":
                            await connected.open_connection("127.0.0.1", port)
                        else:
                            await connected.forward_remote_port("127.0.0.1", 0, "127.0.0.1", port)
                    assert not reached.is_set()

    asyncio.run(exercise())


def test_remote_environment_is_not_retained_by_the_control_channel(tmp_path, monkeypatch):
    observed = []
    original = server_module.Receiver.eof_received

    def inspect_channel(self):
        observed.append(self.channel.get_environment())
        return original(self)

    monkeypatch.setattr(server_module.Receiver, "eof_received", inspect_channel)

    async def exercise():
        async with host(tmp_path) as (_, connection, host_key, key):
            async with ssh(connection, host_key, key) as connected:
                result = await connected.run(
                    COMMAND,
                    input=frame(request(connection)),
                    env={"PRIVATE_SENTINEL": "unrequested-value"},
                    encoding=None,
                )
                assert result.exit_status == 0
                assert observed == [{}]
                assert b"PRIVATE_SENTINEL" not in result.stdout

    asyncio.run(exercise())


def test_oversized_frame_is_refused_without_queuing_work(tmp_path):
    async def exercise():
        async with host(tmp_path) as (store, connection, host_key, key):
            async with ssh(connection, host_key, key) as connected:
                result = await connected.run(
                    COMMAND, input=struct.pack("!I", MAX_REQUEST + 1), encoding=None
                )
                assert result.exit_status == 2
                assert not result.stdout and not result.stderr
            assert store.claim() is None

    asyncio.run(exercise())


def test_revocation_applies_to_an_already_authenticated_connection(tmp_path):
    async def exercise():
        async with host(tmp_path) as (store, connection, host_key, owner_key):
            key = asyncssh.generate_private_key("ssh-ed25519")
            enrolled = store.grant(
                connection.operator_id,
                request(
                    connection,
                    "operators.grant",
                    expected_revision=1,
                    operator=Operator(
                        name="On call",
                        role="operator",
                        public_key=key.export_public_key().decode().strip(),
                    ).model_dump(mode="json"),
                ),
            )
            delegated = Connection(
                **{
                    **connection.model_dump(mode="json"),
                    "operator_id": enrolled["operator_id"],
                    "operator_key_fingerprint": key.get_fingerprint("sha256"),
                }
            )
            async with ssh(delegated, host_key, key) as connected:
                store.revoke(
                    connection.operator_id,
                    request(
                        connection,
                        "operators.revoke",
                        expected_revision=2,
                        operator_id=enrolled["operator_id"],
                    ),
                )
                result = await connected.run(
                    COMMAND,
                    input=frame(
                        request(delegated, "service.stop", approve_service_interruption=True)
                    ),
                    encoding=None,
                )
                body = json.loads(result.stdout[4:])
                assert body["ok"] is False and body["error"]["code"] == "host_access_denied"
            with pytest.raises(HostControlError) as error:
                await call(delegated, key.export_private_key("openssh"), request(delegated))
            assert error.value.code == "host_access_denied"
            assert store.claim() is None

    asyncio.run(exercise())


def test_disconnect_after_durable_intent_reconnects_without_duplicate_work(tmp_path, monkeypatch):
    committed, release = threading.Event(), threading.Event()
    original = server_module.dispatch

    def interrupted_reply(*args):
        result = original(*args)
        committed.set()
        release.wait(3)
        return result

    monkeypatch.setattr(server_module, "dispatch", interrupted_reply)

    async def exercise():
        async with host(tmp_path) as (store, connection, _, key):
            action = request(connection, "service.stop", approve_service_interruption=True)
            task = asyncio.create_task(call(connection, key.export_private_key("openssh"), action))
            try:
                assert await asyncio.wait_for(asyncio.to_thread(committed.wait, 2), 3)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                release.set()
            reply = await call(connection, key.export_private_key("openssh"), action)
            assert reply["result"]["operation_id"] == str(action.request_id)
            with store.transaction() as conn:
                assert conn.execute("SELECT count(*) FROM operations").fetchone()[0] == 1

    asyncio.run(exercise())
