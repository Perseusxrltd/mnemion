"""The installed migration gate cannot consume replaced or unpinned release bytes."""

import copy
import hashlib
import sys

import pytest

from deploy.installed_upgrade_probe import REPOSITORY, inventory, main


@pytest.fixture
def release():
    tag = "v4.1.0"
    binary = b"fixed installer bytes"
    digest = hashlib.sha256(binary).hexdigest()
    checksums = (digest + "  installer.exe\n").encode()

    def asset(name, value):
        return {
            "name": name,
            "state": "uploaded",
            "size": len(value),
            "digest": "sha256:" + hashlib.sha256(value).hexdigest(),
            "browser_download_url": f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}",
        }

    return (
        {
            "tag_name": tag,
            "target_commitish": "a" * 40,
            "draft": True,
            "prerelease": False,
            "published_at": None,
            "assets": [asset("installer.exe", binary), asset("SHA256SUMS.txt", checksums)],
        },
        checksums,
    )


def test_candidate_requires_the_exact_reviewed_commit_and_complete_bytes(release):
    record, checksums = release
    assert set(inventory(record, checksums, tag="v4.1.0", commit="a" * 40)) == {
        "installer.exe",
        "SHA256SUMS.txt",
    }
    with pytest.raises(ValueError, match="pinned source"):
        inventory(record, checksums, tag="v4.1.0", commit="b" * 40)
    replaced = copy.deepcopy(record)
    replaced["assets"][0]["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="inventories disagree"):
        inventory(replaced, checksums, tag="v4.1.0", commit="a" * 40)


def test_an_unpublished_previous_version_cannot_count_as_public_upgrade_acceptance(release):
    record, checksums = release
    with pytest.raises(ValueError, match="already be public"):
        inventory(record, checksums, tag="v4.1.0", commit=None)
    record.update(draft=False, published_at="2026-10-12T00:00:00Z")
    assert inventory(record, checksums, tag="v4.1.0", commit=None)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "different_repository", "unfinished"])
def test_partial_or_redirected_release_assets_are_rejected(release, mutation):
    record, checksums = release
    if mutation == "missing":
        record["assets"].pop(0)
    elif mutation == "duplicate":
        record["assets"].append(copy.deepcopy(record["assets"][0]))
    elif mutation == "different_repository":
        record["assets"][0]["browser_download_url"] = "https://example.test/installer.exe"
    else:
        record["assets"][0]["state"] = "uploading"
    with pytest.raises(ValueError):
        inventory(record, checksums, tag="v4.1.0", commit="a" * 40)


@pytest.mark.parametrize("ci,runner", [("false", "github-hosted"), ("true", "self-hosted")])
def test_personal_or_persistent_hosts_are_rejected_before_creating_state(
    tmp_path, monkeypatch, ci, runner
):
    output = tmp_path / "must-not-be-created"
    monkeypatch.setenv("CI", ci)
    monkeypatch.setenv("GITHUB_REPOSITORY", REPOSITORY)
    monkeypatch.setenv("RUNNER_ENVIRONMENT", runner)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "installed-upgrade",
            "--from-tag",
            "v4.0.14",
            "--to-tag",
            "v4.1.0",
            "--commit",
            "a" * 40,
            "--platform",
            "linux",
            "--arch",
            "x64",
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit, match="disposable CI runners"):
        main()
    assert not output.exists()
