"""Managed scan lifetimes, update coordination and secret-free observations."""

import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

import psutil
import pytest

from mnemion.connectors import managed, runner
from mnemion.service import service_updates, update_state
from mnemion.service.update_manifest import ManifestError
from mnemion.version import __version__

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Managed service updates run on Unix")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    state = update_state.directory(tmp_path / "managed")
    root = update_state.directory(state / "updates")
    identifier = str(uuid4())
    registry = update_state.directory(root / "connectors")
    entry = update_state.directory(registry / identifier)
    path = tmp_path / "connector.json"
    update_state.write(
        path,
        {
            "service_url": "http://127.0.0.1:7892",
            "service_token": {"file": "private.token"},
            "connector_id": identifier,
            "poll_seconds": 30,
            "remote_sync": False,
            "provider": {
                "type": "filesystem",
                "path": "notes",
                "scope_id": "fixture",
                "name": "Fixture",
                "members": ["employee:one"],
                "publish_to_mapped_members": True,
            },
        },
    )
    monkeypatch.setattr(service_updates, "_root", lambda _: (state, root, {}))
    monkeypatch.setattr(managed.supervision, "status", lambda _: {"ready": True})
    return SimpleNamespace(state=state, root=root, identifier=identifier, entry=entry, path=path)


def executable(tmp_path, version, body=""):
    location = tmp_path / version
    package = location / "mnemion/connectors"
    package.mkdir(parents=True)
    (location / "mnemion/__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    (package / "runner.py").write_text(
        "import json, os, sys, time\nfrom pathlib import Path\n"
        "assert sys.argv[1] == '--config' and len(sys.argv) == 3\n"
        "config = json.loads(Path(sys.argv[2]).read_text())\n"
        "with Path(os.environ['MNEMION_FIXTURE_RECEIPT']).open('a') as out:\n"
        f" out.write(json.dumps({{'version': {version!r}, 'config': config, 'pid': os.getpid(), "
        "'trigger': os.environ.get('MNEMION_CONNECTOR_SCAN_TRIGGER'), "
        "'database_inherited': 'MNEMION_ADMIN_DATABASE_URL' in os.environ, "
        "'owner_inherited': 'MNEMION_API_KEY' in os.environ, "
        "'ssh_preserved': os.environ.get('SSH_AUTH_SOCK') == 'fixture-agent'}) + '\\n')\n"
        "time.sleep(0.05)\n" + body
    )
    return {
        "version": version,
        "python": sys.executable,
        "directory": str(location),
        "isolated": False,
    }


def test_each_scan_uses_current_verified_runtime_including_rollback(setup, tmp_path, monkeypatch):
    first = executable(tmp_path, "4.1.2")
    second = executable(tmp_path, "4.1.3")
    runtimes = iter([first, second, first])
    monkeypatch.setattr(service_updates, "resolved_runtime", lambda _: next(runtimes))
    receipt = tmp_path / "runs.jsonl"
    monkeypatch.setenv("MNEMION_FIXTURE_RECEIPT", str(receipt))
    monkeypatch.setenv("MNEMION_ADMIN_DATABASE_URL", "must-not-be-inherited")
    monkeypatch.setenv("MNEMION_API_KEY", "unrelated-owner-must-not-be-inherited")
    monkeypatch.setenv("SSH_AUTH_SOCK", "fixture-agent")
    before = setup.path.read_bytes()
    config = managed._configuration(setup.path)
    observation = managed.Observation(setup.entry, setup.identifier)
    with update_state.lock(setup.entry) as singleton:
        for trigger in ("startup", "poll", "requested"):
            assert (
                managed._scan(
                    setup.state,
                    setup.root,
                    config,
                    setup.entry,
                    singleton,
                    observation,
                    managed.Control(),
                    trigger=trigger,
                )
                == 0
            )
    rows = [json.loads(line) for line in receipt.read_text().splitlines()]
    assert [row["version"] for row in rows] == ["4.1.2", "4.1.3", "4.1.2"]
    assert [row["trigger"] for row in rows] == ["startup", "poll", "requested"]
    assert len({row["pid"] for row in rows}) == 3
    for row in rows:
        assert row["config"]["connector_id"] == setup.identifier
        assert row["config"]["provider"]["path"] == str(tmp_path / "notes")
        assert row["config"]["service_token"]["file"] == str(tmp_path / "private.token")
        assert not row["database_inherited"] and not row["owner_inherited"]
        assert row["ssh_preserved"]
    assert setup.path.read_bytes() == before
    assert not (setup.entry / "scan.json").stat().st_mode & 0o077
    row = managed.status(setup.root)["items"][0]
    assert row["scan_version"] == "4.1.2" and row["launcher_version"] == __version__
    assert row["state"] == "waiting" and row["running"] and not row["scan_running"]
    assert "private.token" not in json.dumps(row) and "service_url" not in row


def test_managed_watch_preserves_poll_and_requested_reasons_through_update_waits(
    setup, tmp_path, monkeypatch
):
    runtime = executable(tmp_path, "4.1.5")
    monkeypatch.setattr(service_updates, "resolved_runtime", lambda _: runtime)
    receipt = tmp_path / "triggers.jsonl"
    monkeypatch.setenv("MNEMION_FIXTURE_RECEIPT", str(receipt))
    monkeypatch.delenv(runner.SCAN_TRIGGER_ENV, raising=False)
    reasons = iter(("poll", "requested"))
    scans = 0

    def wait(*args, **kwargs):
        nonlocal scans
        scans += 1
        if scans == 3:
            raise managed.Stopped()
        return next(reasons)

    # A blocked runtime must retain the already pending requested scan reason.
    waiting = iter((False, False, True, False))
    monkeypatch.setattr(update_state, "connector_update_waiting", lambda _: next(waiting))
    monkeypatch.setattr(managed, "wait_for_sync", wait)
    control = managed.Control()
    monkeypatch.setattr(control, "sleep", lambda _: time.sleep(0.001))
    with pytest.raises(managed.Stopped):
        managed.run(setup.state, setup.path, control)
    rows = [json.loads(line) for line in receipt.read_text().splitlines()]
    assert [row["trigger"] for row in rows] == ["startup", "poll", "requested"]


def test_shared_scan_lease_allows_peers_and_blocks_updates_until_child_exits(tmp_path):
    root = update_state.directory(tmp_path / "updates")
    with update_state.lock(root, shared=True) as descriptor:
        with update_state.lock(root, shared=True):
            with pytest.raises(update_state.OperationBusy):
                with update_state.lock(root):
                    pytest.fail("An update cannot replace a runtime during a scan")
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(20)"], pass_fds=(descriptor,)
        )
    try:
        with pytest.raises(update_state.OperationBusy):
            with update_state.lock(root):
                pytest.fail("A surviving child must retain its lease after launcher exit")
    finally:
        child.terminate()
        child.wait(timeout=5)
    with update_state.lock(root):
        pass


@pytest.mark.parametrize("condition", ["journal", "unready", "invalid_runtime", "updater_busy"])
def test_no_scan_can_start_during_transition_or_from_unverified_runtime(
    setup, monkeypatch, condition
):
    def forbidden(*args, **kwargs):
        pytest.fail("No child may start from this host state")

    monkeypatch.setattr(managed.subprocess, "Popen", forbidden)
    config = managed._configuration(setup.path)
    observation = managed.Observation(setup.entry, setup.identifier)
    if condition == "journal":
        update_state.write(setup.root / "journal.json", {"phase": "starting"})
    if condition == "unready":
        monkeypatch.setattr(managed.supervision, "status", lambda _: {"ready": False})
    if condition == "invalid_runtime":

        def invalid(_):
            raise ManifestError("Managed runtime does not match its verified staging record")

        monkeypatch.setattr(service_updates, "resolved_runtime", invalid)
    with update_state.lock(setup.entry) as singleton:

        def call():
            return managed._scan(
                setup.state,
                setup.root,
                config,
                setup.entry,
                singleton,
                observation,
                managed.Control(),
            )

        if condition == "invalid_runtime":
            with pytest.raises(ManifestError, match="verified"):
                call()
        elif condition == "updater_busy":
            with update_state.lock(setup.root), pytest.raises(update_state.OperationBusy):
                call()
        else:
            assert call() is None


def test_duplicate_managed_launcher_cannot_take_over_registered_connector(setup):
    with update_state.lock(setup.entry), pytest.raises(update_state.OperationBusy):
        managed.run(setup.state, setup.path, managed.Control())
    assert not (setup.entry / "status.json").exists()


def test_config_identity_and_private_regular_file_are_required(setup, tmp_path):
    with pytest.raises(ManifestError, match="identity"):
        managed._configuration(setup.path, str(uuid4()))
    link = tmp_path / "linked.json"
    link.symlink_to(setup.path)
    with pytest.raises(ManifestError, match="private regular"):
        managed._configuration(link)
    setup.path.chmod(0o644)
    with pytest.raises(ManifestError, match="private regular"):
        managed._configuration(setup.path)


def test_explicit_connector_key_reference_is_preserved_without_database_credentials(
    setup, monkeypatch
):
    config = managed._configuration(setup.path)
    config.service_token = type(config.service_token)(env="MNEMION_API_KEY")
    monkeypatch.setenv("MNEMION_API_KEY", "explicit-connector-reference")
    monkeypatch.setenv("MNEMION_DATABASE_URL", "restricted-database")
    assert managed._environment(config)["MNEMION_API_KEY"] == "explicit-connector-reference"
    assert "MNEMION_DATABASE_URL" not in managed._environment(config)
    config.service_token = type(config.service_token)(env="MNEMION_DATABASE_URL")
    with pytest.raises(ManifestError, match="dedicated"):
        managed._environment(config)


def test_stale_process_birth_is_not_reported_as_a_live_connector(setup):
    observation = managed.Observation(setup.entry, setup.identifier)
    observation.record("waiting")
    value = update_state.read(setup.entry / "status.json")
    identity = value["process_identity"]
    key = "ticks" if identity["kind"] == "linux-start" else "created"
    identity[key] += 1
    update_state.write(setup.entry / "status.json", value)
    result = managed.status(setup.root)
    assert result["unmanaged_processes_included"] is False
    assert result["items"][0]["state"] == "stopped"
    assert not result["items"][0]["running"]


def test_stop_drains_scan_and_provider_in_separate_process_group(setup, tmp_path, monkeypatch):
    pid_file = tmp_path / "provider.pid"
    runtime = executable(
        tmp_path,
        "4.1.3",
        (
            "import subprocess\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)\n"
            f"Path({str(pid_file)!r}).write_text(str(child.pid))\n"
            "time.sleep(60)\n"
        ),
    )
    monkeypatch.setattr(service_updates, "resolved_runtime", lambda _: runtime)
    monkeypatch.setenv("MNEMION_FIXTURE_RECEIPT", str(tmp_path / "run.jsonl"))

    class Control(managed.Control):
        def sleep(self, seconds):
            if pid_file.exists():
                self.stop()
            return super().sleep(seconds)

    observation = managed.Observation(setup.entry, setup.identifier)
    try:
        with update_state.lock(setup.entry) as singleton, pytest.raises(managed.Stopped):
            managed._scan(
                setup.state,
                setup.root,
                managed._configuration(setup.path),
                setup.entry,
                singleton,
                observation,
                Control(),
            )
        assert not managed._alive(observation.value["scan_identity"])
        provider = int(pid_file.read_text())
        assert (
            not psutil.pid_exists(provider)
            or psutil.Process(provider).status() == psutil.STATUS_ZOMBIE
        )
        with update_state.lock(setup.root):
            pass
    finally:
        if pid_file.exists():
            try:
                psutil.Process(int(pid_file.read_text())).kill()
            except psutil.NoSuchProcess:
                pass


def test_cli_requires_watch_and_does_not_expose_rejected_configuration(setup, capsys):
    with pytest.raises(SystemExit) as error:
        runner.main(["--config", str(setup.path), "--managed-state", str(setup.state)])
    assert error.value.code == 2
    setup.path.write_text('{"service_token":"private-sentinel-never-log"}')
    assert managed.main(setup.state, setup.path) == 2
    assert "private-sentinel-never-log" not in capsys.readouterr().err


def test_scan_report_identifies_actual_running_version():
    report = {"scopes": []}
    runner._stamp(report, "2026-10-12T00:00:00Z", time.monotonic())
    assert report["runner_version"] == __version__


def test_provider_command_interruption_does_not_leave_a_separate_group(monkeypatch):
    from mnemion.connectors import providers

    original = subprocess.Popen
    children = []

    def launch(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        real_wait = child.wait
        interrupted = False

        def wait(*args, **kwargs):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                raise KeyboardInterrupt()
            return real_wait(*args, **kwargs)

        child.wait = wait
        return child

    monkeypatch.setattr(providers.subprocess, "Popen", launch)
    try:
        with pytest.raises(KeyboardInterrupt):
            providers.command([sys.executable, "-c", "import time; time.sleep(60)"], timeout=10)
        assert len(children) == 1 and children[0].poll() is not None
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


def test_waiting_updater_pauses_new_scans_and_stale_intent_expires(setup, monkeypatch):
    elapsed = [10.0]
    monkeypatch.setattr(update_state, "time", SimpleNamespace(monotonic=lambda: elapsed[0]))
    update_state.pause_new_connector_scans(setup.root)
    assert update_state.connector_update_waiting(setup.root)
    with update_state.lock(setup.entry) as singleton:
        observation = managed.Observation(setup.entry, setup.identifier)
        assert (
            managed._scan(
                setup.state,
                setup.root,
                managed._configuration(setup.path),
                setup.entry,
                singleton,
                observation,
                managed.Control(),
            )
            is None
        )
        assert observation.value["state"] == "waiting_for_update"
    elapsed[0] += 301
    assert not update_state.connector_update_waiting(setup.root)
    update_state.pause_new_connector_scans(setup.root)
    value = update_state.read(setup.root / "connector-update-pending.json")
    value["process_identity"]["pid"] = 2**31 - 1
    update_state.write(setup.root / "connector-update-pending.json", value)
    assert not update_state.connector_update_waiting(setup.root)
    update_state.clear_connector_pause(setup.root)
    assert not (setup.root / "connector-update-pending.json").exists()


def test_supported_verified_runtime_requests_launcher_handoff(setup, tmp_path, monkeypatch):
    runtime = {
        "version": "4.1.3",
        "connector_protocol": 1,
        "isolated": True,
        "package": str(tmp_path / "installed/mnemion"),
    }
    monkeypatch.setattr(service_updates, "resolved_runtime", lambda _: runtime)
    with update_state.lock(setup.entry) as singleton, pytest.raises(managed.Handoff) as result:
        managed._scan(
            setup.state,
            setup.root,
            managed._configuration(setup.path),
            setup.entry,
            singleton,
            managed.Observation(setup.entry, setup.identifier),
            managed.Control(),
            handoff=True,
            trigger="requested",
        )
    assert result.value.runtime is runtime
    assert result.value.trigger == "requested"
    with update_state.lock(setup.root):
        pass


def test_handoff_preserves_original_paths_and_only_connector_environment(
    setup, tmp_path, monkeypatch
):
    runtime = {
        "python": str(tmp_path / "verified/bin/python"),
        "directory": str(tmp_path / "verified"),
    }
    runtime_dir = tmp_path / "verified"
    runtime_dir.mkdir()
    captured = {}

    def handoff(*args):
        raise managed.Handoff(runtime, "requested")

    class Executed(BaseException):
        pass

    def execute(program, arguments, environment):
        captured.update(program=program, arguments=arguments, environment=environment)
        raise Executed()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MNEMION_ADMIN_DATABASE_URL", "must-not-follow-handoff")
    monkeypatch.setattr(managed, "run", handoff)
    monkeypatch.setattr(managed.os, "execve", execute)
    with pytest.raises(Executed):
        managed.main(setup.state.relative_to(tmp_path), setup.path.relative_to(tmp_path))
    assert captured["arguments"] == [
        runtime["python"],
        "-I",
        "-m",
        "mnemion.connectors.runner",
        "--config",
        str(setup.path),
        "--watch",
        "--managed-state",
        str(setup.state),
    ]
    assert "MNEMION_ADMIN_DATABASE_URL" not in captured["environment"]
    assert captured["environment"][runner.SCAN_TRIGGER_ENV] == "requested"
