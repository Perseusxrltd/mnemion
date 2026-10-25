"""Private immutable release output, retention and malformed-data exclusion."""

from copy import deepcopy
from contextlib import closing
from itertools import product
import json
import os
import sqlite3
import time

import pytest

from mnemion.product_telemetry import wire
from mnemion.product_telemetry.collector import Collector
from mnemion.product_telemetry.publication import ReportStore, validate
from mnemion.product_telemetry.reporting import AggregateWindow


@pytest.fixture
def summary():
    window = AggregateWindow(2900)
    for _ in range(64):
        for column, coin in product(range(16), range(4)):
            draws = iter((column, coin))
            assert window.contribute(wire.encode(0, 3, random_below=lambda _: next(draws)))
    result = window.seal()
    assert result is not None
    return result


def test_only_validated_closed_aggregates_are_saved_and_an_existing_week_is_immutable(
    tmp_path, summary
):
    def clock():
        return 345600 + 2901 * 604800

    store = ReportStore(tmp_path / "publisher", clock=clock)
    store(summary)
    assert store.reports() == [summary]
    reopened = ReportStore(store.root, clock=clock)
    changed = deepcopy(summary)
    changed["views"][0]["estimates"][3]["fraction"] = 0.99
    with pytest.raises(sqlite3.IntegrityError):
        reopened(changed)
    assert reopened.reports() == [summary]
    with closing(sqlite3.connect(store.path)) as database:
        assert [row[1] for row in database.execute("PRAGMA table_info(reports)")] == [
            "week",
            "body",
        ]
        rows = database.execute("SELECT week, body FROM reports").fetchall()
    assert rows == [(2900, json.dumps(summary, separators=(",", ":")))]
    assert store.path.stat().st_size <= 1024 * 1024
    if os.name != "nt":
        assert store.path.stat().st_mode & 0o077 == 0
        assert store.root.stat().st_mode & 0o077 == 0


def test_expiry_survives_restart_and_runs_at_a_boundary_without_a_qualifying_new_window(
    tmp_path, summary
):
    current = [345600 + 2901 * 604800]
    store = ReportStore(tmp_path / "publisher", clock=lambda: current[0])
    for week in range(2900, 2909):
        current[0] = 345600 + (week + 1) * 604800
        value = deepcopy(summary)
        value["window_week"] = week
        store(value)
    assert [item["window_week"] for item in store.reports()] == list(range(2901, 2909))
    reopened = ReportStore(store.root, clock=lambda: current[0])
    app = Collector(reopened, clock=lambda: current[0])
    current[0] += 604800 * 10
    assert app._advance()
    with closing(sqlite3.connect(store.path)) as database:
        assert database.execute("SELECT count(*) FROM reports").fetchone()[0] == 0
    assert reopened.reports() == []


def test_busy_publisher_drops_without_waiting_or_replacing_the_prior_window(tmp_path, summary):
    store = ReportStore(tmp_path / "publisher", clock=lambda: 345600 + 2902 * 604800)
    store(summary)
    next_window = deepcopy(summary)
    next_window["window_week"] += 1
    with closing(sqlite3.connect(store.path, isolation_level=None)) as writer:
        writer.execute("BEGIN IMMEDIATE")
        before = time.monotonic()
        with pytest.raises(sqlite3.OperationalError):
            store(next_window)
        assert time.monotonic() - before < 0.25
        writer.rollback()
    assert store.reports() == [summary]


@pytest.mark.parametrize(
    "damage",
    [
        "extra",
        "label",
        "view_state",
        "estimate_state",
        "nan",
        "huge",
        "unknown_count",
        "boolean_interval",
    ],
)
def test_private_text_extra_fields_and_nonfinite_numbers_never_enter_publisher_storage(
    tmp_path, summary, damage
):
    store = ReportStore(tmp_path / "publisher", clock=lambda: 345600 + 2901 * 604800)
    value = deepcopy(summary)
    cell = value["views"][0]["estimates"][3]
    if damage == "extra":
        value["source"] = "PRIVATE_RAW_CONTEXT"
    elif damage == "label":
        cell["value"] = "PRIVATE_WORKSPACE"
    elif damage == "view_state":
        value["views"][0]["state"] = {"private": "PRIVATE_VALUE"}
    elif damage == "estimate_state":
        cell["state"] = ["PRIVATE_VALUE"]
    elif damage == "nan":
        cell["fraction"] = float("nan")
    elif damage == "huge":
        cell["fraction"] = 10**1000
    elif damage == "boolean_interval":
        cell["interval"][0] = False
    else:
        value["views"][1]["report_range"] = {"minimum": 1, "maximum_exclusive": 2}
    with pytest.raises(wire.WireError, match="^telemetry_invalid_report$"):
        store(value)
    assert store.reports() == []
    assert b"PRIVATE" not in store.path.read_bytes()


def test_publisher_refuses_an_unclosed_week_or_an_unsafe_path(tmp_path, summary):
    store = ReportStore(tmp_path / "publisher", clock=lambda: 345600 + 2900 * 604800)
    assert validate(summary) is summary
    with pytest.raises(wire.WireError):
        store(summary)
    assert store.reports() == []
    if os.name != "nt":
        (tmp_path / "redirect").symlink_to(store.root, target_is_directory=True)
        with pytest.raises(wire.WireError):
            ReportStore(tmp_path / "redirect")


def test_legacy_report_bodies_remain_immutable_and_readable_alongside_volume_reports(
    tmp_path, summary
):
    def clock():
        return 345600 + 2901 * 604800

    store = ReportStore(tmp_path / "publisher", clock=clock)
    legacy = deepcopy(summary)
    legacy["schema_version"] = 1
    legacy["window_week"] = 2899
    del legacy["report_range"]
    # Preserve the old body's bytes, including its original formatting. A read
    # must not synthesize a volume count or migrate this immutable closed week.
    original = json.dumps(legacy, indent=2)
    with closing(sqlite3.connect(store.path)) as database:
        database.execute("INSERT INTO reports VALUES (?, ?)", (2899, original))
        database.commit()
    store(summary)
    reopened = ReportStore(store.root, clock=clock)
    assert reopened.reports() == [legacy, summary]
    with closing(sqlite3.connect(store.path)) as database:
        assert (
            database.execute("SELECT body FROM reports WHERE week=2899").fetchone()[0] == original
        )
    assert "report_range" not in reopened.reports()[0]


@pytest.mark.parametrize(
    "bounds",
    [
        None,
        {"minimum": True, "maximum_exclusive": 128},
        {"minimum": 32, "maximum_exclusive": 64},
        {"minimum": 65, "maximum_exclusive": 130},
        {"minimum": 64, "maximum_exclusive": 4096},
        {"minimum": 64, "maximum_exclusive": 128, "source": "PRIVATE_CONTEXT"},
        {"minimum": 64, "maximum_exclusive": 128},  # Too few for the reported view.
        {"minimum": 2**24, "maximum_exclusive": 2**25},
    ],
)
def test_invalid_or_inconsistent_volume_never_enters_retained_reports(tmp_path, summary, bounds):
    store = ReportStore(tmp_path / "publisher", clock=lambda: 345600 + 2901 * 604800)
    value = deepcopy(summary)
    value["report_range"] = bounds
    with pytest.raises(wire.WireError):
        store(value)
    assert store.reports() == []
    assert b"PRIVATE_CONTEXT" not in store.path.read_bytes()


def test_total_cannot_claim_more_reports_than_its_suppressed_views_allow(summary):
    for item in summary["views"]:
        item.update(state="insufficient_reports", report_range=None, estimates=None)
    summary["report_range"] = {"minimum": 131072, "maximum_exclusive": 262144}
    with pytest.raises(wire.WireError):
        validate(summary)
