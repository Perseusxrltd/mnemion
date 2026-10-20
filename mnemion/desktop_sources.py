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
from .connectors.config import ConnectorConfig
from .connectors.providers import ProviderError
from .connectors.runner import sync
from .sdk import Client, MnemionError
from .service.models import Command

MAX_SOURCES = 16
MAX_REQUEST = 256 * 1024


class Source(Command):
    id: UUID
    endpoint: str = Field(max_length=2048)
    tenant_id: UUID
    connector_id: UUID
    principal_id: UUID
    name: str = Field(min_length=1, max_length=200)
    provider: Literal["filesystem", "conversations"]
    path: str = Field(min_length=1, max_length=4096)
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
        # Share the established HTTPS/loopback contract, including path prefixes.
        config = self.connector(Path("unused-capture-state"))
        self.endpoint = config.service_url
        if not Path(self.path).is_absolute() or "\x00" in self.path:
            raise ValueError("Choose an absolute source folder")
        return self

    def connector(self, capture: Path) -> ConnectorConfig:
        provider = {
            "type": self.provider,
            "path": self.path,
            "scope_id": "selected-source",
            "name": self.name,
            "members": self.members,
            "publish_to_mapped_members": True,
            "max_files": self.max_files,
        }
        if self.provider == "conversations":
            provider.update(state_directory=str(capture), max_scan_seconds=60)
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

    @field_validator("sealed_key")
    @classmethod
    def encrypted_bytes(cls, value):
        if not base64.b64decode(value, validate=True):
            raise ValueError("Use an OS-protected source key")
        return value


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
    candidate = SourceState(revision=str(uuid4()), sources=sources)
    local_state.directory(root)
    with local_state.lock(root):
        if load(root).revision != expected:
            raise local_state.LocalSetupError(
                "source_settings_changed", "Source settings changed. Refresh before retrying."
            )
        local_state.write(root / "sources.json", candidate.model_dump(mode="json"))
    return candidate.model_dump(mode="json")


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
        or connector.get("access_mode") != "published"
        or connector.get("disabled_at") is not None
    ):
        raise local_state.LocalSetupError(
            "source_connection_unavailable", "Enable this connection and check its application."
        )
    return source


def perform(root: Path, request: dict, private_roots=()) -> dict:
    operation = request.get("operation")
    fields = {
        "load": {"operation"},
        "store": {"operation", "expected_revision", "sources"},
        "verify": {"operation", "source", "credential"},
        "scan": {"operation", "source", "credential"},
    }
    if operation not in fields or set(request) != fields[operation]:
        raise ValueError("Choose a supported private source operation")
    if operation == "load":
        return load(root).model_dump(mode="json")
    if operation == "store":
        return store(root, request["expected_revision"], request["sources"])
    source = Source.model_validate(request["source"])
    credential = request["credential"]
    if (
        not isinstance(credential, str)
        or not 16 <= len(credential) <= 8192
        or any(not 33 <= ord(c) <= 126 for c in credential)
    ):
        raise ValueError("Supply the dedicated source key through the private pipe")
    local_state.directory(root)
    with Client(source.endpoint, credential, timeout=20, retries=0) as client:
        verify(source, root, client, private_roots)
        if operation == "verify":
            return source.model_dump(mode="json")
        if not source.enabled:
            raise ValueError("Resume the source before scanning")
        capture = root / ("capture-" + str(source.id))
        if source.provider == "conversations":
            local_state.directory(capture)
        report = sync(source.connector(capture), client=client)
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
        httpx.HTTPError,
    ) as exc:
        stopped.set()
        code = exc.code if isinstance(exc, local_state.LocalSetupError) else "source_unavailable"
        emit({"event": "result", "ok": False, "error": code})
        return 2


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    arguments(parser)
    raise SystemExit(dispatch(parser.parse_args()))
