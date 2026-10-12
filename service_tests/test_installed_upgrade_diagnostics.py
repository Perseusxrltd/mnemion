"""Failure evidence must exclude provider messages, keys and local data."""

import json
import subprocess

import pytest

from deploy.installed_upgrade_diagnostics import (
    inspect_local_status,
    inspect_mac_startup,
    mac_startup_symbols,
    public_status,
    smoke_reason,
)


def test_setup_evidence_keeps_only_operating_codes_and_our_code_locations():
    secret = "mnm_" + "x" * 48
    private = "postgresql://owner:synthetic-password@private.invalid/workspace"
    result = public_status(
        {
            "state": "error",
            "stage": "backup",
            "errorCode": "local_setup_failed",
            "message": private,
            "settings": {"key": secret},
            "connection": {"credential": secret},
            "diagnostic": {
                "category": "operating_system",
                "errno": 13,
                "winerror": 5,
                "message": private,
                "locations": [
                    {
                        "module": "mnemion.service.recovery",
                        "function": "create_backup",
                        "line": 230,
                        "locals": {"credential": secret},
                    },
                    {"module": secret, "function": "unsafe", "line": 10},
                ],
            },
        }
    )
    assert result == {
        "available": True,
        "state": "error",
        "stage": "backup",
        "error_code": "local_setup_failed",
        "diagnostic": {
            "category": "operating_system",
            "errno": 13,
            "winerror": 5,
            "locations": [
                {"module": "mnemion.service.recovery", "function": "create_backup", "line": 230}
            ],
        },
    }
    assert secret not in json.dumps(result) and private not in json.dumps(result)


@pytest.mark.parametrize("bad", [None, [], {"state": [], "diagnostic": {"category": []}}])
def test_malformed_status_cannot_smuggle_arbitrary_values_into_evidence(bad):
    result = public_status(bad)
    assert set(result) == {"available"}


def test_secret_shaped_codes_and_unknown_messages_are_omitted():
    secret = "mnm_" + "x" * 48
    result = public_status({"state": "error", "errorCode": secret})
    assert result == {"available": True, "state": "error"}
    assert smoke_reason({"stage": "startup-error", "error": secret}) == {
        "smoke_stage": "startup-error"
    }
    assert smoke_reason(
        {
            "stage": "startup-error",
            "error": "The UI did not open or automatically restore " + secret,
        }
    ) == {"smoke_stage": "startup-error", "reason": "local_reopen_timeout"}


def test_invalid_debug_destinations_do_not_start_a_process(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("A diagnostic process was started without an isolated loopback port")

    monkeypatch.setattr("deploy.installed_upgrade_diagnostics.subprocess.run", forbidden)
    for port in (None, 0, 80, True, "9222", 65536):
        assert inspect_local_status(port, {}) == {"available": False}


def test_native_sample_exports_only_known_symbols():
    secret = "mnm_" + "x" * 48
    private = "postgresql://owner:synthetic-password@private.invalid/workspace"
    sample = "OS trace " + secret + private + "\nSecItemCopyMatching /private/example\nuv_run\n"
    assert mac_startup_symbols(sample) == ["SecItemCopyMatching", "uv_run"]
    assert smoke_reason({"stage": "tray-ready", "error": secret}) == {"smoke_stage": "tray-ready"}


def test_native_sample_cannot_run_on_a_personal_host(monkeypatch, tmp_path):
    monkeypatch.setattr("deploy.installed_upgrade_diagnostics.sys.platform", "darwin")
    monkeypatch.delenv("CI", raising=False)

    def forbidden(*args, **kwargs):
        pytest.fail("A native process was sampled outside the disposable CI runner")

    monkeypatch.setattr("deploy.installed_upgrade_diagnostics.subprocess.run", forbidden)
    assert inspect_mac_startup(123, tmp_path, {}) == {"available": False}
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("phase", ["http", "pages", "runtime", "complete"])
def test_debug_failure_layer_contains_no_raw_response(monkeypatch, phase):
    secret = "mnm_" + "x" * 48
    envelope = {"phase": phase, "pageCount": 1, "status": None, "error": secret}
    monkeypatch.setattr(
        "deploy.installed_upgrade_diagnostics.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, json.dumps(envelope), secret),
    )
    assert inspect_local_status(12345, {}) == {"available": False, "probe": phase, "page_count": 1}


def test_unknown_debug_status_and_counts_are_omitted(monkeypatch):
    secret = "mnm_" + "x" * 48
    envelope = {"phase": secret, "pageCount": secret, "status": {"message": secret}}
    monkeypatch.setattr(
        "deploy.installed_upgrade_diagnostics.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, json.dumps(envelope), secret),
    )
    assert inspect_local_status(12345, {}) == {"available": True}
