"""Credential transport commands; passwords and encrypted files stay out of repr."""

from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, field_validator
from zxcvbn import zxcvbn

from .contracts import ResponseModel
from .models import Command
from .vault_models import VaultEntry, VaultExport


class KeepassPreviewInput(Command):
    file: SecretStr = Field(min_length=88, max_length=1333336)
    password: SecretStr | None = Field(default=None, max_length=1024)
    key_file: SecretStr | None = Field(default=None, max_length=87384)
    namespace: str = Field(default="keepass", pattern=r"^[A-Za-z0-9_-]{1,24}$")
    mask_names: bool = Field(default=True, strict=True)


class KeepassImportInput(KeepassPreviewInput):
    expected_plan: str = Field(pattern=r"^[a-f0-9]{64}$")
    import_current_values: Literal[True]

    @field_validator("import_current_values", mode="before")
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError("Explicit approval of the current-field import is required")
        return value


class KeepassExportInput(Command):
    entry_ids: list[UUID] = Field(min_length=1, max_length=100)
    password: SecretStr = Field(min_length=12, max_length=1024)

    @field_validator("entry_ids")
    @classmethod
    def distinct_entries(cls, values):
        return VaultExport.distinct_entries(values)

    @field_validator("password")
    @classmethod
    def strong_export_password(cls, value):
        if zxcvbn(value.get_secret_value()[:72])["score"] < 3:
            raise ValueError(
                "Choose a longer, less predictable export passphrase or use Generate password"
            )
        return value


class KeepassOmissions(ResponseModel):
    history_entries: int
    attachments: int
    recycled_entries: int


class KeepassPreview(ResponseModel):
    plan: str
    entries: int
    credentials: int
    empty_fields: int
    names: list[str]
    mask_names: bool
    omitted: KeepassOmissions
    name_conflicts: int
    can_import: bool
    already_imported: bool


class KeepassImported(ResponseModel):
    items: list[VaultEntry]
    already_imported: bool


class KeepassExported(ResponseModel):
    format: Literal["kdbx"] = "kdbx"
    version: Literal["4.1"] = "4.1"
    file: str = Field(repr=False)
    sha256: str
    credentials: int
    entries: int
