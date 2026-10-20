"""Maintenance polling cannot infer closure from partial data or execute issue text."""

import copy

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


@pytest.mark.parametrize("workflow", ["release.yml", "database-cache.yml"])
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
    if workflow == "database-cache.yml":
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


def test_generated_titles_are_text_instead_of_remote_images_or_html():
    value = subject.escaped(
        "![remote](https://example.invalid/image) <script>run()</script> | next\nrow"
    )
    assert "![" not in value and "<script>" not in value and "\\|" in value and "\n" not in value
