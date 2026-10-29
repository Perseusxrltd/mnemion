"""Local work ownership, meaningful-work filtering and coarse process sensors."""

import json
import argparse
from contextlib import nullcontext
from io import BytesIO
from types import SimpleNamespace
from typing import get_args

import pytest

from mnemion import maintenance_measurement as measured
from mnemion.product_telemetry import aggregate, policy
from mnemion.product_telemetry.catalog import maintenance_specification


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "private"
    monkeypatch.setattr(policy, "default_directory", lambda: root)
    monkeypatch.setattr(policy, "company_policy_file", lambda: tmp_path / "absent-company.json")
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/telemetry")
    policy.configure(
        root,
        {"enabled": True, "expected_revision": 0, "disclosure_version": policy.DISCLOSURE_VERSION},
    )
    return root


def report(**changes):
    return {
        "completed": True,
        "changed": 7,
        "removed": 0,
        "conflicts": 0,
        "remote_sync_available": True,
        "PRIVATE_LABEL": "PRIVATE_SOURCE_CONTENT",
        **changes,
    }


def test_fresh_source_work_collects_only_fixed_counters_and_process_buckets(installation):
    observation = measured.begin_source(capture=False, owned=True)
    observation.process = SimpleNamespace(
        memory_info=lambda: SimpleNamespace(rss=123456789),
        cpu_times=lambda: SimpleNamespace(user=12.0, system=1.0),
    )
    observation.cpu = 12.9
    observation.started -= 1
    observation.finish(report())
    rows = aggregate.preview(installation)
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == 1
    assert {row.get("workflow") for row in rows if "workflow" in row} == {"sources.scan"}
    assert {row["metric"] for row in rows} >= {"rss_bytes", "cpu_millicores", "work_items"}
    assert "PRIVATE" not in json.dumps(rows) and "123456789" not in json.dumps(rows)
    assert b"PRIVATE" not in (installation / policy.DATABASE_NAME).read_bytes()


def test_empty_and_paused_scans_and_unowned_work_create_no_measurements(installation):
    assert measured.begin_source(capture=False, owned=False) is None
    measured.begin_source(capture=False, owned=True).finish(report(changed=0))
    measured.begin_source(capture=True, owned=True).finish({"paused": True})
    assert aggregate.preview(installation) == []


def test_capture_partial_work_and_final_opt_out_preserve_original_generation(installation):
    active = measured.begin_source(capture=True, owned=True, memory_limit=256 * 1024**2)
    active.process = None
    active.finish(
        report(
            completed=False,
            remote_sync_available=False,
            capture={
                "locally_accepted": 3,
                "remote_committed_events": 0,
                "pending_events": 3,
                "database_bytes": 65536,
                "reason_code": "capture_delivery_unavailable",
            },
        )
    )
    rows = aggregate.preview(installation)
    assert next(row for row in rows if row["metric"] == "outcomes")["bucket"] == "deferred"
    assert next(row for row in rows if row["metric"] == "reasons")["bucket"] == "offline"
    stale = measured.begin_source(capture=False, owned=True)
    policy.configure(installation, {"enabled": False, "expected_revision": 0})
    stale.finish(report())
    assert aggregate.preview(installation) == []


def test_sensor_failure_preserves_the_real_source_outcome(installation):
    active = measured.begin_source(capture=False, owned=True)
    active.process = SimpleNamespace(
        memory_info=lambda: (_ for _ in ()).throw(OSError("PRIVATE_SENSOR"))
    )
    active.finish(report())
    rows = aggregate.preview(installation)
    assert next(row for row in rows if row["metric"] == "outcomes")["bucket"] == "success"
    assert not any(row["metric"] in {"rss_bytes", "cpu_millicores"} for row in rows)


@pytest.mark.parametrize("fresh", [12, 0, None])
def test_capture_counts_only_fresh_receipts_and_keeps_work_and_results_separate(
    installation, fresh
):
    active = measured.begin_source(capture=True, owned=True)
    active.process = None
    active.finish(
        report(
            capture={
                "locally_accepted": 3,
                "remote_committed_events": 12,
                "newly_stored_events": fresh,
                "pending_events": 0,
                "database_bytes": 65536,
                "PRIVATE_RECEIPT": "PRIVATE_ITEMS",
            }
        )
    )
    rows = aggregate.preview(installation)
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == 1
    assert {row.get("workflow") for row in rows} == {"capture.collect"}
    assert next(row for row in rows if row["metric"] == "work_items")["bucket"] == 2
    results = [row for row in rows if row["metric"] == "result_items"]
    assert len(results) == int(fresh is not None)
    if results:
        assert results[0]["bucket"] == (3 if fresh == 12 else 0)
    assert "PRIVATE" not in json.dumps(rows)


@pytest.mark.parametrize("fresh", [0, None])
def test_reconciled_or_unknown_receipts_alone_do_not_invent_a_fresh_capture_use(
    installation, fresh
):
    active = measured.begin_source(capture=True, owned=True)
    active.finish(
        report(
            capture={
                "locally_accepted": 0,
                "remote_committed_events": 12,
                "newly_stored_events": fresh,
                "pending_events": 0,
                "database_bytes": 65536,
            }
        )
    )
    assert aggregate.preview(installation) == []


@pytest.mark.parametrize("completed", [True, False])
def test_new_delivery_without_local_capture_finishes_once(installation, completed):
    active = measured.begin_source(capture=True, owned=True)
    active.process = None
    active.finish(
        report(
            completed=completed,
            capture={
                "locally_accepted": 0,
                "remote_committed_events": 12,
                "newly_stored_events": 12,
                "pending_events": 0,
                "database_bytes": 65536,
            },
        )
    )
    active.finish(report())
    rows = aggregate.preview(installation)
    assert {row.get("workflow") for row in rows} == {"capture.deliver"}
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == 1
    assert next(row for row in rows if row["metric"] == "result_items")["bucket"] == 3
    assert next(row for row in rows if row["metric"] == "outcomes")["bucket"] == (
        "success" if completed else "deferred"
    )


@pytest.mark.parametrize("mode", ["owned", "inspect", "managed", "remote"])
def test_actual_connector_entrypoint_owns_only_its_local_work(
    installation, monkeypatch, capsys, mode
):
    from mnemion.connectors import runner

    monkeypatch.delenv(runner.SCAN_REPORT_ENV, raising=False)
    monkeypatch.delenv(runner.SCAN_TRIGGER_ENV, raising=False)
    if mode == "managed":
        monkeypatch.setenv(runner.SCAN_REPORT_ENV, "PRIVATE_MANAGED_REPORT")
    if mode == "remote":
        monkeypatch.setenv(runner.SCAN_TRIGGER_ENV, "requested")
    monkeypatch.setattr(
        runner, "read_config", lambda _: SimpleNamespace(capture=None, poll_seconds=300)
    )
    calls = []

    def sync(*args, **kwargs):
        calls.append(kwargs)
        return report()

    monkeypatch.setattr(runner, "sync", sync)
    monkeypatch.setattr(runner, "_report_managed", lambda _: None)
    args = SimpleNamespace(
        capture_control=False,
        watch=False,
        inspect=mode == "inspect",
        managed_state=None,
        config="PRIVATE_CONFIG",
    )
    assert runner.execute(args, argparse.ArgumentParser()) == 0
    assert len(calls) == 1
    returned = json.loads(capsys.readouterr().out)
    assert returned["PRIVATE_LABEL"] == "PRIVATE_SOURCE_CONTENT"
    rows = aggregate.preview(installation)
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == (
        1 if mode == "owned" else 0
    )


def test_all_capture_controls_have_an_explicit_owned_or_excluded_classification():
    from mnemion.connectors.headless_capture_control import Control

    spec = maintenance_specification()
    assert set(spec["capture_controls"]) == set(get_args(Control.model_fields["action"].annotation))
    for entry in spec["capture_controls"].values():
        assert ("workflow" in entry) != ("exclusion" in entry)
        if "exclusion" in entry:
            assert entry["exclusion"] in spec["exclusions"]


def capture_command(monkeypatch, tmp_path, action, effect):
    from mnemion.connectors import capture_resources, headless_capture_control, runner

    monkeypatch.delenv(runner.SCAN_REPORT_ENV, raising=False)
    monkeypatch.delenv(runner.SCAN_TRIGGER_ENV, raising=False)
    monkeypatch.setattr(
        runner,
        "read_config",
        lambda _: SimpleNamespace(capture=SimpleNamespace(memory_limit_mib=256)),
    )
    monkeypatch.setattr(capture_resources, "bounded", lambda _: nullcontext())
    body = {
        "action": action,
        "confirm": True,
        "expected_revision": "PRIVATE_REVISION",
        "preview_hash": "a" * 64,
        "archive": str(tmp_path / "PRIVATE_ARCHIVE"),
        "archive_sha256": "b" * 64,
        "recovery_key": {"env": "PRIVATE_RECOVERY_KEY"},
        "retirement_token": {"env": "PRIVATE_RETIREMENT_TOKEN"},
    }
    monkeypatch.setattr(
        runner.sys, "stdin", SimpleNamespace(buffer=BytesIO(json.dumps(body).encode()))
    )
    calls = []

    def perform(config, request):
        calls.append(request.action)
        assert request.expected_revision == "PRIVATE_REVISION"
        return effect()

    monkeypatch.setattr(headless_capture_control, "perform", perform)
    args = SimpleNamespace(
        capture_control=True,
        watch=False,
        inspect=False,
        managed_state=None,
        config="PRIVATE_CONFIG",
    )
    return runner, args, calls


@pytest.mark.parametrize(
    "action,spec", list(maintenance_specification()["capture_controls"].items())
)
def test_actual_capture_control_entrypoint_records_only_its_fixed_acknowledgement(
    installation, monkeypatch, tmp_path, capsys, action, spec
):
    result = {"PRIVATE_RESULT": "PRIVATE_CAPTURE_CONTENT", "delivered": 12789}
    runner, args, calls = capture_command(monkeypatch, tmp_path, action, lambda: result)
    assert runner.execute(args, argparse.ArgumentParser()) == 0
    assert calls == [action]
    assert json.loads(capsys.readouterr().out)["result"] == result
    rows = aggregate.preview(installation)
    if "exclusion" in spec:
        assert rows == []
    else:
        assert sum(row["count"] for row in rows if row["metric"] == "submissions") == 1
        assert {row["workflow"] for row in rows} == {spec["workflow"]}
        assert {row["surface"] for row in rows} == {"headless"}
        assert (
            next(row for row in rows if row["metric"] == "outcomes")["bucket"] == spec["completion"]
        )
        assert not {"work_items", "result_items", "queue_items"} & {row["metric"] for row in rows}
    assert "PRIVATE" not in json.dumps(rows) and "12789" not in json.dumps(rows)
    assert b"PRIVATE" not in (installation / policy.DATABASE_NAME).read_bytes()


@pytest.mark.parametrize(
    "action,expected", [("preview", "capture.preview"), ("pause", "capture.pause")]
)
def test_standalone_preview_and_pause_have_capture_specific_categories(
    installation, monkeypatch, tmp_path, capsys, action, expected
):
    result = {"PRIVATE_RESULT": "PRIVATE_CONTENT"}
    runner, args, calls = capture_command(monkeypatch, tmp_path, action, lambda: result)
    assert runner.execute(args, argparse.ArgumentParser()) == 0
    assert calls == [action]
    assert json.loads(capsys.readouterr().out)["result"] == result
    rows = aggregate.preview(installation)
    assert {row["workflow"] for row in rows} == {expected}
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == 1
    assert "PRIVATE" not in json.dumps(rows)


@pytest.mark.parametrize(
    "condition",
    ["managed", "remote", "opted_out", "unavailable", "late_opt_out", "observer_failure"],
)
def test_capture_controls_preserve_work_without_inheriting_or_resurrecting_consent(
    installation, monkeypatch, tmp_path, capsys, condition
):
    def effect():
        if condition == "late_opt_out":
            policy.configure(installation, {"enabled": False, "expected_revision": 0})
        return {"PRIVATE_RESULT": True}

    runner, args, calls = capture_command(monkeypatch, tmp_path, "pause", effect)
    if condition == "managed":
        monkeypatch.setenv(runner.SCAN_REPORT_ENV, "PRIVATE_MANAGED_REPORT")
    elif condition == "remote":
        monkeypatch.setenv(runner.SCAN_TRIGGER_ENV, "requested")
    elif condition == "opted_out":
        policy.configure(installation, {"enabled": False, "expected_revision": 0})
    elif condition == "unavailable":
        monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", False)
    elif condition == "observer_failure":
        monkeypatch.setattr(
            measured,
            "begin_capture_control",
            lambda *_a, **_k: (_ for _ in ()).throw(OSError("PRIVATE_OBSERVER")),
        )
    assert runner.execute(args, argparse.ArgumentParser()) == 0
    assert calls == ["pause"]
    assert json.loads(capsys.readouterr().out)["result"] == {"PRIVATE_RESULT": True}
    assert aggregate.preview(installation) == []


def test_capture_control_uncertainty_does_not_retry_the_original_operation(
    installation, monkeypatch, tmp_path, capsys
):
    def effect():
        raise OSError("PRIVATE_AFTER_MUTATION")

    runner, args, calls = capture_command(monkeypatch, tmp_path, "backup", effect)
    assert runner.execute(args, argparse.ArgumentParser()) == 2
    assert calls == ["backup"]
    assert "PRIVATE_AFTER_MUTATION" not in capsys.readouterr().err
    rows = aggregate.preview(installation)
    assert next(row for row in rows if row["metric"] == "outcomes")["bucket"] == "unconfirmed"
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == 1


def test_reusable_capture_control_helper_does_not_acquire_an_owner(monkeypatch):
    from mnemion.connectors import headless_capture_control as controls

    monkeypatch.setattr(controls.device, "status", lambda _: {"private": "PRIVATE_RESULT"})
    monkeypatch.setattr(
        measured.workflow, "begin", lambda *_a, **_k: pytest.fail("A helper inferred ownership")
    )
    assert controls.perform(SimpleNamespace(capture=True), {"action": "status"}) == {
        "private": "PRIVATE_RESULT"
    }


def test_capture_control_interruption_preserves_the_interrupt_and_never_replays(
    installation, monkeypatch, tmp_path
):
    def effect():
        raise KeyboardInterrupt

    runner, args, calls = capture_command(monkeypatch, tmp_path, "drain", effect)
    with pytest.raises(KeyboardInterrupt):
        runner.execute(args, argparse.ArgumentParser())
    assert calls == ["drain"]
    rows = aggregate.preview(installation)
    assert next(row for row in rows if row["metric"] == "outcomes")["bucket"] == "cancelled"
