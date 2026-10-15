"""Portable recovery remains authenticated, private, bounded and server-independent."""

import base64
import hashlib
import json
import re
import socket
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import pytest

from mnemion.private_output import private_output
from mnemion.service import cli, recovery_kit
from mnemion.service.recovery_directory import RecoveryDirectory


def record():
    return {
        "tenant_id": str(uuid4()),
        "revision": 1,
        "updated_at": "2026-10-15T00:00:00Z",
        "updated_by": str(uuid4()),
        "directory": RecoveryDirectory(
            instructions="PRIVATE_RECOVERY_REFERENCE_FIXTURE <script>alert(1)</script>",
        ).model_dump(mode="json"),
    }


def decrypt(html, passphrase):
    envelope = json.loads(re.search(r"const sealed = (.*);", html)[1])
    key = hashlib.pbkdf2_hmac(
        "sha256", passphrase.encode(), base64.b64decode(envelope["salt"]), 600_000, 32
    )
    clear = AESGCM(key).decrypt(
        base64.b64decode(envelope["iv"]),
        base64.b64decode(envelope["ciphertext"]),
        b"mnemion-recovery-kit-v1",
    )
    return json.loads(clear)


def test_portable_kit_has_authenticated_ciphertext_and_a_self_contained_viewer():
    source = record()
    source["future_private_field"] = "fixture-token-that-must-never-be-exported"
    phrase = "independent fixture passphrase 🧠"
    html = recovery_kit.render_kit(
        source, phrase, endpoint="https://memory.example.org", workspace_name="Fixture workspace"
    )
    assert source["directory"]["instructions"] not in html
    assert phrase not in html and source["future_private_field"] not in html
    clear = decrypt(html, phrase)
    assert clear["record"]["directory"] == source["directory"]
    assert "future_private_field" not in clear["record"]
    script = re.search(r"<script>(.*?)</script>", html, re.DOTALL)[1]
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    assert f"script-src 'sha256-{digest}'" in html
    assert "default-src 'none'" in html and "form-action 'none'" in html
    assert "__MNEMION_" not in html
    with pytest.raises(InvalidTag):
        decrypt(html, "incorrect fixture passphrase")
    envelope = json.loads(re.search(r"const sealed = (.*);", html)[1])
    damaged = bytearray(base64.b64decode(envelope["ciphertext"]))
    damaged[-1] ^= 1
    corrupted = html.replace(envelope["ciphertext"], base64.b64encode(damaged).decode())
    with pytest.raises(InvalidTag):
        decrypt(corrupted, phrase)


@pytest.mark.parametrize(
    "change",
    [
        {"passphrase": "too short"},
        {"passphrase": "a" * 4097},
        {"endpoint": "https://person:secret@example.org"},
        {"endpoint": "http://remote.example.org"},
        {"workspace_name": "bad\x00name"},
    ],
)
def test_invalid_kit_inputs_fail_before_an_export(change):
    values = {
        "passphrase": "independent fixture passphrase",
        "endpoint": "https://memory.example.org",
        "workspace_name": "Fixture workspace",
        **change,
    }
    with pytest.raises(ValueError):
        recovery_kit.render_kit(record(), **values)


def test_installed_cli_creates_a_private_kit_offline_and_never_overwrites(
    tmp_path, monkeypatch, capsys
):
    def forbid_network(*args, **kwargs):
        pytest.fail("An independent recovery kit must not contact the workspace")

    monkeypatch.setattr(socket, "create_connection", forbid_network)
    record_file, passphrase_file, output = (
        tmp_path / name for name in ("record.json", "phrase", "kit.html")
    )
    phrase = "fixture-only separate passphrase"
    directory = record()
    directory["directory"]["instructions"] = "🧠" * 1450
    for path, content in [
        (
            record_file,
            json.dumps({"operation": "recovery.directory", "result": directory}).encode(),
        ),
        (passphrase_file, phrase.encode()),
    ]:
        with private_output(path) as private:
            private.write(content)
    arguments = [
        "recovery-kit",
        "--record-file",
        str(record_file),
        "--passphrase-file",
        str(passphrase_file),
        "--endpoint",
        "https://memory.example.org",
        "--workspace-name",
        "Fixture workspace",
        "--output",
        str(output),
    ]
    assert cli.main(arguments) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["created"] and result["encrypted"] and result["network_requests"] == 0
    original = output.read_bytes()
    assert decrypt(original.decode(), phrase)["workspace_name"] == "Fixture workspace"
    assert cli.main(arguments) == 1
    assert output.read_bytes() == original
    assert phrase not in capsys.readouterr().out
