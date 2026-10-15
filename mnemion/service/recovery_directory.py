"""Bounded organization recovery references, never credentials or host commands."""

from datetime import datetime, timedelta, timezone
import json
import re
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import Depends
from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from .contracts import ResponseModel
from .db import Database, Identity, require_administrator
from .errors import ServiceError
from .models import Command, json_value
from .repository import audit

Label = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=120, pattern=r"^[^\x00-\x1f\x7f]+$"
    ),
]
MAX_DIRECTORY_BYTES = 6144


def reference_url(value: str | None, *, workspace: bool = False) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    loopback = workspace and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        not parsed.hostname
        or parsed.scheme not in ({"http", "https"} if loopback else {"https"})
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "\\" in value
        or re.search(r"[\s\x00-\x1f\x7f]", value)
    ):
        raise ValueError("Use an HTTPS entry address without credentials, query or fragment")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("Use a valid entry-address port")
    return value.rstrip("/")


class RecoveryHost(Command):
    id: UUID = Field(default_factory=uuid4)
    name: Label
    role: Literal["primary", "recovery", "ingestion"] = "primary"
    platform: Literal["windows", "macos", "linux", "managed", "other"] = "other"
    workspace_url: str | None = Field(default=None, max_length=2048)
    operator_url: str | None = Field(default=None, max_length=2048)
    operator: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=600)

    @field_validator("workspace_url")
    @classmethod
    def workspace_address(cls, value):
        return reference_url(value, workspace=True)

    @field_validator("operator_url")
    @classmethod
    def operator_address(cls, value):
        return reference_url(value)


class RecoveryMaterial(Command):
    id: UUID = Field(default_factory=uuid4)
    name: Label
    kind: Literal["database_backup", "recovery_ledger", "source_mirror"]
    location: str = Field(min_length=1, max_length=1024)
    access_url: str | None = Field(default=None, max_length=2048)
    reported_verified_at: AwareDatetime | None = Field(
        default=None, description="Administrator-reported observation, not automatic verification."
    )
    notes: str = Field(default="", max_length=600)

    @field_validator("access_url")
    @classmethod
    def access_address(cls, value):
        return reference_url(value)


class RecoveryContact(Command):
    id: UUID = Field(default_factory=uuid4)
    name: Label
    channel: str = Field(min_length=1, max_length=300)
    responsibility: str = Field(default="", max_length=300)


class RecoveryDirectory(Command):
    instructions: str = Field(default="", max_length=2000)
    independent_url: str | None = Field(default=None, max_length=2048)
    hosts: list[RecoveryHost] = Field(default_factory=list, max_length=16)
    materials: list[RecoveryMaterial] = Field(default_factory=list, max_length=16)
    contacts: list[RecoveryContact] = Field(default_factory=list, max_length=16)

    @field_validator("independent_url")
    @classmethod
    def independent_address(cls, value):
        return reference_url(value)

    @model_validator(mode="after")
    def bounded_references(self):
        identifiers = [item.id for item in [*self.hosts, *self.materials, *self.contacts]]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Recovery entries must have different identifiers")
        document = self.model_dump(mode="json")

        def readable(value):
            if isinstance(value, str) and re.search(r"[\x00-\x08\x0b-\x1f\x7f]", value):
                raise ValueError("Recovery references must contain readable text")
            if isinstance(value, dict):
                for item in value.values():
                    readable(item)
            elif isinstance(value, list):
                for item in value:
                    readable(item)

        readable(document)
        if any(not item.location.strip() for item in self.materials) or any(
            not item.channel.strip() for item in self.contacts
        ):
            raise ValueError("Recovery locations and contact channels must contain text")
        text = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
        if len(text.encode("utf-8")) > MAX_DIRECTORY_BYTES:
            raise ValueError("Keep the recovery directory within 6 KiB; link to longer runbooks")
        if re.search(
            r"\bmnm_[A-Za-z0-9_-]{20,}|\bBearer\s+\S+|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bpostgres(?:ql)?://",
            text,
            re.IGNORECASE,
        ):
            raise ValueError("Store recovery references here, never credentials or private keys")
        return self


class RecoveryDirectoryInput(Command):
    expected_revision: int = Field(ge=0, le=2147483646, strict=True)
    directory: RecoveryDirectory

    @model_validator(mode="after")
    def reported_dates(self):
        # Validate new reports without making old records unreadable after a
        # host clock correction.
        latest = datetime.now(timezone.utc) + timedelta(minutes=5)
        if any(
            item.reported_verified_at and item.reported_verified_at > latest
            for item in self.directory.materials
        ):
            raise ValueError("A reported verification must describe a past observation")
        return self


class RecoveryDirectoryRecord(ResponseModel):
    tenant_id: UUID
    revision: int = Field(ge=0, le=2147483647, strict=True)
    updated_at: AwareDatetime | None
    updated_by: UUID | None
    directory: RecoveryDirectory


class RecoveryDirectoryService:
    def __init__(self, database: Database):
        self.db = database

    @staticmethod
    def _record(conn, identity: Identity) -> dict:
        row = conn.execute(
            "SELECT tenant_id,revision,document AS directory,updated_at,updated_by "
            "FROM mnemion.recovery_directories WHERE tenant_id=%s",
            (identity.tenant_id,),
        ).fetchone()
        return (
            json_value(row)
            if row
            else {
                "tenant_id": str(identity.tenant_id),
                "revision": 0,
                "updated_at": None,
                "updated_by": None,
                "directory": RecoveryDirectory().model_dump(mode="json"),
            }
        )

    def get(self, identity: Identity) -> dict:
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            return self._record(conn, identity)

    def update(self, identity: Identity, command: RecoveryDirectoryInput) -> dict:
        # Share the revocation lock and recheck authority after waiting for it.
        with self.db.administration_transaction(identity) as conn:
            require_administrator(conn)
            current = self._record(conn, identity)
            if current["revision"] != command.expected_revision:
                raise ServiceError(
                    409,
                    "recovery_directory_changed",
                    "Another administrator changed the recovery directory. Reload and review before saving.",
                )
            value = command.directory.model_dump_json()
            revision = command.expected_revision + 1
            conn.execute(
                """INSERT INTO mnemion.recovery_directories
                   (tenant_id,revision,document,updated_by) VALUES (%s,%s,%s::jsonb,%s)
                   ON CONFLICT(tenant_id) DO UPDATE SET revision=excluded.revision,
                     document=excluded.document,updated_by=excluded.updated_by,
                     updated_at=clock_timestamp()""",
                (identity.tenant_id, revision, value, identity.principal_id),
            )
            audit(
                conn,
                identity,
                "recovery_directory.updated",
                identity.tenant_id,
                details={
                    "revision": revision,
                    "hosts": len(command.directory.hosts),
                    "materials": len(command.directory.materials),
                    "contacts": len(command.directory.contacts),
                },
            )
            return self._record(conn, identity)


def attach_recovery_directory(app, database, authenticated):
    service = RecoveryDirectoryService(database)
    Auth = Annotated[Identity, Depends(authenticated)]

    @app.get("/v1/recovery-directory", tags=["Recovery"], response_model=RecoveryDirectoryRecord)
    def directory(identity: Auth):
        """Read administrator-only recovery references; this does not contact or control a host."""
        return service.get(identity)

    @app.put("/v1/recovery-directory", tags=["Recovery"], response_model=RecoveryDirectoryRecord)
    def update_directory(command: RecoveryDirectoryInput, identity: Auth):
        """Update the reviewed revision with current admin authority; entries grant no host access."""
        return service.update(identity, command)
