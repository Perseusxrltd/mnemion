"""Portable encrypted host custody; no database credentials in the public plan."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from uuid import UUID, uuid4
import zipfile

import psycopg
from psycopg.rows import dict_row

from .. import backup_encryption as encryption
from ..archives import (
    MANIFEST,
    canonical_json,
    private_json,
    verified_archive,
    write_archive,
)
from ..connectors.config import DriveConfig, RcloneConfig, SlackConfig, read_config
from ..local_state import temporary_directory
from ..private_output import private_output
from ..version import __version__
from . import recovery, supervision, update_state

FORMAT = "mnemion-host-recovery"
MAX_ASSETS = 128
MAX_ASSET_BYTES = 8 * 1024**2
MAX_ASSETS_BYTES = 64 * 1024**2
ASSET = re.compile(r"^asset-[0-9]{3}$")
COUNTED_TABLES = {
    "tenants",
    "spaces",
    "principals",
    "api_keys",
    "space_grants",
    "connectors",
    "connector_bindings",
    "memories",
    "vault_entries",
}


class HostRecoveryError(ValueError):
    """A fixed operator diagnostic, safe to return without configuration values."""


def read_private(path: Path, maximum=1_048_576) -> bytes:
    path = Path(path).expanduser().absolute()
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_size > maximum
            or os.name == "posix"
            and (info.st_uid != os.getuid() or info.st_mode & 0o077)
        ):
            raise HostRecoveryError("Use a bounded private regular file owned by this account.")
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise HostRecoveryError("A private host input exceeds its size limit.")
    return value


def key_file(path: Path) -> str:
    value = read_private(path, 256).decode("ascii").strip()
    encryption.key_id(value)
    return value


def create_key(path: Path) -> dict:
    value = encryption.new_key()
    with private_output(path) as output:
        output.write((value + "\n").encode())
    return {"created": True, "key_file": str(path), "key_id": encryption.key_id(value)}


def runtime_environment(value: dict) -> dict:
    value = supervision._environment(value)
    forbidden = {
        "BASH_ENV",
        "ENV",
        "SHELLOPTS",
        "GIT_SSH_COMMAND",
        "GIT_ASKPASS",
        "SSH_ASKPASS",
        "PATH",
        "HOME",
        "SHELL",
        "NODE_OPTIONS",
    }
    if any(
        name in forbidden
        or name.startswith(("LD_", "DYLD_", "SUPERVISOR_"))
        or name.startswith("PYTHON")
        and name not in {"PYTHONUNBUFFERED", "PYTHONDONTWRITEBYTECODE"}
        for name in value
    ):
        raise HostRecoveryError(
            "Set executable and shell overrides separately on the new host; recovery packages contain data and provider settings."
        )
    return value


def owner_connection(state: Path, admin: Path | None) -> str:
    owner_file = admin or state / "updates/owner.json"
    if not owner_file.exists():
        raise HostRecoveryError(
            "For an unmanaged host, supply --admin-credentials with its private database-owner file."
        )
    owner = json.loads(read_private(owner_file)).get("admin_database_url")
    if not isinstance(owner, str) or not owner:
        raise HostRecoveryError("Supply the host's private database-owner credentials.")
    from .service_updates import _target

    for filename, field in (("api.json", "database_url"), ("worker.json", "worker_database_url")):
        if _target(owner) != _target(json.loads(read_private(state / filename))[field]):
            raise HostRecoveryError(
                "The backup owner and service logins must identify the same database."
            )
    return owner


@contextmanager
def _capture_state(state: Path, *, lock_held: bool):
    """Give recovery capture a bounded turn, then read the protected settings."""
    state, previous = supervision.settings(state)
    managed = previous.get("managed_updates") is True
    previous_runtime = update_state.read(state / "updates/active.json") if managed else None
    with (
        (
            update_state.borrowed_lock(state / "updates")
            if lock_held
            else update_state.operator_lock(state / "updates", wait_seconds=300)
        )
        if managed
        else nullcontext()
    ):
        state, settings = supervision.settings(state)
        if managed != (settings.get("managed_updates") is True):
            raise HostRecoveryError(
                "Host management changed while capture waited; check its current configuration."
            )
        if managed and update_state.read(state / "updates/active.json") != previous_runtime:
            raise HostRecoveryError(
                "The active host runtime changed while capture waited; run the command again with its current runtime."
            )
        yield state, settings


def export_ledger(
    state: Path,
    output: Path,
    secret_file: Path,
    *,
    admin: Path | None = None,
    lock_held: bool = False,
) -> dict:
    with (
        _capture_state(state, lock_held=lock_held) as (state, _),
        temporary_directory(prefix="mnemion-host-ledger-") as root,
    ):
        owner, secret = owner_connection(state, admin), key_file(secret_file)
        ledger = root / "ledger.json"
        report = recovery.export_ledger(owner, ledger)
        receipt = encryption.encrypt_file(ledger, output, secret, kind="ledger")
        return {
            "ledger_file": str(output),
            "sha256": receipt.encrypted_sha256,
            "key_id": receipt.key_id,
            "snapshot_at": report["snapshot_at"],
            "off_host_delivery_verified": False,
        }


@contextmanager
def opened_ledger(path: Path, secret_file: Path, expected_sha256: str):
    with temporary_directory(prefix="mnemion-host-ledger-open-") as root:
        plaintext = root / "ledger.json"
        receipt = encryption.decrypt_file(
            path, plaintext, key_file(secret_file), expected_kind="ledger"
        )
        if receipt.encrypted_sha256 != expected_sha256:
            raise HostRecoveryError("The access ledger differs from the reviewed encrypted ledger.")
        yield plaintext, recovery.read_ledger(plaintext)


class Assets:
    def __init__(self, root: Path):
        self.root = root
        self.items = []
        self.members = {}
        self.paths = {}
        self.total = 0

    def add(self, content: bytes, *, path: Path | None = None, json_file=False) -> str:
        source = str(path.expanduser().absolute()) if path else None
        if source is not None and source in self.paths:
            return self.paths[source]
        if (
            len(self.items) >= MAX_ASSETS
            or len(content) > MAX_ASSET_BYTES
            or self.total + len(content) > MAX_ASSETS_BYTES
        ):
            raise HostRecoveryError("Host settings exceed the bounded private-file budget.")
        identifier = f"asset-{len(self.items):03d}"
        destination = self.root / identifier
        with private_output(destination) as output:
            output.write(content)
        self.items.append({"id": identifier, "source": source, "json": json_file})
        self.members["assets/" + identifier] = destination
        self.total += len(content)
        if source:
            self.paths[source] = identifier
        return identifier

    def file(self, path: Path) -> str:
        content = read_private(path, MAX_ASSET_BYTES)
        try:
            json.loads(content)
        except (ValueError, UnicodeError, RecursionError):
            is_json = False
        else:
            is_json = True
        return self.add(content, path=path, json_file=is_json)


def references(value):
    if isinstance(value, dict):
        for name, item in value.items():
            if name.endswith("_env") and isinstance(item, str):
                yield name, item
            yield from references(item)
    elif isinstance(value, list):
        for item in value:
            yield from references(item)


def snapshot(
    state: Path,
    output: Path,
    secret_file: Path,
    *,
    admin: Path | None = None,
    connector_configs: list[Path] = (),
    include_files: list[Path] = (),
    pg_bin: Path | None = None,
    plan_output: Path | None = None,
    lock_held: bool = False,
) -> dict:
    if output.exists() or plan_output is not None and plan_output.exists():
        raise HostRecoveryError(
            "Choose new package and plan destinations; existing files are preserved."
        )
    with (
        _capture_state(state, lock_held=lock_held) as (state, settings),
        temporary_directory(prefix="mnemion-host-export-") as root,
    ):
        if output.exists() or plan_output is not None and plan_output.exists():
            raise HostRecoveryError(
                "Choose new package and plan destinations; existing files are preserved."
            )
        owner, secret = owner_connection(state, admin), key_file(secret_file)
        connector_configs = list(
            dict.fromkeys(
                [
                    *(Path(item["config"]) for item in settings.get("connectors", [])),
                    *(path.expanduser().absolute() for path in connector_configs),
                ]
            )
        )
        assets = Assets(root)
        environment = runtime_environment(settings["environment"])
        # Caches and broker sockets belong to the destination hardware.
        environment.pop("MNEMION_MODEL_CACHE", None)
        environment.pop("MNEMION_MODEL_BROKER", None)
        for path in include_files:
            if path.expanduser().absolute() == secret_file.expanduser().absolute():
                raise HostRecoveryError("Keep the package encryption key outside the package.")
            assets.file(path)
        for name, value in list(environment.items()):
            if name.endswith(("_CONFIG", "_FILE", "_BUNDLE")) and Path(value).is_absolute():
                assets.file(Path(value))
        # Explicit provider configurations can reference additional credentials
        # through environment variables. Copy those references, never every
        # variable inherited by this operator process.
        for item in list(assets.items):
            if not item["json"]:
                continue
            data = json.loads(assets.members["assets/" + item["id"]].read_bytes())
            for kind, variable in references(data):
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", variable):
                    raise HostRecoveryError(
                        "An included configuration has an invalid credential reference."
                    )
                if variable in supervision.ROLE_VARIABLES or variable.startswith(
                    ("LD_", "DYLD_", "PYTHON")
                ):
                    raise HostRecoveryError(
                        "Use dedicated provider variables, separate from database or runtime credentials."
                    )
                value = environment.get(variable, os.environ.get(variable))
                if value is None:
                    raise HostRecoveryError(
                        "A configured provider variable is missing; supply it before exporting."
                    )
                environment[variable] = value
                if kind in {"file_env", "ca_bundle_env"}:
                    assets.file(Path(value))
        connectors = []
        with psycopg.connect(owner, row_factory=dict_row) as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            for path in connector_configs:
                read_private(path)
                config = read_config(path)
                token = config.service_token.read()
                registered = connection.execute(
                    """SELECT c.id,c.provider FROM mnemion.connectors c JOIN mnemion.api_keys k
                    ON k.tenant_id=c.tenant_id AND k.principal_id=c.principal_id
                    WHERE c.id=%s AND k.token_hash=%s""",
                    (config.connector_id, hashlib.sha256(token.encode()).hexdigest()),
                ).fetchone()
                if not registered or registered["provider"] != config.provider.type:
                    raise HostRecoveryError(
                        "An included connector does not belong to this database and provider."
                    )
                data = config.model_dump(mode="json")
                token_asset = assets.add((token + "\n").encode())
                data["service_token"] = {"file": "@" + token_asset}
                if isinstance(config.provider, (SlackConfig, DriveConfig)):
                    token_asset = assets.add((config.provider.token.read() + "\n").encode())
                    data["provider"]["token"] = {"file": "@" + token_asset}
                if isinstance(config.provider, RcloneConfig) and config.provider.config_file:
                    assets.file(config.provider.config_file)
                connectors.append({"id": str(config.connector_id), "config": data})
        if len(connectors) > 64 or len({item["id"] for item in connectors}) != len(connectors):
            raise HostRecoveryError("Choose at most 64 distinct connector configurations.")
        environment = runtime_environment(environment)
        backup_path = root / "database.mnemion"
        recovery.create_backup(owner, backup_path, pg_bin=pg_bin)
        ledger_path = root / "ledger.json"
        recovery.export_ledger(owner, ledger_path)
        ledger = recovery.read_ledger(ledger_path)
        # This archive was just created by create_backup, which already hashes
        # its files. Read its manifest without unpacking a second database copy.
        with zipfile.ZipFile(backup_path) as created_archive:
            backup = json.loads(created_archive.read(MANIFEST))
            plan = {
                "format": FORMAT,
                "version": 1,
                "package_id": str(uuid4()),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "service_version": __version__,
                "backup_id": backup["backup_id"],
                "snapshot_at": backup["snapshot_at"],
                "ledger_at": ledger["snapshot_at"],
                "postgres_major": backup["server_version"] // 10000,
                "tenant_ids": backup["tenant_ids"],
                "counts": {
                    name: entry["count"]
                    for name, entry in backup["tables"].items()
                    if name in COUNTED_TABLES
                },
                "files": len(assets.items),
                "connectors": [
                    {"id": item["id"], "provider": item["config"]["provider"]["type"]}
                    for item in connectors
                ],
                "source_updates": supervision.configuration_status(state, settings)["updates"],
                "public_origin_configured": bool(settings.get("public_url")),
                "network_listener": settings["host"] not in {"127.0.0.1", "::1"},
                "application_keys_in_ledger": len(ledger["application_key_state"]["keys"]),
                "external_transport_verified": False,
                "model_cache_included": False,
            }
        host = {
            "plan": plan,
            "host": settings["host"],
            "port": settings["port"],
            "public_url": settings.get("public_url"),
            "environment": environment,
            "assets": assets.items,
            "connectors": connectors,
        }
        if len(canonical_json(host)) > 1_048_576:
            raise HostRecoveryError("The host recovery recipe exceeds 1 MiB.")
        host_path = root / "host.json"
        private_json(host_path, host)
        archive_path = root / "host.mnemion"
        write_archive(
            archive_path,
            {
                "host.json": host_path,
                "database.mnemion": backup_path,
                "ledger.json": ledger_path,
                **assets.members,
            },
            {"format": FORMAT, "version": 1, "package_id": plan["package_id"]},
        )
        receipt = encryption.encrypt_file(archive_path, output, secret, kind="bundle")
        result = {
            "package_file": str(output),
            "sha256": receipt.encrypted_sha256,
            "key_id": receipt.key_id,
            "plan": plan,
            "off_host_delivery_verified": False,
        }
        if plan_output is not None:
            private_json(plan_output, {key: result[key] for key in ("sha256", "key_id", "plan")})
        return result


@contextmanager
def opened(package: Path, secret_file: Path, expected_sha256: str | None = None):
    with temporary_directory(prefix="mnemion-host-open-") as private:
        archive = private / "host.mnemion"
        receipt = encryption.decrypt_file(
            package, archive, key_file(secret_file), expected_kind="bundle"
        )
        digest = receipt.encrypted_sha256
        if expected_sha256 is not None and digest != expected_sha256:
            raise HostRecoveryError("The package differs from the reviewed encrypted package.")
        with opened_archive(archive) as (host, root):
            yield host, root, digest


@contextmanager
def opened_archive(archive: Path, *, temporary_directory: Path | None = None, cancelled=None):
    """Validate decrypted custody data without adopting any source host settings.

    The native desktop supplies its private scratch directory and cancellation
    hook. Unix host recovery retains its existing encrypted-file interface.
    """
    with verified_archive(
        archive,
        FORMAT,
        temporary_directory=temporary_directory,
        check_cancelled=lambda: recovery._cancel(cancelled),
    ) as (manifest, root):
        if manifest["files"]["host.json"]["size"] > 1_048_576:
            raise HostRecoveryError("The host recipe exceeds its size budget.")
        host = json.loads((root / "host.json").read_bytes())
        plan = host["plan"]
        if (
            plan.get("format") != FORMAT
            or type(plan.get("version")) is not int
            or plan["version"] != 1
        ):
            raise HostRecoveryError("Unsupported host recovery plan.")
        if str(UUID(plan["package_id"])) != manifest.get("package_id"):
            raise HostRecoveryError("The host plan and archive disagree.")
        if not isinstance(host["assets"], list) or len(host["assets"]) > MAX_ASSETS:
            raise HostRecoveryError("Invalid host file inventory.")
        asset_ids = [item["id"] for item in host["assets"]]
        if len(set(asset_ids)) != len(asset_ids) or any(
            not ASSET.fullmatch(item) for item in asset_ids
        ):
            raise HostRecoveryError("Invalid host file identities.")
        expected = {"host.json", "database.mnemion", "ledger.json"} | {
            "assets/" + item for item in asset_ids
        }
        if set(manifest["files"]) != expected:
            raise HostRecoveryError("The host package has missing or unexpected files.")
        if sum(
            manifest["files"]["assets/" + item]["size"] for item in asset_ids
        ) > MAX_ASSETS_BYTES or any(
            manifest["files"]["assets/" + item]["size"] > MAX_ASSET_BYTES for item in asset_ids
        ):
            raise HostRecoveryError("The private host files exceed their size budget.")
        runtime_environment(host["environment"])
        public_plan(plan)
        recovery.read_ledger(root / "ledger.json")
        yield host, root


def inspect(package: Path, secret_file: Path) -> dict:
    with opened(package, secret_file) as (host, _, digest):
        return {
            "authenticated": True,
            "sha256": digest,
            "plan": public_plan(host["plan"]),
            "database_restore_verified": False,
            "default_access_policy": "rotate_all",
            "default_update_mode": "managed",
            "off_host_delivery_verified": False,
        }


def public_plan(value: dict) -> dict:
    """Allowlist the non-secret plan; never print arbitrary archived properties."""
    result = {"format": FORMAT, "version": 1}
    for key in ("package_id", "backup_id"):
        result[key] = str(UUID(value[key]))
    for key in ("created_at", "snapshot_at", "ledger_at"):
        stamp = datetime.fromisoformat(value[key])
        if stamp.tzinfo is None:
            raise HostRecoveryError("Host recovery dates must include their timezone.")
        result[key] = stamp.isoformat()
    version = value["service_version"]
    if not isinstance(version, str) or not re.fullmatch(
        r"[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}", version
    ):
        raise HostRecoveryError("Invalid host recovery service version.")
    result["service_version"] = version
    for key in ("postgres_major", "files", "application_keys_in_ledger"):
        if type(value[key]) is not int or not 0 <= value[key] <= 1_000_000_000:
            raise HostRecoveryError("Invalid host recovery counts.")
        result[key] = value[key]
    result["tenant_ids"] = [str(UUID(item)) for item in value["tenant_ids"]]
    result["counts"] = {}
    for key, count in value["counts"].items():
        if key not in COUNTED_TABLES or type(count) is not int or count < 0:
            raise HostRecoveryError("Invalid host recovery inventory.")
        result["counts"][key] = count
    result["connectors"] = []
    for item in value["connectors"]:
        if item["provider"] not in {"filesystem", "git", "rclone", "slack", "gdrive"}:
            raise HostRecoveryError("Invalid bundled connector provider.")
        result["connectors"].append({"id": str(UUID(item["id"])), "provider": item["provider"]})
    mode, enabled = value["source_updates"]["mode"], value["source_updates"]["enabled"]
    if mode not in {"manual", "managed"} or enabled is not None and type(enabled) is not bool:
        raise HostRecoveryError("Invalid saved automatic update mode.")
    result["source_updates"] = {"mode": mode, "enabled": enabled}
    for key in (
        "public_origin_configured",
        "network_listener",
        "external_transport_verified",
        "model_cache_included",
    ):
        if type(value[key]) is not bool:
            raise HostRecoveryError("Invalid host recovery flag.")
        result[key] = value[key]
    return result
