"""HTTP errors, size limits and redirects cannot bypass signed update integrity."""

import hashlib
import io
from types import SimpleNamespace
from urllib.error import HTTPError
import urllib.request

import pytest

from mnemion.service.update_manifest import Artifact, ManifestError
from mnemion.service import update_transport as transport


class Response(io.BytesIO):
    status = 200

    def __init__(self, data, headers=None, url=None):
        super().__init__(data)
        self.headers = headers if headers is not None else {"Content-Length": str(len(data))}
        self.url = url or transport.manifest_url()

    def geturl(self):
        return self.url


def serve(monkeypatch, response):
    calls = []

    def open(request, **kwargs):
        calls.append(request)
        assert request.get_header("Authorization") is None
        return response

    monkeypatch.setattr(
        transport.urllib.request, "build_opener", lambda *args: SimpleNamespace(open=open)
    )
    return calls


def test_public_manifest_has_no_service_credentials(monkeypatch):
    calls = serve(monkeypatch, Response(b"signed public metadata"))
    monkeypatch.setenv("MNEMION_API_KEY", "sentinel-private-not-for-release-host")
    assert transport.fetch_manifest() == b"signed public metadata"
    assert len(calls) == 1 and calls[0].full_url == transport.manifest_url()


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/release",
        "https://github.com.attacker.invalid/release",
        "https://user:password@github.com/release",
        "https://127.0.0.1/release",
        "https://github.com:444/release",
        "file:///private/settings",
    ],
)
def test_redirects_cannot_leave_official_https_hosts(url):
    handler = transport._Redirects()
    with pytest.raises(ManifestError, match="official HTTPS"):
        handler.redirect_request(
            urllib.request.Request(transport.manifest_url()), None, 302, "found", {}, url
        )


def test_github_asset_redirect_is_allowed():
    target = "https://release-assets.githubusercontent.com/asset?signature=public-download-token"
    request = transport._Redirects().redirect_request(
        urllib.request.Request(transport.manifest_url()), None, 302, "found", {}, target
    )
    assert request.full_url == target


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Length": "9999999"},
        {"Content-Length": "invalid"},
        {"Content-Length": "9"},
        {"Content-Encoding": "gzip"},
    ],
)
def test_invalid_response_size_or_encoding_cannot_be_accepted(monkeypatch, headers):
    serve(monkeypatch, Response(b"fixture", headers=headers))
    with pytest.raises(ManifestError):
        transport.fetch_manifest()


def test_unsigned_length_does_not_remove_streaming_size_limit(monkeypatch):
    serve(monkeypatch, Response(b"x" * 20, headers={}))
    monkeypatch.setattr(transport, "MAX_MANIFEST_BYTES", 10)
    with pytest.raises(ManifestError, match="size budget"):
        transport.fetch_manifest()


def test_download_publishes_only_verified_bytes_and_reuses_exact_cached_file(tmp_path, monkeypatch):
    data = b"exact signed bytes"
    artifact = Artifact("mnemion-4.0.8.tar.gz", len(data), hashlib.sha256(data).hexdigest())
    calls = serve(monkeypatch, Response(data))
    path = tmp_path / artifact.name
    transport.download_artifact("4.0.8", artifact, path)
    assert path.read_bytes() == data
    transport.download_artifact("4.0.8", artifact, path)
    assert len(calls) == 1
    path.write_bytes(b"x" * len(data))
    with pytest.raises(ManifestError, match="digest"):
        transport.download_artifact("4.0.8", artifact, path)
    assert len(calls) == 1


def test_failed_integrity_removes_partial_download(tmp_path, monkeypatch):
    data = b"corrupt package"
    serve(monkeypatch, Response(data))
    artifact = Artifact("mnemion-4.0.8.tar.gz", len(data), "0" * 64)
    with pytest.raises(ManifestError, match="digest"):
        transport.download_artifact("4.0.8", artifact, tmp_path / artifact.name)
    assert not list(tmp_path.iterdir())


def test_release_without_service_feed_is_distinct_from_an_integrity_failure(monkeypatch):
    def missing(*args, **kwargs):
        raise HTTPError(transport.manifest_url(), 404, "Not found", {}, None)

    monkeypatch.setattr(
        transport.urllib.request, "build_opener", lambda *args: SimpleNamespace(open=missing)
    )
    with pytest.raises(transport.UpdateNotPublished):
        transport.fetch_manifest()
