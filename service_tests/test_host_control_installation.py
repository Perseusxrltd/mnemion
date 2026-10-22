"""Adoption is explicit, atomic and independent of memory API availability."""

import asyncio
import os
from pathlib import Path
import signal
import socket
import sys

import asyncssh
import pytest

from mnemion.host_control import HostControlError, installation, lifecycle
from mnemion.host_control.protocol import Operator
from mnemion.host_control.transport import Connection, call
from mnemion.host_control.store import Store
from mnemion.service import runtime_pins, service_updates as updates, supervision
from mnemion.service import update_state as state_io
from mnemion.service.update_manifest import ManifestError
from mnemion.version import __version__
from service_tests.test_host_control_store import request
from service_tests.test_supervision import wait_until

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Unix managed host adoption")


@pytest.fixture
def prepared_host(tmp_path):
    roles = tmp_path / "roles.json"
    state_io.write(roles, {"database_url": "fixture-api", "worker_database_url": "fixture-worker"})
    service = tmp_path / "memory service"
    supervision.prepare(service, roles, roles, managed_updates=True, inherit_environment=False)
    _, root, config = updates._root(service)
    baseline = {
        "slot": None,
        "python": sys.executable,
        "directory": config["directory"],
        "package": str(Path(installation.__file__).resolve().parents[1]),
        "version": __version__,
        "isolated": False,
        "migrations": {},
        "generations": [],
    }
    state_io.write(root / "active.json", baseline)
    state_io.write(
        root / "config.json",
        {
            "format": 1,
            "enabled": False,
            "interval_seconds": 21600,
            "uv": "not-used",
            "baseline": baseline,
        },
    )
    key = asyncssh.generate_private_key("ssh-ed25519")
    operator = Operator(
        name="Independent custodian",
        role="custodian",
        public_key=key.export_public_key().decode().strip(),
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    return service, tmp_path / "control state 20%", operator, key, port


def test_actual_runtime_probe_and_idempotent_adoption_preserve_identity(prepared_host):
    service, control, operator, key, port = prepared_host
    first = installation.adopt(control, service, operator, port=port)
    files = {name: (control / name).read_bytes() for name in ("host.key", "settings.json")}
    second = installation.adopt(control, service, operator, port=port)
    assert second["already_prepared"] and first["connection"] == second["connection"]
    assert {name: (control / name).read_bytes() for name in files} == files
    root, value = installation.settings(control)
    assert root == control and value["host_id"] == first["connection"]["host_id"]
    pins = runtime_pins.read(service / "updates")
    assert pins["state"] == str(control) and pins["current"]["slot"] is None
    assert first["connection"]["operator_key_fingerprint"] == key.get_fingerprint("sha256")
    assert not (control / "ready.json").exists()
    assert not supervision.status(service)["running"]


def test_adoption_finishes_a_lost_pin_write_without_rekeying(prepared_host, monkeypatch):
    service, control, operator, _, port = prepared_host
    original = installation._pins
    monkeypatch.setattr(installation, "_pins", lambda *_: (_ for _ in ()).throw(OSError()))
    with pytest.raises(OSError):
        installation.adopt(control, service, operator, port=port)
    key = (control / "host.key").read_bytes()
    assert (control / "settings.json").exists()
    assert runtime_pins.read(service / "updates") is None
    monkeypatch.setattr(installation, "_pins", original)
    result = installation.adopt(control, service, operator, port=port)
    assert result["already_prepared"] and (control / "host.key").read_bytes() == key
    assert runtime_pins.read(service / "updates")["host_id"] == result["connection"]["host_id"]


def test_unapproved_network_or_nested_state_never_creates_an_adoption(prepared_host):
    service, control, operator, _, port = prepared_host
    with pytest.raises(HostControlError, match="network listener"):
        installation.adopt(control, service, operator, bind="0.0.0.0", port=port)
    with pytest.raises(HostControlError, match="outside"):
        installation.adopt(service / "control", service, operator, port=port)
    assert not control.exists() and not (service / "control").exists()
    assert runtime_pins.read(service / "updates") is None


@pytest.mark.parametrize("filename", ["launcher.py", "supervisord.conf", "launchd.plist"])
def test_changed_startup_configuration_is_refused(prepared_host, filename):
    service, control, operator, _, port = prepared_host
    installation.adopt(control, service, operator, port=port)
    with (control / filename).open("ab") as stream:
        stream.write(b"\nchanged")
    with pytest.raises(HostControlError, match="changed host startup"):
        installation.settings(control)


def test_changed_control_host_key_cannot_replace_an_enrollment(prepared_host):
    service, control, operator, _, port = prepared_host
    installation.adopt(control, service, operator, port=port)
    (control / "host.key").write_bytes(
        asyncssh.generate_private_key("ssh-ed25519").export_private_key()
    )
    with pytest.raises(HostControlError, match="identity"):
        installation.settings(control)


@pytest.mark.parametrize("kind", ["invalid", "broken_link"])
def test_invalid_runtime_custody_is_not_treated_as_absent(tmp_path, kind):
    root = state_io.directory(tmp_path / "updates")
    path = root / runtime_pins.FILE
    if kind == "invalid":
        state_io.write(path, {"format": 1, "current": {}})
    else:
        path.symlink_to(tmp_path / "absent")
    with pytest.raises(ManifestError):
        runtime_pins.protected(root)


def test_independent_supervisor_serves_real_ssh_while_memory_api_is_absent(prepared_host):
    service, control, operator, key, port = prepared_host
    adopted = installation.adopt(control, service, operator, port=port)
    connection = Connection.model_validate(adopted["connection"])

    def remote(action, **fields):
        return asyncio.run(
            call(
                connection,
                key.export_private_key(),
                request(adopted["connection"], action, **fields),
            )
        )

    try:
        assert lifecycle.start(control)["ready"]
        assert not supervision.status(service)["running"]
        observed = remote("host.status")
        assert observed["ok"] and observed["result"]["service"]["running"] is False
        operation = remote("service.stop", approve_service_interruption=True)["result"]
        complete = wait_until(
            lambda: (
                result
                if (
                    result := remote("operations.get", operation_id=operation["operation_id"])[
                        "result"
                    ]
                )["phase"]
                == "succeeded"
                else None
            )
        )
        assert complete["result"]["stopped"] and complete["effect_started_at"]
        assert lifecycle.status(control)["ready"]
        first = state_io.read(control / "ready.json")
        os.kill(first["pid"], signal.SIGTERM)
        wait_until(
            lambda: (
                value
                if (value := lifecycle.status(control))["ready"]
                and state_io.read(control / "ready.json")["pid"] != first["pid"]
                else None
            )
        )
        again = remote("operations.get", operation_id=operation["operation_id"])
        assert again["result"] == complete
        assert remote("host.status")["result"]["operator"]["id"] == str(connection.operator_id)
        store = Store(control / "authority")
        with state_io.lock(control / "worker"):
            uncertain = store.enqueue(
                str(connection.operator_id),
                request(
                    adopted["connection"],
                    "service.stop",
                    approve_service_interruption=True,
                ),
            )
            assert store.claim()["operation_id"] == uncertain["operation_id"]
            assert store.interrupted() == 1
        history = remote("operations.list")["result"]["operations"]
        assert any(item["operation_id"] == uncertain["operation_id"] for item in history)
        resolving = remote(
            "operations.resolve",
            operation_id=uncertain["operation_id"],
            approve_current_state=True,
        )["result"]
        wait_until(
            lambda: (
                remote("operations.get", operation_id=resolving["operation_id"])["result"]["phase"]
                == "succeeded"
            )
        )
        original = remote("operations.get", operation_id=uncertain["operation_id"])["result"]
        assert original["phase"] == "failed" and original["error"] == "worker_interrupted"
        assert original["result"]["original_outcome"] == "unconfirmed"
        assert not supervision.status(service)["running"]
    finally:
        assert lifecycle.stop(control)["stopped"]
        assert not supervision.status(service)["running"]
