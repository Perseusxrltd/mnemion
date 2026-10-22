"""Recover selected evidence onto a new, paused, currently authorized device.

The private helper receives OS-sealed settings from the native controller. It
publishes a resumable local intent before moving evidence into the device inbox;
an interruption never initializes or overwrites an existing source.
"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
import os
import time
from types import SimpleNamespace
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from . import desktop_capture as capture, local_state
from .archives import _rename_exclusive
from .capture_coverage import utc_now, utc_timestamp
from .capture_policy import CapturePolicy
from .connectors.capture_archive import _audit
from .connectors.capture_delivery import verify_grant
from .connectors.capture_transfer import (
    device_binding,
    policy_binding,
    restore_device_copy,
    restore_policy_copy,
)
from .connectors.conversation_inbox import InboxError, binding_value, open_inbox
from .connectors.live_conversations import ConversationProvider
from .desktop_capture_backup import Inspection
from .desktop_capture_preview import normalize, selection_for
from .desktop_sources import SavedSource, SourceState, load, source_folder
from .desktop_source_identity import _verify_copy
from .sdk import Client
from .service.capture_models import CaptureSource
from .service.models import Command

MAX_RECOVERIES = 16


class Intent(Command):
    format: Literal["mnemion-capture-recovery-v1"]
    created_at: str = Field(max_length=32)
    archive_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    original_binding: dict
    previous_grant_revoked: Literal[True]
    source: SavedSource
    policy_change: bool = Field(default=False, strict=True)
    replaces: SavedSource | None = Field(default=None, repr=False)

    _time = field_validator("created_at")(utc_timestamp)

    @field_validator("original_binding")
    @classmethod
    def original(cls, value):
        return binding_value(value)


class Restore(Inspection):
    operation: Literal["capture_restore"]
    expected_revision: str = Field(min_length=1, max_length=128)
    archive_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source: SavedSource
    preview_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    credential: str = Field(min_length=16, max_length=8192, pattern=r"^[\x21-\x7e]+$", repr=False)
    retirement_credential: str = Field(
        min_length=16, max_length=1024, pattern=r"^[\x21-\x7e]+$", repr=False
    )
    inbox_key: str = Field(min_length=44, max_length=44, repr=False)
    policy_change: bool = Field(default=False, strict=True)
    replace_id: UUID | None = None
    previous_inbox_key: str | None = Field(default=None, min_length=44, max_length=44, repr=False)
    confirm: Literal[True]

    @model_validator(mode="after")
    def reviewed_replacement(self):
        if (self.replace_id is not None or self.previous_inbox_key is not None) and (
            not self.policy_change or self.replace_id is None or self.previous_inbox_key is None
        ):
            raise ValueError("Review the original device and unlock its inbox for a policy change")
        return self

    @field_validator("confirm", mode="before")
    @classmethod
    def confirmation(cls, value):
        if value is not True:
            raise ValueError("Confirm recovery and retirement of the previous device grant")
        return value


class RecoveryControl(Command):
    operation: Literal["capture_restore_load", "capture_restore_finish", "capture_restore_discard"]
    id: UUID
    expected_revision: str = Field(min_length=1, max_length=128)
    credential: str | None = Field(default=None, min_length=16, max_length=8192, repr=False)
    inbox_key: str | None = Field(default=None, min_length=44, max_length=44, repr=False)
    confirm: bool = Field(default=False, strict=True)
    file: str | None = Field(default=None, max_length=4096)
    recovery_key: str | None = Field(default=None, min_length=50, max_length=50, repr=False)


def intent_path(root, identifier):
    return root / f"inbox-recovery-{identifier}.json"


def read_intent(root, identifier):
    value = Intent.model_validate(local_state.read(intent_path(root, identifier)))
    source = value.source
    if (
        source.id != identifier
        or source.provider != "conversations"
        or source.enabled
        or not source.custody
        or source.custody.grant_id == UUID(value.original_binding["grant_id"])
    ):
        raise InboxError("capture_binding_mismatch")
    (policy_binding if value.policy_change else device_binding)(
        value.original_binding, capture.binding(source)
    )
    if value.replaces is not None:
        if not value.policy_change or capture.binding(value.replaces) != value.original_binding:
            raise InboxError("capture_binding_mismatch")
        _replacement(value.replaces, source)
    return value


def list_intents(root):
    rows = []
    for path in root.glob("inbox-recovery-*.json"):
        if len(rows) >= MAX_RECOVERIES:
            raise InboxError("capture_capacity_blocked")
        identifier = UUID(path.name.removeprefix("inbox-recovery-").removesuffix(".json"))
        intent = read_intent(root, identifier)
        rows.append(
            {
                "id": str(identifier),
                "name": intent.source.name,
                "endpoint": intent.source.endpoint,
                "archive_sha256": intent.archive_sha256,
                "created_at": intent.created_at,
                "copy_available": capture.inbox_path(root, identifier).exists(),
                **({"policy_change": True} if intent.policy_change else {}),
            }
        )
    return {
        "format": "mnemion-capture-recoveries-v1",
        "items": sorted(rows, key=lambda item: item["id"]),
    }


def pending_replacement(root, source_id):
    """A paused predecessor cannot collect again during an unfinished handover."""
    for row in list_intents(root)["items"]:
        intent = read_intent(root, UUID(row["id"]))
        if intent.replaces and intent.replaces.id == source_id:
            return True
    return False


def _current(root, expected):
    current = load(root)
    if current.revision != expected:
        raise InboxError("capture_settings_changed")
    return current


def _verify_target(root, source, credential, private_roots, *, current_policy=False):
    source.path = str(source_folder(source, root, private_roots))
    with Client(source.endpoint, credential, timeout=15, retries=0) as client:
        me = client.request("GET", "/v1/me")
        if (
            me.get("tenant_id") != str(source.tenant_id)
            or me.get("principal_id") != str(source.principal_id)
            or me.get("administrator") is not False
        ):
            raise InboxError("capture_binding_mismatch")
        connector = next(
            (
                item
                for item in client.request("GET", "/v1/connectors").get("items", [])
                if item.get("id") == str(source.connector_id)
            ),
            {},
        )
        if (
            connector.get("provider") != "conversations"
            or connector.get("access_mode") != "published"
            or connector.get("principal_id") != str(source.principal_id)
            or connector.get("disabled_at") is not None
        ):
            raise InboxError("capture_binding_mismatch")
        verify_grant(SimpleNamespace(binding=capture.binding(source)), client)
        remote = CaptureSource.model_validate(
            client.request(
                "GET",
                f"/v1/connectors/{source.connector_id}/capture-sources/{source.custody.source_id}",
            )
        )
        if remote.revoked_at or set(remote.members) != set(source.members):
            raise InboxError("capture_settings_changed")
        if current_policy and (
            remote.capture_policy != source.capture_policy
            or remote.capture_mode != source.capture_mode
        ):
            raise InboxError("capture_settings_changed")


def _receipt(intent, status):
    return {
        "format": "mnemion-capture-restored-v1",
        "id": str(intent.source.id),
        "archive_sha256": intent.archive_sha256,
        "previous_grant_id": intent.original_binding["grant_id"],
        "grant_id": str(intent.source.custody.grant_id),
        "previous_grant_revoked": True,
        "source_enrolled": True,
        "source_enabled": False,
        "status": status,
        **({"policy_change": True} if intent.policy_change else {}),
        **({"replaced_source_id": str(intent.replaces.id)} if intent.replaces else {}),
    }


def _replacement(previous, source):
    if (
        previous.enabled
        or not previous.custody
        or previous.id == source.id
        or any(
            getattr(previous, field) != getattr(source, field)
            for field in (
                "endpoint",
                "tenant_id",
                "connector_id",
                "principal_id",
                "provider",
                "path",
            )
        )
    ):
        raise InboxError("capture_settings_changed")
    policy_binding(capture.binding(previous), capture.binding(source))


def _verify_producer_copy(source, inbox):
    adapter = ConversationProvider(source.connector(inbox.root / "capture-preview").provider)
    adapter.scopes()
    deadline = time.monotonic() + 45
    for scope, value in inbox.connection.execute("SELECT scope,payload FROM checkpoints"):
        if time.monotonic() >= deadline:
            raise InboxError("capture_source_changed")
        relative = adapter.paths.get(scope)
        if relative is not None:
            import json

            checkpoint = json.loads(inbox._open(value, "checkpoint:" + scope))
            try:
                _verify_copy(adapter.root, relative, checkpoint.get("checkpoint") or "", deadline)
            except local_state.LocalSetupError as error:
                # Preserve the copied-prefix diagnostic instead of letting the
                # inbox context translate it into an unrelated storage error.
                raise InboxError(error.code) from None


def _admit(root, inbox):
    usage = capture.device_usage(root, inbox)
    if (
        usage["pending_bytes"] > capture.DEVICE_PENDING_BYTES
        or usage["database_bytes"] > capture.DEVICE_DATABASE_BYTES
    ):
        raise InboxError("capture_capacity_blocked")


def _producer_marker(root, source):
    folder = Path(source.path)
    info = folder.stat()
    return {
        "format": 1,
        "source_id": str(source.id),
        "endpoint": source.endpoint,
        "tenant_id": str(source.tenant_id),
        "connector_id": str(source.connector_id),
        "principal_id": str(source.principal_id),
        "path": str(folder),
        "scope_id": source.scope_id or "selected-source",
        "device": info.st_dev,
        "inode": info.st_ino,
    }


def _publish(root, current, intent, inbox_key):
    source = intent.source
    existing = next((item for item in current.sources if item.id == source.id), None)
    if existing is not None and (
        capture.identity(existing) != capture.identity(source)
        or existing.sealed_key != source.sealed_key
    ):
        raise InboxError("capture_settings_changed")
    previous = None
    if intent.replaces:
        previous = next((item for item in current.sources if item.id == intent.replaces.id), None)
        if (previous is not None and previous.model_dump() != intent.replaces.model_dump()) or (
            previous is None and existing is None
        ):
            raise InboxError("capture_settings_changed")
        _replacement(intent.replaces, source)
    with open_inbox(
        capture.inbox_path(root, source.id),
        capture.binding(source),
        inbox_key,
        limits=capture.limits(source),
    ) as inbox:
        status = _audit(inbox)
        _verify_producer_copy(source, inbox)
        _admit(root, inbox)
    marker = {**capture.identity(source), "state": "ready"}
    marker_path = capture.record_path(root, source.id)
    if marker_path.exists():
        if local_state.read(marker_path) != marker:
            raise InboxError("capture_binding_mismatch")
    else:
        local_state.write(marker_path, marker, replace=False)
    local_state.write(
        root / f"conversation-identity-{source.id}.json", _producer_marker(root, source)
    )
    if intent.replaces:
        old = intent.replaces
        state = capture.enrollment(root, old)
        local_state.write(capture.record_path(root, old.id), {**state, "state": "retired"})
    if existing is None:
        retained = [item for item in current.sources if not previous or item.id != previous.id]
        current = SourceState(revision=str(uuid4()), sources=[*retained, source])
        local_state.write(root / "sources.json", current.model_dump(mode="json", exclude_none=True))
    receipt = _receipt(intent, status)
    receipt["source_enabled"] = existing.enabled if existing else False
    # Keep the non-secret origin receipt; delete duplicate OS-sealed credentials
    # only after the live source settings and its ready marker are durable.
    local_state.write(root / f"inbox-origin-{source.id}.json", receipt)
    intent_path(root, source.id).unlink()
    local_state._sync_directory(root)
    return {"document": current.model_dump(mode="json", exclude_none=True), "recovery": receipt}


def restore(root, request, private_roots):
    source = request.source
    if source.provider != "conversations" or not source.custody or source.enabled:
        raise ValueError("Recover a retained conversation source in the paused state")
    source.path = str(source_folder(source, root, private_roots))
    preview = normalize(root, selection_for(source), private_roots)
    if preview.fingerprint != request.preview_hash:
        raise InboxError("capture_settings_changed")
    inbox_key = capture.key_bytes(request.inbox_key)
    with local_state.lock(root):
        current = _current(root, request.expected_revision)
        previous = None
        if request.replace_id:
            previous = next(
                (item for item in current.sources if item.id == request.replace_id), None
            )
            if previous is None:
                raise InboxError("capture_settings_changed")
            previous = SavedSource.model_validate(previous.model_dump())
            _replacement(previous, source)
        if any(
            item.id == source.id
            or (
                (item.endpoint, item.connector_id) == (source.endpoint, source.connector_id)
                and item.id != request.replace_id
            )
            for item in current.sources
        ):
            raise InboxError("capture_settings_changed")
        if list_intents(root)["items"]:
            raise local_state.LocalSetupError(
                "capture_recovery_pending",
                "Finish the pending capture recovery before starting another.",
            )
        if (
            capture.inbox_path(root, source.id).exists()
            or capture.record_path(root, source.id).exists()
        ):
            raise InboxError("capture_enrollment_missing")
        source.status_epoch = uuid4()
        SourceState(
            revision=str(uuid4()),
            sources=[*(item for item in current.sources if item.id != request.replace_id), source],
        )
        with ExitStack() as stack:
            temporary = stack.enter_context(
                local_state.temporary_directory(prefix="capture-recover-", dir=root)
            )
            original = (
                stack.enter_context(capture.opened(root, previous, request.previous_inbox_key))[0]
                if previous
                else None
            )
            recovered = (restore_policy_copy if request.policy_change else restore_device_copy)(
                request.file,
                request.recovery_key,
                temporary / "inbox",
                staging_root=local_state.directory(root / "capture-backups"),
                expected_sha256=request.archive_sha256,
                selected_binding=capture.binding(source),
                inbox_key=inbox_key,
                **({"original_inbox": original} if request.policy_change else {}),
            )
            if recovered.original_binding["grant_id"] == str(source.custody.grant_id):
                raise InboxError("capture_binding_mismatch")
            with open_inbox(recovered.directory, recovered.binding, inbox_key) as inbox:
                _verify_producer_copy(source, inbox)
                _admit(root, inbox)
            _verify_target(
                root,
                source,
                request.credential,
                private_roots,
                current_policy=request.policy_change,
            )
            old = previous or source.model_copy(deep=True)
            if previous is None:
                old.custody.grant_id = UUID(recovered.original_binding["grant_id"])
                old.capture_mode = recovered.original_binding["capture_mode"]
                old.capture_policy = (
                    CapturePolicy.model_validate(recovered.original_binding["capture_policy"])
                    if recovered.original_binding.get("capture_policy")
                    else None
                )
            capture.revoke_for_removal(old, request.retirement_credential)
            intent = Intent(
                format="mnemion-capture-recovery-v1",
                created_at=utc_now(),
                archive_sha256=request.archive_sha256,
                original_binding=recovered.original_binding,
                previous_grant_revoked=True,
                source=source,
                policy_change=request.policy_change,
                replaces=previous,
            )
            local_state.write(
                intent_path(root, source.id),
                intent.model_dump(mode="json", exclude_none=True),
                replace=False,
            )
            with local_state.lock(local_state.directory(root / "inbox-budget")):
                _rename_exclusive(recovered.directory, capture.inbox_path(root, source.id))
                local_state._sync_directory(root)
                return _publish(root, current, intent, inbox_key)


def _discard(root, current, intent, credential):
    source = intent.source
    if any(item.id == source.id for item in current.sources):
        raise InboxError("capture_settings_changed")
    if intent.replaces:
        previous = next((item for item in current.sources if item.id == intent.replaces.id), None)
        if previous is None or previous.model_dump() != intent.replaces.model_dump():
            raise InboxError("capture_settings_changed")
    capture.revoke_for_removal(source, credential)
    folder = capture.inbox_path(root, source.id)
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
    marker = capture.record_path(root, source.id)
    if marker.exists():
        expected = {**capture.identity(source), "state": "ready"}
        if local_state.read(marker) != expected:
            raise InboxError("capture_binding_mismatch")
        local_state.write(marker, {**expected, "state": "discarded"})
    if intent.replaces:
        old = intent.replaces
        state = capture.enrollment(root, old)
        # A discarded replacement cannot revive the old grant. Keep the
        # original paused inbox readable for backup or a fresh reviewed retry.
        local_state.write(capture.record_path(root, old.id), {**state, "state": "revoked"})
    intent_path(root, source.id).unlink()
    local_state._sync_directory(root)
    return {"discarded": True, "replacement_grant_revoked": True, "archive_modified": False}


def perform(root, value, private_roots=()):
    root = local_state.directory(Path(root))
    if value.get("operation") == "capture_restore_list":
        if set(value) != {"operation"}:
            raise ValueError("Read pending capture recoveries without credentials")
        return list_intents(root)
    if value.get("operation") == "capture_restore":
        return restore(root, Restore.model_validate(value), private_roots)
    request = RecoveryControl.model_validate(value)
    with local_state.lock(root):
        current = _current(root, request.expected_revision)
        intent = read_intent(root, request.id)
        if request.operation == "capture_restore_load":
            if (
                request.credential
                or request.inbox_key
                or request.confirm
                or request.file
                or request.recovery_key
            ):
                raise ValueError("Load only the pending recovery's protected source settings")
            return {
                "source": intent.source.model_dump(mode="json", exclude_none=True),
                "archive_sha256": intent.archive_sha256,
                "previous_grant_id": intent.original_binding["grant_id"],
            }
        if not request.confirm or not request.credential:
            raise ValueError("Confirm recovery with this device's protected keys")
        if request.operation == "capture_restore_discard":
            if request.file or request.recovery_key or request.inbox_key:
                raise ValueError("Discard only the selected unfinished recovery")
            return _discard(root, current, intent, request.credential)
        if not request.inbox_key:
            raise ValueError("Unlock the device inbox key before finishing recovery")
        _verify_target(root, intent.source, request.credential, private_roots)
        inbox_key = capture.key_bytes(request.inbox_key)
        target = capture.inbox_path(root, request.id)
        with local_state.lock(local_state.directory(root / "inbox-budget")):
            if not target.exists():
                if not request.file or not request.recovery_key:
                    raise local_state.LocalSetupError(
                        "capture_recovery_archive_required",
                        "Choose the original backup and recovery key to finish this interrupted copy.",
                    )
                file = Inspection(
                    operation="capture_inspect",
                    file=request.file,
                    recovery_key=request.recovery_key,
                )
                restored = (restore_policy_copy if intent.policy_change else restore_device_copy)(
                    file.file,
                    file.recovery_key,
                    target,
                    staging_root=local_state.directory(root / "capture-backups"),
                    expected_sha256=intent.archive_sha256,
                    selected_binding=capture.binding(intent.source),
                    inbox_key=inbox_key,
                )
                if restored.original_binding != intent.original_binding:
                    raise InboxError("capture_binding_mismatch")
            return _publish(root, current, intent, inbox_key)
