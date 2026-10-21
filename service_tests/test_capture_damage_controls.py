"""An unavailable capture enrollment must not prevent an evidence-preserving pause."""

import base64
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mnemion import desktop_capture as capture, desktop_sources as desktop, local_state
from mnemion.connectors.conversation_inbox import InboxError
from service_tests.test_desktop_durable_capture import (
    conversation_source as conversation_source,
    custody as custody,
    encoded,
    enrolled as enrolled,
    offline,
)


@pytest.mark.parametrize("damage", ["missing_enrollment", "invalid_enrollment", "damaged_key"])
def test_pause_preserves_accepted_evidence_with_unavailable_enrollment(
    enrolled, monkeypatch, damage
):
    root, source, scan, _ = enrolled
    (Path(source.path) / "accepted.jsonl").write_bytes(encoded("Keep this accepted memory"))
    with monkeypatch.context() as patch:
        offline(patch, root, source)
        assert desktop.perform(root, scan)["capture"]["pending_events"] == 1
    database = capture.inbox_path(root, source.id) / "inbox.sqlite3"
    original_database = database.read_bytes()
    marker = capture.record_path(root, source.id)
    if damage == "missing_enrollment":
        marker.unlink()
    elif damage == "invalid_enrollment":
        local_state.write(marker, {"state": "damaged"})
    else:
        saved = desktop.load(root)
        saved.sources[0].sealed_inbox_key = base64.b64encode(b"damaged protected key").decode()
        local_state.write(root / "sources.json", saved.model_dump(mode="json", exclude_none=True))
    damaged_marker = marker.read_bytes() if marker.exists() else None
    current = desktop.load(root)
    paused = current.sources[0].model_copy(update={"enabled": False})
    result = desktop.store(root, current.revision, [paused])
    assert result["sources"][0]["enabled"] is False
    reopened = desktop.load(root)
    assert reopened.sources[0].model_dump(exclude={"status_epoch"}) == paused.model_dump(
        exclude={"status_epoch"}
    )
    assert database.read_bytes() == original_database
    assert (marker.read_bytes() if marker.exists() else None) == damaged_marker

    # Stopping is permitted; it cannot repair custody or authorize a later start.
    saved_pause = (root / "sources.json").read_bytes()
    with pytest.raises(InboxError):
        desktop.store(root, reopened.revision, [paused.model_copy(update={"enabled": True})])
    assert (root / "sources.json").read_bytes() == saved_pause
    assert database.read_bytes() == original_database
    assert (marker.read_bytes() if marker.exists() else None) == damaged_marker


def test_unchanged_damaged_sibling_does_not_block_another_sources_pause(enrolled):
    root, source, scan, _ = enrolled
    current = desktop.load(root)
    sibling = desktop.SavedSource.model_validate(
        {
            **current.sources[0].model_dump(mode="json"),
            "id": str(uuid4()),
            "connector_id": str(uuid4()),
            "provider": "filesystem",
            "capture_mode": None,
            "custody": None,
            "sealed_inbox_key": None,
            "name": "Independent sibling",
        }
    )
    desktop.store(root, current.revision, [*current.sources, sibling])
    marker = capture.record_path(root, source.id)
    marker.unlink()
    current = desktop.load(root)
    updated = [
        item.model_copy(update={"enabled": False}) if item.id == sibling.id else item
        for item in current.sources
    ]
    desktop.store(root, current.revision, updated)
    reopened = desktop.load(root)
    assert not reopened.sources[1].enabled
    assert reopened.sources[0] == current.sources[0]
    assert not marker.exists()
    with pytest.raises(InboxError, match="capture_enrollment_missing"):
        desktop.perform(root, scan)
    assert not (capture.inbox_path(root, source.id) / "inbox.sqlite3").exists()


@pytest.mark.parametrize("edit", ["capture_mode", "members", "sealed_inbox_key"])
def test_pause_cannot_smuggle_an_enrollment_change_when_its_marker_is_missing(enrolled, edit):
    root, source, _, _ = enrolled
    marker = capture.record_path(root, source.id)
    marker.unlink()
    current = desktop.load(root)
    value = {
        "capture_mode": "complete",
        "members": ["different-reader"],
        "sealed_inbox_key": base64.b64encode(b"replacement protected key").decode(),
    }[edit]
    changed = current.sources[0].model_copy(update={"enabled": False, edit: value})
    original = (root / "sources.json").read_bytes()
    with pytest.raises(InboxError):
        desktop.store(root, current.revision, [changed])
    assert (root / "sources.json").read_bytes() == original
    assert not marker.exists()


@pytest.mark.parametrize("field", ["sealed_key", "sealed_inbox_key"])
@pytest.mark.parametrize("damaged", [None, "%not-base64%", "YQ=="])
def test_missing_or_malformed_saved_key_preserves_pause_and_unrelated_controls(
    enrolled, monkeypatch, field, damaged
):
    root, source, scan, _ = enrolled
    (Path(source.path) / "accepted.jsonl").write_bytes(encoded("Accepted before key loss"))
    with monkeypatch.context() as patch:
        offline(patch, root, source)
        assert desktop.perform(root, scan)["capture"]["pending_events"] == 1
    current = desktop.load(root)
    sibling = desktop.SavedSource.model_validate(
        {
            **current.sources[0].model_dump(mode="json"),
            "id": str(uuid4()),
            "connector_id": str(uuid4()),
            "provider": "filesystem",
            "capture_mode": None,
            "custody": None,
            "sealed_inbox_key": None,
            "name": "Independent source",
        }
    )
    desktop.store(root, current.revision, [*current.sources, sibling])
    value = local_state.read(root / "sources.json")
    if damaged is None:
        del value["sources"][0][field]
    else:
        value["sources"][0][field] = damaged
    local_state.write(root / "sources.json", value)
    database = capture.inbox_path(root, source.id) / "inbox.sqlite3"
    marker = capture.record_path(root, source.id)
    original_database, original_marker = database.read_bytes(), marker.read_bytes()

    current = desktop.load(root)
    assert getattr(current.sources[0], field) == damaged
    desktop.store(
        root,
        current.revision,
        [
            current.sources[0],
            current.sources[1].model_copy(update={"enabled": False}),
        ],
    )
    current = desktop.load(root)
    assert not current.sources[1].enabled
    desktop.perform(
        root,
        {
            "operation": "pause",
            "expected_revision": current.revision,
            "id": str(source.id),
        },
    )
    paused = desktop.load(root)
    saved_pause = (root / "sources.json").read_bytes()
    assert not paused.sources[0].enabled
    assert getattr(paused.sources[0], field) == damaged
    for changes in ({"enabled": True}, {"name": "Unreviewed change"}):
        with pytest.raises((ValidationError, InboxError)):
            desktop.store(
                root,
                paused.revision,
                [
                    paused.sources[0].model_copy(update=changes),
                    paused.sources[1],
                ],
            )
        assert (root / "sources.json").read_bytes() == saved_pause
    assert database.read_bytes() == original_database
    assert marker.read_bytes() == original_marker


@pytest.mark.parametrize("changed", ["origin", "key_hash"])
def test_key_loss_never_allows_retirement_of_an_unverified_enrollment(
    enrolled, monkeypatch, changed
):
    root, source, scan, _ = enrolled
    (Path(source.path) / "accepted.jsonl").write_bytes(encoded("Retain until exact revocation"))
    with monkeypatch.context() as patch:
        offline(patch, root, source)
        desktop.perform(root, scan)
    value = local_state.read(root / "sources.json")
    value["sources"][0]["enabled"] = False
    del value["sources"][0]["sealed_inbox_key"]
    local_state.write(root / "sources.json", value)
    marker = capture.record_path(root, source.id)
    record = local_state.read(marker)
    if changed == "origin":
        record["binding"]["namespace"] = "different-source"
    else:
        record["sealed_key_sha256"] = "not-an-enrollment-hash"
    local_state.write(marker, record)
    database = capture.inbox_path(root, source.id) / "inbox.sqlite3"
    before, marker_before = database.read_bytes(), marker.read_bytes()
    monkeypatch.setattr(
        capture, "Client", lambda *a, **k: pytest.fail("Unverified origin: no HTTP")
    )
    with pytest.raises(InboxError, match="capture_binding_mismatch"):
        capture.retire(
            root,
            {
                "operation": "capture_retire",
                "id": str(source.id),
                "expected_revision": value["revision"],
                "credential": None,
                "discard_local_inbox": True,
            },
        )
    assert database.read_bytes() == before
    assert marker.read_bytes() == marker_before
