"""One bounded HTTPS attempt for an already-reserved anonymous report.

There is no scheduler, DNS lookup, proxy, credential store, redirect, retry or
shutdown flush. The fixed endpoint must match the disclosed collector. Encrypted
TLS byte accounting is explicit; TCP/IP overhead still needs platform evidence.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from ipaddress import ip_address
import re
import socket
import ssl

from . import delivery, policy
from .endpoint import Endpoint

MAX_TLS_BYTES = 32768
MAX_HEADERS = 2048
RECEIVE_BUFFER_BYTES = 4096


@dataclass(frozen=True, slots=True)
class AttemptResult:
    outcome: str
    encrypted_bytes_charged: int = 0


class _Stopped(Exception):
    pass


class _WireLimit(Exception):
    pass


class _Channel:
    def __init__(self, endpoint: Endpoint, budget, report):
        self.endpoint, self.budget, self.report = endpoint, budget, report
        self.loop = asyncio.get_running_loop()
        self.raw = None
        self.incoming = ssl.MemoryBIO()
        self.outgoing = ssl.MemoryBIO()
        self.secure = None
        self.charged = 0
        self.closed = False
        self.pending_io = None

    def abort(self):
        self.closed = True
        if self.raw is not None:
            # No TLS unwrap/close_notify or application flush after cancellation.
            self.raw.close()
        if self.pending_io is not None:
            self.pending_io.cancel()

    async def wait_io(self, operation):
        self.pending_io = asyncio.create_task(operation)
        try:
            return await self.pending_io
        except asyncio.CancelledError:
            if self.closed:
                raise _Stopped from None
            raise
        finally:
            self.pending_io = None

    def permitted(self):
        if self.closed or not self.budget.current(self.report):
            raise _Stopped

    def charge(self, amount):
        if self.charged + amount > MAX_TLS_BYTES:
            raise _WireLimit
        self.charged += amount

    async def flush_handshake(self):
        self.permitted()
        while self.outgoing.pending:
            data = self.outgoing.read(min(4096, self.outgoing.pending))
            self.charge(len(data))  # Uncertain/partial sends are never refunded.
            self.permitted()
            await self.wait_io(self.loop.sock_sendall(self.raw, data))

    async def receive(self):
        self.permitted()
        remaining = MAX_TLS_BYTES - self.charged
        if remaining <= 0:
            raise _WireLimit
        data = await self.wait_io(self.loop.sock_recv(self.raw, min(4096, remaining)))
        if not data:
            raise _Stopped
        self.charge(len(data))
        self.incoming.write(data)

    async def connect(self):
        self.permitted()
        # A literal release-owned address prevents an uncancellable system DNS
        # worker from continuing after the five-second attempt has stopped.
        family = (
            socket.AF_INET6 if ip_address(self.endpoint.address).version == 6 else socket.AF_INET
        )
        self.raw = socket.socket(family, socket.SOCK_STREAM)
        self.raw.setblocking(False)
        # Bound the kernel's receive window before connect. Limiting reads or
        # TLS accounting alone still lets a burst fill an ambient large socket
        # buffer before the oversized response is rejected. Linux reports twice
        # the requested SO_RCVBUF for bookkeeping; decline if the OS cannot
        # honor that bound. This does not bound retransmissions on the network.
        self.raw.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RECEIVE_BUFFER_BYTES)
        if (
            not 0
            < self.raw.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
            <= (2 * RECEIVE_BUFFER_BYTES)
        ):
            raise _Stopped
        self.raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # Explicit release roots replace the ambient/system/extra trust store.
        # create_default_context keeps Python's certificate/hostname safeguards;
        # cadata prevents it from loading every unrelated system CA.
        context = ssl.create_default_context(
            cadata="\n".join(self.endpoint.certificate_authorities)
        )
        trusted = context.cert_store_stats()
        if (
            trusted["x509"] != len(self.endpoint.certificate_authorities)
            or trusted["x509_ca"] != trusted["x509"]
        ):
            raise _Stopped
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.options |= ssl.OP_NO_TICKET
        context.set_alpn_protocols(["http/1.1"])
        self.secure = context.wrap_bio(
            self.incoming, self.outgoing, server_side=False, server_hostname=self.endpoint.host
        )
        self.permitted()
        await self.wait_io(
            self.loop.sock_connect(self.raw, (self.endpoint.address, self.endpoint.port))
        )
        while True:
            self.permitted()
            try:
                self.secure.do_handshake()
                break
            except ssl.SSLWantReadError:
                await self.flush_handshake()
                await self.receive()
            except ssl.SSLWantWriteError:
                await self.flush_handshake()
        await self.flush_handshake()

    def handoff(self, body: bytes) -> bool:
        """Called only inside the current policy's short final-write lock."""
        if self.closed or self.raw is None or self.secure is None or len(body) != 4:
            return False
        if self.outgoing.pending:
            return False
        request = self.endpoint.headers() + body
        if self.secure.write(request) != len(request):
            return False
        encrypted = self.outgoing.read()
        if not encrypted or len(encrypted) > MAX_HEADERS:
            return False
        self.charge(len(encrypted))
        # This is a single nonblocking kernel handoff, with no await, DNS, TLS
        # negotiation or retry under the privacy lock. A short/failed write
        # closes the attempt; its possible partial exposure stays charged.
        return self.raw.send(encrypted) == len(encrypted)

    async def response(self) -> bool:
        headers = bytearray()
        while b"\r\n\r\n" not in headers:
            self.permitted()
            if len(headers) >= MAX_HEADERS:
                return False
            try:
                data = self.secure.read(MAX_HEADERS - len(headers))
                if not data:
                    return False
                headers.extend(data)
            except ssl.SSLWantReadError:
                # A controlled collector needs no additional client TLS
                # messages after the one application handoff. Do not flush a
                # surprise renegotiation/key-update request during shutdown.
                if self.outgoing.pending:
                    return False
                await self.receive()
        block, extra = headers.split(b"\r\n\r\n", 1)
        lines = bytes(block).split(b"\r\n")
        if extra or not re.fullmatch(rb"HTTP/1\.1 204(?: [\x20-\x7e]*)?", lines[0]):
            return False
        names = set()
        for line in lines[1:]:
            if b":" not in line:
                return False
            name, value = line.split(b":", 1)
            name = name.lower()
            if not re.fullmatch(rb"[a-z0-9-]+", name) or name in names:
                return False
            names.add(name)
            if name == b"transfer-encoding" or (
                name == b"content-length" and value.strip() != b"0"
            ):
                return False
        return True


async def send(
    budget: delivery.DeliveryBudget, report: delivery.PreparedReport, endpoint: Endpoint
) -> AttemptResult:
    """Use one reservation; the existing caller owns this task and its lifetime.

    Every return/cancellation closes the socket, erases the report and removes
    its matching lease. The caller's cancellation is propagated. No new attempt
    or periodic wake is created, and no exception text enters product metrics.
    """
    # Claim before connection setup and before acquiring cleanup responsibility.
    # A duplicate call must neither open another TLS connection nor cancel the
    # existing request that still owns this report's one spent reservation.
    if type(report) is not delivery.PreparedReport or not report.claim_transport():
        return AttemptResult("suppressed")
    if not policy.COLLECTION_AVAILABLE or type(endpoint) is not Endpoint or not endpoint.validate():
        budget.cancel(report)
        return AttemptResult("suppressed")
    channel = _Channel(endpoint, budget, report)
    watcher = None
    outcome = "failed"
    try:
        if not budget.current(report):
            return AttemptResult("suppressed")
        remaining = report._monotonic_deadline - delivery._monotonic()
        if remaining <= 0:
            return AttemptResult("deadline")
        async with asyncio.timeout(min(remaining, delivery.DEADLINE_MS / 1000)):
            watcher = asyncio.create_task(budget.watch(report, channel.abort))
            await channel.connect()
            if not budget.guarded_write(report, channel.handoff):
                outcome = "suppressed"
            elif await channel.response():
                outcome = "delivered"
    except TimeoutError:
        outcome = "deadline"
    except _WireLimit:
        outcome = "wire_limit"
    except _Stopped:
        outcome = "suppressed"
    except (OSError, ssl.SSLError, ValueError):
        outcome = "suppressed" if channel.closed else "failed"
    finally:
        channel.abort()
        if watcher is not None:
            watcher.cancel()
            with suppress(asyncio.CancelledError):
                await watcher
        budget.cancel(report)
    return AttemptResult(outcome, channel.charged)
