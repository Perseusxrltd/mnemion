"""Bounded-RAM journal projection, including duplicates and permanent denials."""

from contextlib import contextmanager
import sqlite3

from ..local_state import temporary_directory
from .format import JournalEntry, JournalError, parse_line


class JournalIndex:
    def __init__(self, connection, *, max_records=1_000_000, max_bytes=2 * 1024**3):
        self.db = connection
        self.max_records, self.max_bytes = max_records, max_bytes
        self.records = self.bytes = self.duplicates = 0
        self.observed_records = self.observed_bytes = 0
        self.db.executescript("""
          PRAGMA cache_size=-2048;
          PRAGMA temp_store=FILE;
          PRAGMA journal_mode=OFF;
          PRAGMA synchronous=OFF;
          CREATE TABLE seen(id TEXT PRIMARY KEY, digest TEXT NOT NULL, namespace TEXT NOT NULL);
          CREATE TABLE locations(id TEXT PRIMARY KEY, uri TEXT);
          CREATE TABLE versions(origin TEXT NOT NULL, version INTEGER NOT NULL,
                                digest TEXT NOT NULL, PRIMARY KEY(origin,version));
          CREATE TABLE latest(origin TEXT PRIMARY KEY, version INTEGER NOT NULL,
                              denied INTEGER NOT NULL, action TEXT NOT NULL, line BLOB NOT NULL);
        """)

    def add(self, entry: JournalEntry, *, uri=None):
        line = entry.line()
        digest = entry.digest
        # Repeated physical records still cost I/O and CPU, even when their
        # logical operation has already been seen.
        self.observed_records += 1
        self.observed_bytes += len(line)
        if self.observed_records > self.max_records or self.observed_bytes > self.max_bytes:
            raise JournalError("journal_inventory_limit")
        previous = self.db.execute(
            "SELECT digest FROM seen WHERE id=?", (str(entry.id),)
        ).fetchone()
        if previous:
            if previous[0] != digest:
                raise JournalError("journal_entry_conflict")
            self.duplicates += 1
            return
        self.records += 1
        self.bytes += len(line)
        # Two distinct operations must not claim the same origin/version.
        previous = self.db.execute(
            "SELECT digest FROM versions WHERE origin=? AND version=?",
            (entry.origin, entry.version),
        ).fetchone()
        if previous and previous[0] != digest:
            raise JournalError("journal_version_conflict")
        self.db.execute(
            "INSERT INTO seen VALUES (?,?,?)",
            (str(entry.id), digest, f"{entry.tenant_id}:{entry.space_id}"),
        )
        self.db.execute("INSERT INTO locations VALUES (?,?)", (str(entry.id), uri))
        self.db.execute(
            "INSERT OR IGNORE INTO versions VALUES (?,?,?)", (entry.origin, entry.version, digest)
        )
        self.db.execute(
            """
          INSERT INTO latest VALUES (?,?,?,?,?) ON CONFLICT(origin) DO UPDATE SET
            denied=max(latest.denied,excluded.denied),
            action=CASE WHEN excluded.version>latest.version THEN excluded.action ELSE latest.action END,
            line=CASE WHEN excluded.version>latest.version THEN excluded.line ELSE latest.line END,
            version=max(latest.version,excluded.version)
        """,
            (entry.origin, entry.version, int(entry.action == "forget"), entry.action, line),
        )

    def current(self):
        for (line,) in self.db.execute(
            "SELECT line FROM latest WHERE denied=0 AND action='upsert' ORDER BY origin"
        ):
            yield parse_line(line)

    def denials(self):
        for (origin,) in self.db.execute(
            "SELECT origin FROM latest WHERE denied=1 ORDER BY origin"
        ):
            yield origin

    def location(self, entry):
        row = self.db.execute("SELECT uri FROM locations WHERE id=?", (str(entry.id),)).fetchone()
        return row[0] if row else None

    def inventories(self):
        return dict(self.db.execute("SELECT namespace,count(*) FROM seen GROUP BY namespace"))

    def describe(self):
        active = self.db.execute(
            "SELECT count(*) FROM latest WHERE denied=0 AND action='upsert'"
        ).fetchone()[0]
        denied = self.db.execute("SELECT count(*) FROM latest WHERE denied=1").fetchone()[0]
        return {
            "records": self.records,
            "duplicates": self.duplicates,
            "bytes": self.bytes,
            "active_memories": active,
            "forgotten_memories": denied,
        }


@contextmanager
def journal_index(*, directory=None, **limits):
    # Private disposable SQLite keeps large histories out of Python's heap. It
    # conveys no database roles, service identities or trust in source authors.
    with temporary_directory(prefix="mnemion-journal-", dir=directory) as root:
        connection = sqlite3.connect(root / "index.sqlite3")
        try:
            yield JournalIndex(connection, **limits)
        finally:
            connection.close()
