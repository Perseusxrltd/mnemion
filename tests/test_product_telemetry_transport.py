from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, closing, suppress
from datetime import datetime, timedelta, timezone
import socket
import sqlite3
import ssl
from types import SimpleNamespace

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
import pytest

from mnemion.product_telemetry import aggregate, delivery, policy, transport


@pytest.fixture(scope="module")
def certificates(tmp_path_factory):
    folder = tmp_path_factory.mktemp("telemetry-tls")
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    certificate, private_key = folder / "certificate.pem", folder / "key.pem"
    certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private_key.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    private_key.chmod(0o600)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.num_tickets = 0
    context.load_cert_chain(certificate, private_key)
    return certificate, context


@pytest.fixture
def installation(tmp_path, monkeypatch, certificates):
    assert policy.COLLECTION_AVAILABLE is False
    root = tmp_path / "private"
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "company_policy_file", lambda: tmp_path / "company.json")
    original_context = ssl.create_default_context

    def trusted_context():
        context = original_context()
        context.load_verify_locations(cafile=certificates[0])
        return context

    monkeypatch.setattr(ssl, "create_default_context", trusted_context)
    budget = delivery.DeliveryBudget(root)

    def prepare(endpoint):
        authority = endpoint.host if endpoint.port == 443 else f"{endpoint.host}:{endpoint.port}"
        monkeypatch.setattr(policy, "COLLECTOR_URL", f"https://{authority}/v1/report")
        state = policy.configure(
            root, {"enabled": True, "expected_revision": 0, "disclosure_version": 1}
        )
        assert aggregate.record(
            root,
            {"kind": "submission", "workflow": "memory.recall", "surface": "native_agent"},
            expected_revision=state["revision"],
            expected_generation=state["store_generation"],
        )
        report = budget.reserve(
            expected_revision=state["revision"],
            expected_generation=state["store_generation"],
            network="unmetered",
            constrained=False,
        )
        assert report is not None
        return report

    def cleaned(report):
        assert report._closed and report._body == b"\0" * 4
        with closing(sqlite3.connect(root / policy.DATABASE_NAME)) as database:
            assert database.execute("SELECT lease_token FROM delivery_state").fetchall() == [
                (None,)
            ]
            assert database.execute("SELECT count(*) FROM delivery_attempts").fetchone() == (1,)

    return SimpleNamespace(
        root=root, budget=budget, prepare=prepare, cleaned=cleaned, context=certificates[1]
    )


@asynccontextmanager
async def peer(context, mode="success"):
    entered, release = asyncio.Event(), asyncio.Event()
    requests, tasks = [], set()

    async def handle(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        try:
            if mode == "stall_handshake":
                await reader.read(4096)
                entered.set()
                await release.wait()
                return
            headers = await reader.readuntil(b"\r\n\r\n")
            body = await reader.readexactly(4)
            requests.append((headers, body))
            entered.set()
            if mode == "hold":
                await release.wait()
            response = b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            if mode == "redirect":
                response = b"HTTP/1.1 302 Found\r\nLocation: https://example.invalid/private\r\nContent-Length: 0\r\n\r\n"
            if mode == "large_headers":
                response = b"HTTP/1.1 204 No Content\r\nX-Noise: " + b"a" * 4096 + b"\r\n\r\n"
            writer.write(response)
            await writer.drain()
        except (OSError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()
            tasks.discard(task)

    server = await asyncio.start_server(
        handle, "127.0.0.1", 0, ssl=None if mode == "stall_handshake" else context
    )
    endpoint = transport.Endpoint("localhost", "127.0.0.1", server.sockets[0].getsockname()[1])
    try:
        yield SimpleNamespace(
            endpoint=endpoint, entered=entered, release=release, requests=requests
        )
    finally:
        release.set()
        server.close()
        await server.wait_closed()
        for task in list(tasks):
            task.cancel()
        await asyncio.gather(*list(tasks), return_exceptions=True)


def test_tls_handoff_is_one_four_byte_request_without_dns_credentials_or_retries(
    installation, monkeypatch
):
    f = installation

    async def run():
        async with peer(f.context) as server:
            report = f.prepare(server.endpoint)
            original = bytes(report._body)

            def forbidden_dns(*_args, **_kwargs):
                raise AssertionError("No system resolver may be started")

            monkeypatch.setattr(socket, "getaddrinfo", forbidden_dns)
            result = await transport.send(f.budget, report, server.endpoint)
            assert result.outcome == "delivered"
            assert 0 < result.encrypted_bytes_charged <= transport.MAX_TLS_BYTES
            assert len(server.requests) == 1 and server.requests[0][1] == original
            headers = server.requests[0][0]
            assert headers.startswith(b"POST /v1/report HTTP/1.1\r\n")
            names = {line.split(b":", 1)[0].lower() for line in headers.split(b"\r\n")[1:] if line}
            assert names == {b"host", b"content-type", b"content-length", b"connection"}
            f.cleaned(report)
            assert (await transport.send(f.budget, report, server.endpoint)).outcome == "suppressed"
            assert len(server.requests) == 1

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["hold", "stall_handshake"])
def test_opt_out_closes_pending_tls_io_promptly_and_keeps_spending(installation, mode):
    f = installation

    async def run():
        async with peer(f.context, mode) as server:
            report = f.prepare(server.endpoint)
            task = asyncio.create_task(transport.send(f.budget, report, server.endpoint))
            await asyncio.wait_for(server.entered.wait(), 2)
            policy.configure(f.root, {"enabled": False, "expected_revision": 0})
            result = await asyncio.wait_for(task, 1)
            assert result.outcome == "suppressed"
            assert len(server.requests) == (1 if mode == "hold" else 0)
            f.cleaned(report)

    asyncio.run(run())


def test_caller_cancellation_is_propagated_and_cleans_the_active_socket_and_lease(installation):
    f = installation

    async def run():
        async with peer(f.context, "hold") as server:
            report = f.prepare(server.endpoint)
            task = asyncio.create_task(transport.send(f.budget, report, server.endpoint))
            await asyncio.wait_for(server.entered.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 1)
            f.cleaned(report)

    asyncio.run(run())


def test_concurrent_senders_share_one_connection_and_leave_the_winner_intact(installation):
    f = installation

    async def run():
        async with peer(f.context) as server:
            report = f.prepare(server.endpoint)
            results = await asyncio.gather(
                *[transport.send(f.budget, report, server.endpoint) for _ in range(2)]
            )
            assert sorted(result.outcome for result in results) == ["delivered", "suppressed"]
            assert (
                sum(result.encrypted_bytes_charged for result in results) <= transport.MAX_TLS_BYTES
            )
            assert len(server.requests) == 1
            f.cleaned(report)

    asyncio.run(run())


def test_a_second_sender_cannot_cancel_a_request_already_waiting_for_its_response(installation):
    f = installation

    async def run():
        async with peer(f.context, "hold") as server:
            report = f.prepare(server.endpoint)
            first = asyncio.create_task(transport.send(f.budget, report, server.endpoint))
            await asyncio.wait_for(server.entered.wait(), 2)
            second = await transport.send(f.budget, report, server.endpoint)
            assert second == transport.AttemptResult("suppressed")
            assert f.budget.current(report)
            server.release.set()
            assert (await asyncio.wait_for(first, 1)).outcome == "delivered"
            assert len(server.requests) == 1
            f.cleaned(report)

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["redirect", "large_headers"])
def test_response_limits_and_redirects_never_create_another_request(installation, mode):
    f = installation

    async def run():
        async with peer(f.context, mode) as server:
            report = f.prepare(server.endpoint)
            result = await transport.send(f.budget, report, server.endpoint)
            assert result.outcome == "failed" and len(server.requests) == 1
            assert result.encrypted_bytes_charged <= transport.MAX_TLS_BYTES
            f.cleaned(report)

    asyncio.run(run())


def test_wrong_certificate_name_prevents_the_report_body_from_being_sent(installation):
    f = installation

    async def run():
        async with peer(f.context) as server:
            endpoint = transport.Endpoint("wrong.invalid", "127.0.0.1", server.endpoint.port)
            report = f.prepare(endpoint)
            result = await transport.send(f.budget, report, endpoint)
            assert result.outcome == "failed" and not server.requests
            f.cleaned(report)

    asyncio.run(run())


def test_tls_byte_limit_stops_an_incomplete_handshake_without_application_data(
    installation, monkeypatch
):
    f = installation
    monkeypatch.setattr(transport, "MAX_TLS_BYTES", 512)

    async def run():
        async with peer(f.context) as server:
            report = f.prepare(server.endpoint)
            result = await transport.send(f.budget, report, server.endpoint)
            assert result.outcome == "wire_limit"
            assert result.encrypted_bytes_charged <= 512 and not server.requests
            f.cleaned(report)

    asyncio.run(run())


def test_real_five_second_deadline_stops_a_silent_peer(installation):
    f = installation

    async def run():
        async with peer(f.context, "stall_handshake") as server:
            report = f.prepare(server.endpoint)
            started = asyncio.get_running_loop().time()
            result = await asyncio.wait_for(transport.send(f.budget, report, server.endpoint), 6)
            elapsed = asyncio.get_running_loop().time() - started
            assert result.outcome in {"deadline", "suppressed"}
            assert 4.5 < elapsed < 5.5 and not server.requests
            f.cleaned(report)

    asyncio.run(run())
