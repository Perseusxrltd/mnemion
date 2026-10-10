"""Maintain the public website's fallback from a verified, published GitHub release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

REPOSITORY = "Perseusxrltd/mnemion"
ORIGIN = f"https://github.com/{REPOSITORY}"
API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_BYTES = 512 * 1024
TAG = re.compile(r"v(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})")
FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,254}")
DIGEST = re.compile(r"sha256:[a-f0-9]{64}")


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url: str, *, api: bool = False) -> bytes:
    """Bound the transfer and never forward API credentials to an asset host."""
    opener = build_opener(NoRedirects())
    deadline = time.monotonic() + 45
    for _ in range(4):
        target = urlsplit(url)
        hosts = (
            {"api.github.com"} if api else {"github.com", "release-assets.githubusercontent.com"}
        )
        if (
            target.scheme != "https"
            or target.hostname not in hosts
            or target.username is not None
            or target.password is not None
            or target.port not in {None, 443}
            or target.fragment
        ):
            raise ValueError("Release lookup left the approved GitHub hosts")
        headers = {"User-Agent": "Mnemion-release-publisher", "Accept-Encoding": "identity"}
        if api:
            headers.update(
                {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
            )
            if token := os.environ.get("GH_TOKEN"):
                headers["Authorization"] = f"Bearer {token}"
        try:
            response = opener.open(Request(url, headers=headers), timeout=15)
        except HTTPError as error:
            location = error.headers.get("Location")
            status = error.code
            error.close()
            if not api and status in {301, 302, 303, 307, 308} and location:
                url = location
                continue
            raise RuntimeError(f"Release lookup failed (HTTP {status})") from None
        with response:
            declared = response.headers.get("Content-Length")
            if declared is not None and (
                not re.fullmatch(r"[0-9]{1,9}", declared) or int(declared) > MAX_BYTES
            ):
                raise ValueError("Release metadata exceeds its size limit")
            result = bytearray()
            while chunk := response.read(16 * 1024):
                result.extend(chunk)
                if len(result) > MAX_BYTES or time.monotonic() > deadline:
                    raise ValueError("Release metadata exceeds its transfer limit")
            return bytes(result)
    raise ValueError("Too many release redirects")


def version(tag: str) -> tuple[int, int, int]:
    match = TAG.fullmatch(tag) if isinstance(tag, str) else None
    if not match or int(match[1]) < 4:
        raise ValueError("A stable Mnemion v1 distribution (4.x or newer) is required")
    return tuple(map(int, match.groups()))


def manifest(release: dict, checksums: bytes) -> dict:
    """Cross-check GitHub's uploaded-asset digests against the published inventory."""
    if (
        not isinstance(release, dict)
        or release.get("draft") is not False
        or release.get("prerelease") is not False
    ):
        raise ValueError("Only published stable releases can update the website")
    tag = release.get("tag_name")
    version(tag)
    if release.get("html_url") != f"{ORIGIN}/releases/tag/{tag}":
        raise ValueError("Release belongs to another repository")
    published = release.get("published_at")
    if not isinstance(published, str) or len(published) > 40:
        raise ValueError("Release has no publication date")
    try:
        date = datetime.fromisoformat(published)
    except ValueError:
        raise ValueError("Release has an invalid publication date") from None
    if date.tzinfo is None:
        raise ValueError("Release publication date must include its timezone")
    assets = release.get("assets")
    if not isinstance(assets, list) or not 1 <= len(assets) <= 100:
        raise ValueError("Invalid release asset inventory")
    inventory = {}
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError("Invalid release asset")
        name = asset.get("name")
        if (
            not isinstance(name, str)
            or not FILENAME.fullmatch(name)
            or name in inventory
            or asset.get("state") != "uploaded"
            or type(asset.get("size")) is not int
            or not 0 < asset["size"] <= 2 * 1024**3
            or not isinstance(asset.get("digest"), str)
            or not DIGEST.fullmatch(asset["digest"])
            or asset.get("browser_download_url") != f"{ORIGIN}/releases/download/{tag}/{name}"
        ):
            raise ValueError("Unsafe, incomplete or duplicate release asset")
        inventory[name] = {
            key: asset[key] for key in ("name", "size", "state", "digest", "browser_download_url")
        }
    checksum_asset = inventory.get("SHA256SUMS.txt")
    if not checksum_asset or not 0 < len(checksums) <= MAX_BYTES:
        raise ValueError("Published checksums are required")
    if (
        checksum_asset["size"] != len(checksums)
        or checksum_asset["digest"] != "sha256:" + hashlib.sha256(checksums).hexdigest()
    ):
        raise ValueError("Published checksum file does not match GitHub's digest")
    listed = {}
    for line in checksums.decode("utf-8", errors="strict").splitlines():
        match = re.fullmatch(r"([a-f0-9]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]{0,254})", line)
        if not match or match[2] in listed:
            raise ValueError("Malformed or duplicate published checksum")
        listed[match[2]] = "sha256:" + match[1]
    if set(listed) != set(inventory) - {"SHA256SUMS.txt"} or any(
        inventory[name]["digest"] != digest for name, digest in listed.items()
    ):
        raise ValueError("Published asset inventory or digest disagrees with its checksums")

    available = 0
    for platform, extension in (("windows", "exe"), ("macos", "dmg"), ("linux", "AppImage")):
        for arch in ("x64", "arm64"):
            artifact_arch = "x86_64" if platform == "linux" and arch == "x64" else arch
            installer = f"Mnemion-Studio-{tag[1:]}-{platform}-{artifact_arch}.{extension}"
            if installer not in inventory:
                continue
            required = {
                "windows": [f"latest-{arch}.yml", f"latest-{arch}-windows.json"],
                "macos": [
                    f"Mnemion-Studio-{tag[1:]}-macos-{arch}.zip",
                    f"latest-{arch}-mac.yml",
                    f"latest-{arch}-mac.xml",
                ],
                "linux": [f"latest-{arch}-linux{'-arm64' if arch == 'arm64' else ''}.yml"],
            }[platform]
            if not all(name in inventory for name in required):
                raise ValueError("An installer is missing its required update assets")
            available += 1
    if not available:
        raise ValueError("No complete native release is available")
    return {
        "schema": 1,
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "html_url": release["html_url"],
        "published_at": published,
        "assets": [inventory[name] for name in sorted(inventory)],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("deploy/published-release.json"))
    args = parser.parse_args()
    release = json.loads(fetch(API, api=True))
    # Validate tag and construct the only checksum URL we will ever request.
    tag = release.get("tag_name") if isinstance(release, dict) else None
    version(tag)
    data = manifest(release, fetch(f"{ORIGIN}/releases/download/{tag}/SHA256SUMS.txt"))
    output = args.output
    if output.is_symlink():
        raise ValueError("The published manifest must be a regular file")
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if version(existing["tag_name"]) > version(data["tag_name"]):
            raise ValueError("Refusing to replace a newer published manifest with an older release")
    encoded = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
    if not output.exists() or output.read_text(encoding="utf-8") != encoded:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    print(f"Verified website manifest: {tag}, {len(data['assets'])} published assets")


if __name__ == "__main__":
    main()
