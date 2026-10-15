"""Private ownership receipts for native encrypted copies, never a memory index.

Only successful native capture registers files. Names found in a cloud folder
do not establish ownership. Losing this catalogue retains the external copies.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
from uuid import UUID

from . import local_state as state
from .private_output import private_output

MAX_CATALOG_BYTES = 64 * 1024**2
MAX_FILE_BYTES = 50 * 1024**3 + 2048
NAME = re.compile(r"(snapshot|ledger)-\d{8}T\d{6}Z-([a-f0-9]{32})\.mnemion\.enc")


def _problem():
    return state.LocalSetupError(
        "backup_catalog",
        "The private backup inventory could not be verified. Review the current backup files before retrying.",
    )


def folder_identity(folder: Path) -> tuple[str, str]:
    info = folder.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
    ):
        raise _problem()
    return str(info.st_dev), str(info.st_ino)


def file_identity(info) -> tuple[int, int, int, int, int]:
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
        or info.st_nlink != 1
    ):
        raise _problem()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


@contextmanager
def open_catalog(root: Path, *, create: bool = False):
    """The caller holds the native backup-operations lock for the whole action."""
    control = root / "backup-operations"
    path = control / "inventory.sqlite3"
    if not path.exists() and not path.is_symlink() and not create:
        yield None
        return
    state.directory(control)
    if create and not path.exists():
        try:
            with private_output(path):
                pass
        except FileExistsError:
            pass
    before = state._regular(path)
    if before.st_size > MAX_CATALOG_BYTES:
        raise _problem()
    if os.name == "nt":
        from .private_input import _windows_open

        descriptor = _windows_open(path)
        try:
            checked = os.fstat(descriptor)
            if (checked.st_dev, checked.st_ino) != (before.st_dev, before.st_ino):
                raise _problem()
        finally:
            os.close(descriptor)
    connection = None
    try:
        # mode=rw prevents a deleted or swapped path from silently becoming a
        # new unprotected database. No extension loading or user SQL is allowed.
        connection = sqlite3.connect(path.absolute().as_uri() + "?mode=rw", uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        current = state._regular(path)
        if (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
            raise _problem()
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 0 and create:
            connection.execute("BEGIN IMMEDIATE")
            with connection:
                connection.execute(
                    "CREATE TABLE scopes (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, "
                    "folder TEXT NOT NULL, device TEXT NOT NULL, inode TEXT NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE copies (sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "scope_id TEXT NOT NULL REFERENCES scopes(id), name TEXT NOT NULL, "
                    "kind TEXT NOT NULL CHECK(kind IN ('snapshot','ledger')), "
                    "operation_id TEXT NOT NULL, key_id TEXT NOT NULL, "
                    "bytes INTEGER NOT NULL CHECK(bytes>=0), sha256 TEXT NOT NULL, "
                    "verified_at TEXT NOT NULL, cleanup_attempts INTEGER NOT NULL DEFAULT 0 "
                    "CHECK(cleanup_attempts>=0), UNIQUE(scope_id,name))"
                )
                connection.execute(
                    "CREATE INDEX copies_retention ON copies(scope_id,key_id,kind,sequence DESC)"
                )
                connection.execute("PRAGMA user_version=1")
        elif version != 1:
            raise _problem()
        yield connection
        connection.commit()
    except sqlite3.Error:
        if connection is not None:
            connection.rollback()
        raise _problem() from None
    except BaseException:
        if connection is not None:
            connection.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()


def scope(connection, folder: Path, workspace_id: str, *, create=False):
    folder = folder.absolute()
    normalized = os.path.normcase(str(folder))
    device, inode = folder_identity(folder)
    # A replaced/remounted folder begins a new ownership scope. Old receipts
    # never authorize deletion on another filesystem at the same pathname.
    identifier = hashlib.sha256(
        (workspace_id + "\0" + normalized + "\0" + device + "\0" + inode).encode()
    ).hexdigest()
    found = connection.execute("SELECT * FROM scopes WHERE id=?", (identifier,)).fetchone()
    if found is None:
        if not create:
            return None
        connection.execute(
            "INSERT INTO scopes VALUES (?,?,?,?,?)",
            (identifier, workspace_id, str(folder), device, inode),
        )
        return identifier
    if (
        found["workspace_id"] != workspace_id
        or os.path.normcase(found["folder"]) != normalized
        or (found["device"], found["inode"]) != (device, inode)
    ):
        raise state.LocalSetupError(
            "backup_destination_changed",
            "This backup folder is on a different filesystem or was replaced. Existing copies were retained.",
        )
    return identifier


def register(root: Path, folder: Path, receipt: dict) -> None:
    """Called only after both encrypted files passed capture authentication."""
    try:
        if not isinstance(receipt["workspace_id"], str):
            raise ValueError()
        workspace_id = str(UUID(receipt["workspace_id"]))
        operation = receipt["operation_id"]
        if not re.fullmatch(r"[a-f0-9]{32}", operation):
            raise ValueError()
        stamp = receipt["verified_at"]
        if (
            not isinstance(stamp, str)
            or len(stamp) > 40
            or datetime.fromisoformat(stamp).tzinfo is None
        ):
            raise ValueError()
        files = []
        for kind in ("snapshot", "ledger"):
            if kind not in receipt:
                continue
            value = receipt[kind]
            path = Path(value["file"])
            match = NAME.fullmatch(path.name)
            if (
                path.parent != folder
                or not match
                or match.groups() != (kind, operation)
                or value["authenticated"] is not True
                or type(value["bytes"]) is not int
                or not 1 <= value["bytes"] <= MAX_FILE_BYTES
                or not re.fullmatch(r"[a-f0-9]{64}", value["sha256"])
                or not re.fullmatch(r"[a-f0-9]{24}", value["key_id"])
                or file_identity(path.lstat())[2] != value["bytes"]
            ):
                raise ValueError()
            files.append(
                (
                    path.name,
                    kind,
                    operation,
                    value["key_id"],
                    value["bytes"],
                    value["sha256"],
                    stamp,
                )
            )
        if (
            not files
            or not any(value[1] == "ledger" for value in files)
            or len({value[3] for value in files}) != 1
        ):
            raise ValueError()
    except (KeyError, ValueError, TypeError, OSError):
        raise _problem() from None
    with open_catalog(root, create=True) as connection:
        identifier = scope(connection, folder, workspace_id, create=True)
        for values in files:
            previous = connection.execute(
                "SELECT name,kind,operation_id,key_id,bytes,sha256,verified_at FROM copies "
                "WHERE scope_id=? AND name=?",
                (identifier, values[0]),
            ).fetchone()
            if previous is not None:
                if tuple(previous) != values:
                    raise _problem()
                continue
            connection.execute(
                "INSERT INTO copies(scope_id,name,kind,operation_id,key_id,bytes,sha256,verified_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (identifier, *values),
            )


def row_available(folder: Path, row) -> tuple[str, tuple | None]:
    """Metadata presence is explicit; it is not cryptographic re-verification."""
    validate_row(row)
    try:
        identity = file_identity((folder / row["name"]).lstat())
        return ("present", identity) if identity[2] == row["bytes"] else ("changed", identity)
    except FileNotFoundError:
        return "missing", None
    except (OSError, state.LocalSetupError):
        return "unavailable", None


def validate_row(row) -> None:
    try:
        match = NAME.fullmatch(row["name"])
        if (
            not match
            or match.groups() != (row["kind"], row["operation_id"])
            or type(row["sequence"]) is not int
            or row["sequence"] < 1
            or type(row["bytes"]) is not int
            or not 1 <= row["bytes"] <= MAX_FILE_BYTES
            or not re.fullmatch(r"[a-f0-9]{64}", row["sha256"])
            or not re.fullmatch(r"[a-f0-9]{24}", row["key_id"])
            or not isinstance(row["verified_at"], str)
            or len(row["verified_at"]) > 40
            or datetime.fromisoformat(row["verified_at"]).tzinfo is None
        ):
            raise ValueError()
    except (KeyError, IndexError, ValueError, TypeError):
        raise _problem() from None
