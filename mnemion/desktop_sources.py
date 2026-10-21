"""Private desktop source storage and bounded scans; never an HTTP endpoint.

Studio owns scheduling and encrypts each dedicated application key with the OS.
This helper receives plaintext credentials only through its process pipe. It
reuses the connector's inventory, permission and conversation checkpoint rules.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import sys
import threading
from typing import Literal
from uuid import UUID, uuid4

import httpx
from pydantic import Field, ValidationError, field_validator, model_validator

from . import local_state
from .capture_policy import CapturePolicy
from .connectors.config import ConnectorConfig
from .connectors.providers import ProviderError
from .connectors.runner import sync
from .desktop_capture import Custody
from .connectors.conversation_inbox import InboxError
from .desktop_provider_credentials import credential as provider_credential
from .sdk import Client, MnemionError
from .service.models import Command

MAX_SOURCES = 16
MAX_REQUEST = 256 * 1024


class SlackSelection(Command):
    team_id: str = Field(pattern=r"^[TE][A-Z0-9]+$", max_length=128)
    channels: list[str] = Field(min_length=1, max_length=128)
    include_threads: bool = Field(default=True, strict=True)

    @field_validator("channels")
    @classmethod
    def identifiers(cls, value):
        import re

        if len(set(value)) != len(value) or any(
            not re.fullmatch(r"[CGD][A-Z0-9]{1,127}", item) for item in value
        ):
            raise ValueError("Choose distinct Slack channel IDs")
        return value


class DriveSelection(Command):
    folder_ids: list[str] = Field(default_factory=list, max_length=128)
    file_ids: list[str] = Field(default_factory=list, max_length=128)
    recursive: bool = Field(default=True, strict=True)

    @field_validator("folder_ids", "file_ids")
    @classmethod
    def identifiers(cls, value):
        import re

        if len(set(value)) != len(value) or any(
            not re.fullmatch(r"[A-Za-z0-9_-]{1,300}", item) for item in value
        ):
            raise ValueError("Choose distinct Drive folder or file IDs")
        return value


class Source(Command):
    id: UUID
    endpoint: str = Field(max_length=2048)
    tenant_id: UUID
    connector_id: UUID
    principal_id: UUID
    name: str = Field(min_length=1, max_length=200)
    provider: Literal["filesystem", "conversations", "slack", "gdrive"]
    capture_mode: Literal["complete", "messages"] | None = None
    capture_policy: CapturePolicy | None = None
    custody: Custody | None = None
    scope_id: str | None = Field(default=None, min_length=1, max_length=400)
    path: str | None = Field(default=None, min_length=1, max_length=4096)
    slack: SlackSelection | None = None
    gdrive: DriveSelection | None = None
    members: list[str] = Field(max_length=128)
    publish_to_mapped_members: Literal[True]
    poll_seconds: int = Field(default=300, ge=30, le=3600, strict=True)
    memory_limit_mib: int = Field(default=256, ge=128, le=2048, strict=True)
    max_files: int = Field(default=10000, ge=1, le=100000, strict=True)
    enabled: bool = Field(default=True, strict=True)

    @field_validator("members")
    @classmethod
    def audience(cls, value):
        if len(set(value)) != len(value) or any(
            not item or len(item) > 512 or any(ord(c) < 32 for c in item) for item in value
        ):
            raise ValueError("Choose distinct mapped identities")
        return value

    @model_validator(mode="after")
    def address_and_path(self):
        if self.capture_policy is not None:
            if (
                self.provider != "conversations"
                or self.capture_mode != self.capture_policy.capture_mode
                or bool(self.custody) != (self.capture_policy.retention == "until_deleted")
            ):
                raise ValueError("Match the source's approved capture policy and retention")
        if self.provider != "conversations" and self.capture_mode is not None:
            raise ValueError("Capture mode applies only to live conversation sources")
        if self.provider != "conversations" and self.custody is not None:
            raise ValueError("Retained capture applies only to conversation sources")
        if self.provider not in {"filesystem", "conversations"} and self.scope_id is not None:
            raise ValueError(
                "A folder identity applies only to filesystem and conversation sources"
            )
        # Share the established HTTPS/loopback contract, including path prefixes.
        config = self.connector(Path("unused-capture-state"))
        self.endpoint = config.service_url
        if self.provider in {"filesystem", "conversations"}:
            if (
                not self.path
                or not Path(self.path).is_absolute()
                or "\x00" in self.path
                or self.slack is not None
                or self.gdrive is not None
            ):
                raise ValueError("Choose an absolute source folder without cloud settings")
        elif (
            self.path is not None
            or (self.provider == "slack") != (self.slack is not None)
            or (self.provider == "gdrive") != (self.gdrive is not None)
        ):
            raise ValueError("Choose the selected cloud provider's settings")
        return self

    def connector(self, capture: Path) -> ConnectorConfig:
        if self.provider in {"slack", "gdrive"}:
            selection = self.slack if self.provider == "slack" else self.gdrive
            provider = {
                "type": self.provider,
                **(selection.model_dump() if selection else {}),
                "token": {"env": "MNEMION_DESKTOP_PROVIDER_UNUSED"},
            }
            if self.provider == "slack":
                provider.update(page_size=15, max_messages=self.max_files)
            else:
                provider.update(
                    max_files=self.max_files,
                    max_file_bytes=min(20_000_000, self.memory_limit_mib * 65536),
                )
        else:
            provider = {
                "type": self.provider,
                "path": self.path,
                "scope_id": self.scope_id or "selected-source",
                "name": self.name,
                "members": self.members,
                "publish_to_mapped_members": True,
                "max_files": self.max_files,
            }
            if self.provider == "conversations":
                provider.update(
                    state_directory=str(capture),
                    max_scan_seconds=60,
                    capture_mode=self.capture_mode or "complete",
                    capture_policy=self.capture_policy,
                )
            else:
                provider["max_file_bytes"] = min(20_000_000, self.memory_limit_mib * 65536)
        return ConnectorConfig.model_validate(
            {
                "version": 1,
                "service_url": self.endpoint,
                "service_token": {"env": "MNEMION_DESKTOP_SOURCE_UNUSED"},
                "connector_id": self.connector_id,
                "provider": provider,
                "poll_seconds": self.poll_seconds,
                # Access expires after missed scans; a paused PC is not proof of
                # current provider access. Long intervals get an adequate lease.
                "access_lease_seconds": max(900, self.poll_seconds * 3),
            }
        )


class SavedSource(Source):
    sealed_key: str = Field(min_length=16, max_length=16384)
    sealed_provider: str | None = Field(default=None, min_length=16, max_length=32768)
    sealed_inbox_key: str | None = Field(default=None, min_length=16, max_length=16384)
    # Private configuration identity. Never a public setting or caller authority.
    # Old settings remain readable; enabled-only changes retain their old epoch.
    status_epoch: UUID | None = None

    @field_validator("sealed_key", "sealed_provider", "sealed_inbox_key")
    @classmethod
    def encrypted_bytes(cls, value):
        if value is not None and not base64.b64decode(value, validate=True):
            raise ValueError("Use an OS-protected source key")
        return value

    @model_validator(mode="after")
    def cloud_credential(self):
        if (self.provider in {"slack", "gdrive"}) != bool(self.sealed_provider):
            raise ValueError("Cloud credentials must use separate OS-protected storage")
        if bool(self.custody) != bool(self.sealed_inbox_key):
            raise ValueError("Retained capture needs a separate OS-protected inbox key")
        return self


class SourceState(Command):
    format: Literal[1] = 1
    revision: str = Field(pattern=r"^(not-configured|[a-f0-9-]{36})$")
    sources: list[SavedSource] = Field(max_length=MAX_SOURCES)

    @model_validator(mode="after")
    def distinct(self):
        if len({item.id for item in self.sources}) != len(self.sources) or len(
            {(item.endpoint, item.connector_id) for item in self.sources}
        ) != len(self.sources):
            raise ValueError("This connection already runs on this computer")
        return self


def load(root: Path) -> SourceState:
    local_state.directory(root)
    try:
        value = local_state.read(root / "sources.json")
    except FileNotFoundError:
        value = {"format": 1, "revision": "not-configured", "sources": []}
    return SourceState.model_validate(value)


def store(root: Path, expected: str, sources: list) -> dict:
    from .desktop_source_status import settings
    from .desktop_capture import enrollment, register

    candidate = SourceState(revision=str(uuid4()), sources=sources)
    local_state.directory(root)
    with local_state.lock(root):
        current = load(root)
        if current.revision != expected:
            raise local_state.LocalSetupError(
                "source_settings_changed", "Source settings changed. Refresh before retrying."
            )
        previous = {source.id: source for source in current.sources}
        remaining = {source.id for source in candidate.sources}
        for source in current.sources:
            if (
                source.custody
                and source.id not in remaining
                and enrollment(root, source)["state"] != "discarded"
            ):
                raise InboxError("capture_retire_required")
        for source in candidate.sources:
            old = previous.get(source.id)
            if old and old.custody and not source.custody:
                raise InboxError("capture_policy_change_requires_migration")
            if source.custody:
                register(root, source, old)
            source.status_epoch = (
                old.status_epoch
                if old is not None and settings(old) == settings(source)
                else uuid4()
            )
        local_state.write(
            root / "sources.json", candidate.model_dump(mode="json", exclude_none=True)
        )
    return candidate.model_dump(mode="json", exclude_none=True)


def source_folder(source: Source, root: Path, private_roots=()) -> Path:
    path = Path(source.path)
    # A network folder is allowed when mounted by the user. Do not follow a
    # replaced folder symlink/junction or ingest the app's own private records.
    if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
        raise ValueError("Choose an ordinary source folder")
    path = path.resolve(strict=True)
    private = [root.resolve(), *(Path(item).resolve() for item in private_roots)]
    if not path.is_dir() or any(
        path == item or path in item.parents or item in path.parents for item in private
    ):
        raise ValueError("Keep the source separate from private app state")
    return path


def verify(source: Source, root: Path, client: Client, private_roots=()) -> Source:
    if source.provider in {"filesystem", "conversations"}:
        source.path = str(source_folder(source, root, private_roots))
    me = client.request("GET", "/v1/me")
    if (
        me.get("tenant_id") != str(source.tenant_id)
        or me.get("principal_id") != str(source.principal_id)
        or me.get("administrator") is not False
    ):
        raise local_state.LocalSetupError(
            "source_identity_mismatch",
            "Use this connection's dedicated application key in the expected workspace.",
        )
    items = client.request("GET", "/v1/connectors").get("items", [])
    connector = next((item for item in items if item.get("id") == str(source.connector_id)), {})
    if (
        connector.get("principal_id") != str(source.principal_id)
        or connector.get("provider") != source.provider
        or connector.get("access_mode")
        != ("provider" if source.provider in {"slack", "gdrive"} else "published")
        or connector.get("disabled_at") is not None
    ):
        raise local_state.LocalSetupError(
            "source_connection_unavailable", "Enable this connection and check its application."
        )
    if source.provider == "filesystem":
        # A replacement device must retain the established source space. Using
        # the desktop default for an older CLI source would create a second
        # scope and suspend the original as absent from the provider catalog.
        page = client.request(
            "GET", f"/v1/connectors/{source.connector_id}/scopes", params={"limit": 2}
        )
        scopes = page.get("items")
        if not isinstance(scopes, list) or len(scopes) > 1 or page.get("next_cursor"):
            raise local_state.LocalSetupError(
                "source_scope_ambiguous",
                "This connection has several recorded folders. Keep its original adapter configuration; Studio cannot choose one safely.",
            )
        namespace = source.scope_id or "selected-source"
        if scopes:
            scope = scopes[0]
            external = scope.get("external_id") if isinstance(scope, dict) else None
            if (
                not isinstance(external, str)
                or not external.startswith("filesystem:")
                or not 1 <= len(external.removeprefix("filesystem:")) <= 400
                or scope.get("connector_id") != str(source.connector_id)
            ):
                raise local_state.LocalSetupError(
                    "source_scope_ambiguous", "The existing folder identity could not be verified."
                )
            namespace = external.removeprefix("filesystem:")
            if source.scope_id is not None and source.scope_id != namespace:
                raise local_state.LocalSetupError(
                    "source_scope_mismatch",
                    "The existing folder identity has changed. Retain its original connection settings before scanning.",
                )
        # Ordinary desktop sources keep their previous saved-file shape. Only
        # a non-default namespace needs the new field on a replacement device.
        source.scope_id = None if namespace == "selected-source" else namespace
    elif source.provider == "conversations":
        from .desktop_source_identity import verify_conversation_identity

        verify_conversation_identity(source, root, client, load(root).sources)
        if source.scope_id == "selected-source":
            source.scope_id = None
        if source.custody:
            from .desktop_capture import verify as verify_capture

            verify_capture(source, root, client)
    return source


def cloud_adapter(source: Source, value: str):
    # The public connector configuration contains a placeholder reference only.
    # Its token reader is replaced in memory, without files or environment changes.
    try:
        token = provider_credential(source.provider, value)
    except ValueError:
        raise local_state.LocalSetupError(
            "source_provider_credentials",
            "Check the selected provider's private credential.",
        ) from None
    config = source.connector(Path("unused-capture-state")).provider
    if source.provider == "slack":
        from .connectors.slack import SlackProvider

        adapter = SlackProvider(config)
    else:
        from .connectors.gdrive import DriveProvider

        adapter = DriveProvider(config)
    adapter.http.token = token
    return adapter


def verify_cloud(adapter, provider: str):
    if provider == "slack":
        adapter.scopes()  # auth.test validates the exact selected Slack workspace.
    else:
        result = adapter.http.get("about", {"fields": "user(permissionId)"})
        user = result.get("user")
        if (
            not isinstance(user, dict)
            or not isinstance(user.get("permissionId"), str)
            or not user["permissionId"]
        ):
            raise ProviderError("invalid_drive_identity")
    # The first scan checks each actual channel/file membership before publishing.


def perform(root: Path, request: dict, private_roots=()) -> dict:
    operation = request.get("operation")
    if operation in {
        "capture_restore",
        "capture_restore_list",
        "capture_restore_load",
        "capture_restore_finish",
        "capture_restore_discard",
    }:
        from .desktop_capture_restore import perform as capture_restore

        return capture_restore(root, request, private_roots)
    if operation in {"capture_export", "capture_inspect"}:
        from .desktop_capture_backup import perform as capture_backup

        return capture_backup(root, request)
    if operation == "preview":
        from .desktop_capture_preview import preview

        if set(request) != {"operation", "selection"}:
            raise ValueError("Choose a bounded conversation preview")
        return preview(root, request["selection"], private_roots)
    if operation == "capture_retire":
        from .desktop_capture import retire

        return retire(root, request)
    if operation in {"status", "status_begin", "status_finish", "status_repair"}:
        from .desktop_source_status import perform as status_operation

        return status_operation(root, request)
    fields = {
        "load": {"operation"},
        "store": {"operation", "expected_revision", "sources"},
        "verify": {"operation", "source", "credential"},
        "scan": {"operation", "source", "credential"},
    }
    allowed = (
        fields.get(operation, set())
        | ({"provider_credential"} if operation in {"verify", "scan"} else set())
        | ({"inbox_key"} if operation == "scan" else set())
        | ({"preview_hash"} if operation == "verify" else set())
    )
    if operation not in fields or not fields[operation] <= set(request) <= allowed:
        raise ValueError("Choose a supported private source operation")
    if operation == "load":
        return load(root).model_dump(mode="json", exclude_none=True)
    if operation == "store":
        return store(root, request["expected_revision"], request["sources"])
    source = Source.model_validate(request["source"])
    if operation == "verify" and source.capture_policy is not None:
        from .desktop_capture_preview import normalize, selection_for

        selection = normalize(root, selection_for(source), private_roots)
        if request.get("preview_hash") != selection.fingerprint:
            raise local_state.LocalSetupError(
                "source_preview_required", "Preview the current capture settings before saving."
            )
    credential = request["credential"]
    if (
        not isinstance(credential, str)
        or not 16 <= len(credential) <= 8192
        or any(not 33 <= ord(c) <= 126 for c in credential)
    ):
        raise ValueError("Supply the dedicated source key through the private pipe")
    local_state.directory(root)
    cloud = source.provider in {"slack", "gdrive"}
    if cloud != ("provider_credential" in request):
        raise ValueError("Supply separate credentials only for cloud sources")
    if operation == "scan" and source.custody:
        from .desktop_capture import scan as capture_scan

        return capture_scan(root, source, request.get("inbox_key"), credential, private_roots)
    if "inbox_key" in request:
        raise ValueError("Only retained capture accepts a separate inbox key")
    with Client(source.endpoint, credential, timeout=20, retries=0) as client:
        verify(source, root, client, private_roots)
        adapter = cloud_adapter(source, request["provider_credential"]) if cloud else None
        try:
            if operation == "verify":
                if adapter:
                    verify_cloud(adapter, source.provider)
                return source.model_dump(mode="json", exclude_none=True)
            if not source.enabled:
                raise ValueError("Resume the source before scanning")
            capture = root / ("capture-" + str(source.id))
            if source.provider == "conversations":
                local_state.directory(capture)
            report = sync(source.connector(capture), client=client, adapter=adapter)
        finally:
            if adapter:
                adapter.close()
        # Only bounded operational counters cross the app bridge, never source
        # content, raw diagnostics, provider IDs or authentication responses.
        return {
            key: report[key]
            for key in (
                "completed",
                "timestamp",
                "duration_seconds",
                "changed",
                "removed",
                "unchanged",
                "conflicts",
                "remote_sync_available",
            )
        }


def arguments(parser):
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--private-root", action="append", default=[], type=Path)


def dispatch(args) -> int:
    output_lock = threading.Lock()
    stopped = threading.Event()

    def emit(value):
        with output_lock:
            if value.get("event") == "resources" and stopped.is_set():
                return
            if value.get("event") == "result":
                stopped.set()
            print(json.dumps(value, separators=(",", ":")), flush=True)

    try:
        body = sys.stdin.buffer.read(MAX_REQUEST + 1)
        if len(body) > MAX_REQUEST:
            raise ValueError("Source request is too large")
        request = json.loads(body)
        if not isinstance(request, dict):
            raise ValueError("Invalid source request")
        if request.get("operation") == "scan":
            import psutil

            source = Source.model_validate(request.get("source"))
            process = psutil.Process()
            parent = process.parent()

            def watch():
                while not stopped.wait(2):
                    if parent is None or not parent.is_running():
                        os._exit(2)
                    rss = process.memory_info().rss
                    if rss > source.memory_limit_mib * 1024 * 1024:
                        emit({"event": "result", "ok": False, "error": "source_memory_limit"})
                        os._exit(2)
                    emit({"event": "resources", "rss_bytes": rss})

            threading.Thread(target=watch, daemon=True).start()
        result = perform(args.root, request, args.private_root)
        stopped.set()
        emit({"event": "result", "ok": True, "result": result})
        return 0
    except (
        OSError,
        ValueError,
        ValidationError,
        local_state.LocalSetupError,
        MnemionError,
        ProviderError,
        InboxError,
        httpx.HTTPError,
    ) as exc:
        stopped.set()
        code = (
            exc.code
            if isinstance(exc, (local_state.LocalSetupError, InboxError))
            else "source_unavailable"
        )
        if isinstance(exc, ProviderError) and getattr(exc, "code", None) in {
            "provider_access_lost",
            "slack_access_lost",
            "slack_workspace_mismatch",
            "provider_rate_limited",
            "provider_unavailable",
            "invalid_drive_identity",
        }:
            code = exc.code
        emit({"event": "result", "ok": False, "error": code})
        return 2


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    arguments(parser)
    raise SystemExit(dispatch(parser.parse_args()))
