"""Authenticated, bounded metadata for managed service updates.

This module verifies release identity and bytes. It does not grant permission
to run migrations, stop a deployment, or execute a downloaded package.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

MAX_MANIFEST_BYTES = 65536
MAX_PACKAGE_BYTES = 128 * 1024 * 1024
SIGNATURE_DOMAIN = b"mnemion-service-update-v1\n"
DEFAULT_REPOSITORY = "Perseusxrltd/mnemion"
_VERSION = re.compile(r"(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})")
_DIGEST = re.compile(r"[a-f0-9]{64}")
_RUNTIME_WHEEL = re.compile(
    r"cryptography-([0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5})-cp311-abi3-macosx_11_0_x86_64\.whl"
)


class ManifestError(ValueError):
    """A public diagnostic that never includes rejected document contents."""


def version_tuple(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise ManifestError("Expected a bounded stable release version")
    return tuple(map(int, value.split(".")))


def runtime_wheel_version(name: str) -> str:
    match = _RUNTIME_WHEEL.fullmatch(name) if isinstance(name, str) else None
    if match is None:
        raise ManifestError("Unsupported managed runtime wheel")
    version_tuple(match[1])
    return match[1]


def _object(pairs):
    value = {}
    for key, content in pairs:
        if key in value:
            raise ManifestError("Duplicate update document field")
        value[key] = content
    return value


def _json(content: bytes) -> dict:
    if not isinstance(content, bytes) or len(content) > MAX_MANIFEST_BYTES:
        raise ManifestError("Update metadata exceeds its size budget")
    try:
        value = json.loads(content, object_pairs_hook=_object)
    except (ValueError, UnicodeError, RecursionError):
        raise ManifestError("Invalid update metadata document") from None
    if not isinstance(value, dict):
        raise ManifestError("Update metadata must be an object")
    return value


def _canonical(value: dict) -> bytes:
    try:
        content = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError):
        raise ManifestError("Invalid update metadata document") from None
    if len(content) > MAX_MANIFEST_BYTES:
        raise ManifestError("Update metadata exceeds its size budget")
    return content


@dataclass(frozen=True)
class Artifact:
    name: str
    size: int
    sha256: str

    def verify_file(self, path: Path) -> None:
        if path.is_symlink():
            raise ManifestError("A downloaded package cannot be a symbolic link")
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size != self.size:
                    raise ManifestError(
                        "Downloaded package size does not match its signed metadata"
                    )
                digest = hashlib.sha256()
                size = 0
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.size:
                        raise ManifestError("Downloaded package grew beyond its signed size")
                    digest.update(chunk)
            if size != self.size or digest.hexdigest() != self.sha256:
                raise ManifestError("Downloaded package does not match its signed digest")
        except OSError:
            raise ManifestError("Cannot verify the downloaded package file") from None


@dataclass(frozen=True)
class ServiceRelease:
    version: str
    repository: str
    commit: str
    created_at: str
    python_versions: tuple[str, ...]
    artifacts: tuple[Artifact, ...]
    lock_sha256: str
    migrations: tuple[tuple[str, str], ...]
    runtime_wheels: tuple[Artifact, ...] = ()

    @property
    def schema_sha256(self) -> str:
        return hashlib.sha256(_canonical(dict(self.migrations))).hexdigest()

    def is_newer_than(self, current: str) -> bool:
        return version_tuple(self.version) > version_tuple(current)


def validate_payload(value: dict, *, repository: str = DEFAULT_REPOSITORY) -> ServiceRelease:
    if not isinstance(repository, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", repository
    ):
        raise ManifestError("Invalid configured release repository")
    fields = {
        "kind",
        "protocol",
        "channel",
        "version",
        "repository",
        "commit",
        "created_at",
        "python_versions",
        "artifacts",
        "lock_sha256",
        "migrations",
        "runtime_wheels",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ManifestError("Unexpected service-update fields")
    if (
        value["kind"] != "mnemion-service-update"
        or type(value["protocol"]) is not int
        or value["protocol"] != 1
        or value["channel"] != "stable"
        or value["repository"] != repository
    ):
        raise ManifestError("Unsupported service-update protocol, repository or channel")
    version = value["version"]
    version_tuple(version)
    if not isinstance(value["commit"], str) or not re.fullmatch(r"[a-f0-9]{40}", value["commit"]):
        raise ManifestError("Invalid signed source commit")
    try:
        datetime.strptime(value["created_at"], "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        raise ManifestError("Invalid update creation timestamp") from None
    versions = value["python_versions"]
    if (
        not isinstance(versions, list)
        or not 1 <= len(versions) <= 10
        or any(not isinstance(p, str) or not re.fullmatch(r"3\.[1-9][0-9]?", p) for p in versions)
        or len(set(versions)) != len(versions)
    ):
        raise ManifestError("Invalid supported Python versions")
    artifacts = value["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise ManifestError("A service update needs its wheel and source package")
    expected = {f"mnemion-{version}-py3-none-any.whl", f"mnemion-{version}.tar.gz"}
    checked = []
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {"name", "size", "sha256"}:
            raise ManifestError("Invalid service-update artifact fields")
        if (
            not isinstance(item["name"], str)
            or item["name"] not in expected
            or type(item["size"]) is not int
            or not 0 < item["size"] <= MAX_PACKAGE_BYTES
            or not isinstance(item["sha256"], str)
            or not _DIGEST.fullmatch(item["sha256"])
        ):
            raise ManifestError("Invalid service-update artifact identity, size or digest")
        expected.remove(item["name"])
        checked.append(Artifact(**item))
    if not isinstance(value["lock_sha256"], str) or not _DIGEST.fullmatch(value["lock_sha256"]):
        raise ManifestError("Invalid dependency-lock digest")
    migrations = value["migrations"]
    if not isinstance(migrations, dict) or not 1 <= len(migrations) <= 256:
        raise ManifestError("Invalid migration inventory")
    for name, digest in migrations.items():
        if (
            not isinstance(name, str)
            or len(name) > 128
            or not re.fullmatch(r"[0-9]{3}_[a-z0-9_]+\.sql", name)
            or not isinstance(digest, str)
            or not _DIGEST.fullmatch(digest)
        ):
            raise ManifestError("Invalid migration name or digest")
    wheels = value["runtime_wheels"]
    if not isinstance(wheels, list) or len(wheels) > 1:
        raise ManifestError("Invalid managed runtime wheel inventory")
    checked_wheels = []
    for item in wheels:
        if not isinstance(item, dict) or set(item) != {"name", "size", "sha256"}:
            raise ManifestError("Invalid managed runtime wheel fields")
        runtime_wheel_version(item["name"])
        if (
            type(item["size"]) is not int
            or not 0 < item["size"] <= MAX_PACKAGE_BYTES
            or not isinstance(item["sha256"], str)
            or not _DIGEST.fullmatch(item["sha256"])
        ):
            raise ManifestError("Invalid managed runtime wheel size or digest")
        checked_wheels.append(Artifact(**item))
    return ServiceRelease(
        version,
        repository,
        value["commit"],
        value["created_at"],
        tuple(versions),
        tuple(checked),
        value["lock_sha256"],
        tuple(sorted(migrations.items())),
        tuple(checked_wheels),
    )


def verify_manifest(
    content: bytes, public_key: bytes, *, repository: str = DEFAULT_REPOSITORY
) -> ServiceRelease:
    envelope = _json(content)
    if set(envelope) != {"payload", "signature"}:
        raise ManifestError("Invalid signed update envelope")
    try:
        payload = base64.b64decode(envelope["payload"], validate=True)
        signature = base64.b64decode(envelope["signature"], validate=True)
        if len(signature) != 64 or len(public_key) != 32:
            raise ValueError("length")
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, SIGNATURE_DOMAIN + payload)
    except (ValueError, TypeError, InvalidSignature):
        raise ManifestError("Service update signature verification failed") from None
    return validate_payload(_json(payload), repository=repository)


def sign_manifest(
    payload: dict, private_key: bytes, *, repository: str = DEFAULT_REPOSITORY
) -> bytes:
    validate_payload(payload, repository=repository)
    content = _canonical(payload)
    try:
        signature = Ed25519PrivateKey.from_private_bytes(private_key).sign(
            SIGNATURE_DOMAIN + content
        )
    except (ValueError, TypeError):
        raise ManifestError("Invalid service-update signing key") from None
    return _canonical(
        {
            "payload": base64.b64encode(content).decode(),
            "signature": base64.b64encode(signature).decode(),
        }
    )
