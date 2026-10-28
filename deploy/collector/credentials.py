"""Rotate the collector's single private TLS credential without network access.

Run from a root-owned Certbot deploy hook. Certificate trust/ingress acceptance
is a separate release decision; this validates only the pair, name and lifetime.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from datetime import datetime, timezone
import hashlib
from ipaddress import ip_address
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import sys
import time
from uuid import uuid4

CERTIFICATE_LIMIT = 16 * 1024
KEY_LIMIT = 16 * 1024
BUNDLE_LIMIT = CERTIFICATE_LIMIT + KEY_LIMIT + 2
UNIT = "mnemion-telemetry.service"


class RotationError(Exception):
    """Only a fixed code may cross the command boundary."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RotationError("invalid_arguments")


def _protect_process() -> None:
    if sys.platform != "linux":
        raise RotationError("unsupported_platform")
    import resource

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    prctl.restype = ctypes.c_int
    if prctl(4, 0, 0, 0, 0) != 0 or prctl(3, 0, 0, 0, 0) != 0:
        raise RotationError("crash_protection_unavailable")


def _checked_file(fd: int, maximum: int, *, private: bool) -> os.stat_result:
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_nlink != 1
        or info.st_size > maximum
        or info.st_mode & (0o077 if private else 0o022)
    ):
        raise RotationError("unsafe_file")
    return info


def _read_file(path: str | Path, maximum: int, *, private: bool, directory=None) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        before = _checked_file(fd, maximum, private=private)
        data = bytearray()
        while len(data) <= maximum:
            chunk = os.read(fd, min(8192, maximum + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(fd)
        if (
            len(data) != before.st_size
            or len(data) > maximum
            or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        ):
            raise RotationError("file_changed")
        return bytes(data)
    finally:
        os.close(fd)


@contextmanager
def _directory(path: Path):
    import fcntl

    if not path.is_absolute() or path.resolve() != path:
        raise RotationError("unsafe_directory")
    path.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    lock = None
    try:
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise RotationError("unsafe_directory")
        lock = os.open(
            ".credentials.lock",
            os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o600,
            dir_fd=fd,
        )
        _checked_file(lock, 0, private=True)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RotationError("rotation_busy") from None
        yield fd
    finally:
        if lock is not None:
            os.close(lock)
        os.close(fd)


def _hostname(value: str) -> None:
    try:
        ip_address(value)
        return
    except ValueError:
        pass
    label = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    if not value or len(value) > 253 or any(not re.fullmatch(label, p) for p in value.split(".")):
        raise RotationError("invalid_hostname")


def _validate(path: Path, certificate: bytes, hostname: str) -> dict:
    """A bounded in-memory TLS handshake checks the actual key and certificate.

    Trust the supplied certificate for this local check only. No ambient CA
    store, DNS, listener, key log or external connection is used.
    """
    _hostname(hostname)
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.minimum_version = ssl.TLSVersion.TLSv1_3
    server_context.load_cert_chain(path, password="")
    client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_context.minimum_version = ssl.TLSVersion.TLSv1_3
    client_context.verify_flags = ssl.VERIFY_X509_PARTIAL_CHAIN | ssl.VERIFY_X509_TRUSTED_FIRST
    client_context.load_verify_locations(cadata=certificate.decode("ascii"))
    incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
    peer_incoming, peer_outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
    client = client_context.wrap_bio(incoming, outgoing, server_hostname=hostname)
    server = server_context.wrap_bio(peer_incoming, peer_outgoing, server_side=True)
    completed = [False, False]
    exchanged = 0
    for _ in range(12):
        for index, (participant, output, target) in enumerate(
            ((client, outgoing, peer_incoming), (server, peer_outgoing, incoming))
        ):
            if not completed[index]:
                try:
                    participant.do_handshake()
                    completed[index] = True
                except ssl.SSLWantReadError:
                    pass
            packet = output.read()
            exchanged += len(packet)
            if exchanged > 64 * 1024:
                raise RotationError("invalid_certificate")
            if packet:
                target.write(packet)
        if all(completed):
            break
    else:
        raise RotationError("invalid_certificate")
    expiry = ssl.cert_time_to_seconds(client.getpeercert()["notAfter"])
    if expiry - time.time() < 86400:
        raise RotationError("certificate_expiring")
    return {
        "certificate_sha256": hashlib.sha256(client.getpeercert(binary_form=True)).hexdigest(),
        "not_after": datetime.fromtimestamp(expiry, timezone.utc).isoformat(),
        "validation_scope": "key_pair_hostname_validity",
    }


def _activate() -> str:
    def run(arguments):
        return subprocess.run(
            ["systemctl", *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            check=False,
        )

    state = run(["show", UNIT, "--property=LoadState,ActiveState"])
    if state.returncode:
        raise RotationError("service_state_unavailable")
    fields = dict(p.split("=", 1) for p in state.stdout.decode("ascii").splitlines() if "=" in p)
    if fields.get("LoadState") == "not-found":
        return "not_running"
    if fields.get("LoadState") != "loaded":
        raise RotationError("service_state_unavailable")
    if fields.get("ActiveState") not in {"active", "activating", "reloading"}:
        return "not_running"
    if run(["try-restart", UNIT]).returncode or run(["is-active", "--quiet", UNIT]).returncode:
        raise RotationError("service_restart_failed")
    return "restarted"


def rotate(lineage: Path, destination: Path, hostname: str, *, restart_active=False) -> dict:
    if sys.platform != "linux" or not lineage.is_absolute():
        raise RotationError("invalid_configuration")
    _hostname(hostname)
    # Certbot's live files are intentional symlinks. Resolve each, then open a
    # regular owned file without following another final symlink. A mismatched
    # pair during another renewal fails validation before replacing anything.
    certificate = _read_file(
        (lineage / "fullchain.pem").resolve(strict=True), CERTIFICATE_LIMIT, private=False
    ).strip()
    key = _read_file(
        (lineage / "privkey.pem").resolve(strict=True), KEY_LIMIT, private=True
    ).strip()
    cert_pattern = (
        rb"(?:-----BEGIN CERTIFICATE-----\r?\n[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----\s*)+"
    )
    key_pattern = (
        rb"-----BEGIN ((?:RSA |EC )?PRIVATE KEY)-----\r?\n[A-Za-z0-9+/=\r\n]+-----END \1-----"
    )
    if not re.fullmatch(cert_pattern, certificate) or not re.fullmatch(key_pattern, key):
        raise RotationError("invalid_certificate")
    bundle = certificate + b"\n" + key + b"\n"
    with _directory(destination) as directory:
        name = ".tls-" + uuid4().hex + ".pending"
        pending = True
        fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(bundle)
                stream.flush()
                os.fsync(stream.fileno())
            # Refer to the already-open directory, even if a parent is renamed.
            metadata = _validate(Path(f"/proc/self/fd/{directory}/{name}"), certificate, hostname)
            try:
                previous = _read_file("tls.pem", BUNDLE_LIMIT, private=True, directory=directory)
            except FileNotFoundError:
                previous = None
            changed = previous != bundle
            if changed:
                os.replace(name, "tls.pem", src_dir_fd=directory, dst_dir_fd=directory)
                pending = False
                os.fsync(directory)
            activation = _activate() if restart_active and changed else "not_requested"
            return {"schema_version": 1, "changed": changed, "activation": activation, **metadata}
        finally:
            if pending:
                os.unlink(name, dir_fd=directory)


def main(argv=None) -> int:
    parser = Parser(description=__doc__)
    parser.add_argument("--lineage", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path("/etc/mnemion-telemetry"))
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--restart-active", action="store_true")
    try:
        args = parser.parse_args(argv)
        _protect_process()
        renewed = os.environ.get("RENEWED_LINEAGE")
        if renewed and Path(renewed).resolve(strict=True) != args.lineage.resolve(strict=True):
            print(
                json.dumps(
                    {"schema_version": 1, "changed": False, "activation": "unrelated_lineage"}
                )
            )
            return 0
        result = rotate(
            args.lineage, args.destination, args.hostname, restart_active=args.restart_active
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except RotationError as exc:
        error = str(exc)
    except (ssl.SSLError, UnicodeError, KeyError, ValueError):
        error = "invalid_certificate"
    except (OSError, subprocess.SubprocessError):
        error = "credential_operation_failed"
    except Exception:
        error = "credential_operation_failed"
    print(json.dumps({"schema_version": 1, "error": error}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
