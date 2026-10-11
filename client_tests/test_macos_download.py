"""Transient build downloads recover without accepting partial or changed bytes."""

import hashlib
import io
from urllib.error import HTTPError, URLError

import pytest

from deploy import macos_sparkle


def test_native_download_recovers_a_timeout_and_mid_stream_failure(tmp_path, monkeypatch):
    payload = b"complete pinned native dependency"
    attempts = 0

    class Interrupted(io.BytesIO):
        def read(self, size):
            if self.tell():
                raise URLError("connection lost during transfer")
            return super().read(4)

    def request(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise URLError("connection timed out")
        if attempts == 2:
            return Interrupted(b"partial bytes that must not survive")
        return io.BytesIO(payload)

    monkeypatch.setattr(macos_sparkle, "urlopen", request)
    monkeypatch.setattr(macos_sparkle.time, "sleep", lambda seconds: None)
    destination = tmp_path / "native.tar.xz"
    macos_sparkle.download(
        "https://example.com/native", destination, hashlib.sha256(payload).hexdigest(), 100
    )
    assert destination.read_bytes() == payload and attempts == 3
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("fault", ["digest", "size"])
def test_invalid_native_bytes_are_not_retried_or_published(tmp_path, monkeypatch, fault):
    attempts = 0

    def request(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        return io.BytesIO(b"invalid bytes")

    monkeypatch.setattr(macos_sparkle, "urlopen", request)
    with pytest.raises(ValueError):
        macos_sparkle.download(
            "https://example.com/native",
            tmp_path / "native",
            "0" * 64,
            100 if fault == "digest" else 2,
        )
    assert attempts == 1 and not list(tmp_path.iterdir())


def test_existing_download_is_never_overwritten(tmp_path, monkeypatch):
    destination = tmp_path / "native"
    destination.write_bytes(b"existing")
    monkeypatch.setattr(
        macos_sparkle, "urlopen", lambda *args, **kwargs: pytest.fail("must not download")
    )
    with pytest.raises(FileExistsError):
        macos_sparkle.download("https://example.com/native", destination, "0" * 64, 100)
    assert destination.read_bytes() == b"existing"


@pytest.mark.parametrize("code,expected_attempts", [(503, 3), (404, 1)])
def test_native_download_http_retries_are_bounded(tmp_path, monkeypatch, code, expected_attempts):
    attempts = 0

    def request(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise HTTPError("https://example.com/native", code, "fixture", {}, io.BytesIO())

    monkeypatch.setattr(macos_sparkle, "urlopen", request)
    monkeypatch.setattr(macos_sparkle.time, "sleep", lambda seconds: None)
    with pytest.raises(RuntimeError if code == 503 else HTTPError):
        macos_sparkle.download("https://example.com/native", tmp_path / "native", "0" * 64, 100)
    assert attempts == expected_attempts and not list(tmp_path.iterdir())
