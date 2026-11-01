"""HTTP errors, size limits and redirects cannot bypass signed update integrity."""

import errno
import hashlib
import io
import json
import socket
import ssl
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
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


SENTINEL_URL = "https://user:sentinel-password@github.com/Perseusxrltd/mnemion?sentinel-query=1"
_HTTPS = "Cannot download the service update over HTTPS"
_HTTP = "The service update host returned an HTTP error"


def _raise(factory):
    return lambda: factory()


def _cases():
    transient = [
        ("temporary-dns", lambda: socket.gaierror(socket.EAI_AGAIN, SENTINEL_URL), "dns_temporary"),
        ("timeout", lambda: TimeoutError(SENTINEL_URL), "timeout"),
        ("etimeout", lambda: OSError(errno.ETIMEDOUT, SENTINEL_URL), "timeout"),
        ("reset", lambda: ConnectionResetError(SENTINEL_URL), "connection_reset"),
        ("reset-errno", lambda: OSError(errno.ECONNRESET, SENTINEL_URL), "connection_reset"),
        ("aborted", lambda: ConnectionAbortedError(SENTINEL_URL), "connection_reset"),
        ("aborted-errno", lambda: OSError(errno.ECONNABORTED, SENTINEL_URL), "connection_reset"),
        (
            "net-unreachable",
            lambda: OSError(errno.ENETUNREACH, SENTINEL_URL),
            "network_unreachable",
        ),
        (
            "host-unreachable",
            lambda: OSError(errno.EHOSTUNREACH, SENTINEL_URL),
            "network_unreachable",
        ),
    ]
    cases = []
    for name, factory, category in transient:
        cases.append((f"direct-{name}", factory, "open", category))
        wrapped = _raise(lambda factory=factory: URLError(factory()))
        cases.append((f"wrapped-{name}", wrapped, "open", category))
    cases.extend(
        [
            (
                "double-wrapped-timeout",
                lambda: URLError(URLError(TimeoutError(SENTINEL_URL))),
                "open",
                "timeout",
            ),
            (
                "certificate",
                lambda: ssl.SSLCertVerificationError(1, SENTINEL_URL),
                "open",
                "tls_certificate",
            ),
            (
                "wrapped-certificate",
                lambda: URLError(ssl.SSLCertVerificationError(1, SENTINEL_URL)),
                "open",
                "tls_certificate",
            ),
            ("other-tls", lambda: ssl.SSLError(1, SENTINEL_URL), "open", "tls_other"),
            (
                "permanent-dns",
                lambda: socket.gaierror(socket.EAI_NONAME, SENTINEL_URL),
                "open",
                "dns_other",
            ),
            (
                "text-is-not-a-category",
                lambda: URLError(f"{SENTINEL_URL} EAI_AGAIN ETIMEDOUT"),
                "open",
                "transport_other",
            ),
            ("unknown-os", lambda: OSError(errno.EIO, SENTINEL_URL), "open", "transport_other"),
            ("unknown-value", lambda: ValueError(SENTINEL_URL), "open", "transport_other"),
            ("read-timeout", lambda: TimeoutError(SENTINEL_URL), "read", "timeout"),
            ("read-etimeout", lambda: OSError(errno.ETIMEDOUT, SENTINEL_URL), "read", "timeout"),
            ("local-timeout", lambda: TimeoutError(SENTINEL_URL), "write", None),
            ("local-etimeout", lambda: OSError(errno.ETIMEDOUT, SENTINEL_URL), "write", None),
            ("local-enospc", lambda: OSError(errno.ENOSPC, SENTINEL_URL), "write", None),
            ("http-401", lambda: _http(401), "http", "http_other"),
            ("http-403", lambda: _http(403), "http", "http_other"),
            ("http-404-manifest", lambda: _http(404), "http", "not_published"),
            ("http-429", lambda: _http(429), "http", "http_rate_limited"),
            ("http-503", lambda: _http(503), "http", "http_server"),
            ("http-404-artifact", lambda: _http(404), "http-artifact", "http_other"),
            ("bad-encoding", lambda: None, "encoding", None),
        ]
    )
    return cases


def _http(code):
    return HTTPError(
        SENTINEL_URL,
        code,
        SENTINEL_URL,
        {"Proxy-Authorization": "sentinel-password", "Cookie": "sentinel-query"},
        None,
    )


class _FailingRead(Response):
    def __init__(self, error):
        super().__init__(b"signed public metadata")
        self.error = error

    def read1(self, size=-1):
        raise self.error


class _FailingDisk:
    def __init__(self, error):
        self.error = error

    def write(self, _chunk):
        raise self.error


def _perform(monkeypatch, factory, where):
    def open_error(request, **kwargs):
        raise factory()

    def open_response(request, **kwargs):
        if where == "encoding":
            return Response(
                b"fixture",
                headers={"Content-Encoding": "gzip", "Set-Cookie": "sentinel-password"},
            )
        if where == "read":
            return _FailingRead(factory())
        return Response(b"signed public metadata")

    opener = open_error if where in {"open", "http", "http-artifact"} else open_response
    monkeypatch.setattr(
        transport.urllib.request,
        "build_opener",
        lambda *args: SimpleNamespace(open=opener),
    )
    if where == "write":
        transport._download(transport.manifest_url(), 1000, _FailingDisk(factory()))
    elif where == "http-artifact":
        transport._download(transport.artifact_url("4.0.8", "mnemion-4.0.8.tar.gz"), 1000)
    else:
        transport.fetch_manifest()


_TRANSPORT_CASES = _cases()


@pytest.mark.parametrize(
    ("name", "factory", "where", "category"),
    _TRANSPORT_CASES,
    ids=[case[0] for case in _TRANSPORT_CASES],
)
def test_transport_errors_keep_a_fixed_category_and_no_request_details(
    monkeypatch, name, factory, where, category
):
    with pytest.raises(ManifestError) as caught:
        _perform(monkeypatch, factory, where)
    error = caught.value
    if category is None:
        assert type(error) is ManifestError
        assert not isinstance(error, transport.TransportFailure)
    elif category == "not_published":
        assert type(error) is transport.UpdateNotPublished
        assert str(error) == "The stable release has no managed service update yet"
    else:
        assert type(error) is transport.TransportFailure
        assert error.category == category
        assert error.retryable is (category in transport.RETRYABLE_TRANSPORT)
        assert str(error) == (_HTTP if category.startswith("http_") else _HTTPS)
    history = {"event": "check_failed", "detail": str(error)}
    if isinstance(error, transport.TransportFailure):
        history.update(category=error.category, retryable=error.retryable, transport_retry=0)
    blob = json.dumps(
        {"detail": str(error), "args": error.args, "fields": error.__dict__, "history": history},
        default=str,
    )
    assert "sentinel-password" not in blob
    assert "sentinel-query" not in blob
    assert "Proxy-Authorization" not in blob
    assert error.__cause__ is None
