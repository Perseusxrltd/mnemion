"""Release orchestration guards; real signature coverage lives in release tests."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deploy import verify_artifacts as subject

REPO = "example/mnemion"
COMMIT = "a" * 40


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text('[project]\nversion = "4.1.2"\n')
    (source / "deploy").mkdir()
    (source / "deploy/release.py").write_text("# Fixture validator placeholder\n")
    output = tmp_path / "verified"
    payloads = {"payload.bin": b"fixture bytes"}
    payloads["SHA256SUMS.txt"] = (
        hashlib.sha256(payloads["payload.bin"]).hexdigest() + "  payload.bin\n"
    ).encode()
    release = {
        "id": 17,
        "tag_name": "v4.1.2",
        "target_commitish": COMMIT,
        "draft": True,
        "prerelease": False,
        "body": "A release.",
        "assets": [
            {
                "id": index,
                "name": name,
                "state": "uploaded",
                "size": len(data),
                "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
            }
            for index, (name, data) in enumerate(payloads.items(), 1)
        ],
    }
    run = {
        "id": 99,
        "head_sha": COMMIT,
        "path": ".github/workflows/release.yml",
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": REPO},
        "head_repository": {"full_name": REPO},
    }
    jobs = {
        "headSha": COMMIT,
        "conclusion": "success",
        "jobs": [
            {"name": name, "status": "completed", "conclusion": "success"}
            for name in ("Release preflight", "assemble")
        ],
    }
    state = SimpleNamespace(
        source=source,
        output=output,
        payloads=payloads,
        release=release,
        run=run,
        jobs=jobs,
        calls=[],
        validations=[],
        dirty=False,
        wrong_source=False,
        after_download=None,
        during_validation=None,
        tag_commit=COMMIT,
    )

    def github(*args):
        state.calls.append(args)
        if args == ("api", f"repos/{REPO}/actions/runs/99"):
            return json.dumps(run)
        if args[:3] == ("run", "view", "99"):
            return json.dumps(jobs)
        if args[:3] == ("release", "view", "v4.1.2"):
            return json.dumps({"databaseId": 17})
        if args == ("api", f"repos/{REPO}/releases/17"):
            value = copy.deepcopy(release)
            if state.after_download and state.validations:
                state.after_download(value)
            return json.dumps(value)
        if args[:3] == ("release", "download", "v4.1.2"):
            name = args[args.index("--pattern") + 1]
            directory = Path(args[args.index("--dir") + 1])
            (directory / name).write_bytes(payloads[name])
            return ""
        if args == ("api", f"repos/{REPO}/git/ref/tags/v4.1.2"):
            return json.dumps({"object": {"type": "commit", "sha": state.tag_commit}})
        raise AssertionError(f"Unexpected GitHub operation: {args}")

    def process(args, **kwargs):
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(stdout=("b" * 40 if state.wrong_source else COMMIT))
        if args[:2] == ["git", "status"]:
            return SimpleNamespace(stdout=" M pyproject.toml\n" if state.dirty else "")
        assert args == [
            subject.sys.executable,
            str(source / "deploy/release.py"),
            "--artifacts",
            str(output / "artifacts"),
        ]
        assert kwargs["cwd"] == source and kwargs["check"] is True
        state.validations.append(args)
        state.validation_environment = kwargs["env"]
        if state.during_validation:
            state.during_validation(output / "artifacts")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subject, "gh", github)
    monkeypatch.setattr(subject.subprocess, "run", process)
    return state


def test_complete_bytes_exact_source_and_read_only_operations(fixture):
    state = fixture
    receipt = subject.verify(REPO, 99, state.source, state.output)
    assert receipt["source_commit"] == COMMIT and receipt["assets"] == 2
    assert receipt["release_state"] == "draft" and len(state.validations) == 1
    assert receipt["asset_ids_sizes_digests_unchanged_after_verification"]
    assert json.loads((state.output / "release-verification.json").read_text()) == receipt
    assert all(call[1] in {"view", "download"} for call in state.calls if call[0] == "release")
    assert all("--method" not in call for call in state.calls)


@pytest.mark.parametrize(
    "failure",
    [
        "failed",
        "foreign",
        "wrong_workflow",
        "wrong_event",
        "unfinished",
        "missing_job",
        "job_failure",
        "job_commit",
    ],
)
def test_wrong_or_incomplete_gates_refuse_before_download(fixture, failure):
    state = fixture
    if failure == "failed":
        state.run["conclusion"] = "failure"
    elif failure == "foreign":
        state.run["head_repository"]["full_name"] = "foreign/repository"
    elif failure == "wrong_workflow":
        state.run["path"] = ".github/workflows/other.yml"
    elif failure == "wrong_event":
        state.run["event"] = "pull_request"
    elif failure == "unfinished":
        state.run["status"] = "in_progress"
    elif failure == "missing_job":
        state.jobs["jobs"].pop()
    elif failure == "job_failure":
        state.jobs["jobs"][-1]["conclusion"] = "failure"
    else:
        state.jobs["headSha"] = "b" * 40
    with pytest.raises(ValueError):
        subject.verify(REPO, 99, state.source, state.output)
    assert not state.output.exists()
    assert not any(c[:2] == ("release", "download") for c in state.calls)


@pytest.mark.parametrize("failure", ["wrong_source", "dirty"])
def test_checkout_must_match_exact_unchanged_source(fixture, failure):
    setattr(fixture, failure, True)
    with pytest.raises(ValueError):
        subject.verify(REPO, 99, fixture.source, fixture.output)
    assert not fixture.output.exists()


@pytest.mark.parametrize(
    "failure",
    [
        "traversal",
        "duplicate",
        "size",
        "digest",
        "missing_checksum",
        "source",
        "prerelease",
        "relative_docs",
    ],
)
def test_asset_and_release_boundaries(fixture, failure):
    value = fixture.release
    if failure == "traversal":
        value["assets"][0]["name"] = "../outside"
    elif failure == "duplicate":
        value["assets"].append(copy.deepcopy(value["assets"][0]))
    elif failure == "size":
        value["assets"][0]["size"] = subject.MAX_ASSET_BYTES + 1
    elif failure == "digest":
        value["assets"][0]["digest"] = None
    elif failure == "missing_checksum":
        value["assets"].pop()
    elif failure == "source":
        value["target_commitish"] = "main"
    elif failure == "prerelease":
        value["prerelease"] = True
    else:
        value["body"] = "[notes](../docs/notes.md)"
    with pytest.raises(ValueError):
        subject.verify(REPO, 99, fixture.source, fixture.output)
    assert not fixture.output.exists()


def test_bad_download_refuses_before_production_validator(fixture):
    fixture.payloads["payload.bin"] = b"tampered bytes"
    with pytest.raises(ValueError, match="Downloaded bytes differ"):
        subject.verify(REPO, 99, fixture.source, fixture.output)
    assert not fixture.validations
    assert not (fixture.output / "release-verification.json").exists()


def test_linked_cache_is_never_overwritten(fixture, tmp_path):
    directory = fixture.output / "artifacts"
    directory.mkdir(parents=True)
    sentinel = tmp_path / "outside"
    sentinel.write_bytes(b"retain this file")
    (directory / "payload.bin").symlink_to(sentinel)
    with pytest.raises(ValueError, match="regular files"):
        subject.verify(REPO, 99, fixture.source, fixture.output)
    assert sentinel.read_bytes() == b"retain this file"


@pytest.mark.parametrize("target", ["SHA256SUMS.txt", "payload.bin"])
def test_validator_cannot_change_verified_local_bytes(fixture, target):
    fixture.during_validation = lambda directory: (directory / target).write_bytes(b"changed")
    with pytest.raises(ValueError):
        subject.verify(REPO, 99, fixture.source, fixture.output)
    assert not (fixture.output / "release-verification.json").exists()


def test_remote_replacement_during_verification_prevents_receipt(fixture):
    fixture.after_download = lambda release: release["assets"][0].update(id=300)
    with pytest.raises(ValueError, match="changed while verification"):
        subject.verify(REPO, 99, fixture.source, fixture.output)
    assert not (fixture.output / "release-verification.json").exists()


def test_published_release_requires_its_exact_git_tag(fixture):
    fixture.release["draft"] = False
    receipt = subject.verify(REPO, 99, fixture.source, fixture.output)
    assert receipt["release_state"] == "published"
    (fixture.output / "release-verification.json").unlink()
    fixture.tag_commit = "b" * 40
    with pytest.raises(ValueError, match="Published tag"):
        subject.verify(REPO, 99, fixture.source, fixture.output)
    assert not (fixture.output / "release-verification.json").exists()


def test_existing_files_are_reused_only_when_their_bytes_match(fixture):
    subject.verify(REPO, 99, fixture.source, fixture.output)
    fixture.calls.clear()
    subject.verify(REPO, 99, fixture.source, fixture.output)
    assert not any(c[:2] == ("release", "download") for c in fixture.calls)
    (fixture.output / "artifacts/payload.bin").write_bytes(b"bad cached bytes")
    fixture.calls.clear()
    subject.verify(REPO, 99, fixture.source, fixture.output)
    downloads = [c for c in fixture.calls if c[:2] == ("release", "download")]
    assert (
        len(downloads) == 1 and downloads[0][downloads[0].index("--pattern") + 1] == "payload.bin"
    )


def test_production_validator_failure_cannot_issue_a_receipt(fixture):
    def rejected(_):
        raise ValueError("Production signature rejected")

    fixture.during_validation = rejected
    with pytest.raises(ValueError, match="Production signature rejected"):
        subject.verify(REPO, 99, fixture.source, fixture.output)
    assert not (fixture.output / "release-verification.json").exists()


def test_total_download_and_asset_count_are_bounded(fixture):
    original = copy.deepcopy(fixture.release)
    fixture.release["assets"] *= subject.MAX_ASSETS + 1
    with pytest.raises(ValueError, match="exceeds its bound"):
        subject.inventory(fixture.release, "4.1.2", COMMIT)
    original["assets"] = [
        {
            "id": index + 10,
            "name": "SHA256SUMS.txt" if index == 0 else f"part-{index}",
            "state": "uploaded",
            "size": subject.MAX_ASSET_BYTES,
            "digest": "sha256:" + "a" * 64,
        }
        for index in range(5)
    ]
    with pytest.raises(ValueError, match="total bound"):
        subject.inventory(original, "4.1.2", COMMIT)


def test_release_validator_does_not_inherit_github_credentials(fixture, monkeypatch):
    credentials = {"GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"}
    for name in credentials:
        monkeypatch.setenv(name, "fixture-only-credential")
    monkeypatch.setenv("MNEMION_VERIFICATION_FIXTURE", "keep ordinary environment")
    subject.verify(REPO, 99, fixture.source, fixture.output)
    assert credentials.isdisjoint(fixture.validation_environment)
    assert (
        fixture.validation_environment["MNEMION_VERIFICATION_FIXTURE"]
        == "keep ordinary environment"
    )
