"""Private desktop enrollment and capture, with local acceptance before HTTP.

The separately sealed inbox key belongs to saved source settings. A small
enrollment record distinguishes a never-used inbox from a lost one. Only the
former may be initialized; a missing ready database is never recreated.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import os
import re
import sqlite3
import time
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from . import local_state
from .capture_coverage import CaptureCoverage
from .connectors.capture_delivery import retire_grant, verify_grant
from .connectors.capture_cycle import cycle
from .connectors.capture_storage import StorageReport
from .connectors.conversation_capture import capture_available
from .connectors.conversation_inbox import InboxError, Limits, open_inbox
from .connectors.live_conversations import ConversationProvider
from .sdk import Client
from .service.models import Command

DEVICE_PENDING_BYTES = 1024**3
DEVICE_DATABASE_BYTES = 2 * 1024**3
MIB = 1024**2


class Custody(Command):
    source_id: UUID
    grant_id: UUID
    keep_accepted: Literal[True]
    pending_limit_mib: int = Field(default=256, ge=1, le=1024, strict=True)


CAPTURE_REASONS = frozenset(
    {
        "capture_authorization_revoked",
        "capture_binding_mismatch",
        "capture_binding_invalid",
        "capture_delivery_unavailable",
        "capture_delivery_pending",
        "capture_capacity_blocked",
        "capture_scan_pending",
        "capture_disk_full",
        "capture_enrollment_missing",
        "capture_integrity_failed",
        "capture_inbox_missing",
        "capture_key_unavailable",
        "capture_not_initialized",
        "capture_policy_change_requires_migration",
        "capture_server_upgrade_required",
        "capture_settings_changed",
        "capture_source_changed",
        "capture_source_unavailable",
        "capture_storage_not_private",
        "capture_storage_unavailable",
        "capture_event_invalid",
        "capture_event_conflict",
        "capture_checkpoint_invalid",
        "capture_retire_required",
        "capture_retirement_credentials",
        "capture_prefix_changed",
        "source_changed_during_read",
        "conversation_scan_deadline",
        "conversation_record_limit",
        "conversation_file_limit",
        "conversation_event_conflict",
    }
)


class CaptureReport(Command):
    locally_accepted: int = Field(ge=0, le=10**12, strict=True)
    pending_events: int = Field(ge=0, le=10**12, strict=True)
    pending_bytes: int = Field(ge=0, le=10**12, strict=True)
    remote_committed_events: int = Field(ge=0, le=10**12, strict=True)
    stored_events: int = Field(ge=0, le=10**12, strict=True)
    forgotten_events: int = Field(ge=0, le=10**12, strict=True)
    unknown_pages: int = Field(ge=0, le=10**12, strict=True)
    database_bytes: int = Field(ge=0, le=10**12, strict=True)
    device_pending_bytes: int = Field(ge=0, le=10**12, strict=True)
    device_database_bytes: int = Field(ge=0, le=10**12, strict=True)
    over_limit: bool = Field(strict=True)
    capture_complete: bool = Field(strict=True)
    delivery_complete: bool = Field(strict=True)
    reason_code: str | None = None
    coverage: CaptureCoverage | None = None
    storage: StorageReport | None = None

    @model_validator(mode="after")
    def storage_matches(self):
        if self.storage is not None and self.storage.database_bytes != self.database_bytes:
            raise ValueError("Storage cleanup must describe the observed inbox")
        return self

    @field_validator("reason_code")
    @classmethod
    def reason(cls, value):
        if value is not None and value not in CAPTURE_REASONS:
            raise ValueError("Use a bounded capture reason")
        return value


def binding(source):
    return {
        "tenant_id": str(source.tenant_id),
        "connector_id": str(source.connector_id),
        "source_id": str(source.custody.source_id),
        "grant_id": str(source.custody.grant_id),
        "namespace": source.scope_id or "selected-source",
        "capture_mode": source.capture_mode or "complete",
        **(
            {"capture_policy": source.capture_policy.model_dump(mode="json")}
            if source.capture_policy
            else {}
        ),
    }


def record_path(root, source_id):
    return root / f"inbox-enrollment-{source_id}.json"


def inbox_path(root, source_id):
    return root / f"inbox-{source_id}"


def identity(source):
    return {
        "format": 1,
        "id": str(source.id),
        "endpoint": source.endpoint,
        "principal_id": str(source.principal_id),
        "path": source.path,
        "binding": binding(source),
        "sealed_key_sha256": hashlib.sha256(source.sealed_inbox_key.encode()).hexdigest(),
    }


def enrollment(root, source):
    try:
        value = local_state.read(record_path(root, source.id))
    except FileNotFoundError:
        raise InboxError("capture_enrollment_missing") from None
    expected = identity(source)
    if (
        not isinstance(value, dict)
        or set(value) != {*expected, "state"}
        or any(value[key] != item for key, item in expected.items())
        or value.get("state") not in {"pending", "ready", "revoked", "retired", "discarded"}
    ):
        raise InboxError("capture_binding_mismatch")
    return value


def register(root, source, previous):
    """Called under the settings lock before publishing the saved source.

    A failed settings commit may leave an empty enrollment with no runnable
    source. It cannot accept data. Reusing that ID with a different key fails.
    """
    if previous:
        if not previous.custody or identity(previous) != identity(source):
            raise InboxError("capture_policy_change_requires_migration")
        enrollment(root, source)
        return
    marker = record_path(root, source.id)
    if marker.exists() or marker.is_symlink():
        enrollment(root, source)
        return
    if inbox_path(root, source.id).exists():
        raise InboxError("capture_enrollment_missing")
    local_state.write(marker, {**identity(source), "state": "pending"})


def key_bytes(value):
    try:
        key = base64.b64decode(value, validate=True)
        if len(key) != 32:
            raise ValueError()
        return key
    except (TypeError, ValueError):
        raise InboxError("capture_key_unavailable") from None


def saved_source(root, source):
    from .desktop_sources import Source, load

    saved = next((item for item in load(root).sources if item.id == source.id), None)
    if (
        saved is None
        or Source.model_validate(saved.model_dump(include=set(Source.model_fields))) != source
    ):
        raise InboxError("capture_settings_changed")
    if not saved.custody or not saved.sealed_inbox_key:
        raise InboxError("capture_enrollment_missing")
    return saved


def limits(source):
    return Limits(pending_bytes=source.custody.pending_limit_mib * MIB)


@contextmanager
def opened(root, source, encoded_key, *, initialize=False):
    state = enrollment(root, source)
    if state["state"] in {"retired", "discarded"}:
        raise InboxError("capture_authorization_revoked")
    folder = inbox_path(root, source.id)
    pending = state["state"] == "pending"
    if pending and not initialize:
        raise InboxError("capture_not_initialized")
    create = pending and not (folder / "inbox.sqlite3").exists()
    with open_inbox(
        folder, binding(source), key_bytes(encoded_key), create=create, limits=limits(source)
    ) as inbox:
        if pending:
            # No acceptance may precede the durable ready marker. If its write
            # failed previously, only a verified, genuinely empty DB can resume.
            if any(
                inbox.connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
                for table in (
                    "events",
                    "pages",
                    "checkpoints",
                    "producer_segments",
                    "producer_events",
                )
            ):
                raise InboxError("capture_integrity_failed")
            state = {**state, "state": "ready"}
            local_state.write(record_path(root, source.id), state)
        yield inbox, state


def device_usage(root, current):
    """Count selected payload separately from bounded encrypted DB overhead.

    Call under the device admission lock. Other deliveries can only reduce
    pending payload; every desktop producer uses this same admission lock.
    No producer content or inbox key is read from other sources.
    """
    pending, database, retained_databases = 0, 0, 0
    for folder in root.glob("inbox-*"):
        if not folder.is_dir() or folder == current.root:
            continue
        local_state.directory(folder)
        path = folder / "inbox.sqlite3"
        if not path.exists():
            continue
        retained_databases += 1
        if retained_databases > 64:
            raise InboxError("capture_capacity_blocked")
        local_state._regular(path)
        if os.name == "nt":
            from .private_input import _windows_open

            os.close(_windows_open(path))
        try:
            connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
            try:
                connection.execute("PRAGMA trusted_schema=OFF")
                row = connection.execute(
                    "SELECT COALESCE(SUM(size),0) FROM events WHERE state='pending'"
                ).fetchone()
                pending += row[0]
                database += (
                    connection.execute("PRAGMA page_count").fetchone()[0]
                    * connection.execute("PRAGMA page_size").fetchone()[0]
                )
            finally:
                connection.close()
        except sqlite3.Error:
            raise InboxError("capture_storage_unavailable") from None
    own = current.status()
    return {
        "pending_bytes": pending + own["pending_bytes"],
        "database_bytes": database + own["database_bytes"],
    }


def local_capture(root, source, inbox, private_roots):
    from .desktop_sources import source_folder

    try:
        folder = source_folder(source, root, private_roots)
        marker = local_state.read(root / f"conversation-identity-{source.id}.json")
        info = folder.stat()
        if any(
            marker.get(key) != value
            for key, value in {
                "path": str(folder),
                "device": info.st_dev,
                "inode": info.st_ino,
                "scope_id": source.scope_id or "selected-source",
                "source_id": str(source.id),
            }.items()
        ):
            raise InboxError("capture_source_changed")
    except (OSError, ValueError, local_state.LocalSetupError):
        return {"completed": False, "scopes": [], "errors": ["capture_source_unavailable"]}
    with local_state.lock(local_state.directory(root / "inbox-budget")):
        usage = device_usage(root, inbox)
        own = inbox.status()
        inbox.limits = replace(
            inbox.limits,
            pending_bytes=max(
                1,
                min(
                    inbox.limits.pending_bytes,
                    DEVICE_PENDING_BYTES - usage["pending_bytes"] + own["pending_bytes"],
                ),
            ),
            database_bytes=max(
                65536,
                min(
                    inbox.limits.database_bytes,
                    DEVICE_DATABASE_BYTES - usage["database_bytes"] + own["database_bytes"],
                ),
            ),
        )
        provider = ConversationProvider(source.connector(root / f"capture-{source.id}").provider)
        return capture_available(inbox, provider)


def scan(root, source, encoded_key, credential, private_roots=()):
    began = time.monotonic()
    saved = saved_source(root, source)
    if not source.enabled:
        raise InboxError("capture_settings_changed")
    with opened(root, saved, encoded_key, initialize=True) as (inbox, state):

        def usage():
            with local_state.lock(local_state.directory(root / "inbox-budget")):
                return device_usage(root, inbox)

        return cycle(
            inbox,
            collect=(lambda: local_capture(root, source, inbox, private_roots))
            if state["state"] == "ready"
            else None,
            client=lambda: Client(source.endpoint, credential, timeout=10, retries=0),
            revoked=lambda: local_state.write(
                record_path(root, source.id), {**state, "state": "revoked"}
            ),
            usage=usage,
            started=began,
        )


def verify(source, root, client):
    from types import SimpleNamespace
    from .service.capture_models import CaptureSource

    page = client.request(
        "GET", f"/v1/connectors/{source.connector_id}/scopes", params={"limit": 1}
    )
    if page.get("items") or page.get("next_cursor") or not isinstance(page.get("items"), list):
        raise InboxError("capture_policy_change_requires_migration")
    grant = verify_grant(SimpleNamespace(binding=binding(source)), client)
    policy = CaptureSource.model_validate(
        client.request(
            "GET",
            f"/v1/connectors/{source.connector_id}/capture-sources/{source.custody.source_id}",
        )
    )
    if (
        policy.source_id != str(source.custody.source_id)
        or policy.connector_id != str(source.connector_id)
        or policy.namespace != (source.scope_id or "selected-source")
        or set(policy.members) != set(source.members)
        or policy.revoked_at
    ):
        raise InboxError("capture_binding_mismatch")
    if policy.has_capture_history:
        from .desktop_sources import load

        known = next((item for item in load(root).sources if item.id == source.id), None)
        if not known or not known.custody or binding(known) != binding(source):
            raise InboxError("capture_policy_change_requires_migration")
        # A fresh local enrollment cannot infer old accepted/forgotten ranges
        # from current files. Restore the matching private inbox and key first.
        if (
            enrollment(root, known)["state"] != "ready"
            or not (inbox_path(root, known.id) / "inbox.sqlite3").is_file()
        ):
            raise InboxError("capture_policy_change_requires_migration")
    return grant


def revoke_for_removal(source, credential):
    if not isinstance(credential, str) or not re.fullmatch(
        r"[A-Za-z0-9_.~+/=-]{16,1024}", credential
    ):
        raise InboxError("capture_retirement_credentials")
    with Client(source.endpoint, credential, timeout=10, retries=0) as client:
        retire_grant(binding(source), client)


def retire(root, request):
    """Confirm remote revocation before the explicit local discard.

    Offline users can pause immediately. Retirement waits for the server; a
    lost DELETE reply is reconciled by GET on the next invocation. Once the
    irreversible revocation is recorded, local cleanup can resume offline.
    """
    from .desktop_sources import load

    if (
        set(request)
        != {"operation", "id", "expected_revision", "credential", "discard_local_inbox"}
        or request["discard_local_inbox"] is not True
    ):
        raise ValueError("Confirm permanent removal of this device's selected inbox")
    with local_state.lock(root):
        current = load(root)
        source = next((item for item in current.sources if str(item.id) == request["id"]), None)
        if (
            current.revision != request["expected_revision"]
            or source is None
            or not source.custody
            or source.enabled
        ):
            raise InboxError("capture_settings_changed")
        state = enrollment(root, source)
    if state["state"] not in {"retired", "discarded"}:
        # An administrator can confirm this exact grant after a device key is
        # lost or revoked. This one-use credential never changes saved keys or
        # authorizes intake. Current server rights and the full binding apply.
        revoke_for_removal(source, request["credential"])
        with local_state.lock(root):
            refreshed = load(root)
            if refreshed.revision != current.revision:
                raise InboxError("capture_settings_changed")
            state = {**state, "state": "retired"}
            local_state.write(record_path(root, source.id), state)
    # A retained retirement record prevents any subsequent scan/re-enrollment.
    # Only known, private database files are removed, never producer files.
    folder = inbox_path(root, source.id)
    if folder.exists():
        with local_state.lock(local_state.directory(folder)):
            for name in (
                "inbox.sqlite3",
                "inbox.sqlite3-journal",
                "inbox.sqlite3-wal",
                "inbox.sqlite3-shm",
            ):
                path = folder / name
                if path.exists() or path.is_symlink():
                    local_state._regular(path)
                    if os.name == "nt":
                        from .private_input import _windows_open

                        os.close(_windows_open(path))
                    path.unlink()
            local_state._sync_directory(folder)
    local_state.write(record_path(root, source.id), {**state, "state": "discarded"})
    return {"retired": True, "remote_grant_revoked": True, "local_inbox_discarded": True}
