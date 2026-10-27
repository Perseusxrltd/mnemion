"""Actual dedicated TLS ingress, metadata exclusion and bounded lifetimes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import signal
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

from mnemion.product_telemetry.server import ConfigurationError, MetadataBoundary, _systemd_listener

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


def _running_server(tmp_path, certificates, *, activated=False, crash_isolation=False):
    certificate, private_key = certificates
    inherited_fd = None
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
        if activated:
            reserved.listen(64)
            inherited_fd = os.dup(reserved.fileno())
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
    options = {}
    environment = {**os.environ, "SSLKEYLOGFILE": str(keylog), "PYTHONNOUSERSITE": "1"}
    if crash_isolation:
        # Deliberately faulted children receive no account credentials, user
        # configuration or provider environment. A failed guard can expose only
        # these synthetic fixtures, and never writes a core in the source tree.
        environment = {
            "PATH": os.environ.get("PATH", os.defpath),
            "PYTHONPATH": str(ROOT),
            "PYTHONNOUSERSITE": "1",
            "SSLKEYLOGFILE": str(keylog),
            "LANG": "C.UTF-8",
        }
    if inherited_fd is not None:
        wrapper = (
            "import os,runpy,sys;fd=int(sys.argv.pop(1));"
            "os.dup2(fd,3) if fd!=3 else None;"
            "os.close(fd) if fd!=3 else None;"
            "os.environ.update(LISTEN_PID=str(os.getpid()),LISTEN_FDS='1',LISTEN_FDNAMES='telemetry');"
            "runpy.run_module('mnemion.product_telemetry.server',run_name='__main__')"
        )
        command = [
            COLLECTOR_PYTHON,
            "-c",
            wrapper,
            str(inherited_fd),
            *command[3:],
            "--systemd-socket",
        ]
        options["pass_fds"] = (inherited_fd,)
    with stdout.open("wb") as out, stderr.open("wb") as err:
        try:
            child = subprocess.Popen(
                command,
                cwd=tmp_path if crash_isolation else ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                **options,
            )
            instance.process = child
        finally:
            if inherited_fd is not None:
                os.close(inherited_fd)
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


@pytest.fixture
def server(tmp_path, certificates, request):
    mode = getattr(request, "param", "standalone")
    activated = mode in {"systemd", "systemd-crash"}
    if activated and sys.platform != "linux":
        pytest.skip("systemd listener handoff is Linux-specific")
    yield from _running_server(
        tmp_path, certificates, activated=activated, crash_isolation=mode.endswith("-crash")
    )


@pytest.mark.skipif(sys.platform != "linux", reason="Linux kernel crash-dump disposition")
@pytest.mark.parametrize("server", ["standalone-crash", "systemd-crash"], indirect=True)
def test_running_collector_crash_does_not_dump_an_incomplete_private_request(server, tmp_path):
    with connect(server) as channel:
        # Keep a real TLS request incomplete at the crash boundary. This token
        # is synthetic; the isolated child inherits no user or provider secrets.
        channel.sendall(
            b"POST /v1/report HTTP/1.1\r\nHost: localhost\r\n"
            b"X-Test-Private: " + CANARY + b"\r\nContent-Length: 4\r\n\r\n\x02"
        )
        channel.settimeout(0.05)
        with pytest.raises(socket.timeout):
            channel.recv(1)
        pidfd = os.pidfd_open(server.process.pid)
        try:
            signal.pidfd_send_signal(pidfd, signal.SIGABRT)
            deadline = time.monotonic() + 5
            while True:
                event = os.waitid(
                    os.P_PID, server.process.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG
                )
                if event is not None:
                    break
                assert time.monotonic() < deadline, "The faulted collector did not exit"
                time.sleep(0.01)
            assert event.si_status == signal.SIGABRT
            assert event.si_code == os.CLD_KILLED, "The kernel attempted a core dump"
            assert server.process.wait(timeout=2) == -signal.SIGABRT
        finally:
            os.close(pidfd)
    assert not list(tmp_path.glob("core*"))
    # Fixture teardown also requires empty output, no TLS key log, no private
    # canary in retained state, and an empty report export after restart.


@pytest.mark.parametrize(
    "field,value", [("LISTEN_PID", "0"), ("LISTEN_FDS", "2"), ("LISTEN_FDNAMES", "unrelated")]
)
def test_unrelated_or_extra_service_manager_descriptors_are_refused(monkeypatch, field, value):
    monkeypatch.setenv("LISTEN_PID", str(os.getpid()))
    monkeypatch.setenv("LISTEN_FDS", "1")
    monkeypatch.setenv("LISTEN_FDNAMES", "telemetry")
    monkeypatch.setenv(field, value)
    with pytest.raises(ConfigurationError):
        _systemd_listener("127.0.0.1", 8443)


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


@pytest.mark.parametrize("server", ["standalone", "systemd"], indirect=True)
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
            + b"\r\n\x02\x00\x00\x00",
            204,
        ),
        (
            b"POST /v1/report HTTP/1.1\r\nHost: localhost\r\nContent-Length: 4\r\n\r\n\x02\x00\x00\x02",
            204,  # Reviewed packets use the same bounded transport.
        ),
        (
            b"POST /v1/report HTTP/1.1\r\nHost: localhost\r\nContent-Length: 4\r\n\r\n\x01\x00\x00\x00",
            400,  # Legacy wire cannot establish automatic inclusion.
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


@pytest.mark.skipif(sys.platform != "linux", reason="Linux process dumpability")
def test_linux_collector_disables_dumps_before_serving(tmp_path):
    # The fresh child starts dumpable with a zero core-file limit, the policy
    # that alone cannot stop a configured Linux piped core handler.
    script = """
import ctypes,json,resource,sys
from pathlib import Path
from mnemion.product_telemetry import server
libc=ctypes.CDLL(None)
libc.prctl.argtypes=[ctypes.c_int,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong]
libc.prctl.restype=ctypes.c_int
assert libc.prctl(4,1,0,0,0)==0
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
async def inspect(args,store,listener=None):
    print(json.dumps({'dumpable':libc.prctl(3,0,0,0,0),
                      'core_limits':list(resource.getrlimit(resource.RLIMIT_CORE))}))
    return 0
server._serve=inspect
raise SystemExit(server.main(['serve','--state',sys.argv[1],
    '--certificate',str(Path(sys.argv[1]).parent/'certificate.pem'),
    '--private-key',str(Path(sys.argv[1]).parent/'private-key.pem')]))
"""
    result = subprocess.run(
        [COLLECTOR_PYTHON, "-c", script, str(tmp_path / "collector")],
        cwd=ROOT,
        capture_output=True,
        timeout=8,
        check=True,
    )
    assert result.stderr == b""
    assert json.loads(result.stdout) == {"dumpable": 0, "core_limits": [0, 0]}


@pytest.mark.skipif(sys.platform != "linux", reason="Linux process dumpability")
@pytest.mark.parametrize("failure", ["load", "set", "read", "still_dumpable", "limit"])
def test_linux_privacy_failure_refuses_state_and_listener(tmp_path, monkeypatch, capsys, failure):
    import ctypes
    import resource

    from mnemion.product_telemetry import server

    calls = []

    class Prctl:
        def __call__(self, option, *_unused):
            calls.append(option)
            if option == 4:
                return -1 if failure == "set" else 0
            return -1 if failure == "read" else 1 if failure == "still_dumpable" else 0

    def library(*_args, **_kwargs):
        if failure == "load":
            raise OSError(CANARY.decode())
        return SimpleNamespace(prctl=Prctl())

    def limit(*_args):
        if failure == "limit":
            raise OSError(CANARY.decode())

    async def unexpected_serve(*_args):
        calls.append("serve")
        return 0

    monkeypatch.setattr(ctypes, "CDLL", library)
    monkeypatch.setattr(resource, "setrlimit", limit)
    monkeypatch.setattr(server, "_serve", unexpected_serve)
    state = tmp_path / "must-not-exist"
    assert (
        server.main(
            [
                "serve",
                "--state",
                str(state),
                "--certificate",
                str(tmp_path / "certificate.pem"),
                "--private-key",
                str(tmp_path / "private-key.pem"),
            ]
        )
        == 2
    )
    assert not state.exists() and "serve" not in calls
    output = capsys.readouterr()
    assert output.out == ""
    assert json.loads(output.err) == {"error": "telemetry_collector_configuration_invalid"}


def test_linux_dump_protection_is_not_applied_to_other_platforms(monkeypatch):
    import ctypes

    from mnemion.product_telemetry import server

    def unexpected(*_args, **_kwargs):
        pytest.fail("Non-Linux collection attempted a Linux kernel operation")

    monkeypatch.setattr(server.sys, "platform", "darwin")
    monkeypatch.setattr(ctypes, "CDLL", unexpected)
    server._disable_crash_dumps()


def test_report_inspection_does_not_change_process_dump_policy(tmp_path, monkeypatch, capsys):
    from mnemion.product_telemetry import server

    def unexpected():
        pytest.fail("Report inspection changed process dump policy")

    state = tmp_path / "reports"
    server.ReportStore(state)
    monkeypatch.setattr(server, "_disable_crash_dumps", unexpected)
    assert server.main(["reports", "--state", str(state)]) == 0
    assert json.loads(capsys.readouterr().out) == {"schema_version": 1, "reports": []}
