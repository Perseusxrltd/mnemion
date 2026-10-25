"""Actual dedicated TLS ingress, metadata exclusion and bounded lifetimes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
from types import SimpleNamespace

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
import pytest

from mnemion.product_telemetry.server import MetadataBoundary

ROOT = Path(__file__).resolve().parents[1]
CANARY = b"PRIVATE_REQUEST_CANARY"
COLLECTOR_PYTHON = os.environ.get("MNEMION_TEST_COLLECTOR_PYTHON", sys.executable)


@pytest.fixture(scope="module")
def certificates(tmp_path_factory):
    folder = tmp_path_factory.mktemp("collector-certificate")
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
    return certificate, private_key


def connect(server):
    raw = socket.create_connection(("127.0.0.1", server.port), timeout=8)
    try:
        return server.context.wrap_socket(raw, server_hostname="localhost")
    except BaseException:
        raw.close()
        raise


def response(channel):
    received = bytearray()
    while part := channel.recv(2048):
        received.extend(part)
        assert len(received) <= 4096
    return bytes(received)


@pytest.fixture
def server(tmp_path, certificates):
    certificate, private_key = certificates
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    state = tmp_path / "collector"
    stdout, stderr = tmp_path / "stdout", tmp_path / "stderr"
    keylog = tmp_path / "forbidden-keylog"
    context = ssl.create_default_context(cafile=certificate)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.set_alpn_protocols(["h2", "http/1.1"])
    instance = SimpleNamespace(port=port, context=context, state=state)
    command = [
        COLLECTOR_PYTHON,
        "-m",
        "mnemion.product_telemetry.server",
        "serve",
        "--state",
        str(state),
        "--port",
        str(port),
        "--certificate",
        str(certificate),
        "--private-key",
        str(private_key),
    ]
    with stdout.open("wb") as out, stderr.open("wb") as err:
        child = subprocess.Popen(
            command,
            cwd=ROOT,
            env={**os.environ, "SSLKEYLOGFILE": str(keylog), "PYTHONNOUSERSITE": "1"},
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
        )
        try:
            deadline = time.monotonic() + 8
            while True:
                assert child.poll() is None, stderr.read_text()
                try:
                    with connect(instance) as channel:
                        channel.sendall(b"OPTIONS /v1/report HTTP/1.1\r\nHost: localhost\r\n\r\n")
                        assert response(channel).startswith(b"HTTP/1.1 204")
                    break
                except OSError:
                    assert time.monotonic() < deadline
                    time.sleep(0.02)
            yield instance
        finally:
            child.terminate()
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)
                pytest.fail("collector did not finish bounded shutdown")
    assert not keylog.exists()
    assert stdout.read_bytes() == stderr.read_bytes() == b""
    assert {p.name for p in state.iterdir()} == {"reports.sqlite3"}
    assert CANARY not in (state / "reports.sqlite3").read_bytes()
    # A restart/export must not expose the discarded live week's contributions.
    exported = subprocess.run(
        [
            COLLECTOR_PYTHON,
            "-m",
            "mnemion.product_telemetry.server",
            "reports",
            "--state",
            str(state),
        ],
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=8,
    )
    assert json.loads(exported.stdout) == {"schema_version": 1, "reports": []}
    assert exported.stderr == b""


def test_only_fixed_route_flags_reach_aggregate_processing():
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/report",
        "query_string": CANARY,
        "headers": [(b"authorization", CANARY), (b"x-forwarded-for", CANARY)],
        "client": ("192.0.2.7", 10000),
        "server": ("192.0.2.8", 8443),
        "trace": CANARY,
    }
    original_headers = scope["headers"]

    async def app(filtered, _receive, _send):
        assert filtered["path"] == "/v1/report"
        assert filtered["query_string"] == b"?"
        assert filtered["headers"] == []
        assert filtered["client"] is filtered["server"] is None
        assert "trace" not in filtered
        assert CANARY.decode() not in repr(filtered)

    asyncio.run(MetadataBoundary(app)(scope, None, None))
    assert original_headers == []
    assert CANARY.decode() not in repr(scope)


def test_real_tls_accepts_only_bounded_packets_without_logs_or_resume_tickets(server):
    requests = [
        (
            b"POST /v1/report HTTP/1.1\r\nHost: localhost\r\nContent-Length: 4\r\n"
            + b"".join(
                name + b": " + CANARY + b"\r\n"
                for name in (
                    b"Authorization",
                    b"Cookie",
                    b"User-Agent",
                    b"Referer",
                    b"Origin",
                    b"X-Forwarded-For",
                    b"X-Request-ID",
                )
            )
            + b"\r\n\x01\x00\x00\x00",
            204,
        ),
        (
            b"POST /v1/report?"
            + CANARY
            + b" HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n",
            404,
        ),
        (
            b"GET /" + CANARY + b" HTTP/1.1\r\nHost: localhost\r\nCookie: " + CANARY + b"\r\n\r\n",
            404,
        ),
        (
            b"POST /v1/report HTTP/1.1\r\nHost: localhost\r\nContent-Length: 5\r\nUser-Agent: "
            + CANARY
            + b"\r\n\r\n12345",
            400,
        ),
        (b"GET / HTTP/1.1\r\nprivate malformed header " + CANARY + b"\r\n\r\n", 400),
    ]
    for raw, status in requests:
        with connect(server) as channel:
            channel.sendall(raw)
            received = response(channel)
            assert received.startswith(f"HTTP/1.1 {status}".encode())
            assert len(received) < 2048
            assert CANARY not in received
            assert not channel.session.has_ticket
            assert channel.version() == "TLSv1.3"
            assert channel.selected_alpn_protocol() == "http/1.1"
            headers = received.lower().split(b"\r\n\r\n")[0]
            assert b"\r\nset-cookie:" not in headers
            assert b"\r\nserver:" not in headers
            assert b"\r\ndate:" not in headers


def test_large_headers_are_closed_before_aggregate_processing(server):
    with connect(server) as channel:
        channel.sendall(
            b"POST /v1/report HTTP/1.1\r\nHost: localhost\r\nX-Padding: " + CANARY * 300
        )
        assert response(channel) == b""


@pytest.mark.parametrize("phase", ["handshake", "body"])
def test_stalled_connections_expire_without_a_retained_request(server, phase):
    channel = (
        connect(server)
        if phase == "body"
        else socket.create_connection(("127.0.0.1", server.port), timeout=8)
    )
    with channel:
        started = time.monotonic()
        if phase == "body":
            channel.sendall(
                b"POST /v1/report HTTP/1.1\r\nHost: localhost\r\nContent-Length: 4\r\n\r\n\x01"
            )
        else:
            channel.sendall(b"\x16\x03\x01")
        assert response(channel) == b""
        assert 3 <= time.monotonic() - started < 8


def test_tls12_is_refused(server, certificates):
    context = ssl.create_default_context(cafile=certificates[0])
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    with socket.create_connection(("127.0.0.1", server.port), timeout=8) as raw:
        with pytest.raises(ssl.SSLError):
            context.wrap_socket(raw, server_hostname="localhost")


def test_cli_configuration_errors_do_not_echo_private_values(tmp_path, certificates):
    result = subprocess.run(
        [
            COLLECTOR_PYTHON,
            "-m",
            "mnemion.product_telemetry.server",
            "serve",
            "--state",
            str(tmp_path / "unused"),
            "--bind",
            CANARY.decode(),
            "--certificate",
            str(certificates[0]),
            "--private-key",
            str(certificates[1]),
        ],
        cwd=ROOT,
        capture_output=True,
        timeout=8,
    )
    assert result.returncode == 2
    assert result.stdout == b""
    assert json.loads(result.stderr) == {"error": "telemetry_collector_configuration_invalid"}
    assert not (tmp_path / "unused").exists()
