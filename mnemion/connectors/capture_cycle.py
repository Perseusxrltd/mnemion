"""One shared local-first capture/delivery cycle for native and headless devices."""

from __future__ import annotations

from datetime import datetime, timezone
import time

import httpx

from ..sdk import MnemionError
from .capture_delivery import DeliveryProgress, deliver
from .capture_scheduling import (
    BACKFILL_POLL_SECONDS as BACKFILL_POLL_SECONDS,
    BACKFILL_REASONS as BACKFILL_REASONS,
    backfill_pending as backfill_pending,
)
from .capture_storage import reclaim
from .conversation_inbox import InboxError


def cycle(inbox, *, collect, client, revoked, usage, started=None):
    """The collector commits before constructing any remote client.

    Enrollment, process lifetime and protected credentials belong to the caller.
    Both callers share exact receipt reconciliation and current negative fences.
    """
    began = time.monotonic() if started is None else started
    storage = reclaim(inbox)
    local = {"completed": False, "scopes": [], "errors": ["capture_authorization_revoked"]}
    if collect is not None:
        try:
            local = collect()
        except InboxError as error:
            local["errors"] = [error.code]
    progress = DeliveryProgress()
    remote_error, fence_pending = None, False
    try:
        with client() as remote_client:
            remote = deliver(inbox, remote_client, progress=progress)
            fence_pending = remote["fence_sweep_pending"]
    except (MnemionError, httpx.HTTPError, InboxError, ValueError) as error:
        remote_error = (
            error.code if isinstance(error, InboxError) else "capture_delivery_unavailable"
        )
        if isinstance(error, MnemionError) and error.status in {401, 403}:
            remote_error = "capture_authorization_revoked"
        if remote_error == "capture_authorization_revoked":
            revoked()
    storage = reclaim(inbox, previous_bytes=storage["reclaimed_bytes"])
    status = inbox.status()
    device = usage()
    capture = {
        "locally_accepted": sum(item["locally_accepted"] for item in local["scopes"]),
        "pending_events": status["pending_events"],
        "pending_bytes": status["pending_bytes"],
        "remote_committed_events": progress.remote_committed_events,
        "newly_stored_events": progress.newly_stored_events,
        "stored_events": status["stored_events"],
        "forgotten_events": status["forgotten_events"],
        "unknown_pages": status["unknown_pages"],
        "database_bytes": status["database_bytes"],
        "over_limit": status["over_limit"],
        "capture_complete": local["completed"],
        "delivery_complete": not remote_error
        and not status["pending_events"]
        and not fence_pending
        and not status["history"]["fence_history_blocked"],
        "device_pending_bytes": device["pending_bytes"],
        "device_database_bytes": device["database_bytes"],
        "reason_code": next(iter(local["errors"]), None)
        or remote_error
        or ("capture_fence_capacity" if status["history"]["fence_history_blocked"] else None)
        or ("capture_scan_pending" if local.get("deferred") else None)
        or ("capture_delivery_pending" if status["pending_events"] or fence_pending else None),
        "coverage": status["coverage"],
        "history": status["history"],
        "storage": storage,
    }
    return {
        "completed": capture["capture_complete"] and capture["delivery_complete"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": time.monotonic() - began,
        "changed": progress.remote_committed_events,
        "removed": 0,
        "unchanged": 0,
        "conflicts": 0,
        "remote_sync_available": remote_error is None,
        "capture": capture,
    }
