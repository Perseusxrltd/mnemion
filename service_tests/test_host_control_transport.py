"""Real SSH exchanges verify host pins and durable reconnects without a memory API."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
import os
import struct
from uuid import uuid4

import asyncssh
import pytest

from mnemion.host_control import HostControlError
from mnemion.host_control.protocol import MAX_RESPONSE, Operator, canonical, parse
from mnemion.host_control.receiver import dispatch
from mnemion.host_control.store import Store
from mnemion.host_control.transport import COMMAND, Connection, call

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Managed hosts require Unix")


@asynccontextmanager
async def server(tmp_path, *, delay=0, oversized=False, wrong_request=False):
    host_key = asyncssh.generate_private_key("ssh-ed25519")
    user_key = asyncssh.generate_private_key("ssh-ed25519")
    service = tmp_path / "managed-service"
    service.mkdir(mode=0o700)
    store, identity = Store.adopt(
        tmp_path / "control",
        service,
        "existing-service",
        Operator(
            name="Independent custodian",
            role="custodian",
            public_key=user_key.export_public_key().decode().strip(),
        ),
    )
    observed = {"auth_calls": 0, "commands": [], "delay": delay, "tasks": set()}

    class Session(asyncssh.SSHServerSession):
        def connection_made(self, channel):
            self.channel = channel
            self.data = bytearray()

        def exec_requested(self, command):
            observed["commands"].append(command)
            return command == COMMAND

        def data_received(self, data, datatype):
            self.data.extend(data)
            if len(self.data) > 16388:
                self.channel.exit(1)

        def eof_received(self):
            async def reply():
                raw = bytes(self.data)
                assert struct.unpack("!I", raw[:4])[0] == len(raw) - 4
                body = dispatch(store, identity["operator_id"], raw[4:])
                if wrong_request:
                    value = json.loads(body)
                    value["request_id"] = str(uuid4())
                    body = canonical(value)
                if observed["delay"]:
                    await asyncio.sleep(observed["delay"])
                try:
                    self.channel.write(
                        struct.pack("!I", MAX_RESPONSE + 1 if oversized else len(body)) + body
                    )
                    self.channel.exit(0)
                except (BrokenPipeError, asyncssh.Error):
                    pass

            task = asyncio.create_task(reply())
            observed["tasks"].add(task)
            task.add_done_callback(observed["tasks"].discard)
            return True

    class Server(asyncssh.SSHServer):
        def begin_auth(self, username):
            return True

        def public_key_auth_supported(self):
            return True

        def validate_public_key(self, username, key):
            observed["auth_calls"] += 1
            return username == "mnemion" and key == user_key.convert_to_public()

        def session_requested(self):
            return Session()

    async with await asyncssh.create_server(
        Server, "127.0.0.1", 0, server_host_keys=[host_key], encoding=None
    ) as listener:
        connection = Connection(
            **{key: identity[key] for key in ("host_id", "operator_id")},
            hostname="127.0.0.1",
            port=listener.get_port(),
            username="mnemion",
            host_key_fingerprint=host_key.get_fingerprint("sha256"),
            operator_key_fingerprint=user_key.get_fingerprint("sha256"),
        )
        try:
            yield store, connection, user_key.export_private_key("openssh"), observed
        finally:
            for task in list(observed["tasks"]):
                task.cancel()
            await asyncio.gather(*observed["tasks"], return_exceptions=True)


def request(connection, action="host.status", **extra):
    now = datetime.now(timezone.utc)
    lifetime = (
        {}
        if action in {"host.status", "operations.get", "operators.list", "operations.list"}
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
                **extra,
            }
        )
    )


def test_pinned_ssh_uses_only_the_registered_command_and_key(tmp_path, monkeypatch):
    # An absent local SSH program, unrelated agent and invalid user config are
    # irrelevant: the client uses the bundled library and explicit enrollment.
    monkeypatch.setenv("SSH_AUTH_SOCK", "/unrelated/agent")
    monkeypatch.setenv("PATH", "/no-local-ssh-program")

    async def exercise():
        async with server(tmp_path) as (_, connection, key, observed):
            result = await call(connection, key, request(connection))
            assert result["ok"]
            assert result["result"]["operator"]["role"] == "custodian"
            assert observed["commands"] == [COMMAND]

    asyncio.run(exercise())


def test_changed_server_key_stops_before_operator_authentication(tmp_path):
    async def exercise():
        async with server(tmp_path) as (_, connection, key, observed):
            wrong = asyncssh.generate_private_key("ssh-ed25519").get_fingerprint("sha256")
            connection = connection.model_copy(update={"host_key_fingerprint": wrong})
            with pytest.raises(HostControlError) as error:
                await call(connection, key, request(connection))
            assert error.value.code == "host_identity_changed"
            assert observed["auth_calls"] == 0
            assert observed["commands"] == []

    asyncio.run(exercise())


def test_operator_key_mismatch_is_refused_without_connecting(tmp_path):
    async def exercise():
        async with server(tmp_path) as (_, connection, _, observed):
            wrong = asyncssh.generate_private_key("ssh-ed25519").export_private_key("openssh")
            with pytest.raises(HostControlError) as error:
                await call(connection, wrong, request(connection))
            assert error.value.code == "invalid_operator_key"
            assert observed["auth_calls"] == 0

    asyncio.run(exercise())


def test_lost_ssh_reply_reconnects_to_the_same_durable_job(tmp_path):
    async def exercise():
        async with server(tmp_path, delay=0.25) as (store, connection, key, observed):
            action = request(connection, "service.stop", approve_service_interruption=True)
            with pytest.raises(HostControlError) as error:
                await call(connection, key, action, timeout=0.1)
            assert error.value.code == "host_connection_timeout"
            observed["delay"] = 0
            result = await call(connection, key, action)
            assert result["ok"] and result["result"]["operation_id"] == str(action.request_id)
            assert result["result"]["phase"] == "queued"
            with store.transaction() as conn:
                assert conn.execute("SELECT count(*) FROM operations").fetchone()[0] == 1

    asyncio.run(exercise())


@pytest.mark.parametrize("mode", ["oversized", "wrong_request"])
def test_response_bounds_and_identity_are_enforced(tmp_path, mode):
    async def exercise():
        async with server(tmp_path, **{mode: True}) as (_, connection, key, _):
            with pytest.raises(HostControlError) as error:
                await call(connection, key, request(connection))
            assert error.value.code == "invalid_host_response"

    asyncio.run(exercise())
