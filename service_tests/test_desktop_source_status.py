"""Private on-disk observations and configuration/crash boundaries; no network."""

import base64
import json
import os
import subprocess
import sys
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mnemion import desktop_source_status as status
from mnemion import desktop_sources as sources
from mnemion import local_state
from mnemion.capture_coverage import CaptureCoverage, IndexCounts, IndexProgress, IndexSweep
from mnemion.desktop_capture import CaptureReport


@pytest.fixture
def saved(tmp_path):
    root = tmp_path / "private"
    value = {
        "id": str(uuid4()),
        "endpoint": "https://memory.example.invalid",
        "tenant_id": str(uuid4()),
        "connector_id": str(uuid4()),
        "principal_id": str(uuid4()),
        "name": "Private synthetic source",
        "provider": "filesystem",
        "path": str(tmp_path / "selected"),
        "members": ["employee:synthetic"],
        "publish_to_mapped_members": True,
        "sealed_key": base64.b64encode(b"synthetic protected bytes only").decode(),
    }
    document = sources.store(root, "not-configured", [value])
    return root, document["sources"][0], document["revision"]


def report(completed=True, **changes):
    return {
        "completed": completed,
        "timestamp": "2026-10-20T12:00:00Z",
        "duration_seconds": 0.5,
        "changed": 1,
        "removed": 0,
        "unchanged": 3,
        "conflicts": 0,
        "remote_sync_available": True,
        **changes,
    }


def backfill_report(delivered=False):
    pending = 0 if delivered else 2
    return report(
        completed=False,
        capture=CaptureReport(
            locally_accepted=2,
            pending_events=pending,
            pending_bytes=pending * 512,
            remote_committed_events=2 - pending,
            stored_events=2 - pending,
            forgotten_events=0,
            unknown_pages=0,
            database_bytes=65536,
            device_pending_bytes=pending * 512,
            device_database_bytes=65536,
            over_limit=False,
            capture_complete=False,
            delivery_complete=delivered,
            reason_code="capture_scan_pending",
        ).model_dump(mode="json"),
    )


def begin(saved, owner=None, run=None):
    root, source, revision = saved
    owner, run = owner or str(uuid4()), run or str(uuid4())
    result = sources.perform(
        root,
        {
            "operation": "status_begin",
            "expected_revision": revision,
            "id": source["id"],
            "owner": owner,
            "run": run,
        },
    )
    return owner, run, result


def finish(saved, owner, run, **fields):
    return sources.perform(
        saved[0],
        {"operation": "status_finish", "id": saved[1]["id"], "owner": owner, "run": run, **fields},
    )


def observe(saved, owner=None):
    return sources.perform(
        saved[0],
        {"operation": "status", "owner": owner or str(uuid4()), "expected_revision": saved[2]},
    )["sources"]


def repair(saved, token, **changes):
    return sources.perform(
        saved[0],
        {
            "operation": "status_repair",
            "owner": str(uuid4()),
            "expected_revision": saved[2],
            "id": saved[1]["id"],
            "repair_token": token,
            "confirm": True,
            **changes,
        },
    )


def test_success_failure_partial_and_schedule_survive_reopen_without_settings_churn(
    saved, monkeypatch
):
    original = (saved[0] / "sources.json").read_bytes()
    monkeypatch.setattr(status, "now", lambda: "2026-10-20T12:00:01+00:00")
    owner, run, opened = begin(saved)
    assert opened["activity"]["phase"] == "scanning"
    assert opened["activity"]["durability"] == "saved"
    assert observe(saved, owner)[0]["activity"]["phase"] == "scanning"
    good = finish(saved, owner, run, report=report())["activity"]
    assert good["phase"] == "complete"
    assert good["next_scan_at"] == "2026-10-20T12:05:01+00:00"
    assert good["last_success_report"] == report()
    assert observe(saved)[0]["activity"] == good
    owner, run, _ = begin(saved)
    failed = finish(saved, owner, run, reason_code="provider_unavailable")["activity"]
    assert failed["report"] == failed["last_success_report"] == report()
    assert failed["last_failure"]["reason_code"] == "provider_unavailable"
    owner, run, _ = begin(saved)
    partial = finish(saved, owner, run, report=report(False, changed=2))["activity"]
    assert partial["report"]["changed"] == 2
    assert partial["last_success_report"]["changed"] == 1
    assert partial["last_failure"]["reason_code"] == "partial"
    owner, run, _ = begin(saved)
    later = finish(saved, owner, run, report=report(changed=4))["activity"]
    assert later["last_success_report"]["changed"] == 4
    assert later["last_failure"] == partial["last_failure"], (
        "Success does not erase the previous failure"
    )
    assert (saved[0] / "sources.json").read_bytes() == original
    assert observe(saved)[0]["activity"] == later


@pytest.mark.parametrize("delivered", [False, True])
def test_backfill_survives_reopen_without_inventing_success_or_failure(
    saved, monkeypatch, delivered
):
    monkeypatch.setattr(status, "now", lambda: "2026-10-21T07:00:00+00:00")
    original = (saved[0] / "sources.json").read_bytes()
    owner, run, _ = begin(saved)
    first = finish(saved, owner, run, report=backfill_report(delivered))["activity"]
    assert first["phase"] == "backfill"
    assert first["durability"] == "saved"
    assert first["reason_code"] == "capture_scan_pending"
    assert first["next_scan_at"] == "2026-10-21T07:05:00+00:00"
    assert "last_success_report" not in first and "last_failure" not in first
    assert observe(saved)[0]["activity"] == first

    owner, run, _ = begin(saved)
    good = finish(saved, owner, run, report=report())["activity"]
    owner, run, _ = begin(saved)
    failed = finish(saved, owner, run, reason_code="provider_unavailable")["activity"]
    owner, run, _ = begin(saved)
    resumed = finish(saved, owner, run, report=backfill_report(delivered))["activity"]
    assert resumed["phase"] == "backfill"
    assert resumed["report"] == backfill_report(delivered)
    assert resumed["last_success_report"] == good["report"]
    assert resumed["last_failure"] == failed["last_failure"]
    assert observe(saved)[0]["activity"] == resumed
    assert (saved[0] / "sources.json").read_bytes() == original


def test_backfill_claim_requires_an_observed_report_and_remote_availability(saved):
    owner, run, _ = begin(saved)
    before = (saved[0] / "source-status.json").read_bytes()
    with pytest.raises(ValidationError):
        finish(saved, owner, run, reason_code="capture_scan_pending")
    assert (saved[0] / "source-status.json").read_bytes() == before
    incomplete = backfill_report()
    incomplete["remote_sync_available"] = False
    failed = finish(saved, owner, run, report=incomplete)["activity"]
    assert failed["phase"] == "attention"
    assert failed["last_failure"]["reason_code"] == "partial"

    path = saved[0] / "source-status.json"
    claimed = json.loads(path.read_bytes())
    claimed["records"][0].update(phase="backfill", reason_code="capture_scan_pending")
    path.write_text(json.dumps(claimed))
    preserved = path.read_bytes()
    damaged = observe(saved)[0]["activity"]
    assert damaged["reason_code"] == "source_status_invalid"
    assert path.read_bytes() == preserved, "An invalid success claim cannot silently repair itself"


def test_fresh_process_observes_crashed_scan_as_unknown_not_complete(saved):
    owner, run, _ = begin(saved)
    finish(saved, owner, run, report=report())
    owner, run, _ = begin(saved)
    original = (saved[0] / "source-status.json").read_bytes()
    code = """
import json, sys
from pathlib import Path
from mnemion.desktop_sources import perform
print(json.dumps(perform(Path(sys.argv[1]), json.loads(sys.argv[2]))))
"""
    request = {"operation": "status", "owner": str(uuid4()), "expected_revision": saved[2]}
    reopened = subprocess.run(
        [sys.executable, "-c", code, str(saved[0]), json.dumps(request)],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    activity = json.loads(reopened.stdout)["sources"][0]["activity"]
    assert activity["phase"] == "attention"
    assert activity["reason_code"] == "interrupted"
    assert "finished_at" not in activity and "next_scan_at" not in activity
    assert activity["last_success_report"] == report()
    assert (saved[0] / "source-status.json").read_bytes() == original, (
        "A status read is not a recovery mutation"
    )
    next_owner, next_run, new = begin(saved)
    assert new["activity"]["last_failure"]["reason_code"] == "interrupted"
    with pytest.raises(local_state.LocalSetupError):
        finish(saved, owner, run, report=report())
    finish(saved, next_owner, next_run, report=report())


@pytest.mark.parametrize("index_observed", [False, True])
def test_saved_capture_keeps_nullable_wire_fields_across_finish_reopen_and_next_scan(
    saved, index_observed
):
    index = IndexProgress()
    if index_observed:
        index = IndexProgress(
            status="available",
            last_attempt_at="2026-10-20T12:00:00Z",
            completed=IndexSweep(
                generation_id="synthetic-generation",
                inference_paused=True,
                started_at="2026-10-20T12:00:00Z",
                observed_at="2026-10-20T12:00:00Z",
                pages=1,
                counts=IndexCounts(),
            ),
        )
    capture = CaptureReport(
        locally_accepted=0,
        pending_events=0,
        pending_bytes=0,
        remote_committed_events=0,
        stored_events=0,
        forgotten_events=0,
        unknown_pages=0,
        database_bytes=0,
        device_pending_bytes=0,
        device_database_bytes=0,
        over_limit=False,
        capture_complete=True,
        delivery_complete=True,
        coverage=CaptureCoverage(capture_mode="messages", index=index),
    ).model_dump(mode="json")
    owner, run, _ = begin(saved)
    finished = finish(saved, owner, run, report=report(capture=capture))["activity"]
    reopened = observe(saved)[0]["activity"]
    _, _, restarted = begin(saved)
    for activity in (finished, reopened, restarted["activity"]):
        for field in ("report", "last_success_report"):
            assert activity[field]["capture"] == capture, (
                "Unknown coverage and index fields must remain explicit nulls on the desktop wire"
            )


def test_ambiguous_writes_are_not_replayed_and_original_observations_remain(saved, monkeypatch):
    write = local_state.write
    calls = []

    def lost_reply(path, value, **kwargs):
        calls.append(path.name)
        write(path, value, **kwargs)
        raise OSError("synthetic lost return after committed write")

    owner, run = str(uuid4()), str(uuid4())
    monkeypatch.setattr(local_state, "write", lost_reply)
    with pytest.raises(OSError):
        begin(saved, owner, run)
    assert calls == ["source-status.json"]
    before = (saved[0] / "source-status.json").read_bytes()
    monkeypatch.setattr(local_state, "write", write)
    with pytest.raises(local_state.LocalSetupError):
        begin(saved, owner, run)
    assert (saved[0] / "source-status.json").read_bytes() == before
    monkeypatch.setattr(local_state, "write", lost_reply)
    with pytest.raises(OSError):
        finish(saved, owner, run, report=report())
    monkeypatch.setattr(local_state, "write", write)
    assert observe(saved)[0]["activity"]["phase"] == "complete"
    with pytest.raises(local_state.LocalSetupError):
        finish(saved, owner, run, report=report())
    assert len(calls) == 2


def test_pause_retains_history_but_reconfiguration_removal_and_reused_id_cannot_resurrect_it(saved):
    owner, run, _ = begin(saved)
    finish(saved, owner, run, report=report())
    root, value, revision = saved
    epoch = value["status_epoch"]
    paused = sources.store(
        root, revision, [{**value, "enabled": False, "status_epoch": str(uuid4())}]
    )
    assert paused["sources"][0]["status_epoch"] == epoch, "Caller cannot control the private epoch"
    assert (
        observe((root, paused["sources"][0], paused["revision"]))[0]["activity"][
            "last_success_report"
        ]
        == report()
    )
    with pytest.raises(local_state.LocalSetupError):
        begin((root, paused["sources"][0], paused["revision"]))
    changed = sources.store(root, paused["revision"], [{**value, "max_files": 17}])
    assert changed["sources"][0]["status_epoch"] != epoch
    assert observe((root, changed["sources"][0], changed["revision"])) == []
    assert (
        finish((root, changed["sources"][0], changed["revision"]), owner, run, report=report())[
            "ignored"
        ]
        is True
    )
    removed = sources.store(root, changed["revision"], [])
    assert observe((root, value, removed["revision"])) == []
    reused = sources.store(root, removed["revision"], [value])
    assert reused["sources"][0]["status_epoch"] not in {
        epoch,
        changed["sources"][0]["status_epoch"],
    }
    assert observe((root, reused["sources"][0], reused["revision"])) == []


def test_legacy_settings_do_not_churn_on_scan_or_enabled_only_save(saved):
    root, value, revision = saved
    value.pop("status_epoch")
    local_state.write(
        root / "sources.json", {"format": 1, "revision": revision, "sources": [value]}
    )
    original = (root / "sources.json").read_bytes()
    owner, run, _ = begin(saved)
    finish(saved, owner, run, report=report())
    assert (root / "sources.json").read_bytes() == original
    paused = sources.store(root, revision, [{**value, "enabled": False}])
    assert "status_epoch" not in paused["sources"][0]
    assert observe((root, value, paused["revision"]))[0]["activity"]["phase"] == "complete"


@pytest.mark.parametrize(
    "change",
    [
        {"changed": -1},
        {"changed": True},
        {"changed": 10**12 + 1},
        {"completed": "true"},
        {"timestamp": "private raw contents"},
        {"timestamp": "2026-02-31T12:00:00Z"},
        {"duration_seconds": float("nan")},
        {"duration_seconds": float("inf")},
        {"credential": "do-not-persist"},
        {"raw_events": ["do-not-persist"]},
    ],
)
def test_reports_refuse_unbounded_or_untyped_data_without_overwriting_good_state(saved, change):
    owner, run, _ = begin(saved)
    before = (saved[0] / "source-status.json").read_bytes()
    with pytest.raises(ValidationError):
        finish(saved, owner, run, report=report(**change))
    assert (saved[0] / "source-status.json").read_bytes() == before


@pytest.mark.parametrize(
    "damaged",
    [
        b"not-json",
        b'{"format": 99, "records": []}',
        b'{"format": 1, "records": [], "message": "private raw error"}',
        b'{"format": 99, "format": 1, "records": []}',
        b'{"format": 1, "records": [], "records": []}',
        b"x" * (256 * 1024 + 1),
    ],
)
def test_damaged_status_is_retained_and_offline_pause_remove_still_work(saved, damaged):
    path = saved[0] / "source-status.json"
    path.write_bytes(damaged)
    path.chmod(0o600)
    activity = observe(saved)[0]["activity"]
    assert activity["reason_code"] == "source_status_invalid"
    assert activity["durability"] == "unavailable"
    assert ("repair_token" in activity) == (len(damaged) <= local_state.MAX_RECORD_BYTES)
    with pytest.raises(local_state.LocalSetupError):
        begin(saved)
    assert path.read_bytes() == damaged
    paused = sources.store(saved[0], saved[2], [{**saved[1], "enabled": False}])
    sources.store(saved[0], paused["revision"], [])
    assert path.read_bytes() == damaged


def test_explicit_repair_preserves_private_original_settings_capture_and_future_schedule(
    saved, monkeypatch
):
    root, value, revision = saved
    second = {**value, "id": str(uuid4()), "connector_id": str(uuid4()), "enabled": False}
    document = sources.store(root, revision, [value, second])
    saved = root, value, document["revision"]
    original_settings = (root / "sources.json").read_bytes()
    capture = local_state.directory(root / ("capture-" + value["id"])) / "checkpoint.db"
    capture.write_bytes(b"synthetic capture checkpoint remains exact")
    inbox = root / "synthetic-inbox.db"
    inbox.write_bytes(b"synthetic retained raw inbox")
    path = root / "source-status.json"
    damaged = b"SECRET raw malformed diagnostics\n{"
    path.write_bytes(damaged)
    path.chmod(0o600)
    monkeypatch.setattr(sources, "sync", lambda *args, **kwargs: pytest.fail("Repair cannot scan"))
    monkeypatch.setattr(
        sources,
        "Client",
        lambda *args, **kwargs: pytest.fail("Repair cannot open credentials or the network"),
    )
    activity = observe(saved)[0]["activity"]
    assert "SECRET" not in json.dumps(activity)
    result = repair(saved, activity["repair_token"])
    assert result == {
        "format": 1,
        "repaired": True,
        "history_restored": False,
        "original_preserved": True,
    }
    assert (root / "sources.json").read_bytes() == original_settings
    assert capture.read_bytes() == b"synthetic capture checkpoint remains exact"
    assert inbox.read_bytes() == b"synthetic retained raw inbox"
    archives = list((root / "recovery").glob("source-status-*.bin"))
    assert len(archives) == 1 and archives[0].read_bytes() == damaged
    if os.name != "nt":
        assert archives[0].stat().st_mode & 0o077 == 0
    restored = observe(saved)
    assert len(restored) == 2
    for entry in restored:
        observed = entry["activity"]
        assert observed["phase"] == "waiting" and observed["reason_code"] == "history_reset"
        assert observed["durability"] == "saved"
        assert "report" not in observed and "started_at" not in observed
        assert "last_success_report" not in observed and "repair_token" not in observed
        assert status.datetime.fromisoformat(observed["next_scan_at"]) > status.datetime.now(
            status.timezone.utc
        )
    code = "from mnemion.desktop_sources import perform; from pathlib import Path; import json,sys; print(json.dumps(perform(Path(sys.argv[1]),json.loads(sys.argv[2]))))"
    request = {"operation": "status", "owner": str(uuid4()), "expected_revision": saved[2]}
    reopened = subprocess.run(
        [sys.executable, "-c", code, str(root), json.dumps(request)],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert json.loads(reopened.stdout)["sources"] == restored
    assert "SECRET" not in reopened.stdout + reopened.stderr
    with pytest.raises(local_state.LocalSetupError, match="changed"):
        repair(saved, activity["repair_token"])
    assert len(list((root / "recovery").glob("source-status-*.bin"))) == 1


def test_repair_refuses_changed_bytes_or_settings_and_requires_explicit_boolean_confirmation(saved):
    root, value, revision = saved
    path = root / "source-status.json"
    path.write_bytes(b"damaged first")
    path.chmod(0o600)
    token = observe(saved)[0]["activity"]["repair_token"]
    for changes in (
        {"confirm": False},
        {"confirm": 1},
        {"confirm": None},
        {"repair_token": "SECRET"},
    ):
        with pytest.raises(ValidationError):
            repair(saved, token, **changes)
    assert not (root / "recovery").exists()
    path.write_bytes(b"damaged changed")
    with pytest.raises(local_state.LocalSetupError, match="changed"):
        repair(saved, token)
    assert path.read_bytes() == b"damaged changed"
    fresh = observe(saved)[0]["activity"]["repair_token"]
    changed = sources.store(root, revision, [{**value, "enabled": False}])
    with pytest.raises(local_state.LocalSetupError, match="changed"):
        repair(saved, fresh)
    with pytest.raises(local_state.LocalSetupError, match="changed"):
        repair((root, value, changed["revision"]), fresh)
    assert not (root / "recovery").exists()


def test_failed_repair_publication_retains_original_and_preserved_copy(saved, monkeypatch):
    path = saved[0] / "source-status.json"
    path.write_bytes(b"malformed preserved original")
    path.chmod(0o600)
    token = observe(saved)[0]["activity"]["repair_token"]
    monkeypatch.setattr(
        local_state,
        "_publish",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError("synthetic final publication failure")
        ),
    )
    with pytest.raises(OSError):
        repair(saved, token)
    assert path.read_bytes() == b"malformed preserved original"
    archives = list((saved[0] / "recovery").glob("source-status-*.bin"))
    assert len(archives) == 1 and archives[0].read_bytes() == path.read_bytes()
    assert observe(saved)[0]["activity"]["repair_token"] == token


def test_lost_repair_reply_is_observed_without_replaying_the_mutation(saved, monkeypatch):
    path = saved[0] / "source-status.json"
    path.write_bytes(b"damaged before lost reply")
    path.chmod(0o600)
    token = observe(saved)[0]["activity"]["repair_token"]
    original = local_state.replace_damaged
    calls = []

    def lose(*args, **kwargs):
        calls.append(1)
        original(*args, **kwargs)
        raise OSError("synthetic lost return after repair")

    monkeypatch.setattr(local_state, "replace_damaged", lose)
    with pytest.raises(OSError):
        repair(saved, token)
    assert observe(saved)[0]["activity"]["reason_code"] == "history_reset"
    with pytest.raises(local_state.LocalSetupError, match="changed"):
        repair(saved, token)
    assert calls == [1]


@pytest.mark.skipif(os.name == "nt", reason="Unix fixture permissions and symlink")
def test_unsafe_status_paths_never_receive_a_repair_token_or_become_mutable(saved):
    path = saved[0] / "source-status.json"
    target = saved[0] / "unrelated-private-file"
    target.write_bytes(b"unrelated private file")
    target.chmod(0o600)
    path.symlink_to(target)
    assert "repair_token" not in observe(saved)[0]["activity"]
    with pytest.raises(local_state.LocalSetupError):
        repair(saved, "a" * 64)
    assert path.is_symlink() and target.read_bytes() == b"unrelated private file"
    path.unlink()
    path.write_bytes(b"damaged but overly accessible")
    path.chmod(0o644)
    assert "repair_token" not in observe(saved)[0]["activity"]
    with pytest.raises(local_state.LocalSetupError):
        repair(saved, "a" * 64)
    assert path.read_bytes() == b"damaged but overly accessible"


def test_status_payload_lock_and_private_file_bounds(saved, monkeypatch):
    monkeypatch.setattr(
        sources,
        "Client",
        lambda *args, **kwargs: pytest.fail("Status must never contact a workspace"),
    )
    owner, run, _ = begin(saved)
    for extra in (
        {"message": "private exception"},
        {"reason_code": "arbitrary private error"},
        {"report": report(), "reason_code": "partial"},
    ):
        with pytest.raises(ValidationError):
            finish(saved, owner, run, **extra)
    original = (saved[0] / "source-status.json").read_bytes()
    with local_state.lock(saved[0]):
        with pytest.raises(local_state.LocalSetupError):
            observe(saved)
    assert (saved[0] / "source-status.json").read_bytes() == original
    assert saved[1]["name"].encode() not in original
    assert saved[1]["path"].encode() not in original
    assert saved[1]["sealed_key"].encode() not in original
    if os.name != "nt":
        assert (saved[0] / "source-status.json").stat().st_mode & 0o077 == 0
    record = json.loads(original)["records"][0]
    with pytest.raises(ValidationError):
        status.State(records=[record, record])
    with pytest.raises(ValidationError):
        status.State(records=[{**record, "id": str(uuid4())} for _ in range(17)])


def test_failed_settings_save_does_not_erase_last_valid_history(saved, monkeypatch):
    owner, run, _ = begin(saved)
    finish(saved, owner, run, report=report())
    before = (saved[0] / "source-status.json").read_bytes()
    monkeypatch.setattr(
        local_state,
        "write",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("synthetic storage failure")),
    )
    with pytest.raises(OSError):
        sources.store(saved[0], saved[2], [{**saved[1], "max_files": 3}])
    assert sources.load(saved[0]).revision == saved[2]
    assert (saved[0] / "source-status.json").read_bytes() == before
    assert observe(saved)[0]["activity"]["phase"] == "complete"
