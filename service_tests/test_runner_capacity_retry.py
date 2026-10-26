"""Runner outages may retry once; executing or untrusted failures never do."""

import copy
import json
from types import SimpleNamespace

import pytest

from deploy import runner_capacity_retry as subject


@pytest.fixture
def fixture(monkeypatch):
    repo = subject.REPOSITORY
    state = SimpleNamespace(
        run={
            "id": 123,
            "run_attempt": 1,
            "head_sha": "a" * 40,
            "head_branch": "v4.22.0",
            "path": ".github/workflows/public-updates.yml",
            "event": "workflow_dispatch",
            "status": "completed",
            "conclusion": "failure",
            "head_repository": {"full_name": repo},
            "repository": {"full_name": repo},
        },
        latest={
            "tag_name": "v4.22.0",
            "draft": False,
            "prerelease": False,
            "published_at": "2026-10-19T18:49:46Z",
        },
        jobs=[
            {"id": 7, "run_id": 123, "status": "completed", "conclusion": "success"},
            {"id": 8, "run_id": 123, "status": "completed", "conclusion": "skipped"},
            {
                "id": 9,
                "run_id": 123,
                "status": "completed",
                "conclusion": "cancelled",
                "steps": [],
                "runner_name": "",
                "runner_id": 0,
                "check_run_url": f"https://api.github.com/repos/{repo}/check-runs/99",
            },
        ],
        annotations=[
            {"annotation_level": "failure", "message": subject.CAPACITY_FAILURE},
            {
                "annotation_level": "notice",
                "message": "Due to capacity constraints, jobs targeting macOS arm64 runners may experience longer queue times.",
            },
        ],
        sha="a" * 40,
        main_sha="a" * 40,
        ci_runs=[],
        ci_comparison={
            "status": "ahead",
            "base_commit": {"sha": "a" * 40},
            "merge_base_commit": {"sha": "a" * 40},
            "files": [{"filename": "deploy/maintenance-status.json", "status": "modified"}],
        },
        comparison="ahead",
        mutate=None,
        calls=[],
    )

    def api(actual_repo, path):
        assert actual_repo == repo
        if path == "actions/runs/123":
            return copy.deepcopy(state.run)
        if path == "releases/latest":
            return state.latest
        if path == "git/ref/heads/main":
            return {"object": {"type": "commit", "sha": state.main_sha}}
        if path == "actions/workflows/ci.yml/runs?branch=main&event=push&per_page=1":
            return {"workflow_runs": state.ci_runs}
        if path.startswith("git/ref/"):
            return {"object": {"type": "commit", "sha": state.sha}}
        if path.startswith("compare/"):
            if state.run["path"] == subject.SOURCE_CHECKS:
                return state.ci_comparison
            return {"status": state.comparison}
        raise AssertionError(path)

    def gh(*arguments):
        state.calls.append(arguments)
        if arguments == (
            "api",
            "--method",
            "POST",
            f"repos/{repo}/actions/runs/123/rerun-failed-jobs",
        ):
            return ""
        assert arguments[0] == "api"
        if arguments[1] == f"repos/{repo}/actions/runs/123/attempts/1/jobs?per_page=100&page=1":
            return json.dumps({"jobs": state.jobs, "total_count": len(state.jobs)})
        if arguments[1] == f"repos/{repo}/check-runs/99/annotations?per_page=100&page=1":
            if state.mutate:
                state.mutate()
            return json.dumps(state.annotations)
        raise AssertionError(arguments)

    monkeypatch.setattr(subject, "api", api)
    monkeypatch.setattr(subject, "gh", gh)
    return state


def mutations(state):
    return [call for call in state.calls if "POST" in call]


@pytest.mark.parametrize("candidate", ["public", "candidate", "source"])
def test_exact_capacity_failure_retries_only_failed_jobs_once(fixture, candidate):
    if candidate == "candidate":
        fixture.run.update(path=".github/workflows/release.yml", head_branch="release/4.24.0-r2")
    elif candidate == "source":
        fixture.run.update(path=subject.SOURCE_CHECKS, head_branch="main", event="push")
        fixture.ci_runs = [copy.deepcopy(fixture.run)]
    dry = subject.inspect(123)
    assert dry["eligible"] and not dry["retried"] and dry["job_ids"] == [9]
    assert not mutations(fixture)
    assert subject.inspect(123, apply=True)["retried"]
    assert len(mutations(fixture)) == 1
    fixture.run["run_attempt"] = 2
    assert not subject.inspect(123, apply=True)["eligible"]
    assert len(mutations(fixture)) == 1


def source_checks(fixture):
    fixture.run.update(path=subject.SOURCE_CHECKS, head_branch="main", event="push")
    fixture.ci_runs = [copy.deepcopy(fixture.run)]


def test_source_checks_allow_only_documentation_advancement_on_main(fixture):
    source_checks(fixture)
    fixture.main_sha = "b" * 40
    assert subject.inspect(123, apply=True)["retried"]
    assert len(mutations(fixture)) == 1


@pytest.mark.parametrize(
    "damage",
    [
        "branch",
        "event",
        "newer_run",
        "source_change",
        "code_rename",
        "truncated",
        "missing",
        "diverged",
    ],
)
def test_superseded_or_unproved_source_checks_never_retry(fixture, damage):
    source_checks(fixture)
    fixture.main_sha = "b" * 40
    if damage == "branch":
        fixture.run["head_branch"] = "codex/other"
    elif damage == "event":
        fixture.run["event"] = "pull_request"
    elif damage == "newer_run":
        fixture.ci_runs[0]["id"] = 124
    elif damage == "source_change":
        fixture.ci_comparison["files"] = [{"filename": "mnemion/version.py"}]
    elif damage == "code_rename":
        fixture.ci_comparison["files"] = [
            {"filename": "docs/code.md", "previous_filename": "mnemion/version.py"}
        ]
    elif damage == "truncated":
        fixture.ci_comparison["files"] = [{"filename": f"docs/{i}.md"} for i in range(300)]
    elif damage == "missing":
        fixture.ci_comparison.pop("files")
    else:
        fixture.ci_comparison["status"] = "diverged"
    assert not subject.inspect(123, apply=True)["eligible"]
    assert not mutations(fixture)


@pytest.mark.parametrize("change", ["newer_run", "source_change"])
def test_source_retry_rechecks_supersession_immediately_before_mutation(fixture, change):
    source_checks(fixture)

    def mutate():
        if change == "newer_run":
            fixture.ci_runs[0]["id"] = 124
        else:
            fixture.main_sha = "b" * 40
            fixture.ci_comparison["files"] = [{"filename": "mnemion/version.py"}]

    fixture.mutate = mutate
    assert not subject.inspect(123, apply=True)["eligible"]
    assert not mutations(fixture)


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_attempt", 2),
        ("event", "pull_request"),
        ("path", ".github/workflows/ci.yml"),
        ("head_branch", "main"),
        ("head_sha", "not-a-commit"),
        ("status", "in_progress"),
        ("conclusion", "success"),
        ("head_repository", {"full_name": "outsider/mnemion"}),
        ("repository", {"full_name": "outsider/mnemion"}),
    ],
)
def test_untrusted_in_progress_or_repeated_runs_never_retry(fixture, field, value):
    fixture.run[field] = value
    assert not subject.inspect(123, apply=True)["eligible"]
    assert not mutations(fixture)


@pytest.mark.parametrize(
    "field,value",
    [
        ("steps", [{"name": "Run tests", "conclusion": "failure"}]),
        ("runner_name", "GitHub Actions 99"),
        ("runner_id", 13),
        ("conclusion", "timed_out"),
        ("status", "queued"),
        ("run_id", 124),
        ("check_run_url", "https://example.invalid/check-runs/99"),
    ],
)
def test_executed_or_unproven_failure_stays_for_investigation(fixture, field, value):
    fixture.jobs[-1][field] = value
    assert not subject.inspect(123, apply=True)["eligible"]
    assert not mutations(fixture)


@pytest.mark.parametrize(
    "annotations",
    [
        [],
        [{"annotation_level": "failure", "message": "The operation was canceled."}],
        [{"annotation_level": "notice", "message": subject.CAPACITY_FAILURE}],
        [
            {"annotation_level": "failure", "message": subject.CAPACITY_FAILURE},
            {"annotation_level": "failure", "message": "Test failed."},
        ],
    ],
)
def test_only_explicit_exclusive_capacity_failure_is_eligible(fixture, annotations):
    fixture.annotations = annotations
    assert not subject.inspect(123, apply=True)["eligible"]
    assert not mutations(fixture)


def test_a_second_real_failure_blocks_retry_of_the_entire_run(fixture):
    fixture.jobs.append(
        {
            "id": 10,
            "run_id": 123,
            "status": "completed",
            "conclusion": "failure",
            "steps": [{"conclusion": "failure"}],
        }
    )
    assert not subject.inspect(123, apply=True)["eligible"]
    assert not mutations(fixture)


@pytest.mark.parametrize("change", ["attempt", "source", "latest", "tag"])
def test_rechecks_run_and_current_release_immediately_before_mutation(fixture, change):
    def mutate():
        if change == "attempt":
            fixture.run["run_attempt"] = 2
        elif change == "source":
            fixture.run["head_sha"] = "b" * 40
        elif change == "latest":
            fixture.latest["tag_name"] = "v4.24.0"
        else:
            fixture.sha = "b" * 40

    fixture.mutate = mutate
    assert not subject.inspect(123, apply=True)["eligible"]
    assert not mutations(fixture)


def test_a_release_candidate_must_remain_on_main(fixture):
    fixture.run.update(path=".github/workflows/release.yml", head_branch="release/4.24.0")
    fixture.comparison = "diverged"
    assert not subject.inspect(123, apply=True)["eligible"]
    assert not mutations(fixture)


def test_truncated_job_inventory_stops_before_retry(monkeypatch):
    monkeypatch.setattr(subject, "gh", lambda *_: json.dumps({"jobs": [{}], "total_count": 2}))
    with pytest.raises(ValueError, match="Incomplete job inventory"):
        subject.pages("actions/runs/123/attempts/1/jobs", "jobs")
