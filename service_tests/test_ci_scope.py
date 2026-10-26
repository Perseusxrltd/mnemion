"""Use real Git changes to verify which work may avoid product build queues."""

import subprocess

import pytest

from deploy.ci_scope import scope


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
