"""Real free-page reclamation must preserve custody and uncertain delivery."""

from dataclasses import replace
import sqlite3
from types import SimpleNamespace

import pytest

from mnemion.connectors import capture_storage as storage
from mnemion.connectors.conversation_inbox import Limits, open_inbox
from service_tests.test_conversation_inbox import SCOPE, event, receipt
from service_tests.test_conversation_inbox import inbox_settings as inbox_settings


@pytest.fixture(autouse=True)
def small_cleanup_threshold(monkeypatch):
    # Exercise real SQLite transactions with a small disposable corpus.
    monkeypatch.setattr(storage, "MINIMUM_RECLAIM_BYTES", 4096)


def filled(inbox, *, pending=True, legacy=False, count=12):
    if legacy:
        inbox.connection.execute("PRAGMA auto_vacuum=NONE")
        inbox.connection.execute("VACUUM")
    selected = [
        event(inbox.binding, "Retained cleanup fixture é. " * 200, external=str(index))
        for index in range(count)
    ]
    inbox.accept(SCOPE, selected, {"accepted": count}, verify=lambda: True)
    while page := inbox.page():
        inbox.acknowledge(receipt(inbox.binding, page["page"]))
    from mnemion.capture_identity import capture_lineage_id

    inbox.forget(capture_lineage_id(SCOPE, selected[0]["item"]))
    if pending:
        inbox.accept(
            SCOPE,
            [event(inbox.binding, "Uncertain delivery must survive cleanup", external="pending")],
            {"accepted": count + 1},
            verify=lambda: True,
        )
        uncertain = inbox.page()["page"]
    else:
        uncertain = None
    assert inbox.connection.execute("PRAGMA freelist_count").fetchone()[0] > 0
    return selected, uncertain


def logical(inbox):
    return {
        table: sorted(inbox.connection.execute(f"SELECT * FROM {table}").fetchall())
        for table in (
            "metadata",
            "events",
            "checkpoints",
            "pages",
            "page_events",
            "denials",
            "producer_segments",
            "producer_events",
        )
    }


def test_reclamation_keeps_every_record_and_pending_page_after_restart(inbox_settings):
    root, binding, _ = inbox_settings
    with open_inbox(*inbox_settings, create=True) as inbox:
        assert inbox.connection.execute("PRAGMA auto_vacuum").fetchone()[0] == 2
        selected, uncertain = filled(inbox)
        records, before = logical(inbox), inbox.status()["database_bytes"]
        report = storage.reclaim(inbox)
        assert report["state"] == "reclaimed"
        assert 0 < report["reclaimed_bytes"] <= storage.RECLAIM_BYTES
        assert report["database_bytes"] == before - report["reclaimed_bytes"]
        assert report["database_bytes"] == (root / "inbox.sqlite3").stat().st_size
        assert logical(inbox) == records
    with open_inbox(*inbox_settings) as inbox:
        assert logical(inbox) == records
        assert inbox.page() == {"reconcile": True, "page": uncertain}
        assert (
            inbox.accept(SCOPE, selected, {"accepted": 13}, verify=lambda: True)["locally_accepted"]
            == 0
        )
        assert inbox.acknowledge(receipt(binding, uncertain))["pending_events"] == 0
        assert inbox.status()["forgotten_events"] == 1


def test_legacy_conversion_waits_for_pending_delivery_then_preserves_history(inbox_settings):
    with open_inbox(*inbox_settings, create=True) as inbox:
        _, uncertain = filled(inbox, legacy=True)
        records = logical(inbox)
        report = storage.reclaim(inbox)
        assert report["state"] == "deferred" and report["reason"] == "pending_legacy"
        assert inbox.connection.execute("PRAGMA auto_vacuum").fetchone()[0] == 0
        assert logical(inbox) == records
        inbox.acknowledge(receipt(inbox.binding, uncertain))
        records = logical(inbox)
        report = storage.reclaim(inbox)
        assert report["state"] == "reclaimed" and report["reclaimed_bytes"] > 0
        assert inbox.connection.execute("PRAGMA auto_vacuum").fetchone()[0] == 2
        assert logical(inbox) == records
        assert inbox.connection.execute("PRAGMA temp_store").fetchone()[0] == 2


def test_byte_budget_resumes_and_reduced_database_limit_becomes_usable(inbox_settings, monkeypatch):
    monkeypatch.setattr(storage, "RECLAIM_BYTES", 32768)
    with open_inbox(*inbox_settings, create=True) as inbox:
        selected, _ = filled(inbox, pending=False)
        records = logical(inbox)
        before = inbox.status()["database_bytes"]
        inbox.limits = replace(Limits(), database_bytes=131072)
        assert inbox.status()["over_limit"]
        reclaimed = 0
        for _ in range(100):
            report = storage.reclaim(inbox)
            assert report["reclaimed_bytes"] <= storage.RECLAIM_BYTES
            reclaimed += report["reclaimed_bytes"]
            if report["state"] != "deferred":
                break
            assert report["reason"] == "byte_budget"
        else:
            pytest.fail("Bounded cleanup never finished")
        assert reclaimed == before - report["database_bytes"]
        assert logical(inbox) == records
        assert not inbox.status()["over_limit"]
        assert (
            inbox.accept(
                SCOPE,
                [event(inbox.binding, external="new")],
                {"accepted": len(selected) + 1},
                verify=lambda: True,
            )["locally_accepted"]
            == 1
        )


@pytest.mark.parametrize("legacy", [False, True])
def test_disk_reserve_defers_without_changing_custody(inbox_settings, monkeypatch, legacy):
    with open_inbox(*inbox_settings, create=True) as inbox:
        filled(inbox, pending=False, legacy=legacy)
        records = logical(inbox)
        monkeypatch.setattr(
            storage, "shutil", SimpleNamespace(disk_usage=lambda _: SimpleNamespace(free=0))
        )
        report = storage.reclaim(inbox)
        assert report["state"] == "deferred" and report["reason"] == "disk_reserve"
        assert report["reclaimed_bytes"] == 0 and logical(inbox) == records


@pytest.mark.parametrize("legacy", [False, True])
def test_elapsed_budget_does_not_start_a_cleanup(inbox_settings, monkeypatch, legacy):
    with open_inbox(*inbox_settings, create=True) as inbox:
        filled(inbox, pending=False, legacy=legacy)
        records = logical(inbox)
        monkeypatch.setattr(storage, "RECLAIM_SECONDS", 0)
        report = storage.reclaim(inbox)
        assert report["state"] == "deferred" and report["reason"] == "time_budget"
        assert report["reclaimed_bytes"] == 0 and logical(inbox) == records


def test_interrupted_legacy_conversion_rolls_back_and_can_resume(inbox_settings, monkeypatch):
    with open_inbox(*inbox_settings, create=True) as inbox:
        filled(inbox, pending=False, legacy=True, count=160)
        records = logical(inbox)
        clock = iter([0.0, 0.0])
        original_time = storage.time
        monkeypatch.setattr(storage, "time", SimpleNamespace(monotonic=lambda: next(clock, 1.0)))
        report = storage.reclaim(inbox)
        assert report["state"] == "deferred" and report["reason"] == "time_budget"
        assert not inbox.connection.in_transaction
        assert inbox.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert logical(inbox) == records
        monkeypatch.setattr(storage, "time", original_time)
        report = storage.reclaim(inbox)
        assert report["state"] == "reclaimed" and logical(inbox) == records


def test_sqlite_cleanup_failure_remains_separate_from_delivery(inbox_settings):
    with open_inbox(*inbox_settings, create=True) as inbox:
        _, uncertain = filled(inbox)
        records = logical(inbox)
        inbox.connection.set_authorizer(
            lambda action, first, *_: (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_PRAGMA and first == "incremental_vacuum"
                else sqlite3.SQLITE_OK
            )
        )
        try:
            report = storage.reclaim(inbox)
        finally:
            inbox.connection.set_authorizer(None)
        assert report["state"] == "failed" and report["reason"] == "sqlite_failure"
        assert logical(inbox) == records
        assert inbox.acknowledge(receipt(inbox.binding, uncertain))["pending_events"] == 0


def test_cleanup_cannot_commit_an_in_progress_acceptance(inbox_settings):
    with open_inbox(*inbox_settings, create=True) as inbox:
        with inbox._transaction():
            with pytest.raises(RuntimeError, match="idle inbox transaction"):
                storage.reclaim(inbox)
            assert inbox.connection.in_transaction


def test_encrypted_backup_after_cleanup_preserves_recovery(inbox_settings, tmp_path):
    from mnemion.backup_encryption import new_key
    from mnemion.connectors.capture_archive import export_archive, restore_new_inbox

    _, binding, key = inbox_settings
    archive, secret = tmp_path / "cleaned.capture", new_key()
    staging, recovered = tmp_path / "staging", tmp_path / "recovered"
    with open_inbox(*inbox_settings, create=True) as inbox:
        _, uncertain = filled(inbox)
        records = logical(inbox)
        assert storage.reclaim(inbox)["reclaimed_bytes"] > 0
        exported = export_archive(
            inbox, key, archive, secret, staging_root=staging, name="Cleaned fixture"
        )
    restored = restore_new_inbox(
        archive, secret, recovered, staging_root=staging, expected_sha256=exported["archive_sha256"]
    )
    with open_inbox(recovered, binding, restored.inbox_key) as inbox:
        assert logical(inbox) == records
        assert inbox.page() == {"reconcile": True, "page": uncertain}
        assert inbox.acknowledge(receipt(binding, uncertain))["pending_events"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"raw_body": "Never publish this unexpected content"},
        {"reclaimable_bytes": 65537},
        {"reclaimed_bytes": -1},
        {"reclaimed_bytes": True},
        {"state": "reclaimed"},
        {"state": "deferred"},
        {"reason": "sqlite_failure"},
        {"state": "failed", "reason": "time_budget"},
    ],
)
def test_storage_observations_reject_invalid_or_content_bearing_state(changes):
    value = {
        "format": "mnemion-capture-storage-v1",
        "state": "idle",
        "database_bytes": 65536,
        "reclaimable_bytes": 0,
        "reclaimed_bytes": 0,
        "reason": None,
        **changes,
    }
    with pytest.raises(ValueError):
        storage.StorageReport.model_validate(value)
