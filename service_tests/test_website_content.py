"""Invalid or unpublished Git documentation must preserve the previous public copy."""

import json
from pathlib import Path
import shutil

from jsonschema import ValidationError
import pytest

from deploy import website_content as website


@pytest.fixture
def source(tmp_path):
    root = Path(__file__).resolve().parents[1]
    for name in [website.SOURCE, website.SCHEMA, "deploy/published-release.json"]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    content = website.read_json(tmp_path / website.SOURCE)

    def guides(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"doc", "updatesDoc"}:
                    path = tmp_path / item
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("# Published guide\n")
                guides(item)
        elif isinstance(value, list):
            for item in value:
                guides(item)

    guides(content)
    website.publish(tmp_path, write=True)
    return tmp_path


def edit(root, change):
    path = root / website.SOURCE
    value = website.read_json(path)
    change(value)
    path.write_text(json.dumps(value, ensure_ascii=False))


def test_git_content_publication_is_idempotent_and_updates_only_valid_text(source):
    target = source / website.OUTPUT
    before = target.stat().st_mtime_ns
    assert not website.publish(source, write=True)["changed"]
    assert target.stat().st_mtime_ns == before
    edit(source, lambda value: value["overview"].update(body="New reviewed public text."))
    assert website.publish(source, write=True)["written"]
    assert website.read_json(target)["content"]["overview"]["body"] == "New reviewed public text."


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value["hero"]["heading"].__setitem__(0, "<script>unsafe</script>"),
        lambda value: value["hero"]["heading"].__setitem__(0, "x" * 81),
        lambda value: value["setup"]["steps"][0]["links"][0].update(doc="docs/../../private.md"),
        lambda value: value["project"].update(href="https://other.example"),
        lambda value: value.update(schema_version=2),
    ],
)
def test_invalid_content_preserves_previous_manifest(source, change):
    before = (source / website.OUTPUT).read_bytes()
    edit(source, change)
    with pytest.raises(ValidationError):
        website.publish(source, write=True)
    assert (source / website.OUTPUT).read_bytes() == before


def test_future_release_content_waits_without_replacing_the_last_public_copy(source):
    before = (source / website.OUTPUT).read_bytes()
    edit(source, lambda value: value.update(minimum_release="99.0.0"))
    result = website.publish(source, write=True)
    assert result["held_for_release"] and not result["written"]
    assert (source / website.OUTPUT).read_bytes() == before


def test_text_rejected_by_the_consumer_is_not_published(source):
    before = (source / website.OUTPUT).read_bytes()
    edit(source, lambda value: value["overview"].update(body=" Padded text "))
    with pytest.raises(ValueError, match="surrounding whitespace"):
        website.publish(source, write=True)
    assert (source / website.OUTPUT).read_bytes() == before


def test_missing_or_external_guide_cannot_be_published(source, tmp_path):
    guide = source / "docs/service/sign-in.md"
    guide.unlink()
    with pytest.raises(ValueError, match="guide"):
        website.publish(source, write=True)
    outside = tmp_path.parent / (tmp_path.name + "-external.md")
    outside.write_text("# External\n")
    guide.symlink_to(outside)
    try:
        with pytest.raises(ValueError, match="guide"):
            website.publish(source, write=True)
    finally:
        outside.unlink()


def test_duplicate_or_oversized_json_fails_before_any_publication(source):
    path = source / website.SOURCE
    before = (source / website.OUTPUT).read_bytes()
    for text in ['{"schema_version":1,"schema_version":1}', "x" * (website.MAX_BYTES + 1)]:
        path.write_text(text)
        with pytest.raises(ValueError):
            website.publish(source, write=True)
        assert (source / website.OUTPUT).read_bytes() == before


def test_content_documents_remain_eligible_for_documentation_only_push_checks():
    from deploy.ci_scope import documentation

    assert all(documentation(path) for path in [website.SOURCE, website.SCHEMA, website.OUTPUT])
    assert not documentation("deploy/website_content.py")
    assert not documentation(".github/workflows/website-release.yml")
