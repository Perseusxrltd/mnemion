"""Pinned SSH carried by the bundled Python runtime, without a local SSH tool."""

import asyncio
import hmac
import ipaddress
import json
import re
import struct
from typing import Literal
from uuid import UUID

import asyncssh
from pydantic import Field, field_validator

from . import HostControlError
from .protocol import Document, MAX_REQUEST, MAX_RESPONSE, canonical

COMMAND = "mnemion-host-control-v1"


class Connection(Document):
    host_id: UUID
    operator_id: UUID
    hostname: str = Field(min_length=1, max_length=253)
    port: int = Field(default=7893, strict=True, ge=1, le=65535)
    username: str = Field(default="mnemion", pattern=r"^[a-z_][a-z0-9_-]{0,63}$")
    host_key_algorithm: Literal[
        "ssh-ed25519",
        "ecdsa-sha2-nistp256",
        "ecdsa-sha2-nistp384",
        "ecdsa-sha2-nistp521",
        "rsa-sha2-512",
    ] = "ssh-ed25519"
    host_key_fingerprint: str = Field(pattern=r"^SHA256:[A-Za-z0-9+/]{43}$")
    operator_key_fingerprint: str = Field(pattern=r"^SHA256:[A-Za-z0-9+/]{43}$")

    @field_validator("hostname")
    @classmethod
    def address(cls, value):
        if re.search(r"[\s/@%\\\[\]]", value):
            raise ValueError("Use one host address without SSH options or credentials.")
        try:
            return ipaddress.ip_address(value).compressed
        except ValueError:
            name = value.encode("idna").decode("ascii").lower().removesuffix(".")
            if len(name) > 253 or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in name.split(".")
            ):
                raise ValueError("Use one host address without SSH options or credentials.")
            return name


async def _response(reader):
    header = await reader.readexactly(4)
    length = struct.unpack("!I", header)[0]
    if not 1 <= length <= MAX_RESPONSE:
        raise HostControlError("invalid_host_response", "The host response exceeds its bound.")
    payload = await reader.readexactly(length)
    if await reader.read(1):
        raise HostControlError("invalid_host_response", "The host returned an unexpected response.")
    return json.loads(payload)


async def _stderr(reader):
    total = 0
    while chunk := await reader.read(4096):
        total += len(chunk)
        if total > 4096:
            raise HostControlError(
                "invalid_host_response", "The host returned unexpected diagnostics."
            )
    # Remote diagnostics are never displayed or interpreted as instructions.


async def call(connection: Connection, private_key: bytes, request, *, timeout=15):
    if type(timeout) not in (int, float) or not 0 < timeout <= 30:
        raise HostControlError(
            "invalid_deadline", "Use a host connection deadline of at most 30 seconds."
        )
    if request.host_id != connection.host_id:
        raise HostControlError("wrong_host", "This request belongs to a different enrolled host.")
    if not isinstance(private_key, bytes) or len(private_key) > 16384:
        raise HostControlError(
            "invalid_operator_key", "The private host operator key is unavailable."
        )
    try:
        key = asyncssh.import_private_key(private_key)
        if key.get_algorithm() != "ssh-ed25519" or not hmac.compare_digest(
            key.get_fingerprint("sha256"), connection.operator_key_fingerprint
        ):
            raise ValueError
    except (ValueError, asyncssh.KeyImportError):
        raise HostControlError(
            "invalid_operator_key", "The private key does not match this operator enrollment."
        ) from None
    payload = canonical(request.model_dump(mode="json"))
    if len(payload) > MAX_REQUEST:
        raise HostControlError("invalid_request", "Host requests must fit within 16 KiB.")

    class PinnedClient(asyncssh.SSHClient):
        def validate_host_public_key(self, host, addr, port, public_key):
            return (
                host == connection.hostname
                and port == connection.port
                and hmac.compare_digest(
                    public_key.get_fingerprint("sha256"), connection.host_key_fingerprint
                )
            )

    try:
        async with asyncio.timeout(timeout):
            async with asyncssh.connect(
                connection.hostname,
                port=connection.port,
                username=connection.username,
                config=None,
                # Empty, not None: verification remains enabled and calls the
                # exact fingerprint callback. Never use ambient known_hosts.
                known_hosts=b"",
                server_host_key_algs=[connection.host_key_algorithm],
                client_factory=PinnedClient,
                client_keys=[key],
                agent_path=None,
                agent_forwarding=False,
                password_auth=False,
                kbdint_auth=False,
                host_based_auth=False,
                # AsyncSSH initializes its platform GSS context before checking
                # the auth flags. This channel uses only the enrolled key and
                # must not load Windows SSPI or ambient Kerberos credentials.
                gss_host=None,
                gss_auth=False,
                gss_kex=False,
                preferred_auth=["publickey"],
                connect_timeout=min(timeout, 10),
                login_timeout=min(timeout, 10),
                keepalive_interval=5,
                keepalive_count_max=1,
            ) as ssh:
                async with ssh.create_process(
                    COMMAND,
                    input=struct.pack("!I", len(payload)) + payload,
                    encoding=None,
                    request_pty=False,
                    x11_forwarding=False,
                    window=256 * 1024,
                    max_pktsize=32768,
                ) as process:
                    reads = [
                        asyncio.create_task(_response(process.stdout)),
                        asyncio.create_task(_stderr(process.stderr)),
                    ]
                    try:
                        result, _ = await asyncio.gather(*reads)
                    finally:
                        for task in reads:
                            if not task.done():
                                task.cancel()
                        await asyncio.gather(*reads, return_exceptions=True)
                    await process.wait_closed()
                    if process.exit_status != 0:
                        raise HostControlError(
                            "host_control_unavailable", "The host control receiver is unavailable."
                        )
    except asyncssh.HostKeyNotVerifiable:
        raise HostControlError(
            "host_identity_changed",
            "The server key does not match this enrolled host. Have its owner verify the change.",
        ) from None
    except asyncssh.PermissionDenied:
        raise HostControlError(
            "host_access_denied",
            "The host did not accept this operator key. Check its current enrollment.",
        ) from None
    except TimeoutError:
        raise HostControlError(
            "host_connection_timeout",
            "The host reply did not arrive in time. Inspect this operation before retrying.",
        ) from None
    except (asyncssh.Error, OSError, EOFError, ValueError, asyncio.IncompleteReadError) as error:
        if isinstance(error, HostControlError):
            raise
        raise HostControlError(
            "host_control_unavailable",
            "The independent host connection is unavailable. Inspect the same operation after reconnecting.",
        ) from None
    if (
        not isinstance(result, dict)
        or set(result)
        != {"protocol", "host_id", "operator_id", "request_id", "ok", "result", "error"}
        or type(result["protocol"]) is not int
        or result["protocol"] != 1
        or result["host_id"] != str(connection.host_id)
        or result["operator_id"] != str(connection.operator_id)
        or result["request_id"] != str(request.request_id)
        or type(result["ok"]) is not bool
        or (
            result["ok"] and (not isinstance(result["result"], dict) or result["error"] is not None)
        )
        or (
            not result["ok"]
            and (result["result"] is not None or not isinstance(result["error"], dict))
        )
    ):
        raise HostControlError(
            "invalid_host_response",
            "The host response did not match this operation and enrollment.",
        )
    return result
