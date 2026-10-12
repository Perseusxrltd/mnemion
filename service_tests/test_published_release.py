"""A public website snapshot must never promote drafts or unauthenticated assets."""

import hashlib
import io
import json
import sys
from urllib.error import HTTPError, URLError

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


class FetchResponse(io.BytesIO):
    headers = {}


def transport(monkeypatch, results):
    calls = []
    delays = []

    class Opener:
        def open(self, request, *, timeout):
            calls.append((request.full_url, dict(request.header_items()), timeout))
            result = results.pop(0)
            if isinstance(result, Exception):
                raise result
            return FetchResponse(result)

    monkeypatch.setattr(publisher, "build_opener", lambda *_: Opener())
    monkeypatch.setattr(publisher.time, "sleep", delays.append)
    return calls, delays


def failure(status, headers=None):
    return HTTPError(publisher.API, status, "fixture error", headers or {}, io.BytesIO())


def test_temporary_gateway_failures_retry_without_forwarding_api_credentials(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "fixture-api-credential")
    destination = "https://release-assets.githubusercontent.com/fixture"
    calls, delays = transport(
        monkeypatch,
        [
            failure(302, {"Location": destination}),
            failure(504),
            failure(503),
            b"verified bytes",
        ],
    )
    assert (
        publisher.fetch(publisher.ORIGIN + "/releases/download/v4.1.2/SHA256SUMS.txt")
        == b"verified bytes"
    )
    assert len(calls) == 4 and delays == [1, 2]
    assert [row[0] for row in calls[1:]] == [destination] * 3
    assert all("Authorization" not in row[1] for row in calls)


@pytest.mark.parametrize("status", [502, 503, 504])
def test_gateway_retry_budget_is_finite(monkeypatch, status):
    calls, delays = transport(monkeypatch, [failure(status)] * 3)
    with pytest.raises(RuntimeError, match=f"HTTP {status}"):
        publisher.fetch(publisher.API, api=True)
    assert len(calls) == 3 and delays == [1, 2]


@pytest.mark.parametrize("error", [failure(403), failure(404), URLError("certificate rejected")])
def test_permanent_or_certificate_errors_are_not_retried(monkeypatch, error):
    calls, delays = transport(monkeypatch, [error])
    with pytest.raises((RuntimeError, URLError)):
        publisher.fetch(publisher.API, api=True)
    assert len(calls) == 1 and not delays


def test_retry_preserves_host_and_api_redirect_boundaries(monkeypatch):
    calls, delays = transport(
        monkeypatch, [failure(504), failure(302, {"Location": "https://example.com/"})]
    )
    with pytest.raises(ValueError, match="approved GitHub hosts"):
        publisher.fetch(publisher.ORIGIN + "/releases/download/v4.1.2/SHA256SUMS.txt")
    assert len(calls) == 2 and delays == [1]
    calls, delays = transport(monkeypatch, [failure(302, {"Location": "https://github.com/"})])
    with pytest.raises(RuntimeError, match="HTTP 302"):
        publisher.fetch(publisher.API, api=True)
    assert len(calls) == 1 and not delays


def test_exhausted_deadline_prevents_backoff_and_another_request(monkeypatch):
    ticks = iter([0, 0, 45])
    monkeypatch.setattr(publisher.time, "monotonic", lambda: next(ticks))
    calls, delays = transport(monkeypatch, [failure(504)])
    with pytest.raises(ValueError, match="transfer limit"):
        publisher.fetch(publisher.API, api=True)
    assert len(calls) == 1 and not delays
