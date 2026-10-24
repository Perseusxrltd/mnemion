"""Privacy, contribution limits and real SQLite fences for local aggregation."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys

import pytest

from mnemion.product_telemetry import aggregate, catalog, policy


@pytest.fixture
def enabled(tmp_path, monkeypatch):
    root, company = tmp_path / "installation", tmp_path / "company.json"
    monkeypatch.setattr(policy, "company_policy_file", lambda: company)
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/telemetry")
    monkeypatch.setattr(aggregate, "_day", lambda: 20000)
    current = policy.configure(
        root, {"enabled": True, "expected_revision": 0, "disclosure_version": 1}
    )
    return root, company, current["revision"], current["store_generation"]


def observation(**extra):
    return {
        "kind": "outcome",
        "workflow": "memory.recall",
        "surface": "headless",
        "outcome": "success",
        **extra,
    }


def test_inactive_build_does_not_touch_disk_or_read_private_inputs(tmp_path):
    assert not policy.COLLECTION_AVAILABLE
    root = tmp_path / "absent"
    assert aggregate.record(root, {"secret": "PRIVATE_SENTINEL"}, expected_revision=0) is False
    assert not root.exists()


def test_every_catalog_workflow_has_nonoverlapping_decodable_cells():
    seen = set()
    for workflow in catalog.WORKFLOWS:
        for surface in catalog.SURFACES:
            _, cells = catalog.observation(
                {"kind": "submission", "workflow": workflow, "surface": surface}
            )
            assert not seen.intersection(cells)
            seen.update(cells)
            assert catalog.describe(cells[0]) == {
                "workflow": workflow,
                "surface": surface,
                "metric": "submissions",
                "group": "usage",
            }
            family = workflow.split(".")[0]
            for name, spec in catalog.METRICS.items():
                if spec["families"] == "all" or family in spec["families"]:
                    for value in [0, *spec["upper_bounds"], catalog.MAX_PRIMITIVE]:
                        _, measured = catalog.observation(
                            observation(workflow=workflow, surface=surface, **{name: value})
                        )
                        assert catalog.describe(measured[-1])["metric"] == name
    for name, spec in catalog.RESOURCE_METRICS.items():
        for value in [0, *spec["upper_bounds"], catalog.MAX_PRIMITIVE]:
            _, cells = catalog.observation({"kind": "resource", "metric": name, "value": value})
            assert not seen.intersection(cells)
            assert catalog.describe(cells[0])["metric"] == name


@pytest.mark.parametrize(
    "bad",
    [
        True,
        None,
        -1,
        float("nan"),
        float("inf"),
        10**1000,
        "PRIVATE_SENTINEL",
        {"secret": "PRIVATE_SENTINEL"},
    ],
)
def test_non_numeric_unbounded_or_private_sensor_is_rejected(enabled, bad):
    root, _, revision, generation = enabled
    value = observation(latency_ms=bad)
    with pytest.raises(catalog.MeasurementError, match="^telemetry_invalid_measurement$"):
        catalog.observation(value)
    assert (
        aggregate.record(root, value, expected_revision=revision, expected_generation=generation)
        is False
    )
    assert aggregate.preview(root) == []


def test_content_and_vault_sizes_never_enter_store(enabled):
    root, _, revision, generation = enabled
    for value in [
        observation(query="PRIVATE_SENTINEL"),
        observation(workflow="PRIVATE_SENTINEL"),
        observation(reason="PRIVATE_SENTINEL"),
        observation(workflow="vault.read", result_items=12345),
        observation(workflow="vault.write", payload_bytes_sent=12345),
    ]:
        assert (
            aggregate.record(
                root, value, expected_revision=revision, expected_generation=generation
            )
            is False
        )
    assert b"PRIVATE_SENTINEL" not in (root / policy.DATABASE_NAME).read_bytes()
    assert aggregate.preview(root) == []


def test_clips_numbers_and_retains_only_fixed_buckets(enabled):
    root, _, revision, generation = enabled
    assert aggregate.record(
        root,
        observation(latency_ms=123.456, result_items=37),
        expected_revision=revision,
        expected_generation=generation,
    )
    rows = aggregate.preview(root)
    assert len(rows) == 3
    assert all(row["count"] == 1 for row in rows)
    assert {row["metric"] for row in rows} == {"outcomes", "latency_ms", "result_items"}
    assert next(row for row in rows if row["metric"] == "latency_ms")["bucket"] == 2
    assert next(row for row in rows if row["metric"] == "result_items")["bucket"] == 3
    assert "123.456" not in json.dumps(rows)
    with sqlite3.connect(root / policy.DATABASE_NAME) as connection:
        for row in connection.execute("SELECT * FROM pending"):
            assert all(type(value) is int for value in row)


def test_daily_contribution_and_resource_limits_do_not_build_event_history(enabled, monkeypatch):
    root, _, revision, generation = enabled
    outcomes = [
        aggregate.record(
            root, observation(), expected_revision=revision, expected_generation=generation
        )
        for _ in range(80)
    ]
    assert sum(outcomes) == 64
    resource = {"kind": "resource", "metric": "rss_bytes", "value": 1024**3}
    assert (
        sum(
            aggregate.record(
                root, resource, expected_revision=revision, expected_generation=generation
            )
            for _ in range(30)
        )
        == 24
    )
    assert len(aggregate.preview(root)) == 2
    monkeypatch.setattr(aggregate, "_day", lambda: 20001)
    assert aggregate.record(
        root, observation(), expected_revision=revision, expected_generation=generation
    )
    assert next(row for row in aggregate.preview(root) if row["metric"] == "outcomes")["count"] == 1
    monkeypatch.setattr(aggregate, "_day", lambda: 20003)
    assert aggregate.preview(root) == []
    assert aggregate.record(
        root, observation(), expected_revision=revision, expected_generation=generation
    )
    assert len(aggregate.preview(root)) == 1


def test_opt_out_then_reenable_fences_an_old_native_process(enabled):
    root, _, revision, generation = enabled
    assert aggregate.record(
        root, observation(), expected_revision=revision, expected_generation=generation
    )
    disabled = policy.configure(root, {"enabled": False, "expected_revision": revision})
    assert disabled["pending_records"] == 0
    enabled_again = policy.configure(
        root,
        {
            "enabled": True,
            "expected_revision": disabled["revision"],
            "expected_generation": generation,
            "disclosure_version": 1,
        },
    )
    assert enabled_again["pending_records"] == 0
    # A genuinely separate old worker, with a stale captured policy revision.
    program = """
import json,sys
from pathlib import Path
from mnemion.product_telemetry import policy,aggregate
policy.COLLECTION_AVAILABLE=True
policy.COLLECTOR_URL='https://example.invalid/telemetry'
request=json.load(sys.stdin)
print(aggregate.record(Path(request['root']),request['value'],expected_revision=request['revision'],expected_generation=request['generation']))
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        input=json.dumps(
            {
                "root": str(root),
                "revision": revision,
                "generation": generation,
                "value": observation(),
            }
        ),
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    assert result.stdout.strip() == "False"
    assert result.stderr == ""
    assert aggregate.preview(root) == []
    assert aggregate.record(
        root,
        observation(),
        expected_revision=enabled_again["revision"],
        expected_generation=enabled_again["store_generation"],
    )


def test_company_narrowing_removes_disallowed_groups_and_unknown_policy_suppresses(enabled):
    root, company, revision, generation = enabled
    assert aggregate.record(
        root, observation(latency_ms=12), expected_revision=revision, expected_generation=generation
    )
    company.write_text(
        json.dumps({"schema_version": 1, "enabled": True, "metric_groups": ["usage"]})
    )
    assert aggregate.record(
        root, observation(latency_ms=99), expected_revision=revision, expected_generation=generation
    )
    assert {row["group"] for row in aggregate.preview(root)} == {"usage"}
    with sqlite3.connect(root / policy.DATABASE_NAME) as connection:
        assert connection.execute("SELECT count(*) FROM pending").fetchone()[0] == 1
    company.write_text('{"secret":"PRIVATE_SENTINEL"}')
    assert (
        aggregate.record(
            root, observation(), expected_revision=revision, expected_generation=generation
        )
        is False
    )
    assert policy.status(root)["pending_records"] == 0


def test_full_queue_accepts_existing_cells_and_drops_new_cells_without_growth(enabled):
    root, _, revision, generation = enabled
    cells = []
    for workflow in catalog.WORKFLOWS:
        for surface in catalog.SURFACES:
            for outcome in catalog.OUTCOMES:
                _, encoded = catalog.observation(
                    observation(workflow=workflow, surface=surface, outcome=outcome)
                )
                cells.append(encoded[0])
    with sqlite3.connect(root / policy.DATABASE_NAME) as connection:
        connection.executemany(
            "INSERT INTO pending VALUES (?, 1, 20000)", [(cell,) for cell in cells[:512]]
        )
    assert policy.status(root)["pending_records"] == 512
    assert aggregate.record(
        root,
        observation(workflow=catalog.WORKFLOWS[0], surface="desktop"),
        expected_revision=revision,
        expected_generation=generation,
    )
    assert (
        aggregate.record(
            root,
            observation(workflow="vault.read"),
            expected_revision=revision,
            expected_generation=generation,
        )
        is False
    )
    assert policy.status(root)["pending_records"] == 512
    assert (root / policy.DATABASE_NAME).stat().st_size <= policy.MAX_DATABASE_BYTES
    assert not (root / (policy.DATABASE_NAME + "-wal")).exists()
    policy.configure(root, {"enabled": False, "expected_revision": revision})
    with sqlite3.connect(root / policy.DATABASE_NAME) as connection:
        assert connection.execute("SELECT count(*) FROM pending").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM producer_budget").fetchone()[0] == 0


def test_busy_store_never_blocks_canonical_work_or_records(enabled):
    root, _, revision, generation = enabled
    with sqlite3.connect(root / policy.DATABASE_NAME) as other:
        other.execute("BEGIN IMMEDIATE")
        assert (
            aggregate.record(
                root, observation(), expected_revision=revision, expected_generation=generation
            )
            is False
        )
        other.rollback()
    assert aggregate.preview(root) == []


def test_source_controls_store_upgrades_without_losing_explicit_opt_out(enabled):
    root, _, revision, generation = enabled
    disabled = policy.configure(root, {"enabled": False, "expected_revision": revision})
    with sqlite3.connect(root / policy.DATABASE_NAME) as connection:
        connection.execute("DROP TRIGGER producer_budget_bound")
        connection.execute("DROP TABLE producer_budget")
        connection.execute("ALTER TABLE preferences DROP COLUMN store_generation")
        connection.execute("PRAGMA user_version=1")
    assert policy.status(root)["reason"] == "user_disabled"
    assert (
        aggregate.record(
            root,
            observation(),
            expected_revision=disabled["revision"],
            expected_generation=generation,
        )
        is False
    )
    policy.configure(root, {"enabled": False, "expected_revision": disabled["revision"]})
    with sqlite3.connect(root / policy.DATABASE_NAME) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
    assert policy.status(root)["reason"] == "user_disabled"


def test_recreated_store_rejects_old_work_even_when_revision_numbers_repeat(enabled):
    root, _, revision, generation = enabled
    assert aggregate.record(
        root, observation(), expected_revision=revision, expected_generation=generation
    )
    (root / policy.DATABASE_NAME).unlink()
    assert policy.status(root)["store_generation"] is None
    fresh = policy.configure(
        root,
        {
            "enabled": True,
            "expected_revision": 0,
            "expected_generation": None,
            "disclosure_version": 1,
        },
    )
    assert fresh["revision"] == revision
    assert fresh["store_generation"] != generation
    assert (
        aggregate.record(
            root, observation(), expected_revision=revision, expected_generation=generation
        )
        is False
    )
    assert aggregate.preview(root) == []
    with pytest.raises(policy.PolicyError, match="telemetry_choice_changed"):
        policy.configure(
            root,
            {
                "enabled": True,
                "expected_revision": revision,
                "expected_generation": generation,
                "disclosure_version": 1,
            },
        )
    assert aggregate.record(
        root,
        observation(),
        expected_revision=fresh["revision"],
        expected_generation=fresh["store_generation"],
    )
    # The nonce controls local policy. It never enters measurement cells.
    assert generation not in json.dumps(aggregate.preview(root))
    assert fresh["store_generation"] not in json.dumps(aggregate.preview(root))
