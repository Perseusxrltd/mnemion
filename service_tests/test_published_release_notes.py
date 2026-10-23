from copy import deepcopy

import pytest

from deploy import published_release_notes as notes

COMMIT = "a" * 40


@pytest.fixture
def publication(tmp_path, monkeypatch):
    for name, text in {
        "docs/releases/4.46.3.md": (
            "# Mnemion 4.46.3\n\nPublished release. "
            "[New proof](../validation/new.md) and [status](../RELEASE_STATUS.md).\n"
        ),
        "docs/releases/4.46.4.md": "# Mnemion 4.46.4\n\nFuture work.\n",
        "docs/validation/new.md": "Qualified after publication.\n",
        "docs/RELEASE_STATUS.md": "Maintained status.\n",
    }.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    release = {
        "id": 17,
        "tag_name": "v4.46.3",
        "target_commitish": "b" * 40,
        "draft": False,
        "prerelease": False,
        "published_at": "2026-10-23T14:50:04Z",
        "html_url": f"{notes.ORIGIN}/releases/tag/v4.46.3",
        "body": "Old candidate notes.",
        "assets": [
            {"id": 23, "name": "installer.exe", "size": 123, "digest": "sha256:" + "c" * 64}
        ],
    }
    mutations = []

    def api(path, body=None):
        assert path in {"releases/latest", "releases/17"}
        if body is not None:
            assert path == "releases/17"
            mutations.append(deepcopy(body))
            release.update(body)
        return deepcopy(release)

    monkeypatch.setattr(notes, "api", api)
    monkeypatch.setattr(
        notes, "git", lambda root, *args: COMMIT if args == ("rev-parse", "HEAD") else ""
    )
    return tmp_path, release, mutations


def test_current_git_docs_update_only_published_body_and_second_sync_does_nothing(publication):
    root, release, mutations = publication
    before = notes.identity(release)
    result = notes.synchronize(root, write=True)
    assert result["version"] == "4.46.3" and result["written"] is True
    assert len(mutations) == 1 and set(mutations[0]) == {"body"}
    assert notes.identity(release) == before
    assert f"/blob/{COMMIT}/docs/validation/new.md" in release["body"]
    assert "/blob/main/docs/RELEASE_STATUS.md" in release["body"]
    assert "v4.46.3/docs/validation/new.md" not in release["body"]
    assert "Future work" not in release["body"]
    assert notes.synchronize(root, write=True)["changed"] is False
    assert len(mutations) == 1


def test_preview_and_uncommitted_documentation_cannot_write(publication, monkeypatch):
    root, release, mutations = publication
    assert notes.synchronize(root)["written"] is False
    monkeypatch.setattr(
        notes,
        "git",
        lambda root, *args: (
            COMMIT if args == ("rev-parse", "HEAD") else " M docs/releases/4.46.3.md"
        ),
    )
    with pytest.raises(ValueError, match="Commit the reviewed"):
        notes.synchronize(root, write=True)
    assert mutations == [] and release["body"] == "Old candidate notes."


@pytest.mark.parametrize(
    "change",
    [
        {"draft": True},
        {"prerelease": True},
        {"tag_name": "v4.46.3-preview"},
        {"html_url": "https://example.org/release"},
        {"target_commitish": "main"},
    ],
)
def test_noncanonical_or_unpublished_release_is_preserved(publication, change):
    root, release, mutations = publication
    release.update(change)
    with pytest.raises(ValueError):
        notes.synchronize(root, write=True)
    assert mutations == []


def test_release_changed_during_review_is_not_overwritten(publication, monkeypatch):
    root, release, mutations = publication
    original = notes.api

    def changed(path, body=None):
        if path == "releases/17" and body is None:
            release["body"] = "Newer publication description."
        return original(path, body)

    monkeypatch.setattr(notes, "api", changed)
    with pytest.raises(RuntimeError, match="changed during review"):
        notes.synchronize(root, write=True)
    assert mutations == []


def test_missing_post_release_documentation_cannot_publish_a_broken_link(publication):
    root, _, mutations = publication
    (root / "docs/validation/new.md").unlink()
    with pytest.raises(ValueError, match="does not exist"):
        notes.synchronize(root, write=True)
    assert mutations == []
