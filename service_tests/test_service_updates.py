"""Managed updates preserve runtime identity and never roll back accepted data."""

import copy
from contextlib import nullcontext
import json
import os
import subprocess
import sys
from types import SimpleNamespace
import xmlrpc.client

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from deploy.service_update_manifest import payload
from mnemion.service import service_updates as updates
from mnemion.service import update_state as state_io
from mnemion.service.update_manifest import ManifestError, sign_manifest, validate_payload
from service_tests.update_fixture import package_inputs

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Managed Supervisor updates run on Unix")


@pytest.fixture
def managed(tmp_path, monkeypatch, request):
    state = state_io.directory(tmp_path / "managed")
    root = state_io.directory(state / "updates")
    for name in ("logs", "releases", "backups", "cache"):
        state_io.directory(root / name)
    inputs = tmp_path / "publisher"
    artifacts = package_inputs(inputs, version=getattr(request, "param", "4.0.8"))
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
@pytest.mark.parametrize("managed", ["4.1.0"], indirect=True)
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

    monkeypatch.setattr(
        updates,
        "time",
        SimpleNamespace(
            monotonic=lambda: elapsed[0], time=lambda: 1_791_872_000 + elapsed[0], sleep=sleep
        ),
    )
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

    monkeypatch.setattr(
        updates,
        "time",
        SimpleNamespace(
            monotonic=lambda: elapsed[0], time=lambda: 1_791_872_000 + elapsed[0], sleep=sleep
        ),
    )
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


@pytest.mark.parametrize("correction", ["suspended", "backwards"])
def test_running_watcher_checks_after_clock_correction_without_waiting_another_interval(
    managed, monkeypatch, correction
):
    clock = {"monotonic": 0, "wall": 1_791_872_000}
    calls = []
    corrected = False

    def sleep(seconds):
        nonlocal corrected
        if len(calls) == 2:
            raise updates.UpdateInterrupted()
        clock["monotonic"] += seconds
        clock["wall"] += seconds
        if calls and not corrected:
            corrected = True
            if correction == "suspended":
                clock["monotonic"] += 5 * 3600
                clock["wall"] += 16 * 3600
            else:
                clock["monotonic"] += 6 * 3600
                clock["wall"] -= 86400
        if clock["monotonic"] > 30000:
            raise AssertionError("The running watcher did not check promptly after resume")

    def check(_):
        calls.append(dict(clock))
        return {"status": "current"}

    monkeypatch.setattr(
        updates,
        "time",
        SimpleNamespace(
            monotonic=lambda: clock["monotonic"], time=lambda: clock["wall"], sleep=sleep
        ),
    )
    monkeypatch.setattr(updates.random, "uniform", lambda low, high: low)
    monkeypatch.setattr(updates, "_check", check)
    assert updates.watch(managed.state) == 0
    assert len(calls) == 2 and calls[0]["monotonic"] == 60
    # The second check is the first normal loop after resume/correction.
    assert calls[1]["monotonic"] == (18070 if correction == "suspended" else 21670)
    schedule = state_io.read(managed.root / "schedule.json")
    assert schedule["reason"] == "periodic" and schedule["last_attempt_at"]


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


@pytest.fixture
def host_telemetry(tmp_path, monkeypatch):
    from mnemion.product_telemetry import policy

    root = tmp_path / "product-telemetry"
    monkeypatch.setattr(policy, "default_directory", lambda: root)
    monkeypatch.setattr(policy, "company_policy_file", lambda: tmp_path / "company.json")
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/v1/report")
    policy.configure(root, {"enabled": True, "expected_revision": 0, "disclosure_version": 1})
    return root


@pytest.mark.parametrize("owned", [True, False])
def test_automatic_cutover_has_one_owner_and_manual_apply_has_none(
    managed, monkeypatch, host_telemetry, owned
):
    from mnemion.product_telemetry import aggregate

    staged(managed, monkeypatch)
    events = []
    monkeypatch.setattr(updates, "_backup", lambda *args: events.append("backup") or "PRIVATE.zip")
    monkeypatch.setattr(
        updates,
        "_processes",
        lambda *args, start, **kwargs: events.append("start" if start else "stop"),
    )
    with updates.update_measurement.automatic_watcher() if owned else nullcontext():
        # A ready cached stage must not become another download observation.
        assert updates._stage(managed.root, managed.settings)["status"] == "staged"
        result = updates._apply(managed.state, managed.root, managed.settings)
    assert result["status"] == "updated"
    assert events == ["backup", "stop", "start"]
    rows = aggregate.preview(host_telemetry)
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == int(owned)
    assert all(row["workflow"] == "update.apply" for row in rows)
    assert [row["bucket"] for row in rows if row["metric"] == "outcomes"] == (
        ["success"] if owned else []
    )
    assert "PRIVATE" not in json.dumps(rows)


def test_fresh_stage_records_once_but_current_and_cached_versions_do_not(
    managed, monkeypatch, host_telemetry
):
    from mnemion.product_telemetry import aggregate

    runtime = staged(managed, monkeypatch)
    receipt = managed.root / "releases" / runtime["slot"] / "ready.json"
    saved = state_io.read(receipt)
    receipt.unlink()
    calls = []

    def stage(*args):
        calls.append(True)
        state_io.write(receipt, saved)
        return {"status": "staged", "automatic_compatible": True}

    monkeypatch.setattr(updates, "_stage_fresh", stage)
    with updates.update_measurement.automatic_watcher():
        assert updates._stage(managed.root, managed.settings)["status"] == "staged"
        assert updates._stage(managed.root, managed.settings)["status"] == "staged"
        state_io.write(managed.root / "active.json", runtime)
        with pytest.raises(ManifestError, match="newer"):
            updates._stage(managed.root, managed.settings)
    assert calls == [True]
    rows = aggregate.preview(host_telemetry)
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == 1
    assert all(row["workflow"] == "update.download" for row in rows)


@pytest.mark.parametrize("ending", ["restored", "rollback_unconfirmed", "interrupted"])
def test_real_recovery_observes_fresh_work_without_replaying_interrupted_apply(
    managed, monkeypatch, host_telemetry, ending
):
    from mnemion.product_telemetry import aggregate, policy

    candidate = staged(managed, monkeypatch)
    monkeypatch.setattr(updates, "_backup", lambda *args: "PRIVATE_BACKUP.zip")

    def process(state, *, start):
        if start:
            if ending == "interrupted":
                raise updates.UpdateInterrupted()
            if state_io.read(managed.root / "active.json") == candidate:
                raise ManifestError("PRIVATE_CANDIDATE_FAILURE")
            if ending == "rollback_unconfirmed":
                raise OSError("PRIVATE_ROLLBACK_FAILURE")

    monkeypatch.setattr(updates, "_processes", process)
    with updates.update_measurement.automatic_watcher():
        expected = (
            updates.UpdateInterrupted
            if ending == "interrupted"
            else OSError
            if ending == "rollback_unconfirmed"
            else ManifestError
        )
        with pytest.raises(expected):
            updates._apply(managed.state, managed.root, managed.settings)
    if ending == "interrupted":
        assert aggregate.preview(host_telemetry) == []
        assert state_io.read(managed.root / "journal.json")["phase"] == "starting"
        monkeypatch.setattr(updates, "_processes", lambda *args, **kwargs: None)
        # A new process/lifetime observes only the rollback it actually runs.
        with updates.update_measurement.automatic_watcher():
            updates._recover(managed.state, managed.root)
        expected_outcomes = {"update.rollback": "success"}
    elif ending == "restored":
        expected_outcomes = {"update.apply": "failed", "update.rollback": "success"}
        with updates.update_measurement.automatic_watcher():
            assert updates._apply(managed.state, managed.root, managed.settings)["status"] == (
                "held_after_failure"
            )
    else:
        expected_outcomes = {"update.apply": "unconfirmed", "update.rollback": "unconfirmed"}
        assert (managed.root / "journal.json").exists()
    rows = aggregate.preview(host_telemetry)
    assert {
        row["workflow"]: row["bucket"] for row in rows if row["metric"] == "outcomes"
    } == expected_outcomes
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == len(
        expected_outcomes
    )
    assert b"PRIVATE" not in (host_telemetry / policy.DATABASE_NAME).read_bytes()


def test_mid_cutover_opt_out_keeps_the_update_and_suppresses_telemetry(
    managed, monkeypatch, host_telemetry
):
    from mnemion.product_telemetry import aggregate, policy

    staged(managed, monkeypatch)
    monkeypatch.setattr(updates, "_backup", lambda *args: "PRIVATE.zip")

    def process(state, *, start):
        if start:
            policy.configure(host_telemetry, {"enabled": False, "expected_revision": 0})

    monkeypatch.setattr(updates, "_processes", process)
    with updates.update_measurement.automatic_watcher():
        assert updates._apply(managed.state, managed.root, managed.settings)["status"] == "updated"
    assert aggregate.preview(host_telemetry) == []
    assert not (managed.root / "journal.json").exists()


@pytest.mark.parametrize("managed", ["4.0.8", "4.1.0"], indirect=True)
def test_successful_cutover_takes_backup_before_stopping_and_preserves_previous(
    managed, monkeypatch
):
    candidate = staged(managed, monkeypatch)
    assert updates.check(managed.state)["version_compatible"]
    if candidate["version"] == "4.1.0":
        # A slot staged by the old patch-only policy remains usable after the
        # policy update. Its saved classification is not a permanent blocker.
        state_io.write(
            managed.root / "releases" / candidate["slot"] / "ready.json",
            {"runtime": candidate, "automatic_compatible": False},
        )
    assert updates.stage(managed.state)["automatic_compatible"]
    state_io.write(managed.root / "history.json", {"events": []})
    status = updates.status(managed.state)
    assert status["version_policy"] == "same_major"
    assert status["pending_update"]["operator_required"] is False
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


@pytest.mark.parametrize("managed", ["4.1.0"], indirect=True)
@pytest.mark.parametrize("changed", ["major", "schema", "models"])
def test_cached_minor_release_cannot_bypass_current_compatibility_guards(
    managed, monkeypatch, changed
):
    staged(managed, monkeypatch)
    current = copy.deepcopy(managed.old)
    if changed == "major":
        current["version"] = "3.9.9"
    elif changed == "schema":
        current["migrations"]["002_operator_change.sql"] = "f" * 64
    else:
        current["generations"] = ["different-generation"]
    state_io.write(managed.root / "active.json", current)
    monkeypatch.setattr(updates, "_backup", lambda *args: pytest.fail("Must refuse before backup"))
    monkeypatch.setattr(
        updates, "_processes", lambda *args, **kwargs: pytest.fail("Must not stop any process")
    )
    assert updates.stage(managed.state)["automatic_compatible"] is False
    assert updates.apply(managed.state)["status"] == "operator_required"
    assert state_io.read(managed.root / "active.json") == current
    assert not (managed.root / "journal.json").exists()


@pytest.mark.parametrize("with_diagnostics", [False, True])
def test_failed_new_start_restores_runtime_without_reverting_accepted_data(
    managed, monkeypatch, with_diagnostics
):
    candidate = staged(managed, monkeypatch)
    accepted = ["before-update"]
    monkeypatch.setattr(updates, "_backup", lambda *args: "verified.zip")

    def process(state, *, start):
        if start and state_io.read(managed.root / "active.json") == candidate:
            accepted.append("accepted-before-health-failure")
            if with_diagnostics:
                raise updates.ProcessTransitionError(
                    "Fixture readiness failure: private-sentinel",
                    reason="readiness_timeout",
                    start=True,
                    observation={
                        "ready": False,
                        "http_ready": True,
                        "children_initialized": False,
                        "private_setting": "private-sentinel",
                        "processes": [
                            {"name": "mnemion-api", "statename": "RUNNING"},
                            {"name": "mnemion-worker", "statename": "RUNNING"},
                        ],
                    },
                )
            raise ManifestError("Fixture readiness failure")

    monkeypatch.setattr(updates, "_processes", process)
    with pytest.raises(ManifestError, match="previous service runtime was restored"):
        updates.apply(managed.state)
    assert accepted == ["before-update", "accepted-before-health-failure"]
    assert state_io.read(managed.root / "active.json") == managed.old
    assert not (managed.root / "journal.json").exists()
    assert updates.apply(managed.state)["status"] == "held_after_failure"
    failed = updates.status(managed.state)["last_failure"]
    assert failed["version"] == candidate["version"]
    if with_diagnostics:
        assert failed["transition"]["reason"] == "readiness_timeout"
        assert failed["transition"]["checks"]["children_initialized"] is False
        assert failed["transition"]["process_states"]["mnemion-worker"] == "RUNNING"
    else:
        assert failed["transition"] is None
    assert "private-sentinel" not in (managed.root / "failed.json").read_text()


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


def test_failed_diagnostics_write_still_attempts_original_runtime_recovery(managed, monkeypatch):
    candidate = staged(managed, monkeypatch)
    monkeypatch.setattr(updates, "_backup", lambda *args: "verified.zip")
    recovered = []

    def process(state, *, start):
        if start and state_io.read(managed.root / "active.json") == candidate:
            raise updates.ProcessTransitionError(
                "Fixture readiness timeout", reason="readiness_timeout", start=True
            )
        if start:
            recovered.append(True)

    write = state_io.write

    def write_without_diagnostics(path, value, **kwargs):
        if path == managed.root / "journal.json" and "transition" in value:
            raise OSError("Fixture diagnostics write unavailable")
        return write(path, value, **kwargs)

    monkeypatch.setattr(updates, "_processes", process)
    monkeypatch.setattr(state_io, "write", write_without_diagnostics)
    with pytest.raises(OSError, match="diagnostics write"):
        updates.apply(managed.state)
    assert recovered == [True]
    assert state_io.read(managed.root / "active.json") == managed.old
    assert not (managed.root / "journal.json").exists()
    assert (
        state_io.read(managed.root / "failed.json")["transition"]["reason"] == "readiness_timeout"
    )


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


@pytest.mark.parametrize(
    ("start", "where"),
    [(start, where) for start in (True, False) for where in ("connect", "command", "observe")]
    + [(True, "readiness")],
)
def test_process_transition_recovers_from_busy_supervisor_and_lost_replies(
    tmp_path, monkeypatch, start, where
):
    states = dict.fromkeys(("mnemion-api", "mnemion-worker"), "STOPPED" if start else "RUNNING")
    target = "RUNNING" if start else "STOPPED"
    changed = dict.fromkeys(states, 0)
    failed = False

    def busy(point):
        nonlocal failed
        if point == where and not failed:
            failed = True
            raise TimeoutError("Fixture supervisor busy")

    def command(name, wait):
        assert wait is False
        if states[name] == target:
            raise xmlrpc.client.Fault(60 if start else 70, "Already in the requested state")
        states[name] = target
        changed[name] += 1
        busy("command")  # The action happened but its acknowledgement was lost.

    def observe():
        busy("observe")
        return [{"name": name, "statename": state} for name, state in states.items()]

    def rpc(settings):
        busy("connect")
        return nullcontext(
            SimpleNamespace(
                supervisor=SimpleNamespace(
                    startProcess=command, stopProcess=command, getAllProcessInfo=observe
                )
            )
        )

    def readiness(state):
        busy("readiness")
        return {"ready": all(value == target for value in states.values())}

    monkeypatch.setattr(updates.supervision, "settings", lambda state: (state, {}))
    monkeypatch.setattr(updates.supervision, "_rpc", rpc)
    monkeypatch.setattr(updates.supervision, "status", readiness)
    monkeypatch.setattr(updates.time, "sleep", lambda duration: None)
    updates._processes(tmp_path, start=start)
    assert failed
    assert all(value == target for value in states.values())
    assert set(changed.values()) == {1}


@pytest.mark.parametrize("identity_error", [False, True])
def test_process_transition_keeps_its_deadline_and_does_not_retry_identity_failures(
    tmp_path, monkeypatch, identity_error
):
    calls = []
    clock = iter(range(0, 200, 10))

    def rpc(settings):
        calls.append(True)
        if identity_error:
            raise updates.supervision.SupervisionError("Different supervisor instance")
        raise TimeoutError("Fixture remains busy")

    monkeypatch.setattr(updates.supervision, "settings", lambda state: (state, {}))
    monkeypatch.setattr(updates.supervision, "_rpc", rpc)
    monkeypatch.setattr(updates.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(updates.time, "sleep", lambda duration: None)
    error = updates.supervision.SupervisionError if identity_error else ManifestError
    with pytest.raises(error, match="Different supervisor|requested process transition"):
        updates._processes(tmp_path, start=True)
    assert len(calls) == (1 if identity_error else 17)


@pytest.mark.parametrize("missing", ["http_ready", "instance_matches", "children_initialized"])
def test_running_processes_do_not_bypass_readiness_and_timeout_preserves_the_failed_check(
    tmp_path, monkeypatch, missing
):
    clock = [0]
    starts = []
    processes = [
        {"name": "mnemion-api", "statename": "RUNNING"},
        {"name": "mnemion-worker", "statename": "RUNNING"},
    ]
    observed = {
        "ready": False,
        "service_ready": False,
        "http_ready": True,
        "instance_matches": True,
        "children_initialized": True,
        "processes": processes,
        missing: False,
    }
    client = SimpleNamespace(
        supervisor=SimpleNamespace(
            startProcess=lambda name, wait: starts.append(name),
            getAllProcessInfo=lambda: processes,
        )
    )
    monkeypatch.setattr(updates.supervision, "settings", lambda state: (state, {}))
    monkeypatch.setattr(updates.supervision, "_rpc", lambda settings: nullcontext(client))
    monkeypatch.setattr(updates.supervision, "status", lambda state: observed)
    monkeypatch.setattr(updates.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        updates.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    with pytest.raises(updates.ProcessTransitionError) as caught:
        updates._processes(tmp_path, start=True)
    assert starts == ["mnemion-api", "mnemion-worker"]
    assert clock[0] == 180
    evidence = caught.value.diagnostics
    assert evidence["reason"] == "readiness_timeout"
    assert evidence["budget_seconds"] == 180
    assert evidence["checks"][missing] is False
    assert set(evidence["process_states"].values()) == {"RUNNING"}


def test_slow_start_waits_for_real_readiness_without_restarting_running_children(
    tmp_path, monkeypatch
):
    clock, starts = [0], []
    processes = [
        {"name": "mnemion-api", "statename": "RUNNING"},
        {"name": "mnemion-worker", "statename": "RUNNING"},
    ]
    client = SimpleNamespace(
        supervisor=SimpleNamespace(
            startProcess=lambda name, wait: starts.append(name),
            getAllProcessInfo=lambda: processes,
        )
    )
    monkeypatch.setattr(updates.supervision, "settings", lambda state: (state, {}))
    monkeypatch.setattr(updates.supervision, "_rpc", lambda settings: nullcontext(client))
    monkeypatch.setattr(updates.supervision, "status", lambda state: {"ready": clock[0] >= 105})
    monkeypatch.setattr(updates.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        updates.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    updates._processes(tmp_path, start=True)
    assert clock[0] == 105
    assert starts == ["mnemion-api", "mnemion-worker"]


@pytest.mark.parametrize("budget", [60, 90, 180])
def test_saved_transition_diagnostics_preserve_historical_and_current_bounds(budget):
    value = {"reason": "readiness_timeout", "budget_seconds": budget}
    assert updates.transition_diagnostics(value) == value


@pytest.mark.parametrize("invalid", [None, [], {"reason": []}, {"reason": "private-sentinel"}])
def test_unrecognized_saved_transition_diagnostics_are_not_disclosed(invalid):
    assert updates.transition_diagnostics(invalid) is None


def test_saved_transition_diagnostics_discard_unknown_fields_and_values():
    observed = updates.transition_diagnostics(
        {
            "reason": "readiness_timeout",
            "direction": {},
            "budget_seconds": "private-sentinel",
            "checks": {"ready": False, "http_ready": "private-sentinel", "token": "hidden"},
            "process_states": {"mnemion-api": "RUNNING", "private-sentinel": "RUNNING"},
            "private_setting": "private-sentinel",
        }
    )
    assert observed == {
        "reason": "readiness_timeout",
        "checks": {"ready": False},
        "process_states": {"mnemion-api": "RUNNING"},
    }


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
