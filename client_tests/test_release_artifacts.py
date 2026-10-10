"""Reject altered update bytes and paths before an automatic-update release."""

import base64
import hashlib

import pytest
import yaml

from deploy.release import verify_feed


def fixture_feed(tmp_path):
    payload = tmp_path / "Mnemion-4.0.0.AppImage"
    payload.write_bytes(b"synthetic installer bytes")
    digest = base64.b64encode(hashlib.sha512(payload.read_bytes()).digest()).decode()
    entry = {"url": payload.name, "size": payload.stat().st_size, "sha512": digest}
    data = {"version": "4.0.0", "files": [entry], "path": payload.name, "sha512": digest}
    feed = tmp_path / "latest-x64-linux.yml"
    feed.write_text(yaml.safe_dump(data), encoding="utf-8")
    return feed, payload, data


def test_update_payload_bytes_are_verified(tmp_path):
    feed, payload, _ = fixture_feed(tmp_path)
    verify_feed(feed, tmp_path, "4.0.0")
    payload.write_bytes(b"substituted installer bytes")
    with pytest.raises(ValueError, match="hash or size mismatch"):
        verify_feed(feed, tmp_path, "4.0.0")


@pytest.mark.parametrize(
    "url", ["../outside.exe", "..\\outside.exe", "https://example.com/app.exe"]
)
def test_update_payload_cannot_escape_release(tmp_path, url):
    feed, _, data = fixture_feed(tmp_path)
    data["files"][0]["url"] = url
    feed.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError, match="local release filenames"):
        verify_feed(feed, tmp_path, "4.0.0")


def test_update_legacy_pointer_cannot_disagree(tmp_path):
    feed, _, data = fixture_feed(tmp_path)
    data["sha512"] = "wrong hash"
    feed.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError, match="pointer disagrees"):
        verify_feed(feed, tmp_path, "4.0.0")
