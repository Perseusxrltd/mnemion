"""Reviewed native agent configuration, independent of a running Studio session.

Dedicated application credentials remain in private per-installation files.
Configuration backups and replacement reuse the existing agent setup contract.
Installed state is observed from the actual client file, never an optimistic flag.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import UUID, uuid4

import httpx
from pydantic import Field, field_validator

from . import agent_runtime, agent_setup, local_state
from .connectors.config import service_url
from .private_output import private_output
from .sdk import Client, MnemionError
from .service.models import Command

MAX_INSTALLATIONS = 64


class Setup(Command):
    id: UUID
    client: str
    server_name: str = Field(default="mnemion", pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    config_path: str = Field(min_length=1, max_length=4096)
    endpoint: str = Field(min_length=1, max_length=2048)
    tenant_id: UUID
    principal_id: UUID
    legacy_space: UUID | None = None

    @field_validator("client")
    @classmethod
    def supported_client(cls, value):
        if value not in agent_setup.CLIENTS:
            raise ValueError("Choose a supported agent profile")
        return value

    @field_validator("endpoint")
    @classmethod
    def secure_address(cls, value):
        return service_url(value)

    @field_validator("config_path")
    @classmethod
    def absolute_path(cls, value):
        if not Path(value).is_absolute() or "\x00" in value:
            raise ValueError("Choose an absolute agent configuration path")
        return value


class Record(Setup):
    created_at: str
    executable: str = Field(min_length=1, max_length=4096)
    launcher: bool = False


def location(root: Path, identifier: UUID) -> Path:
    return root / str(identifier)


def key_path(root: Path, identifier: UUID) -> Path:
    return location(root, identifier) / "credentials.json"


def node(root: Path, record: Record) -> dict:
    return setup_command(root, record, Path(record.executable))


def setup_command(root: Path, setup: Setup, executable: Path) -> dict:
    launcher = setup.launcher if isinstance(setup, Record) else agent_runtime.available(executable)
    if launcher:
        return agent_runtime.command(root, key_path(root, setup.id), setup.legacy_space)
    return agent_setup.server_config(
        key_path(root, setup.id),
        python=str(executable),
        legacy_space=str(setup.legacy_space) if setup.legacy_space else None,
        standalone=True,
    )


def observed(root: Path, record: Record) -> dict:
    target = Path(record.config_path)
    content = agent_setup.configuration(target)
    digest = hashlib.sha256(content).hexdigest() if content is not None else None
    value = agent_setup.document(record.client, content)
    current = agent_setup.servers(record.client, value).get(record.server_name)
    installed = current == node(root, record)
    credential_exists = key_path(root, record.id).is_file()
    return {
        **record.model_dump(mode="json", exclude={"executable"}),
        "configuration_hash": digest,
        "state": "installed"
        if installed and credential_exists
        else "key_missing"
        if installed
        else "replaced"
        if current is not None
        else "removed",
        "private_key_file_exists": credential_exists,
        "agent_restart_required": installed,
    }


def records(root: Path) -> list[Record]:
    local_state.directory(root)
    result = []
    for path in sorted(root.iterdir()):
        try:
            identifier = UUID(path.name)
        except ValueError:
            continue
        if len(result) >= MAX_INSTALLATIONS:
            raise ValueError("Review existing agent installations before adding another")
        local_state.directory(path)
        record = Record.model_validate(local_state.read(path / "setup.json"))
        if record.id != identifier:
            raise ValueError("Agent setup identity differs from its private directory")
        result.append(record)
    return result


def maintained(root: Path, executable: Path | None = None) -> tuple[list[Record], str | None]:
    local_state.directory(root)
    attention = None
    with local_state.lock(root):
        saved = records(root)
        if (
            executable
            and agent_runtime.available(executable)
            and any(record.launcher for record in saved)
        ):
            try:
                agent_runtime.prepare(root, executable)
            except (OSError, ValueError, local_state.LocalSetupError):
                attention = "The private agent runtime could not be refreshed. Existing files are retained; check available disk space and reopen Studio to retry."
    return saved, attention


def maintain(root: Path, executable: Path | None = None) -> dict:
    _, attention = maintained(root, executable)
    return {"runtime_attention": attention}


def status(root: Path, executable: Path | None = None) -> dict:
    saved, attention = maintained(root, executable)
    profiles = []
    for client in agent_setup.CLIENTS:
        try:
            path = agent_setup.default_path(client)
            profiles.append(
                {
                    "client": client,
                    "config_path": str(path),
                    "exists": path.is_file(),
                    "custom_path_required": False,
                }
            )
        except ValueError:
            profiles.append(
                {
                    "client": client,
                    "config_path": None,
                    "exists": False,
                    "custom_path_required": True,
                }
            )
    installations = []
    for record in saved:
        try:
            installations.append(observed(root, record))
        except (OSError, ValueError):
            installations.append(
                {
                    **record.model_dump(mode="json", exclude={"executable"}),
                    "state": "unverified",
                    "configuration_hash": None,
                    "private_key_file_exists": key_path(root, record.id).is_file(),
                    "agent_restart_required": False,
                }
            )
    return {
        "profiles": profiles,
        "installations": installations,
        "credential_storage": "private_os_account_file",
        "max_installations": MAX_INSTALLATIONS,
        "runtime_version": agent_runtime.current_version(root),
        "runtime_attention": attention,
    }


def reviewed_plan(root: Path, setup: Setup, executable: Path, *, remove=False):
    target = Path(setup.config_path)
    private = root.resolve()
    resolved = target.resolve()
    if resolved == private or private in resolved.parents or resolved in private.parents:
        raise ValueError("Agent configuration must be separate from Mnemion's private setup files")
    suffixes = {
        "toml": {".toml"},
        "yaml": {".yaml", ".yml"},
        "json5": {".json", ".json5"},
        "json": {".json"},
    }
    if target.suffix.lower() not in suffixes[agent_setup.CLIENTS[setup.client][0]]:
        raise ValueError("Choose the configuration file format used by this agent")
    return agent_setup.plan(
        setup.client,
        target,
        key_path(root, setup.id),
        python=str(executable),
        legacy_space=str(setup.legacy_space) if setup.legacy_space else None,
        standalone=True,
        server_name=setup.server_name,
        remove=remove,
        server=setup_command(root, setup, executable),
    )


def preview(root: Path, request: dict, executable: Path) -> dict:
    definition = dict(request["setup"])
    definition.setdefault("id", str(uuid4()))
    if not definition.get("config_path"):
        definition["config_path"] = str(agent_setup.default_path(definition["client"]))
    setup = Setup.model_validate(definition)
    plan = reviewed_plan(root, setup, executable)
    return {
        "setup": setup.model_dump(mode="json"),
        "configuration_hash": plan.expected_hash,
        "replacing": plan.replacing,
        "snippet": plan.snippet,
        "command": setup_command(root, setup, executable),
        "credential_storage": "private_os_account_file",
    }


def install(root: Path, request: dict, executable: Path) -> dict:
    setup = Setup.model_validate(request["setup"])
    if request["confirm"] is not True:
        raise ValueError("Review and confirm this agent connection")
    credential = request["credential"]
    if (
        not isinstance(credential, str)
        or not 16 <= len(credential) <= 8192
        or any(not 33 <= ord(c) <= 126 for c in credential)
    ):
        raise ValueError("Use a dedicated application key")
    local_state.directory(root)
    with local_state.lock(root):
        if len(records(root)) >= MAX_INSTALLATIONS:
            raise ValueError("Review existing agent installations before adding another")
        plan = reviewed_plan(root, setup, executable)
        if plan.expected_hash != request["configuration_hash"]:
            raise local_state.LocalSetupError(
                "agent_settings_changed", "Agent settings changed. Preview again before installing."
            )
        if plan.replacing and request["replace_existing"] is not True:
            raise ValueError("Confirm replacement of this named MCP connection")
        with Client(setup.endpoint, credential, timeout=20, retries=0) as client:
            me = client.request("GET", "/v1/me")
            if (
                me.get("tenant_id") != str(setup.tenant_id)
                or me.get("principal_id") != str(setup.principal_id)
                or me.get("administrator") is not False
                or me.get("kind") != "application"
            ):
                raise local_state.LocalSetupError(
                    "agent_identity_mismatch",
                    "Use the selected application's key in the expected workspace.",
                )
        launcher = agent_runtime.available(executable)
        if launcher:
            try:
                agent_runtime.prepare(root, executable)
            except (OSError, ValueError, local_state.LocalSetupError):
                raise local_state.LocalSetupError(
                    "agent_runtime_unavailable",
                    "The private agent runtime could not be prepared. Check disk space or repair Studio before retrying.",
                ) from None
        # Prepare durable identity and private credentials before pointing an
        # agent at them. A lost reply remains inspectable from the actual config.
        directory = local_state.directory(location(root, setup.id), exist_ok=False)
        record = Record(
            **setup.model_dump(),
            created_at=datetime.now(timezone.utc).isoformat(),
            executable=str(executable),
            launcher=launcher,
        )
        try:
            local_state.write(directory / "setup.json", record.model_dump(mode="json"))
        except BaseException:
            if not any(directory.iterdir()):
                directory.rmdir()
            raise
        with private_output(key_path(root, setup.id)) as stream:
            stream.write(
                (json.dumps({"api_url": setup.endpoint, "api_key": credential}) + "\n").encode()
            )
        result = agent_setup.apply(plan)
        current = observed(root, record)
        if current["state"] != "installed":
            raise local_state.LocalSetupError(
                "agent_install_unconfirmed", "Read setup status before retrying this connection."
            )
        return {"installation": current, "backup": result["backup"], "changed": result["changed"]}


def remove(root: Path, request: dict) -> dict:
    if request["confirm"] is not True:
        raise ValueError("Confirm removal of this device's agent connection and private key file")
    identifier = UUID(request["id"])
    local_state.directory(root)
    with local_state.lock(root):
        record = next((item for item in records(root) if item.id == identifier), None)
        if record is None:
            raise ValueError("Choose an existing installation")
        current = observed(root, record)
        if current["configuration_hash"] != request["configuration_hash"]:
            raise local_state.LocalSetupError(
                "agent_settings_changed", "Agent settings changed. Refresh before removing."
            )
        result = {"changed": False, "backup": None}
        if current["state"] in {"installed", "key_missing"}:
            result = agent_setup.apply(
                reviewed_plan(root, record, Path(record.executable), remove=True)
            )
        # A replaced entry belongs to the current client configuration. Preserve
        # it; clean only this installation's explicitly confirmed private key.
        path = key_path(root, identifier)
        if path.exists():
            local_state.read(path)
            path.unlink()
        final = observed(root, record)
        directory = location(root, identifier)
        # Only remove the known app-owned files. Unexpected user files are
        # retained under a retired name, outside the active installation list.
        retired = root / ("retired-" + uuid4().hex)
        directory.rename(retired)
        (retired / "setup.json").unlink()
        if not any(retired.iterdir()):
            retired.rmdir()
        return {
            "installation": {**final, "state": "removed"},
            "backup": result["backup"],
            "changed": result["changed"],
            "server_key_revoked": False,
        }


def perform(root: Path, request: dict, executable: Path) -> dict:
    fields = {
        "status": {"operation"},
        "maintain": {"operation"},
        "preview": {"operation", "setup"},
        "install": {
            "operation",
            "setup",
            "configuration_hash",
            "credential",
            "confirm",
            "replace_existing",
        },
        "remove": {"operation", "id", "configuration_hash", "confirm"},
    }
    operation = request.get("operation")
    if operation not in fields or set(request) != fields[operation]:
        raise ValueError("Choose a supported private agent setup operation")
    if operation == "status":
        return status(root, executable)
    if operation == "maintain":
        return maintain(root, executable)
    if operation == "preview":
        return preview(root, request, executable)
    if operation == "install":
        return install(root, request, executable)
    return remove(root, request)


def arguments(parser):
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--engine-executable", type=Path, required=True)


def dispatch(args) -> int:
    try:
        body = sys.stdin.buffer.read(256 * 1024 + 1)
        if len(body) > 256 * 1024:
            raise ValueError("Agent setup request is too large")
        request = json.loads(body)
        if not isinstance(request, dict):
            raise ValueError("Invalid agent setup request")
        result = perform(args.root, request, args.engine_executable)
        print(
            json.dumps({"event": "result", "ok": True, "result": result}, separators=(",", ":")),
            flush=True,
        )
        return 0
    except (
        OSError,
        ValueError,
        KeyError,
        local_state.LocalSetupError,
        MnemionError,
        httpx.HTTPError,
    ) as error:
        code = (
            error.code
            if isinstance(error, local_state.LocalSetupError)
            else "agent_setup_unavailable"
        )
        print(json.dumps({"event": "result", "ok": False, "error": code}), flush=True)
        return 2
