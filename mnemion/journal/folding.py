"""Bounded, repeatable filing of complete journals into Markdown and intact archives."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import io
import time
from uuid import UUID

from .. import local_state
from .format import JournalError, MAX_FILE_BYTES, journal_path, matches_path, parse_file, parse_line
from .index import journal_index
from .notes import note_path, notes_prefix, render_note, validate_note
from .privacy import scan


@dataclass(frozen=True, slots=True)
class Blob:
    path: str
    oid: str
    size: int


def _inventory(journal, head):
    prefix, notes = journal.destination.prefix, notes_prefix(journal.destination)
    raw = journal._git("ls-tree", "-r", "-l", "-z", head, "--", prefix, notes, maximum=8 * 1024**2)
    files, views = {}, {}
    for row in raw.split(b"\0"):
        if not row:
            continue
        try:
            attributes, filename = row.split(b"\t", 1)
            mode, kind, oid, size = attributes.split()
            path = filename.decode("utf-8")
        except (ValueError, UnicodeError):
            raise JournalError("invalid_journal_git_tree") from None
        if path in {prefix, notes}:
            raise JournalError("journal_path_is_not_a_directory")
        target = None
        if path.startswith(prefix + "/") and path.endswith(".jsonl"):
            target = files
        elif path.startswith(notes + "/"):
            name = path[len(notes) + 1 :]
            try:
                if name == f"{UUID(name.removesuffix('.md'))}.md":
                    target = views
            except ValueError:
                pass  # Unrelated files are left untouched.
        if target is None:
            continue
        try:
            if mode != b"100644" or kind != b"blob":
                raise ValueError
            length = int(size)
            if not 0 <= length <= MAX_FILE_BYTES:
                raise ValueError
            target[path] = Blob(path, journal._oid(oid), length)
        except ValueError:
            raise JournalError("journal_path_is_not_a_regular_file") from None
        if len(files) + len(views) > 50_000:
            raise JournalError("journal_inventory_limit")
    if sum(blob.size for blob in files.values()) > 2 * 1024**3:
        raise JournalError("journal_inventory_limit")
    return files, views


def _read_objects(journal, objects):
    """One Git process per bounded group, rather than one per journal line/file."""
    batch, size = [], 0

    def read(group):
        maximum = sum(blob.size + 128 for blob in group)
        stream = io.BytesIO(
            journal._git(
                "cat-file",
                "--batch",
                input="".join(blob.oid + "\n" for blob in group).encode(),
                maximum=maximum,
            )
        )
        for blob in group:
            if stream.readline(128) != f"{blob.oid} blob {blob.size}\n".encode():
                raise JournalError("invalid_journal_git_object")
            data = stream.read(blob.size)
            if len(data) != blob.size or stream.read(1) != b"\n":
                raise JournalError("invalid_journal_git_object")
            yield blob, data
        if stream.read(1):
            raise JournalError("invalid_journal_git_object")

    for blob in objects:
        if batch and size + blob.size > MAX_FILE_BYTES:
            yield from read(batch)
            batch, size = [], 0
        batch.append(blob)
        size += blob.size
    if batch:
        yield from read(batch)


def _day(journal, path):
    relative = path[len(journal.destination.prefix) + 1 :]
    archived = relative.startswith("_archive/")
    if archived:
        relative = relative.removeprefix("_archive/")
    parsed, writer, part = journal_path(relative)
    return relative, parsed, writer, part, archived


def _matches(blob, content):
    if blob is None or blob.size != len(content):
        return False
    algorithm = "sha256" if len(blob.oid) == 64 else "sha1"
    return (
        hashlib.new(algorithm, f"blob {len(content)}\0".encode() + content).hexdigest() == blob.oid
    )


def _plan(journal, head, index, *, cutoff):
    destination = journal.destination
    files, views = _inventory(journal, head)
    catalog = journal._catalog(head)
    eligible = []
    series = {}
    index.db.execute("CREATE TABLE fold_origins(origin TEXT PRIMARY KEY)")
    for blob, data in _read_objects(journal, files.values()):
        relative, day, writer, part, archived = _day(journal, blob.path)
        if part and catalog.schema_version < 2:
            raise JournalError("journal_catalog_layout_mismatch")
        series.setdefault((day, writer), set()).add(part)
        old = day < cutoff.date()
        if old and not archived:
            eligible.append(blob)
        for entry in parse_file(io.BytesIO(data)):
            journal._scope(entry)
            if not matches_path(entry, relative):
                raise JournalError("journal_record_path_mismatch")
            index.add(entry, uri=blob.path)
            if old or archived:
                index.db.execute("INSERT OR IGNORE INTO fold_origins VALUES (?)", (entry.origin,))
    if any(parts != set(range(max(parts) + 1)) for parts in series.values()):
        raise JournalError("journal_incomplete_series")
    if index.records != catalog.records:
        raise JournalError("journal_incomplete_inventory")

    updates, pending_notes, written_bytes, notes = [], 0, 0, 0
    # Denials are considered before ordinary content. Only complete, current
    # journal state may create a note; neither old files nor notes stand alone.
    rows = index.db.execute(
        """SELECT l.line,l.denied,f.origin IS NOT NULL FROM latest l
           LEFT JOIN fold_origins f ON f.origin=l.origin
           ORDER BY (l.denied=1 OR l.action<>'upsert') DESC,l.origin"""
    )
    for line, denied, old in rows:
        entry = parse_line(line)
        path = note_path(destination, entry.memory_id)
        previous = views.get(path)
        if not old and previous is None:
            continue
        state = (
            "forgotten" if denied else "quarantined" if entry.action == "quarantine" else "active"
        )
        content = render_note(entry, destination, state=state, source=destination.prefix)
        if _matches(previous, content):
            continue
        if (
            notes >= destination.max_batch_entries
            or written_bytes + len(content) > destination.max_batch_bytes
        ):
            pending_notes += 1
            continue
        if previous is not None:
            data = next(_read_objects(journal, [previous]))[1]
            validate_note(data, destination, entry.memory_id)
        if state == "active":
            scan(entry, personal_data=destination.personal_data_scan, scanner=destination.scanner)
        updates.append(journal._update(path, content))
        notes += 1
        written_bytes += len(content)

    archived_files, archived_bytes = 0, 0
    # Batches can prepare notes over several runs. No day file moves until all
    # current notes required by this complete inventory have been materialized.
    if not pending_notes:
        for blob in sorted(eligible, key=lambda item: item.path)[: destination.max_batch_entries]:
            relative = blob.path[len(destination.prefix) + 1 :]
            target = destination.prefix + "/_archive/" + relative
            previous = files.get(target)
            if previous is None:
                updates.append(f"100644 {blob.oid}\t{target}\n")
            else:
                contents = dict(
                    (item.path, data) for item, data in _read_objects(journal, [previous, blob])
                )
                before, addition = contents[previous.path], contents[blob.path]
                if not (before.startswith(addition) or b"\n" + addition in before):
                    if len(before) + len(addition) > MAX_FILE_BYTES:
                        raise JournalError("journal_file_too_large")
                    if written_bytes + len(addition) > destination.max_batch_bytes:
                        continue
                    updates.append(journal._update(target, before + addition))
                    written_bytes += len(addition)
            updates.append(f"0 {'0' * len(head)}\t{blob.path}\n")
            archived_files += 1
            archived_bytes += blob.size
    return updates, {
        "notes": notes,
        "archived_files": archived_files,
        "archived_bytes": archived_bytes,
        "pending_notes": pending_notes,
        "pending_files": len(eligible) - archived_files,
        "read_bytes": sum(blob.size for blob in files.values()),
        "written_bytes": written_bytes,
        **index.describe(),
    }


def fold(journal, *, after_hours=24, now=None, before_push=None):
    if type(after_hours) is not int or not 24 <= after_hours <= 8760:
        raise ValueError("Archive only after at least 24 hours, up to one year")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Use an aware archive time")
    cutoff = now.astimezone(timezone.utc) - timedelta(hours=after_hours)
    started = time.monotonic()
    with local_state.lock(journal.control):
        for attempt in range(3):
            head = journal._fetch()
            if head is None:
                if before_push is not None:
                    before_push()
                return {
                    "commit": None,
                    "notes": 0,
                    "archived_files": 0,
                    "pending_notes": 0,
                    "pending_files": 0,
                    "read_bytes": 0,
                    "written_bytes": 0,
                }
            journal._protect_previous(head)
            journal._git("read-tree", head)
            with journal_index(directory=journal.spool.root) as index:
                updates, report = _plan(journal, head, index, cutoff=cutoff)
            commit = journal._commit_push(
                head,
                updates,
                "Organize Mnemion memory journal and archive intact records",
                before_push=before_push,
            )
            if commit is None:
                continue
            report.update(
                commit=commit,
                attempts=attempt + 1,
                elapsed_seconds=round(time.monotonic() - started, 3),
                destination_fingerprint=journal.destination.fingerprint,
            )
            local_state.write(journal.spool.root / "publication.json", report)
            return report
    raise JournalError("journal_push_rejected")
