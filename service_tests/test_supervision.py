"""Real user-level process supervision without systemd or production data."""

import json
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import plistlib
import signal
import socket
from threading import Thread
import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import psutil
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from mnemion.service import supervision
from mnemion.service.admin import bootstrap_tenant
from mnemion.service.db import migrate

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Supervisor is a Unix process manager")


@pytest.fixture
def supervised_database(postgres):
    name = "supervised_" + uuid4().hex
    with psycopg.connect(postgres[0], autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    admin = make_conninfo(postgres[0], dbname=name)
    migrate(admin)
    owner = bootstrap_tenant(admin, tenant_name="Supervisor fixture", administrator_name="Owner")
    try:
        yield (
            make_conninfo(postgres[1], dbname=name),
            make_conninfo(postgres[2], dbname=name),
            owner,
        )
    finally:
        with psycopg.connect(postgres[0], autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def inputs(tmp_path, api="fixture-api", worker="fixture-worker"):
    path = tmp_path / "roles.json"
    path.write_text(json.dumps({"database_url": api, "worker_database_url": worker}))
    path.chmod(0o600)
    return path


def wait_until(condition, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if value := condition():
            return value
        time.sleep(0.25)
    raise AssertionError("The supervised fixture did not reach the required state")


def test_real_api_and_worker_recover_from_crashes_and_stop_cleanly(
    supervised_database, tmp_path, monkeypatch
):
    api, worker, owner = supervised_database
    roles = inputs(tmp_path, api, worker)
    state = tmp_path / "private state 20%"
    runtime_env = tmp_path / "environment.json"
    runtime_env.write_text(
        json.dumps(
            {
                "MNEMION_MODEL_OFFLINE": "1",
                "MNEMION_MODEL_CACHE": str(tmp_path / "models"),
                "MNEMION_EVALUATIONS_DISABLED": "1",
                "MNEMION_LIBRARIAN_DISABLED": "1",
            }
        )
    )
    monkeypatch.setenv("MNEMION_ADMIN_DATABASE_URL", "sentinel-admin-must-not-reach-children")
    monkeypatch.setenv("MNEMION_API_KEY", "sentinel-owner-must-not-reach-children")
    monkeypatch.setenv("PGPASSWORD", "sentinel-postgres-must-not-reach-children")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    prepared = supervision.prepare(state, roles, roles, port=port, environment=runtime_env)
    assert prepared["systemd_required"] is False
    assert r"20\%" in prepared["cron_entry"]
    launchd = plistlib.loads(Path(prepared["launchd_file"]).read_bytes())
    assert launchd["Label"] == prepared["launchd_label"]
    assert launchd["ProgramArguments"][-3:] == ["run", "--state-dir", str(state)]
    assert launchd["KeepAlive"] == {"SuccessfulExit": False}
    assert supervision.prepare(state, roles, roles, port=port, environment=runtime_env) == prepared
    assert json.loads((state / "api.json").read_text()) == {"database_url": api}
    assert json.loads((state / "worker.json").read_text()) == {"worker_database_url": worker}
    assert "sentinel-admin" not in (state / "settings.json").read_text()
    runtime = Path(json.loads((state / "settings.json").read_text())["runtime"])
    recorded = []
    try:
        current = supervision.start(state)
        assert current["running"]
        current = wait_until(
            lambda: value if (value := supervision.status(state))["ready"] else None
        )
        assert current["instance_matches"]
        recorded = [psutil.Process(item["pid"]) for item in current["processes"]]
        assert supervision.start(state)["supervisor_pid"] == current["supervisor_pid"]
        for item in current["processes"]:
            environment = psutil.Process(item["pid"]).environ()
            assert "MNEMION_ADMIN_DATABASE_URL" not in environment
            assert "MNEMION_API_KEY" not in environment
            assert "PGPASSWORD" not in environment
            if item["name"] == "mnemion-api":
                assert "MNEMION_WORKER_DATABASE_URL" not in environment
            else:
                assert "MNEMION_DATABASE_URL" not in environment
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            assert client.get("/v1/me").status_code == 401
            assert (
                client.get(
                    "/v1/me", headers={"Authorization": "Bearer " + owner["api_key"]}
                ).status_code
                == 200
            )
        for role in ("mnemion-worker", "mnemion-api"):
            previous = next(item["pid"] for item in current["processes"] if item["name"] == role)
            os.kill(previous, signal.SIGKILL)

            def replacement():
                value = supervision.status(state)
                return (
                    value
                    if value["ready"]
                    and any(
                        item["name"] == role and item["pid"] != previous
                        for item in value["processes"]
                    )
                    else None
                )

            recovered = wait_until(replacement)
            assert recovered["supervisor_pid"] == current["supervisor_pid"]
            recorded += [psutil.Process(item["pid"]) for item in recovered["processes"]]
            current = recovered
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            assert (
                client.get(
                    "/v1/me", headers={"Authorization": "Bearer " + owner["api_key"]}
                ).status_code
                == 200
            )
        assert (runtime / "control.sock").stat().st_mode & 0o777 == 0o600
        assert all(path.stat().st_mode & 0o077 == 0 for path in state.glob("*.json"))
        assert supervision.stop(state) == {"stopped": True}
        assert not supervision.status(state)["running"]
        assert supervision.stop(state)["already_stopped"]
    finally:
        supervision.stop(state)
        for process in recorded:
            assert not process.is_running() or process.status() == psutil.STATUS_ZOMBIE
        try:
            runtime.rmdir()
        except OSError:
            pass


@pytest.mark.parametrize("suffix", ["bad;command", "bad#comment", "bad\nsection"])
def test_supervisor_ini_injection_is_rejected_before_credentials_are_published(tmp_path, suffix):
    roles = inputs(tmp_path)
    state = tmp_path / suffix
    with pytest.raises(ValueError, match="paths cannot"):
        supervision.prepare(state, roles, roles)
    assert not (state / "api.json").exists()


def test_configuration_cannot_replace_existing_credentials_or_accept_admin_environment(tmp_path):
    roles = inputs(tmp_path)
    state = tmp_path / "state"
    supervision.prepare(state, roles, roles)
    before = (state / "api.json").read_bytes()
    roles.write_text(
        json.dumps({"database_url": "changed", "worker_database_url": "fixture-worker"})
    )
    with pytest.raises(ValueError, match="settings differ"):
        supervision.prepare(state, roles, roles)
    assert (state / "api.json").read_bytes() == before
    environment = tmp_path / "environment.json"
    environment.write_text(json.dumps({"MNEMION_ADMIN_DATABASE_URL": "not-a-runtime-setting"}))
    with pytest.raises(ValueError, match="role files"):
        supervision.prepare(tmp_path / "other", roles, roles, environment=environment)


def test_saved_configuration_survives_formatter_changes_but_rejects_edits(tmp_path, monkeypatch):
    roles = inputs(tmp_path)
    state = tmp_path / "state"
    supervision.prepare(state, roles, roles)
    monkeypatch.setattr(supervision, "render", lambda *args: "a future formatter")
    assert supervision.settings(state)[1]["format"] == 1
    config = state / "supervisord.conf"
    config.write_text(config.read_text() + "\n# unexpected edit\n")
    with pytest.raises(ValueError, match="configuration was changed"):
        supervision.settings(state)


def test_an_unresponsive_supervisor_is_not_reported_as_stopped(tmp_path, monkeypatch):
    roles = inputs(tmp_path)
    state = tmp_path / "state"
    supervision.prepare(state, roles, roles)

    def unavailable(value):
        raise TimeoutError("The process has not answered")

    monkeypatch.setattr(supervision, "_rpc", unavailable)
    with pytest.raises(TimeoutError):
        supervision.status(state)
    with pytest.raises(TimeoutError):
        supervision.stop(state)


def test_stop_waits_for_a_closed_socket_after_a_shutdown_connection_reset(tmp_path, monkeypatch):
    roles = inputs(tmp_path)
    state = tmp_path / "state"
    supervision.prepare(state, roles, roles)
    attempts = 0

    def disconnecting(value):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return nullcontext(SimpleNamespace(supervisor=SimpleNamespace(shutdown=lambda: True)))
        if attempts == 2:
            raise ConnectionResetError("shutdown closed the in-flight connection")
        raise FileNotFoundError("shutdown completed")

    monkeypatch.setattr(supervision, "_rpc", disconnecting)
    assert supervision.stop(state) == {"stopped": True}


def test_prepared_state_rejects_exposed_credentials(tmp_path):
    roles = inputs(tmp_path)
    state = tmp_path / "state"
    supervision.prepare(state, roles, roles)
    (state / "api.json").chmod(0o644)
    with pytest.raises(ValueError, match="private and owned"):
        supervision.settings(state)


def test_cli_does_not_echo_private_values_in_parser_errors(tmp_path, capsys):
    roles = inputs(tmp_path)
    result = supervision.main(
        [
            "prepare",
            "--state-dir",
            str(tmp_path / "state"),
            "--api-credentials",
            str(roles),
            "--worker-credentials",
            str(roles),
            "--host",
            "sentinel-private-input",
        ]
    )
    assert result == 2
    output = capsys.readouterr()
    assert "sentinel-private-input" not in output.err + output.out
    assert "error" in json.loads(output.err)


@pytest.mark.parametrize("same_instance", [False, True])
def test_a_different_http_service_cannot_satisfy_instance_readiness(
    tmp_path, monkeypatch, same_instance
):
    class ForeignService(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header(
                "X-Mnemion-Instance", instance if same_instance else "mnemion-" + "0" * 24
            )
            self.send_header("X-Mnemion-Process", str(os.getpid()))
            self.end_headers()

        def log_message(self, *args):
            pass

    roles = inputs(tmp_path)
    state = tmp_path / "state"
    server = ThreadingHTTPServer(("127.0.0.1", 0), ForeignService)
    thread = Thread(target=server.serve_forever, daemon=True)
    try:
        supervision.prepare(state, roles, roles, port=server.server_port)
        instance = supervision.settings(state)[1]["identifier"]
        process_info = [
            {"name": "mnemion-" + role, "statename": "RUNNING", "pid": 1, "exitstatus": 0}
            for role in ("api", "worker")
        ]
        client = SimpleNamespace(
            supervisor=SimpleNamespace(getAllProcessInfo=lambda: process_info, getPID=lambda: 1)
        )
        monkeypatch.setattr(supervision, "_rpc", lambda value: nullcontext(client))
        thread.start()
        result = supervision.status(state)
        assert result["running"] and result["http_ready"]
        assert not result["ready"] and not result["instance_matches"]
    finally:
        if thread.is_alive():
            server.shutdown()
            thread.join(timeout=3)
        server.server_close()
