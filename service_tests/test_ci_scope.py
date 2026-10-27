"""Use real Git changes to verify which work may avoid product build queues."""

import subprocess

import pytest

from deploy.ci_scope import TELEMETRY_PATHS, scope


def changed_repository(root, paths):
    def git(*arguments):
        return subprocess.check_output(["git", *arguments], cwd=root, text=True).strip()

    git("init", "-q")
    git("config", "user.name", "Scope fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "commit.gpgsign", "false")
    (root / "README.md").write_text("Fixture\n")
    git("add", ".")
    git("commit", "-qm", "Before")
    before = git("rev-parse", "HEAD")
    for name in paths:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Changed fixture\n")
    git("add", ".")
    git("commit", "-qm", "After")
    return {"before": before, "after": git("rev-parse", "HEAD")}


def test_isolated_renderer_changes_do_not_reserve_product_runners(tmp_path):
    event = changed_repository(
        tmp_path,
        [
            ".github/workflows/telemetry-renderer.yml",
            "deploy/probe_telemetry_renderer.py",
            "docs/check.md",
        ],
    )
    assert scope(tmp_path, event, event_name="push") == {
        "runtime": False,
        "reason": "diagnostic_only",
    }


@pytest.mark.parametrize("path", ["mnemion/service/api.py", ".github/workflows/desktop.yml"])
def test_one_runtime_or_release_change_keeps_all_checks(tmp_path, path):
    event = changed_repository(tmp_path, ["deploy/probe_telemetry_renderer.py", path])
    assert scope(tmp_path, event, event_name="push")["runtime"] is True


def test_release_and_manual_validation_never_skip_diagnostic_only_changes(tmp_path):
    event = changed_repository(tmp_path, ["deploy/report_telemetry_renderer.py"])
    assert scope(tmp_path, event, event_name="push", release=True)["runtime"] is True
    assert scope(tmp_path, event, event_name="workflow_dispatch")["runtime"] is True
    assert scope(tmp_path, event, event_name="pull_request")["runtime"] is True


def test_missing_comparison_history_keeps_all_checks(tmp_path):
    event = changed_repository(tmp_path, ["deploy/probe_telemetry_renderer.py"])
    event["before"] = "1" * 40
    assert scope(tmp_path, event, event_name="push") == {
        "runtime": True,
        "reason": "unavailable_diff",
    }


@pytest.mark.parametrize(
    "path",
    [
        "mnemion/product_telemetry/workflow.py",
        "studio/electron/telemetry-owner.ts",
        "studio/frontend/src/workspace/telemetry-policy.ts",
        "tests/test_product_telemetry_transport.py",
    ],
)
def test_reviewed_components_select_telemetry_checks_only_for_pushes(tmp_path, path):
    event = changed_repository(tmp_path, [path, "docs/telemetry.md"])
    assert scope(tmp_path, event, event_name="push") == {
        "runtime": False,
        "telemetry": True,
        "reason": "telemetry_components_only",
    }
    for event_name, release in [
        ("push", True),
        ("workflow_call", False),
        ("workflow_dispatch", False),
        ("pull_request", False),
    ]:
        selected = scope(tmp_path, event, event_name=event_name, release=release)
        assert selected["runtime"] is True and not selected.get("telemetry", False)


@pytest.mark.parametrize(
    "path",
    [
        "mnemion/cli.py",
        "mnemion/service/api.py",
        "studio/frontend/src/App.tsx",
        "mnemion/product_telemetry/unknown.py",
        "studio/electron/telemetry-new.ts",
        "mnemion/product_telemetry/disclosure.json",
        "mnemion/product_telemetry/transport-route.json",
        "mnemion/product_telemetry/catalog.json",
        "mnemion/product_telemetry/wire-v2.json",
        "pyproject.toml",
        "uv.lock",
        "studio/frontend/package-lock.json",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
        "deploy/ci_scope.py",
    ],
)
def test_telemetry_mixed_with_shared_or_unknown_source_keeps_full_checks(tmp_path, path):
    event = changed_repository(tmp_path, ["mnemion/product_telemetry/workflow.py", path])
    selected = scope(tmp_path, event, event_name="push")
    assert selected["runtime"] is True and not selected.get("telemetry", False)


def test_allowlist_only_names_existing_isolated_components():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert TELEMETRY_PATHS and all((root / path).is_file() for path in TELEMETRY_PATHS)
