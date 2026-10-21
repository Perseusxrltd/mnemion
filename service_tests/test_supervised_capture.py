"""Keep explicitly referenced inbox keys across the private supervisor boundary."""

import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import psutil
import pytest

from mnemion.connectors import headless_capture as device
from mnemion.connectors.headless_capture_control import perform
from mnemion.service import supervision
from service_tests.test_capture_custody import custody as custody
from service_tests.test_headless_capture_controls import (
    configuration as configuration,
    configured,
)
from service_tests.test_headless_durable_capture import headless as headless
from service_tests.test_live_conversations import (
    conversation_source as conversation_source,
    encoded,
)
from service_tests.test_supervision import (
    inputs,
    supervised_database as supervised_database,
    wait_until,
)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Supervisor is a Unix process manager")


def prepared(tmp_path, configuration, *, environment=None):
    config_path, config = configured(tmp_path, configuration)
    roles = inputs(tmp_path)
    env_path = tmp_path / "supervisor-environment.json"
    env_path.write_text(json.dumps(environment or {}))
    env_path.chmod(0o600)
    state = tmp_path / "supervisor"
    supervision.prepare(state, roles, roles, environment=env_path, connector_configs=(config_path,))
    return state, config_path, config


@pytest.mark.parametrize("location", ["inherited", "settings"])
def test_supervised_capture_child_can_read_only_its_referenced_keys(
    tmp_path, configuration, monkeypatch, location
):
    secret = base64.b64encode(os.urandom(32)).decode()
    configuration["capture"]["inbox_key"] = {"env": "CAPTURE_FIXTURE_INBOX_KEY"}
    configuration["service_token"] = {"env": "CAPTURE_FIXTURE_APPLICATION_KEY"}
    keys = {
        "CAPTURE_FIXTURE_INBOX_KEY": secret,
        "CAPTURE_FIXTURE_APPLICATION_KEY": "fixture-application-credential",
    }
    for name, value in keys.items():
        monkeypatch.setenv(name, value if location == "inherited" else "wrong-inherited-value")
    monkeypatch.setenv("MNEMION_ADMIN_DATABASE_URL", "fixture-admin-never-inherited")
    monkeypatch.setenv("PGPASSWORD", "fixture-database-never-inherited")
    monkeypatch.setenv("UNRELATED_PRIVATE_KEY", "fixture-unrelated-never-inherited")
    state, config_path, config = prepared(
        tmp_path, configuration, environment=keys if location == "settings" else None
    )
    saved = (state / "settings.json").read_bytes()
    launches = []

    def execute(executable, arguments, environment):
        launches.append(arguments)
        assert executable == sys.executable
        assert arguments[-3:] == ["--config", str(config_path), "--watch"]
        assert all(
            name not in environment
            for name in ("MNEMION_ADMIN_DATABASE_URL", "PGPASSWORD", "UNRELATED_PRIVATE_KEY")
        )
        # Cross a real process boundary and use the capture key reader. No key
        # bytes enter command arguments, logs, status or assertion diagnostics.
        result = subprocess.run(
            [
                executable,
                "-c",
                "import sys\n"
                "from pathlib import Path\n"
                "from mnemion.connectors.config import read_config\n"
                "from mnemion.connectors.headless_capture import key_bytes, reference\n"
                "c=read_config(Path(sys.argv[1]))\n"
                "assert len(key_bytes(reference(c.capture.inbox_key))) == 32\n"
                "assert reference(c.service_token) == 'fixture-application-credential'\n",
                str(config_path),
            ],
            env=environment,
            cwd=Path(__file__).parents[1],
            capture_output=True,
            timeout=15,
        )
        assert secret.encode() not in result.stdout + result.stderr
        assert result.returncode == 0, "The supervised child could not reopen its configured keys"

    monkeypatch.chdir(Path(__file__).parents[1])
    monkeypatch.setattr(supervision.os, "execve", execute)
    assert supervision.connector_child(state, str(config.connector_id)) == 0
    assert len(launches) == 1 and (state / "settings.json").read_bytes() == saved


@pytest.mark.parametrize(
    "reference",
    [
        "CAPTURE_FIXTURE_MISSING",
        "MNEMION_ADMIN_DATABASE_URL",
        "MNEMION_VAULT_KEY",
        "PYTHONPATH",
    ],
)
def test_supervised_capture_refuses_missing_or_privileged_key_references_before_launch(
    tmp_path, configuration, monkeypatch, reference
):
    configuration["capture"]["inbox_key"] = {"env": reference}
    monkeypatch.delenv(reference, raising=False)
    if reference != "CAPTURE_FIXTURE_MISSING":
        monkeypatch.setenv(reference, "private-fixture-never-log")
    state, _, config = prepared(tmp_path, configuration)
    saved = (state / "settings.json").read_bytes()
    launches = []
    monkeypatch.chdir(Path(__file__).parents[1])
    monkeypatch.setattr(supervision.os, "execve", lambda *args: launches.append(True))
    with pytest.raises(supervision.SupervisionError) as error:
        supervision.connector_child(state, str(config.connector_id))
    assert "private-fixture-never-log" not in str(error.value)
    assert not launches and (state / "settings.json").read_bytes() == saved


def test_real_supervisor_restarts_capture_and_delivers_the_original_offline_queue(
    env, headless, supervised_database, tmp_path, monkeypatch
):
    config = headless["config"]
    secret = base64.b64encode(os.urandom(32)).decode()
    key_name = "CAPTURE_SUPERVISOR_INBOX_KEY"
    monkeypatch.setenv(key_name, secret)
    config.capture.inbox_key = type(config.capture.inbox_key)(env=key_name)
    config.remote_sync = False
    headless["file"].write_text(config.model_dump_json(), encoding="utf-8")
    preview = perform(config, {"action": "preview"})
    enrolled = perform(
        config,
        {
            "action": "enroll",
            "expected_revision": "not-enrolled",
            "preview_hash": preview["configuration_hash"],
            "confirm": True,
        },
    )
    perform(
        config, {"action": "resume", "expected_revision": enrolled["revision"], "confirm": True}
    )
    key_hash = device.read_record(config)["key_sha256"]
    text = "Supervised capture retains an offline memory across a worker crash"
    source = config.provider.path / "supervised.jsonl"
    source.write_bytes(encoded(text))
    headless["offline"].set()
    api, worker, _ = supervised_database
    roles = inputs(tmp_path, api, worker)
    environment = tmp_path / "capture-environment.json"
    environment.write_text(
        json.dumps(
            {
                key_name: secret,
                "MNEMION_MODEL_OFFLINE": "1",
                "MNEMION_MODEL_CACHE": str(tmp_path / "models"),
                "MNEMION_EVALUATIONS_DISABLED": "1",
                "MNEMION_LIBRARIAN_DISABLED": "1",
            }
        )
    )
    environment.chmod(0o600)
    state = tmp_path / "supervised-capture"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    supervision.prepare(
        state,
        roles,
        roles,
        port=port,
        environment=environment,
        connector_configs=(headless["file"],),
    )
    connector_name = "mnemion-connector-" + config.connector_id.hex

    def capture(**expected):
        activity = device.status(config).get("activity") or {}
        value = (activity.get("report") or {}).get("capture", {})
        return value if all(value.get(key) == count for key, count in expected.items()) else None

    try:
        started = supervision.start(state)
        assert started["running"]
        wait_until(lambda: capture(locally_accepted=1, pending_events=1))
        assert text.encode() not in (device.paths(config)[2] / "inbox.sqlite3").read_bytes()
        current = supervision.status(state)
        original = next(row for row in current["processes"] if row["name"] == connector_name)
        child = psutil.Process(original["pid"])
        assert str(headless["file"]) in child.cmdline()
        source.unlink()
        headless["offline"].clear()
        child.kill()
        child.wait(timeout=10)

        def restarted():
            row = next(
                item
                for item in supervision.status(state)["processes"]
                if item["name"] == connector_name
            )
            return row if row["statename"] == "RUNNING" and row["pid"] != original["pid"] else None

        replacement = wait_until(restarted)
        final = wait_until(lambda: capture(pending_events=0, stored_events=1))
        assert final["delivery_complete"] and replacement["pid"] != original["pid"]
        assert device.read_record(config)["key_sha256"] == key_hash
        with env.db.transaction(headless["reader"]) as connection:
            identifiers = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM mnemion.memories WHERE deleted_at IS NULL"
                )
            ]
        assert (
            sum(
                text in env.memory.fetch(headless["reader"], item)["content"]
                for item in identifiers
            )
            == 1
        )
        for log in (state / "logs").glob("*.log"):
            assert secret.encode() not in log.read_bytes()
    finally:
        stopped = supervision.stop(state)
        assert stopped["stopped"]
    assert not supervision.status(state)["running"]
