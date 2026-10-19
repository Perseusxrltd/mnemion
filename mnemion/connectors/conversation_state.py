"""Private metadata checkpoints; no source bodies or credentials are cached."""

from contextlib import contextmanager
import json
import sqlite3

from .. import local_state
from ..private_output import private_output
from .providers import ProviderError

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    scope TEXT PRIMARY KEY, state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS segments (
    scope TEXT NOT NULL, start INTEGER NOT NULL, refs TEXT NOT NULL,
    seen TEXT NOT NULL, PRIMARY KEY(scope,start)
);
CREATE TABLE IF NOT EXISTS events (
    scope TEXT NOT NULL, session TEXT NOT NULL, event TEXT NOT NULL,
    digest TEXT NOT NULL, position INTEGER NOT NULL,
    PRIMARY KEY(scope,session,event)
);
CREATE INDEX IF NOT EXISTS events_position ON events(scope,position);
"""


class CaptureState:
    def __init__(self, connection, scope):
        self.connection, self.scope = connection, scope

    def read(self):
        row = self.connection.execute(
            "SELECT state FROM files WHERE scope=?", (self.scope,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def rewind_events(self, start):
        self.connection.execute(
            "DELETE FROM events WHERE scope=? AND position>=?", (self.scope, start)
        )

    def event(self, session, event, digest, position):
        old = self.connection.execute(
            "SELECT digest FROM events WHERE scope=? AND session=? AND event=?",
            (self.scope, session, event),
        ).fetchone()
        if old:
            if old[0] != digest:
                raise ProviderError("conversation_event_conflict")
            return False
        self.connection.execute(
            "INSERT INTO events(scope,session,event,digest,position) VALUES(?,?,?,?,?)",
            (self.scope, session, event, digest, position),
        )
        return True

    def references(self, before, scan):
        for start, refs in self.connection.execute(
            "SELECT start,refs FROM segments WHERE scope=? AND start<? ORDER BY start",
            (self.scope, before),
        ):
            self.connection.execute(
                "UPDATE segments SET seen=? WHERE scope=? AND start=?",
                (scan, self.scope, start),
            )
            yield json.loads(refs)

    def segment(self, start, items, scan, *, reuse=False):
        previous = (
            self.connection.execute(
                "SELECT refs FROM segments WHERE scope=? AND start=?", (self.scope, start)
            ).fetchone()
            if reuse
            else None
        )
        known = (
            {(value["external_id"], value["revision"]) for value in json.loads(previous[0])}
            if previous
            else set()
        )
        refs = [{"external_id": item.external_id, "revision": item.revision} for item in items]
        self.connection.execute(
            "INSERT INTO segments(scope,start,refs,seen) VALUES(?,?,?,?) "
            "ON CONFLICT(scope,start) DO UPDATE SET refs=excluded.refs,seen=excluded.seen",
            (self.scope, start, json.dumps(refs, separators=(",", ":")), scan),
        )
        return known

    def commit(self, value, scan):
        self.connection.execute(
            "DELETE FROM segments WHERE scope=? AND seen<>?", (self.scope, scan)
        )
        self.connection.execute(
            "INSERT INTO files(scope,state) VALUES(?,?) "
            "ON CONFLICT(scope) DO UPDATE SET state=excluded.state",
            (self.scope, json.dumps(value, separators=(",", ":"))),
        )
        self.connection.commit()

    def invalidate(self):
        self.connection.rollback()
        self.connection.execute("DELETE FROM files WHERE scope=?", (self.scope,))
        self.connection.commit()


@contextmanager
def capture_state(directory, owner, scope):
    """Hold one OS lock and commit metadata only after the service acknowledges."""
    try:
        root = local_state.directory(directory)
        with local_state.lock(root):
            marker = root / "source.json"
            try:
                local_state.write(marker, owner, replace=False)
            except FileExistsError:
                if local_state.read(marker) != owner:
                    raise ProviderError("conversation_cache_source_mismatch") from None
            path = root / "capture.sqlite3"
            if not path.exists():
                with private_output(path):
                    pass
            for candidate in (path, root / "capture.sqlite3-journal"):
                if candidate.exists() or candidate.is_symlink():
                    local_state._regular(candidate)
            connection = sqlite3.connect(path)
            try:
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.execute("PRAGMA cache_size=-2048")
                connection.execute("PRAGMA temp_store=MEMORY")
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("PRAGMA max_page_count=262144")
                connection.executescript(SCHEMA)
                connection.execute("BEGIN IMMEDIATE")
                yield CaptureState(connection, scope)
            finally:
                connection.rollback()
                connection.close()
    except sqlite3.Error:
        raise ProviderError("conversation_checkpoint_unavailable") from None
    except local_state.LocalSetupError:
        raise ProviderError("conversation_checkpoint_not_private") from None
