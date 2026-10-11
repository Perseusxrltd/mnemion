"""Validate immutable release versions and complete architecture-specific feeds."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from xml.etree import ElementTree as ET


def verify_ed25519(archive: Path, signature: str, public_key: str) -> None:
    if archive.is_symlink() or not archive.is_file() or not 0 < archive.stat().st_size <= 1024**3:
        raise ValueError("Missing, unsafe or oversized signed update archive")
    try:
        if (
            len(base64.b64decode(signature, validate=True)) != 64
            or len(base64.b64decode(public_key, validate=True)) != 32
        ):
            raise ValueError("Invalid signature length")
    except (ValueError, TypeError) as error:
        raise ValueError("Invalid Ed25519 signing metadata") from error
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node 22+ is required for release-signature verification")
    result = subprocess.run(
        [
            node,
            str(Path(__file__).with_name("verify-mac-signature.mjs")),
            str(archive),
            public_key,
            signature,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise ValueError("Update archive signature does not match the installed public key")


def verify_sparkle_feed(
    feed: Path, artifacts: Path, version: str, architecture: str, public_key: str
) -> None:
    if architecture not in {"x64", "arm64"}:
        raise ValueError("Invalid update architecture")
    if feed.is_symlink() or not feed.is_file() or feed.stat().st_size > 100_000:
        raise ValueError("Missing, unsafe or oversized macOS update feed")
    content = feed.read_bytes()
    if b"<!DOCTYPE" in content or b"<!ENTITY" in content:
        raise ValueError("Update feed declarations are not allowed")
    try:
        document = ET.fromstring(content)
    except ET.ParseError as error:
        raise ValueError("Malformed macOS update feed") from error
    if document.tag != "rss" or document.get("version") != "2.0":
        raise ValueError("Invalid macOS update feed")
    items = document.findall("./channel/item")
    if len(items) != 1:
        raise ValueError("A release feed must contain exactly one version")
    item = items[0]
    ns = "{http://www.andymatuschak.org/xml-namespaces/sparkle}"
    if (
        item.findtext(ns + "version") != version
        or item.findtext(ns + "shortVersionString") != version
    ):
        raise ValueError("Wrong version in the macOS update feed")
    if item.findtext(ns + "minimumSystemVersion") != "13.0":
        raise ValueError("The macOS minimum version does not match the application")
    enclosures = item.findall("enclosure")
    if len(enclosures) != 1:
        raise ValueError("A macOS release requires one signed full archive")
    enclosure = enclosures[0]
    filename = f"Mnemion-Studio-{version}-macos-{architecture}.zip"
    expected = f"https://github.com/Perseusxrltd/mnemion/releases/download/v{version}/{filename}"
    if enclosure.get("url") != expected or enclosure.get("type") != "application/octet-stream":
        raise ValueError("The macOS archive URL does not match the immutable release")
    archive = artifacts / filename
    if (
        archive.is_symlink()
        or not archive.is_file()
        or enclosure.get("length") != str(archive.stat().st_size)
    ):
        raise ValueError("The macOS update archive size does not match")
    verify_ed25519(archive, enclosure.get(ns + "edSignature", ""), public_key)


def verify_feed(feed: Path, artifacts: Path, version: str) -> None:
    import yaml

    if not feed.is_file() or feed.stat().st_size > 100_000:
        raise ValueError(f"Missing or oversized update feed: {feed.name}")
    data = yaml.safe_load(feed.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != version:
        raise ValueError(f"Wrong version in {feed.name}")
    entries = data.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"Missing payload list in {feed.name}")
    hashes = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid update payload entry")
        name = entry.get("url", "")
        if not isinstance(name, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._+-]{0,254}", name
        ):
            raise ValueError("Update payloads must be local release filenames")
        path = artifacts / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing or unsafe update payload: {name}")
        with path.open("rb") as stream:
            digest = base64.b64encode(hashlib.file_digest(stream, "sha512").digest()).decode(
                "ascii"
            )
        if entry.get("sha512") != digest or entry.get("size") != path.stat().st_size:
            raise ValueError(f"Update payload hash or size mismatch: {name}")
        hashes[name] = digest
    if data.get("path") not in hashes or data.get("sha512") != hashes[data["path"]]:
        raise ValueError(f"Legacy update pointer disagrees in {feed.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("A stable version is required")
    from mnemion.version import __version__
    from deploy.release_targets import release_targets

    if version != __version__:
        raise ValueError("Python versions disagree")
    targets = release_targets(version)
    platforms = list(targets)
    notes = root / "docs" / "releases" / f"{version}.md"
    if not notes.is_file() or not notes.read_text(encoding="utf-8").startswith(
        f"# Mnemion {version}"
    ):
        raise ValueError("Add release notes for this version before shipping")
    roadmap = (root / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    if f"Current distribution: **{version}**" not in roadmap:
        raise ValueError("Review and update the roadmap for this release")
    client_version = tomllib.loads((root / "studio/client/pyproject.toml").read_text())["project"][
        "version"
    ]
    if client_version != version:
        raise ValueError("Desktop Python client version disagrees")
    for name in ("packages/client", "studio/frontend", "studio/electron"):
        for filename in ("package.json", "package-lock.json"):
            if json.loads((root / name / filename).read_text())["version"] != version:
                raise ValueError(f"Version mismatch: {name}/{filename}")
    if args.artifacts is None:
        print(f"Validated Mnemion {version}: package versions, release notes and roadmap")
        return
    from deploy.bundle_studio import verify_python_distributions

    verify_python_distributions(args.artifacts, version)
    if tuple(map(int, version.split("."))) >= (4, 0, 8):
        from deploy.service_update_manifest import verify_document

        verify_document(root, args.artifacts)
    files = [path for path in args.artifacts.iterdir() if path.name != "SHA256SUMS.txt"]
    for architecture in ("x64", "arm64"):
        suffixes = {
            "windows": "",
            "macos": "-mac",
            "linux": "-linux" if architecture == "x64" else "-linux-arm64",
        }
        for platform in platforms:
            if architecture not in targets[platform]:
                continue
            extension = {"windows": "exe", "macos": "dmg", "linux": "AppImage"}[platform]
            artifact_arch = (
                "x86_64" if platform == "linux" and architecture == "x64" else architecture
            )
            installer = (
                args.artifacts / f"Mnemion-Studio-{version}-{platform}-{artifact_arch}.{extension}"
            )
            if installer.is_symlink() or not installer.is_file() or installer.stat().st_size <= 0:
                raise ValueError(f"Missing or unsafe release installer: {installer.name}")
            suffix = suffixes[platform]
            feed = args.artifacts / f"latest-{architecture}{suffix}.yml"
            verify_feed(feed, args.artifacts, version)
        if architecture in targets.get("macos", []):
            public_key = json.loads((root / "studio/electron/native/sparkle.json").read_text())[
                "publicKey"
            ]
            verify_sparkle_feed(
                args.artifacts / f"latest-{architecture}-mac.xml",
                args.artifacts,
                version,
                architecture,
                public_key,
            )
        if architecture in targets.get("windows", []):
            node = shutil.which("node")
            if node is None:
                raise RuntimeError("Node 22+ is required for Windows signature verification")
            verified = subprocess.run(
                [
                    node,
                    str(root / "deploy/windows_updates.mjs"),
                    "verify",
                    "--artifacts",
                    str(args.artifacts.resolve()),
                    "--arch",
                    architecture,
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if verified.returncode:
                raise ValueError("Windows update manifest does not authenticate the installer")
    checksums = []
    for path in sorted(files):
        if path.is_symlink() or not path.is_file():
            raise ValueError("Release assets must be regular files")
        native = re.fullmatch(
            rf"Mnemion-Studio-{re.escape(version)}-(windows|macos|linux)-(x64|arm64|x86_64|amd64)\.(exe|dmg|zip|AppImage|deb)(\.blockmap)?",
            path.name,
        )
        if native:
            platform, architecture = native.group(1), native.group(2)
            architecture = "x64" if architecture in {"x86_64", "amd64"} else architecture
            if architecture not in targets.get(platform, []):
                raise ValueError("An unselected native installer cannot be published")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        checksums.append(f"{digest.hexdigest()}  {path.name}")
    (args.artifacts / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n")
    print(f"Validated Mnemion {version}: {len(files)} assets for {', '.join(platforms)}")


if __name__ == "__main__":
    main()
