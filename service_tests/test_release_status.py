"""A status record must not turn availability or unrelated green CI into readiness."""

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
