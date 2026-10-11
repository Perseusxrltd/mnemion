"""Build a service-update envelope from already verified release packages."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tomllib

from mnemion.service.update_manifest import (
    DEFAULT_REPOSITORY,
    MAX_PACKAGE_BYTES,
    ManifestError,
    sign_manifest,
    validate_payload,
    verify_manifest,
)
from mnemion.service.update_packages import inspected_packages
from mnemion.service.update_trust import SERVICE_UPDATE_PUBLIC_KEY
from mnemion.service.runtime_wheels import inspect_wheel


def _digest(path: Path, maximum: int, *, allow_empty: bool = False) -> tuple[int, str]:
    if path.is_symlink():
        raise ManifestError("A release input cannot be a symbolic link")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or not (0 if allow_empty else 1) <= info.st_size <= maximum
        ):
            raise ManifestError("Release input is not a bounded regular file")
        digest = hashlib.sha256()
        size = 0
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            if size > maximum:
                raise ManifestError("Release input exceeded its size budget")
            digest.update(chunk)
    if size != info.st_size:
        raise ManifestError("Release input changed while being signed")
    return size, digest.hexdigest()


def payload(
    root: Path,
    artifacts: Path,
    commit: str,
    *,
    repository: str = DEFAULT_REPOSITORY,
    created_at: datetime | None = None,
) -> dict:
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    # A new interpreter range needs a corresponding native/dependency review.
    if project["requires-python"].replace(" ", "") != ">=3.12,<3.15":
        raise ManifestError("Review service-update Python compatibility before signing this range")
    version = project["version"]
    packages = []
    for name in (f"mnemion-{version}.tar.gz", f"mnemion-{version}-py3-none-any.whl"):
        size, digest = _digest(artifacts / name, MAX_PACKAGE_BYTES)
        packages.append({"name": name, "size": size, "sha256": digest})
    runtime_wheels = []
    for path in sorted(artifacts.glob("cryptography-*.whl")):
        size, digest = _digest(path, MAX_PACKAGE_BYTES)
        runtime_wheels.append({"name": path.name, "size": size, "sha256": digest})
    migrations = {}
    for path in sorted((root / "mnemion/service/migrations").glob("*.sql")):
        _, migrations[path.name] = _digest(path, 8 * 1024 * 1024)
    _, lock = _digest(root / "uv.lock", 32 * 1024 * 1024)
    created_at = created_at or datetime.now(timezone.utc)
    if created_at.utcoffset() is None:
        raise ManifestError("Use an explicit timezone for service-update metadata")
    return {
        "kind": "mnemion-service-update",
        "protocol": 1,
        "channel": "stable",
        "version": version,
        "repository": repository,
        "commit": commit,
        "created_at": created_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python_versions": ["3.12", "3.13", "3.14"],
        "artifacts": packages,
        "runtime_wheels": runtime_wheels,
        "lock_sha256": lock,
        "migrations": migrations,
    }


def signed_document(
    root: Path,
    artifacts: Path,
    commit: str,
    private_key: bytes,
    public_key: bytes,
    *,
    repository: str = DEFAULT_REPOSITORY,
    created_at: datetime | None = None,
) -> bytes:
    value = payload(root, artifacts, commit, repository=repository, created_at=created_at)
    release = validate_payload(value, repository=repository)
    for artifact in release.runtime_wheels:
        inspect_wheel(artifacts / artifact.name, artifact, root / "uv.lock")
    with inspected_packages(artifacts, release) as source:
        if (source / "pyproject.toml").read_bytes() != (root / "pyproject.toml").read_bytes():
            raise ManifestError("Packaged project differs from the reviewed checkout")
        for path in (source / "mnemion").rglob("*"):
            if path.is_file():
                relative = path.relative_to(source)
                reviewed = root / relative
                if (
                    reviewed.is_symlink()
                    or not reviewed.is_file()
                    or _digest(reviewed, MAX_PACKAGE_BYTES, allow_empty=True)
                    != _digest(path, MAX_PACKAGE_BYTES, allow_empty=True)
                ):
                    raise ManifestError("Packaged service differs from the reviewed checkout")
    document = sign_manifest(value, private_key, repository=repository)
    # Fail if the release secret does not match the public key installed in clients.
    verify_manifest(document, public_key, repository=repository)
    return document


def signing_key_from_environment() -> bytes:
    """Read the designated release secret without printing or forwarding it."""
    try:
        key = base64.b64decode(os.environ["MNEMION_SERVICE_UPDATE_PRIVATE_KEY"], validate=True)
        if len(key) != 32:
            raise ValueError("length")
        return key
    except (KeyError, ValueError, TypeError):
        raise ManifestError(
            "Configure the service-update signing secret before publishing"
        ) from None


def write_document(path: Path, document: bytes) -> None:
    # The envelope is public. The private key is neither serialized nor logged.
    json.loads(document)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as output:
        output.write(document + b"\n")


def verify_document(root: Path, artifacts: Path, *, public_key: bytes = SERVICE_UPDATE_PUBLIC_KEY):
    path = artifacts / "service-update.json"
    from mnemion.service.update_manifest import MAX_MANIFEST_BYTES

    _digest(path, MAX_MANIFEST_BYTES)
    release = verify_manifest(path.read_bytes(), public_key)
    expected = payload(root, artifacts, release.commit)
    if release != validate_payload({**expected, "created_at": release.created_at}):
        raise ManifestError("Signed service update differs from the release inputs")
    with inspected_packages(artifacts, release):
        pass
    for artifact in release.runtime_wheels:
        inspect_wheel(artifacts / artifact.name, artifact, root / "uv.lock")
    return release


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("sign", "verify"))
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--commit")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    try:
        if args.action == "sign":
            actual_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
            ).stdout.strip()
            if args.commit != actual_commit:
                raise ManifestError("The signed commit must be the checked-out release commit")
            subprocess.run(
                ["git", "diff", "--quiet", "HEAD", "--", "mnemion", "pyproject.toml", "uv.lock"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            document = signed_document(
                root,
                args.artifacts,
                args.commit,
                signing_key_from_environment(),
                SERVICE_UPDATE_PUBLIC_KEY,
            )
            write_document(args.artifacts / "service-update.json", document)
        release = verify_document(root, args.artifacts)
        print(json.dumps({"version": release.version, "commit": release.commit, "verified": True}))
        return 0
    except (ManifestError, OSError, ValueError, subprocess.SubprocessError):
        # No private key, rejected document, package content or subprocess output.
        print(json.dumps({"error": "Service update signing or verification failed"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
