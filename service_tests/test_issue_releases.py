"""Release labels follow public evidence and never hide a reopened report."""

import json
from types import SimpleNamespace

import pytest

from deploy import issue_releases as subject


@pytest.fixture
def report(tmp_path, monkeypatch):
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy/issue-releases.json").write_text(
        json.dumps({"schema": 1, "releases": {"4.2.3": [25]}})
    )
    directory = tmp_path / "docs/validation/releases"
    directory.mkdir(parents=True)
    receipt = directory / "4.2.3-status.json"
    receipt.write_text(
        json.dumps(
            {
                "release_checks": "passed",
                "availability": "published",
                "tag_name": "v4.2.3",
                "source_commit": "a" * 40,
            }
        )
    )
    value = SimpleNamespace(
        root=tmp_path,
        receipt=receipt,
        calls=[],
        issue={"state": "OPEN", "labels": []},
        release={
            "draft": False,
            "prerelease": False,
            "published_at": "2026-10-13T17:00:00Z",
            "target_commitish": "a" * 40,
            "tag_name": "v4.2.3",
        },
    )

    def gh(*args):
        value.calls.append(args)
        if args[0] == "api":
            return json.dumps(value.release)
        if args[:2] == ("label", "list"):
            return ""  # gh can return no JSON when the search has no match.
        if args[:2] == ("issue", "view"):
            return json.dumps(value.issue)
        if args[:2] == ("issue", "close"):
            value.issue["state"] = "CLOSED"
        if args[:2] == ("issue", "edit"):
            value.issue["labels"] = [{"name": "fixed-in:4.2.3"}]
        return ""

    monkeypatch.setattr(subject, "gh", gh)
    return value


def test_first_verified_release_labels_and_closes_once_but_reopened_report_stays_open(report):
    result = subject.reconcile(report.root, apply=True)
    assert result["labeled"] == result["closed"] == 1
    report.issue["state"] = "OPEN"
    report.calls.clear()
    result = subject.reconcile(report.root, apply=True)
    assert result["labeled"] == result["closed"] == 0
    assert not any(call[:2] in {("issue", "close"), ("issue", "edit")} for call in report.calls)


@pytest.mark.parametrize("failure", ["missing_evidence", "changed_source", "draft"])
def test_incomplete_or_changed_release_cannot_close_an_issue(report, failure):
    if failure == "missing_evidence":
        report.receipt.unlink()
        assert subject.reconcile(report.root, apply=True)["pending"] == ["4.2.3"]
    else:
        if failure == "changed_source":
            report.release["target_commitish"] = "b" * 40
        else:
            report.release["draft"] = True
        with pytest.raises(ValueError):
            subject.reconcile(report.root, apply=True)
    assert all(call[0] == "api" for call in report.calls)
