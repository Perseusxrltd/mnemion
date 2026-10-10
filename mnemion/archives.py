"""Versioned local archives: verify every byte before publishing any state."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from .portable_paths import path_key, portable_part

MANIFEST = "manifest.json"
MAX_ARCHIVE_BYTES = 50 * 1024**3


def canonical_json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _member(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or ":" in name
        or "\x00" in name
        or path.is_absolute()
        or any(not portable_part(p) for p in name.split("/"))
    ):
        raise ValueError("Unsafe archive member")
    return name


def publish_file(staged: Path, output: Path) -> None:
    """Atomic, exclusive publication on the same filesystem; never clobber."""
    with staged.open("rb") as source:
        os.fsync(source.fileno())
    os.link(staged, output)
    if os.name != "nt":
        descriptor = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def private_json(output: Path, value: dict) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".mnemion-json-", dir=output.parent)
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(canonical_json(value) + b"\n")
            target.flush()
            os.fsync(target.fileno())
        publish_file(staged, output)
    finally:
        staged.unlink(missing_ok=True)


def write_archive(output: Path, members: dict[str, Path], metadata: dict) -> dict:
    output = Path(output)
    if output.exists():
        raise FileExistsError("Backup output already exists")
    if MANIFEST in members or len({path_key(n) for n in members}) != len(members):
        raise ValueError("Duplicate archive member")
    inventory = {}
    for name, path in sorted(members.items()):
        _member(name)
        if not path.is_file() or path.is_symlink():
            raise ValueError("Archive input must be a regular file")
        inventory[name] = {"size": path.stat().st_size, "sha256": file_hash(path)}
    if sum(item["size"] for item in inventory.values()) > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive exceeds the 50 GiB local archive limit")
    manifest = {**metadata, "files": inventory}
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".mnemion-archive-", dir=output.parent)
    os.close(descriptor)
    staged = Path(name)
    try:
        with zipfile.ZipFile(
            staged, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1
        ) as archive:
            for name, path in sorted(members.items()):
                archive.write(path, name)
            archive.writestr(MANIFEST, canonical_json(manifest))
        # A changing input is not a consistent backup. Verify the bytes actually
        # archived, not just the preliminary inventory.
        with verified_archive(staged, metadata["format"], metadata["version"]):
            pass
        publish_file(staged, output)
    finally:
        staged.unlink(missing_ok=True)
    return manifest


@contextmanager
def verified_archive(path: Path, format_name: str, version: int = 1):
    """Fully validate and unpack into an isolated directory, then yield it.

    Digests detect corruption, not an attacker who can replace both the payload
    and its manifest. Administrative database backups must come from a trusted
    backup location.
    """
    with tempfile.TemporaryDirectory(prefix="mnemion-verified-") as directory:
        root = Path(directory)
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                if (
                    MANIFEST not in names
                    or len(names) != len(set(path_key(n) for n in names))
                    or len(names) > 200_000
                    or archive.getinfo(MANIFEST).file_size > 64 * 1024**2
                ):
                    raise ValueError("Invalid archive manifest or duplicate members")
                manifest = json.loads(archive.read(MANIFEST))
                if (
                    not isinstance(manifest, dict)
                    or manifest.get("format") != format_name
                    or manifest.get("version") != version
                ):
                    raise ValueError("Unsupported archive format or version")
                inventory = manifest.get("files")
                if not isinstance(inventory, dict) or set(names) != {MANIFEST, *inventory}:
                    raise ValueError("Archive does not match its complete file manifest")
                if sum(i.file_size for i in archive.infolist()) > MAX_ARCHIVE_BYTES:
                    raise ValueError("Archive exceeds the 50 GiB local archive limit")
                for name, entry in inventory.items():
                    _member(name)
                    info = archive.getinfo(name)
                    if not isinstance(entry, dict) or info.file_size != entry.get("size"):
                        raise ValueError("Archive member size mismatch")
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(name) as source, target.open("xb") as destination:
                        shutil.copyfileobj(source, destination, 1024 * 1024)
                    if file_hash(target) != entry.get("sha256"):
                        raise ValueError("Archive member checksum mismatch")
        except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid or incomplete archive") from exc
        yield manifest, root
