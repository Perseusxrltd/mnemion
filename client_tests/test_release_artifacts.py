"""Reject altered update bytes and paths before an automatic-update release."""

import base64
import hashlib
import json
import subprocess

import pytest
import yaml

from deploy.macos_sparkle import create_feed
from deploy.release import verify_feed, verify_sparkle_feed


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


def signed_mac_fixture(tmp_path):
    archive = tmp_path / "Mnemion-Studio-4.0.0-macos-arm64.zip"
    archive.write_bytes(b"synthetic update archive for signature validation")
    # Keys are ephemeral and never returned, printed or written to the fixture.
    script = """
      const fs = require('node:fs'), crypto = require('node:crypto');
      const pair = crypto.generateKeyPairSync('ed25519');
      const jwk = pair.publicKey.export({format:'jwk'});
      console.log(JSON.stringify({
        key: Buffer.from(jwk.x, 'base64url').toString('base64'),
        signature: crypto.sign(null, fs.readFileSync(process.argv[1]), pair.privateKey).toString('base64')
      }));
    """
    result = subprocess.run(
        ["node", "-e", script, str(archive)],
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    signed = json.loads(result.stdout)
    feed = tmp_path / "latest-arm64-mac.xml"
    feed.write_bytes(create_feed("4.0.0", "arm64", archive, signed["signature"]))
    return archive, feed, signed["key"]


def test_mac_updates_require_the_installed_signing_key(tmp_path):
    archive, feed, key = signed_mac_fixture(tmp_path)
    verify_sparkle_feed(feed, tmp_path, "4.0.0", "arm64", key)
    original = archive.read_bytes()
    archive.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    with pytest.raises(ValueError, match="signature does not match"):
        verify_sparkle_feed(feed, tmp_path, "4.0.0", "arm64", key)


def test_mac_update_feed_rejects_replaced_key_and_cross_architecture(tmp_path):
    _, feed, key = signed_mac_fixture(tmp_path)
    wrong_key = base64.b64encode(b"x" * 32).decode()
    with pytest.raises(ValueError, match="signature does not match"):
        verify_sparkle_feed(feed, tmp_path, "4.0.0", "arm64", wrong_key)
    with pytest.raises(ValueError, match="URL does not match"):
        verify_sparkle_feed(feed, tmp_path, "4.0.0", "x64", key)


def test_mac_update_feed_is_bound_to_the_immutable_repository_release(tmp_path):
    _, feed, key = signed_mac_fixture(tmp_path)
    original = feed.read_text()
    feed.write_text(original.replace("https://github.com/", "https://example.invalid/"))
    with pytest.raises(ValueError, match="URL does not match"):
        verify_sparkle_feed(feed, tmp_path, "4.0.0", "arm64", key)
    feed.write_text(original)
    with pytest.raises(ValueError, match="Wrong version"):
        verify_sparkle_feed(feed, tmp_path, "4.0.1", "arm64", key)


def test_mac_feed_generator_rejects_arbitrary_paths(tmp_path):
    path = tmp_path / "unrelated.zip"
    path.write_bytes(b"fixture")
    signature = base64.b64encode(b"x" * 64).decode()
    with pytest.raises(ValueError, match="canonical release filename"):
        create_feed("4.0.0", "arm64", path, signature)
