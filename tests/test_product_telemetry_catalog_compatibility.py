"""Saved coordinates and immutable reports survive the first catalog extension."""

from contextlib import closing
from copy import deepcopy
from itertools import product
import json
from pathlib import Path
import sqlite3

import pytest

from mnemion.product_telemetry import catalog, wire
from mnemion.product_telemetry.publication import ReportStore, validate
from mnemion.product_telemetry.reporting import AggregateWindow


FIXTURES = Path(__file__).with_name("fixtures")
LEGACY = json.loads((FIXTURES / "telemetry-catalog-v1.json").read_text())


def test_every_original_coordinate_keeps_its_workflow_surface_and_metric_definition():
    old = LEGACY["catalog"]
    names = [
        f"{family}.{operation}"
        for family, operations in old["workflows"].items()
        for operation in operations
    ]
    assert catalog.WORKFLOWS[:94] == tuple(names)
    assert catalog.WORKFLOWS[94:] == ("capture.split", "models.test")
    for field in ("surfaces", "outcomes", "reasons", "metrics", "resource_metrics", "limits"):
        assert catalog.CATALOG[field] == old[field]
    for position, name in enumerate(names):
        for surface, label in enumerate(old["surfaces"]):
            scope, cells = catalog.observation(
                {"kind": "submission", "workflow": name, "surface": label}
            )
            assert scope == position * 4 + surface
            assert cells == (scope * 128,)
            assert catalog.describe(cells[0]) == {
                "workflow": name,
                "surface": label,
                "metric": "submissions",
                "group": "usage",
            }


def test_old_wire_views_keep_weights_domains_and_every_existing_category_position():
    old = LEGACY["wire"]
    assert wire.WIRE["version"] == old["version"] == 2
    assert wire.WIRE["packet"] == old["packet"]
    assert wire.WIRE["maximum_report_bytes"] == old["maximum_report_bytes"] == 4
    assert len(wire.VIEWS) == len(old["views"])
    for before, after in zip(old["views"], wire.VIEWS, strict=True):
        assert {key: value for key, value in before.items() if key != "values"} == {
            key: value for key, value in after.items() if key != "values"
        }
        assert after["values"][: len(before["values"])] == before["values"]
        if before["name"] != "feature":
            assert after == before
    assert wire.VIEWS[1]["values"][95:] == ["capture.split", "models.test"]
    expected_storage = len(old["views"]) * 8 + sum(view["domain"] * 8 for view in old["views"])
    assert AggregateWindow(2900).storage_bytes == expected_storage


@pytest.mark.parametrize("version", [1, 2, 3])
def test_closed_legacy_feature_reports_remain_byte_preserved_beside_expanded_reports(
    tmp_path, version
):
    previous = json.loads((FIXTURES / "telemetry-feature-report-v3.json").read_text())
    assert len(previous["views"][1]["estimates"]) == 95
    if version < 3:
        del previous["estimation_population"], previous["reviewed_report_use"]
        previous["confidence_assumptions"] = (
            "independent_randomization_by_conforming_senders_not_authenticated_clients_or_poisoning_resistance"
        )
    if version == 1:
        del previous["report_range"]
    previous["schema_version"] = version
    original = json.dumps(previous, indent=2)
    store = ReportStore(tmp_path / "publisher", clock=lambda: 345600 + 2902 * 604800)
    with closing(sqlite3.connect(store.path)) as database:
        database.execute("INSERT INTO reports VALUES (?, ?)", (2900, original))
        database.commit()
    current = AggregateWindow(2901)
    for _ in range(8):
        for column, coin in product(range(128), range(4)):
            draws = iter((column, coin))
            assert current.contribute(wire.encode(1, 96, random_below=lambda _: next(draws)))
    report = current.seal()
    assert report["schema_version"] == 4
    assert report["views"][1]["estimates"][-1]["value"] == "models.test"
    assert report["views"][1]["estimates"][-1]["fraction"] == 1
    store(report)
    reopened = ReportStore(store.root, clock=lambda: 345600 + 2902 * 604800)
    assert reopened.reports() == [previous, report]
    with closing(sqlite3.connect(store.path)) as database:
        assert (
            database.execute("SELECT body FROM reports WHERE week=2900").fetchone()[0] == original
        )
    invalid = deepcopy(report)
    invalid["views"][1]["estimates"] = invalid["views"][1]["estimates"][:95]
    with pytest.raises(wire.WireError):
        validate(invalid)
    expanded_old = deepcopy(previous)
    expanded_old["views"][1]["estimates"].extend(report["views"][1]["estimates"][-2:])
    with pytest.raises(wire.WireError):
        validate(expanded_old)
