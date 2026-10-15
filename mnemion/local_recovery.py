"""Restore authenticated native backups into a new, independently owned host."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Literal
from uuid import UUID
import zipfile

import psycopg
from pydantic import Field, SecretStr, field_validator

from . import backup_encryption as encryption, local_state as state
from .archives import MANIFEST, MAX_ARCHIVE_BYTES
from .local_backup import BackupInspection, LocalBackupContext, _control, _now
from .local_database import LocalDatabase, prepare_credentials
from .service import recovery


class RecoveryRequest(BackupInspection):
    ledger_source: str = Field(min_length=1, max_length=4096)
    ledger_key: SecretStr | None = None
    destination: str = Field(min_length=1, max_length=4096)
    snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    ledger_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    primary_tenant_id: UUID
    trusted_backup_confirmed: Literal[True]

    @field_validator("ledger_source", "destination")
    @classmethod
    def path(cls, value):
        return BackupInspection.file(value)

    @field_validator("ledger_key")
    @classmethod
    def ledger_recovery_key(cls, value):
        if value is not None:
            encryption.key_id(value.get_secret_value())
        return value


def _preview(path: Path) -> dict:
    # The envelope has already authenticated these bytes. This bounded preview
    # supplies setup hints only; canonical restore verifies the full archive
    # inventory and schema before creating any database.
    with zipfile.ZipFile(path) as archive:
        if archive.getinfo(MANIFEST).file_size > 1024 * 1024:
            raise state.LocalSetupError("backup_format", "The backup setup inventory is too large.")
        value = json.loads(archive.read(MANIFEST))
    if not isinstance(value, dict) or value.get("format") != recovery.BACKUP_FORMAT:
        raise state.LocalSetupError("backup_format", "Choose a complete database snapshot.")
    return value


def restore(
    root: Path,
    runtime: Path,
    request: RecoveryRequest,
    *,
    cancelled=None,
    emit=None,
) -> dict:
    """Keep existing data untouched; return no recovered credentials over IPC."""
    from .local_workspace import SetupOptions, initialize

    control = _control(root)
    target = Path(request.destination)
    if target.resolve().is_relative_to(root.resolve()):
        raise state.LocalSetupError(
            "recovery_destination", "Choose a new data folder outside the current workspace."
        )
    if not target.parent.is_dir():
        raise state.LocalSetupError("recovery_destination", "Choose an existing parent folder.")
    if target.exists() or target.is_symlink():
        raise state.LocalSetupError(
            "recovery_destination",
            "The recovery data folder must be new. Existing data was retained.",
        )

    def progress(stage, message):
        if emit:
            emit({"event": "backup_progress", "stage": stage, "message": message})

    from .local_backup import _decrypt_space

    _decrypt_space(control, request.source, request.ledger_source)
    with (
        state.lock(control),
        state.temporary_directory(prefix="restore-", dir=control) as scratch,
    ):
        progress("authenticating", "Authenticating the snapshot and the selected access ledger…")
        snapshot = encryption.decrypt_file(
            Path(request.source),
            scratch / "snapshot",
            request.recovery_key.get_secret_value(),
            expected_kind="snapshot",
            cancelled=cancelled,
        )
        ledger = encryption.decrypt_file(
            Path(request.ledger_source),
            scratch / "ledger",
            (request.ledger_key or request.recovery_key).get_secret_value(),
            expected_kind="ledger",
            cancelled=cancelled,
        )
        if (
            snapshot.encrypted_sha256 != request.snapshot_sha256
            or ledger.encrypted_sha256 != request.ledger_sha256
        ):
            raise state.LocalSetupError(
                "backup_changed", "A selected recovery file changed. Inspect both files again."
            )
        manifest = _preview(scratch / "snapshot")
        if str(request.primary_tenant_id) not in manifest.get("tenant_ids", []):
            raise state.LocalSetupError(
                "workspace_identity", "The selected organization is not in this backup."
            )
        context = manifest.get("context", {}).get("local_workspace")
        hints = (
            LocalBackupContext.model_validate_json(json.dumps(context))
            if context is not None
            else None
        )
        sizes = [entry.get("size") for entry in manifest.get("files", {}).values()]
        if not sizes or any(
            type(size) is not int or not 0 <= size <= MAX_ARCHIVE_BYTES for size in sizes
        ):
            raise state.LocalSetupError("backup_format", "The backup file inventory is invalid.")
        # A dump's compressed size is not its eventual database size. Reserve
        # room conservatively and still treat subsequent disk errors as failures.
        required = max(2 * 1024**3, sum(sizes) * 4)
        if shutil.disk_usage(target.parent).free < required:
            raise state.LocalSetupError(
                "disk_budget", "Free more disk space before restoring this database snapshot."
            )
        recovery._cancel(cancelled)
        # Exclusive creation is the final check, including concurrent callers.
        state.directory(target, exist_ok=False)
        with state.lock(target):
            settings = initialize(
                target,
                SetupOptions(
                    workspace_name=(
                        (hints.workspace_name if hints else "Workspace")[:188] + " (recovered)"
                    ),
                    owner_name=hints.owner_name if hints else "Recovery administrator",
                    embedding_profile=hints.embedding_profile if hints else "e5-small",
                    threads=hints.threads if hints else 2,
                ),
            )
            credentials = prepare_credentials(target)
            record = {
                "format": 1,
                "state": "restoring",
                "started_at": _now(),
                "workspace_id": settings["workspace_id"],
                "source_workspace_id": str(hints.workspace_id) if hints else None,
                "backup_id": manifest["backup_id"],
                "snapshot_sha256": snapshot.encrypted_sha256,
                "ledger_sha256": ledger.encrypted_sha256,
                "data_directory": str(target),
            }
            state.write(target / "recovery.json", record, replace=False)
            database = LocalDatabase(target, runtime, settings, credentials)
            try:
                progress("database", "Creating a separate private database for recovery…")
                database.start()
                recovery._cancel(cancelled)
                progress(
                    "restoring", "Verifying data and reconciling current deletions and access…"
                )
                restored = recovery.restore_backup(
                    database.dsn(database="postgres"),
                    scratch / "snapshot",
                    database_name="mnemion",
                    deletion_ledger=scratch / "ledger",
                    credentials_output=target / "recovery-administrators.json",
                    pg_bin=runtime / "bin",
                    temporary_directory=scratch,
                    cancelled=cancelled,
                )
                administrators = state.read(target / "recovery-administrators.json")[
                    "organizations"
                ]
                primary = next(
                    value
                    for value in administrators
                    if value["tenant_id"] == str(request.primary_tenant_id)
                )
                credentials.update(
                    {
                        key: primary[key]
                        for key in ("tenant_id", "principal_id", "key_id", "api_key")
                    }
                )
                # Use a separate private setup space. This preserves the current
                # ledger's grants on every recovered space and avoids making an
                # old remote embedding provider part of native startup checks.
                with (
                    psycopg.connect(database.dsn()) as connection,
                    recovery._cancel_queries(connection, cancelled),
                ):
                    connection.execute(
                        "INSERT INTO mnemion.spaces(tenant_id,id,name) VALUES (%s,%s,'Recovery checks')",
                        (credentials["tenant_id"], credentials["space_id"]),
                    )
                    connection.execute(
                        "INSERT INTO mnemion.space_grants(tenant_id,space_id,principal_id,role) VALUES (%s,%s,%s,'administrator')",
                        (
                            credentials["tenant_id"],
                            credentials["space_id"],
                            credentials["principal_id"],
                        ),
                    )
                state.write(target / "credentials.json", credentials)
                recovery._cancel(cancelled)
                record.update(
                    state="restored",
                    restored_at=_now(),
                    tenant_id=credentials["tenant_id"],
                    tenant_count=len(administrators),
                    keys_rotated=True,
                    verified_tables=restored["verified_tables"],
                    deletions_reconciled=restored["deletions_reconciled"],
                    ledger_at=restored["ledger_at"],
                    external_connections_require_review=True,
                )
            except BaseException:
                # The isolated copy is retained for diagnosis. No selection or
                # native activation is published on an incomplete operation.
                state.write(target / "recovery.json", {**record, "state": "incomplete"})
                raise
            finally:
                database.stop()
            state.write(target / "recovery.json", record)
            progress("complete", "Recovery copy verified. Review it before switching workspaces.")
            return record
