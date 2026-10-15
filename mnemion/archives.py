"""Versioned local archives: verify every byte before publishing any state."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import tempfile
import sys
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Callable

from .portable_paths import path_key, portable_part
from .local_state import temporary_directory as private_temporary_directory

MANIFEST = "manifest.json"
MAX_ARCHIVE_BYTES = 50 * 1024**3


def canonical_json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _checkpoint(check_cancelled: Callable[[], None] | None) -> None:
    if check_cancelled is not None:
        check_cancelled()


def _copy(source, destination, check_cancelled=None) -> None:
    while True:
        _checkpoint(check_cancelled)
        block = source.read(1024 * 1024)
        if not block:
            return
        destination.write(block)


def file_hash(path: Path, *, check_cancelled=None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            _checkpoint(check_cancelled)
            block = source.read(1024 * 1024)
            if not block:
                break
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


def _rename_exclusive(staged: Path, output: Path) -> None:
    """Publish on filesystems without hard links, without a check/rename race."""
    if os.name == "nt":
        # Windows rename refuses an existing destination, including on exFAT.
        os.rename(staged, output)
        return
    import ctypes

    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        function = getattr(library, "renamex_np", None)
        arguments = [os.fsencode(staged), os.fsencode(output), 4]  # RENAME_EXCL
        signature = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    else:
        function = getattr(library, "renameat2", None)
        arguments = [-100, os.fsencode(staged), -100, os.fsencode(output), 1]  # RENAME_NOREPLACE
        signature = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    if function is None:
        raise OSError(errno.ENOTSUP, "This filesystem cannot publish backups exclusively")
    function.argtypes, function.restype = signature, ctypes.c_int
    if function(*arguments) != 0:
        error = ctypes.get_errno()
        raise OSError(error, "The backup could not be published exclusively", str(output))


def publish_file(staged: Path, output: Path) -> None:
    """Atomic, exclusive publication on the same filesystem; never clobber."""
    # Windows' CRT cannot flush a read-only descriptor (_commit reports EBADF).
    # Reopen the complete staged file for writing without truncating any bytes;
    # failure still prevents the exclusive link from publishing the backup.
    with staged.open("r+b") as source:
        os.fsync(source.fileno())
    try:
        os.link(staged, output)
    except OSError as error:
        if error.errno not in {
            errno.EPERM,
            errno.EOPNOTSUPP,
            errno.ENOSYS,
            errno.EXDEV,
            errno.EINVAL,
        }:
            raise
        _rename_exclusive(staged, output)
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


def write_archive(
    output: Path,
    members: dict[str, Path],
    metadata: dict,
    *,
    check_cancelled=None,
    temporary_directory: Path | None = None,
) -> dict:
    _checkpoint(check_cancelled)
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
        inventory[name] = {
            "size": path.stat().st_size,
            "sha256": file_hash(path, check_cancelled=check_cancelled),
        }
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
                _checkpoint(check_cancelled)
                info = zipfile.ZipInfo.from_file(path, name)
                info.compress_type = zipfile.ZIP_DEFLATED
                # ZipInfo's public compress_level property requires Python 3.13.
                # This is the same field ZipFile.write uses on supported 3.11/3.12.
                info._compresslevel = 1
                with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
                    _copy(source, target, check_cancelled)
            archive.writestr(MANIFEST, canonical_json(manifest))
        # A changing input is not a consistent backup. Verify the bytes actually
        # archived, not just the preliminary inventory.
        with verified_archive(
            staged,
            metadata["format"],
            metadata["version"],
            check_cancelled=check_cancelled,
            temporary_directory=temporary_directory,
        ):
            pass
        _checkpoint(check_cancelled)
        publish_file(staged, output)
    finally:
        staged.unlink(missing_ok=True)
    return manifest


@contextmanager
def verified_archive(
    path: Path,
    format_name: str,
    version: int = 1,
    *,
    check_cancelled=None,
    temporary_directory: Path | None = None,
):
    """Fully validate and unpack into an isolated directory, then yield it.

    Digests detect corruption, not an attacker who can replace both the payload
    and its manifest. Administrative database backups must come from a trusted
    backup location.
    """
    _checkpoint(check_cancelled)
    with private_temporary_directory(prefix="mnemion-verified-", dir=temporary_directory) as root:
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
                unpacked_bytes = sum(i.file_size for i in archive.infolist())
                if unpacked_bytes > MAX_ARCHIVE_BYTES:
                    raise ValueError("Archive exceeds the 50 GiB local archive limit")
                if shutil.disk_usage(root).free < unpacked_bytes + 64 * 1024**2:
                    raise ValueError("Free more disk space to verify this archive")
                for name, entry in inventory.items():
                    _checkpoint(check_cancelled)
                    _member(name)
                    info = archive.getinfo(name)
                    if not isinstance(entry, dict) or info.file_size != entry.get("size"):
                        raise ValueError("Archive member size mismatch")
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(name) as source, target.open("xb") as destination:
                        _copy(source, destination, check_cancelled)
                    if file_hash(target, check_cancelled=check_cancelled) != entry.get("sha256"):
                        raise ValueError("Archive member checksum mismatch")
        except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid or incomplete archive") from exc
        _checkpoint(check_cancelled)
        yield manifest, root
