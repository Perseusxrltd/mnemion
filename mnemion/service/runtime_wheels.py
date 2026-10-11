"""Inspect signed native dependency wheels without executing their contents."""

from __future__ import annotations

from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import platform
import re
import stat
import tomllib
import zipfile

from .update_manifest import Artifact, ManifestError, ServiceRelease, runtime_wheel_version
from .update_packages import MAX_ENTRIES, MAX_EXPANDED_BYTES, _copy, _name


def selected_wheels(release: ServiceRelease) -> tuple[Artifact, ...]:
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        return ()
    if not release.runtime_wheels:
        raise ManifestError("This release lacks its signed Intel Mac runtime wheel")
    try:
        major = int(platform.mac_ver()[0].split(".")[0])
    except ValueError:
        raise ManifestError("Cannot determine the Intel Mac runtime compatibility") from None
    if major < 11:
        raise ManifestError("The managed Intel Mac runtime requires macOS 11 or newer")
    return release.runtime_wheels


def inspect_wheel(path: Path, artifact: Artifact, lock: Path) -> dict[str, str]:
    artifact.verify_file(path)
    version = runtime_wheel_version(artifact.name)
    prefix = f"cryptography-{version}.dist-info/"
    try:
        packages = tomllib.loads(lock.read_text())["package"]
        locked = [item for item in packages if item["name"] == "cryptography"]
        if len(locked) != 1 or locked[0]["version"] != version:
            raise ManifestError("Native dependency differs from the signed dependency lock")
        source_hash = locked[0]["sdist"]["hash"]
        if not isinstance(source_hash, str) or not re.fullmatch(
            r"sha256:[a-f0-9]{64}", source_hash
        ):
            raise ManifestError("Native dependency source lacks a locked hash")
        inventory = {}
        names = set()
        expanded = 0
        with zipfile.ZipFile(path) as archive:
            if len(archive.infolist()) > MAX_ENTRIES:
                raise ManifestError("Excessive native dependency entries")
            for item in archive.infolist():
                name = _name(item.filename.rstrip("/"))
                if name in names or not name.startswith(("cryptography/", prefix)):
                    raise ManifestError("Unexpected native dependency path")
                names.add(name)
                if (
                    stat.S_IFMT(item.external_attr >> 16) not in (0, stat.S_IFREG, stat.S_IFDIR)
                    or item.flag_bits & 1
                ):
                    raise ManifestError("Native dependency contains a link or special file")
                if item.is_dir():
                    continue
                expanded += item.file_size
                if expanded > MAX_EXPANDED_BYTES:
                    raise ManifestError("Native dependency exceeds its expanded size budget")
                with archive.open(item) as stream:
                    inventory[name] = _copy(stream, None, item.file_size)

            def document(name):
                item = archive.getinfo(prefix + name)
                if item.file_size > 1024 * 1024:
                    raise ManifestError("Native dependency metadata exceeds its size budget")
                return archive.read(item)

            metadata = BytesParser().parsebytes(document("METADATA"), headersonly=True)
            wheel = BytesParser().parsebytes(document("WHEEL"), headersonly=True)
            provenance = json.loads(document("mnemion-build.json"))
            if not isinstance(provenance, dict):
                raise ManifestError("Native dependency lacks its reviewed build provenance")
            if metadata.get_all("Name") != ["cryptography"] or metadata.get_all("Version") != [
                version
            ]:
                raise ManifestError("Native dependency metadata disagrees with its filename")
            if wheel.get_all("Tag") != ["cp311-abi3-macosx_11_0_x86_64"] or wheel.get_all(
                "Root-Is-Purelib"
            ) != ["false"]:
                raise ManifestError("Native dependency has incompatible wheel tags")
            if (
                provenance.get("format") != 1
                or provenance.get("cryptography_version") != version
                or provenance.get("cryptography_source_sha256")
                != source_hash.removeprefix("sha256:")
                or provenance.get("static_openssl") is not True
                or provenance.get("target") != "macosx_11_0_x86_64"
                or not re.fullmatch(
                    r"[0-9]+\.[0-9]+\.[0-9]+", provenance.get("openssl_version", "")
                )
                or not re.fullmatch(r"[a-f0-9]{64}", provenance.get("openssl_source_sha256", ""))
                or not any(
                    name.startswith("cryptography/") and name.endswith(".so") for name in inventory
                )
                or prefix + "licenses/LICENSE.OpenSSL" not in inventory
            ):
                raise ManifestError("Native dependency lacks its reviewed build provenance")
        return inventory
    except (OSError, KeyError, TypeError, ValueError, zipfile.BadZipFile) as error:
        if isinstance(error, ManifestError):
            raise
        raise ManifestError("Cannot inspect the signed native dependency") from error


def verify_installed(artifacts: Path, release: ServiceRelease, package: Path, lock: Path) -> None:
    for artifact in selected_wheels(release):
        if (
            lock.is_symlink()
            or hashlib.sha256(lock.read_bytes()).hexdigest() != release.lock_sha256
        ):
            raise ManifestError("Managed native dependency lock changed after staging")
        inventory = inspect_wheel(artifacts / artifact.name, artifact, lock)
        expected = {p: h for p, h in inventory.items() if p.startswith("cryptography/")}
        actual = {}
        directory = package.parent / "cryptography"
        if directory.is_symlink() or not directory.is_dir():
            raise ManifestError("Managed native dependency is missing or unsafe")
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise ManifestError("Managed native dependency cannot contain links")
            if path.is_file() and "__pycache__" not in path.relative_to(directory).parts:
                relative = path.relative_to(package.parent).as_posix()
                if relative not in expected:
                    raise ManifestError("Unexpected installed native dependency file")
                with path.open("rb") as stream:
                    actual[relative] = _copy(stream, None, path.stat().st_size)
        if actual != expected:
            raise ManifestError("Installed native dependency differs from its signed wheel")
