"""Private host key setup, separate from workspace users and memory credentials."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from . import local_state as state
from .service.oauth import _json_object
from .service.vault_crypto import VaultCipher, VaultSettings, decode_key


class VaultRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    format: Literal[1] = 1
    workspace_id: UUID
    revision: UUID
    updated_at: str
    key: SecretStr
    enabled: bool
    mcp_enabled: bool
    mcp_metadata_enabled: bool = False

    @field_validator("key")
    @classmethod
    def checked_key(cls, value):
        decode_key(value.get_secret_value())
        return value


class VaultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    workspace_id: UUID
    expected_revision: str = Field(pattern=r"^(?:not-configured|[a-f0-9-]{36}|[a-f0-9]{64})$")


class VaultChange(VaultRequest):
    action: Literal["configure", "restore"] = "configure"
    enabled: bool
    mcp_enabled: bool = False
    mcp_metadata_enabled: bool | None = None
    recovery_key: SecretStr | None = None
    key_saved: bool = False

    @field_validator("recovery_key")
    @classmethod
    def checked_key(cls, value):
        if value is not None:
            decode_key(value.get_secret_value())
        return value


def _record(root: Path, workspace_id: str):
    try:
        content = state.read_bytes(root / "vault-access.json")
    except FileNotFoundError:
        return None, None, "not-configured"
    try:
        if len(content) > 4096:
            raise ValueError("Vault settings exceed their limit")
        json.loads(content, object_pairs_hook=_json_object)
        saved = VaultRecord.model_validate_json(content)
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
        "enabled": False,
        "mcp_enabled": False,
        "mcp_metadata_enabled": False,
        "key_id": None,
        "message": "Vault settings could not be read safely. Memory access is retained.",
    }
    try:
        saved, content, revision = _record(root, workspace_id)
    except (OSError, state.LocalSetupError):
        return view
    view.update(revision=revision, repairable=True)
    if saved is None and content is None and os.environ.get("MNEMION_VAULT_KEY"):
        view.update(
            state="external",
            repairable=False,
            message="The host environment manages this vault key. Maintain that configuration through its host operator.",
        )
    elif saved is None and content is not None:
        view["message"] = (
            "Restore the original vault key to repair these settings. The damaged private record will be retained."
        )
    elif saved is None:
        view.update(
            state="not_configured",
            message="Create an encrypted credentials vault or restore its existing key.",
        )
    else:
        view.update(
            state="configured" if saved.enabled else "disabled",
            enabled=saved.enabled,
            mcp_enabled=saved.mcp_enabled,
            mcp_metadata_enabled=saved.mcp_metadata_enabled,
            key_id=VaultCipher(saved.key.get_secret_value()).key_id,
            message="The vault key is saved on this host. Credential access still requires explicit grants."
            if saved.enabled
            else "Vault access is disabled; the private key and encrypted values are retained.",
        )
    return view


def _current(root: Path, request: VaultRequest):
    from .local_workspace import configuration

    workspace = configuration(root)
    if str(request.workspace_id) != workspace["workspace_id"]:
        raise state.LocalSetupError("settings_changed", "Choose the current local workspace.")
    saved, content, revision = _record(root, workspace["workspace_id"])
    if revision != request.expected_revision:
        raise state.LocalSetupError(
            "settings_changed", "Vault settings changed. Refresh and review them again."
        )
    if saved is None and content is None and os.environ.get("MNEMION_VAULT_KEY"):
        raise state.LocalSetupError(
            "vault_external_configuration",
            "This host already manages its vault through the environment. Review that configuration with its operator.",
        )
    return saved, content


def configure(root: Path, change: VaultChange):
    with state.lock(root):
        saved, content = _current(root, change)
        damaged = saved is None and content is not None
        if damaged and change.action != "restore":
            raise state.LocalSetupError(
                "vault_repair_required", "Restore the original encryption key to repair this vault."
            )
        key = change.recovery_key or (saved.key if saved else None)
        if key is None or (
            (saved is None or change.action == "restore")
            and not (change.recovery_key and change.key_saved)
        ):
            raise state.LocalSetupError(
                "vault_key_required",
                "Supply a vault key and confirm its independent recovery copy before saving.",
            )
        if saved and key != saved.key and change.action != "restore":
            raise state.LocalSetupError(
                "vault_key_changed",
                "Use Restore key to replace the host key from a known backup. Changing a key does not re-encrypt existing credentials.",
            )
        updated = VaultRecord(
            workspace_id=change.workspace_id,
            revision=uuid4(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            key=key,
            enabled=change.enabled,
            mcp_enabled=change.mcp_enabled,
            mcp_metadata_enabled=change.mcp_metadata_enabled
            if change.mcp_metadata_enabled is not None
            else (saved.mcp_metadata_enabled if saved else False),
        )
        value = updated.model_dump(mode="json")
        value["key"] = key.get_secret_value()
        path = root / "vault-access.json"
        if content is not None and (damaged or (saved and saved.key != key)):
            state.replace_damaged(path, value, expected=content, kind="vault")
        else:
            state.write(path, value, replace=content is not None)
        return inspection(root, str(change.workspace_id))


def reveal_key(root: Path, request: VaultRequest):
    saved, _ = _current(root, request)
    if saved is None:
        raise state.LocalSetupError(
            "vault_key_missing", "This host has no readable saved vault key."
        )
    return {
        "workspace_id": str(request.workspace_id),
        "revision": str(saved.revision),
        "key_id": VaultCipher(saved.key.get_secret_value()).key_id,
        "recovery_key": saved.key.get_secret_value(),
    }


def settings(root: Path, workspace_id: str):
    try:
        saved, content, _ = _record(root, workspace_id)
    except (OSError, state.LocalSetupError):
        return VaultSettings()
    if saved is None:
        return VaultSettings.from_environment() if content is None else VaultSettings()
    return VaultSettings(
        key=saved.key,
        enabled=saved.enabled,
        mcp_enabled=saved.mcp_enabled,
        mcp_metadata_enabled=saved.mcp_metadata_enabled,
    )
