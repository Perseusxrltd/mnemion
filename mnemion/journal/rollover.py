"""Bounded daily journal rollover with a disposable, content-free Git object index."""

from contextlib import contextmanager
from dataclasses import dataclass
import io
import sqlite3

from .. import local_state
from ..private_output import private_output
from .format import (
    JournalError,
    MAX_FILE_BYTES,
    MAX_SERIES_FILES,
    journal_path,
    matches_path,
    parse_file,
)

MAX_SERIES_BYTES = 2 * 1024**3
MAX_SERIES_RECORDS = 1_000_000


@dataclass(frozen=True, slots=True)
class Segment:
    path: str
    relative: str
    part: int
    archived: bool
    oid: str
    size: int


def inventory(journal, head, path, *, catalog_version):
    if head is None:
        return []
    prefix = journal.destination.prefix
    relative = path[len(prefix) + 1 :]
    day, writer, _ = journal_path(relative)
    directories = [f"{prefix}/{day}", f"{prefix}/_archive/{day}"]
    raw = journal._git("ls-tree", "-r", "-l", "-z", head, "--", *directories, maximum=8 * 1024**2)
    result, total = [], 0
    for row in raw.split(b"\0"):
        if not row:
            continue
        try:
            attributes, encoded = row.split(b"\t", 1)
            mode, kind, oid, size = attributes.split()
            current = encoded.decode("utf-8")
            name = current.rsplit("/", 1)[-1]
            if name != f"{writer}.jsonl" and not name.startswith(f"{writer}.part-"):
                continue
            archived = current.startswith(prefix + "/_archive/")
            candidate = current[len(prefix) + (10 if archived else 1) :]
            parsed_day, parsed_writer, part = journal_path(candidate)
            if parsed_day != day or parsed_writer != writer:
                raise ValueError
            length = int(size)
            if mode != b"100644" or kind != b"blob" or not 0 <= length <= MAX_FILE_BYTES:
                raise ValueError
            result.append(Segment(current, candidate, part, archived, journal._oid(oid), length))
            total += length
        except (ValueError, UnicodeError):
            raise JournalError("journal_record_path_mismatch") from None
        if len(result) > MAX_SERIES_FILES * 2 or total > MAX_SERIES_BYTES:
            raise JournalError("journal_inventory_limit")
    parts = {segment.part for segment in result}
    if parts and parts != set(range(max(parts) + 1)):
        raise JournalError("journal_incomplete_series")
    if parts - {0} and catalog_version < 2:
        raise JournalError("journal_catalog_layout_mismatch")
    return sorted(result, key=lambda segment: (segment.part, segment.archived))


class DeliveryIndex:
    """Only immutable object IDs and validated event hashes are cached, never text."""

    def __init__(self, connection, fingerprint):
        self.db = connection
        self.db.executescript("""
          PRAGMA trusted_schema=OFF;
          PRAGMA foreign_keys=ON;
          PRAGMA cache_size=-2048;
          PRAGMA temp_store=FILE;
          PRAGMA journal_mode=DELETE;
          CREATE TABLE IF NOT EXISTS identity(fingerprint TEXT NOT NULL, version INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,oid TEXT NOT NULL,records INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS events(path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            id TEXT NOT NULL,digest TEXT NOT NULL,origin TEXT NOT NULL,version INTEGER NOT NULL,
            PRIMARY KEY(path,id));
          CREATE INDEX IF NOT EXISTS event_identity ON events(id);
          CREATE INDEX IF NOT EXISTS event_version ON events(origin,version);
          CREATE TEMP TABLE current_files(path TEXT PRIMARY KEY,oid TEXT NOT NULL);
        """)
        identity = self.db.execute("SELECT fingerprint,version FROM identity").fetchall()
        if identity != [(fingerprint, 1)]:
            self.db.execute("DELETE FROM events")
            self.db.execute("DELETE FROM files")
            self.db.execute("DELETE FROM identity")
            self.db.execute("INSERT INTO identity VALUES (?,1)", (fingerprint,))

    def select(self, segments):
        self.db.execute("DELETE FROM current_files")
        self.db.executemany(
            "INSERT INTO current_files VALUES (?,?)", ((s.path, s.oid) for s in segments)
        )

    def known(self, segment):
        return (
            self.db.execute(
                "SELECT 1 FROM files WHERE path=? AND oid=?", (segment.path, segment.oid)
            ).fetchone()
            is not None
        )

    def check(self, entry, digest=None):
        digest = digest or entry.digest
        rows = self.db.execute(
            """SELECT e.id,e.digest FROM events e JOIN files f ON f.path=e.path
            JOIN current_files c ON c.path=f.path AND c.oid=f.oid
            WHERE e.id=? OR (e.origin=? AND e.version=?)""",
            (str(entry.id), entry.origin, entry.version),
        ).fetchall()
        for identity, previous_digest in rows:
            if previous_digest != digest:
                raise JournalError(
                    "journal_entry_conflict"
                    if identity == str(entry.id)
                    else "journal_version_conflict"
                )
        return bool(rows)

    def remember(self, journal, segment, data):
        self.db.execute("DELETE FROM files WHERE path=?", (segment.path,))
        self.db.execute("INSERT INTO files VALUES (?,?,0)", (segment.path, segment.oid))
        count = 0
        for entry in parse_file(io.BytesIO(data)):
            journal._scope(entry)
            if not matches_path(entry, segment.relative):
                raise JournalError("journal_record_path_mismatch")
            digest = entry.digest
            self.check(entry, digest)
            self.db.execute(
                "INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)",
                (segment.path, str(entry.id), digest, entry.origin, entry.version),
            )
            count += 1
        self.db.execute("UPDATE files SET records=? WHERE path=?", (count, segment.path))

    def bounded(self, *, extra=0):
        count = self.db.execute(
            """SELECT coalesce(sum(f.records),0) FROM files f JOIN current_files c
            ON c.path=f.path AND c.oid=f.oid"""
        ).fetchone()[0]
        if count + extra > MAX_SERIES_RECORDS:
            raise JournalError("journal_inventory_limit")


@contextmanager
def delivery_index(journal):
    path = journal.control / "delivery-index.sqlite3"
    if not path.exists() and not path.is_symlink():
        with private_output(path):
            pass
    for candidate in [
        path,
        *(path.with_name(path.name + suffix) for suffix in ("-journal", "-wal", "-shm")),
    ]:
        if candidate.exists() or candidate.is_symlink():
            local_state._regular(candidate)
    connection = sqlite3.connect(path)
    try:
        with connection:
            yield DeliveryIndex(connection, journal.destination.fingerprint)
    except sqlite3.DatabaseError:
        # It is a rebuildable accelerator, never a publication receipt. Refuse
        # this attempt; the next attempt reconstructs it from immutable Git data.
        connection.close()
        for candidate in [
            path,
            *(path.with_name(path.name + suffix) for suffix in ("-journal", "-wal", "-shm")),
        ]:
            if candidate.exists() or candidate.is_symlink():
                local_state._regular(candidate)
                candidate.unlink()
        raise JournalError("journal_delivery_index_rebuild_required") from None
    finally:
        connection.close()


def append(journal, head, path, additions, index, *, catalog_version):
    segments = inventory(journal, head, path, catalog_version=catalog_version)
    index.select(segments)
    read_bytes = 0
    tail, tail_data = (segments[-1] if segments else None), None
    for segment in segments:
        if index.known(segment):
            continue
        data = journal._git("cat-file", "blob", segment.oid, maximum=MAX_FILE_BYTES)
        read_bytes += len(data)
        if len(data) != segment.size:
            raise JournalError("invalid_journal_git_object")
        index.remember(journal, segment, data)
        if segment == tail:
            tail_data = data
    index.bounded()
    new, seen, versions = [], {}, {}
    for entry in sorted(additions, key=lambda item: (item.ts, str(item.id))):
        digest = entry.digest
        if str(entry.id) in seen:
            if seen[str(entry.id)] != digest:
                raise JournalError("journal_entry_conflict")
            continue
        key = (entry.origin, entry.version)
        if key in versions and versions[key] != digest:
            raise JournalError("journal_version_conflict")
        seen[str(entry.id)], versions[key] = digest, digest
        if not index.check(entry, digest):
            new.append(entry)
    if not new:
        return [], 0, {"read_bytes": read_bytes, "written_bytes": 0, "rollover_files": 0}
    index.bounded(extra=len(new))
    if (
        sum(segment.size for segment in segments) + sum(len(entry.line()) for entry in new)
        > MAX_SERIES_BYTES
    ):
        raise JournalError("journal_inventory_limit")
    if tail is not None and tail_data is None:
        tail_data = journal._git("cat-file", "blob", tail.oid, maximum=MAX_FILE_BYTES)
        read_bytes += len(tail_data)
        if len(tail_data) != tail.size:
            raise JournalError("invalid_journal_git_object")
    target, part = (tail.path, tail.part) if tail else (path, 0)
    data = bytearray(tail_data or b"")
    tail_data = None
    updates, written, rollovers, dirty = [], 0, 0, False
    for entry in new:
        line = entry.line()
        if len(line) > MAX_FILE_BYTES:
            raise JournalError("journal_file_too_large")
        if len(data) + len(line) > MAX_FILE_BYTES:
            if dirty:
                updates.append(journal._update(target, bytes(data)))
                written += len(data)
            part += 1
            if part >= MAX_SERIES_FILES:
                raise JournalError("journal_inventory_limit")
            base = tail.path if tail else path
            folder = base.rsplit("/", 1)[0]
            target = f"{folder}/{entry.writer}.part-{part:06d}.jsonl"
            data, dirty = bytearray(), False
            rollovers += 1
        data.extend(line)
        dirty = True
    if dirty:
        updates.append(journal._update(target, bytes(data)))
        written += len(data)
    return (
        updates,
        len(new),
        {"read_bytes": read_bytes, "written_bytes": written, "rollover_files": rollovers},
    )
