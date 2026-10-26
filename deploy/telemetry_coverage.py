"""Generate the read-only telemetry coverage view from reviewed source maps.

This describes declared source boundaries, not installation activity, complete
sensor coverage, or permission to collect. No operational state is an input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .telemetry_actions import build as action_coverage


INPUTS = (
    "catalog.json",
    "control-origins.json",
    "desktop-origins.json",
    "studio-methods.json",
    "ui-origins.json",
    "mcp-origins.json",
    "maintenance-origins.json",
)
OUTPUT = Path("mnemion/product_telemetry/workflow-coverage.json")
OWNERS = {
    "control_cli": "Local command line",
    "native_commands": "Native app and agent commands",
    "studio_actions": "Studio app actions",
    "browser_connections": "Browser connection controls",
    "legacy_ui": "Legacy app actions",
    "local_stdio": "Local stdio agents",
    "local_maintenance": "Local source and updater work",
    "headless_controls": "Standalone capture controls",
    "headless_models": "Local model preparation",
}


def build(root: Path) -> dict:
    directory = root / OUTPUT.parent
    raw = {name: (directory / name).read_bytes() for name in INPUTS}
    documents = {name: json.loads(data) for name, data in raw.items()}
    if any(document.get("version") != 1 for document in documents.values()):
        raise ValueError("Review coverage generation for the new telemetry map version")
    catalog = documents["catalog.json"]
    workflows = {
        f"{family}.{operation}": set()
        for family, operations in catalog["workflows"].items()
        for operation in operations
    }

    def add(owner: str, entry: dict) -> None:
        if "exclusion" in entry:
            if "workflow" in entry or "variants" in entry:
                raise ValueError("A telemetry origin cannot be both mapped and excluded")
            return
        names = entry.get("variants", {}).values() if "variants" in entry else [entry["workflow"]]
        for name in names:
            if name not in workflows:
                raise ValueError("A telemetry origin references an unknown workflow")
            workflows[name].add(owner)

    controls = documents["control-origins.json"]["operations"]
    for entry in controls.values():
        add("control_cli", entry)
    for entry in documents["desktop-origins.json"]["operations"].values():
        add("native_commands", entry)
    for operation in documents["studio-methods.json"]["methods"].values():
        if operation in controls:
            add("studio_actions", controls[operation])
    ui = documents["ui-origins.json"]
    for group, owner in (("browser", "browser_connections"), ("legacy", "legacy_ui")):
        for entry in ui[group].values():
            add(owner, entry)
    mcp = documents["mcp-origins.json"]
    for group in ("gateway", "legacy"):
        for entry in mcp[group].values():
            if entry.get("control") is True:
                # The read/write gateways delegate to the same reviewed control
                # map. Their aliases do not become another telemetry owner.
                for control in controls.values():
                    add("local_stdio", control)
            else:
                add("local_stdio", entry)
    for entry in documents["maintenance-origins.json"]["origins"].values():
        add("local_maintenance", entry)
    for entry in documents["maintenance-origins.json"]["capture_controls"].values():
        add("headless_controls", entry)
    for entry in documents["maintenance-origins.json"]["model_preparation"].values():
        add("headless_models", entry)

    rows = [
        {
            "workflow": name,
            "state": "mapped" if owners else "unmeasured",
            "owners": [owner for owner in OWNERS if owner in owners],
        }
        for name, owners in workflows.items()
    ]
    mapped = sum(row["state"] == "mapped" for row in rows)
    actions, action_inputs = action_coverage(root, documents)
    return {
        "schema_version": 1,
        "catalog_version": catalog["version"],
        "scope": "declared_source_boundaries",
        "qualification": (
            "Mapped categories have a declared source boundary; they are not guaranteed "
            "on every screen or client. Unmeasured categories have no current mapped "
            "boundary. Neither state grants collection permission or qualifies sensors, "
            "delivery, anonymity or a release."
        ),
        "summary": {"total": len(rows), "mapped": mapped, "unmeasured": len(rows) - mapped},
        "owners": OWNERS,
        "workflows": rows,
        "action_coverage": actions,
        "source_inputs": {
            **{name: hashlib.sha256(data).hexdigest() for name, data in raw.items()},
            **action_inputs,
        },
    }


def render(root: Path) -> str:
    return json.dumps(build(root), indent=2, ensure_ascii=False) + "\n"


def verify(root: Path) -> None:
    expected = render(root)
    try:
        current = (root / OUTPUT).read_text(encoding="utf-8")
    except FileNotFoundError:
        current = None
    if current != expected:
        raise ValueError(
            "Telemetry coverage is stale; run python -m deploy.telemetry_coverage --write"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.write:
        (root / OUTPUT).write_text(render(root), encoding="utf-8")
    else:
        verify(root)
    print(json.dumps({"telemetry_coverage": build(root)["summary"], "written": args.write}))


if __name__ == "__main__":
    main()
