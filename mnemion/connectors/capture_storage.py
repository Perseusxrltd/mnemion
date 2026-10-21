"""Bounded reclamation of SQLite free pages, preserving every logical record.

Only the inbox's existing process lock may own this connection. A cleanup never
acknowledges evidence, changes a checkpoint or removes a receipt/deletion fence.
"""

from __future__ import annotations

import shutil
import sqlite3
import time
from typing import Literal

from pydantic import Field, model_validator

from ..service.models import Command

MIB = 1024**2
MINIMUM_RECLAIM_BYTES = 4 * MIB
RECLAIM_BYTES = 64 * MIB
RECLAIM_SECONDS = 0.5


class StorageReport(Command):
    format: Literal["mnemion-capture-storage-v1"]
    state: Literal["idle", "reclaimed", "deferred", "failed"]
    database_bytes: int = Field(ge=0, le=10**12, strict=True)
    reclaimable_bytes: int = Field(ge=0, le=10**12, strict=True)
    reclaimed_bytes: int = Field(ge=0, le=10**12, strict=True)
    reason: (
        Literal["time_budget", "byte_budget", "disk_reserve", "pending_legacy", "sqlite_failure"]
        | None
    ) = None

    @model_validator(mode="after")
    def consistent(self):
        if self.reclaimable_bytes > self.database_bytes:
            raise ValueError("Unused storage cannot exceed the database")
        if (self.state in {"deferred", "failed"}) != (self.reason is not None):
            raise ValueError("Deferred storage cleanup needs its observed reason")
        if (self.state == "failed") != (self.reason == "sqlite_failure"):
            raise ValueError("A failed cleanup needs its observed failure")
        if self.state == "idle" and self.reclaimed_bytes:
            raise ValueError("An idle cleanup cannot claim reclaimed bytes")
        if self.state == "reclaimed" and not self.reclaimed_bytes:
            raise ValueError("A completed cleanup needs actual reclaimed bytes")
        return self


def _pages(connection):
    size = connection.execute("PRAGMA page_size").fetchone()[0]
    count = connection.execute("PRAGMA page_count").fetchone()[0]
    free = connection.execute("PRAGMA freelist_count").fetchone()[0]
    return size, count, free


def reclaim(inbox, *, previous_bytes=0):
    """Return actual cleanup observations, separate from delivery success.

    New inboxes use incremental vacuum. A pre-existing inbox converts only after
    all pending evidence has settled, with disk reserve and a cooperative time
    budget. SQLite commits a completed conversion or rolls it back intact.
    """
    connection = inbox.connection
    if connection.in_transaction:
        raise RuntimeError("Storage cleanup needs an idle inbox transaction")
    size, before, free = _pages(connection)
    released, reason, failed = previous_bytes, None, False
    threshold = min(MINIMUM_RECLAIM_BYTES, max(size, inbox.limits.database_bytes // 16))
    needed = free * size >= threshold or (before * size > inbox.limits.database_bytes and free > 0)
    if needed:
        deadline = time.monotonic() + RECLAIM_SECONDS
        original_temp = connection.execute("PRAGMA temp_store").fetchone()[0]
        mode = connection.execute("PRAGMA auto_vacuum").fetchone()[0]
        connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        try:
            if time.monotonic() >= deadline:
                reason = "time_budget"
            elif mode != 2:
                if (
                    connection.execute(
                        "SELECT 1 FROM events WHERE state='pending' LIMIT 1"
                    ).fetchone()
                    or connection.execute(
                        "SELECT 1 FROM pages WHERE state='pending' LIMIT 1"
                    ).fetchone()
                ):
                    reason = "pending_legacy"
                elif shutil.disk_usage(inbox.root).free < before * size * 2 + MIB:
                    reason = "disk_reserve"
                else:
                    # Keep the conversion's temporary database on disk. Inbox
                    # payload and context values remain encrypted throughout.
                    connection.execute("PRAGMA temp_store=FILE")
                    connection.execute("PRAGMA auto_vacuum=INCREMENTAL")
                    connection.execute("VACUUM")
            else:
                remaining = RECLAIM_BYTES // size
                while free and remaining > 2:
                    if time.monotonic() >= deadline:
                        reason = "time_budget"
                        break
                    # Returning a data page can also release a pointer-map or
                    # lock page. Reserve two pages inside the byte allowance.
                    pages = min(free, remaining - 2, 256)
                    if shutil.disk_usage(inbox.root).free < pages * size * 8 + MIB:
                        reason = "disk_reserve"
                        break
                    # Stepping every returned row is required: execute alone
                    # can perform only the first page of incremental vacuum.
                    connection.execute(f"PRAGMA incremental_vacuum({pages})").fetchall()
                    _, current, free = _pages(connection)
                    remaining = max(0, RECLAIM_BYTES // size - (before - current))
                if free and remaining <= 2 and reason is None:
                    reason = "byte_budget"
        except OSError:
            reason = "disk_reserve"
        except sqlite3.Error as error:
            if getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT:
                reason = "time_budget"
            else:
                reason, failed = "sqlite_failure", True
        finally:
            connection.set_progress_handler(None, 0)
            connection.execute(f"PRAGMA temp_store={original_temp}")
        _, after, free = _pages(connection)
        released += max(0, before - after) * size
    else:
        after = before
    return StorageReport(
        format="mnemion-capture-storage-v1",
        state="failed" if failed else "deferred" if reason else "reclaimed" if released else "idle",
        database_bytes=after * size,
        reclaimable_bytes=free * size,
        reclaimed_bytes=released,
        reason=reason,
    ).model_dump()
