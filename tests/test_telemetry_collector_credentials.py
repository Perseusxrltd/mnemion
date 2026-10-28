"""Actual TLS-pair rotation, fail-closed storage and renewal-hook behavior."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import ssl
import stat
import subprocess
import sys
from threading import Event
from types import SimpleNamespace

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
import pytest

from deploy.collector import credentials

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux collector provisioning")
ROOT = Path(__file__).resolve().parents[1]


def lineage(path, *, hostname="localhost", expires=30, begins=-1, key=None):
    path.mkdir(mode=0o700)
    key = key or ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now + timedelta(days=begins))
        .not_valid_after(now + timedelta(days=expires))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    (path / "fullchain.pem").write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private_key = path / "privkey.pem"
    private_key.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    private_key.chmod(0o600)
    return path


def command(source, destination, *extra, environment=None):
    return subprocess.run(
        [
            sys.executable,
            "-I",
            str(ROOT / "deploy/collector/credentials.py"),
            "--lineage",
            str(source),
            "--destination",
            str(destination),
            "--hostname",
            "localhost",
            *extra,
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=10,
        env=environment,
    )


def test_private_bundle_is_actual_matching_tls_material_and_unchanged_is_noop(
    tmp_path, monkeypatch
):
    source = lineage(tmp_path / "lineage")
    destination = tmp_path / "credentials"
    forbidden = tmp_path / "keylog"
    monkeypatch.setenv("SSLKEYLOGFILE", str(forbidden))
    first = credentials.rotate(source, destination, "localhost")
    bundle = destination / "tls.pem"
    original = bundle.read_bytes(), bundle.stat().st_ino, bundle.stat().st_mtime_ns
    assert first["changed"] and first["activation"] == "not_requested"
    assert first["validation_scope"] == "key_pair_hostname_validity"
    certificate = x509.load_pem_x509_certificate((source / "fullchain.pem").read_bytes())
    assert first["certificate_sha256"] == certificate.fingerprint(hashes.SHA256()).hex()
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert stat.S_IMODE(bundle.stat().st_mode) == 0o600
    monkeypatch.setattr(
        credentials, "_activate", lambda: pytest.fail("unchanged material restarted")
    )
    again = credentials.rotate(source, destination, "localhost", restart_active=True)
    assert again == {**first, "changed": False}
    assert (bundle.read_bytes(), bundle.stat().st_ino, bundle.stat().st_mtime_ns) == original
    assert {p.name for p in destination.iterdir()} == {".credentials.lock", "tls.pem"}
    assert not forbidden.exists()


def test_certbot_symlinks_and_changed_pair_replace_one_generation(tmp_path, monkeypatch):
    old = lineage(tmp_path / "old")
    new = lineage(tmp_path / "new")
    current = tmp_path / "live"
    current.mkdir()
    for name in ("fullchain.pem", "privkey.pem"):
        (current / name).symlink_to(old / name)
    destination = tmp_path / "credentials"
    initial = credentials.rotate(current, destination, "localhost")
    for name in ("fullchain.pem", "privkey.pem"):
        (current / name).unlink()
        (current / name).symlink_to(new / name)
    activations = []
    monkeypatch.setattr(credentials, "_activate", lambda: activations.append(True) or "restarted")
    replaced = credentials.rotate(current, destination, "localhost", restart_active=True)
    assert replaced["changed"] and replaced["activation"] == "restarted"
    assert replaced["certificate_sha256"] != initial["certificate_sha256"]
    assert activations == [True]
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(destination / "tls.pem", password="")


@pytest.mark.parametrize(
    "invalid", ["mismatched", "hostname", "expired", "future", "expiring", "text"]
)
def test_invalid_renewal_preserves_installed_pair_and_never_restarts(
    tmp_path, monkeypatch, invalid
):
    installed = lineage(tmp_path / "installed")
    destination = tmp_path / "credentials"
    credentials.rotate(installed, destination, "localhost")
    original = (destination / "tls.pem").read_bytes()
    options = {
        "hostname": {"hostname": "other.invalid"},
        "expired": {"begins": -3, "expires": -1},
        "future": {"begins": 1},
        "expiring": {"expires": 0.25},
    }.get(invalid, {})
    source = lineage(tmp_path / "incoming", **options)
    if invalid == "mismatched":
        (source / "privkey.pem").write_bytes((installed / "privkey.pem").read_bytes())
    if invalid == "text":
        (source / "fullchain.pem").write_bytes(b"PRIVATE_TLS_INPUT_CANARY")
    monkeypatch.setattr(credentials, "_activate", lambda: pytest.fail("invalid pair restarted"))
    with pytest.raises((credentials.RotationError, ssl.SSLError)):
        credentials.rotate(source, destination, "localhost", restart_active=True)
    assert (destination / "tls.pem").read_bytes() == original
    assert {p.name for p in destination.iterdir()} == {".credentials.lock", "tls.pem"}


@pytest.mark.parametrize(
    "unsafe", ["key_mode", "key_link", "key_large", "directory", "symlink", "fifo"]
)
def test_unsafe_storage_is_refused_before_credential_replacement(tmp_path, unsafe):
    source = lineage(tmp_path / "lineage")
    destination = tmp_path / "credentials"
    credentials.rotate(source, destination, "localhost")
    bundle = destination / "tls.pem"
    original = bundle.read_bytes()
    if unsafe == "key_mode":
        (source / "privkey.pem").chmod(0o644)
    elif unsafe == "key_link":
        os.link(source / "privkey.pem", tmp_path / "extra-key")
    elif unsafe == "key_large":
        (source / "privkey.pem").write_bytes(b"x" * (credentials.KEY_LIMIT + 1))
    elif unsafe == "directory":
        destination.chmod(0o755)
    elif unsafe == "symlink":
        copy = tmp_path / "original"
        bundle.replace(copy)
        bundle.symlink_to(copy)
    elif unsafe == "fifo":
        bundle.unlink()
        os.mkfifo(bundle, 0o600)
    with pytest.raises((credentials.RotationError, OSError)):
        credentials.rotate(source, destination, "localhost")
    if unsafe == "fifo":
        assert stat.S_ISFIFO(bundle.lstat().st_mode)
    else:
        assert bundle.read_bytes() == original


def test_competing_process_fails_immediately_under_existing_rotation_lock(tmp_path):
    source = lineage(tmp_path / "lineage")
    destination = tmp_path / "credentials"
    with credentials._directory(destination):
        refused = command(source, destination)
    assert refused.returncode == 1 and refused.stderr == b""
    assert json.loads(refused.stdout) == {"schema_version": 1, "error": "rotation_busy"}
    assert not (destination / "tls.pem").exists()


def test_readers_never_receive_a_mixed_pair_while_two_certificates_rotate(tmp_path):
    sources = [lineage(tmp_path / str(i)) for i in range(2)]
    destination = tmp_path / "credentials"
    credentials.rotate(sources[0], destination, "localhost")
    stopped = Event()
    started = Event()

    def reader():
        count = 0
        started.set()
        while not stopped.is_set():
            # The service manager takes one file snapshot. No second file open
            # is used to select a private key from a different generation.
            snapshot = (destination / "tls.pem").read_bytes()
            parsed = x509.load_pem_x509_certificate(snapshot)
            private = serialization.load_pem_private_key(
                snapshot[snapshot.index(b"-----BEGIN PRIVATE") :], None
            )
            assert parsed.public_key().public_numbers() == private.public_key().public_numbers()
            count += 1
        return count

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(reader)
        assert started.wait(2)
        try:
            for index in range(8):
                credentials.rotate(sources[(index + 1) % 2], destination, "localhost")
        finally:
            stopped.set()
        assert result.result(timeout=3) > 0


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (b"LoadState=not-found\nActiveState=inactive\n", "not_running"),
        (b"LoadState=loaded\nActiveState=inactive\n", "not_running"),
        (b"LoadState=loaded\nActiveState=active\n", "restarted"),
    ],
)
def test_restart_does_not_start_an_absent_or_stopped_service(monkeypatch, state, expected):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert kwargs["timeout"] == 30 and kwargs["stdin"] == subprocess.DEVNULL
        return SimpleNamespace(returncode=0, stdout=state if args[1] == "show" else b"")

    monkeypatch.setattr(credentials.subprocess, "run", run)
    assert credentials._activate() == expected
    assert all(args[0] == "systemctl" and credentials.UNIT in args for args in calls)
    assert len(calls) == (3 if expected == "restarted" else 1)


def test_failed_restart_retains_valid_new_bundle_and_reports_failure(tmp_path, monkeypatch):
    source = lineage(tmp_path / "lineage")
    destination = tmp_path / "credentials"

    def fail():
        raise credentials.RotationError("service_restart_failed")

    monkeypatch.setattr(credentials, "_activate", fail)
    with pytest.raises(credentials.RotationError, match="service_restart_failed"):
        credentials.rotate(source, destination, "localhost", restart_active=True)
    assert (destination / "tls.pem").is_file()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(destination / "tls.pem", password="")


def test_cli_ignores_unrelated_lineage_and_refusals_never_echo_input(tmp_path):
    source = lineage(tmp_path / "lineage")
    unrelated = lineage(tmp_path / "unrelated")
    destination = tmp_path / "credentials"
    environment = {**os.environ, "RENEWED_LINEAGE": str(unrelated)}
    ignored = command(source, destination, environment=environment)
    assert ignored.returncode == 0 and ignored.stderr == b""
    assert json.loads(ignored.stdout)["activation"] == "unrelated_lineage"
    assert not destination.exists()
    (source / "fullchain.pem").write_bytes(b"PRIVATE_TLS_INPUT_CANARY")
    refused = command(source, destination)
    assert refused.returncode == 1 and refused.stderr == b""
    assert json.loads(refused.stdout) == {"schema_version": 1, "error": "invalid_certificate"}
    assert b"CANARY" not in refused.stdout and str(tmp_path).encode() not in refused.stdout


def test_service_manager_snapshots_one_credential_for_the_tls_pair():
    unit = (ROOT / "deploy/collector/mnemion-telemetry.service").read_text()
    assert unit.count("LoadCredential=") == 1
    assert "LoadCredential=tls.pem:/etc/mnemion-telemetry/tls.pem" in unit
    assert "--certificate %d/tls.pem --private-key %d/tls.pem" in unit


def test_installed_bundle_works_in_actual_collector_without_tls_or_request_logs(tmp_path):
    from tests.test_product_telemetry_collector_server import _running_server, connect, response

    source = lineage(tmp_path / "lineage")
    destination = tmp_path / "credentials"
    credentials.rotate(source, destination, "localhost")
    bundle = destination / "tls.pem"
    with contextmanager(_running_server)(tmp_path, (bundle, bundle)) as server:
        with connect(server) as channel:
            channel.sendall(
                b"POST /v1/report HTTP/1.1\r\nHost: localhost\r\n"
                b"Content-Length: 4\r\n\r\n\x02\x00\x00\x02"
            )
            assert response(channel).startswith(b"HTTP/1.1 204")
    # The reused real-server fixture verifies empty logs, no TLS key log,
    # bounded shutdown and absence of retained individual reports.
