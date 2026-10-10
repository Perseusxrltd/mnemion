"""A public website snapshot must never promote drafts or unauthenticated assets."""

import hashlib
import json
import sys

import pytest

from deploy import published_release as publisher


def published(version="4.0.1"):
    names = [
        f"Mnemion-Studio-{version}-windows-x64.exe",
        "latest-x64.yml",
        "latest-x64-windows.json",
    ]
    data = {name: f"published fixture: {name}".encode() for name in names}
    checksums = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n" for name, content in data.items()
    ).encode()
    data["SHA256SUMS.txt"] = checksums
    release = {
        "tag_name": f"v{version}",
        "draft": False,
        "prerelease": False,
        "html_url": f"{publisher.ORIGIN}/releases/tag/v{version}",
        "published_at": "2026-10-10T19:00:00Z",
        "assets": [
            {
                "name": name,
                "state": "uploaded",
                "size": len(content),
                "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
                "browser_download_url": f"{publisher.ORIGIN}/releases/download/v{version}/{name}",
            }
            for name, content in data.items()
        ],
    }
    return release, checksums


def test_verified_partial_release_snapshot_is_stable_and_excludes_private_api_metadata():
    release, checksums = published()
    release["upload_url"] = "unnecessary API data"
    result = publisher.manifest(release, checksums)
    assert result["tag_name"] == "v4.0.1"
    assert result["draft"] is False
    assert "upload_url" not in result
    assert len(result["assets"]) == 4
    assert result == publisher.manifest(release, checksums)


@pytest.mark.parametrize(
    "patch",
    [
        {"draft": True},
        {"prerelease": True},
        {"tag_name": "v3.5.5"},
        {"tag_name": "v4.0.1-beta.1"},
        {"tag_name": "v04.0.1"},
        {"html_url": "https://example.com/release"},
        {"published_at": None},
        {"published_at": "2026-10-10T19:00:00"},
    ],
)
def test_only_stable_publications_qualify(patch):
    release, checksums = published()
    with pytest.raises(ValueError):
        publisher.manifest({**release, **patch}, checksums)


@pytest.mark.parametrize(
    "patch",
    [
        {"name": "../installer.exe"},
        {"state": "open"},
        {"size": 0},
        {"size": True},
        {"digest": None},
        {"digest": "sha256:" + "0" * 64},
        {"browser_download_url": "https://example.com/installer.exe"},
    ],
)
def test_unverified_or_substituted_asset_is_rejected(patch):
    release, checksums = published()
    release["assets"][0].update(patch)
    with pytest.raises(ValueError):
        publisher.manifest(release, checksums)


def test_modified_checksum_file_and_incomplete_inventory_are_rejected():
    release, checksums = published()
    with pytest.raises(ValueError, match="checksum file"):
        publisher.manifest(release, checksums + b"\n")
    release["assets"].pop(1)
    with pytest.raises(ValueError, match="inventory"):
        publisher.manifest(release, checksums)


def test_main_uses_official_endpoints_and_never_replaces_a_newer_snapshot(tmp_path, monkeypatch):
    output = tmp_path / "published-release.json"
    release, checksums = published()
    requests = []

    def fetch(url, *, api=False):
        requests.append((url, api))
        return json.dumps(release).encode() if api else checksums

    monkeypatch.setattr(publisher, "fetch", fetch)
    monkeypatch.setattr(sys, "argv", ["published-release", "--output", str(output)])
    publisher.main()
    assert requests == [
        (publisher.API, True),
        (f"{publisher.ORIGIN}/releases/download/v4.0.1/SHA256SUMS.txt", False),
    ]
    before = output.read_bytes()
    stat = output.stat()
    publisher.main()
    assert output.stat().st_mtime_ns == stat.st_mtime_ns
    release, checksums = published("4.0.0")
    with pytest.raises(ValueError, match="newer published"):
        publisher.main()
    assert output.read_bytes() == before
