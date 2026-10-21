"""Private desktop archive operations; workspace credentials never enter them."""

from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from . import backup_encryption, desktop_capture, local_state
from .connectors.capture_archive import CaptureArchiveError, export_archive, inspect_archive
from .service.models import Command


class Inspection(Command):
    operation: Literal["capture_inspect"]
    file: str = Field(min_length=1, max_length=4096)
    recovery_key: str = Field(min_length=50, max_length=50, repr=False)

    @field_validator("file")
    @classmethod
    def absolute_file(cls, value):
        if not Path(value).is_absolute() or "\x00" in value:
            raise ValueError("Choose an absolute capture archive path")
        return value

    @field_validator("recovery_key")
    @classmethod
    def valid_key(cls, value):
        backup_encryption.key_id(value)
        return value


class Export(Inspection):
    operation: Literal["capture_export"]
    id: UUID
    expected_revision: str = Field(min_length=1, max_length=128)
    inbox_key: str = Field(min_length=44, max_length=44, repr=False)
    confirm: Literal[True]

    @field_validator("confirm", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Confirm creation of the portable inbox archive")
        return value


def perform(root, value):
    from .desktop_sources import load

    request = (Export if value.get("operation") == "capture_export" else Inspection).model_validate(
        value
    )
    root = local_state.directory(root)
    staging = local_state.directory(root / "capture-backups")
    try:
        if isinstance(request, Inspection) and not isinstance(request, Export):
            return inspect_archive(Path(request.file), request.recovery_key, staging_root=staging)
        with local_state.lock(root):
            document = load(root)
            if document.revision != request.expected_revision:
                raise local_state.LocalSetupError(
                    "capture_settings_changed", "Refresh this source before creating its backup."
                )
            source = next((item for item in document.sources if item.id == request.id), None)
            if source is None or not source.custody or source.enabled:
                raise local_state.LocalSetupError(
                    "capture_backup_unavailable",
                    "Pause a retained source before creating its backup.",
                )
            with desktop_capture.opened(root, source, request.inbox_key) as (inbox, _):
                return export_archive(
                    inbox,
                    desktop_capture.key_bytes(request.inbox_key),
                    Path(request.file),
                    request.recovery_key,
                    staging_root=staging,
                    name=source.name,
                )
    except (CaptureArchiveError, backup_encryption.EncryptionError):
        raise local_state.LocalSetupError(
            "capture_backup_unavailable",
            "The capture archive could not be created or verified. Original evidence was retained.",
        ) from None
