"""Real Git rollover, cached retries and complete archive/denial replay."""

from datetime import timedelta
import io
import json
import sqlite3

import pytest

from mnemion.connectors.journal_projection import project_documents
from mnemion.connectors.protocol import Document
from mnemion.journal.format import JournalError, journal_path, parse_catalog, parse_file
from mnemion.journal.git import GitJournal
from mnemion.journal import rollover
from service_tests.test_journal_folding import NOW, OLD, content, paths
from service_tests.test_memory_journal import commit_file, configure, entry, git, revision


def records(destination):
    return [
        item
        for path in paths(destination)
        if path.endswith(".jsonl")
        for item in parse_file(io.BytesIO(content(destination, path)))
    ]


def catalog(destination):
    return parse_catalog(content(destination, destination.prefix + "/catalog.json"))


def documents(destination):
    return [
        Document(
            external_id=path,
            revision="fixture",
            title=path,
            text=content(destination, path).decode(),
            metadata={"path": path},
        )
        for path in paths(destination)
    ]


def small_limit(monkeypatch, first):
    # Each complete record still fits. A second complete record needs rollover.
    limit = len(first.line()) + 30
    monkeypatch.setattr(rollover, "MAX_FILE_BYTES", limit)
    return limit


def test_actual_twenty_megabyte_day_rolls_over_without_rewriting_sealed_history(tmp_path):
    first = entry(text="A public synthetic memory. " * 2300)
    destination = configure(tmp_path, first)
    publisher = GitJournal(destination)
    prior = [
        revision(first, version=number, ts=first.ts + timedelta(microseconds=number))
        for number in range(1, 340)
    ]
    assert sum(len(item.line()) for item in prior) > 20_000_000
    for offset in range(0, len(prior), 100):
        publisher.publish(prior[offset : offset + 100])
    day_files = [path for path in paths(destination) if path.endswith(".jsonl")]
    assert len(day_files) == 2
    assert all(len(content(destination, path)) <= 20_000_000 for path in day_files)
    assert {item.id for item in records(destination)} == {item.id for item in prior}
    assert catalog(destination).records == len(prior)
    assert catalog(destination).schema_version == 2
    base = destination.prefix + "/" + first.relative_path
    sealed = content(destination, base)
    later = revision(prior[-1], text="The next memory still publishes.")
    publisher.publish([later])
    assert content(destination, base) == sealed
    published = publisher.publish([prior[0], prior[-1], later])
    repeated = publisher.publish([prior[0], prior[-1], later])
    assert repeated["commit"] == published["commit"]
    assert repeated["append_planning"]["read_bytes"] == 0
    assert catalog(destination).records == len(prior) + 1


def test_rollover_survives_lost_receipt_another_publisher_and_conflicting_retries(
    tmp_path, monkeypatch
):
    first = entry(ts=OLD)
    limit = small_limit(monkeypatch, first)
    destination = configure(tmp_path, first)
    publisher = GitJournal(destination)
    one = publisher.publish([first])
    assert catalog(destination).schema_version == 1
    second = revision(first, ts=OLD + timedelta(seconds=1))
    two = publisher.publish([second])
    assert two["append_planning"]["rollover_files"] == 1
    assert content(destination, destination.prefix + "/" + first.relative_path) == first.line()
    replacement = GitJournal(destination.model_copy(update={"state_directory": tmp_path / "fresh"}))
    assert replacement.publish([first, second])["commit"] == two["commit"]
    assert replacement.publish([first, second])["append_planning"]["read_bytes"] == 0
    assert one["commit"] != two["commit"] and catalog(destination).records == 2
    with pytest.raises(JournalError, match="journal_entry_conflict"):
        replacement.publish([second.model_copy(update={"text": "Conflicting bytes"})])
    with pytest.raises(JournalError, match="journal_version_conflict"):
        replacement.publish([revision(second, version=second.version, text="Conflicting version")])
    assert all(
        len(content(destination, path)) <= limit
        for path in paths(destination)
        if path.endswith(".jsonl")
    )


def test_concurrent_rollover_retries_merge_both_writers_without_double_acknowledgment(
    tmp_path, monkeypatch
):
    first = entry(ts=OLD)
    small_limit(monkeypatch, first)
    destination = configure(tmp_path, first)
    publisher = GitJournal(destination)
    publisher.publish([first])
    other = GitJournal(destination.model_copy(update={"state_directory": tmp_path / "other"}))
    second, third = revision(first), revision(first, version=3)
    injected = False

    def race():
        nonlocal injected
        if not injected:
            injected = True
            other.publish([second])

    report = publisher.publish([third], before_push=race)
    assert report["attempts"] == 2
    assert {item.id for item in records(destination)} == {first.id, second.id, third.id}
    assert catalog(destination).records == 3
    assert publisher.publish([first, second, third])["commit"] == report["commit"]


def test_archived_segments_accept_late_records_and_denials_remain_complete(tmp_path, monkeypatch):
    first = entry(ts=OLD)
    small_limit(monkeypatch, first)
    second = revision(first, text="Updated decision.")
    destination = configure(tmp_path, first)
    publisher = GitJournal(destination)
    publisher.publish([first, second])
    before = {
        path: content(destination, path) for path in paths(destination) if path.endswith(".jsonl")
    }
    assert publisher.fold(now=NOW)["archived_files"] == 2
    for path, value in before.items():
        target = destination.prefix + "/_archive/" + path[len(destination.prefix) + 1 :]
        assert content(destination, target) == value
    denied = revision(second, action="forget", text=None)
    publisher.publish([denied])
    malicious = revision(denied, text="A later upsert must not undo deletion.", action="upsert")
    publisher.publish([malicious])
    publisher.fold(now=NOW)
    assert catalog(destination).records == 4
    assert len({item.id for item in records(destination)}) == 4
    assert not [item for item in project_documents(documents(destination)) if item is not None]
    selected = [
        document
        for document in documents(destination)
        if not document.text.startswith(denied.line().decode())
    ]
    with pytest.raises(JournalError, match="journal_incomplete_inventory"):
        list(project_documents(selected))


def test_rollover_catalog_upgrade_cannot_be_downgraded_or_hide_missing_segments(
    tmp_path, monkeypatch
):
    first = entry()
    small_limit(monkeypatch, first)
    destination = configure(tmp_path, first)
    publisher = GitJournal(destination)
    publisher.publish([first, revision(first)])
    head = publisher.publish([first])["commit"]
    value = json.loads(content(destination, destination.prefix + "/catalog.json"))
    value["schema_version"] = 1
    commit_file(
        destination.local_repository,
        destination.prefix + "/catalog.json",
        json.dumps(value).encode(),
        head=head,
    )
    with pytest.raises(JournalError, match="journal_remote_history_changed"):
        publisher.publish([revision(first, version=3)])
    fresh = GitJournal(destination.model_copy(update={"state_directory": tmp_path / "fresh"}))
    with pytest.raises(JournalError, match="journal_catalog_layout_mismatch"):
        fresh.publish([first])
    with pytest.raises(JournalError, match="journal_catalog_layout_mismatch"):
        fresh.fold(now=NOW)


def test_index_contains_no_memory_text_and_rebuilds_after_loss_or_damage(tmp_path, monkeypatch):
    first = entry(text="Synthetic private content must stay out of the metadata cache.")
    small_limit(monkeypatch, first)
    destination = configure(tmp_path, first)
    publisher = GitJournal(destination)
    original = publisher.publish([first, revision(first)])
    publisher.publish([first])
    cache = publisher.control / "delivery-index.sqlite3"
    assert first.text.encode() not in cache.read_bytes()
    with sqlite3.connect(cache) as db:
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 2
    cache.unlink()
    assert publisher.publish([first])["commit"] == original["commit"]
    cache.write_bytes(b"Damaged disposable metadata")
    with pytest.raises(JournalError, match="journal_delivery_index_rebuild_required"):
        publisher.publish([first])
    assert not cache.exists()
    assert publisher.publish([first])["commit"] == original["commit"]


@pytest.mark.parametrize(
    "suffix", ["part-000000", "part-0000010", "part-999999", "part-1", "PART-000001"]
)
def test_ambiguous_segment_names_are_rejected(suffix):
    first = entry()
    with pytest.raises(JournalError, match="journal_record_path_mismatch"):
        journal_path(f"{first.ts.date()}/{first.writer}.{suffix}.jsonl")


def test_series_limits_refuse_publication_without_acknowledging_new_entries(tmp_path, monkeypatch):
    first = entry()
    small_limit(monkeypatch, first)
    destination = configure(tmp_path, first)
    publisher = GitJournal(destination)
    initial = publisher.publish([first])
    monkeypatch.setattr(rollover, "MAX_SERIES_BYTES", len(first.line()))
    with pytest.raises(JournalError, match="journal_inventory_limit"):
        publisher.publish([revision(first)])
    assert (
        git(destination.local_repository, "rev-parse", "main").decode().strip() == initial["commit"]
    )


def test_sealed_objects_are_not_reread_while_a_changed_tail_is_revalidated(tmp_path, monkeypatch):
    first = entry()
    small_limit(monkeypatch, first)
    destination = configure(tmp_path, first)
    publisher = GitJournal(destination)
    second = revision(first)
    publisher.publish([first, second])
    publisher.publish([first, second])
    sealed = (
        git(
            destination.local_repository,
            "rev-parse",
            "main:" + destination.prefix + "/" + first.relative_path,
        )
        .decode()
        .strip()
    )
    original_git = publisher._git
    objects = []

    def observed(*args, **kwargs):
        if args[:2] == ("cat-file", "blob"):
            objects.append(args[2])
        return original_git(*args, **kwargs)

    monkeypatch.setattr(publisher, "_git", observed)
    third = revision(second)
    publisher.publish([third])
    assert sealed not in objects
    assert third.id in {item.id for item in records(destination)}
    with pytest.raises(JournalError, match="journal_entry_conflict"):
        publisher.publish([first.model_copy(update={"text": "A false retry"})])


def test_a_fresh_publisher_rejects_missing_numbered_parts(tmp_path, monkeypatch):
    first = entry()
    small_limit(monkeypatch, first)
    destination = configure(tmp_path, first)
    publisher = GitJournal(destination)
    head = publisher.publish([first])["commit"]
    value = json.loads(content(destination, destination.prefix + "/catalog.json"))
    value.update(schema_version=2, records=2)
    head = commit_file(
        destination.local_repository,
        destination.prefix + "/catalog.json",
        json.dumps(value).encode(),
        head=head,
    )
    third_path = f"{destination.prefix}/{first.ts.date()}/{first.writer}.part-000002.jsonl"
    commit_file(destination.local_repository, third_path, revision(first).line(), head=head)
    fresh = GitJournal(destination.model_copy(update={"state_directory": tmp_path / "fresh"}))
    with pytest.raises(JournalError, match="journal_incomplete_series"):
        fresh.publish([first])
    with pytest.raises(JournalError, match="journal_incomplete_series"):
        fresh.fold(now=NOW)
