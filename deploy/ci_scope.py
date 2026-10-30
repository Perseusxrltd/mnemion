"""Select reviewed push checks; releases and unknown changes keep the full matrix."""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

METADATA = {
    "deploy/issue-releases.json",
    "deploy/maintenance-status.json",
    "deploy/published-release.json",
    "deploy/release-status.json",
    "deploy/research-watch.json",
    "deploy/website-content.json",
    "docs/website/content.json",
    "docs/website/content.schema.json",
}

# These files only prepare or run separately dispatched diagnostics. No
# application/release builder imports them. Keep this explicit: runtime,
# release workflows and unknown files still run all checks.
RENDERER_DIAGNOSTICS = {
    ".github/workflows/telemetry-browser-journeys.yml",
    ".github/workflows/telemetry-renderer.yml",
    "deploy/probe_telemetry_browser.mjs",
    "deploy/probe_telemetry_browser.py",
    "deploy/probe_telemetry_renderer.py",
    "deploy/report_telemetry_renderer.py",
    "deploy/telemetry_memory_fixture.py",
    "studio/electron/scripts/probe-telemetry-renderer.mjs",
    "studio/frontend/scripts/build-telemetry-probe.mjs",
    "tests/test_telemetry_browser_journey.py",
}

# Only these existing component boundaries may use telemetry push checks.
# Unknown files, shared app/service code, dependencies, release routes,
# disclosure activation and wire/catalog definitions still run the full matrix.
# This is a fixed source allowlist, never a directory scan of the changed tree.
TELEMETRY_COMPONENTS = {
    "mnemion/product_telemetry": {
        "activity.py",
        "aggregate.py",
        "catalog.py",
        "cli.py",
        "conditions.py",
        "delivery.py",
        "inspection.py",
        "network.py",
        "network_system.py",
        "policy.py",
        "review.py",
        "review_clock.py",
        "review_clock_system.py",
        "review_storage.py",
        "transport.py",
        "workflow.py",
        "workflow-coverage.json",
    },
    "studio/electron": {
        "telemetry-activity.ts",
        "telemetry-catalog.ts",
        "telemetry-conditions.ts",
        "telemetry-cpu.ts",
        "telemetry-delivery.ts",
        "telemetry-network.ts",
        "telemetry-owner.ts",
        "telemetry-private-store.ts",
        "telemetry-resources.ts",
        "telemetry-review.ts",
        "telemetry-review-clock.ts",
        "telemetry-review-lifetime.ts",
        "telemetry-store.ts",
        "telemetry-transport.ts",
        "telemetry-workflow.ts",
    },
    "studio/frontend/src/workspace": {
        "telemetry-activity.ts",
        "telemetry-aggregate.ts",
        "telemetry-budget.ts",
        "telemetry-capability.ts",
        "telemetry-company.ts",
        "telemetry-conditions.ts",
        "telemetry-delivery.ts",
        "telemetry-policy.ts",
        "telemetry-refusals.ts",
        "telemetry-review.ts",
        "telemetry-review-clock.ts",
        "telemetry-setup.ts",
        "telemetry-transport.ts",
    },
    "studio/electron/scripts": {
        "test-product-telemetry.mjs",
        "test-telemetry-cold-start.mjs",
        "test-telemetry-delivery.mjs",
        "test-telemetry-network.mjs",
        "test-telemetry-owner.mjs",
        "test-telemetry-private-store.mjs",
        "test-telemetry-resources.mjs",
        "test-telemetry-store.mjs",
        "test-telemetry-transport.mjs",
        "test-telemetry-wire.mjs",
    },
    "studio/frontend/scripts": {
        "test-product-telemetry.mjs",
        "test-telemetry-activity.mjs",
        "test-telemetry-client.mjs",
        "test-telemetry-conditions.mjs",
        "test-telemetry-delivery.mjs",
        "test-telemetry-inspection.mjs",
        "test-telemetry-review-clock.mjs",
    },
    "tests": {
        "test_product_telemetry_aggregate.py",
        "test_product_telemetry_classic_cli.py",
        "test_product_telemetry_coverage.py",
        "test_product_telemetry_delivery.py",
        "test_product_telemetry_endpoint.py",
        "test_product_telemetry_inspection.py",
        "test_product_telemetry_maintenance.py",
        "test_product_telemetry_mcp.py",
        "test_product_telemetry_mcp_inventory.py",
        "test_product_telemetry_network.py",
        "test_product_telemetry_network_system.py",
        "test_product_telemetry_policy.py",
        "test_product_telemetry_preview.py",
        "test_product_telemetry_privacy_attacks.py",
        "test_product_telemetry_review_clock_system.py",
        "test_product_telemetry_review_lifetime.py",
        "test_product_telemetry_transport.py",
        "test_product_telemetry_wire.py",
        "test_product_telemetry_workflows.py",
    },
}
TELEMETRY_PATHS = {
    f"{directory}/{name}" for directory, names in TELEMETRY_COMPONENTS.items() for name in names
}


def documentation(path: str) -> bool:
    parts = PurePosixPath(path).parts
    if not parts or path.startswith("/") or ".." in parts:
        return False
    return (
        path in METADATA
        or (len(parts) == 1 and path.endswith(".md"))
        or (parts[0] == "docs" and path.endswith(".md"))
        # Dated acceptance reports and fixed release receipts accompany guides;
        # schemas, nested fixtures and unknown JSON retain runtime checks.
        # Releases always do.
        or bool(re.fullmatch(r"docs/validation/\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9_.-]*\.json", path))
        or bool(
            re.fullmatch(
                r"docs/validation/releases/\d+\.\d+\.\d+-(?:status|publication|artifacts)\.json",
                path,
            )
        )
    )


def scope(root: Path, event: dict, *, event_name: str, release: bool = False) -> dict:
    if release or event_name != "push":
        return {"runtime": True, "reason": "release_or_non_push"}
    before, after = event.get("before"), event.get("after")
    if any(
        not isinstance(value, str) or not re.fullmatch("[0-9a-f]{40}", value) or value == "0" * 40
        for value in (before, after)
    ):
        return {"runtime": True, "reason": "missing_revision"}
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, timeout=10, text=True
        ).strip()
        if head != after:
            return {"runtime": True, "reason": "different_checkout"}
        result = subprocess.run(
            ["git", "diff", "--no-renames", "--name-only", "-z", before, after, "--"],
            cwd=root,
            capture_output=True,
            timeout=15,
            check=True,
        )
        paths = result.stdout.decode("utf-8").rstrip("\0").split("\0")
    except (OSError, subprocess.SubprocessError, UnicodeError):
        # A shallow checkout or unavailable push base must retain every check.
        return {"runtime": True, "reason": "unavailable_diff"}
    only_docs = bool(paths) and all(documentation(path) for path in paths)
    only_diagnostics = bool(paths) and all(
        documentation(path) or path in RENDERER_DIAGNOSTICS for path in paths
    )
    if (
        not only_diagnostics
        and paths
        and all(documentation(path) or path in TELEMETRY_PATHS for path in paths)
    ):
        return {"runtime": False, "telemetry": True, "reason": "telemetry_components_only"}
    return {
        "runtime": not only_diagnostics,
        "reason": "documentation_only"
        if only_docs
        else "diagnostic_only"
        if only_diagnostics
        else "runtime_or_unknown_files",
    }


def main() -> None:
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        if not isinstance(event, dict):
            raise ValueError("Invalid event")
    except (KeyError, OSError, ValueError):
        event = {}
    result = scope(
        Path.cwd(),
        event,
        event_name=os.environ.get("GITHUB_EVENT_NAME", ""),
        release=os.environ.get("MNEMION_CI_RELEASE", "false") != "false",
    )
    print("runtime=" + str(result["runtime"]).lower())
    print("telemetry=" + str(result.get("telemetry", False)).lower())
    print("reason=" + result["reason"])


if __name__ == "__main__":
    main()
