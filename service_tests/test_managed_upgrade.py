"""Operator migrations retain signed boundaries, failure recovery and accepted data."""

import copy
import json
import os
from types import SimpleNamespace

import pytest

from mnemion.archives import write_archive
from mnemion.service import managed_upgrade as subject
from mnemion.service import service_updates as updates
from mnemion.service import update_state as state_io
from mnemion.service.recovery import BACKUP_FORMAT
from mnemion.service.update_manifest import ManifestError, sign_manifest
from service_tests.test_service_updates import managed as managed, staged

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Managed Supervisor upgrades run on Unix"
)


@pytest.fixture
def upgrade_host(managed, monkeypatch, tmp_path):
    value = copy.deepcopy(managed.value)
    value["migrations"]["002_added.sql"] = "b" * 64
    managed.value = value
    monkeypatch.setattr(
        updates, "fetch_manifest", lambda: sign_manifest(value, managed.key.private_bytes_raw())
    )
    candidate = staged(managed, monkeypatch)
    candidate["migrations"] = value["migrations"]
    state_io.write(
        managed.root / "releases" / candidate["slot"] / "ready.json",
        {"runtime": candidate, "automatic_compatible": False},
    )
    events = []
    runtime = SimpleNamespace(
        schema=managed.old["migrations"], accepted=["existing-memory"], fail=None
    )
    monkeypatch.setattr(updates, "_stage", lambda *args: None)
    monkeypatch.setattr(subject, "_schema", lambda *args: runtime.schema)

    def migrate(*args):
        events.append("migrate")
        if runtime.fail == "migration":
            raise ManifestError("Transaction failed")
        runtime.schema = candidate["migrations"]

    def backup(*args, **kwargs):
        assert kwargs == {"allow_migration": True}
        events.append("backup")
        if runtime.fail == "backup":
            raise ManifestError("Backup failed")
        source = tmp_path / "snapshot.txt"
        source.write_text(
            "A protocol fixture; the real backup path has separate PostgreSQL coverage."
        )
        output = managed.root / "backups/verified.zip"
        write_archive(output, {"snapshot.txt": source}, {"format": BACKUP_FORMAT, "version": 1})
        return output.name

    def processes(state, *, start, updater_only=False, service_only=False):
        events.append(("updater-" if updater_only else "") + ("start" if start else "stop"))
        if start and not updater_only:
            assert service_only, "API and worker readiness must work while the updater is stopped"
            if (
                runtime.fail == "readiness"
                and state_io.read(managed.root / "active.json") == candidate
            ):
                runtime.accepted.append("accepted-before-readiness-failure")
                raise ManifestError("Worker not ready")

    monkeypatch.setattr(subject, "_migrate", migrate)
    monkeypatch.setattr(updates, "_backup", backup)
    monkeypatch.setattr(updates, "_processes", processes)
    return SimpleNamespace(managed=managed, candidate=candidate, runtime=runtime, events=events)


def run(host, **kwargs):
    return subject.upgrade(
        host.managed.state, version=host.candidate["version"], allow_migration=True, **kwargs
    )


def test_operator_plan_and_upgrade_preserve_identity_and_enable_future_patches(upgrade_host):
    host = upgrade_host
    plan = subject.plan(host.managed.state)
    assert plan["migrations"] == ["002_added.sql"] and plan["operator_required"]
    assert host.events == []
    result = run(host)
    assert result["status"] == "upgraded" and not result["database_restored"]
    assert host.events == ["backup", "updater-stop", "stop", "migrate", "start", "updater-start"]
    assert state_io.read(host.managed.root / "previous.json") == host.managed.old
    assert host.runtime.accepted == ["existing-memory"]
    assert updates.check(host.managed.state)["status"] == "current"
    assert not (host.managed.root / subject.JOURNAL).exists()


@pytest.mark.parametrize("failure", ["backup", "migration"])
def test_failure_before_migration_commit_preserves_old_runtime(upgrade_host, failure):
    host = upgrade_host
    host.runtime.fail = failure
    with pytest.raises(ManifestError):
        run(host)
    assert host.runtime.schema == host.managed.old["migrations"]
    assert state_io.read(host.managed.root / "active.json") == host.managed.old
    assert not (host.managed.root / subject.JOURNAL).exists()
    if failure == "backup":
        assert host.events == ["backup"]
    else:
        assert host.events[-2:] == ["start", "updater-start"]


def test_failure_after_commit_resumes_forward_without_reapplying_or_losing_accepted_writes(
    upgrade_host,
):
    host = upgrade_host
    host.runtime.fail = "readiness"
    with pytest.raises(ManifestError, match="No database backup was restored"):
        run(host)
    assert subject.upgrade_status(host.managed.root)["phase"] == "recovery_required"
    assert host.runtime.schema == host.candidate["migrations"]
    assert state_io.read(host.managed.root / "active.json") == host.candidate
    with pytest.raises(ManifestError, match="pending managed schema upgrade"):
        updates.apply(host.managed.state)
    host.runtime.fail = None
    assert run(host, resume=True)["status"] == "upgraded"
    assert host.events.count("backup") == host.events.count("migrate") == 1
    assert host.runtime.accepted == ["existing-memory", "accepted-before-readiness-failure"]
    assert not (host.managed.root / subject.JOURNAL).exists()


def test_exact_version_and_explicit_authorization_are_required_before_changes(upgrade_host):
    host = upgrade_host
    with pytest.raises(ManifestError, match="--allow-migration"):
        subject.upgrade(host.managed.state, version=host.candidate["version"])
    with pytest.raises(ManifestError, match="version changed"):
        subject.upgrade(host.managed.state, version="4.0.9", allow_migration=True)
    assert host.events == []


@pytest.mark.parametrize("change", ["edited", "removed", "inserted"])
def test_migration_history_cannot_be_edited_removed_or_reordered(change):
    old = {"001_first.sql": "a", "003_third.sql": "b"}
    new = {**old, "004_fourth.sql": "c"}
    if change == "edited":
        new["001_first.sql"] = "changed"
    elif change == "removed":
        del new["003_third.sql"]
    else:
        new["002_inserted.sql"] = "inserted"
    with pytest.raises(ManifestError, match="preserve every applied migration"):
        subject.extension(old, new)


def test_status_retains_signed_blocked_release_when_last_check_is_stale(upgrade_host):
    host = upgrade_host
    state_io.write(host.managed.root / "history.json", {"events": []})
    state_io.write(
        host.managed.root / "last-check.json",
        {
            "status": "current",
            "current_version": host.managed.old["version"],
            "checked_at": "2026-10-13T11:00:00Z",
        },
    )
    result = updates.status(host.managed.state)
    assert result["last_check"]["status"] == "current"
    assert result["pending_update"]["operator_required"]
    assert result["pending_update"]["available_version"] == host.candidate["version"]
    assert result["pending_update"]["upgrade_reasons"] == ["schema_changed"]


def test_busy_command_reports_a_machine_readable_defer_without_fetching(
    managed, monkeypatch, capsys
):
    monkeypatch.setattr(updates, "fetch_manifest", lambda: pytest.fail("Busy check must not fetch"))
    with state_io.lock(managed.root):
        assert updates.main(["check", "--state-dir", str(managed.state)]) == 75
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "deferred" and result["retry_after_seconds"] == 30
