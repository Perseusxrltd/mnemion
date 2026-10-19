"""Actual local Git, crash receipts, privacy checks and adversarial replay cases."""

from datetime import datetime, timedelta, timezone
import io
import os
import secrets
import subprocess
import sys
import threading
from uuid import uuid4

import pytest

from mnemion.journal import JournalEntry, JournalError
from mnemion.journal.config import Configuration, Destination
from mnemion.journal.format import JournalCatalog, parse_file, parse_line
from mnemion.journal.git import GitJournal
from mnemion.journal.index import journal_index
from mnemion.journal.privacy import scan
from mnemion.journal.process import run
from mnemion.journal.spool import Spool
from mnemion.local_state import lock


def entry(**changes):
    return JournalEntry(
        **{
            "id": uuid4(),
            "ts": datetime.now(timezone.utc),
            "tenant_id": uuid4(),
            "space_id": uuid4(),
            "memory_id": uuid4(),
            "version": 1,
            "writer": uuid4(),
            "text": "Billing: the PostgreSQL migration is approved.",
            **changes,
        }
    )


def revision(original, **changes):
    return JournalEntry.model_validate(
        {**original.model_dump(), "id": uuid4(), "version": original.version + 1, **changes}
    )


def git(root, *args, input=None):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], input=input, stderr=subprocess.DEVNULL
    )


def configure(tmp_path, first):
    remote = tmp_path / "team-memory.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return Destination(
        id="team",
        label="Team memory",
        tenant_id=first.tenant_id,
        space_id=first.space_id,
        state_directory=tmp_path / "journal-state",
        local_repository=remote,
    )


def commit_file(remote, path, content, *, head=None):
    if head:
        git(remote, "read-tree", head)
    else:
        git(remote, "read-tree", "--empty")
    blob = git(remote, "hash-object", "-w", "--stdin", input=content).strip().decode()
    git(remote, "update-index", "--add", "--cacheinfo", "100644", blob, path)
    tree = git(remote, "write-tree").strip().decode()
    args = [
        "-c",
        "user.name=Journal fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit-tree",
        tree,
        *(["-p", head] if head else []),
        "-m",
        "Fixture",
    ]
    commit = git(remote, *args).strip().decode()
    git(remote, "update-ref", "refs/heads/main", commit)
    return commit


def test_journal_round_trip_preserves_unicode_timezone_and_rejects_ambiguous_input():
    original = entry(
        text="Mémoire 東京 🧠", ts=datetime(2026, 10, 19, 14, tzinfo=timezone(timedelta(hours=2)))
    )
    restored = parse_line(original.line())
    assert restored == original and restored.ts.hour == 12
    for invalid in [
        original.line().rstrip(),
        b'{"id":1,"id":2}\n',
        b"{}\n",
        original.line().replace(b'"schema_version":1', b'"schema_version":true'),
        original.line().replace(b'"schema_version":1', b'"schema_version":2'),
    ]:
        with pytest.raises(JournalError):
            parse_line(invalid)
    with pytest.raises(JournalError):
        list(parse_file(io.BytesIO(original.line() + original.line()[:-4])))


def test_projection_ignores_duplicates_and_honours_forgetting_in_any_file_order(tmp_path):
    first = entry()
    changed = revision(first, text="The decision is complete.")
    forgotten = revision(changed, action="forget", text=None)
    malicious = revision(forgotten, action="upsert", text="An old copy must not resurrect this.")
    with journal_index(directory=tmp_path) as index:
        for value in [malicious, changed, first, forgotten, first]:
            index.add(value)
        assert list(index.current()) == []
        assert list(index.denials()) == [first.origin]
        assert index.describe()["duplicates"] == 1
    assert list(tmp_path.iterdir()) == []


def test_quarantine_and_current_revision_survive_dated_file_reordering(tmp_path):
    first = entry()
    hidden = revision(first, action="quarantine", text=None)
    visible = revision(hidden, action="upsert", text="Reviewed and released.")
    with journal_index(directory=tmp_path) as index:
        index.add(hidden)
        index.add(first)
        assert not list(index.current())
        index.add(visible)
        assert list(index.current()) == [visible]


def test_conflicting_identity_or_version_and_resource_limits_fail_closed(tmp_path):
    first = entry()
    for changed, code in [
        (first.model_copy(update={"text": "Changed bytes"}), "journal_entry_conflict"),
        (revision(first, version=first.version), "journal_version_conflict"),
    ]:
        with journal_index(directory=tmp_path) as index:
            index.add(first)
            with pytest.raises(JournalError, match=code):
                index.add(changed)
    with journal_index(directory=tmp_path, max_records=1) as index:
        index.add(first)
        with pytest.raises(JournalError, match="journal_inventory_limit"):
            index.add(revision(first))


@pytest.mark.parametrize("where", ["text", "metadata"])
def test_sensitive_values_are_rejected_before_any_journal_write(where):
    value = secrets.token_urlsafe(32)
    for original in [
        entry(
            **{where: ('{"password":"' + value + '"}') if where == "text" else {"password": value}}
        ),
        entry(text="Access: " + "mnm_" + value),
        entry(text="Contact private.person@example.invalid"),
        entry(text="Telephone +33 6 12 34 56 78"),
    ]:
        with pytest.raises(JournalError) as failure:
            scan(original)
        assert value not in str(failure.value) and "private.person" not in str(failure.value)
    scan(entry(text="Use your API key from the vault; never paste it here."))


def test_operator_scanner_receives_original_record_without_service_credentials(monkeypatch):
    monkeypatch.setenv("MNEMION_DATABASE_URL", "private-service-setting")
    script = "import json,sys,os; x=json.load(sys.stdin); print(json.dumps({'allow':x['text'].startswith('Billing') and 'MNEMION_DATABASE_URL' not in os.environ}))"
    scan(entry(), scanner=(sys.executable, "-c", script))
    with pytest.raises(JournalError, match="journal_scanner_rejected"):
        scan(entry(), scanner=(sys.executable, "-c", "print('{}')"))
    with pytest.raises(JournalError):
        run([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x'*65536)"], maximum=100)
    with pytest.raises(JournalError, match="journal_program_interrupted"):
        run([sys.executable, "-c", "import time; time.sleep(20)"], timeout=0.1)


@pytest.mark.parametrize(
    "changes",
    [
        {"remote": "https://user:password@example.invalid/repo", "local_repository": None},
        {"remote": "http://example.invalid/repo", "local_repository": None},
        {"remote": "https://example.invalid/repo?token=example", "local_repository": None},
        {"branch": "main:other"},
        {"branch": "--all"},
        {"prefix": "../private"},
        {"prefix": "."},
        {"prefix": "memory/.git"},
        {"prefix": "memory/CON"},
        {"scanner": ["relative-scanner"]},
    ],
)
def test_destination_rejects_credentials_unsafe_paths_refs_and_scanners(tmp_path, changes):
    first = entry()
    config = configure(tmp_path, first)
    with pytest.raises(ValueError):
        Destination.model_validate({**config.model_dump(), **changes})


def test_private_spool_replays_once_and_removes_unpublished_forgotten_content(tmp_path):
    first = entry()
    config = configure(tmp_path, first)
    spool = Spool(config)
    spool.record(first)
    Spool(config).record(first)
    assert list(spool.records()) == [first]
    with pytest.raises(JournalError, match="journal_entry_conflict"):
        spool.record(first.model_copy(update={"text": "Tampered"}))
    forgotten = revision(first, action="forget", text=None)
    spool.forget_pending_content(forgotten)
    assert list(spool.records()) == [forgotten]
    with lock(spool.root):
        spool.acknowledge([forgotten])
    assert list(spool.records()) == []
    if os.name != "nt":
        assert config.state_directory.stat().st_mode & 0o077 == 0


def test_real_git_publication_preserves_unrelated_files_and_deduplicates_retries(tmp_path):
    first = entry()
    config = configure(tmp_path, first)
    original_head = commit_file(config.local_repository, "notes/keep.md", b"Existing team notes\n")
    publisher = GitJournal(config)
    report = publisher.publish([first])
    assert report["commit"] != original_head
    assert git(config.local_repository, "show", "main:notes/keep.md") == b"Existing team notes\n"
    path = config.prefix + "/" + first.relative_path
    assert git(config.local_repository, "show", "main:" + path) == first.line()
    assert publisher.publish([first])["commit"] == report["commit"]
    changed = revision(first)
    publisher.publish([first, changed])
    assert git(config.local_repository, "show", "main:" + path) == first.line() + changed.line()


def test_remote_conflict_refetches_without_force_and_preserves_other_writer(tmp_path):
    first = entry()
    config = configure(tmp_path, first)
    publisher = GitJournal(config)
    publisher.publish([first])
    other = GitJournal(config.model_copy(update={"state_directory": tmp_path / "other-state"}))
    concurrent = revision(first)
    ours = revision(concurrent)
    injected = False

    def race():
        nonlocal injected
        if not injected:
            injected = True
            other.publish([concurrent])

    result = publisher.publish([ours], before_push=race)
    assert result["attempts"] == 2
    values = list(
        parse_file(
            io.BytesIO(
                git(
                    config.local_repository,
                    "show",
                    "main:" + config.prefix + "/" + first.relative_path,
                )
            )
        )
    )
    assert {value.id for value in values} == {first.id, concurrent.id, ours.id}


def test_changed_remote_history_and_callback_denial_cannot_publish(tmp_path):
    first = entry()
    config = configure(tmp_path, first)
    publisher = GitJournal(config)
    published = publisher.publish([first])["commit"]

    def denied():
        raise JournalError("publication_permission_revoked")

    with pytest.raises(JournalError, match="publication_permission_revoked"):
        publisher.publish([revision(first)], before_push=denied)
    assert git(config.local_repository, "rev-parse", "main").strip().decode() == published
    path = config.prefix + "/" + first.relative_path
    changed = commit_file(config.local_repository, path, b"", head=published)
    with pytest.raises(JournalError, match="journal_remote_history_changed"):
        publisher.publish([revision(first)])
    assert git(config.local_repository, "rev-parse", "main").strip().decode() == changed


def test_configuration_does_not_share_spool_or_remote_prefix_between_spaces(tmp_path):
    first = entry()
    config = configure(tmp_path, first)
    other = config.model_copy(
        update={"id": "other", "space_id": uuid4(), "state_directory": tmp_path / "other-state"}
    )
    with pytest.raises(ValueError):
        Configuration(destinations=[config, other])


def test_connector_projects_current_memories_across_active_and_archived_files():
    from mnemion.connectors.journal_projection import project_documents
    from mnemion.connectors.protocol import Document

    first = entry()
    changed = revision(first, text="The current decision.")
    other = entry(tenant_id=first.tenant_id, space_id=first.space_id)
    forgotten = revision(other, action="forget", text=None)

    def document(path, values):
        return Document(
            external_id=path,
            revision="snapshot",
            title=path,
            text=b"".join(value.line() for value in values).decode(),
            uri="https://example.invalid/repo/" + path,
            metadata={"path": path},
        )

    documents = [
        document("memory/buffer/new.jsonl", [forgotten, changed]),
        document("memory/buffer/_archive/old.jsonl", [first, other, first]),
    ]
    catalog = Document(
        external_id="catalog.json",
        revision="snapshot",
        title="Journal catalog",
        text=JournalCatalog(tenant_id=first.tenant_id, space_id=first.space_id, records=4)
        .encoded()
        .decode(),
        metadata={"path": "catalog.json"},
    )
    result = [value for value in project_documents([catalog, *documents]) if value is not None]
    assert len(result) == 1 and result[0].text == changed.text
    assert result[0].external_id == "journal:" + changed.origin
    moved = [document("memory/buffer/_archive/moved.jsonl", [changed, forgotten, first, other])]
    again = [value for value in project_documents([catalog, *moved]) if value is not None]
    assert result[0].items().__next__().external_id == again[0].items().__next__().external_id
    assert result[0].revision == again[0].revision


def test_malformed_journal_is_never_imported_as_raw_memory():
    from mnemion.connectors.journal_projection import project_documents
    from mnemion.connectors.protocol import Document

    first = entry()
    document = Document(
        external_id="part.jsonl",
        revision="snapshot",
        title="Journal",
        text=first.line().decode()[:-2],
        metadata={"path": "part.jsonl"},
    )
    with pytest.raises(JournalError):
        list(project_documents([document]))


def test_omitted_denial_or_missing_catalog_blocks_partial_journal_replay():
    from mnemion.connectors.journal_projection import project_documents
    from mnemion.connectors.protocol import Document

    original = entry()
    data = Document(
        external_id="old.jsonl",
        revision="old",
        title="Old journal",
        text=original.line().decode(),
        metadata={"path": "old.jsonl"},
    )
    catalog = Document(
        external_id="catalog.json",
        revision="current",
        title="Journal catalog",
        text=JournalCatalog(tenant_id=original.tenant_id, space_id=original.space_id, records=2)
        .encoded()
        .decode(),
        metadata={"path": "catalog.json"},
    )
    for selected in [[data], [catalog, data]]:
        with pytest.raises(JournalError, match="journal_incomplete_inventory"):
            list(project_documents(selected))


def test_duplicate_input_still_consumes_the_inventory_budget():
    first = entry()
    with journal_index(max_records=2) as index:
        index.add(first)
        index.add(first)
        with pytest.raises(JournalError, match="journal_inventory_limit"):
            index.add(first)


def test_slow_remote_publication_does_not_hold_the_local_capture_lock(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    first = entry()
    destination = configure(tmp_path, first)
    publisher = GitJournal(destination)
    waiting, release = threading.Event(), threading.Event()

    def pause():
        waiting.set()
        assert release.wait(10)

    with ThreadPoolExecutor(max_workers=2) as pool:
        publishing = pool.submit(publisher.publish, [first], before_push=pause)
        try:
            assert waiting.wait(5)
            captured = revision(first, text="Captured while another entry is publishing")
            pool.submit(Spool(destination).record, captured).result(timeout=2)
        finally:
            release.set()
        assert publishing.result(timeout=10)["entries"] == 1
    assert list(Spool(destination).records()) == [captured]


def test_operator_enrollment_is_private_and_requires_current_fingerprint_to_replace(
    tmp_path, capsys
):
    from mnemion.service.cli import main

    first = entry()
    path = tmp_path / "registry.json"
    command = [
        "journal",
        "enroll",
        "--config",
        str(path),
        "--id",
        "office",
        "--label",
        "Office",
        "--tenant",
        str(first.tenant_id),
        "--space",
        str(first.space_id),
        "--state",
        str(tmp_path / "state"),
        "--remote",
        "https://example.invalid/team/memory.git",
    ]
    assert main(command) == 0
    capsys.readouterr()
    registered = Configuration.from_file(path)
    assert registered.destinations[0].personal_data_scan
    before = path.read_bytes()
    assert main(command) == 1 and path.read_bytes() == before
    capsys.readouterr()
    assert main(command + ["--expected-fingerprint", registered.destinations[0].fingerprint]) == 0
    capsys.readouterr()
    secret = secrets.token_urlsafe(32)
    command[-1] = "https://user:" + secret + "@example.invalid/memory.git"
    assert main(command) == 1 and secret not in capsys.readouterr().out
    assert path.read_bytes() == before
