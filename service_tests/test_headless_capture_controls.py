"""Portable headless configuration, credential and command-resource boundaries."""

import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mnemion import local_state
from mnemion.connectors.config import ConnectorConfig, read_config
from mnemion.connectors.headless_capture_control import perform
from mnemion.connectors.conversation_inbox import InboxError


@pytest.fixture
def configuration(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    return {
        "service_url": "http://127.0.0.1:9",
        "service_token": {"file": "private/application.token"},
        "connector_id": str(uuid4()),
        "provider": {
            "type": "conversations",
            "path": "logs",
            "scope_id": "fixture",
            "name": "Fixture",
            "members": [],
            "publish_to_mapped_members": True,
            "capture_mode": "messages",
            "state_directory": "private/provider",
        },
        "capture": {
            "id": str(uuid4()),
            "tenant_id": str(uuid4()),
            "principal_id": str(uuid4()),
            "source_id": str(uuid4()),
            "grant_id": str(uuid4()),
            "keep_accepted": True,
            "state_directory": "private",
            "inbox_key": {"file": "private/inbox.key"},
        },
    }


def configured(tmp_path, configuration):
    path = tmp_path / "connector.json"
    path.write_text(json.dumps(configuration), encoding="utf-8")
    path.chmod(0o600)
    return path, read_config(path)


def test_explicit_retention_and_policy_are_not_coerced_or_assumed(configuration):
    for value in (False, 1, "true"):
        changed = json.loads(json.dumps(configuration))
        changed["capture"]["keep_accepted"] = value
        with pytest.raises(ValidationError):
            ConnectorConfig.model_validate(changed)
    configuration["provider"]["include"] = ["secret*.jsonl"]
    with pytest.raises(ValidationError, match="explicit capture policy"):
        ConnectorConfig.model_validate(configuration)
    configuration.pop("capture")
    assert ConnectorConfig.model_validate(configuration).capture is None


def test_relative_private_references_and_offline_inspection_do_not_need_credentials(
    tmp_path, configuration
):
    path, config = configured(tmp_path, configuration)
    assert config.capture.inbox_key.file == tmp_path / "private/inbox.key"
    assert config.capture.state_directory == tmp_path / "private"
    (tmp_path / "logs/chat.jsonl").write_text('{"role":"user","content":"preview only"}\n')
    result = subprocess.run(
        [sys.executable, "-m", "mnemion.connectors.runner", "--config", str(path), "--inspect"],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=Path(__file__).parents[1],
    )
    assert result.returncode == 0, result.stderr
    preview = json.loads(result.stdout)["preview"]
    assert preview["records"]["selected"] == 1 and not preview["content_saved"]
    assert "preview only" not in result.stdout and not config.capture.inbox_key.file.exists()


def test_generated_keys_are_exclusive_private_and_never_enter_output(tmp_path, configuration):
    _, config = configured(tmp_path, configuration)
    result = perform(config, {"action": "key", "confirm": True})
    secret = config.capture.inbox_key.file.read_text().strip()
    assert len(secret) == 44 and secret not in json.dumps(result)
    if os.name == "posix":
        assert config.capture.inbox_key.file.stat().st_mode & 0o077 == 0
    with pytest.raises(FileExistsError):
        perform(config, {"action": "key", "confirm": True})
    assert config.capture.inbox_key.file.read_text().strip() == secret
    config.capture.inbox_key.file = tmp_path / "logs/dangerous.jsonl"
    with pytest.raises(InboxError, match="capture_storage_not_private"):
        perform(config, {"action": "key", "confirm": True})
    assert not config.capture.inbox_key.file.exists()


def test_cli_errors_never_echo_inline_credentials_or_raw_config(tmp_path, configuration):
    configuration["capture"]["inbox_key"] = "private-example-key-must-not-be-printed"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(configuration))
    result = subprocess.run(
        [sys.executable, "-m", "mnemion.connectors.runner", "--config", str(path)],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=Path(__file__).parents[1],
    )
    assert result.returncode == 2
    assert "private-example-key-must-not-be-printed" not in result.stdout + result.stderr
    assert json.loads(result.stderr)["error"] == "invalid_config"


def test_real_child_exits_at_its_memory_budget():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from mnemion.connectors.capture_resources import bounded\n"
            "import time\nwith bounded(128):\n data=bytearray(160*1024**2)\n time.sleep(4)\n",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=Path(__file__).parents[1],
    )
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"] == "capture_memory_limit"


def test_status_rejects_unbounded_or_content_bearing_observations(tmp_path, configuration):
    _, config = configured(tmp_path, configuration)
    from mnemion.connectors.headless_capture import FORMAT, paths, status

    local_state.write(
        paths(config)[1],
        {
            "format": FORMAT,
            "id": str(config.capture.id),
            "state": "finished",
            "unexpected_content": "not a status field",
        },
    )
    with pytest.raises(InboxError, match="capture_integrity_failed"):
        status(config)
