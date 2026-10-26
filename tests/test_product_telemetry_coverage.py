"""The public coverage inventory must not overstate source instrumentation."""

import json
from pathlib import Path
import shutil

import pytest

from deploy import telemetry_coverage
from mnemion.product_telemetry import catalog


ROOT = Path(__file__).resolve().parents[1]


def test_published_inventory_matches_sources_and_keeps_unmeasured_categories_visible():
    telemetry_coverage.verify(ROOT)
    coverage = catalog.coverage_specification()
    assert coverage["scope"] == "declared_source_boundaries"
    assert coverage["summary"] == {"total": 94, "mapped": 87, "unmeasured": 7}
    assert [row["workflow"] for row in coverage["workflows"]] == list(catalog.WORKFLOWS)
    rows = {row["workflow"]: row for row in coverage["workflows"]}
    assert rows["memory.recall"]["state"] == "mapped"
    assert "studio_actions" in rows["memory.recall"]["owners"]
    assert rows["update.verify"] == {
        "workflow": "update.verify",
        "state": "unmeasured",
        "owners": [],
    }
    assert rows["backup.list"]["state"] == "unmeasured"
    assert "headless_controls" in rows["capture.drain"]["owners"]
    assert rows["models.prepare"]["owners"] == ["headless_models"]
    # Reading static disclosure data does not retain a caller's modifications.
    rows["memory.recall"]["owners"].clear()
    assert catalog.coverage_specification() != coverage


@pytest.fixture
def source_maps(tmp_path):
    directory = tmp_path / telemetry_coverage.OUTPUT.parent
    directory.mkdir(parents=True)
    for name in (*telemetry_coverage.INPUTS, telemetry_coverage.OUTPUT.name):
        shutil.copyfile(ROOT / telemetry_coverage.OUTPUT.parent / name, directory / name)
    return tmp_path, directory


def test_new_catalog_entry_stays_unmeasured_and_blocks_a_stale_release(source_maps):
    root, directory = source_maps
    path = directory / "catalog.json"
    document = json.loads(path.read_text())
    document["workflows"]["workspace"].append("future_action")
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="Telemetry coverage is stale"):
        telemetry_coverage.verify(root)
    rows = telemetry_coverage.build(root)["workflows"]
    assert next(row for row in rows if row["workflow"] == "workspace.future_action") == {
        "workflow": "workspace.future_action",
        "state": "unmeasured",
        "owners": [],
    }


def test_removed_origin_does_not_keep_its_old_coverage_claim(source_maps):
    root, directory = source_maps
    path = directory / "desktop-origins.json"
    document = json.loads(path.read_text())
    document["operations"]["host.create"] = {"exclusion": "state_inspection"}
    path.write_text(json.dumps(document))
    coverage = telemetry_coverage.build(root)
    row = next(row for row in coverage["workflows"] if row["workflow"] == "host.adopt")
    assert row["state"] == "unmeasured" and row["owners"] == []
    with pytest.raises(ValueError, match="Telemetry coverage is stale"):
        telemetry_coverage.verify(root)


def test_unknown_selector_workflow_cannot_become_a_coverage_claim(source_maps):
    root, directory = source_maps
    path = directory / "desktop-origins.json"
    document = json.loads(path.read_text())
    document["operations"]["host.request"]["variants"]["backup.verify"] = "unknown.workflow"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="unknown workflow"):
        telemetry_coverage.build(root)
