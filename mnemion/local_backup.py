"""Native host-operator snapshots and ledger files for guided recovery.

Only the OS account owning the local database can use these operations. Keys
arrive in memory from the caller; they are never saved in operator status.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from . import backup_catalog as catalog, backup_encryption as encryption
from . import backup_retention as retention, local_state as state
from .archives import verified_archive
from .backup_retention import RetentionPolicy
from .local_database import LocalDatabase, prepare_credentials
from .service import recovery
from .version import __version__


class LocalBackupContext(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    format: Literal[1] = 1
    workspace_id: UUID
    primary_tenant_id: UUID
    workspace_name: str = Field(min_length=1, max_length=200)
    owner_name: str = Field(min_length=1, max_length=200)
    embedding_profile: Literal["e5-small", "bge-small-en"]
    threads: int = Field(ge=1, le=8)
    application_version: str = Field(pattern=r"^[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}$")

    @field_validator("workspace_name", "owner_name")
    @classmethod
    def name(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Use a workspace name without control characters")
        return value


class BackupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    workspace_id: UUID
    destination: str = Field(min_length=1, max_length=4096)
    recovery_key: SecretStr
    watch_parent: bool = False
    retention: RetentionPolicy = Field(default_factory=RetentionPolicy)

    @field_validator("destination")
    @classmethod
    def folder(cls, value):
        if not Path(value).is_absolute() or any(ord(c) < 32 for c in value):
            raise ValueError("Choose an absolute backup folder without control characters")
        return value

    @field_validator("recovery_key")
    @classmethod
    def key(cls, value):
        encryption.key_id(value.get_secret_value())
        return value


class BackupInventoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    workspace_id: UUID
    destination: str = Field(min_length=1, max_length=4096)
    key_id: str = Field(pattern=r"^[a-f0-9]{24}$")
    policy: RetentionPolicy = Field(default_factory=RetentionPolicy)
    watch_parent: bool = False

    @field_validator("destination")
    @classmethod
    def folder(cls, value):
        return BackupRequest.folder(value)


class BackupPruneRequest(BackupInventoryRequest):
    plan_token: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm: bool

    @field_validator("confirm")
    @classmethod
    def confirmed(cls, value):
        if value is not True:
            raise ValueError("Review and confirm removal of the older tracked copies")
        return value


class BackupInspection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: str = Field(min_length=1, max_length=4096)
    recovery_key: SecretStr
    watch_parent: bool = False

    @field_validator("source")
    @classmethod
    def file(cls, value):
        if not Path(value).is_absolute() or any(ord(c) < 32 for c in value):
            raise ValueError("Choose an absolute backup file without control characters")
        return value

    @field_validator("recovery_key")
    @classmethod
    def key(cls, value):
        encryption.key_id(value.get_secret_value())
        return value


def _now():
    return datetime.now(timezone.utc).isoformat()


def _require_space(location: Path, required: int) -> None:
    if shutil.disk_usage(location).free < required + 64 * 1024**2:
        raise state.LocalSetupError(
            "disk_budget",
            "Free more disk space or choose another drive before this backup operation.",
        )


def _decrypt_space(control: Path, *sources: str) -> None:
    # File sizes are admission hints only. The encryption reader still checks
    # regular files, identities, authenticated lengths and every encrypted byte.
    _require_space(control, sum(Path(source).stat().st_size for source in sources))


def _control(root: Path):
    state.directory(root)
    return state.directory(root / "backup-operations")


def _destination(root: Path, selection: str, workspace_id: str, *, create=True) -> Path:
    base = Path(selection).resolve(strict=True)
    if not base.is_dir():
        raise state.LocalSetupError("backup_destination", "Choose an existing backup folder.")
    destination = base / "Mnemion backups" / workspace_id
    if destination.is_relative_to(root.resolve()):
        raise state.LocalSetupError(
            "backup_destination", "Choose a backup folder outside this workspace's data folder."
        )
    for directory in (destination.parent, destination):
        if create:
            directory.mkdir(mode=0o700, exist_ok=True)
        try:
            info = directory.lstat()
        except FileNotFoundError:
            if not create:
                return destination
            raise
        if (
            not directory.is_dir()
            or directory.is_symlink()
            or getattr(info, "st_file_attributes", 0) & 0x400
        ):
            raise state.LocalSetupError(
                "backup_destination",
                "The managed backup folder cannot be a link or redirected directory.",
            )
    return destination


def _database(root: Path, runtime: Path, workspace_id: UUID):
    from .local_workspace import configuration

    settings = configuration(root)
    if settings["workspace_id"] != str(workspace_id):
        raise state.LocalSetupError("settings_changed", "Choose the current local workspace.")
    if not (root / "credentials.json").is_file() or not (root / "database").is_dir():
        raise state.LocalSetupError(
            "backup_unavailable", "Start the existing local workspace before backing it up."
        )
    credentials = prepare_credentials(root)
    database = LocalDatabase(root, runtime, settings, credentials)
    # Verify the current database path, TLS peer and native executable. This
    # helper neither starts nor stops the already-owned server.
    database._verify_server()
    with psycopg.connect(database.dsn()) as connection:
        if not connection.execute(
            "SELECT 1 FROM mnemion.tenants WHERE id=%s", (credentials["tenant_id"],)
        ).fetchone():
            raise state.LocalSetupError(
                "workspace_identity", "The database does not contain this local workspace."
            )
    return database, settings, credentials


def _context(settings: dict, credentials: dict) -> dict:
    # An explicit allowlist excludes database passwords, keys, remote routing,
    # provider tokens and future private host settings.
    return {
        "local_workspace": {
            "format": 1,
            "workspace_id": settings["workspace_id"],
            "primary_tenant_id": credentials["tenant_id"],
            "workspace_name": settings["workspace_name"],
            "owner_name": settings["owner_name"],
            "embedding_profile": settings["embedding_profile"],
            "threads": settings["threads"],
            "application_version": __version__,
        }
    }


def _seal(source: Path, output: Path, key: str, kind, cancelled):
    created = encryption.encrypt_file(source, output, key, kind=kind, cancelled=cancelled)
    verified = encryption.verify_file(output, key, expected_kind=kind, cancelled=cancelled)
    if asdict(verified) != {**asdict(created), "authenticated": True}:
        raise state.LocalSetupError(
            "backup_verification",
            "The written backup did not match its verified input. It was retained for inspection.",
        )
    return {
        "file": str(output),
        "bytes": verified.encrypted_bytes,
        "sha256": verified.encrypted_sha256,
        "key_id": verified.key_id,
        "authenticated": True,
    }


def capture(
    root: Path,
    runtime: Path,
    request: BackupRequest,
    *,
    ledger_only=False,
    cancelled=None,
    emit=None,
):
    """Capture from the live local database without changing its memory state."""
    control = _control(root)

    def progress(stage, message):
        if emit:
            emit({"event": "backup_progress", "stage": stage, "message": message})

    with state.lock(control):
        recovery._cancel(cancelled)
        database, settings, credentials = _database(root, runtime, request.workspace_id)
        destination = _destination(root, request.destination, settings["workspace_id"])
        estimate = 0
        if not ledger_only:
            with psycopg.connect(database.dsn(), options="-c statement_timeout=5000") as connection:
                estimate = connection.execute(
                    "SELECT pg_database_size(current_database())"
                ).fetchone()[0]
        _require_space(control, estimate * 4)
        _require_space(destination, estimate * 2)
        key = request.recovery_key.get_secret_value()
        identifier = uuid4().hex
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        with state.temporary_directory(prefix="capture-", dir=control) as scratch:
            snapshot = None
            if not ledger_only:
                progress("snapshot", "Saving a consistent database snapshot…")
                snapshot = recovery.create_backup(
                    database.dsn(),
                    scratch / "snapshot.mnemion",
                    pg_bin=runtime / "bin",
                    context=_context(settings, credentials),
                    temporary_directory=scratch,
                    cancelled=cancelled,
                )
            progress("ledger", "Recording current deletions and access permissions…")
            ledger = recovery.export_ledger(
                database.dsn(), scratch / "ledger.json", cancelled=cancelled
            )
            payload = recovery.read_ledger(scratch / "ledger.json")
            record = {
                "format": 1,
                "operation_id": identifier,
                "workspace_id": settings["workspace_id"],
                "scope": "complete_local_database",
                "tenant_count": len(payload["tenant_ids"]),
                "ledger_at": ledger["snapshot_at"],
                "application_version": __version__,
            }
            if snapshot is not None:
                progress("encrypting_snapshot", "Encrypting and verifying the database backup…")
                record["snapshot"] = {
                    **_seal(
                        scratch / "snapshot.mnemion",
                        destination / f"snapshot-{stamp}-{identifier}.mnemion.enc",
                        key,
                        "snapshot",
                        cancelled,
                    ),
                    "backup_id": snapshot["backup_id"],
                    "snapshot_at": snapshot["snapshot_at"],
                    "memory_count": snapshot["tables"].get("memories", 0),
                }
            progress("encrypting_ledger", "Encrypting and verifying the access ledger…")
            record["ledger"] = _seal(
                scratch / "ledger.json",
                destination / f"ledger-{stamp}-{identifier}.mnemion.enc",
                key,
                "ledger",
                cancelled,
            )
            record["verified_at"] = _now()
            catalog.register(root, destination, record)
            state.write(
                root / "last-ledger.json",
                {key: value for key, value in record.items() if key != "snapshot"},
            )
            if snapshot is not None:
                state.write(root / "last-backup.json", record)
                # Pruning follows a verified full capture. Ledger-only runs
                # never repeatedly hash large snapshots or remove history.
                if request.retention.mode == "limited":
                    try:
                        record["retention"] = retention.cleanup(
                            root,
                            destination,
                            settings["workspace_id"],
                            encryption.key_id(key),
                            request.retention,
                            cancelled=cancelled,
                            emit=emit,
                        )
                    except (OSError, state.LocalSetupError):
                        record["retention_warning"] = (
                            "The new snapshot and access ledger were verified. Cleanup could not finish; review the backup inventory."
                        )
                    state.write(root / "last-backup.json", record)
            progress("complete", "Encrypted recovery files were saved and verified locally.")
            return record


def inspect_inventory(
    root: Path, request: BackupInventoryRequest, *, prune=False, cancelled=None, emit=None
):
    """Offline owner control: no database start, decryption key or provider login."""
    from .local_workspace import configuration

    with state.lock(_control(root)):
        encryption._cancel(cancelled)
        settings = configuration(root)
        if settings["workspace_id"] != str(request.workspace_id):
            raise state.LocalSetupError("settings_changed", "Choose the current local workspace.")
        folder = _destination(root, request.destination, settings["workspace_id"], create=False)
        arguments = (root, folder, settings["workspace_id"], request.key_id, request.policy)
        if prune:
            if not isinstance(request, BackupPruneRequest) or request.confirm is not True:
                raise state.LocalSetupError(
                    "backup_confirmation", "Review and confirm the current cleanup plan."
                )
            return retention.cleanup(
                *arguments, expected_plan=request.plan_token, cancelled=cancelled, emit=emit
            )
        return retention.inventory(*arguments)


def inspect_file(root: Path, request: BackupInspection, *, cancelled=None) -> dict:
    """Authenticate and inspect a selected file; never execute database SQL."""
    control = _control(root)
    _decrypt_space(control, request.source)
    with (
        state.lock(control),
        state.temporary_directory(prefix="inspect-", dir=control) as scratch,
    ):
        unlocked = scratch / "unlocked"
        receipt = encryption.decrypt_file(
            Path(request.source),
            unlocked,
            request.recovery_key.get_secret_value(),
            cancelled=cancelled,
        )
        common = {
            "kind": receipt.kind,
            "key_id": receipt.key_id,
            "encrypted_bytes": receipt.encrypted_bytes,
            "sha256": receipt.encrypted_sha256,
            "authenticated": True,
        }
        if receipt.kind == "ledger":
            ledger = recovery.read_ledger(unlocked)
            return {
                **common,
                "ledger_at": ledger["snapshot_at"],
                "tenant_count": len(ledger["tenant_ids"]),
                "deletion_count": len(ledger["deletions"]),
            }
        if receipt.kind == "bundle":
            from .local_host_recovery import open_contents

            with open_contents(unlocked, scratch, cancelled=cancelled) as host:
                result = _inspect_snapshot(host.snapshot, scratch, cancelled=cancelled)
                return {
                    **common,
                    **result,
                    "kind": "host",
                    "ledger_at": host.ledger_at,
                    "embedded_ledger_sha256": host.ledger_sha256,
                    "host_package": host.description,
                }
        if receipt.kind != "snapshot":
            raise state.LocalSetupError(
                "backup_format", "Choose an encrypted snapshot, host package or access ledger."
            )
        return {**common, **_inspect_snapshot(unlocked, scratch, cancelled=cancelled)}


def _inspect_snapshot(source: Path, scratch: Path, *, cancelled=None) -> dict:
    with verified_archive(
        source,
        recovery.BACKUP_FORMAT,
        temporary_directory=scratch,
        check_cancelled=lambda: recovery._cancel(cancelled),
    ) as (manifest, members):
        if set(manifest["files"]) != {"database.dump", "deletions.json"}:
            raise state.LocalSetupError("backup_format", "The database backup is incomplete.")
        ledger = recovery.read_ledger(members / "deletions.json")
        context = manifest.get("context", {})
        if not isinstance(context, dict) or len(json.dumps(context)) > 16 * 1024:
            raise state.LocalSetupError("backup_format", "The backup's setup metadata is invalid.")
        local = context.get("local_workspace")
        context = (
            {
                "local_workspace": LocalBackupContext.model_validate_json(
                    json.dumps(local)
                ).model_dump(mode="json")
            }
            if local is not None
            else {}
        )
        return {
            "backup_id": manifest["backup_id"],
            "snapshot_at": manifest["snapshot_at"],
            "ledger_at": ledger["snapshot_at"],
            "tenant_count": len(manifest["tenant_ids"]),
            "tenant_ids": manifest["tenant_ids"],
            "memory_count": manifest["tables"].get("memories", {}).get("count", 0),
            "application_version": manifest["application_version"],
            "server_version": manifest["server_version"],
            "context": context,
            "archive_verified": True,
        }


def dispatch(root: Path, runtime: Path | None, action: str, emit) -> int:
    """Bounded private stdin protocol for both one-shot and app-owned jobs."""
    import signal
    import sys
    import threading
    from pydantic import ValidationError

    stop = threading.Event()
    # A completed app job can exit while its parent still holds stdin open.
    # Raw input avoids a daemon waiting on a BufferedReader shutdown lock.
    source = getattr(sys.stdin.buffer, "raw", sys.stdin.buffer)
    line = source.readline(16385)
    try:
        if len(line) > 16384:
            raise ValueError("Oversized request")
        if action == "backup-restore":
            from .local_recovery import RecoveryRequest

            model = RecoveryRequest
        elif action in {"backup-inventory", "backup-prune"}:
            model = BackupPruneRequest if action == "backup-prune" else BackupInventoryRequest
        else:
            model = BackupInspection if action == "backup-inspect" else BackupRequest
        request = model.model_validate_json(line)
    except (ValueError, ValidationError):
        raise state.LocalSetupError(
            "backup_options",
            "Check the selected file or folder, workspace and complete recovery key.",
        ) from None

    def control():
        while command := source.readline(1025):
            try:
                if len(command) > 1024 or json.loads(command) == {"action": "cancel"}:
                    stop.set()
                    return
            except ValueError:
                stop.set()
                return
        if request.watch_parent:
            stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    threading.Thread(target=control, name="mnemion-backup-control", daemon=True).start()
    try:
        if action == "backup-inspect":
            result = inspect_file(root, request, cancelled=stop.is_set)
            emit(
                {"event": "backup_inspection", "engine_version": __version__, "inspection": result}
            )
        elif action == "backup-restore":
            from .local_recovery import restore

            if runtime is None:
                raise state.LocalSetupError(
                    "missing_runtime", "The bundled database tools are required for recovery."
                )
            result = restore(root, runtime, request, cancelled=stop.is_set, emit=emit)
            emit({"event": "recovery", "engine_version": __version__, "receipt": result})
        elif action in {"backup-inventory", "backup-prune"}:
            result = inspect_inventory(
                root, request, prune=action == "backup-prune", cancelled=stop.is_set, emit=emit
            )
            emit(
                {
                    "event": "backup_retention" if action == "backup-prune" else "backup_inventory",
                    "engine_version": __version__,
                    "receipt": result,
                }
            )
        else:
            if runtime is None:
                raise state.LocalSetupError(
                    "missing_runtime", "The bundled database tools are required for local backups."
                )
            result = capture(
                root,
                runtime,
                request,
                ledger_only=action == "backup-ledger",
                cancelled=stop.is_set,
                emit=emit,
            )
            emit({"event": "backup", "engine_version": __version__, "receipt": result})
        return 0
    except (recovery.RecoveryCancelled, encryption.EncryptionCancelled):
        emit(
            {
                "event": "cancelled",
                "message": "The backup operation stopped. Verified recovery points remain available; any completed cleanup removals are recorded in the inventory.",
                "data_retained": True,
            }
        )
        return 2
    except encryption.EncryptionError as error:
        raise state.LocalSetupError("backup_verification", str(error)) from None
