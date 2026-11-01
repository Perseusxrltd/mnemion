"""Public, bounded HTTPS downloads for independently signed service releases."""

from __future__ import annotations

import errno
import os
from pathlib import Path
import socket
import ssl
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
import urllib.request

from .update_manifest import DEFAULT_REPOSITORY, MAX_MANIFEST_BYTES, Artifact, ManifestError

DOWNLOAD_HOSTS = frozenset({"github.com", "release-assets.githubusercontent.com"})
NETWORK_SECONDS = 180
IDLE_SECONDS = 15
_HTTPS_MESSAGE = "Cannot download the service update over HTTPS"
_HTTP_MESSAGE = "The service update host returned an HTTP error"
TRANSPORT_CATEGORIES = frozenset(
    {
        "dns_temporary",
        "dns_other",
        "timeout",
        "connection_reset",
        "network_unreachable",
        "tls_certificate",
        "tls_other",
        "http_rate_limited",
        "http_server",
        "http_other",
        "transport_other",
    }
)
# Retryability is this set, not a string supplied by a caller. HTTP statuses
# are labeled for diagnosis and stay on the normal cadence in this release.
RETRYABLE_TRANSPORT = frozenset(
    {"dns_temporary", "timeout", "connection_reset", "network_unreachable"}
)


class UpdateNotPublished(ManifestError):
    """The current stable release has no service update envelope yet."""


class TransportFailure(ManifestError):
    """A classified download failure. The public text never includes the request."""

    def __init__(self, message: str, category: str):
        if category not in TRANSPORT_CATEGORIES:
            raise ManifestError("Invalid service update transport category")
        super().__init__(message)
        self.category = category

    @property
    def retryable(self) -> bool:
        return self.category in RETRYABLE_TRANSPORT


def _https(url: str) -> None:
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname in DOWNLOAD_HOSTS
            and parsed.port in (None, 443)
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise ManifestError("Service update downloads require the official HTTPS hosts")


class _Redirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 5
    max_repeats = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _cause(error: BaseException) -> BaseException:
    """Follow an exception-valued URLError.reason. Never read its text."""
    current = error
    for _ in range(3):
        if not isinstance(current, URLError):
            break
        reason = getattr(current, "reason", None)
        if not isinstance(reason, BaseException) or reason is current:
            break
        current = reason
    return current


def _errno_category(code: int | None) -> str | None:
    if code == errno.ETIMEDOUT:
        return "timeout"
    if code in (errno.ECONNRESET, errno.ECONNABORTED):
        return "connection_reset"
    if code in (errno.ENETUNREACH, errno.EHOSTUNREACH):
        return "network_unreachable"
    return None


def _category(error: BaseException) -> str:
    cause = _cause(error)
    if isinstance(cause, ssl.SSLCertVerificationError):
        return "tls_certificate"
    if isinstance(cause, ssl.SSLError):
        return "tls_other"
    if isinstance(cause, socket.gaierror):
        code = cause.errno
        if code != socket.EAI_AGAIN and cause.args and cause.args[0] == socket.EAI_AGAIN:
            code = cause.args[0]
        return "dns_temporary" if code == socket.EAI_AGAIN else "dns_other"
    if isinstance(cause, TimeoutError):
        return "timeout"
    if isinstance(cause, (ConnectionResetError, ConnectionAbortedError)):
        return "connection_reset"
    if isinstance(cause, OSError):
        return _errno_category(cause.errno) or "transport_other"
    return "transport_other"


def _transport_failure(error: BaseException) -> TransportFailure:
    return TransportFailure(_HTTPS_MESSAGE, _category(error))


def _http_failure(url: str, error: HTTPError) -> ManifestError:
    if error.code == 404 and url == manifest_url():
        return UpdateNotPublished("The stable release has no managed service update yet")
    if error.code == 429:
        category = "http_rate_limited"
    elif type(error.code) is int and 500 <= error.code <= 599:
        category = "http_server"
    else:
        category = "http_other"
    return TransportFailure(_HTTP_MESSAGE, category)


def _write_download(target, chunk: bytes) -> None:
    """A local write error is not evidence that the HTTPS read failed."""
    try:
        target.write(chunk)
    except OSError:
        raise ManifestError(_HTTPS_MESSAGE) from None


def manifest_url() -> str:
    return f"https://github.com/{DEFAULT_REPOSITORY}/releases/latest/download/service-update.json"


def artifact_url(version: str, name: str) -> str:
    from .update_manifest import version_tuple

    version_tuple(version)
    if name not in {f"mnemion-{version}.tar.gz", f"mnemion-{version}-py3-none-any.whl"}:
        raise ManifestError("Unexpected service update package name")
    return f"https://github.com/{DEFAULT_REPOSITORY}/releases/download/v{version}/{name}"


def _download(url: str, maximum: int, target=None, *, size: int | None = None) -> bytes:
    _https(url)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mnemion-Service-Updater/1", "Accept-Encoding": "identity"},
    )
    deadline = time.monotonic() + NETWORK_SECONDS
    opener = urllib.request.build_opener(_Redirects())
    try:
        with opener.open(request, timeout=IDLE_SECONDS) as response:
            _https(response.geturl())
            if (
                response.status != 200
                or response.headers.get("Content-Encoding", "identity") != "identity"
            ):
                raise ManifestError("Unexpected service update response")
            length = response.headers.get("Content-Length")
            if length is not None:
                if not length.isascii() or not length.isdigit():
                    raise ManifestError("Invalid service update response size")
                if int(length) > maximum or (size is not None and int(length) != size):
                    raise ManifestError("Service update response disagrees with its size budget")
            content = bytearray()
            total = 0
            while True:
                if time.monotonic() >= deadline:
                    raise ManifestError("Service update download exceeded its time budget")
                # read1 returns after a socket read, so a slow sender cannot
                # postpone the deadline check until a complete megabyte arrives.
                chunk = response.read1(min(65536, maximum - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum:
                    raise ManifestError("Service update download exceeded its size budget")
                if target is None:
                    content.extend(chunk)
                else:
                    _write_download(target, chunk)
            if (
                total == 0
                or (size is not None and total != size)
                or (length is not None and total != int(length))
            ):
                raise ManifestError("Incomplete service update download")
            return bytes(content)
    except HTTPError as error:
        raise _http_failure(url, error) from None
    except (OSError, URLError, ValueError) as error:
        if isinstance(error, ManifestError):
            raise
        raise _transport_failure(error) from None


def fetch_manifest() -> bytes:
    return _download(manifest_url(), MAX_MANIFEST_BYTES)


def download_artifact(version: str, artifact: Artifact, destination: Path) -> None:
    """Stream to a private temporary file; publish only exact authenticated bytes."""
    if destination.exists() or destination.is_symlink():
        artifact.verify_file(destination)
        return
    descriptor, name = tempfile.mkstemp(prefix=".service-download-", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            _download(
                artifact_url(version, artifact.name), artifact.size, output, size=artifact.size
            )
            output.flush()
            os.fsync(output.fileno())
        artifact.verify_file(temporary)
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
