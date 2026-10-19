"""Real Git folding must retain history and never reintroduce withdrawn text."""

from datetime import datetime, timezone
import json

import pytest

from mnemion.connectors.journal_projection import project_documents
from mnemion.connectors.protocol import Document
from mnemion.journal.format import JournalError
from mnemion.journal.git import GitJournal
from mnemion.journal.notes import note_path, notes_prefix, validate_note
from service_tests.test_memory_journal import commit_file, configure, entry, git, revision

NOW = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
OLD = datetime(2026, 10, 17, 22, tzinfo=timezone.utc)
RECENT = datetime(2026, 10, 18, 22, tzinfo=timezone.utc)


def content(destination, path):
    return git(destination.local_repository, "show", "main:" + path)


def paths(destination):
    return (
        git(destination.local_repository, "ls-tree", "-r", "--name-only", "main")
        .decode()
        .splitlines()
    )


def test_fold_preserves_bytes_uses_latest_revision_and_only_moves_closed_old_days(tmp_path):
    first = entry(ts=OLD, subject="Billing decision", text="An older question.")
    latest = revision(first, ts=RECENT, text="The current answer is PostgreSQL.")
    destination = configure(tmp_path, first)
    publisher = GitJournal(destination)
    publisher.publish([first, latest])
    catalog = content(destination, destination.prefix + "/catalog.json")
    report = publisher.fold(now=NOW)
    assert report["notes"] == 1 and report["archived_files"] == 1
    assert report["pending_files"] == report["pending_notes"] == 0
    assert (
        content(destination, destination.prefix + "/_archive/" + first.relative_path)
        == first.line()
    )
    assert content(destination, destination.prefix + "/" + latest.relative_path) == latest.line()
    assert destination.prefix + "/" + first.relative_path not in paths(destination)
    assert content(destination, destination.prefix + "/catalog.json") == catalog
    note = content(destination, note_path(destination, first.memory_id))
    assert latest.text.encode() in note and first.text.encode() not in note
    assert validate_note(note, destination, first.memory_id)["version"] == latest.version
    repeated = publisher.fold(now=NOW)
    assert repeated["commit"] == report["commit"]
    assert repeated["notes"] == repeated["archived_files"] == 0


@pytest.mark.parametrize("action,state", [("forget", "forgotten"), ("quarantine", "quarantined")])
def test_denials_clear_views_in_same_push_and_old_views_never_replay(tmp_path, action, state):
    first = entry(ts=OLD, text="Text that must leave the active library.")
    destination = configure(tmp_path, first)
    publisher = GitJournal(destination)
    publisher.publish([first])
    publisher.fold(now=NOW)
    original_view = content(destination, note_path(destination, first.memory_id))
    denied = revision(first, ts=NOW, action=action, text=None)
    publisher.publish([denied])
    note = content(destination, note_path(destination, first.memory_id))
    assert first.text.encode() not in note
    assert validate_note(note, destination, first.memory_id)["state"] == state
    report = publisher.fold(now=NOW)
    assert report["active_memories"] == 0
    documents = [
        Document(
            external_id=path,
            revision="fixture",
            title=path,
            text=content(destination, path).decode(),
            metadata={"path": path},
        )
        for path in paths(destination)
    ]
    for path, value in [
        ("copied-view.md", original_view.decode()),
        (note_path(destination, first.memory_id), first.text),
    ]:
        documents.insert(
            0,
            Document(
                external_id=path,
                revision="old-view",
                title=path,
                text=value,
                metadata={"path": path},
            ),
        )
    assert [item for item in project_documents(documents) if item is not None] == []


def test_partial_note_batches_leave_history_until_the_entire_projection_is_ready(tmp_path):
    first = entry(ts=OLD)
    other = entry(
        ts=OLD, tenant_id=first.tenant_id, space_id=first.space_id, text="Another memory."
    )
    destination = configure(tmp_path, first).model_copy(update={"max_batch_entries": 1})
    publisher = GitJournal(destination)
    publisher.publish([first])
    publisher.publish([other])
    one = publisher.fold(now=NOW)
    assert one["notes"] == 1 and one["pending_notes"] == 1 and one["archived_files"] == 0
    assert all(
        destination.prefix + "/" + record.relative_path in paths(destination)
        for record in [first, other]
    )
    two = publisher.fold(now=NOW)
    assert two["notes"] == 1 and two["pending_notes"] == 0
    assert two["archived_files"] == two["pending_files"] == 1
    three = publisher.fold(now=NOW)
    assert three["archived_files"] == 1 and three["pending_files"] == 0
    for record in [first, other]:
        assert (
            content(destination, destination.prefix + "/_archive/" + record.relative_path)
            == record.line()
        )
        assert record.text.encode() in content(
            destination, note_path(destination, record.memory_id)
        )


def test_concurrent_writer_is_reprojected_before_any_archive_commit(tmp_path):
    first = entry(ts=OLD, text="Earlier answer.")
    destination = configure(tmp_path, first)
    publisher = GitJournal(destination)
    publisher.publish([first])
    peer = GitJournal(destination.model_copy(update={"state_directory": tmp_path / "peer"}))
    latest = revision(first, ts=RECENT, text="Answer from the concurrent writer.")
    callbacks = []

    def race():
        callbacks.append(True)
        if len(callbacks) == 1:
            peer.publish([latest])

    report = publisher.fold(now=NOW, before_push=race)
    assert report["attempts"] == 2
    assert latest.text.encode() in content(destination, note_path(destination, first.memory_id))
    later = revision(latest, ts=OLD, text="Late record in an already archived day.")
    peer.publish([later])
    assert destination.prefix + "/" + first.relative_path not in paths(destination)
    assert later.line() in content(
        destination, destination.prefix + "/_archive/" + later.relative_path
    )
    publisher.fold(now=NOW)
    assert later.text.encode() in content(destination, note_path(destination, first.memory_id))


def test_unrelated_files_and_hand_edits_are_preserved_until_the_source_changes(tmp_path):
    first = entry(ts=OLD)
    destination = configure(tmp_path, first)
    original = commit_file(
        destination.local_repository,
        notes_prefix(destination) + "/personal.md",
        b"Keep my notes.\n",
    )
    publisher = GitJournal(destination)
    publisher.publish([first])
    report = publisher.fold(now=NOW)
    assert report["commit"] != original
    assert content(destination, notes_prefix(destination) + "/personal.md") == b"Keep my notes.\n"
    path = note_path(destination, first.memory_id)
    edited = content(destination, path) + b"\nA hand edit remains in Git history.\n"
    commit_file(destination.local_repository, path, edited, head=report["commit"])
    with pytest.raises(JournalError, match="journal_note_conflict"):
        publisher.fold(now=NOW)
    assert content(destination, path) == edited
    publisher.publish([revision(first, action="forget", text=None)])
    assert (
        validate_note(content(destination, path), destination, first.memory_id)["state"]
        == "forgotten"
    )


def test_incomplete_inventory_and_changed_authority_do_not_archive(tmp_path):
    first = entry(ts=OLD)
    destination = configure(tmp_path, first)
    publisher = GitJournal(destination)
    report = publisher.publish([first])

    def revoked():
        raise JournalError("journal_policy_changed")

    with pytest.raises(JournalError, match="journal_policy_changed"):
        publisher.fold(now=NOW, before_push=revoked)
    assert (
        git(destination.local_repository, "rev-parse", "main").decode().strip() == report["commit"]
    )
    catalog = content(destination, destination.prefix + "/catalog.json").replace(
        b'"records":1', b'"records":2'
    )
    commit_file(
        destination.local_repository,
        destination.prefix + "/catalog.json",
        catalog,
        head=report["commit"],
    )
    with pytest.raises(JournalError, match="journal_incomplete_inventory"):
        publisher.fold(now=NOW)
    assert destination.prefix + "/" + first.relative_path in paths(destination)


def test_empty_journal_and_minimum_age(tmp_path):
    destination = configure(tmp_path, entry())
    publisher = GitJournal(destination)
    assert publisher.fold(now=NOW)["commit"] is None
    for hours in [0, 23, True, 8761]:
        with pytest.raises(ValueError):
            publisher.fold(now=NOW, after_hours=hours)
    with pytest.raises(ValueError):
        publisher.fold(now=NOW.replace(tzinfo=None))


def test_archive_merges_an_intact_reappearing_file_without_discarding_its_bytes(tmp_path):
    first = entry(ts=OLD)
    destination = configure(tmp_path, first)
    publisher = GitJournal(destination)
    publisher.publish([first])
    folded = publisher.fold(now=NOW)
    # A second older host copied a differently serialized, but identical,
    # operation back into the active folder. Preserve its actual bytes too.
    copied = json.dumps(first.model_dump(mode="json"), ensure_ascii=False).encode() + b"\n"
    commit_file(
        destination.local_repository,
        destination.prefix + "/" + first.relative_path,
        copied,
        head=folded["commit"],
    )
    report = publisher.fold(now=NOW)
    assert report["duplicates"] == 1 and report["archived_files"] == 1
    assert (
        content(destination, destination.prefix + "/_archive/" + first.relative_path)
        == first.line() + copied
    )
    repeated = publisher.fold(now=NOW)
    assert repeated["records"] == 1 and repeated["duplicates"] == 1
    assert repeated["commit"] == report["commit"]
