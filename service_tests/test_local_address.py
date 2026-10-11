"""A stopped workspace can change its API port without changing its identity."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from mnemion import local_state as state
from mnemion.local_memory import MemoryChange, configure
from mnemion.local_workspace import PortChange, SetupOptions, change_port, configuration


def workspace(tmp_path):
    root = state.directory(tmp_path / "Workspace Équipe")
    settings = {
        "format": 1,
        "workspace_id": str(uuid4()),
        "created_at": "2026-10-11T00:00:00Z",
        **SetupOptions(workspace_name="My memories", owner_name="Owner").model_dump(),
        "database_port": 17893,
    }
    state.write(root / "configuration.json", settings)
    state.write(root / "credentials.json", {"fixture": "retain this private identity"})
    state.write(root / "model-state.json", {"fixture": "retain the downloaded model"})
    configure(root, MemoryChange(mode="manual", limit_mib=512), initial=True)
    return root, settings


def request(settings, port=None):
    return PortChange(
        workspace_id=UUID(settings["workspace_id"]), expected_port=settings["port"], port=port
    )


def test_automatic_address_preserves_workspace_keys_models_and_budget(tmp_path):
    root, saved = workspace(tmp_path)
    before = {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    updated = change_port(root, request(saved))
    assert updated == {**saved, "port": updated["port"]}
    assert 1024 <= updated["port"] <= 65535
    assert updated["port"] != saved["database_port"]
    assert configuration(root) == updated
    for path, content in before.items():
        if path.name != "configuration.json":
            assert (root / path).read_bytes() == content
    if os.name != "nt":
        assert (root / "configuration.json").stat().st_mode & 0o077 == 0


def test_requested_busy_or_database_port_never_selects_another_silently(tmp_path):
    root, saved = workspace(tmp_path)
    original = (root / "configuration.json").read_bytes()
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        with pytest.raises(state.LocalSetupError) as caught:
            change_port(root, request(saved, occupied.getsockname()[1]))
        assert caught.value.code == "port_in_use"
    with pytest.raises(state.LocalSetupError) as caught:
        change_port(root, request(saved, saved["database_port"]))
    assert caught.value.code == "invalid_port"
    assert (root / "configuration.json").read_bytes() == original


def test_changed_workspace_or_stale_address_cannot_be_overwritten(tmp_path):
    root, saved = workspace(tmp_path)
    original = (root / "configuration.json").read_bytes()
    for change in (
        PortChange(workspace_id=uuid4(), expected_port=saved["port"]),
        PortChange(workspace_id=UUID(saved["workspace_id"]), expected_port=saved["port"] + 1),
    ):
        with pytest.raises(state.LocalSetupError) as caught:
            change_port(root, change)
        assert caught.value.code == "settings_changed"
    assert (root / "configuration.json").read_bytes() == original


def test_interrupted_address_write_preserves_the_previous_configuration(tmp_path, monkeypatch):
    root, saved = workspace(tmp_path)
    original = (root / "configuration.json").read_bytes()

    def interrupted(*args):
        raise OSError("simulated interrupted replacement")

    monkeypatch.setattr(os, "replace", interrupted)
    with pytest.raises(OSError):
        change_port(root, request(saved))
    assert (root / "configuration.json").read_bytes() == original


@pytest.mark.parametrize(
    "change", [{"port": True}, {"port": "7893"}, {"port": 80}, {"port": 65536}, {"host": "0.0.0.0"}]
)
def test_local_address_contract_never_admits_listener_hosts_or_invalid_ports(change):
    payload = {"workspace_id": str(uuid4()), "expected_port": 7892, "port": None, **change}
    with pytest.raises(ValidationError):
        PortChange.model_validate_json(json.dumps(payload))


def test_operator_refuses_a_running_workspace_and_reports_saved_state_without_credentials(tmp_path):
    root, saved = workspace(tmp_path)
    command = [
        sys.executable,
        "-c",
        "from mnemion.service.cli import main; raise SystemExit(main())",
        "local",
        "port",
        "--root",
        str(root),
    ]
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}

    def call():
        return subprocess.run(
            command,
            input=request(saved).model_dump_json() + "\n",
            text=True,
            capture_output=True,
            env=environment,
            timeout=20,
        )

    with state.lock(root):
        refused = call()
        assert refused.returncode != 0
        assert json.loads(refused.stdout)["code"] == "workspace_busy"
    accepted = call()
    assert accepted.returncode == 0, accepted.stderr
    response = json.loads(accepted.stdout)
    assert response["event"] == "status"
    assert response["settings"] == configuration(root)
    assert response["settings"]["workspace_id"] == saved["workspace_id"]
    assert "retain this private identity" not in accepted.stdout


def test_address_change_refuses_a_linked_configuration(tmp_path):
    root, saved = workspace(tmp_path)
    os.link(root / "configuration.json", root / "alias.json")
    with pytest.raises(state.LocalSetupError, match="without links"):
        change_port(root, request(saved))
