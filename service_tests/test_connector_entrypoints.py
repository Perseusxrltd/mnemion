"""Independent connector controls work through the console and native-engine CLI."""

import json
import subprocess
import sys

import pytest

from service_tests.test_headless_capture_controls import configuration as configuration


@pytest.fixture(params=["standalone", "engine"])
def entry(request):
    if request.param == "engine":
        return [sys.executable, "-m", "mnemion.service.cli", "connect"]
    return [sys.executable, "-m", "mnemion.connectors.runner"]


def invoke(entry, path, *arguments, control=None):
    return subprocess.run(
        [*entry, "--config", str(path), *arguments],
        input=json.dumps(control) if control is not None else None,
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_entrypoint_can_preview_before_any_credential_exists(entry, tmp_path, configuration):
    path = tmp_path / "Source Équipe.json"
    path.write_text(json.dumps(configuration), encoding="utf-8")
    marker = "An unselected private preview must not publish this text."
    (tmp_path / "logs/chat.jsonl").write_text(
        json.dumps({"role": "user", "content": marker}) + "\n", encoding="utf-8"
    )
    result = invoke(entry, path, "--inspect")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["preview"]["records"]["selected"] == 1
    assert not report["preview"]["content_saved"]
    assert marker not in result.stdout + result.stderr
    assert not (tmp_path / "private/inbox.key").exists()


def test_entrypoint_generates_exclusive_private_key_without_printing_it(
    entry, tmp_path, configuration
):
    path = tmp_path / "source.json"
    path.write_text(json.dumps(configuration), encoding="utf-8")
    control = {"action": "key", "confirm": True}
    result = invoke(entry, path, "--capture-control", control=control)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "ok": True,
        "result": {"created": True, "purpose": "inbox", "key_printed": False},
    }
    file = tmp_path / "private/inbox.key"
    original = file.read_bytes()
    secret = original.decode().strip()
    assert len(secret) == 44 and secret not in result.stdout + result.stderr
    repeated = invoke(entry, path, "--capture-control", control=control)
    assert repeated.returncode == 2
    assert file.read_bytes() == original
    assert secret not in repeated.stdout + repeated.stderr


def test_entrypoint_redacts_invalid_inline_keys(entry, tmp_path, configuration):
    marker = "private-invalid-inline-inbox-key-do-not-print"
    configuration["capture"]["inbox_key"] = marker
    path = tmp_path / "source.json"
    path.write_text(json.dumps(configuration), encoding="utf-8")
    result = invoke(entry, path, "--capture-control", control={"action": "status"})
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"] == "invalid_config"
    assert marker not in result.stdout + result.stderr


def test_entrypoint_bounds_errors_and_redacts_private_property_names(
    entry, tmp_path, configuration
):
    marker = "private-property-" + "confidential-" * 40
    configuration["service_token"] = "private-inline-token-value"
    configuration["poll_seconds"] = 0
    configuration.update({f"{marker}-{number}": "private-value" for number in range(100)})
    path = tmp_path / "source.json"
    path.write_text(json.dumps(configuration), encoding="utf-8")
    result = invoke(entry, path, "--inspect")
    assert result.returncode == 2
    assert len(result.stderr.encode()) < 8192
    assert marker not in result.stdout + result.stderr
    assert "private-inline-token-value" not in result.stdout + result.stderr
    assert "private-value" not in result.stdout + result.stderr
    report = json.loads(result.stderr)
    assert report["error"] == "invalid_config"
    assert "poll_seconds" in report["fields"]
    assert len(report["fields"]) <= 20
    assert any(hint["field"] == "service_token" for hint in report["hints"])


@pytest.mark.parametrize(
    "options,reason",
    [
        (["--capture-control", "--inspect"], "cannot be combined"),
        (["--capture-control", "--watch"], "cannot be combined"),
        (["--inspect", "--watch"], "cannot be combined"),
        (["--managed-state", "unused"], "requires --watch"),
    ],
)
def test_entrypoint_rejects_conflicting_modes_before_reading_config(
    entry, tmp_path, options, reason
):
    result = invoke(entry, tmp_path / "not-created.json", *options)
    assert result.returncode == 2
    assert reason in result.stderr and "Traceback" not in result.stderr
