"""Explicit secret inputs and metadata-only listings; never generic memory models."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, ConfigDict, Field, SecretStr, StringConstraints, field_validator

from .contracts import ResponseModel
from .models import Command
from .vault_crypto import decode_key

VaultName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=120, pattern=r"^[^\x00-\x1f\x7f]+$"
    ),
]


class VaultPut(Command):
    expected_version: int = Field(ge=0, le=2147483646, strict=True)
    name: VaultName
    value: SecretStr = Field(min_length=1, max_length=65536)


class VaultResponse(ResponseModel):
    model_config = ConfigDict(extra="forbid")


class VaultPermissions(VaultResponse):
    read: bool
    write: bool
    manage: bool


class VaultEntry(VaultResponse):
    id: UUID
    name: str
    version: int
    access_version: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    permissions: VaultPermissions


class VaultValue(VaultEntry):
    value: str = Field(repr=False)


class VaultStatus(VaultResponse):
    configured: bool
    enabled: bool
    mcp_enabled: bool
    available: bool
    error_code: str | None
    key_id: str | None
    required_key_ids: list[str]
    current_key_id: UUID
    current_person_id: UUID | None
    administrator: bool


class VaultGrant(Command):
    expected_access_version: int = Field(ge=1, le=2147483646, strict=True)
    subject_kind: Literal["person", "key"]
    subject_id: UUID
    read: bool = False
    write: bool = False
    remove: bool = False


class VaultGrantRecord(VaultResponse):
    subject_kind: Literal["person", "key"]
    subject_id: UUID
    name: str
    read: bool
    write: bool
    active: bool


class VaultGrants(VaultResponse):
    entry_id: UUID
    access_version: int
    items: list[VaultGrantRecord]


class VaultDelete(Command):
    expected_version: int = Field(ge=1, le=2147483646, strict=True)


class VaultDeleted(VaultResponse):
    id: UUID
    deleted: Literal[True] = True


class VaultEnvelope(Command):
    format: Literal["mnemion-vault-export"] = "mnemion-vault-export"
    version: Literal[1] = 1
    key_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    nonce: str = Field(min_length=16, max_length=16)
    ciphertext: str = Field(min_length=24, max_length=1333360)


class VaultRecoveryKey(Command):
    recovery_key: SecretStr

    @field_validator("recovery_key")
    @classmethod
    def generated_key(cls, value):
        decode_key(value.get_secret_value())
        return value


class VaultExport(VaultRecoveryKey):
    entry_ids: list[UUID] = Field(min_length=1, max_length=100)

    @field_validator("entry_ids")
    @classmethod
    def distinct_entries(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("Choose each credential only once")
        return values


class VaultImport(VaultRecoveryKey):
    archive: VaultEnvelope


class VaultArchiveItem(Command):
    name: VaultName
    value: SecretStr = Field(min_length=1, max_length=65536)


class VaultArchive(Command):
    format: Literal["mnemion-vault-contents"]
    version: Literal[1]
    source_tenant_id: UUID
    exported_at: AwareDatetime
    entries: list[VaultArchiveItem] = Field(min_length=1, max_length=100)


class VaultAuditEvent(VaultResponse):
    id: UUID
    principal_id: UUID
    key_id: UUID
    entry_id: UUID | None
    action: str
    outcome: str
    occurred_at: AwareDatetime
