"""Same-source CI reuse must preserve the entire release check contract."""

from __future__ import annotations

import base64
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
import zipfile

import pytest
import yaml

from deploy import ci_reuse as subject
from deploy import verify_artifacts

REPO = "example/mnemion"
COMMIT = "a" * 40
NOW = datetime.now(timezone.utc)
WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"


@pytest.fixture
def evidence():
    workflow = WORKFLOW.read_bytes()
    expected = subject.required_jobs(workflow.decode())
    run = {
        "id": 99,
        "head_sha": COMMIT,
        "path": ".github/workflows/ci.yml",
        "event": "push",
        "head_branch": "main",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 1,
        "repository": {"full_name": REPO},
        "head_repository": {"full_name": REPO},
        "html_url": f"https://github.com/{REPO}/actions/runs/99",
    }
    rows = [
        {
            "id": index,
            "run_id": 99,
            "head_sha": COMMIT,
            "name": name,
            "status": "completed",
            "conclusion": "success",
            "steps": [{"status": "completed", "conclusion": "success"}],
        }
        for index, name in enumerate(sorted(expected), 1)
    ]
    artifact = {
        "id": 123,
        "name": subject.ARTIFACT,
        "size_in_bytes": 1000,
        "expired": False,
        "expires_at": (NOW + timedelta(days=1)).isoformat(),
        "digest": "sha256:" + "b" * 64,
        "workflow_run": {"id": 99, "head_sha": COMMIT},
    }
    runs = {"total_count": 1, "workflow_runs": [run]}
    jobs = {"total_count": len(rows), "jobs": rows}
    artifacts = {"total_count": 1, "artifacts": [artifact]}
    responses = {
        f"actions/workflows/ci.yml/runs?head_sha={COMMIT}&per_page=10": runs,
        "actions/runs/99/jobs?filter=latest&per_page=100": jobs,
        "actions/runs/99/artifacts?per_page=100": artifacts,
        f"contents/.github/workflows/ci.yml?ref={COMMIT}": {
            "type": "file",
            "path": ".github/workflows/ci.yml",
            "encoding": "base64",
            "size": len(workflow),
            "content": base64.b64encode(workflow).decode(),
        },
    }
    calls = []

    def get(path):
        calls.append(path)
        return responses[path]

    return SimpleNamespace(
        expected=expected,
        run=run,
        runs=runs,
        jobs=jobs,
        artifact=artifact,
        artifacts=artifacts,
        responses=responses,
        calls=calls,
        get=get,
    )


def select(evidence):
    return subject.selection(REPO, COMMIT, evidence.expected, evidence.get, now=NOW)


def test_complete_current_workflow_and_digest_qualify(evidence):
    assert evidence.expected == {
        "Select checks",
        "service (3.12)",
        "service (3.13)",
        "service (3.14)",
        "supervision (macos-15)",
        "supervision (macos-15-intel)",
        "container (ubuntu-22.04)",
        "container (ubuntu-22.04-arm)",
        "legacy",
        "lint",
        "dependency-audit",
        "studio",
    }
    report = select(evidence)
    assert report["reusable"] and report["jobs_passed"] == len(evidence.expected)
    assert report["source_commit"] == COMMIT and report["run_id"] == 99
    assert report["artifact"]["digest"] == evidence.artifact["digest"]
    assert len(evidence.calls) == 3


def test_telemetry_component_push_is_not_full_release_evidence(evidence):
    # These jobs are absent from component-only pushes. Even a successful run
    # with every other job green and an apparent runtime artifact cannot be
    # reused as full release qualification.
    contract = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    for name in ("service", "container"):
        assert contract[name]["if"] == "needs.scope.outputs.runtime == 'true'"
    skipped = []
    for row in evidence.jobs["jobs"]:
        if row["name"].startswith(("service (", "container (")):
            row["conclusion"] = "skipped"
            row["steps"] = []
            skipped.append(row["name"])
    assert len(skipped) == 5
    report = select(evidence)
    assert report["reusable"] is False
    assert report["reason"] == "required_checks_not_successful"
    assert len(evidence.calls) == 2


@pytest.mark.parametrize("change", ["source", "foreign", "pull_request", "branch", "workflow"])
def test_other_sources_and_untrusted_run_origins_do_not_qualify(evidence, change):
    if change == "source":
        evidence.run["head_sha"] = "c" * 40
    elif change == "foreign":
        evidence.run["head_repository"]["full_name"] = "fork/mnemion"
    elif change == "pull_request":
        evidence.run["event"] = "pull_request"
    elif change == "branch":
        evidence.run["head_branch"] = "release/example"
    else:
        evidence.run["path"] = ".github/workflows/other.yml"
    assert select(evidence)["reason"] == "no_matching_run"
    assert len(evidence.calls) == 1


@pytest.mark.parametrize("status,conclusion", [("in_progress", None), ("completed", "failure")])
def test_newer_failed_or_running_attempt_cannot_be_hidden_by_old_success(
    evidence, status, conclusion
):
    newer = {**copy.deepcopy(evidence.run), "id": 100, "status": status, "conclusion": conclusion}
    evidence.runs["workflow_runs"].insert(0, newer)
    evidence.runs["total_count"] += 1
    report = select(evidence)
    assert not report["reusable"] and report["run_id"] == 100
    assert report["reason"] == "latest_run_not_successful"
    assert len(evidence.calls) == 1


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "truncated",
        "skipped",
        "step_failure",
        "unfinished_step",
        "no_steps",
        "foreign_job",
        "duplicate",
    ],
)
def test_partial_or_unsuccessful_checks_never_qualify(evidence, change):
    row = evidence.jobs["jobs"][0]
    if change == "missing":
        evidence.jobs["jobs"].pop()
        evidence.jobs["total_count"] -= 1
    elif change == "truncated":
        evidence.jobs["total_count"] += 1
    elif change == "skipped":
        row["conclusion"] = "skipped"
    elif change == "step_failure":
        row["steps"][0]["conclusion"] = "failure"
    elif change == "unfinished_step":
        row["steps"][0].update(status="in_progress", conclusion=None)
    elif change == "no_steps":
        row["steps"] = []
    elif change == "foreign_job":
        row["head_sha"] = "c" * 40
    else:
        row["id"] = evidence.jobs["jobs"][1]["id"]
    assert not select(evidence)["reusable"]
    assert len(evidence.calls) == 2


@pytest.mark.parametrize(
    "change", ["missing", "duplicate", "expired", "expiry", "digest", "source", "truncated"]
)
def test_required_runtime_artifact_must_be_available_and_tied_to_ci(evidence, change):
    if change == "missing":
        evidence.artifacts.update(total_count=0, artifacts=[])
    elif change == "duplicate":
        evidence.artifacts["artifacts"].append(copy.deepcopy(evidence.artifact))
        evidence.artifacts["total_count"] += 1
    elif change == "expired":
        evidence.artifact["expired"] = True
    elif change == "expiry":
        evidence.artifact["expires_at"] = (NOW - timedelta(seconds=1)).isoformat()
    elif change == "digest":
        evidence.artifact["digest"] = ""
    elif change == "source":
        evidence.artifact["workflow_run"]["head_sha"] = "c" * 40
    else:
        evidence.artifacts["total_count"] += 1
    assert not select(evidence)["reusable"]


def test_new_required_job_is_not_satisfied_by_previous_job_set(evidence):
    contract = yaml.safe_load(WORKFLOW.read_text())
    contract["jobs"]["additional-check"] = {"runs-on": "ubuntu-latest"}
    expected = subject.required_jobs(yaml.safe_dump(contract))
    assert expected == evidence.expected | {"additional-check"}
    assert not subject.selection(REPO, COMMIT, expected, evidence.get, now=NOW)["reusable"]


@pytest.mark.parametrize(
    "matrix",
    [{"include": [{"runner": "ubuntu-latest"}]}, "${{ fromJSON(needs.other.outputs.matrix) }}"],
)
def test_unknown_matrix_disables_optimization(matrix):
    contract = {"jobs": {"test": {"strategy": {"matrix": matrix}}}}
    with pytest.raises(ValueError, match="Unsupported CI matrix"):
        subject.required_jobs(yaml.safe_dump(contract))


def lane_jobs(evidence, *, reuse):
    fixed = [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in ("Release preflight", "assemble", "native / windows-11-arm / arm64")
    ]
    if reuse:
        return fixed + [
            {"name": subject.REUSE_JOB, "status": "completed", "conclusion": "success"},
            {"name": "checks", "status": "completed", "conclusion": "skipped"},
        ]
    return fixed + [
        {"name": subject.REUSE_JOB, "status": "completed", "conclusion": "skipped"},
        *[
            {"name": "checks / " + name, "status": "completed", "conclusion": "success"}
            for name in sorted(evidence.expected)
        ],
    ]


@pytest.mark.parametrize("reuse", [False, True])
def test_publication_allows_only_the_unused_lane_with_complete_proof(evidence, reuse):
    allowed = subject.verify_release_check_lanes(
        REPO, COMMIT, lane_jobs(evidence, reuse=reuse), evidence.get
    )
    assert allowed == ({"checks"} if reuse else {subject.REUSE_JOB})


@pytest.mark.parametrize("change", ["no_proof", "missing_lane", "missing_check", "mixed_lanes"])
def test_publication_rejects_missing_or_mixed_check_lanes(evidence, change):
    rows = lane_jobs(evidence, reuse=change != "missing_check")
    if change == "no_proof":
        evidence.jobs["jobs"][0]["conclusion"] = "skipped"
    elif change == "missing_lane":
        rows.pop()
    elif change == "missing_check":
        rows.pop()
    else:
        rows.append({"name": "checks / lint", "status": "completed", "conclusion": "success"})
    with pytest.raises(ValueError):
        subject.verify_release_check_lanes(REPO, COMMIT, rows, evidence.get)


@pytest.mark.parametrize("reuse", [False, True])
def test_independent_release_verifier_uses_the_same_source_proof(evidence, monkeypatch, reuse):
    rows = lane_jobs(evidence, reuse=reuse)
    run = {
        **evidence.run,
        "id": 101,
        "path": ".github/workflows/release.yml",
        "event": "workflow_dispatch",
    }

    def github(*args):
        if args == ("api", f"repos/{REPO}/actions/runs/101"):
            return json.dumps(run)
        if args[:3] == ("run", "view", "101"):
            return json.dumps({"headSha": COMMIT, "conclusion": "success", "jobs": rows})
        assert args[0] == "api"
        return json.dumps(evidence.get(args[1].removeprefix(f"repos/{REPO}/")))

    monkeypatch.setattr(verify_artifacts, "gh", github)
    assert verify_artifacts.release_run(REPO, 101)["head_sha"] == COMMIT
    rows[2]["conclusion"] = "skipped"
    with pytest.raises(ValueError, match="failed or invalid gate"):
        verify_artifacts.release_run(REPO, 101)


@pytest.mark.parametrize("problem", [RuntimeError("unavailable"), yaml.YAMLError("unsupported")])
def test_unknown_evidence_selects_the_full_check_path(tmp_path, monkeypatch, capsys, problem):
    def failed(*args, **kwargs):
        raise problem

    output = tmp_path / "selection.json"
    monkeypatch.setattr(
        sys, "argv", ["ci_reuse", "--repo", REPO, "--source", COMMIT, "--output", str(output)]
    )
    monkeypatch.setattr(
        subject.subprocess,
        "check_output",
        lambda args, **kwargs: COMMIT if "rev-parse" in args else "",
    )
    monkeypatch.setattr(subject, "required_jobs", failed)
    subject.main()
    assert json.loads(output.read_text())["reason"] == "evidence_unavailable"
    assert capsys.readouterr().out == "reusable=false\nrun_id=\nartifact_id=\nartifact_digest=\n"


def archive(tmp_path, entries):
    path = tmp_path / "runtime.zip"
    with zipfile.ZipFile(path, "w") as package:
        for name, data in entries:
            package.writestr(name, data)
    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return path, digest


def test_artifact_transfer_checks_exact_archive_before_extracting(tmp_path):
    path, digest = archive(
        tmp_path,
        [("cryptography-50.0.2-cp311-abi3-macosx_10_13_x86_64.whl", b"fixture wheel bytes")],
    )
    destination = tmp_path / "restored"
    names = subject.restore_archive(path, destination, digest)
    assert len(names) == 1 and (destination / names[0]).read_bytes() == b"fixture wheel bytes"
    with pytest.raises(FileExistsError):
        subject.restore_archive(path, destination, digest)
    with pytest.raises(ValueError, match="bytes differ"):
        subject.restore_archive(path, tmp_path / "wrong-digest", "sha256:" + "0" * 64)
    assert not (tmp_path / "wrong-digest").exists()


@pytest.mark.parametrize("kind", ["traversal", "symlink", "other_file", "duplicate"])
def test_artifact_never_extracts_paths_links_or_ambiguous_entries(tmp_path, kind):
    name = "runtime.whl"
    if kind == "traversal":
        name = "../runtime.whl"
    elif kind == "symlink":
        name = zipfile.ZipInfo("runtime.whl")
        name.create_system = 3
        name.external_attr = (stat.S_IFLNK | 0o777) << 16
    elif kind == "other_file":
        name = "run.sh"
    entries = [(name, b"fixture")]
    if kind == "duplicate":
        entries *= 2
        with pytest.warns(UserWarning, match="Duplicate name"):
            path, digest = archive(tmp_path, entries)
    else:
        path, digest = archive(tmp_path, entries)
    destination = tmp_path / "restored"
    with pytest.raises(ValueError):
        subject.restore_archive(path, destination, digest)
    assert not destination.exists()


def test_missing_digest_is_rejected_before_any_download(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("An unverified transfer must not start")

    monkeypatch.setattr(subject.subprocess, "run", forbidden)
    with pytest.raises(ValueError, match="before downloading"):
        subject.restore(REPO, 123, None, tmp_path / "restored")
