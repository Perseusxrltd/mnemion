"""One private, bounded preference store for desktop and headless operators.

There are no analytics identifiers or network operations here. SQLite serializes
choices across processes; every producer must consult this same policy inside
its write transaction. Missing disclosure, damaged state and restrictive company
policy suppress collection. A saved opt-out always survives a new disclosure.
"""

from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import sys

from mnemion.private_input import check_private_path

from . import COLLECTION_AVAILABLE, COLLECTOR_URL, CONTRACT, DISCLOSURE_VERSION, SCHEMA_VERSION

APPLICATION_ID = 0x4D4E5450
MAX_DATABASE_BYTES = 96 * 1024
MAX_PENDING = 512
MAX_PENDING_AGE_SECONDS = 48 * 3600
MAX_DOCUMENT_BYTES = 8192
METRIC_GROUPS = tuple(CONTRACT["metric_groups"])
DATABASE_NAME = "product-telemetry.sqlite3"
STORAGE_VERSION = 6
CONNECTION_MODES = ("auto", "unmetered", "metered")

# Attempt accounting is not a measurement or a stable analytics identity. It
# survives opt-out and queue erasure, so changing a choice cannot buy another
# privacy/traffic allowance. Timestamps and lease tokens stay on this machine.
DELIVERY_SCHEMA = """
CREATE TABLE delivery_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    clock_ms INTEGER NOT NULL CHECK (clock_ms BETWEEN 0 AND 86400000000000),
    next_ms INTEGER NOT NULL CHECK (next_ms BETWEEN 0 AND 86400000000000),
    lease_token TEXT CHECK (lease_token IS NULL OR
        (length(lease_token)=32 AND lease_token NOT GLOB '*[^0-9a-f]*')),
    lease_deadline_ms INTEGER NOT NULL CHECK (lease_deadline_ms BETWEEN 0 AND 86400000000000)
);
INSERT INTO delivery_state VALUES (1, 0, 0, NULL, 0);
CREATE TABLE delivery_attempts (
    slot INTEGER PRIMARY KEY CHECK (slot BETWEEN 0 AND 6),
    at_ms INTEGER NOT NULL CHECK (at_ms BETWEEN 0 AND 86400000000000),
    reserved_bytes INTEGER NOT NULL CHECK (reserved_bytes = 65536)
);
"""

# One optional held packet and bounded local control metadata. Older senders
# reject storage version six instead of bypassing a newly enabled review hold.
REVIEW_SCHEMA = """
CREATE TABLE report_review (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    state TEXT NOT NULL CHECK (length(state) <= 4096)
);
INSERT INTO report_review VALUES
    (1, '{"version":1,"mode":"automatic","token":null,"outcome":"inactive","report":null}');
"""


def valid_generation(value: object) -> bool:
    """Private compare-and-set nonce; it is never a product measurement."""
    return type(value) is str and re.fullmatch(r"[0-9a-f]{32}", value) is not None


QUEUE_SCHEMA = """
CREATE TABLE producer_budget (
    scope INTEGER PRIMARY KEY CHECK (scope BETWEEN 0 AND 1023),
    count INTEGER NOT NULL CHECK (count BETWEEN 1 AND 64),
    window_day INTEGER NOT NULL CHECK (window_day BETWEEN 0 AND 1000000)
);
CREATE TRIGGER producer_budget_bound BEFORE INSERT ON producer_budget
WHEN (SELECT count(*) FROM producer_budget) >= 512
AND NOT EXISTS (SELECT 1 FROM producer_budget WHERE scope=NEW.scope)
BEGIN SELECT RAISE(ABORT, 'telemetry_queue_full'); END;
CREATE TRIGGER pending_bound BEFORE INSERT ON pending
WHEN (SELECT count(*) FROM pending) >= 512
AND NOT EXISTS (SELECT 1 FROM pending WHERE cell=NEW.cell)
BEGIN SELECT RAISE(ABORT, 'telemetry_queue_full'); END;
"""

SCHEMA = (
    """
CREATE TABLE preferences (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    revision INTEGER NOT NULL CHECK (revision BETWEEN 0 AND 2147483647),
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    disclosure_version INTEGER NOT NULL CHECK (disclosure_version BETWEEN 0 AND 1000000),
    store_generation TEXT NOT NULL CHECK (length(store_generation)=32 AND store_generation NOT GLOB '*[^0-9a-f]*'),
    connection_mode TEXT NOT NULL DEFAULT 'auto' CHECK (connection_mode IN ('auto', 'unmetered', 'metered'))
);
CREATE TABLE pending (
    cell INTEGER PRIMARY KEY CHECK (cell BETWEEN 0 AND 65535),
    count INTEGER NOT NULL CHECK (count BETWEEN 1 AND 65535),
    window_day INTEGER NOT NULL CHECK (window_day BETWEEN 0 AND 1000000)
);
"""
    + QUEUE_SCHEMA
    + DELIVERY_SCHEMA
    + REVIEW_SCHEMA
)


class PolicyError(ValueError):
    """Fixed public errors never contain paths, payloads or underlying failures."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def default_directory() -> Path:
    override = os.environ.get("MNEMION_STUDIO_USER_DATA")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "mnemion-product-telemetry"


def company_policy_file() -> Path:
    if sys.platform == "win32":
        return (
            Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
            / "Mnemion"
            / "telemetry-policy.json"
        )
    if sys.platform == "darwin":
        return Path("/Library/Application Support/Mnemion/telemetry-policy.json")
    return Path("/etc/mnemion/telemetry-policy.json")


def _absent_company_parent(selected: Path) -> bool:
    """Windows can report a missing entry for a non-directory ancestor."""
    parent = selected.parent
    for _ in range(32):
        try:
            metadata = parent.lstat()
        except FileNotFoundError:
            above = parent.parent
            if above == parent:
                return False
            parent = above
        else:
            return stat.S_ISDIR(metadata.st_mode)
    return False


def company_policy(path: Path | None = None) -> dict:
    """A machine policy can restrict choice, never enable an opted-out user."""
    selected = path if path is not None else company_policy_file()
    try:
        try:
            metadata = selected.lstat()
        except FileNotFoundError:
            if _absent_company_parent(selected):
                return {"state": "unmanaged", "enabled": True, "metric_groups": list(METRIC_GROUPS)}
            raise ValueError from None
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_DOCUMENT_BYTES:
            raise ValueError
        with selected.open("rb") as stream:
            raw = stream.read(MAX_DOCUMENT_BYTES + 1)
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise ValueError
        value = json.loads(raw)
        if (
            not isinstance(value, dict)
            or set(value) != {"schema_version", "enabled", "metric_groups"}
            or type(value["schema_version"]) is not int
            or value["schema_version"] != SCHEMA_VERSION
            or type(value["enabled"]) is not bool
            or not isinstance(value["metric_groups"], list)
            or len(value["metric_groups"]) > len(METRIC_GROUPS)
            or any(
                type(item) is not str or item not in METRIC_GROUPS
                for item in value["metric_groups"]
            )
            or len(set(value["metric_groups"])) != len(value["metric_groups"])
        ):
            raise ValueError
        return {
            "state": "restricted",
            "enabled": value["enabled"],
            "metric_groups": sorted(value["metric_groups"]),
        }
    except (OSError, ValueError, RecursionError):
        return {"state": "unreadable", "enabled": False, "metric_groups": []}


def disclosure() -> dict:
    return {
        **deepcopy(CONTRACT),
        "destination": COLLECTOR_URL,
        "collection_available": COLLECTION_AVAILABLE,
    }


def _root_safe(root: Path) -> None:
    if not root.is_absolute() or root.is_symlink():
        raise PolicyError("telemetry_storage_unavailable")
    if root.exists():
        try:
            check_private_path(root, directory=True)
        except OSError:
            raise PolicyError("telemetry_storage_unavailable")


def _file_safe(path: Path) -> bool:
    try:
        value = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(value.st_mode) or value.st_size > MAX_DATABASE_BYTES:
        raise PolicyError("telemetry_storage_unavailable")
    try:
        check_private_path(path)
    except OSError:
        raise PolicyError("telemetry_storage_unavailable")
    return True


def _connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    connection = sqlite3.connect(
        path.as_uri() + ("?mode=ro" if readonly else "?mode=rw"),
        uri=True,
        timeout=0,
        isolation_level=None,
        cached_statements=8,
    )
    try:
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 65536)
        connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 65536)
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA cache_size=-128")
        connection.execute("PRAGMA mmap_size=0")
        if not readonly:
            connection.execute("PRAGMA secure_delete=ON")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA max_page_count=24")
    except Exception:
        connection.close()
        raise
    return connection


def _preferences(connection: sqlite3.Connection) -> dict:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if (
        connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
        or version not in (1, 2, 3, 4, 5, STORAGE_VERSION)
        or connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete"
    ):
        raise PolicyError("telemetry_storage_unavailable")
    row = connection.execute(
        "SELECT revision, enabled, disclosure_version FROM preferences WHERE singleton=1"
    ).fetchone()
    if (
        row is None
        or any(type(value) is not int for value in row)
        or not 0 <= row[0] < 2147483647
        or row[1] not in (0, 1)
        or not 0 <= row[2] <= DISCLOSURE_VERSION
    ):
        raise PolicyError("telemetry_storage_unavailable")
    generation = None
    if version >= 3:
        generation = connection.execute(
            "SELECT store_generation FROM preferences WHERE singleton=1"
        ).fetchone()[0]
        if not valid_generation(generation):
            raise PolicyError("telemetry_storage_unavailable")
    connection_mode = "auto"
    if version >= 5:
        connection_mode = connection.execute(
            "SELECT connection_mode FROM preferences WHERE singleton=1"
        ).fetchone()[0]
        if type(connection_mode) is not str or connection_mode not in CONNECTION_MODES:
            raise PolicyError("telemetry_storage_unavailable")
    return {
        "revision": row[0],
        "enabled": bool(row[1]),
        "disclosure_version": row[2],
        "store_generation": generation,
        "connection_mode": connection_mode,
    }


def _queue_schema(connection: sqlite3.Connection) -> None:
    """Upgrade the unpublished controls-only store inside its caller's transaction."""
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version == STORAGE_VERSION:
        return
    _preferences(connection)
    # executescript would commit an existing transaction before executing.
    # Use individual complete SQL statements so preference and queue state
    # change atomically, including when a version-one store was opted out.
    if version == 1:
        connection.execute("DROP TRIGGER pending_bound")
        statement = ""
        for line in QUEUE_SCHEMA.splitlines(keepends=True):
            statement += line
            if sqlite3.complete_statement(statement):
                connection.execute(statement)
                statement = ""
    if version <= 2:
        connection.execute("ALTER TABLE preferences ADD COLUMN store_generation TEXT")
        connection.execute("UPDATE preferences SET store_generation=?", (secrets.token_hex(16),))
    if version < 4:
        statement = ""
        for line in DELIVERY_SCHEMA.splitlines(keepends=True):
            statement += line
            if sqlite3.complete_statement(statement):
                connection.execute(statement)
                statement = ""
    if version < 5:
        connection.execute(
            "ALTER TABLE preferences ADD COLUMN connection_mode TEXT NOT NULL DEFAULT 'auto' "
            "CHECK (connection_mode IN ('auto', 'unmetered', 'metered'))"
        )
    if version < 6:
        statement = ""
        for line in REVIEW_SCHEMA.splitlines(keepends=True):
            statement += line
            if sqlite3.complete_statement(statement):
                connection.execute(statement)
                statement = ""
    connection.execute(f"PRAGMA user_version={STORAGE_VERSION}")


def _initialize(root: Path) -> bool:
    _root_safe(root)
    if os.name == "nt":
        from mnemion.private_output import _windows_create_directory

        root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _windows_create_directory(root)
    else:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    _root_safe(root)
    path = root / DATABASE_NAME
    if _file_safe(path):
        return False
    try:
        if os.name == "nt":
            from mnemion.private_output import _windows_create_file

            descriptor = _windows_create_file(path)
        else:
            descriptor = os.open(
                path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600
            )
    except FileExistsError:
        return False
    os.close(descriptor)
    # A crash before the schema commits leaves damaged/unknown state. Never
    # turn that state into a fresh enabled preference on a later read.
    with closing(_connect(path)) as connection:
        connection.execute("PRAGMA page_size=4096")
        connection.execute("PRAGMA max_page_count=24")
        connection.executescript(
            "BEGIN IMMEDIATE;"
            f"PRAGMA application_id={APPLICATION_ID}; PRAGMA user_version={STORAGE_VERSION};"
            + SCHEMA
        )
        connection.execute(
            "INSERT INTO preferences (singleton, revision, enabled, disclosure_version, "
            "store_generation) VALUES (1, 0, 1, 0, ?)",
            (secrets.token_hex(16),),
        )
        connection.commit()
    return True


def transport_available() -> bool:
    """Configured capability only, independent of consent or a live attempt."""
    if not COLLECTION_AVAILABLE or not COLLECTOR_URL:
        return False
    from .endpoint import release_endpoint

    return release_endpoint() is not None


def status(root: Path | None = None, *, policy_path: Path | None = None) -> dict:
    from .delivery import budget_status

    root = root if root is not None else default_directory()
    company = company_policy(policy_path)
    preference = {
        "revision": 0,
        "enabled": True,
        "disclosure_version": 0,
        "store_generation": None,
        "connection_mode": "auto",
    }
    storage, pending = "new", 0
    delivery_budget = budget_status()
    try:
        _root_safe(root)
        if _file_safe(root / DATABASE_NAME):
            with closing(_connect(root / DATABASE_NAME, readonly=True)) as connection:
                connection.execute("BEGIN")
                preference = _preferences(connection)
                pending = connection.execute("SELECT count(*) FROM pending").fetchone()[0]
                if not 0 <= pending <= MAX_PENDING:
                    raise PolicyError("telemetry_storage_unavailable")
                delivery_budget = budget_status(connection)
                connection.rollback()
            storage = "ready"
    except (OSError, sqlite3.Error, ValueError):
        storage = "unreadable"
        delivery_budget.update(
            state="unavailable",
            attempts_in_rolling_week=None,
            reserved_wire_bytes_in_rolling_day=None,
        )
    if storage == "unreadable":
        reason = "storage_unavailable"
    elif not preference["enabled"]:
        reason = "user_disabled"
    elif not company["enabled"] or not company["metric_groups"]:
        reason = "company_policy"
    elif (
        preference["disclosure_version"] != DISCLOSURE_VERSION
        or preference["store_generation"] is None
    ):
        reason = "disclosure_required"
    elif not COLLECTION_AVAILABLE or COLLECTOR_URL is None:
        reason = "collection_unavailable"
    else:
        reason = "enabled"
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": preference["revision"],
        "store_generation": preference["store_generation"],
        "default_enabled": True,
        "user_enabled": preference["enabled"],
        "connection_mode": preference["connection_mode"],
        "effective_enabled": reason == "enabled",
        "reason": reason,
        "storage": storage,
        "disclosure_version": preference["disclosure_version"],
        "required_disclosure_version": DISCLOSURE_VERSION,
        "company_policy": company,
        "pending_records": pending if storage != "unreadable" else None,
        "collection_available": COLLECTION_AVAILABLE,
        "disclosure": disclosure(),
        "delivery_budget": delivery_budget,
    }


def configure(root: Path | None, request: dict, *, policy_path: Path | None = None) -> dict:
    fields = {
        "enabled",
        "expected_revision",
        "expected_generation",
        "disclosure_version",
        "connection_mode",
    }
    if (
        not isinstance(request, dict)
        or set(request) - fields
        or type(request.get("enabled")) is not bool
        or type(request.get("expected_revision")) is not int
        or not 0 <= request["expected_revision"] < 2147483647
        or type(request.get("disclosure_version", 0)) is not int
        or request.get("disclosure_version", 0) not in (0, DISCLOSURE_VERSION)
        or (
            "connection_mode" in request
            and (
                type(request["connection_mode"]) is not str
                or request["connection_mode"] not in CONNECTION_MODES
            )
        )
        or (
            request.get("expected_generation") is not None
            and not valid_generation(request["expected_generation"])
        )
    ):
        raise PolicyError("telemetry_invalid_choice")
    acknowledged = request.get("disclosure_version", 0)
    if acknowledged and (not COLLECTION_AVAILABLE or COLLECTOR_URL is None):
        raise PolicyError("telemetry_disclosure_unavailable")
    root = root if root is not None else default_directory()
    try:
        created = _initialize(root)
        with closing(_connect(root / DATABASE_NAME)) as connection:
            # An explicit human/agent privacy change may briefly wait for an
            # existing reader. Producers and delivery retain zero lock waiting.
            connection.execute("PRAGMA busy_timeout=250")
            connection.execute("BEGIN IMMEDIATE")
            previous = _preferences(connection)
            # Opt-out wins over stale UI state. Re-enabling always requires the
            # current revision and cannot undo another process's newer choice.
            stale = request["expected_revision"] != previous["revision"] or request.get(
                "expected_generation"
            ) != (None if created else previous["store_generation"])
            if request["enabled"] and stale:
                raise PolicyError("telemetry_choice_changed")
            _queue_schema(connection)
            # A stale opt-out still wins, but cannot overwrite a newer network
            # choice. Older clients that omit this field preserve it as well.
            connection_mode = (
                previous["connection_mode"]
                if stale
                else request.get("connection_mode", previous["connection_mode"])
            )
            effective_acknowledgement = acknowledged if request["enabled"] else 0
            if (
                not request["enabled"]
                or request["enabled"] != previous["enabled"]
                or effective_acknowledgement != previous["disclosure_version"]
                or connection_mode != previous["connection_mode"]
            ):
                connection.execute(
                    "UPDATE preferences SET revision=revision+1, enabled=?, disclosure_version=?, connection_mode=? WHERE singleton=1",
                    (int(request["enabled"]), effective_acknowledgement, connection_mode),
                )
            # A new choice never resurrects queued history, including enabling
            # after opt-out. secure_delete also clears freed cells in this DB.
            connection.execute("DELETE FROM pending")
            connection.execute("DELETE FROM producer_budget")
            # Cancel a reserved report without resetting spent privacy/traffic.
            connection.execute(
                "UPDATE delivery_state SET lease_token=NULL, lease_deadline_ms=0 WHERE singleton=1"
            )
            from .review_storage import invalidate

            # A choice erases the held packet, while a preselected manual
            # review mode survives enabling and never resumes by itself.
            invalidate(connection)
            connection.commit()
    except sqlite3.OperationalError as error:
        if getattr(error, "sqlite_errorcode", None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            raise PolicyError("telemetry_busy") from None
        raise PolicyError("telemetry_storage_unavailable") from None
    except (OSError, sqlite3.Error):
        raise PolicyError("telemetry_storage_unavailable") from None
    return status(root, policy_path=policy_path)


def preview(root: Path | None = None, *, policy_path: Path | None = None) -> dict:
    from .aggregate import preview as aggregate_preview
    from .catalog import coverage_specification, specification
    from .wire_v3 import format_example

    current = status(root, policy_path=policy_path)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": current,
        "outbound_body": None,
        "outbound_bytes": 0,
        "outbound_state": "not_inspected",
        "transport_available": current["delivery_budget"]["transport_available"],
        "message": "Synthetic report-format example. No actual outgoing packet was inspected.",
        "illustrative_packet": format_example(),
        "measurement_catalog": specification(),
        "workflow_coverage": coverage_specification(),
        "local_aggregates": aggregate_preview(root, policy_path=policy_path),
    }
