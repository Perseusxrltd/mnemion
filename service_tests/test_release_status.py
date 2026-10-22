"""A status record must not turn availability or unrelated green CI into readiness."""

import base64
from copy import deepcopy

import pytest

from deploy import release_status as status
from deploy.release import verify_roadmap

SOURCE = "a" * 40
PUBLISHED = "2026-10-13T10:10:04Z"
UPLOADED = "2026-10-13T10:08:14Z"


def test_source_roadmap_review_is_independent_of_published_availability():
    verify_roadmap("Reviewed source distribution: **4.2.0**.\nPublished release: 4.1.7.\n", "4.2.0")


@pytest.mark.parametrize(
    "text",
    [
        "Current distribution: **4.2.0**",
        "Reviewed source distribution: **4.1.7**.",
        "Example: Reviewed source distribution: **4.2.0**.",
        "Reviewed source distribution: **4.2.0**.\nReviewed source distribution: **4.1.7**.",
    ],
)
def test_roadmap_requires_one_current_source_review(text):
    with pytest.raises(ValueError, match="Review and update"):
        verify_roadmap(text, "4.2.0")


def run(workflow="ci.yml", **overrides):
    return {
        "id": 42,
        "html_url": f"{status.ORIGIN}/actions/runs/42",
        "head_sha": SOURCE,
        "head_repository": {"full_name": status.REPOSITORY},
        "path": f".github/workflows/{workflow}",
        "event": "release" if workflow in {"public-updates.yml", "website-release.yml"} else "push",
        "created_at": "2026-10-13T10:10:07Z",
        "updated_at": "2026-10-13T10:21:18Z",
        "status": "completed",
        "conclusion": "success",
        **overrides,
    }


def gate(runs, workflow="ci.yml"):
    return status.gate(
        {"workflow_runs": runs},
        workflow,
        SOURCE,
        published_at=PUBLISHED,
        assets_updated_at=UPLOADED,
        published_tag="v4.2.3",
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"head_sha": "b" * 40},
        {"head_repository": {"full_name": "someone/fork"}},
        {"path": ".github/workflows/other.yml"},
        {"event": "pull_request"},
    ],
)
def test_unrelated_green_workflows_are_not_passing_release_evidence(patch):
    assert gate([run(**patch)])["status"] == "not recorded"


@pytest.mark.parametrize(
    "conclusion", ["failure", "cancelled", "skipped", "neutral", "timed_out", None]
)
def test_only_successful_completed_checks_pass(conclusion):
    assert gate([run(conclusion=conclusion)])["status"] == "not passed"
    assert gate([run(status="in_progress", conclusion=conclusion)])["status"] == "pending"


def test_later_failed_retry_does_not_reuse_an_earlier_success():
    earlier = run(updated_at="2026-10-13T10:15:00Z")
    assert gate([earlier, run(conclusion="failure")])["status"] == "not passed"


def test_dispatch_or_prepublication_run_cannot_claim_all_public_updates():
    for patch in ({"event": "workflow_dispatch"}, {"created_at": "2026-10-13T10:00:00Z"}):
        assert (
            gate([run("public-updates.yml", **patch)], "public-updates.yml")["status"]
            == "not recorded"
        )


def test_source_tagged_complete_dispatch_counts_but_partial_selection_does_not():
    values = {
        "event": "workflow_dispatch",
        "head_branch": "v4.2.3",
        "display_title": "Public updates / v4.2.3 / all / all",
    }
    assert gate([run("public-updates.yml", **values)], "public-updates.yml")["status"] == "passed"
    for patch in (
        {"head_branch": "main"},
        {"display_title": "Public updates / v4.2.3 / linux / all"},
        {"display_title": "Public updates / v4.2.2 / all / all"},
    ):
        assert (
            gate([run("public-updates.yml", **{**values, **patch})], "public-updates.yml")["status"]
            == "not recorded"
        )


def test_automatic_verification_names_its_actual_release_source():
    values = {
        "event": "workflow_run",
        "head_sha": "b" * 40,
        "display_title": "Verify release / " + SOURCE,
    }
    assert (
        gate([run("verify-artifacts.yml", **values)], "verify-artifacts.yml")["status"] == "passed"
    )
    values["display_title"] = "Verify release / " + "c" * 40
    assert (
        gate([run("verify-artifacts.yml", **values)], "verify-artifacts.yml")["status"]
        == "not recorded"
    )


@pytest.mark.parametrize(
    "workflow", ["verify-artifacts.yml", "public-updates.yml", "website-release.yml"]
)
def test_replaced_assets_require_new_delivery_evidence(workflow):
    result = status.gate(
        {"workflow_runs": [run(workflow)]},
        workflow,
        SOURCE,
        published_at=PUBLISHED,
        assets_updated_at="2026-10-13T11:00:00Z",
    )
    assert result["status"] == "recheck required"


def test_public_upgrade_requires_each_advertised_architecture():
    targets = [{"platform": "windows", "arch": "x64"}, {"platform": "linux", "arch": "arm64"}]
    evidence = gate([run("public-updates.yml")], "public-updates.yml")
    jobs = {
        "jobs": [
            {"name": "windows / x64 public upgrade", "status": "completed", "conclusion": "success"}
        ]
    }
    assert status.public_upgrade_coverage(evidence, jobs, targets)["missing_targets"] == [
        "linux / arm64 public upgrade"
    ]
    jobs["jobs"].append(
        {"name": "linux / arm64 public upgrade", "status": "completed", "conclusion": "skipped"}
    )
    assert status.public_upgrade_coverage(evidence, jobs, targets)["status"] == "incomplete"
    jobs["jobs"][-1]["conclusion"] = "success"
    assert status.public_upgrade_coverage(evidence, jobs, targets)["targets_passed"] == 2


def test_requirement_counts_do_not_credit_partial_or_ongoing_work():
    contents = "\n".join(
        f"| F0{i} | Requirement | {state} | Evidence |" for i, state in enumerate(status.STATES, 1)
    )
    result = status.requirement_counts(contents)
    assert result["total"] == 6 and result["Shipped"] == 1
    assert result["Partial"] == 1 and result["Ongoing"] == 1
    for changed in (
        contents + "\n" + contents.splitlines()[0],
        contents.replace("Shipped", "Nearly done"),
    ):
        with pytest.raises(ValueError):
            status.requirement_counts(changed)


def test_status_links_cannot_point_at_another_repository():
    with pytest.raises(ValueError, match="another repository"):
        gate([run(html_url="https://example.org/looks-green")])


def test_inventory_only_advertises_installers_that_exist():
    published = {
        "tag_name": "v4.1.7",
        "assets": [
            {
                "name": "Mnemion-Studio-4.1.7-linux-x86_64.AppImage",
                "browser_download_url": "linux-installer",
            },
            {
                "name": "Mnemion-Studio-4.1.7-windows-arm64.exe",
                "browser_download_url": "windows-installer",
            },
        ],
    }
    assert status.installers(published) == [
        {"platform": "windows", "arch": "arm64", "url": "windows-installer"},
        {"platform": "linux", "arch": "x64", "url": "linux-installer"},
    ]
    original = deepcopy(published)
    status.installers(published)
    assert published == original


def job(name, run_id, identifier, **changes):
    return {
        "name": name,
        "id": identifier,
        "run_id": run_id,
        "head_sha": SOURCE,
        "status": "completed",
        "conclusion": "success",
        "steps": [],
        **changes,
    }


def embedded_fixture(monkeypatch, *, broken=None):
    ci = gate([run(conclusion="cancelled")])
    release = gate(
        [run("release.yml", id=43, html_url=f"{status.ORIGIN}/actions/runs/43")], "release.yml"
    )
    original = [job("lint", 42, 1), job("service (3.12)", 42, 2, conclusion="cancelled")]
    embedded = [job("checks / lint", 43, 3), job("checks / service (3.12)", 43, 4)]
    if broken:
        broken(original, embedded)
    monkeypatch.setattr(
        status,
        "api",
        lambda path: {
            "total_count": len(original if "/42/" in path else embedded),
            "jobs": original if "/42/" in path else embedded,
        },
    )
    return ci, release


def test_superseded_branch_uses_every_matching_successful_release_check(monkeypatch):
    ci, release = embedded_fixture(monkeypatch)
    result = status.reuse_release_checks(ci, release, SOURCE)
    assert result["status"] == "passed" and result["run_id"] == 43
    assert result["superseded_run_id"] == 42 and result["jobs_passed"] == 2
    assert ci["status"] == "not passed"


@pytest.mark.parametrize("problem", ["failure", "step_failure", "missing", "skipped", "source"])
def test_reuse_never_conceals_failed_or_incomplete_checks(monkeypatch, problem):
    def broken(original, embedded):
        if problem == "failure":
            original[1]["conclusion"] = "failure"
        elif problem == "step_failure":
            original[1]["steps"] = [{"conclusion": "failure"}]
        elif problem == "missing":
            embedded.pop()
        elif problem == "skipped":
            embedded[1]["conclusion"] = "skipped"
        else:
            embedded[1]["head_sha"] = "b" * 40

    ci, release = embedded_fixture(monkeypatch, broken=broken)
    if problem == "source":
        with pytest.raises(ValueError, match="exact source"):
            status.reuse_release_checks(ci, release, SOURCE)
    else:
        assert status.reuse_release_checks(ci, release, SOURCE) == ci


def test_reuse_does_not_override_actual_failure_or_manual_cancellation(monkeypatch):
    ci, release = embedded_fixture(monkeypatch)
    for change in (
        {"conclusion": "failure"},
        {"event": "workflow_dispatch"},
        {"status": "pending"},
    ):
        candidate = {**ci, **change}
        assert status.reuse_release_checks(candidate, release, SOURCE) == candidate
    assert status.reuse_release_checks(ci, {**release, "status": "not passed"}, SOURCE) == ci


def missing_ci_fixture(monkeypatch, problem=None):
    workflow = b"""jobs:
  lint: {}
  service:
    strategy:
      matrix:
        python: ['3.12', '3.14']
"""
    names = ["checks / lint", "checks / service (3.12)", "checks / service (3.14)"]
    steps = [{"name": "Check", "status": "completed", "conclusion": "success"}]
    jobs = [job(name, 43, n + 1, steps=deepcopy(steps)) for n, name in enumerate(names)]
    jobs.append(job("Reuse verified Product checks", 43, 4, conclusion="skipped"))
    if problem == "missing_target":
        jobs.pop(2)
    elif problem == "extra_target":
        jobs.append(job("checks / service (9.99)", 43, 5, steps=deepcopy(steps)))
    elif problem == "skipped_target":
        jobs[2]["conclusion"] = "skipped"
    elif problem == "empty_steps":
        jobs[2]["steps"] = []
    elif problem == "failed_step":
        jobs[2]["steps"][0]["conclusion"] = "failure"
    elif problem == "pending_step":
        jobs[2]["steps"][0]["status"] = "in_progress"
    elif problem == "missing_lane":
        jobs.pop()
    elif problem == "unsupported_matrix":
        workflow += b"        include: [{python: '3.15'}]\n"
    elif problem == "foreign_source":
        jobs[2]["head_sha"] = "b" * 40
    requests = []

    def get(path):
        requests.append(path)
        if path == f"contents/.github/workflows/ci.yml?ref={SOURCE}":
            return {
                "type": "file",
                "path": ".github/workflows/ci.yml",
                "encoding": "base64",
                "size": len(workflow),
                "content": base64.b64encode(workflow).decode(),
            }
        assert path == "actions/runs/43/jobs?filter=latest&per_page=100&page=1"
        return {"total_count": len(jobs), "jobs": jobs}

    monkeypatch.setattr(status, "api", get)
    release = gate(
        [run("release.yml", id=43, html_url=f"{status.ORIGIN}/actions/runs/43")], "release.yml"
    )
    return gate([]), release, requests


def test_absent_ci_uses_the_complete_matrix_from_the_immutable_release_workflow(monkeypatch):
    ci, release, requests = missing_ci_fixture(monkeypatch)
    result = status.reuse_release_checks(ci, release, SOURCE)
    assert result["status"] == "passed" and result["run_id"] == 43
    assert result["jobs_passed"] == 3 and result["standalone_status"] == "not recorded"
    assert ci["status"] == "not recorded" and "superseded_run_id" not in result
    assert len(requests) == 2
    assert requests[-1] == f"contents/.github/workflows/ci.yml?ref={SOURCE}"


@pytest.mark.parametrize(
    "problem",
    [
        "missing_target",
        "extra_target",
        "skipped_target",
        "empty_steps",
        "failed_step",
        "pending_step",
        "missing_lane",
        "unsupported_matrix",
    ],
)
def test_absent_ci_never_qualifies_partial_or_unverified_release_checks(monkeypatch, problem):
    ci, release, _ = missing_ci_fixture(monkeypatch, problem)
    assert status.reuse_release_checks(ci, release, SOURCE) == ci


def test_absent_ci_requires_every_job_to_belong_to_the_release_source(monkeypatch):
    ci, release, _ = missing_ci_fixture(monkeypatch, "foreign_source")
    with pytest.raises(ValueError, match="exact source"):
        status.reuse_release_checks(ci, release, SOURCE)


def test_job_inventory_requires_complete_pagination_and_stable_identity(monkeypatch):
    first = [job("job " + str(n), 42, n + 1) for n in range(100)]
    second = [job("last job", 42, 101)]
    monkeypatch.setattr(
        status,
        "api",
        lambda path: {"total_count": 101, "jobs": second if path.endswith("page=2") else first},
    )
    assert len(status.complete_jobs(42, SOURCE)) == 101
    second.clear()
    with pytest.raises(ValueError, match="Incomplete"):
        status.complete_jobs(42, SOURCE)
