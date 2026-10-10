"""Validate immutable release versions and complete architecture-specific feeds."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path


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

    if version != __version__:
        raise ValueError("Python versions disagree")
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
    files = [path for path in args.artifacts.iterdir() if path.name != "SHA256SUMS.txt"]
    for architecture in ("x64", "arm64"):
        for suffix in ("", "-mac", "-linux" if architecture == "x64" else "-linux-arm64"):
            feed = args.artifacts / f"latest-{architecture}{suffix}.yml"
            verify_feed(feed, args.artifacts, version)
    checksums = []
    for path in sorted(files):
        if path.is_symlink() or not path.is_file():
            raise ValueError("Release assets must be regular files")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        checksums.append(f"{digest.hexdigest()}  {path.name}")
    (args.artifacts / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n")
    print(f"Validated Mnemion {version}: {len(files)} assets and six update feeds")


if __name__ == "__main__":
    main()
