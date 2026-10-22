"""Bounded agent controls; credential material stays in private references."""

from __future__ import annotations

import base64
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import time
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .. import backup_encryption, local_state
from ..archives import _rename_exclusive
from ..desktop_source_identity import _verify_copy
from ..private_output import private_output
from ..sdk import Client
from ..service.models import Command
from . import headless_capture as device
from .capture_archive import _audit, export_archive, inspect_archive
from .capture_delivery import retire_grant
from .capture_transfer import restore_device_copy
from .config import Token
from .conversation_inbox import InboxError, open_inbox
from .live_conversations import ConversationProvider


class Control(Command):
    action: Literal[
        "status",
        "preview",
        "key",
        "enroll",
        "pause",
        "resume",
        "backup",
        "inspect",
        "restore",
        "finish",
        "discard",
        "retire",
    ]
    confirm: bool = Field(default=False, strict=True)
    expected_revision: str | None = Field(default=None, min_length=1, max_length=128)
    preview_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    archive: str | None = Field(default=None, min_length=1, max_length=4096)
    archive_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    recovery_key: Token | None = None
    retirement_token: Token | None = None
    key_purpose: Literal["inbox", "recovery"] = "inbox"

    @field_validator("archive")
    @classmethod
    def absolute_file(cls, value):
        if value is not None and not Path(value).is_absolute():
            raise ValueError("Use an absolute archive path")
        return value

    @model_validator(mode="after")
    def required(self):
        needs = {
            "enroll": {"expected_revision", "preview_hash"},
            "pause": {"expected_revision"},
            "resume": {"expected_revision"},
            "backup": {"expected_revision", "archive", "recovery_key"},
            "inspect": {"archive", "recovery_key"},
            "restore": {
                "expected_revision",
                "preview_hash",
                "archive",
                "archive_sha256",
                "recovery_key",
                "retirement_token",
            },
            "finish": {"expected_revision", "archive", "archive_sha256", "recovery_key"},
            "discard": {"expected_revision", "retirement_token"},
            "retire": {"expected_revision", "retirement_token"},
        }.get(self.action, set())
        if any(getattr(self, field) is None for field in needs):
            raise ValueError("Supply the references and current revision for this action")
        if self.action not in {"status", "preview", "inspect", "pause"} and not self.confirm:
            raise ValueError("Explicitly confirm this action")
        if self.action == "key" and self.key_purpose == "recovery" and self.recovery_key is None:
            raise ValueError("Choose a private output reference for the recovery key")
        for token in (self.recovery_key, self.retirement_token):
            if token and token.file and not token.file.is_absolute():
                raise ValueError("Use absolute private credential paths in control requests")
        return self


def external(config, value):
    path = Path(value).absolute()
    resolved = path.resolve()
    # A producer can be temporarily missing. Still reject its path and every
    # child, and never put archives/keys inside the working inbox itself.
    for protected in (config.provider.path.resolve(), device.paths(config)[2].resolve()):
        if resolved == protected or protected in resolved.parents:
            raise InboxError("capture_storage_not_private")
    return path


def recovery_key(config, request):
    if request.recovery_key.file:
        external(config, request.recovery_key.file)
    value = device.reference(request.recovery_key)
    backup_encryption.key_id(value)
    return value


def generate_key(config, request):
    token = config.capture.inbox_key if request.key_purpose == "inbox" else request.recovery_key
    if token.file is None:
        raise InboxError("capture_key_file_required")
    with device.locked(config):
        if (
            request.key_purpose == "inbox"
            and device.read_record(config, required=False) is not None
        ):
            raise InboxError("capture_settings_changed")
        path = external(config, token.file)
        local_state.directory(path.parent)
        value = (
            base64.b64encode(os.urandom(32)).decode()
            if request.key_purpose == "inbox"
            else backup_encryption.new_key()
        )
        with private_output(path) as stream:
            stream.write((value + "\n").encode("ascii"))
        local_state._sync_directory(path.parent)
    return {"created": True, "purpose": request.key_purpose, "key_printed": False}


def backup(config, request):
    archive, key = external(config, request.archive), recovery_key(config, request)
    with device.locked(config):
        record = device.read_record(config)
        device.revision(record, request.expected_revision)
        if record["enabled"] or record["state"] in {"pending", "recovering"}:
            raise InboxError("capture_pause_required")
        with device.opened(config, record) as (inbox, _, inbox_key):
            return export_archive(
                inbox,
                inbox_key,
                archive,
                key,
                staging_root=device.root(config) / "capture-backups",
                name=config.provider.name,
            )


def retire(config, request, *, discard=False):
    if request.retirement_token.file:
        external(config, request.retirement_token.file)
    with device.locked(config):
        record = device.read_record(config)
        device.revision(record, request.expected_revision)
        if discard and record["state"] not in {"recovering", "discarding", "discarded"}:
            raise InboxError("capture_settings_changed")
        if record["state"] not in {"retired", "discarding", "discarded"}:
            with Client(
                config.service_url,
                device.reference(request.retirement_token),
                timeout=10,
                retries=0,
            ) as client:
                retire_grant(device.binding(config), client)
            record = device.write_record(
                config, record, state="discarding" if discard else "retired", enabled=False
            )
        if discard and device.paths(config)[2].exists():
            # The retirement record is durable before deleting this unfinished
            # device copy. Original producer data and its archive are untouched.
            directory = device.paths(config)[2]
            with local_state.lock(directory):
                for name in (
                    "inbox.sqlite3",
                    "inbox.sqlite3-journal",
                    "inbox.sqlite3-wal",
                    "inbox.sqlite3-shm",
                ):
                    path = directory / name
                    if path.exists() or path.is_symlink():
                        local_state._regular(path)
                        if os.name == "nt":
                            from ..private_input import _windows_open

                            os.close(_windows_open(path))
                        path.unlink()
                local_state._sync_directory(directory)
        if discard and record["state"] != "discarded":
            device.write_record(config, record, state="discarded", enabled=False)
    return device.status(config)


def producer_identity(config):
    producer = device.folder(config)
    info = producer.stat()
    return {"path": str(producer), "device": info.st_dev, "inode": info.st_ino}


def verify_producer_copy(config, inbox):
    adapter = ConversationProvider(config.provider)
    adapter.scopes()
    deadline = time.monotonic() + 45
    for scope, value in inbox.connection.execute("SELECT scope,payload FROM checkpoints"):
        if time.monotonic() >= deadline:
            raise InboxError("capture_source_changed")
        relative = adapter.paths.get(scope)
        if relative is not None:
            checkpoint = json.loads(inbox._open(value, "checkpoint:" + scope))
            try:
                _verify_copy(adapter.root, relative, checkpoint.get("checkpoint") or "", deadline)
            except local_state.LocalSetupError as error:
                raise InboxError(error.code) from None


def finish_copy(config, record, request, key):
    proof = record["recovery"]
    if request.archive_sha256 != proof["archive_sha256"]:
        raise InboxError("capture_settings_changed")
    with device.connect(config) as client:
        device.verify(config, client, existing=True)
    destination = device.paths(config)[2]
    inbox_key = device.key_bytes(device.reference(config.capture.inbox_key))
    if hashlib.sha256(inbox_key).hexdigest() != record["key_sha256"]:
        raise InboxError("capture_key_unavailable")
    with local_state.lock(device.root(config) / "inbox-budget"):
        if not destination.exists():
            restore_device_copy(
                external(config, request.archive),
                key,
                destination,
                staging_root=device.root(config) / "capture-backups",
                expected_sha256=request.archive_sha256,
                selected_binding=device.binding(config),
                inbox_key=inbox_key,
            )
        with device.opened(config, record) as (inbox, _, _):
            _audit(inbox, None)
            usage = device.device_usage(device.root(config), inbox)
            if (
                usage["pending_bytes"] > device.DEVICE_PENDING_BYTES
                or usage["database_bytes"] > device.DEVICE_DATABASE_BYTES
            ):
                raise InboxError("capture_capacity_blocked")
            if record["folder"] != producer_identity(config):
                raise InboxError("capture_source_changed")
            verify_producer_copy(config, inbox)
            device.write_record(config, record, state="ready", enabled=False)
    return device.status(config)


def restore(config, request, *, finishing=False):
    key = recovery_key(config, request)
    archive = external(config, request.archive)
    with device.locked(config):
        current = device.read_record(config, required=False)
        device.revision(current, request.expected_revision)
        if finishing:
            if current is None or current["state"] != "recovering" or current["recovery"] is None:
                raise InboxError("capture_settings_changed")
            return finish_copy(config, current, request, key)
        if current is not None:
            raise InboxError("capture_settings_changed")
        reviewed = device.preview(config)
        if reviewed["configuration_hash"] != request.preview_hash:
            raise InboxError("capture_settings_changed")
        inbox_key = device.key_bytes(device.reference(config.capture.inbox_key))
        producer = producer_identity(config)
        if request.retirement_token.file:
            external(config, request.retirement_token.file)
        with local_state.lock(device.root(config)):
            if (
                len(
                    list(
                        islice(
                            device.root(config).glob("headless-source-*.json"), device.MAX_DEVICES
                        )
                    )
                )
                >= device.MAX_DEVICES
            ):
                raise InboxError("capture_capacity_blocked")
            if device.paths(config)[2].exists() or device.paths(config)[2].is_symlink():
                raise InboxError("capture_enrollment_missing")
            with local_state.temporary_directory(
                prefix="headless-recover-", dir=device.root(config)
            ) as temporary:
                recovered = restore_device_copy(
                    archive,
                    key,
                    temporary / "inbox",
                    staging_root=device.root(config) / "capture-backups",
                    expected_sha256=request.archive_sha256,
                    selected_binding=device.binding(config),
                    inbox_key=inbox_key,
                )
                original = recovered.original_binding
                if original["grant_id"] == str(config.capture.grant_id):
                    raise InboxError("capture_binding_mismatch")
                # Verify the copy, selected producer prefixes and local capacity
                # before any irreversible remote retirement. The private intent
                # then makes publication failures explicitly resumable.
                with open_inbox(recovered.directory, recovered.binding, inbox_key) as inbox:
                    verify_producer_copy(config, inbox)
                    with local_state.lock(device.root(config) / "inbox-budget"):
                        usage = device.device_usage(device.root(config), inbox)
                        if (
                            usage["pending_bytes"] > device.DEVICE_PENDING_BYTES
                            or usage["database_bytes"] > device.DEVICE_DATABASE_BYTES
                        ):
                            raise InboxError("capture_capacity_blocked")
                with device.connect(config) as client:
                    device.verify(config, client, existing=True)
                with Client(
                    config.service_url,
                    device.reference(request.retirement_token),
                    timeout=10,
                    retries=0,
                ) as client:
                    retire_grant(original, client)
                record = device.write_record(
                    config,
                    {
                        "format": device.FORMAT,
                        "id": str(config.capture.id),
                        "identity": device.identity(config),
                        "binding": device.binding(config),
                        "state": "recovering",
                        "enabled": False,
                        "key_sha256": hashlib.sha256(inbox_key).hexdigest(),
                        "folder": producer,
                        "recovery": {
                            "archive_sha256": request.archive_sha256,
                            "original_binding": original,
                            "previous_grant_revoked": True,
                        },
                    },
                )
                with local_state.lock(device.root(config) / "inbox-budget"):
                    _rename_exclusive(recovered.directory, device.paths(config)[2])
                    local_state._sync_directory(device.root(config))
                    device.write_record(config, record, state="ready", enabled=False)
        return device.status(config)


def perform(config, value):
    if config.capture is None:
        raise InboxError("capture_enrollment_missing")
    request = Control.model_validate(value)
    if request.action == "status":
        return device.status(config)
    if request.action == "preview":
        return device.preview(config)
    if request.action == "key":
        return generate_key(config, request)
    if request.action == "enroll":
        return device.enroll(config, request.model_dump(mode="json"))
    if request.action in {"pause", "resume"}:
        return device.set_enabled(
            config, request.model_dump(mode="json"), request.action == "resume"
        )
    if request.action == "backup":
        return backup(config, request)
    if request.action == "inspect":
        return inspect_archive(
            external(config, request.archive),
            recovery_key(config, request),
            staging_root=device.root(config) / "capture-backups",
        )
    if request.action in {"retire", "discard"}:
        return retire(config, request, discard=request.action == "discard")
    return restore(config, request, finishing=request.action == "finish")
