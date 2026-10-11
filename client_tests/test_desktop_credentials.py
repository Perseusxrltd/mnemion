"""Native DPAPI operations in distinct local-client processes, with no profile key."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mnemion.desktop_credentials import credential_request

ROOT = Path(__file__).resolve().parents[1]


def _request(operation, value):
    executable = os.environ.get("MNEMION_PACKAGED_CLIENT")
    command = [executable] if executable else [sys.executable, str(ROOT / "studio/bridge/main.py")]
    return subprocess.run(
        [*command, "--credential", operation],
        input=json.dumps({"value": value}),
        text=True,
        capture_output=True,
        timeout=20,
    )


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows DPAPI")
def test_fresh_process_decrypts_without_a_chromium_profile(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plain = "Disposable credential — local Windows validation"
    protected = _request("protect", plain)
    assert protected.returncode == 0, protected.stderr
    sealed = json.loads(protected.stdout)["value"]
    assert plain not in protected.stdout and not protected.stderr
    assert plain.encode() not in base64.b64decode(sealed)
    reopened = _request("unprotect", sealed)
    assert reopened.returncode == 0 and not reopened.stderr
    assert json.loads(reopened.stdout)["value"] == plain
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows DPAPI")
def test_altered_ciphertext_fails_without_returning_a_secret():
    plain = "Disposable tamper-validation credential"
    protected = _request("protect", plain)
    assert protected.returncode == 0
    sealed = bytearray(base64.b64decode(json.loads(protected.stdout)["value"]))
    sealed[-1] ^= 1
    failed = _request("unprotect", base64.b64encode(sealed).decode())
    assert failed.returncode == 1 and not failed.stderr
    assert json.loads(failed.stdout)["error"] == "credential_unavailable"
    assert plain not in failed.stdout and "value" not in json.loads(failed.stdout)


def test_invalid_requests_never_echo_the_supplied_value():
    value = "SENSITIVE_DISPOSABLE_MARKER"
    for operation, data in [
        ("protect", b"{invalid"),
        ("protect", json.dumps({"value": value, "extra": True}).encode()),
        ("protect", json.dumps({"value": value * 2000}).encode()),
        ("protect", b'{"value":"\\ud800"}'),
        ("unprotect", json.dumps({"value": value}).encode()),
        ("unprotect", json.dumps({"value": base64.b64encode(value.encode()).decode()}).encode()),
    ]:
        with pytest.raises(ValueError) as raised:
            credential_request(operation, data)
        assert value not in str(raised.value)


@pytest.mark.skipif(sys.platform == "win32", reason="non-Windows fallback refusal")
def test_other_platforms_do_not_substitute_plaintext():
    failed = _request("protect", "Disposable validation credential")
    assert failed.returncode == 1 and not failed.stderr
    result = json.loads(failed.stdout)
    assert result["error"] == "credential_unavailable" and "value" not in result
