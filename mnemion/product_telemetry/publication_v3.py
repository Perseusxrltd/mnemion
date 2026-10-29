"""Immutable closed-week v3 reports. Eight windows, no raw packets, no updates.

This store is separate from the v2 report schema. It is publisher output for a
maintainer, not the local privacy-settings page and not a collector log.
"""

from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import time

from mnemion.private_input import check_private_path
from mnemion.private_output import private_output

from .aggregate_v3 import validate
from .reporting import reporting_week
from .wire_v3 import WIRE, WireV3Error

MAX_REPORT_BYTES = WIRE["storage"]["maximum_report_bytes"]
APPLICATION_ID = 0x4D4E5033
MAX_DATABASE_BYTES = WIRE["storage"]["maximum_database_bytes"]
PAGE_SIZE = WIRE["storage"]["page_size"]
RETAINED = WIRE["reporting"]["retained_windows"]
SCHEMA = f"""
CREATE TABLE reports (
    week INTEGER PRIMARY KEY CHECK(week BETWEEN 0 AND 1000000),
    body TEXT NOT NULL CHECK(length(body) <= {MAX_REPORT_BYTES})
);
CREATE TABLE publication_failures (
    week INTEGER PRIMARY KEY CHECK(week BETWEEN 0 AND 1000000),
    state TEXT NOT NULL CHECK(state = 'publication_failed')
);
CREATE TRIGGER report_limit BEFORE INSERT ON reports
WHEN (SELECT count(*) FROM reports) >= {RETAINED}
BEGIN SELECT RAISE(ABORT, 'telemetry_report_capacity'); END;
"""


class ReportStore:
    def __init__(self, root: Path, *, clock=time.time):
        self.root, self._clock = root, clock
        if not root.is_absolute() or root.is_symlink():
            raise WireV3Error
        if os.name == "nt":
            from mnemion.private_output import _windows_create_directory

            _windows_create_directory(root)
        else:
            root.mkdir(mode=0o700, exist_ok=True)
        check_private_path(root, directory=True)
        self.path = root / "reports-v3.sqlite3"
        if not self.path.exists():
            with private_output(self.path):
                pass
            with closing(self._open(check_schema=False)) as database:
                database.execute(f"PRAGMA page_size={PAGE_SIZE}")
                database.executescript(
                    f"BEGIN IMMEDIATE; PRAGMA application_id={APPLICATION_ID}; PRAGMA user_version=2;"
                    + SCHEMA
                    + "COMMIT;"
                )
        self.prune(reporting_week(clock()))

    def _open(self, *, readonly=False, check_schema=True):
        check_private_path(self.root, directory=True)
        check_private_path(self.path)
        if self.path.stat().st_size > MAX_DATABASE_BYTES:
            raise WireV3Error
        database = sqlite3.connect(
            self.path.as_uri() + ("?mode=ro" if readonly else "?mode=rw"),
            uri=True,
            timeout=0,
            isolation_level=None,
            cached_statements=4,
        )
        try:
            database.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_REPORT_BYTES * 2)
            database.execute("PRAGMA trusted_schema=OFF")
            database.execute("PRAGMA cache_size=-64")
            database.execute("PRAGMA mmap_size=0")
            database.execute(f"PRAGMA max_page_count={MAX_DATABASE_BYTES // PAGE_SIZE}")
            if not readonly:
                database.execute("PRAGMA secure_delete=ON")
                database.execute("PRAGMA synchronous=FULL")
            if check_schema and (
                database.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
                or database.execute("PRAGMA user_version").fetchone()[0] != 2
                or database.execute("PRAGMA journal_mode").fetchone()[0] != "delete"
                or database.execute("SELECT count(*) FROM reports").fetchone()[0] > RETAINED
                or database.execute("SELECT count(*) FROM publication_failures").fetchone()[0]
                > RETAINED
            ):
                raise WireV3Error
            return database
        except Exception:
            database.close()
            raise

    def prune(self, current_week: int):
        if type(current_week) is not int or not 0 <= current_week <= 1000000:
            raise WireV3Error
        with closing(self._open()) as database:
            database.execute("BEGIN IMMEDIATE")
            database.execute("DELETE FROM reports WHERE week < ?", (current_week - RETAINED,))
            database.execute(
                "DELETE FROM publication_failures WHERE week < ?", (current_week - RETAINED,)
            )
            database.commit()

    def __call__(self, result: dict):
        validate(result)
        current = reporting_week(self._clock())
        week = result["window_week"]
        if not current - RETAINED <= week < current:
            raise WireV3Error
        raw = json.dumps(result, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(raw) > MAX_REPORT_BYTES or b"packet" in raw:
            raise WireV3Error
        with closing(self._open()) as database:
            database.execute("BEGIN IMMEDIATE")
            database.execute("DELETE FROM reports WHERE week < ?", (current - RETAINED,))
            database.execute(
                "DELETE FROM publication_failures WHERE week < ?", (current - RETAINED,)
            )
            try:
                database.execute("INSERT INTO reports VALUES (?, ?)", (week, raw.decode("utf-8")))
                database.commit()
            except sqlite3.Error:
                raise WireV3Error from None

    def record_publication_failure(self, week: int) -> None:
        """Remember that a sealed week was not stored. No report body, cohort, or count."""
        current = reporting_week(self._clock())
        if type(week) is not int or not current - RETAINED <= week < current:
            raise WireV3Error
        with closing(self._open()) as database:
            database.execute("BEGIN IMMEDIATE")
            database.execute(
                "DELETE FROM publication_failures WHERE week < ?", (current - RETAINED,)
            )
            try:
                database.execute(
                    "INSERT INTO publication_failures VALUES (?, 'publication_failed')",
                    (week,),
                )
            except sqlite3.IntegrityError:
                pass
            except sqlite3.Error:
                raise WireV3Error from None
            database.commit()

    def publication_failures(self) -> list[dict]:
        current = reporting_week(self._clock())
        self.prune(current)
        found = []
        with closing(self._open(readonly=True)) as database:
            rows = database.execute(
                "SELECT week, state FROM publication_failures WHERE week >= ? AND week < ? ORDER BY week LIMIT 8",
                (current - RETAINED, current),
            )
            for week, state in rows:
                if type(week) is not int or state != "publication_failed":
                    raise WireV3Error
                found.append({"window_week": week, "state": "publication_failed"})
        return found

    def reports(self) -> list[dict]:
        current = reporting_week(self._clock())
        self.prune(current)
        result = []
        with closing(self._open(readonly=True)) as database:
            for week, body in database.execute(
                "SELECT week, body FROM reports WHERE week >= ? AND week < ? ORDER BY week LIMIT 8",
                (current - RETAINED, current),
            ):
                if type(body) is not str or len(body.encode("utf-8")) > MAX_REPORT_BYTES:
                    raise WireV3Error
                report = validate(json.loads(body))
                if report["window_week"] != week:
                    raise WireV3Error
                result.append(report)
        return result
