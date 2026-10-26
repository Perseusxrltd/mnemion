"""The public coverage inventory must not overstate source instrumentation."""

import json
from pathlib import Path
import shutil

import pytest

from deploy import telemetry_actions, telemetry_coverage
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
    for name in telemetry_actions.INPUTS:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
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


def test_missing_action_stays_visible_when_other_sources_cover_the_category(source_maps):
    root, directory = source_maps
    path = directory / "control-origins.json"
    document = json.loads(path.read_text())
    action = next(
        name
        for name, entry in document["operations"].items()
        if entry.get("workflow") == "memory.recall"
    )
    del document["operations"][action]
    path.write_text(json.dumps(document))
    coverage = telemetry_coverage.build(root)
    category = next(row for row in coverage["workflows"] if row["workflow"] == "memory.recall")
    assert category["state"] == "mapped"
    row = next(
        row
        for row in coverage["action_coverage"]["actions"]
        if row["owner"] == "control_cli" and row["action"] == action
    )
    assert row == {"owner": "control_cli", "action": action, "state": "unmeasured", "workflows": []}
    with pytest.raises(ValueError, match="Telemetry coverage is stale"):
        telemetry_coverage.verify(root)


def test_future_interface_action_is_not_hidden_or_given_an_invented_workflow(source_maps):
    root, directory = source_maps
    path = root / "studio/electron/desktop-actions.ts"
    path.write_text(
        path.read_text().replace(
            "} as const",
            "  'future.action': { workspace: false, mutation: true, fields: [] },\n} as const",
            1,
        )
    )
    coverage = telemetry_coverage.build(root)
    assert {
        "owner": "native_commands",
        "action": "future.action",
        "state": "unmeasured",
        "workflows": [],
    } in coverage["action_coverage"]["actions"]
    assert coverage["summary"] == {"total": 94, "mapped": 87, "unmeasured": 7}
    with pytest.raises(ValueError, match="Telemetry coverage is stale"):
        telemetry_coverage.verify(root)
    # An unfinished selector declaration cannot make a known action disappear.
    path = directory / "desktop-origins.json"
    document = json.loads(path.read_text())
    document["operations"]["future.action"] = {"variants": {}, "selector": "enabled"}
    path.write_text(json.dumps(document))
    future = next(
        row
        for row in telemetry_coverage.build(root)["action_coverage"]["actions"]
        if row["action"] == "future.action"
    )
    assert future["state"] == "unmeasured" and future["workflows"] == []


def test_action_exclusions_and_delegation_remain_distinct_bounded_metadata():
    from mnemion.product_telemetry import cli

    coverage = catalog.coverage_specification()
    actions = coverage["action_coverage"]
    rows = actions["actions"]
    assert (
        next(
            row
            for row in rows
            if row["owner"] == "native_commands" and row["action"] == "telemetry.configure"
        )["state"]
        == "excluded"
    )
    assert (
        next(
            row
            for row in rows
            if row["owner"] == "local_stdio" and row["action"] == "gateway.mnemion_read"
        )["delegate"]
        == "control_cli"
    )
    assert all(row["reason"] in actions["reasons"] for row in rows if "reason" in row)
    assert all(workflow in catalog.WORKFLOWS for row in rows for workflow in row["workflows"])
    assert sum(
        actions["summary"][state] for state in ("mapped", "excluded", "delegated", "unmeasured")
    ) == len(rows)
    assert len(json.dumps(actions).encode()) <= 128 * 1024
    assert len(json.dumps(cli.execute(None, {"action": "schema"})).encode()) < 256 * 1024
