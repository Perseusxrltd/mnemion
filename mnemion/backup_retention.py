"""Bounded native backup inventory, reviewed cleanup and retained recovery points."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from . import backup_catalog as catalog, backup_encryption as encryption, local_state as state

BATCH_LIMIT = 200
RECENT_LIMIT = 100


class RetentionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["keep_all", "limited"] = "keep_all"
    snapshots: int = Field(default=7, ge=2, le=365)
    ledgers: int = Field(default=96, ge=2, le=10000)


_PROTECTION = """
WITH snapshot_points AS (
 SELECT sequence,operation_id FROM copies
 WHERE scope_id=:scope AND key_id=:key AND kind='snapshot'
 ORDER BY sequence DESC LIMIT :snapshots
), recent_ledgers AS (
 SELECT sequence FROM copies
 WHERE scope_id=:scope AND key_id=:key AND kind='ledger'
 ORDER BY sequence DESC LIMIT :ledgers
), protected AS (
 SELECT sequence FROM snapshot_points
 UNION SELECT sequence FROM recent_ledgers
 UNION SELECT sequence FROM copies WHERE scope_id=:scope AND key_id=:key
  AND kind='ledger' AND operation_id IN (SELECT operation_id FROM snapshot_points)
 UNION SELECT sequence FROM copies WHERE scope_id=:scope AND key_id=:key
  AND name IN (:last_snapshot,:last_ledger)
)
"""


def _last_names(root: Path, folder: Path, workspace_id: str, key_id: str) -> dict:
    names = {"last_snapshot": "", "last_ledger": ""}
    for filename, kind in (("last-backup.json", "snapshot"), ("last-ledger.json", "ledger")):
        try:
            record = state.read(root / filename)
        except FileNotFoundError:
            continue
        if record.get("workspace_id") != workspace_id:
            continue
        entry = record.get(kind, {})
        path = Path(entry.get("file", ""))
        if path.parent == folder and entry.get("key_id") == key_id:
            if not catalog.NAME.fullmatch(path.name):
                raise catalog._problem()
            names["last_" + kind] = path.name
    return names


def _projection(folder: Path, row, *, protected: bool = False) -> dict:
    availability, _ = catalog.row_available(folder, row)
    return {key: row[key] for key in ("name", "kind", "key_id", "bytes", "verified_at")} | {
        "availability": availability,
        "protected": protected,
    }


def _plan(
    connection, root: Path, folder: Path, workspace_id: str, key_id: str, policy: RetentionPolicy
):
    try:
        identifier = (
            catalog.scope(connection, folder, workspace_id) if connection is not None else None
        )
    except FileNotFoundError:
        identifier = None
    base = {
        "format": 1,
        "workspace_id": workspace_id,
        "key_id": key_id,
        "folder": str(folder),
        "policy": policy.model_dump(),
        "tracked_snapshots": 0,
        "tracked_ledgers": 0,
        "tracked_bytes": 0,
        "other_key_files": 0,
        "candidate_files": 0,
        "candidate_bytes": 0,
        "batch_files": 0,
        "batch_bytes": 0,
        "recent_limit": RECENT_LIMIT,
        "recent": [],
        "state": "keep_all" if policy.mode == "keep_all" else "untracked",
        "message": "Copies without a private ownership receipt are always retained.",
    }
    if identifier is None:
        base["plan_token"] = hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()
        return base, [], [], None
    totals = connection.execute(
        "SELECT kind,COUNT(*) AS count,COALESCE(SUM(bytes),0) AS bytes FROM copies "
        "WHERE scope_id=? AND key_id=? GROUP BY kind",
        (identifier, key_id),
    ).fetchall()
    for row in totals:
        base["tracked_" + ("snapshots" if row["kind"] == "snapshot" else "ledgers")] = row["count"]
        base["tracked_bytes"] += row["bytes"]
    base["other_key_files"] = connection.execute(
        "SELECT COUNT(*) FROM copies WHERE scope_id=? AND key_id!=?",
        (identifier, key_id),
    ).fetchone()[0]
    parameters = {
        "scope": identifier,
        "key": key_id,
        "snapshots": policy.snapshots,
        "ledgers": policy.ledgers,
        **_last_names(root, folder, workspace_id, key_id),
    }
    protected = connection.execute(
        _PROTECTION
        + "SELECT * FROM copies WHERE sequence IN (SELECT sequence FROM protected) ORDER BY sequence DESC",
        parameters,
    ).fetchall()
    for row in protected:
        catalog.validate_row(row)
    protected_ids = {row["sequence"] for row in protected}
    recent = connection.execute(
        "SELECT * FROM copies WHERE scope_id=? AND key_id=? ORDER BY sequence DESC LIMIT ?",
        (identifier, key_id, RECENT_LIMIT),
    ).fetchall()
    base["recent"] = [
        _projection(
            folder, row, protected=policy.mode == "keep_all" or row["sequence"] in protected_ids
        )
        for row in recent
    ]
    candidates = []
    if policy.mode == "limited":
        selection = "FROM copies WHERE scope_id=:scope AND key_id=:key AND sequence NOT IN (SELECT sequence FROM protected)"
        counts = connection.execute(
            _PROTECTION + "SELECT COUNT(*),COALESCE(SUM(bytes),0) " + selection, parameters
        ).fetchone()
        candidates = connection.execute(
            _PROTECTION
            + "SELECT * "
            + selection
            + " ORDER BY cleanup_attempts,sequence LIMIT "
            + str(BATCH_LIMIT),
            parameters,
        ).fetchall()
        for row in candidates:
            catalog.validate_row(row)
        base.update(
            candidate_files=counts[0],
            candidate_bytes=counts[1],
            batch_files=len(candidates),
            batch_bytes=sum(row["bytes"] for row in candidates),
            state="ready",
            message="Cleanup verifies retained recovery points and removes only unchanged tracked copies.",
        )
        if base["tracked_snapshots"] < 2:
            base.update(
                state="insufficient_recovery",
                message="Create two full snapshots with this key before cleaning up older files.",
            )
    token_data = {
        "policy": policy.model_dump(),
        "scope": identifier,
        "directory": catalog.folder_identity(folder),
        "key": key_id,
        "protected": [dict(row) for row in protected],
        "candidates": [dict(row) for row in candidates],
        "counts": [base["candidate_files"], base["tracked_snapshots"], base["tracked_ledgers"]],
    }
    base["plan_token"] = hashlib.sha256(json.dumps(token_data, sort_keys=True).encode()).hexdigest()
    return base, protected, candidates, identifier


def inventory(
    root: Path, folder: Path, workspace_id: str, key_id: str, policy: RetentionPolicy
) -> dict:
    with catalog.open_catalog(root) as connection:
        return _plan(connection, root, folder, workspace_id, key_id, policy)[0]


@contextmanager
def _opened(folder: Path, name: str, *, deleting: bool):
    """Open only the recorded leaf. Windows holds off replacement while hashing."""
    if not catalog.NAME.fullmatch(name):
        raise catalog._problem()
    if os.name == "nt":
        import ctypes as c
        from ctypes import wintypes as w
        import msvcrt

        kernel = c.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [
            w.LPCWSTR,
            w.DWORD,
            w.DWORD,
            c.c_void_p,
            w.DWORD,
            w.DWORD,
            w.HANDLE,
        ]
        kernel.CreateFileW.restype = w.HANDLE
        kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
        kernel.SetFileInformationByHandle.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        kernel.SetFileInformationByHandle.restype = w.BOOL
        handle = kernel.CreateFileW(
            str(folder / name),
            0x80000000 | (0x10000 if deleting else 0),
            1,
            None,
            3,
            0x08200000,
            None,
        )
        if handle in {None, c.c_void_p(-1).value}:
            raise OSError("The backup file is unavailable or in use")
        try:
            descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            kernel.CloseHandle(handle)
            raise
        with os.fdopen(descriptor, "rb") as stream:

            def remove(expected):
                if not deleting or catalog.file_identity(os.fstat(stream.fileno())) != expected:
                    raise catalog._problem()
                disposition = w.BOOL(True)
                if not kernel.SetFileInformationByHandle(
                    handle, 4, c.byref(disposition), c.sizeof(disposition)
                ):
                    raise OSError("The backup file could not be removed")

            yield stream, remove
    else:
        directory = os.open(
            folder, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
                dir_fd=directory,
            )
            with os.fdopen(descriptor, "rb") as stream:

                def remove(expected):
                    current = os.stat(name, dir_fd=directory, follow_symlinks=False)
                    if not deleting or catalog.file_identity(current) != expected:
                        raise catalog._problem()
                    os.unlink(name, dir_fd=directory)
                    # Some removable/network filesystems cannot flush a
                    # directory. Unlink already succeeded: do not misreport
                    # that copy as retained or keep its live catalog row.
                    try:
                        os.fsync(directory)
                    except OSError:
                        pass

                yield stream, remove
        finally:
            os.close(directory)


def _verify(stream, row, cancelled):
    before = catalog.file_identity(os.fstat(stream.fileno()))
    if before[2] != row["bytes"]:
        raise catalog._problem()
    digest = hashlib.sha256()
    while True:
        encryption._cancel(cancelled)
        block = stream.read(encryption.CHUNK_BYTES)
        if not block:
            break
        digest.update(block)
    if (
        catalog.file_identity(os.fstat(stream.fileno())) != before
        or digest.hexdigest() != row["sha256"]
    ):
        raise catalog._problem()
    return before


def _check_retained(folder, directory_identity, retained_identities):
    if catalog.folder_identity(folder) != directory_identity:
        raise catalog._problem()
    # Windows path ctime reports birth time; handle ctime reports change time.
    # Full handle identities are still checked while each file is hashed.
    common_fields = 4 if os.name == "nt" else 5
    if any(
        catalog.file_identity((folder / name).lstat())[:common_fields] != identity[:common_fields]
        for name, identity in retained_identities.items()
    ):
        raise catalog._problem()


@contextmanager
def _record_cleanup(root, result, candidate_count):
    try:
        yield
    except encryption.EncryptionCancelled:
        result.update(
            state="cancelled",
            message="Cleanup stopped. Completed removals remain recorded; retained recovery points were protected.",
        )
        raise
    except (OSError, sqlite3.Error, state.LocalSetupError):
        result.update(
            state="partial" if result["deleted_files"] else "blocked",
            message="Cleanup stopped because its folder or private inventory became unavailable. Review the inventory before retrying.",
        )
        raise
    finally:
        result["remaining_candidates"] = max(0, candidate_count - result["deleted_files"])
        result["completed_at"] = datetime.now(timezone.utc).isoformat()
        state.write(root / "last-retention.json", result)


def cleanup(
    root: Path,
    folder: Path,
    workspace_id: str,
    key_id: str,
    policy: RetentionPolicy,
    *,
    expected_plan: str | None = None,
    cancelled=None,
    emit=None,
) -> dict:
    """One bounded batch. Original snapshot/ledger pairs and other keys survive."""
    encryption._cancel(cancelled)
    with catalog.open_catalog(root) as connection, ExitStack() as retained_files:
        plan, protected, candidates, identifier = _plan(
            connection, root, folder, workspace_id, key_id, policy
        )
        if expected_plan is not None and expected_plan != plan["plan_token"]:
            raise state.LocalSetupError(
                "backup_plan_changed",
                "The backup inventory changed. Review the current cleanup plan before retrying.",
            )
        result = {
            "format": 1,
            "workspace_id": workspace_id,
            "key_id": key_id,
            "folder": str(folder),
            "policy": policy.model_dump(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "state": "complete",
            "deleted_files": 0,
            "deleted_bytes": 0,
            "skipped_files": 0,
            "remaining_candidates": plan["candidate_files"],
            "message": "No older tracked copies need cleanup.",
        }
        retained_files.enter_context(_record_cleanup(root, result, plan["candidate_files"]))
        if plan["state"] != "ready" or not candidates:
            result.update(
                state="blocked" if plan["state"] == "insufficient_recovery" else "complete",
                message=plan["message"],
            )
            return result
        directory_identity = catalog.folder_identity(folder)
        snapshots = [row for row in protected if row["kind"] == "snapshot"][:2]
        keep = {row["sequence"]: row for row in snapshots}
        newest_ledger = next((row for row in protected if row["kind"] == "ledger"), None)
        if newest_ledger is not None:
            keep[newest_ledger["sequence"]] = newest_ledger
        for snapshot in snapshots:
            partner = next(
                (
                    row
                    for row in protected
                    if row["kind"] == "ledger" and row["operation_id"] == snapshot["operation_id"]
                ),
                None,
            )
            if partner is None:
                result.update(
                    state="blocked",
                    message="A retained snapshot has no recorded access ledger. Create fresh complete backups before cleanup.",
                )
                return result
            keep[partner["sequence"]] = partner
        if len(snapshots) != 2 or newest_ledger is None:
            result.update(
                state="blocked",
                message="Two complete recorded recovery points are required before cleanup.",
            )
            return result
        if emit:
            emit(
                {
                    "event": "backup_progress",
                    "stage": "verifying_retention",
                    "message": "Verifying the recovery points that will be kept…",
                }
            )
        retained_identities = {}
        try:
            for row in keep.values():
                stream, _ = retained_files.enter_context(
                    _opened(folder, row["name"], deleting=False)
                )
                retained_identities[row["name"]] = _verify(stream, row, cancelled)
        except (OSError, state.LocalSetupError):
            result.update(
                state="blocked",
                message="A retained recovery point is missing, changed or unavailable. Cleanup kept every older file.",
            )
            return result
        if emit:
            emit(
                {
                    "event": "backup_progress",
                    "stage": "retention",
                    "message": "Removing unchanged older copies within the configured limits…",
                }
            )
        for row in candidates:
            encryption._cancel(cancelled)
            try:
                _check_retained(folder, directory_identity, retained_identities)
            except (OSError, state.LocalSetupError):
                result.update(
                    state="partial",
                    message="A retained recovery point changed during cleanup. Remaining copies were retained.",
                )
                break
            try:
                with _opened(folder, row["name"], deleting=True) as (stream, remove):
                    identity = _verify(stream, row, cancelled)
                    encryption._cancel(cancelled)
                    _check_retained(folder, directory_identity, retained_identities)
                    remove(identity)
                # Record the filesystem mutation before the catalog commit:
                # a database-write failure must not claim the file was retained.
                result["deleted_files"] += 1
                result["deleted_bytes"] += row["bytes"]
                connection.execute(
                    "DELETE FROM copies WHERE sequence=? AND scope_id=?",
                    (row["sequence"], identifier),
                )
                connection.commit()
            except (OSError, state.LocalSetupError):
                result["skipped_files"] += 1
                # Missing or cloud-locked files must not permanently block the
                # rest of a large inventory's bounded cleanup batches.
                connection.execute(
                    "UPDATE copies SET cleanup_attempts=MIN(cleanup_attempts+1,1000000) WHERE sequence=?",
                    (row["sequence"],),
                )
                connection.commit()
        result["remaining_candidates"] = max(0, plan["candidate_files"] - result["deleted_files"])
        result["state"] = (
            "partial" if result["skipped_files"] or result["remaining_candidates"] else "complete"
        )
        result["message"] = (
            "Verified retained recovery points; unchanged older copies were removed."
            if result["state"] == "complete"
            else "Some older copies remain. Changed, missing or unavailable files were not removed; review the inventory."
        )
        return result
