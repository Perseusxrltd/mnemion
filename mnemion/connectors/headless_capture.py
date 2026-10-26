"""Explicit headless custody with a persistent, private device enrollment.

The runner commits selected evidence before opening its remote credential or
client. Configuration alone cannot enroll, unpause or recreate a lost inbox.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import hashlib
from itertools import islice
import os
from types import SimpleNamespace
from typing import Literal
from uuid import uuid4

import psutil
from pydantic import Field, field_validator, model_validator

from .. import local_state, process_identity
from ..capture_coverage import utc_now, utc_timestamp
from ..capture_identity import canonical_capture_json
from ..desktop_capture import (
    CAPTURE_REASONS,
    DEVICE_DATABASE_BYTES,
    DEVICE_PENDING_BYTES,
    device_usage,
    key_bytes,
)
from ..desktop_capture_preview import PreviewSelection, preview as capture_preview
from ..desktop_source_status import Report
from ..desktop_sources import source_folder
from ..private_input import read_private
from ..sdk import Client
from ..service.capture_models import CaptureSource
from ..service.models import Command
from .capture_cycle import cycle
from .capture_delivery import verify_grant
from .conversation_capture import capture_available
from .conversation_inbox import InboxError, Limits, binding_value, open_inbox
from .live_conversations import ConversationProvider

FORMAT = "mnemion-headless-capture-v1"
MIB = 1024**2
MAX_DEVICES = 64


class DeviceFolder(Command):
    path: str = Field(min_length=1, max_length=4096)
    device: int = Field(ge=0, strict=True)
    inode: int = Field(ge=0, strict=True)


class Recovery(Command):
    archive_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    original_binding: dict
    previous_grant_revoked: bool = Field(strict=True)
    policy_change: bool = Field(default=False, strict=True)

    _binding = field_validator("original_binding")(binding_value)


class Enrollment(Command):
    format: Literal["mnemion-headless-capture-v1", "mnemion-headless-capture-v2"]
    id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    identity: str = Field(pattern=r"^[a-f0-9]{64}$")
    binding: dict
    state: Literal[
        "pending", "recovering", "ready", "revoked", "retired", "discarding", "discarded"
    ]
    enabled: bool = Field(strict=True)
    revision: str = Field(pattern=r"^[a-f0-9-]{36}$")
    updated_at: str
    key_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    folder: DeviceFolder
    recovery: Recovery | None = None

    _binding = field_validator("binding")(binding_value)
    _time = field_validator("updated_at")(utc_timestamp)

    @model_validator(mode="after")
    def retirement_state(self):
        if (
            self.recovery
            and not self.recovery.previous_grant_revoked
            and (
                self.format != "mnemion-headless-capture-v2"
                or self.state not in {"recovering", "retired", "discarding", "discarded"}
                or self.enabled
            )
        ):
            raise ValueError("Unconfirmed grant retirement cannot activate a recovered device")
        return self


class Activity(Command):
    format: Literal["mnemion-headless-capture-v1"]
    id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    state: Literal["scanning", "failed", "finished"]
    pid: int = Field(gt=0, lt=2**32, strict=True)
    process: dict = Field(max_length=8)
    started_at: str
    finished_at: str | None = None
    reason_code: str | None = None
    report: Report | None = None

    _time = field_validator("started_at", "finished_at")(utc_timestamp)

    @field_validator("reason_code")
    @classmethod
    def reason(cls, value):
        if value is not None and value not in CAPTURE_REASONS:
            raise ValueError("Use a bounded capture observation")
        return value


def reference(token):
    """Strict protected files for this mode; never repair an unsafe input."""
    try:
        value = (
            os.environ.get(token.env, "")
            if token.env
            else read_private(token.file.expanduser(), maximum=16384).decode("ascii")
        ).strip()
        if not value or len(value) > 16384 or any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise ValueError()
        return value
    except (OSError, ValueError, local_state.LocalSetupError):
        raise InboxError("capture_key_unavailable") from None


def root(config):
    if config.capture is None:
        raise InboxError("capture_enrollment_missing")
    return local_state.directory(config.capture.state_directory.absolute())


def paths(config):
    base = root(config)
    identifier = str(config.capture.id)
    return (
        base / f"headless-source-{identifier}.json",
        base / f"headless-status-{identifier}.json",
        base / f"inbox-{identifier}",
    )


def private_roots(config):
    return [
        config.provider.state_directory,
        *([config._file_path] if config._file_path else []),
        *[
            value.file
            for value in (config.service_token, config.capture.inbox_key)
            if value.file is not None
        ],
    ]


def folder(config):
    return source_folder(config.provider, root(config), private_roots(config))


def binding(config):
    return {
        "tenant_id": str(config.capture.tenant_id),
        "connector_id": str(config.connector_id),
        "source_id": str(config.capture.source_id),
        "grant_id": str(config.capture.grant_id),
        "namespace": config.provider.scope_id,
        "capture_mode": config.provider.capture_mode,
        **(
            {"capture_policy": config.provider.capture_policy.model_dump(mode="json")}
            if config.provider.capture_policy
            else {}
        ),
    }


def selection(config):
    return PreviewSelection(
        path=str(config.provider.path.absolute()),
        capture_mode=config.provider.capture_mode,
        capture_policy=config.provider.capture_policy,
        keep_accepted=True,
        memory_limit_mib=config.capture.memory_limit_mib,
        max_files=config.provider.max_files,
        pending_limit_mib=config.capture.pending_limit_mib,
        history_limit_events=config.capture.history_limit_events,
        database_limit_mib=config.capture.database_limit_mib,
    )


def preview(config):
    return capture_preview(
        root(config), selection(config).model_dump(mode="json"), private_roots(config)
    )


def identity(config):
    # Resource controls are deliberately mutable. Identity, selection, mapped
    # audience and credential references require explicit recovery/re-enrollment.
    provider = config.provider.model_dump(
        mode="json",
        exclude={
            "state_directory",
            "max_files",
            "max_segments",
            "max_scan_seconds",
            "segment_bytes",
            "segment_records",
            "name",
        },
    )
    provider["path"] = str(config.provider.path.resolve())
    value = {
        "endpoint": config.service_url,
        "principal_id": str(config.capture.principal_id),
        "binding": binding(config),
        "provider": provider,
        "service_token": config.service_token.model_dump(mode="json"),
        "inbox_key": config.capture.inbox_key.model_dump(mode="json"),
    }
    return hashlib.sha256(canonical_capture_json(value)).hexdigest()


def read_record(config, *, required=True, matching=True):
    path, _, _ = paths(config)
    try:
        value = local_state.read(path)
    except FileNotFoundError:
        if not required:
            return None
        raise InboxError("capture_enrollment_missing") from None
    try:
        value = Enrollment.model_validate(value).model_dump(mode="json")
    except ValueError:
        raise InboxError("capture_integrity_failed") from None
    if value["id"] != str(config.capture.id):
        raise InboxError("capture_integrity_failed")
    if matching and (value["identity"] != identity(config) or value["binding"] != binding(config)):
        raise InboxError("capture_settings_changed")
    return value


def write_record(config, value, **updates):
    record = {**value, **updates, "revision": str(uuid4()), "updated_at": utc_now()}
    record = Enrollment.model_validate(record).model_dump(mode="json")
    local_state.write(paths(config)[0], record)
    return record


@contextmanager
def locked(config):
    with local_state.lock(root(config) / f"headless-lock-{config.capture.id}"):
        yield


def revision(record, expected):
    if expected != (record["revision"] if record else "not-enrolled"):
        raise InboxError("capture_settings_changed")


def connect(config):
    return Client(config.service_url, reference(config.service_token), timeout=10, retries=0)


def verify(config, client, *, existing=False, current_policy=False):
    me = client.request("GET", "/v1/me")
    if (
        me.get("tenant_id") != str(config.capture.tenant_id)
        or me.get("principal_id") != str(config.capture.principal_id)
        or me.get("administrator") is not False
    ):
        raise InboxError("capture_binding_mismatch")
    registered = next(
        (
            item
            for item in client.request("GET", "/v1/connectors")["items"]
            if item.get("id") == str(config.connector_id)
        ),
        {},
    )
    if (
        registered.get("principal_id") != str(config.capture.principal_id)
        or registered.get("provider") != "conversations"
        or registered.get("access_mode") != "published"
        or registered.get("disabled_at") is not None
    ):
        raise InboxError("capture_binding_mismatch")
    scopes = client.request(
        "GET", f"/v1/connectors/{config.connector_id}/scopes", params={"limit": 1}
    )
    if scopes.get("items") != [] or scopes.get("next_cursor"):
        raise InboxError("capture_policy_change_requires_migration")
    grant = verify_grant(SimpleNamespace(binding=binding(config)), client)
    policy = CaptureSource.model_validate(
        client.request(
            "GET",
            f"/v1/connectors/{config.connector_id}/capture-sources/{config.capture.source_id}",
        )
    )
    if (
        policy.source_id != str(config.capture.source_id)
        or policy.connector_id != str(config.connector_id)
        or policy.namespace != config.provider.scope_id
        or set(policy.members) != set(config.provider.members)
        or policy.revoked_at
    ):
        raise InboxError("capture_binding_mismatch")
    if policy.has_capture_history and not existing:
        raise InboxError("capture_policy_change_requires_migration")
    if current_policy and (
        policy.capture_policy != config.provider.capture_policy
        or policy.capture_mode != config.provider.capture_mode
    ):
        raise InboxError("capture_settings_changed")
    return grant


@contextmanager
def opened(config, record, *, initialize=False):
    key = key_bytes(reference(config.capture.inbox_key))
    if hashlib.sha256(key).hexdigest() != record["key_sha256"]:
        raise InboxError("capture_key_unavailable")
    pending = record["state"] == "pending"
    if pending and not initialize:
        raise InboxError("capture_not_initialized")
    inbox_path = paths(config)[2]
    with open_inbox(
        inbox_path,
        binding(config),
        key,
        create=pending and not (inbox_path / "inbox.sqlite3").exists(),
        limits=Limits(
            pending_bytes=config.capture.pending_limit_mib * MIB,
            database_bytes=config.capture.database_limit_mib * MIB,
            events=config.capture.history_limit_events,
        ),
    ) as inbox:
        if pending:
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
            record = write_record(config, record, state="ready", enabled=False)
        yield inbox, record, key


def enroll(config, request):
    if request.get("confirm") is not True:
        raise InboxError("capture_approval_required")
    with locked(config):
        current = read_record(config, required=False)
        revision(current, request.get("expected_revision"))
        if current and current["state"] != "pending":
            raise InboxError("capture_settings_changed")
        reviewed = preview(config)
        if reviewed["configuration_hash"] != request.get("preview_hash"):
            raise InboxError("capture_settings_changed")
        key = key_bytes(reference(config.capture.inbox_key))
        producer = folder(config)
        info = producer.stat()
        with connect(config) as client:
            verify(config, client)
        if current is None:
            with local_state.lock(root(config)):
                if (
                    len(list(islice(root(config).glob("headless-source-*.json"), MAX_DEVICES)))
                    >= MAX_DEVICES
                ):
                    raise InboxError("capture_capacity_blocked")
                if paths(config)[2].exists() or paths(config)[2].is_symlink():
                    raise InboxError("capture_enrollment_missing")
                current = write_record(
                    config,
                    {
                        "format": FORMAT,
                        "id": str(config.capture.id),
                        "identity": identity(config),
                        "binding": binding(config),
                        "state": "pending",
                        "enabled": False,
                        "key_sha256": hashlib.sha256(key).hexdigest(),
                        "folder": {
                            "path": str(producer),
                            "device": info.st_dev,
                            "inode": info.st_ino,
                        },
                    },
                )
        with opened(config, current, initialize=True):
            pass
    return status(config)


def status(config):
    record = read_record(config, required=False, matching=False)
    report = {
        "format": FORMAT,
        "id": str(config.capture.id),
        "connector_id": str(config.connector_id),
        "state": record["state"] if record else "not-enrolled",
        "revision": record["revision"] if record else "not-enrolled",
        "enabled": bool(record and record["enabled"]),
        "configuration_matches": bool(record and record["identity"] == identity(config)),
        "inbox_present": (paths(config)[2] / "inbox.sqlite3").is_file(),
        "memory_limit_mib": config.capture.memory_limit_mib,
        "pending_limit_mib": config.capture.pending_limit_mib,
        "history_limit_events": config.capture.history_limit_events,
        "database_limit_mib": config.capture.database_limit_mib,
        "activity": None,
        "recovery": record.get("recovery") if record else None,
    }
    try:
        activity = local_state.read(paths(config)[1])
    except FileNotFoundError:
        return report
    try:
        activity = Activity.model_validate(activity).model_dump(mode="json", exclude_none=True)
    except ValueError:
        raise InboxError("capture_integrity_failed") from None
    if activity["id"] != str(config.capture.id):
        raise InboxError("capture_integrity_failed")
    if activity.get("state") == "scanning":
        try:
            running = process_identity.matches(
                activity.get("process"), psutil.Process(activity["pid"])
            )
        except (psutil.Error, OSError, ValueError, KeyError):
            running = False
        activity = {**activity, "state": "scanning" if running else "interrupted"}
    activity.pop("process")
    report["activity"] = activity
    return report


def set_enabled(config, request, enabled):
    with locked(config):
        record = read_record(config)
        revision(record, request.get("expected_revision"))
        if enabled:
            if record["state"] not in {"ready", "revoked"} or request.get("confirm") is not True:
                raise InboxError("capture_approval_required")
            with opened(config, record), connect(config) as client:
                verify(config, client, existing=True)
        write_record(config, record, enabled=enabled, **({"state": "ready"} if enabled else {}))
    return status(config)


def collect(config, record, inbox):
    try:
        producer = folder(config)
        info = producer.stat()
        if record["folder"] != {"path": str(producer), "device": info.st_dev, "inode": info.st_ino}:
            raise InboxError("capture_source_changed")
    except (OSError, ValueError, local_state.LocalSetupError):
        return {"completed": False, "scopes": [], "errors": ["capture_source_unavailable"]}
    with local_state.lock(root(config) / "inbox-budget"):
        usage, own = device_usage(root(config), inbox), inbox.status()
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
        return capture_available(inbox, ConversationProvider(config.provider))


def scan(config, *, client_factory=None):
    with locked(config):
        record = read_record(config)
        if not record["enabled"] or record["state"] != "ready":
            return {
                "completed": False,
                "scopes": [],
                "paused": True,
                "reason_code": "capture_paused",
                "connector_id": str(config.connector_id),
                "provider": "conversations",
            }
        with opened(config, record) as (inbox, record, _):
            activity = {
                "format": FORMAT,
                "id": str(config.capture.id),
                "state": "scanning",
                "pid": os.getpid(),
                "process": process_identity.capture(psutil.Process()),
                "started_at": utc_now(),
            }
            local_state.write(paths(config)[1], activity)

            def usage():
                with local_state.lock(root(config) / "inbox-budget"):
                    return device_usage(root(config), inbox)

            try:
                report = cycle(
                    inbox,
                    collect=lambda: collect(config, record, inbox),
                    client=client_factory or (lambda: connect(config)),
                    revoked=lambda: write_record(config, record, state="revoked", enabled=False),
                    usage=usage,
                )
            except (InboxError, local_state.LocalSetupError, ValueError, OSError) as error:
                reason = getattr(error, "code", "capture_storage_unavailable")
                if reason not in CAPTURE_REASONS:
                    reason = "capture_storage_unavailable"
                local_state.write(
                    paths(config)[1],
                    {
                        **activity,
                        "state": "failed",
                        "finished_at": utc_now(),
                        "reason_code": reason,
                    },
                )
                raise
            local_state.write(
                paths(config)[1],
                {
                    **activity,
                    "state": "finished",
                    "finished_at": utc_now(),
                    "report": {
                        **report,
                        "capture": {
                            key: value
                            for key, value in report["capture"].items()
                            if key != "newly_stored_events"
                        },
                    },
                },
            )
            return {
                **report,
                "connector_id": str(config.connector_id),
                "provider": "conversations",
                "scopes": [],
            }
