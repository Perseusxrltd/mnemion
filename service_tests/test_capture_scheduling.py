"""Fair retained-source work survives bounded passes, failures and recovery."""

from dataclasses import replace
from contextlib import nullcontext
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from mnemion import backup_encryption
from mnemion.connectors import conversation_capture as capture, managed, runner
from mnemion.connectors.capture_archive import export_archive
from mnemion.connectors.capture_transfer import restore_device_copy
from mnemion.connectors.conversation_inbox import Limits, open_inbox
from mnemion.connectors.live_conversations import ConversationProvider
from mnemion.service import service_updates, update_state
from service_tests.test_capture_custody import custody as custody
from service_tests.test_capture_windows import identities
from service_tests.test_durable_conversation_capture import line, selected as selected
from service_tests.test_headless_durable_capture import cli, headless as headless, prepared
from service_tests.test_live_conversations import conversation_source as conversation_source
from service_tests.test_managed_connectors import executable, setup as setup


def files(config, count=3):
    for index in range(count):
        (config.path / f"source-{index}.jsonl").write_bytes(line(f"Small source {index}"))
    provider = ConversationProvider(config)
    order = sorted(provider.scopes())
    return order, {scope: config.path / provider.paths[scope] for scope in order}


@pytest.mark.parametrize("mode", ["messages", "complete"])
def test_reopened_sweeps_rotate_past_busy_source_and_match_one_pass(
    selected, tmp_path, monkeypatch, mode
):
    config, settings = selected
    config.capture_mode = settings[1]["capture_mode"] = mode
    config.segment_records = 1
    order, paths = files(config)
    paths[order[0]].write_bytes(b"".join(line(f"Busy source record {i}") for i in range(4)))
    with open_inbox(tmp_path / "reference", settings[1], os.urandom(32), create=True) as inbox:
        assert capture.capture_available(inbox, ConversationProvider(config))["completed"]
        expected = identities(inbox)
    monkeypatch.setattr(capture, "PASS_SCOPES", 1)
    monkeypatch.setattr(capture, "WINDOW_SEGMENTS", 1)
    visited = []
    for attempt in range(12):
        with open_inbox(*settings, create=attempt == 0) as inbox:
            result = capture.capture_available(inbox, ConversationProvider(config))
            assert not result["errors"]
            visited.append(result["scopes"][0]["external_id"])
            assert visited[-1] == order[attempt % len(order)]
            assert result["coverage"]["uncertain_intervals"] == 0
            assert result["coverage"]["failed_scopes"] == 0
            if result["completed"]:
                assert attempt == 11
                assert identities(inbox) == expected
                assert result["coverage"]["complete_prefix_at"]
            else:
                assert result["deferred"] and result["coverage"]["checking_scopes"]
                assert result["coverage"]["complete_prefix_at"] is None
    assert visited[:3] == order, "Small sources must progress while the first one is backfilling"


@pytest.mark.parametrize("limit", ["scopes", "segments", "bytes", "time"])
def test_shared_work_limits_yield_before_the_next_source(selected, monkeypatch, limit):
    config, settings = selected
    order, paths = files(config)
    if limit == "time":
        elapsed = [0.0]
        monkeypatch.setattr(capture, "time", SimpleNamespace(monotonic=lambda: elapsed[0]))
        monkeypatch.setattr(capture, "PASS_SECONDS", 1)
        original = capture.capture_scope

        def one_slow_scope(*args, **kwargs):
            result = original(*args, **kwargs)
            elapsed[0] += 2
            return result

        monkeypatch.setattr(capture, "capture_scope", one_slow_scope)
    else:
        monkeypatch.setattr(
            capture,
            "PASS_" + limit.upper(),
            paths[order[0]].stat().st_size if limit == "bytes" else 1,
        )
    with open_inbox(*settings, create=True) as inbox:
        result = capture.capture_available(inbox, ConversationProvider(config))
        assert [value["external_id"] for value in result["scopes"]] == order[:1]
        assert result["deferred"] and not result["errors"]
        assert result["coverage"]["checking_scopes"] == 2
        assert result["coverage"]["records"]["lines"] == 1


def test_actual_prefix_verification_bytes_use_the_shared_allowance(selected, monkeypatch):
    config, settings = selected
    config.segment_records = 1
    raw = line("Prefix and next record " + "x" * 200)
    (config.path / "one.jsonl").write_bytes(raw * 6)
    monkeypatch.setattr(capture, "WINDOW_SEGMENTS", 1)
    with open_inbox(*settings, create=True) as inbox:
        first = capture.capture_available(inbox, ConversationProvider(config))
        assert first["coverage"]["records"]["lines"] == 1
    monkeypatch.setattr(capture, "WINDOW_SEGMENTS", 64)
    monkeypatch.setattr(capture, "PASS_BYTES", len(raw) * 2 + 1)
    with open_inbox(*settings) as inbox:
        resumed = capture.capture_available(inbox, ConversationProvider(config))
        report = resumed["scopes"][0]["capture"]
        assert report["segments_rendered"] == 1
        assert report["bytes_read"] > capture.PASS_BYTES, "Prefix verification/read-ahead count too"
        assert resumed["coverage"]["records"]["lines"] == 2
        assert resumed["deferred"] and not resumed["errors"]


def test_capacity_failure_cannot_starve_small_source_or_disappear_from_status(
    selected, monkeypatch
):
    config, settings = selected
    order, paths = files(config, 2)
    paths[order[0]].write_bytes(line("Large blocked record " + "x" * 100_000))
    monkeypatch.setattr(capture, "PASS_SCOPES", 1)
    small = replace(Limits(), pending_bytes=10_000)
    with open_inbox(*settings, create=True, limits=small) as inbox:
        blocked = capture.capture_available(inbox, ConversationProvider(config))
        assert blocked["errors"] == ["capture_capacity_blocked"]
        assert blocked["pending_events"] == 0
    with open_inbox(*settings, limits=small) as inbox:
        other = capture.capture_available(inbox, ConversationProvider(config))
        assert other["scopes"][0]["external_id"] == order[1]
        assert other["pending_events"] > 0
        assert other["coverage"]["failed_scopes"] == 1
        assert other["errors"] == ["capture_source_unavailable"]
        assert not other["completed"], "Earlier uncorrected failures cannot become healthy progress"
    with open_inbox(*settings) as inbox:
        repaired = capture.capture_available(inbox, ConversationProvider(config))
        assert not repaired["errors"] and repaired["coverage"]["failed_scopes"] == 0
        assert capture.capture_available(inbox, ConversationProvider(config))["completed"]


def test_crash_advances_rotation_but_keeps_the_unobserved_attempt_uncertain(selected, monkeypatch):
    config, settings = selected
    order, _ = files(config, 2)
    monkeypatch.setattr(capture, "PASS_SCOPES", 1)

    class Interrupted(BaseException):
        pass

    original = capture.capture_scope
    with monkeypatch.context() as fault:
        fault.setattr(
            capture, "capture_scope", lambda *args, **kwargs: (_ for _ in ()).throw(Interrupted())
        )
        with pytest.raises(Interrupted), open_inbox(*settings, create=True) as inbox:
            capture.capture_available(inbox, ConversationProvider(config))
    assert capture.capture_scope is original
    with open_inbox(*settings) as inbox:
        resumed = capture.capture_available(inbox, ConversationProvider(config))
        assert resumed["scopes"][0]["external_id"] == order[1]
        assert resumed["coverage"]["uncertain_intervals"] == 1
        assert resumed["coverage"]["unknown_prefix_scopes"] == 1
        assert not resumed["completed"]
        for _ in range(2):
            final = capture.capture_available(inbox, ConversationProvider(config))
        assert final["completed"] and final["coverage"]["records"]["lines"] == 2
        assert final["coverage"]["uncertain_intervals"] == 1


def test_encrypted_schedule_corruption_is_retained_and_stops_intake(selected, monkeypatch):
    config, settings = selected
    files(config)
    monkeypatch.setattr(capture, "PASS_SCOPES", 1)
    with open_inbox(*settings, create=True) as inbox:
        before = capture.capture_available(inbox, ConversationProvider(config))
        encrypted = inbox.connection.execute(
            "SELECT value FROM metadata WHERE name='coverage-schedule'"
        ).fetchone()[0]
        damaged = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
        inbox.connection.execute(
            "UPDATE metadata SET value=? WHERE name='coverage-schedule'", (damaged,)
        )
    with open_inbox(*settings) as inbox:
        refused = capture.capture_available(inbox, ConversationProvider(config))
        assert refused["errors"] == ["capture_integrity_failed"]
        assert refused["pending_events"] == before["pending_events"]
        assert (
            inbox.connection.execute(
                "SELECT value FROM metadata WHERE name='coverage-schedule'"
            ).fetchone()[0]
            == damaged
        )


def test_archive_device_recovery_preserves_rotation_with_a_new_key(selected, tmp_path, monkeypatch):
    config, settings = selected
    order, _ = files(config)
    monkeypatch.setattr(capture, "PASS_SCOPES", 1)
    archive, secret = tmp_path / "fair.capture", backup_encryption.new_key()
    with open_inbox(*settings, create=True) as inbox:
        capture.capture_available(inbox, ConversationProvider(config))
        before = identities(inbox)
        exported = export_archive(
            inbox,
            settings[2],
            archive,
            secret,
            staging_root=tmp_path / "staging",
            name="Fair import",
        )
    selected_binding = {**settings[1], "grant_id": str(uuid4())}
    recovered = restore_device_copy(
        archive,
        secret,
        tmp_path / "new-device",
        staging_root=tmp_path / "staging",
        expected_sha256=exported["archive_sha256"],
        selected_binding=selected_binding,
        inbox_key=os.urandom(32),
    )
    with open_inbox(recovered.directory, selected_binding, recovered.inbox_key) as inbox:
        assert identities(inbox) == before
        resumed = capture.capture_available(inbox, ConversationProvider(config))
        assert resumed["scopes"][0]["external_id"] == order[1]
        assert resumed["coverage"]["uncertain_intervals"] == 0


def test_catalog_changes_keep_rotation_and_require_the_new_sweep(selected, monkeypatch):
    config, settings = selected
    order, paths = files(config)
    monkeypatch.setattr(capture, "PASS_SCOPES", 1)
    with open_inbox(*settings, create=True) as inbox:
        first = capture.capture_available(inbox, ConversationProvider(config))
        assert first["scopes"][0]["external_id"] == order[0]
        paths[order[0]].unlink()
        (config.path / "new.jsonl").write_bytes(line("A newly connected source"))
        current = sorted(ConversationProvider(config).scopes())
        expected = [scope for scope in current if scope > order[0]] + [
            scope for scope in current if scope <= order[0]
        ]
        for index, scope in enumerate(expected):
            result = capture.capture_available(inbox, ConversationProvider(config))
            assert result["scopes"][0]["external_id"] == scope
            assert result["completed"] is (index == len(expected) - 1)
            assert result["coverage"]["missing_scopes"] == 1
            assert result["coverage"]["complete_prefix_at"] is None
        assert result["coverage"]["records"]["lines"] == 4


def test_real_headless_watch_resumes_intake_and_bounded_delivery_after_an_outage(
    headless, tmp_path
):
    headless["config"].poll_seconds = 60
    headless["config"].provider.segment_records = 1
    headless["file"].write_text(headless["config"].model_dump_json(), encoding="utf-8")
    prepared(headless, child=True)
    folder = headless["config"].provider.path
    for source in range(9):
        (folder / f"source-{source}.jsonl").write_bytes(
            b"".join(
                line(f"Independent agent source {source} record {index}") for index in range(64)
            )
        )
    headless["offline"].set()
    headless["expected"].append(True)
    first = cli(headless, code=2)
    assert headless["observed"] == [first["capture"]["pending_events"]]
    assert 0 < first["capture"]["pending_events"] <= 256
    assert first["capture"]["coverage"]["checking_scopes"] > 0
    headless["offline"].clear()
    reports = watch_reports(headless, tmp_path)
    queued, completed = reports[0][1], reports[-1][1]
    assert not queued["completed"] and 0 < queued["capture"]["stored_events"] <= 200
    assert {item[1]["capture"]["reason_code"] for item in reports} == {
        "capture_scan_pending",
        "capture_delivery_pending",
        None,
    }
    assert completed["completed"] and completed["capture"]["stored_events"] == 576
    assert completed["capture"]["pending_events"] == 0
    assert completed["capture"]["coverage"]["records"]["selected"] == 576
    assert completed["capture"]["coverage"]["uncertain_intervals"] == 0
    assert all(4 <= after[0] - before[0] < 60 for before, after in zip(reports, reports[1:]))


def watch_reports(headless, tmp_path):
    received, reports = queue.Queue(), []
    with (tmp_path / "watch.stderr").open("w", encoding="utf-8") as errors:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "mnemion.connectors.runner",
                "--config",
                str(headless["file"]),
                "--watch",
            ],
            cwd=Path(__file__).parents[1],
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
        )

        def read_output():
            for raw in process.stdout:
                received.put((time.monotonic(), raw))
            received.put((time.monotonic(), None))

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        deadline = time.monotonic() + 90
        try:
            while len(reports) < 8:
                observed, raw = received.get(timeout=max(0.1, deadline - time.monotonic()))
                assert raw is not None, "The watcher exited before completing its backfill"
                assert headless["secret"] not in raw
                result = json.loads(raw)
                if result.get("event") == "connector_runtime":
                    continue
                reports.append((observed, result))
                if result.get("completed") is True:
                    break
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            reader.join(timeout=5)
            process.stdout.close()
    assert reports[-1][1]["completed"] and reports[-1][1]["trigger"] == "poll"
    assert headless["secret"] not in (tmp_path / "watch.stderr").read_text(encoding="utf-8")
    return reports


@pytest.mark.parametrize("failure", ["exception", "control", "delivery"])
def test_watch_drops_fast_cadence_after_an_error(headless, monkeypatch, failure):
    from mnemion.connectors import capture_resources

    # This mocks scans to test scheduling inside the whole pytest process.
    # That process includes service/model/coverage allocations unrelated to a
    # capture child. The real CLI RSS guard has independent subprocess tests.
    monkeypatch.setattr(capture_resources, "bounded", lambda _: nullcontext())
    config = headless["config"]
    config.remote_sync = False
    headless["file"].write_text(config.model_dump_json(), encoding="utf-8")
    prepared(headless)
    report = {
        "connector_id": str(config.connector_id),
        "timestamp": "2026-10-21T08:00:00+00:00",
        "completed": False,
        "remote_sync_available": True,
        "capture": {"capture_complete": False, "reason_code": "capture_scan_pending"},
    }
    failed = {
        "exception": OSError("Synthetic provider outage"),
        "control": {**report, "control_reported": False},
        "delivery": {**report, "remote_sync_available": False},
    }[failure]
    iterations = [report, failed]

    def scan(*args, **kwargs):
        value = iterations.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    waits = []
    original = runner.wait_for_sync

    def wait(current, **kwargs):
        elapsed = [0.0]

        def sleep(seconds):
            elapsed[0] += seconds

        result = original(current, **kwargs, clock=lambda: elapsed[0], sleep=sleep)
        waits.append(elapsed[0])
        if len(waits) == 2:
            raise KeyboardInterrupt()
        return result

    monkeypatch.delenv(runner.SCAN_REPORT_ENV, raising=False)
    monkeypatch.setattr(runner, "sync", scan)
    monkeypatch.setattr(runner, "wait_for_sync", wait)
    assert runner.main(["--config", str(headless["file"]), "--watch"]) == 130
    assert not iterations, "Both scans must run before testing their retry cadence"
    assert waits == [5, config.poll_seconds]


@pytest.mark.skipif(os.name != "posix", reason="Managed service updates run on Unix")
def test_managed_cadence_requires_a_fresh_matching_incomplete_receipt(
    headless, setup, tmp_path, monkeypatch
):
    config = headless["config"]
    config.connector_id = UUID(setup.identifier)
    update_state.write(setup.path, config.model_dump(mode="json"))
    body = (
        "receipt = Path(os.environ['MNEMION_CONNECTOR_REPORT_PATH'])\n"
        "receipt.write_text(json.dumps({'format': 1, 'connector_id': config['connector_id'], "
        "'runner_version': '4.44.1', 'completed': False, 'capture_backfill': True}))\n"
        "receipt.chmod(0o600)\nraise SystemExit(2)\n"
    )
    good = {**executable(tmp_path, "4.44.1", body), "capture_protocol": 1}
    mismatched = {**executable(tmp_path, "4.44.2", body), "capture_protocol": 1}
    missing = {**executable(tmp_path, "4.44.3", "raise SystemExit(2)\n"), "capture_protocol": 1}
    runtimes = iter((good, mismatched, good, missing))
    monkeypatch.setattr(service_updates, "resolved_runtime", lambda _: next(runtimes))
    monkeypatch.setenv("MNEMION_FIXTURE_RECEIPT", str(tmp_path / "managed-runs.jsonl"))
    waits = []

    def wait(current, **kwargs):
        observed = update_state.read(setup.entry / "status.json")
        assert observed["last_exit_code"] == 2
        assert observed.get("scanned_commit") is None and observed.get("scanned_at") is None
        assert kwargs["failed"] is True
        waits.append(kwargs["backfill"])
        if len(waits) == 4:
            raise managed.Stopped()
        return "poll"

    monkeypatch.setattr(managed, "wait_for_sync", wait)
    with pytest.raises(managed.Stopped):
        managed.run(setup.state, setup.path, managed.Control())
    assert waits == [True, False, True, False]
    assert not (setup.entry / "scan-result.json").exists(), "A previous receipt cannot be reused"
