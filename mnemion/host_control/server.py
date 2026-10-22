"""Restricted, bounded SSH transport for an independently adopted host.

No OS login, shell, PTY, file transfer or forwarding is offered. Work commits to
the durable store before its reply; losing this connection cannot execute it a
second time. The independent worker, not a session, owns service operations.
"""

import asyncio
from contextlib import asynccontextmanager
import ipaddress
import struct

import asyncssh

from . import HostControlError
from .protocol import MAX_REQUEST
from .receiver import dispatch
from .transport import COMMAND

MAX_CONNECTIONS = 32


class Channel(asyncssh.SSHServerChannel):
    """Pinned AsyncSSH integration: refuse ambient environment accumulation.

    These three protocol hooks are deliberately covered by real SSH exchanges.
    Upstream's ordinary shell channel retains arbitrary env values and logs exec
    text before calling the application; neither behavior is useful here.
    """

    def _process_env_request(self, packet):
        packet.get_string()
        packet.get_string()
        packet.check_end()
        return False

    def _process_exec_request(self, packet):
        command = packet.get_string()
        packet.check_end()
        if command != COMMAND.encode("ascii"):
            return False
        return self._start_session(command=COMMAND)

    def _process_subsystem_request(self, packet):
        packet.get_string()
        packet.check_end()
        return False


class Receiver(asyncssh.SSHServerSession):
    def __init__(self, store, actor, tasks, host_status):
        self.store, self.actor, self.tasks, self.host_status = store, actor, tasks, host_status
        self.data = bytearray()
        self.started = False
        self.ended = False
        self.task = None

    def connection_made(self, channel):
        self.channel = channel
        self.timer = asyncio.get_running_loop().call_later(15, self.reject)

    def connection_lost(self, error):
        self.ended = True
        self.timer.cancel()
        if self.task is not None:
            self.task.cancel()
        # Cancelling the awaiting task does not undo a committed SQLite request.
        # dispatch never performs the queued service operation in this thread.

    def exec_requested(self, command):
        if self.started or command != COMMAND:
            return False
        self.started = True
        return True

    def shell_requested(self):
        return False

    def subsystem_requested(self, subsystem):
        return False

    def pty_requested(self, term_type, term_size, term_modes):
        return False

    def reject(self):
        if not self.ended:
            self.ended = True
            self.timer.cancel()
            self.channel.exit(2)
            self.channel.close()

    def data_received(self, data, datatype):
        if self.ended:
            return
        if not self.started or datatype is not None or len(self.data) + len(data) > MAX_REQUEST + 4:
            self.reject()
            return
        self.data.extend(data)
        if len(self.data) >= 4 and not 1 <= struct.unpack("!I", self.data[:4])[0] <= MAX_REQUEST:
            self.reject()

    def eof_received(self):
        if self.ended or self.task is not None:
            return False
        if len(self.data) < 5 or struct.unpack("!I", self.data[:4])[0] != len(self.data) - 4:
            self.reject()
            return False
        self.task = asyncio.create_task(self.reply(bytes(self.data[4:])))
        self.data.clear()
        self.tasks.add(self.task)
        self.task.add_done_callback(self.tasks.discard)
        return True

    async def reply(self, raw):
        try:
            body = await asyncio.to_thread(dispatch, self.store, self.actor, raw, self.host_status)
            if not self.ended:
                self.channel.write(struct.pack("!I", len(body)) + body)
                self.channel.exit(0)
        except Exception:
            # No exception strings or arbitrary remote diagnostics cross the wire.
            self.reject()
        finally:
            self.timer.cancel()


class Server(asyncssh.SSHServer):
    def __init__(self, store, connections, tasks, host_status):
        self.store, self.connections, self.tasks, self.host_status = (
            store,
            connections,
            tasks,
            host_status,
        )
        self.actor = None
        self.authenticated = False
        self.session_started = False

    def connection_made(self, connection):
        self.connection = connection
        self.timer = asyncio.get_running_loop().call_later(30, connection.close)
        if len(self.connections) >= MAX_CONNECTIONS:
            connection.close()
        else:
            self.connections.add(connection)

    def connection_lost(self, error):
        self.timer.cancel()
        self.connections.discard(self.connection)

    def begin_auth(self, username):
        return True

    def public_key_auth_supported(self):
        return True

    async def validate_public_key(self, username, key):
        self.actor = None
        if username != "mnemion" or key.get_algorithm() != "ssh-ed25519":
            return False
        try:
            self.actor = await asyncio.to_thread(
                self.store.authenticate, key.export_public_key().decode("ascii").strip()
            )
            return True
        except (HostControlError, ValueError, OSError):
            return False

    def auth_completed(self):
        # validate_public_key may be an unsigned probe; only this callback follows
        # AsyncSSH's successful proof of private-key possession.
        self.authenticated = self.actor is not None

    def session_requested(self):
        if not self.authenticated or self.session_started:
            return False
        self.session_started = True
        channel = Channel(
            self.connection,
            asyncio.get_running_loop(),
            allow_pty=False,
            line_editor=False,
            line_echo=False,
            line_history=0,
            max_line_length=1024,
            encoding=None,
            errors="strict",
            window=64 * 1024,
            max_pktsize=32768,
        )
        return channel, Receiver(self.store, self.actor, self.tasks, self.host_status)

    def connection_requested(self, dest_host, dest_port, orig_host, orig_port):
        return False

    def server_requested(self, listen_host, listen_port):
        return False

    def unix_connection_requested(self, dest_path):
        return False

    def unix_server_requested(self, listen_path):
        return False


@asynccontextmanager
async def listen(store, private_key, *, host="127.0.0.1", port=7893, host_status=None):
    # Zero is useful for disposable local qualification, not persisted adoption.
    ipaddress.ip_address(host)
    if type(port) is not int or not 0 <= port <= 65535:
        raise HostControlError("invalid_port", "Choose a valid host control port.")
    if not isinstance(private_key, bytes) or len(private_key) > 16384:
        raise HostControlError("invalid_host_key", "The adopted host key needs inspection.")
    try:
        key = asyncssh.import_private_key(private_key)
        if key.get_algorithm() != "ssh-ed25519":
            raise ValueError
    except (ValueError, asyncssh.KeyImportError):
        raise HostControlError(
            "invalid_host_key", "The adopted host key needs inspection."
        ) from None
    connections, tasks = set(), set()
    listener = await asyncssh.create_server(
        lambda: Server(store, connections, tasks, host_status),
        host,
        port,
        config=None,
        server_host_keys=[key],
        authorized_client_keys=None,
        public_key_auth=True,
        password_auth=False,
        kbdint_auth=False,
        host_based_auth=False,
        gss_auth=False,
        gss_kex=False,
        allow_pty=False,
        line_editor=False,
        x11_forwarding=False,
        agent_forwarding=False,
        sftp_factory=None,
        allow_scp=False,
        encoding=None,
        rdns_lookup=False,
        compression_algs=["none"],
        window=64 * 1024,
        max_pktsize=32768,
        login_timeout=10,
        keepalive_interval=5,
        keepalive_count_max=1,
    )
    try:
        async with listener:
            yield listener
    finally:
        current = tuple(connections)
        for connection in current:
            connection.close()
        await asyncio.gather(
            *(connection.wait_closed() for connection in current), return_exceptions=True
        )
        await asyncio.gather(*tuple(tasks), return_exceptions=True)
