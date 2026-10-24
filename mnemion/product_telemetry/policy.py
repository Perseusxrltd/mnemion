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
import sqlite3
import stat
import sys

from . import COLLECTION_AVAILABLE, COLLECTOR_URL, CONTRACT, DISCLOSURE_VERSION, SCHEMA_VERSION

APPLICATION_ID = 0x4D4E5450
MAX_DATABASE_BYTES = 96 * 1024
MAX_PENDING = 512
MAX_PENDING_AGE_SECONDS = 48 * 3600
MAX_DOCUMENT_BYTES = 8192
METRIC_GROUPS = tuple(CONTRACT["metric_groups"])
DATABASE_NAME = "product-telemetry.sqlite3"

SCHEMA = """
CREATE TABLE preferences (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    revision INTEGER NOT NULL CHECK (revision BETWEEN 0 AND 2147483647),
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    disclosure_version INTEGER NOT NULL CHECK (disclosure_version BETWEEN 0 AND 1000000)
);
INSERT INTO preferences VALUES (1, 0, 1, 0);
CREATE TABLE pending (
    cell INTEGER PRIMARY KEY CHECK (cell BETWEEN 0 AND 65535),
    count INTEGER NOT NULL CHECK (count BETWEEN 1 AND 65535),
    window_day INTEGER NOT NULL CHECK (window_day BETWEEN 0 AND 1000000)
);
CREATE TRIGGER pending_bound BEFORE INSERT ON pending
WHEN (SELECT count(*) FROM pending) >= 512
BEGIN SELECT RAISE(ABORT, 'telemetry_queue_full'); END;
"""


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


def company_policy(path: Path | None = None) -> dict:
    """A machine policy can restrict choice, never enable an opted-out user."""
    selected = path if path is not None else company_policy_file()
    try:
        metadata = selected.lstat()
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
    except FileNotFoundError:
        return {"state": "unmanaged", "enabled": True, "metric_groups": list(METRIC_GROUPS)}
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
        metadata = root.stat()
        if not stat.S_ISDIR(metadata.st_mode):
            raise PolicyError("telemetry_storage_unavailable")
        if os.name != "nt" and (metadata.st_uid != os.getuid() or metadata.st_mode & 0o077):
            raise PolicyError("telemetry_storage_unavailable")


def _file_safe(path: Path) -> bool:
    try:
        value = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(value.st_mode) or value.st_size > MAX_DATABASE_BYTES:
        raise PolicyError("telemetry_storage_unavailable")
    if os.name != "nt" and (value.st_uid != os.getuid() or value.st_mode & 0o077):
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
    if (
        connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
        or connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION
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
    return {"revision": row[0], "enabled": bool(row[1]), "disclosure_version": row[2]}


def _initialize(root: Path) -> None:
    _root_safe(root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    _root_safe(root)
    path = root / DATABASE_NAME
    if _file_safe(path):
        return
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return
    os.close(descriptor)
    # A crash before the schema commits leaves damaged/unknown state. Never
    # turn that state into a fresh enabled preference on a later read.
    with closing(_connect(path)) as connection:
        connection.execute("PRAGMA page_size=4096")
        connection.execute("PRAGMA max_page_count=24")
        connection.executescript(
            "BEGIN IMMEDIATE;"
            f"PRAGMA application_id={APPLICATION_ID}; PRAGMA user_version={SCHEMA_VERSION};"
            + SCHEMA
            + "COMMIT;"
        )


def status(root: Path | None = None, *, policy_path: Path | None = None) -> dict:
    root = root if root is not None else default_directory()
    company = company_policy(policy_path)
    preference = {"revision": 0, "enabled": True, "disclosure_version": 0}
    storage, pending = "new", 0
    try:
        _root_safe(root)
        if _file_safe(root / DATABASE_NAME):
            with closing(_connect(root / DATABASE_NAME, readonly=True)) as connection:
                connection.execute("BEGIN")
                preference = _preferences(connection)
                pending = connection.execute("SELECT count(*) FROM pending").fetchone()[0]
                if not 0 <= pending <= MAX_PENDING:
                    raise PolicyError("telemetry_storage_unavailable")
                connection.rollback()
            storage = "ready"
    except (OSError, sqlite3.Error, PolicyError):
        storage = "unreadable"
    if storage == "unreadable":
        reason = "storage_unavailable"
    elif not preference["enabled"]:
        reason = "user_disabled"
    elif not company["enabled"] or not company["metric_groups"]:
        reason = "company_policy"
    elif preference["disclosure_version"] != DISCLOSURE_VERSION:
        reason = "disclosure_required"
    elif not COLLECTION_AVAILABLE or COLLECTOR_URL is None:
        reason = "collection_unavailable"
    else:
        reason = "enabled"
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": preference["revision"],
        "default_enabled": True,
        "user_enabled": preference["enabled"],
        "effective_enabled": reason == "enabled",
        "reason": reason,
        "storage": storage,
        "disclosure_version": preference["disclosure_version"],
        "required_disclosure_version": DISCLOSURE_VERSION,
        "company_policy": company,
        "pending_records": pending if storage != "unreadable" else None,
        "collection_available": COLLECTION_AVAILABLE,
        "disclosure": disclosure(),
    }


def configure(root: Path | None, request: dict, *, policy_path: Path | None = None) -> dict:
    fields = {"enabled", "expected_revision", "disclosure_version"}
    if (
        not isinstance(request, dict)
        or set(request) - fields
        or type(request.get("enabled")) is not bool
        or type(request.get("expected_revision")) is not int
        or not 0 <= request["expected_revision"] < 2147483647
        or type(request.get("disclosure_version", 0)) is not int
        or request.get("disclosure_version", 0) not in (0, DISCLOSURE_VERSION)
    ):
        raise PolicyError("telemetry_invalid_choice")
    acknowledged = request.get("disclosure_version", 0)
    if acknowledged and (not COLLECTION_AVAILABLE or COLLECTOR_URL is None):
        raise PolicyError("telemetry_disclosure_unavailable")
    root = root if root is not None else default_directory()
    try:
        _initialize(root)
        with closing(_connect(root / DATABASE_NAME)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = _preferences(connection)
            # Opt-out wins over stale UI state. Re-enabling always requires the
            # current revision and cannot undo another process's newer choice.
            if request["enabled"] and request["expected_revision"] != previous["revision"]:
                raise PolicyError("telemetry_choice_changed")
            effective_acknowledgement = acknowledged if request["enabled"] else 0
            if (
                not request["enabled"]
                or request["enabled"] != previous["enabled"]
                or effective_acknowledgement != previous["disclosure_version"]
            ):
                connection.execute(
                    "UPDATE preferences SET revision=revision+1, enabled=?, disclosure_version=? WHERE singleton=1",
                    (int(request["enabled"]), effective_acknowledgement),
                )
            # A new choice never resurrects queued history, including enabling
            # after opt-out. secure_delete also clears freed cells in this DB.
            connection.execute("DELETE FROM pending")
            connection.commit()
    except sqlite3.OperationalError as error:
        if getattr(error, "sqlite_errorcode", None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            raise PolicyError("telemetry_busy") from None
        raise PolicyError("telemetry_storage_unavailable") from None
    except (OSError, sqlite3.Error):
        raise PolicyError("telemetry_storage_unavailable") from None
    return status(root, policy_path=policy_path)


def preview(root: Path | None = None, *, policy_path: Path | None = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status(root, policy_path=policy_path),
        "outbound_body": None,
        "outbound_bytes": 0,
        "transport_available": False,
        "message": "No product-telemetry sender is active in this build.",
    }
