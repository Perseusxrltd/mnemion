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
    }
    assert [item["id"] for item in subject.run_rows([row, newer, foreign, obsolete], release)] == [
        2
    ]


def test_generated_titles_are_text_instead_of_remote_images_or_html():
    value = subject.escaped(
        "![remote](https://example.invalid/image) <script>run()</script> | next\nrow"
    )
    assert "![" not in value and "<script>" not in value and "\\|" in value and "\n" not in value
