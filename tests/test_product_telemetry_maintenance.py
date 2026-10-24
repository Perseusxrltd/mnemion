"""Local work ownership, meaningful-work filtering and coarse process sensors."""

import json
import argparse
from types import SimpleNamespace

import pytest

from mnemion import maintenance_measurement as measured
from mnemion.product_telemetry import aggregate, policy


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "private"
    monkeypatch.setattr(policy, "default_directory", lambda: root)
    monkeypatch.setattr(policy, "company_policy_file", lambda: tmp_path / "absent-company.json")
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/telemetry")
    policy.configure(root, {"enabled": True, "expected_revision": 0, "disclosure_version": 1})
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
