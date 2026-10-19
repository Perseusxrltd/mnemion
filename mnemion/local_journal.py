"""Journal destination enrollment for the owning OS account.

Host paths are derived locally. SSH credential references stay with the owning
OS account; key bytes never enter the registration or service API.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import local_state as state
from .journal.config import Configuration, Destination, SshAuthentication
from .journal.format import JournalError
from .service.oauth import _json_object


class JournalDestination(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    space_id: UUID
    label: str = Field(min_length=1, max_length=200)
    remote: str = Field(min_length=1, max_length=2048)
    branch: str = Field(default="main", min_length=1, max_length=200)
    prefix: str = Field(default="memory/native-buffer", min_length=1, max_length=200)
    personal_data_scan: bool = True
    ssh: SshAuthentication | None = None

    @field_validator("label")
    @classmethod
    def visible_label(cls, value):
        if not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Use a visible destination label")
        return value

    @field_validator("remote")
    @classmethod
    def git_remote(cls, value):
        return Destination.git_remote(value)

    @model_validator(mode="after")
    def authentication(self):
        if (urlsplit(self.remote).scheme == "ssh") != (self.ssh is not None):
            raise ValueError("SSH requires a dedicated deploy key and pinned known-hosts file")
        return self

    @field_validator("branch")
    @classmethod
    def git_branch(cls, value):
        return Destination.ref(value)

    @field_validator("prefix")
    @classmethod
    def journal_prefix(cls, value):
        return Destination.portable_prefix(value)

    def destination(self, root: Path, tenant_id: str) -> Destination:
        return Destination(
            id="space-" + str(self.space_id),
            tenant_id=UUID(tenant_id),
            state_directory=root / ("journal-" + str(self.space_id)),
            **self.model_dump(),
        )


class JournalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    format: Literal[1] = 1
    workspace_id: UUID
    revision: UUID
    updated_at: str
    destinations: list[JournalDestination] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def unique(self):
        for values in (
            [d.space_id for d in self.destinations],
            [(d.remote, d.branch, d.prefix.casefold()) for d in self.destinations],
        ):
            if len(values) != len(set(values)):
                raise ValueError("Each space needs its own repository folder")
        return self


class JournalChange(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    workspace_id: UUID
    expected_revision: str = Field(pattern=r"^(?:not-configured|[a-f0-9-]{36}|[a-f0-9]{64})$")
    action: Literal["save", "remove", "reset"]
    destination: JournalDestination | None = None
    space_id: UUID | None = None

    @model_validator(mode="after")
    def operation(self):
        if (self.action == "save") != (self.destination is not None) or (
            self.action == "remove"
        ) != (self.space_id is not None):
            raise ValueError("Choose one destination operation")
        return self


def _record(root: Path, workspace_id: str):
    try:
        content = state.read_bytes(root / "journal-access.json")
    except FileNotFoundError:
        return None, None, "not-configured"
    try:
        if len(content) > 128 * 1024:
            raise ValueError("Journal registrations exceed their limit")
        json.loads(content, object_pairs_hook=_json_object)
        saved = JournalRecord.model_validate_json(content)
        if str(saved.workspace_id) != workspace_id:
            raise ValueError("Different workspace")
        return saved, content, str(saved.revision)
    except (ValueError, RecursionError):
        return None, content, hashlib.sha256(content).hexdigest()


def inspection(root: Path, workspace_id: str):
    view = {
        "revision": "unreadable",
        "repairable": False,
        "state": "configuration_error",
        "git_found": shutil.which("git") is not None,
        "destinations": [],
        "message": "Journal registrations could not be read safely. Memory access is retained.",
    }
    try:
        saved, content, revision = _record(root, workspace_id)
    except (OSError, state.LocalSetupError):
        return view
    view.update(revision=revision, repairable=True)
    if saved is None and content is None and os.environ.get("MNEMION_WRITEBACK_CONFIG"):
        view.update(
            state="external",
            repairable=False,
            message="This host uses an existing journal environment file. Maintain it through the host operator before adopting app-managed registrations.",
        )
    elif saved is None and content is not None:
        view["message"] = (
            "Reset the damaged registrations to repair these settings. The original private file and journal history will be retained."
        )
    else:
        choices = saved.destinations if saved else []
        view.update(
            state="configured" if choices else "not_configured",
            destinations=[d.model_dump(mode="json", exclude_none=True) for d in choices],
            message="Repository choices are registered on this host. Each space still requires separate approval before publication."
            if choices
            else "Register a repository, then approve publication in that space's Git journal.",
        )
    return view


def configure(root: Path, change: JournalChange):
    from .local_workspace import configuration

    with state.lock(root):
        workspace = configuration(root)
        if str(change.workspace_id) != workspace["workspace_id"]:
            raise state.LocalSetupError("settings_changed", "Choose the current local workspace.")
        saved, content, revision = _record(root, workspace["workspace_id"])
        if revision != change.expected_revision:
            raise state.LocalSetupError(
                "settings_changed", "Journal registrations changed. Refresh and review them again."
            )
        if saved is None and content is None and os.environ.get("MNEMION_WRITEBACK_CONFIG"):
            raise state.LocalSetupError(
                "journal_external_configuration",
                "This host already manages its journal registry through the environment. Review that configuration with its operator.",
            )
        damaged = saved is None and content is not None
        if damaged != (change.action == "reset"):
            raise state.LocalSetupError(
                "journal_repair_required" if damaged else "settings_changed",
                "Reset damaged registrations before saving, or refresh if their state changed.",
            )
        choices = {d.space_id: d for d in saved.destinations} if saved else {}
        if change.action == "save":
            if change.destination.ssh:
                from .journal.ssh import credential_bytes

                try:
                    credential_bytes(change.destination.ssh)
                except JournalError:
                    raise state.LocalSetupError(
                        "journal_ssh_credentials_unavailable",
                        "Select existing SSH key and known-hosts files readable only by this OS account, without links. Verify the repository host's keys independently.",
                    ) from None
            choices[change.destination.space_id] = change.destination
        elif change.action == "remove":
            if change.space_id not in choices:
                raise state.LocalSetupError(
                    "settings_changed", "This space is no longer registered. Refresh its settings."
                )
            del choices[change.space_id]
        updated = JournalRecord(
            workspace_id=change.workspace_id,
            revision=uuid4(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            destinations=list(choices.values()),
        )
        value = updated.model_dump(mode="json", exclude_none=True)
        if len(json.dumps(value).encode()) > 128 * 1024:
            raise state.LocalSetupError(
                "journal_capacity", "Journal registrations exceed the 128 KiB limit."
            )
        path = root / "journal-access.json"
        if damaged:
            state.replace_damaged(path, value, expected=content, kind="journal")
        else:
            state.write(path, value, replace=content is not None)
        return inspection(root, str(change.workspace_id))


def configuration(root: Path, workspace_id: str, *, tenant_id: str) -> Configuration:
    try:
        saved, content, _ = _record(root, workspace_id)
    except (OSError, state.LocalSetupError):
        return Configuration()
    if saved is None and content is None:
        return Configuration.from_environment()
    return Configuration(
        destinations=[d.destination(root, tenant_id) for d in saved.destinations] if saved else []
    )
