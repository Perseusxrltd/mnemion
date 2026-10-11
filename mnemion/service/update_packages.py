"""Bounded package inspection before a managed service update can execute code."""

from __future__ import annotations

from contextlib import contextmanager
from email.parser import BytesParser
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import tempfile
import tomllib
import zipfile

from .update_manifest import ManifestError, ServiceRelease

MAX_ENTRIES = 20_000
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 32 * 1024 * 1024


def _name(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or len(value) > 1024
        or path.is_absolute()
        or value != path.as_posix()
        or any(part in ("", ".", "..") or len(part) > 255 for part in value.split("/"))
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
        or "\\" in value
        or ":" in value
    ):
        raise ManifestError("Unsafe service package path")
    return value


def _copy(source, destination: Path | None, size: int) -> str:
    if not 0 <= size <= MAX_MEMBER_BYTES:
        raise ManifestError("Service package member exceeds its size budget")
    digest = hashlib.sha256()
    count = 0
    output = None
    try:
        if destination is not None:
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            output = os.fdopen(descriptor, "wb")
        while chunk := source.read(min(1024 * 1024, size - count + 1)):
            count += len(chunk)
            if count > size:
                raise ManifestError("Service package member exceeds its declared size")
            digest.update(chunk)
            if output is not None:
                output.write(chunk)
        if count != size:
            raise ManifestError("Incomplete service package member")
    finally:
        if output is not None:
            output.close()
    return digest.hexdigest()


def _source(package: Path, destination: Path, version: str) -> dict[str, str]:
    inventory = {}
    names = set()
    expanded = 0
    prefix = f"mnemion-{version}/"
    with tarfile.open(package, "r|gz") as archive:
        for entry in archive:
            full_name = _name(entry.name.rstrip("/"))
            if full_name in names or len(names) >= MAX_ENTRIES:
                raise ManifestError("Duplicate or excessive service package entries")
            names.add(full_name)
            if not entry.isfile() and not entry.isdir():
                raise ManifestError("Service packages cannot contain links or special files")
            if full_name == prefix[:-1] and entry.isdir():
                continue
            if not full_name.startswith(prefix):
                raise ManifestError("Source package belongs to another release")
            relative = _name(full_name.removeprefix(prefix))
            if entry.isdir():
                continue
            expanded += entry.size
            if expanded > MAX_EXPANDED_BYTES:
                raise ManifestError("Expanded service package exceeds its size budget")
            with archive.extractfile(entry) as stream:
                inventory[relative] = _copy(stream, destination / relative, entry.size)
    return inventory


def _wheel(package: Path, version: str) -> tuple[dict[str, str], str]:
    inventory = {}
    names = set()
    expanded = 0
    requires_python = None
    metadata_path = f"mnemion-{version}.dist-info/METADATA"
    with zipfile.ZipFile(package) as archive:
        if len(archive.infolist()) > MAX_ENTRIES:
            raise ManifestError("Excessive service wheel entries")
        for entry in archive.infolist():
            name = _name(entry.filename.rstrip("/"))
            if name in names:
                raise ManifestError("Duplicate service wheel entry")
            names.add(name)
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or entry.flag_bits & 1:
                raise ManifestError("Service wheel contains a link, special or encrypted file")
            if entry.is_dir():
                continue
            expanded += entry.file_size
            if expanded > MAX_EXPANDED_BYTES:
                raise ManifestError("Expanded service wheel exceeds its size budget")
            with archive.open(entry) as stream:
                inventory[name] = _copy(stream, None, entry.file_size)
            if name == metadata_path:
                if entry.file_size > 1024 * 1024:
                    raise ManifestError("Service wheel metadata exceeds its size budget")
                metadata = BytesParser().parsebytes(archive.read(entry), headersonly=True)
                if metadata.get_all("Name") != ["mnemion"] or metadata.get_all("Version") != [
                    version
                ]:
                    raise ManifestError("Service wheel identity disagrees with its filename")
                if len(metadata.get_all("Requires-Python", [])) != 1:
                    raise ManifestError("Missing service wheel Python compatibility")
                requires_python = metadata["Requires-Python"]
    if requires_python is None:
        raise ManifestError("Service wheel lacks its release metadata")
    return inventory, requires_python


@contextmanager
def inspected_packages(artifacts: Path, release: ServiceRelease, *, parent: Path | None = None):
    """Yield an isolated source tree after checking bytes, code, lock and schema.

    Nothing is installed or imported from the candidate. The temporary tree is
    removed even when inspection or a caller's staging operation fails.
    """
    for artifact in release.artifacts:
        artifact.verify_file(artifacts / artifact.name)
    try:
        with tempfile.TemporaryDirectory(prefix="mnemion-service-review-", dir=parent) as name:
            source = Path(name)
            source.chmod(0o700)
            inventory = _source(
                artifacts / f"mnemion-{release.version}.tar.gz", source, release.version
            )
            wheel, requires_python = _wheel(
                artifacts / f"mnemion-{release.version}-py3-none-any.whl", release.version
            )
            source_code = {p: h for p, h in inventory.items() if p.startswith("mnemion/")}
            wheel_code = {p: h for p, h in wheel.items() if p.startswith("mnemion/")}
            if not source_code or source_code != wheel_code:
                raise ManifestError("Source and wheel contain different service code or Studio")
            if inventory.get("uv.lock") != release.lock_sha256:
                raise ManifestError("Dependency lock does not match signed release metadata")
            migrations = {
                p.removeprefix("mnemion/service/migrations/"): h
                for p, h in source_code.items()
                if p.startswith("mnemion/service/migrations/") and p.endswith(".sql")
            }
            if migrations != dict(release.migrations):
                raise ManifestError("Package migrations do not match signed release metadata")
            project = tomllib.loads((source / "pyproject.toml").read_text())["project"]
            if project["name"] != "mnemion" or project["version"] != release.version:
                raise ManifestError("Source project identity disagrees with signed metadata")
            if set(project["requires-python"].replace(" ", "").split(",")) != set(
                requires_python.replace(" ", "").split(",")
            ):
                raise ManifestError("Source and wheel Python compatibility disagree")
            yield source
    except (
        OSError,
        EOFError,
        tarfile.TarError,
        zipfile.BadZipFile,
        KeyError,
        UnicodeError,
    ) as error:
        raise ManifestError("Cannot inspect the complete service package") from error


def copy_inspected_source(artifacts: Path, release: ServiceRelease, destination: Path) -> None:
    """Copy into an exclusively reserved staging tree, never an installed release."""
    with inspected_packages(artifacts, release, parent=destination.parent) as source:
        try:
            destination.mkdir(mode=0o700)
        except FileExistsError:
            raise ManifestError("Service staging destination already exists") from None
        try:
            shutil.copytree(source, destination, dirs_exist_ok=True)
        except BaseException:
            shutil.rmtree(destination)
            raise


def verify_installed_package(artifacts: Path, release: ServiceRelease, package: Path) -> None:
    """Recheck installed application files before each managed runtime handoff."""
    wheel_artifact = next(item for item in release.artifacts if item.name.endswith(".whl"))
    wheel_artifact.verify_file(artifacts / wheel_artifact.name)
    inventory, _ = _wheel(artifacts / wheel_artifact.name, release.version)
    expected = {
        p.removeprefix("mnemion/"): h for p, h in inventory.items() if p.startswith("mnemion/")
    }
    actual = {}
    if package.is_symlink() or not package.is_dir():
        raise ManifestError("Managed runtime package is missing or unsafe")
    for path in package.rglob("*"):
        if path.is_symlink():
            raise ManifestError("Managed runtime application files cannot be symlinks")
        if path.is_file() and "__pycache__" not in path.relative_to(package).parts:
            relative = path.relative_to(package).as_posix()
            if relative not in expected:
                raise ManifestError("Unexpected file in the managed runtime application")
            with path.open("rb") as stream:
                actual[relative] = _copy(stream, None, path.stat().st_size)
    if actual != expected:
        raise ManifestError("Installed application differs from the signed service package")
