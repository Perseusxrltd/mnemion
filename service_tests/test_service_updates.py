"""Managed updates preserve runtime identity and never roll back accepted data."""

import copy
import os
import subprocess
import sys
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from deploy.service_update_manifest import payload
from mnemion.service import service_updates as updates
from mnemion.service import update_state as state_io
from mnemion.service.update_manifest import ManifestError, sign_manifest, validate_payload
from service_tests.update_fixture import package_inputs

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Managed Supervisor updates run on Unix")


@pytest.fixture
def managed(tmp_path, monkeypatch):
    state = state_io.directory(tmp_path / "managed")
    root = state_io.directory(state / "updates")
    for name in ("logs", "releases", "backups", "cache"):
        state_io.directory(root / name)
    inputs = tmp_path / "publisher"
    artifacts = package_inputs(inputs)
    value = payload(inputs, artifacts, "a" * 40)
    key = Ed25519PrivateKey.generate()
    envelope = sign_manifest(value, key.private_bytes_raw())
    monkeypatch.setattr(updates, "SERVICE_UPDATE_PUBLIC_KEY", key.public_key().public_bytes_raw())
    monkeypatch.setattr(updates, "fetch_manifest", lambda: envelope)
    settings = {"environment": {}}
    monkeypatch.setattr(updates, "_root", lambda _: (state, root, settings))
    old = {
        "version": "4.0.7",
        "python": sys.executable,
        "directory": str(tmp_path),
        "isolated": False,
        "migrations": value["migrations"],
        "generations": ["fixture-generation"],
        "slot": None,
    }
    state_io.write(root / "active.json", old)
    state_io.write(
        root / "config.json",
        {
            "format": 1,
            "enabled": True,
            "interval_seconds": 21600,
            "uv": "fixture-uv",
            "baseline": old,
        },
    )
    return SimpleNamespace(
        state=state,
        root=root,
        old=old,
        settings=settings,
        value=value,
        key=key,
        envelope=envelope,
        artifacts=artifacts,
    )


def test_authenticated_checks_preserve_replay_protection_and_private_state(managed, monkeypatch):
    result = updates.check(managed.state)
    assert result == {
        "status": "available",
        "current_version": "4.0.7",
        "available_version": "4.0.8",
        "schema_compatible": True,
        "version_compatible": True,
    }
    candidate = managed.root / "candidate.json"
    assert candidate.stat().st_mode & 0o077 == 0
    assert updates._release(managed.root).version == "4.0.8"
    assert updates.preferences(managed.state, False) == {"enabled": False}
    assert state_io.read(managed.root / "config.json")["enabled"] is False
    state_io.write(managed.root / "seen.json", {"version": "4.0.9"})
    with pytest.raises(ManifestError, match="replay"):
        updates.check(managed.state)
    assert updates._release(managed.root).version == "4.0.8"


def test_wrong_publisher_does_not_change_candidate_or_high_water(managed, monkeypatch):
    updates.check(managed.state)
    before = (managed.root / "candidate.json").read_bytes()
    key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(
        updates, "fetch_manifest", lambda: sign_manifest(managed.value, key.private_bytes_raw())
    )
    with pytest.raises(ManifestError, match="signature"):
        updates.check(managed.state)
    assert (managed.root / "candidate.json").read_bytes() == before
    assert state_io.read(managed.root / "seen.json")["version"] == "4.0.8"


def test_same_signed_version_cannot_change_its_immutable_manifest(managed, monkeypatch):
    updates.check(managed.state)
    value = {**managed.value, "commit": "b" * 40}
    monkeypatch.setattr(
        updates, "fetch_manifest", lambda: sign_manifest(value, managed.key.private_bytes_raw())
    )
    with pytest.raises(ManifestError, match="immutable"):
        updates.check(managed.state)
    assert updates._release(managed.root).commit == "a" * 40


@pytest.mark.parametrize("enabled", [True, False])
def test_watcher_checks_and_applies_by_default_but_pausing_prevents_network(
    managed, monkeypatch, enabled
):
    updates.preferences(managed.state, enabled)
    elapsed = [0]
    calls = []

    def sleep(seconds):
        elapsed[0] += seconds
        if elapsed[0] > 120:
            raise updates.UpdateInterrupted()

    monkeypatch.setattr(updates, "time", SimpleNamespace(monotonic=lambda: elapsed[0], sleep=sleep))
    monkeypatch.setattr(updates.random, "uniform", lambda low, high: low)
    real_check = updates._check

    def check(root):
        calls.append(("check", elapsed[0]))
        return real_check(root)

    monkeypatch.setattr(updates, "_check", check)
    monkeypatch.setattr(
        updates,
        "_stage",
        lambda *args: calls.append(("stage", elapsed[0])) or {"automatic_compatible": True},
    )
    monkeypatch.setattr(
        updates,
        "_apply",
        lambda *args: calls.append(("apply", elapsed[0])) or {"status": "updated"},
    )
    assert updates.watch(managed.state) == 0
    assert calls == ([("check", 60), ("stage", 60), ("apply", 60)] if enabled else [])


def test_watcher_retries_after_a_managed_scan_instead_of_waiting_six_hours(managed, monkeypatch):
    elapsed = [0]
    calls = []
    lease = state_io.lock(managed.root, shared=True)
    lease.__enter__()
    released = False

    def sleep(seconds):
        nonlocal released
        elapsed[0] += seconds
        if elapsed[0] >= 70 and not released:
            lease.__exit__(None, None, None)
            released = True
        if elapsed[0] > 180:
            raise updates.UpdateInterrupted()

    monkeypatch.setattr(updates, "time", SimpleNamespace(monotonic=lambda: elapsed[0], sleep=sleep))
    monkeypatch.setattr(updates.random, "uniform", lambda low, high: low)
    monkeypatch.setattr(
        updates,
        "_check",
        lambda _: (
            calls.append(elapsed[0])
            or {
                "status": "available",
                "schema_compatible": True,
                "version_compatible": True,
            }
        ),
    )
    monkeypatch.setattr(updates, "_stage", lambda *args: {"automatic_compatible": True})
    monkeypatch.setattr(updates, "_apply", lambda *args: {"status": "updated"})
    try:
        assert updates.watch(managed.state) == 0
        assert len(calls) == 1 and 90 <= calls[0] <= 100
    finally:
        if not released:
            lease.__exit__(None, None, None)


def test_changed_schema_is_reported_before_any_process_transition(managed, monkeypatch):
    value = copy.deepcopy(managed.value)
    value["migrations"]["002_new.sql"] = "f" * 64
    monkeypatch.setattr(
        updates, "fetch_manifest", lambda: sign_manifest(value, managed.key.private_bytes_raw())
    )
    assert updates.check(managed.state)["schema_compatible"] is False
    assert state_io.read(managed.root / "active.json") == managed.old


def staged(managed, monkeypatch):
    updates.check(managed.state)
    release = validate_payload(managed.value)
    slot = state_io.directory(updates._slot(managed.root, release))
    runtime = {**managed.old, "version": release.version, "slot": slot.name}
    state_io.write(slot / "ready.json", {"runtime": runtime, "automatic_compatible": True})
    monkeypatch.setattr(
        updates,
        "resolved_runtime",
        lambda state, runtime=None: runtime or state_io.read(managed.root / "active.json"),
    )
    monkeypatch.setattr(updates.supervision, "status", lambda _: {"running": True, "ready": True})
    monkeypatch.setattr(updates, "_models", lambda *args: ["fixture-generation"])
    return runtime


def test_successful_cutover_takes_backup_before_stopping_and_preserves_previous(
    managed, monkeypatch
):
    candidate = staged(managed, monkeypatch)
    events = []
    monkeypatch.setattr(updates, "_backup", lambda *args: events.append("backup") or "verified.zip")

    def process(state, *, start, updater_only=False):
        events.append(("updater-" if updater_only else "") + ("start" if start else "stop"))
        expected = candidate if start or updater_only else managed.old
        assert state_io.read(managed.root / "active.json") == expected

    monkeypatch.setattr(updates, "_processes", process)
    result = updates.apply(managed.state)
    assert events == ["backup", "stop", "start", "updater-stop", "updater-start"]
    assert result["status"] == "updated" and result["database_restored"] is False
    assert state_io.read(managed.root / "previous.json") == managed.old
    assert not (managed.root / "journal.json").exists()


def test_failed_new_start_restores_runtime_without_reverting_accepted_data(managed, monkeypatch):
    candidate = staged(managed, monkeypatch)
    accepted = ["before-update"]
    monkeypatch.setattr(updates, "_backup", lambda *args: "verified.zip")

    def process(state, *, start):
        if start and state_io.read(managed.root / "active.json") == candidate:
            accepted.append("accepted-before-health-failure")
            raise ManifestError("Fixture readiness failure")

    monkeypatch.setattr(updates, "_processes", process)
    with pytest.raises(ManifestError, match="previous service runtime was restored"):
        updates.apply(managed.state)
    assert accepted == ["before-update", "accepted-before-health-failure"]
    assert state_io.read(managed.root / "active.json") == managed.old
    assert not (managed.root / "journal.json").exists()
    assert updates.apply(managed.state)["status"] == "held_after_failure"


def test_interrupted_cutover_leaves_journal_and_recovers_before_retry(managed, monkeypatch):
    candidate = staged(managed, monkeypatch)
    monkeypatch.setattr(updates, "_backup", lambda *args: "verified.zip")

    def interrupted(state, *, start):
        if start:
            raise updates.UpdateInterrupted()

    monkeypatch.setattr(updates, "_processes", interrupted)
    with pytest.raises(updates.UpdateInterrupted):
        updates.apply(managed.state)
    assert state_io.read(managed.root / "active.json") == candidate
    assert state_io.read(managed.root / "journal.json")["phase"] == "starting"
    monkeypatch.setattr(updates, "_processes", lambda *args, **kwargs: None)
    assert updates.apply(managed.state)["status"] == "held_after_failure"
    assert state_io.read(managed.root / "active.json") == managed.old
    assert not (managed.root / "journal.json").exists()


def test_failed_backup_cannot_stop_or_replace_the_running_service(managed, monkeypatch):
    staged(managed, monkeypatch)
    monkeypatch.setattr(
        updates, "_backup", lambda *args: (_ for _ in ()).throw(ManifestError("Backup failed"))
    )
    monkeypatch.setattr(
        updates,
        "_processes",
        lambda *args, **kwargs: pytest.fail("A process was stopped before backup success"),
    )
    with pytest.raises(ManifestError, match="Backup failed"):
        updates.apply(managed.state)
    assert state_io.read(managed.root / "active.json") == managed.old
    assert not (managed.root / "journal.json").exists()


def test_baseline_executable_cannot_be_changed_by_editing_active_pointer(managed):
    assert updates.resolved_runtime(managed.state) == managed.old
    state_io.write(managed.root / "active.json", {**managed.old, "python": "/unrelated/python"})
    with pytest.raises(ManifestError, match="configuration was modified"):
        updates.resolved_runtime(managed.state)


def test_subprocess_output_is_bounded_private_and_has_no_inherited_credentials(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MNEMION_ADMIN_DATABASE_URL", "sentinel-private-admin")
    monkeypatch.setenv("MNEMION_SERVICE_UPDATE_PRIVATE_KEY", "sentinel-private-publisher")
    code = "import os; assert 'MNEMION_ADMIN_DATABASE_URL' not in os.environ; assert 'MNEMION_SERVICE_UPDATE_PRIVATE_KEY' not in os.environ; print('x'*1000000)"
    log = tmp_path / "command.log"
    output = updates._command(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        environment=updates._environment(),
        log=log,
        timeout=10,
    )
    assert len(output) == updates.MAX_COMMAND_LOG_BYTES
    assert log.stat().st_size == updates.MAX_COMMAND_LOG_BYTES
    assert log.stat().st_mode & 0o077 == 0


def test_subprocess_timeout_terminates_work_and_retains_a_bounded_log(tmp_path):
    with pytest.raises(subprocess.TimeoutExpired):
        updates._command(
            [sys.executable, "-c", "import time; print('started',flush=True); time.sleep(60)"],
            cwd=tmp_path,
            environment=updates._environment(),
            log=tmp_path / "timeout.log",
            timeout=0.2,
        )
    assert (tmp_path / "timeout.log").read_bytes() == b"started\n"


def test_private_state_lock_and_event_history_are_bounded(tmp_path):
    root = state_io.directory(tmp_path / "state")
    with state_io.lock(root):
        with pytest.raises(ManifestError, match="already running"):
            with state_io.lock(root):
                pytest.fail("Two installers acquired the same state")
    for number in range(30):
        state_io.record(root, "fixture", number=number)
    history = state_io.read(root / "history.json")["events"]
    assert len(history) == 20 and history[0]["number"] == 10
    (root / "history.json").chmod(0o644)
    with pytest.raises(ManifestError, match="private"):
        state_io.read(root / "history.json")
