"""A retried release job must preserve published versions and stay a draft."""

import hashlib
import json
from pathlib import Path

import pytest

from deploy import draft_release


class GitHub:
    def __init__(self, *, draft=True, exists=True, fail_upload=False):
        self.release = {
            "id": 42,
            "tag_name": "v4.0.0",
            "draft": draft,
            "target_commitish": "a" * 40,
            "assets": [{"name": "old-manifest.json", "size": 0, "digest": None}],
        }
        self.exists = exists
        self.fail_upload = fail_upload
        self.mutations = []

    def __call__(self, *args):
        if args[0] == "api":
            if "--paginate" in args:
                return json.dumps([[self.release] if self.exists else []])
            return json.dumps(self.release)
        if args[1] == "view":
            return json.dumps({"databaseId": 42})
        self.mutations.append(args)
        if args[1] in {"create", "edit"}:
            assert "--draft" in args
            self.exists = True
            self.release["draft"] = True
            self.release["target_commitish"] = args[args.index("--target") + 1]
        elif args[1] == "upload":
            if self.fail_upload:
                raise RuntimeError("Upload interrupted")
            for filename in args[args.index("--clobber") + 1 :]:
                path = Path(filename)
                self.release["assets"] = [
                    a for a in self.release["assets"] if a["name"] != path.name
                ]
                self.release["assets"].append(
                    {
                        "name": path.name,
                        "size": path.stat().st_size,
                        "digest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
        elif args[1] == "delete-asset":
            self.release["assets"] = [a for a in self.release["assets"] if a["name"] != args[3]]
        else:
            raise AssertionError(args)
        return ""


def fixture(tmp_path, monkeypatch, github):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "app.exe").write_bytes(b"verified test payload")
    notes = tmp_path / "notes.md"
    notes.write_text("# Mnemion 4.0.0\n")
    monkeypatch.setattr(draft_release, "gh", github)
    return ("owner/repo", "b" * 40, "4.0.0", artifacts, notes)


def test_published_release_is_never_modified(tmp_path, monkeypatch):
    github = GitHub(draft=False)
    args = fixture(tmp_path, monkeypatch, github)
    with pytest.raises(RuntimeError, match="immutable"):
        draft_release.prepare(*args)
    assert github.mutations == []


@pytest.mark.parametrize("exists", [True, False])
def test_prepare_and_retry_keep_exact_assets_in_a_draft(tmp_path, monkeypatch, exists):
    github = GitHub(exists=exists)
    args = fixture(tmp_path, monkeypatch, github)
    draft_release.prepare(*args)
    draft_release.prepare(*args)
    assert github.release["draft"] is True
    assert github.release["target_commitish"] == "b" * 40
    assert [a["name"] for a in github.release["assets"]] == ["app.exe"]
    assert sum(a[1] == "create" for a in github.mutations) == (0 if exists else 1)


def test_failed_upload_does_not_delete_previous_draft_assets(tmp_path, monkeypatch):
    github = GitHub(fail_upload=True)
    args = fixture(tmp_path, monkeypatch, github)
    with pytest.raises(RuntimeError, match="interrupted"):
        draft_release.prepare(*args)
    assert github.release["draft"] is True
    assert [a["name"] for a in github.release["assets"]] == ["old-manifest.json"]
    assert not any(a[1] == "delete-asset" for a in github.mutations)


def test_api_failure_is_not_treated_as_a_missing_release(tmp_path, monkeypatch):
    calls = []

    def unavailable(*args):
        calls.append(args)
        raise RuntimeError("Authentication or API unavailable")

    args = fixture(tmp_path, monkeypatch, unavailable)
    with pytest.raises(RuntimeError, match="unavailable"):
        draft_release.prepare(*args)
    assert len(calls) == 1
    assert calls[0][0] == "api"


def test_publication_during_preparation_stops_further_changes(tmp_path, monkeypatch):
    github = GitHub()
    calls = 0

    def published_after_listing(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            github.release["draft"] = False
        return github(*args)

    args = fixture(tmp_path, monkeypatch, published_after_listing)
    with pytest.raises(RuntimeError, match="no longer"):
        draft_release.prepare(*args)
    assert github.mutations == []
