"""Owner-only, immutable closed-window reports with eight-window retention.

Only the reviewed numeric postprocessing schema is accepted. No raw reports or
live collector state enter this store. These files are private publisher output,
not a public route, backup instruction or product telemetry destination.
"""

from __future__ import annotations

from contextlib import closing
import json
import math
import os
from pathlib import Path
import sqlite3
import time

from mnemion.private_input import check_private_path
from mnemion.private_output import private_output

from .reporting import reporting_week
from .wire import VIEWS, WIRE, WireError

MAX_REPORT_BYTES = 65536
APPLICATION_ID = 0x4D4E5052
MAX_DATABASE_BYTES = 1024 * 1024
SCHEMA = """
CREATE TABLE reports (
    week INTEGER PRIMARY KEY CHECK(week BETWEEN 0 AND 1000000),
    body TEXT NOT NULL CHECK(length(body) <= 65536)
);
CREATE TRIGGER report_limit BEFORE INSERT ON reports
WHEN (SELECT count(*) FROM reports) >= 8
BEGIN SELECT RAISE(ABORT, 'telemetry_report_capacity'); END;
"""
LEGACY_CONSTANTS = {
    "window_seconds": 604800,
    "report_unit": "unverified_anonymous_report_not_a_user_or_device",
    "sampling": "one_count_weighted_local_category_in_an_independently_chosen_permitted_view",
    "confidence": 0.95,
    "confidence_assumptions": "independent_randomization_by_conforming_senders_not_authenticated_clients_or_poisoning_resistance",
    "privacy_loss_per_report": "ln(3)",
    "participation_or_lifetime_guarantee": False,
}
CONSTANTS = {
    **LEGACY_CONSTANTS,
    "confidence_assumptions": "independent_randomization_and_packet_independent_inclusion_of_correctly_marked_automatic_reports_not_authenticated_clients_or_poisoning_resistance",
    "estimation_population": "automatic_reports_only",
    "reviewed_report_use": "coarse_global_volume_only",
}


def _fraction(value) -> bool:
    return type(value) in (int, float) and 0 <= value <= 1 and math.isfinite(value)


def _report_range(bounds: object, minimum: int) -> bool:
    return (
        type(bounds) is dict
        and set(bounds) == {"minimum", "maximum_exclusive"}
        and all(type(value) is int for value in bounds.values())
        and minimum <= bounds["minimum"] <= WIRE["reporting"]["maximum_reports_per_window"]
        and not bounds["minimum"] & (bounds["minimum"] - 1)
        and bounds["maximum_exclusive"] == bounds["minimum"] * 2
    )


def validate(result: object) -> dict:
    if type(result) is not dict:
        raise WireError
    version = result.get("schema_version")
    if type(version) is not int or version not in (1, 2, WIRE["reporting"]["schema_version"]):
        raise WireError
    constants = CONSTANTS if version == 3 else LEGACY_CONSTANTS
    fields = {*constants, "schema_version", "window_week", "views"}
    if version >= 2:
        fields.add("report_range")
    if (
        set(result) != fields
        or any(
            type(result[key]) is not type(value) or result[key] != value
            for key, value in constants.items()
        )
        or type(result["window_week"]) is not int
        or not 0 <= result["window_week"] <= 1000000
        or type(result["views"]) is not list
        or len(result["views"]) != len(VIEWS)
    ):
        raise WireError
    if version >= 2 and not _report_range(
        result["report_range"], WIRE["reporting"]["minimum_reports_per_window"]
    ):
        raise WireError
    minimum_total, maximum_total = 0, 0
    for spec, item in zip(VIEWS, result["views"], strict=True):
        if (
            type(item) is not dict
            or set(item) != {"view", "unit", "state", "report_range", "estimates"}
            or item["view"] != spec["name"]
            or item["unit"] != spec.get("unit", "categorical_observation")
            or type(item["state"]) is not str
            or item["state"] not in {"insufficient_reports", "estimated", "inconsistent_reports"}
        ):
            raise WireError
        if item["state"] == "insufficient_reports":
            if item["report_range"] is not None or item["estimates"] is not None:
                raise WireError
            maximum_total += WIRE["reporting"]["minimum_reports_per_view"] - 1
            continue
        bounds = item["report_range"]
        if not _report_range(bounds, WIRE["reporting"]["minimum_reports_per_view"]):
            raise WireError
        minimum_total += bounds["minimum"]
        maximum_total += bounds["maximum_exclusive"] - 1
        if item["state"] == "inconsistent_reports":
            if item["estimates"] is not None:
                raise WireError
            continue
        estimates = item["estimates"]
        if type(estimates) is not list or len(estimates) != len(spec["values"]):
            raise WireError
        for label, estimate in zip(spec["values"], estimates, strict=True):
            if (
                type(estimate) is not dict
                or set(estimate) != {"value", "state", "fraction", "interval"}
                or estimate["value"] != label
                or type(estimate["state"]) is not str
                or estimate["state"] not in {"estimated", "insufficient_precision"}
            ):
                raise WireError
            if estimate["state"] == "insufficient_precision":
                if estimate["fraction"] is not None or estimate["interval"] is not None:
                    raise WireError
            else:
                interval = estimate["interval"]
                if (
                    not _fraction(estimate["fraction"])
                    or type(interval) is not list
                    or len(interval) != 2
                    or not all(_fraction(value) for value in interval)
                    or not interval[0] <= estimate["fraction"] <= interval[1]
                ):
                    raise WireError
    if version >= 2 and (
        minimum_total >= result["report_range"]["maximum_exclusive"]
        # Legacy totals cover only categorical inputs. Version3 also includes
        # reviewed volume, without exposing a complementary review-mode count.
        or (version == 2 and maximum_total < result["report_range"]["minimum"])
    ):
        raise WireError
    return result


class ReportStore:
    def __init__(self, root: Path, *, clock=time.time):
        self.root, self._clock = root, clock
        if not root.is_absolute() or root.is_symlink():
            raise WireError
        if os.name == "nt":
            from mnemion.private_output import _windows_create_directory

            _windows_create_directory(root)
        else:
            root.mkdir(mode=0o700, exist_ok=True)
        check_private_path(root, directory=True)
        self.path = root / "reports.sqlite3"
        if not self.path.exists():
            with private_output(self.path):
                pass
            with closing(self._open(check_schema=False)) as database:
                database.executescript(
                    f"BEGIN IMMEDIATE; PRAGMA application_id={APPLICATION_ID}; PRAGMA user_version=1;"
                    + SCHEMA
                    + "COMMIT;"
                )
        self.prune(reporting_week(clock()))

    def _open(self, *, readonly=False, check_schema=True):
        check_private_path(self.root, directory=True)
        check_private_path(self.path)
        if self.path.stat().st_size > MAX_DATABASE_BYTES:
            raise WireError
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
            if not readonly:
                database.execute("PRAGMA secure_delete=ON")
                database.execute("PRAGMA synchronous=FULL")
                database.execute("PRAGMA max_page_count=256")
            if check_schema and (
                database.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
                or database.execute("PRAGMA user_version").fetchone()[0] != 1
                or database.execute("PRAGMA journal_mode").fetchone()[0] != "delete"
                or database.execute("SELECT count(*) FROM reports").fetchone()[0] > 8
            ):
                raise WireError
            return database
        except Exception:
            database.close()
            raise

    def prune(self, current_week: int):
        if type(current_week) is not int or not 0 <= current_week <= 1000000:
            raise WireError
        with closing(self._open()) as database:
            database.execute("BEGIN IMMEDIATE")
            database.execute(
                "DELETE FROM reports WHERE week < ?",
                (current_week - WIRE["reporting"]["retained_windows"],),
            )
            database.commit()

    def __call__(self, result: dict):
        validate(result)
        current = reporting_week(self._clock())
        week = result["window_week"]
        if not current - WIRE["reporting"]["retained_windows"] <= week < current:
            raise WireError
        raw = json.dumps(result, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(raw) > MAX_REPORT_BYTES:
            raise WireError
        with closing(self._open()) as database:
            database.execute("BEGIN IMMEDIATE")
            database.execute(
                "DELETE FROM reports WHERE week < ?",
                (current - WIRE["reporting"]["retained_windows"],),
            )
            # No update/upsert: a second process cannot replace a released
            # view of this week. SQLite commits the complete document or none.
            database.execute("INSERT INTO reports VALUES (?, ?)", (week, raw.decode("utf-8")))
            database.commit()

    def reports(self) -> list[dict]:
        current = reporting_week(self._clock())
        self.prune(current)
        result = []
        with closing(self._open(readonly=True)) as database:
            for week, body in database.execute(
                "SELECT week, body FROM reports WHERE week >= ? AND week < ? ORDER BY week LIMIT 8",
                (current - WIRE["reporting"]["retained_windows"], current),
            ):
                if type(body) is not str or len(body.encode("utf-8")) > MAX_REPORT_BYTES:
                    raise WireError
                report = validate(json.loads(body))
                if report["window_week"] != week:
                    raise WireError
                result.append(report)
        return result
