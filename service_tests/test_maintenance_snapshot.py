"""Maintenance polling cannot infer closure from partial data or execute issue text."""

import copy
import json
import subprocess

import pytest

from deploy import maintenance_snapshot as subject


def test_snapshot_changes_are_stable_and_truncated_issues_cannot_erase_the_inventory():
    issue = {"number": 1, "title": "One report", "updatedAt": "2026-10-14T10:00:00Z", "labels": []}
    rows = subject.issue_rows([issue])
    data = {
        "schema": 1,
        "repository": subject.REPOSITORY,
        "run_window": 100,
        "release": {"version": "v4.2.3"},
        "issues": rows,
        "runs": [],
    }
    previous = {**copy.deepcopy(data), "observed_at": "2026-10-14T10:01:00Z"}
    assert not subject.changes(previous, data)["changed"]
    assert subject.changes(previous, data)["new_or_updated_issues"] == []
    data["issues"][0]["updated_at"] = "2026-10-14T10:02:00Z"
    assert subject.changes(previous, data)["new_or_updated_issues"] == [1]
    with pytest.raises(ValueError, match="pagination"):
        subject.issue_rows([issue] * subject.ISSUE_LIMIT)


def test_run_window_discards_foreign_and_superseded_evidence():
    release = {"published_at": "2026-10-13T17:00:00Z", "target_commitish": "a" * 40}
    row = {
        "id": 1,
        "path": ".github/workflows/release.yml",
        "head_repository": {"full_name": subject.REPOSITORY},
        "head_branch": "release/4.2.4",
        "head_sha": "b" * 40,
        "status": "completed",
        "conclusion": "failure",
        "created_at": "2026-10-14T10:00:00Z",
        "updated_at": "2026-10-14T10:01:00Z",
    }
    newer = {**row, "id": 2, "conclusion": "success"}
    foreign = {**row, "id": 3, "head_repository": {"full_name": "foreign/repo"}}
    obsolete = {
        **row,
        "id": 4,
        "head_branch": "release/4.2.2",
        "created_at": "2026-10-13T10:00:00Z",
        "updated_at": "2026-10-13T10:01:00Z",
    }
    assert [item["id"] for item in subject.run_rows([row, newer, foreign, obsolete], release)] == [
        2
    ]


@pytest.mark.parametrize("workflow", ["release.yml", "database-cache.yml", "desktop.yml"])
def test_new_build_failure_is_retained_when_it_started_before_an_older_release_published(
    workflow,
):
    release = {"published_at": "2026-10-14T12:26:00Z", "target_commitish": "a" * 40}
    row = {
        "id": 5,
        "path": ".github/workflows/" + workflow,
        "head_repository": {"full_name": subject.REPOSITORY},
        "head_branch": "release/4.2.5",
        "head_sha": "b" * 40,
        "status": "completed",
        "conclusion": "failure",
        "created_at": "2026-10-14T12:23:00Z",
        "updated_at": "2026-10-14T12:45:00Z",
    }
    assert [item["id"] for item in subject.run_rows([row], release)] == [5]
    if workflow in {"database-cache.yml", "desktop.yml"}:
        assert workflow not in subject.RELEASE_WORKFLOWS


def test_active_runs_surface_failed_jobs_and_only_completed_attempts_reuse_job_evidence(
    monkeypatch,
):
    release = {
        "tag_name": "v4.2.4",
        "published_at": "2026-10-14T12:26:00Z",
        "target_commitish": "a" * 40,
        "draft": False,
        "prerelease": False,
    }
    run = {
        "id": 5,
        "path": ".github/workflows/release.yml",
        "head_repository": {"full_name": subject.REPOSITORY},
        "head_branch": "release/4.2.5",
        "head_sha": "b" * 40,
        "status": "in_progress",
        "conclusion": None,
        "created_at": "2026-10-14T12:23:00Z",
        "updated_at": "2026-10-14T12:24:00Z",
    }
    observed = []
    jobs = [
        {
            "id": 50,
            "name": "Mac startup",
            "status": "completed",
            "conclusion": "failure",
            "steps": [],
        },
        {
            "id": 51,
            "name": "Windows ARM",
            "status": "in_progress",
            "conclusion": None,
            "steps": [{"name": "Install", "status": "in_progress"}],
        },
    ]

    def remote(*arguments):
        if arguments[0] == "issue":
            return []
        endpoint = arguments[1].split(subject.REPOSITORY + "/", 1)[1]
        if endpoint == "releases/latest":
            return release
        if endpoint == "actions/runs?per_page=100":
            return {"workflow_runs": [run]}
        assert endpoint == "actions/runs/5/jobs?filter=latest&per_page=100"
        observed.append(endpoint)
        return {"total_count": len(jobs), "jobs": jobs}

    monkeypatch.setattr(subject, "object_from_gh", remote)
    first = subject.collect({})
    assert subject.changes({}, first)["failed_runs"] == 1
    assert subject.changes({}, first)["active_runs"] == 1
    assert first["runs"][0]["job_progress"]["active"][0]["steps"] == ["Install"]
    assert first["runs"][0]["job_progress"]["active"][0]["runner_assigned"] is None
    jobs[1]["steps"] = [{"name": "Upgrade and relaunch", "status": "in_progress"}]
    second = subject.collect(first)
    # GitHub's enclosing run timestamp need not change with each job step.
    delta = subject.changes(first, second)
    assert delta["changed"] and len(delta["changed_runs"]) == 1
    rendered = subject.markdown({**second, "observed_at": "2026-10-20T05:30:00Z"})
    assert "1/2 jobs completed; 0 succeeded" in rendered
    assert "Windows ARM: in\\_progress — Upgrade and relaunch" in rendered
    assert len(observed) == 2
    unchanged = subject.collect(second)
    assert not subject.changes(second, unchanged)["changed"]
    assert len(observed) == 3
    jobs[1].update(status="completed", conclusion="success", steps=[])
    run.update(status="completed", conclusion="failure", updated_at="2026-10-14T12:45:00Z")
    completed = subject.collect(second)
    assert len(observed) == 4
    assert completed["runs"][0]["job_progress"] == {
        "total": 2,
        "completed": 2,
        "succeeded": 1,
        "active": [],
    }
    assert subject.collect(completed) == completed
    assert len(observed) == 4

    # Hosted capacity loss can fail the workflow with a cancelled, never-started
    # job and skipped dependents, without any job/step labelled failure.
    jobs[0].update(conclusion="cancelled", runner_id=0)
    jobs[1].update(conclusion="skipped")
    legacy = copy.deepcopy(completed)
    legacy["runs"][0].pop("job_details_schema")
    legacy["runs"][0]["failed_jobs"] = []
    interrupted = subject.collect(legacy)
    assert len(observed) == 5  # Old cached summaries are refreshed once.
    assert interrupted["runs"][0]["failed_jobs"] == [
        {
            "name": "Mac startup",
            "id": 50,
            "conclusion": "cancelled",
            "runner_assigned": False,
            "steps_reported": 0,
            "steps": [],
        }
    ]
    rendered = subject.markdown({**interrupted, "observed_at": "2026-10-20T17:43:03Z"})
    assert "Mac startup (cancelled)" in rendered
    assert "No runner was assigned and no steps were reported" in rendered
    assert subject.collect(interrupted) == interrupted
    assert len(observed) == 5


def test_generated_titles_are_text_instead_of_remote_images_or_html():
    value = subject.escaped(
        "![remote](https://example.invalid/image) <script>run()</script> | next\nrow"
    )
    assert "![" not in value and "<script>" not in value and "\\|" in value and "\n" not in value


@pytest.fixture
def watch_inventory(tmp_path, monkeypatch):
    (tmp_path / "deploy").mkdir()
    (tmp_path / "docs").mkdir()
    data = {
        "schema": 1,
        "repository": subject.REPOSITORY,
        "run_window": 100,
        "release": {"version": "v4.44.2", "url": "https://example.invalid/release"},
        "issues": subject.issue_rows(
            [{"number": 44, "title": "Existing report", "updatedAt": "2026-10-20", "labels": []}]
        ),
        "runs": [],
    }
    path = tmp_path / "deploy/maintenance-status.json"
    path.write_text(json.dumps(data))
    (tmp_path / "docs/MAINTENANCE_STATUS.md").write_text("Original inventory\n")
    clock, delays = [0], []

    def sleep(seconds):
        assert seconds > 0
        delays.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(subject.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(subject.time, "sleep", sleep)
    return tmp_path, data, path, delays


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("private diagnostic output"),
        subprocess.TimeoutExpired(["gh", "private diagnostic output"], 120),
        ValueError("private diagnostic output"),
    ],
)
def test_watcher_preserves_inventory_during_failed_read_and_reports_recovery(
    watch_inventory, monkeypatch, capsys, failure
):
    root, original, path, delays = watch_inventory
    retained = path.read_bytes()
    changed = copy.deepcopy(original)
    changed["issues"][0]["updated_at"] = "2026-10-22"
    responses = iter([original, failure, changed])

    def collect(previous):
        value = next(responses)
        assert path.read_bytes() == retained
        assert (root / "docs/MAINTENANCE_STATUS.md").read_text() == "Original inventory\n"
        assert previous["issues"] == original["issues"]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)

    monkeypatch.setattr(subject, "collect", collect)
    assert subject.observe(root, write=True, watch_seconds=90, interval=30) == 0
    output = capsys.readouterr().out
    assert "private diagnostic output" not in output
    reports = [json.loads(line) for line in output.splitlines()]
    assert [row["observation"] for row in reports] == ["available", "unavailable", "available"]
    assert reports[1]["retained_snapshot"] and reports[1]["last_success_at"]
    assert "closed_issues" not in reports[1] and "changed_runs" not in reports[1]
    assert reports[2]["recovered"] and reports[2]["new_or_updated_issues"] == [44]
    assert reports[2]["closed_issues"] == []
    assert json.loads(path.read_text())["issues"] == changed["issues"]
    assert delays == [30, 30, 30]


def test_watch_outage_is_bounded_and_cannot_finish_with_success(
    watch_inventory, monkeypatch, capsys
):
    root, _, path, delays = watch_inventory
    retained = path.read_bytes()

    def unavailable(previous):
        raise RuntimeError("Read unavailable")

    monkeypatch.setattr(subject, "collect", unavailable)
    assert subject.observe(root, write=True, watch_seconds=1000, interval=60) == 1
    assert delays == [60, 120, 240, 300, 280]
    assert path.read_bytes() == retained
    assert (root / "docs/MAINTENANCE_STATUS.md").read_text() == "Original inventory\n"
    reports = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(reports) == 5 and all(row["last_success_at"] is None for row in reports)
    assert reports[-1]["consecutive_failures"] == 5


def test_one_shot_read_failure_still_fails_ci_without_replacing_inventory(
    watch_inventory, monkeypatch, capsys
):
    root, _, path, delays = watch_inventory
    retained = path.read_bytes()

    def unavailable(previous):
        raise RuntimeError("Read unavailable")

    monkeypatch.setattr(subject, "collect", unavailable)
    with pytest.raises(RuntimeError, match="Read unavailable"):
        subject.observe(root, write=True)
    assert path.read_bytes() == retained and not delays
    assert capsys.readouterr().out == ""
