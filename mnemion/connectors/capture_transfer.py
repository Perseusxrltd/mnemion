"""Re-encrypt an independent inbox copy for a reviewed device authorization.

Current server authority belongs to the enrollment coordinator. This local
primitive never issues a grant, resumes capture, changes policy or overwrites
evidence. It retains historical receipts with their original issuing grant.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from .. import local_state
from ..archives import _rename_exclusive
from ..private_output import private_output
from .capture_archive import (
    DATABASE_BYTES,
    HASH,
    VALUE_BYTES,
    CaptureArchiveError,
    RestoredInbox,
    _audit,
    _cancel,
    _copy,
    _key,
    _space,
    opened_archive,
)
from .conversation_inbox import Inbox, Limits, binding_value


@dataclass(frozen=True)
class DeviceCopy(RestoredInbox):
    original_binding: dict


def device_binding(original, selected):
    """Changing grant/key must not silently change evidence or its organization."""
    selected = binding_value(selected)
    if {k: v for k, v in original.items() if k != "grant_id"} != {
        k: v for k, v in selected.items() if k != "grant_id"
    }:
        raise CaptureArchiveError(
            "Device recovery must retain the original organization, source and capture policy."
        )
    return selected


def _reencrypt(connection, old, new, cancelled):
    # Only encrypted values change. Event/page IDs, immutable content hashes,
    # checkpoints, deletion fences and receipts from the original grant remain.
    for name, value in connection.execute("SELECT name,value FROM metadata"):
        _cancel(cancelled)
        identity = "observation:" + name if name.startswith("coverage") else name
        connection.execute(
            "UPDATE metadata SET value=? WHERE name=?",
            (new._seal(old._open(value, identity), identity), name),
        )
    for table, column, identity_column, prefix in (
        ("events", "payload", "event_id", "event:"),
        ("checkpoints", "payload", "scope", "checkpoint:"),
        ("pages", "payload", "page_id", "page:"),
        ("pages", "receipt", "page_id", "receipt:"),
    ):
        for identifier, value in connection.execute(
            f"SELECT {identity_column},{column} FROM {table} WHERE {column} IS NOT NULL"
        ):
            _cancel(cancelled)
            identity = prefix + identifier
            connection.execute(
                f"UPDATE {table} SET {column}=? WHERE {identity_column}=?",
                (new._seal(old._open(value, identity), identity), identifier),
            )
    for scope, start, value in connection.execute(
        "SELECT scope,start,payload FROM producer_segments"
    ):
        _cancel(cancelled)
        identity = f"segment:{scope}:{start}"
        connection.execute(
            "UPDATE producer_segments SET payload=? WHERE scope=? AND start=?",
            (new._seal(old._open(value, identity), identity), scope, start),
        )


def restore_device_copy(
    source,
    recovery_key,
    destination,
    *,
    staging_root,
    expected_sha256,
    selected_binding,
    inbox_key,
    cancelled=None,
):
    """Create a new private copy with a caller-protected key and reviewed grant.

    The caller must separately confirm current source/device authority and any
    previous-device retirement. A successful copy is not an enrolled source.
    """
    if not isinstance(expected_sha256, str) or not HASH.fullmatch(expected_sha256):
        raise CaptureArchiveError("Inspect this archive before recovering its device.")
    if type(inbox_key) is not bytes or len(inbox_key) != 32:
        raise CaptureArchiveError("Protect a new inbox key before device recovery.")
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise CaptureArchiveError("Recover into a new inbox; existing evidence was retained.")
    with opened_archive(
        source,
        recovery_key,
        staging_root=staging_root,
        expected_sha256=expected_sha256,
        cancelled=cancelled,
    ) as archive:
        if inbox_key == _key(archive.manifest.inbox_key):
            raise CaptureArchiveError("Use a new private inbox key for device recovery.")
        binding = device_binding(archive.manifest.binding, selected_binding)
        _space(destination.parent, archive.manifest.database_bytes * 2)
        with local_state.temporary_directory(
            prefix="capture-device-", dir=destination.parent
        ) as temporary:
            database = temporary / "inbox.sqlite3"
            with archive.database.open("rb") as reader, private_output(database) as writer:
                if (
                    _copy(reader, writer, archive.manifest.database_bytes, cancelled)
                    != archive.manifest.database_sha256
                ):
                    raise CaptureArchiveError("The verified capture snapshot changed.")
            connection = sqlite3.connect(database)
            try:
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("PRAGMA secure_delete=ON")
                connection.execute("PRAGMA cache_size=-2048")
                connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, VALUE_BYTES)
                connection.set_progress_handler(lambda: bool(cancelled and cancelled()), 10000)
                limits = Limits(**archive.manifest.limits)
                old = Inbox(
                    connection,
                    temporary,
                    archive.manifest.binding,
                    _key(archive.manifest.inbox_key),
                    limits,
                )
                new = Inbox(connection, temporary, binding, inbox_key, limits)
                with new._transaction():
                    _reencrypt(connection, old, new, cancelled)
                    status = _audit(new, cancelled)
                    if status["database_bytes"] > DATABASE_BYTES:
                        raise CaptureArchiveError("The recovered inbox exceeds its archive limit.")
                # Authentication is checked again after the durable commit.
                status = _audit(new, cancelled)
            except sqlite3.Error:
                _cancel(cancelled)
                raise CaptureArchiveError("The device inbox copy could not be verified.") from None
            finally:
                connection.close()
            _cancel(cancelled)
            _rename_exclusive(temporary, destination)
            local_state._sync_directory(destination.parent)
        return DeviceCopy(
            destination,
            binding,
            status,
            archive.archive_sha256,
            inbox_key,
            archive.manifest.binding,
        )
