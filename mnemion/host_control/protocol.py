"""Typed operations for an adopted host, without paths or shell commands."""

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
from typing import Annotated, Literal, Union
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from . import HostControlError

MAX_REQUEST = 16 * 1024
MAX_RESPONSE = 128 * 1024
ROLES = {
    "observer": frozenset({"host.status", "operations.get", "operations.list"}),
    "operator": frozenset(
        {
            "host.status",
            "operations.get",
            "operations.list",
            "service.start",
            "service.stop",
            "upgrade.plan",
            "upgrade.apply",
        }
    ),
}
ROLES["custodian"] = ROLES["operator"] | {
    "operators.list",
    "operators.grant",
    "operators.revoke",
    "operations.resolve",
}


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def fingerprint(public_key: str) -> str:
    try:
        parts = public_key.split()
        if len(parts) != 2 or parts[0] != "ssh-ed25519" or len(public_key) > 128:
            raise ValueError
        key = serialization.load_ssh_public_key(public_key.encode("ascii"))
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError
        normalized = key.public_bytes(
            serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH
        ).decode("ascii")
        if normalized != public_key:
            raise ValueError
        raw = base64.b64decode(parts[1], validate=True)
        return "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
    except (ValueError, TypeError, UnicodeError):
        raise HostControlError(
            "invalid_operator_key", "Use one Ed25519 public key without options or a comment."
        ) from None


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Operator(Document):
    name: str = Field(min_length=1, max_length=80)
    public_key: str = Field(max_length=128)
    role: Literal["observer", "operator", "custodian"]
    expires_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def name_text(cls, value):
        if value != value.strip() or not value.isprintable():
            raise ValueError("Use a short printable operator name.")
        return value

    @field_validator("public_key")
    @classmethod
    def key_text(cls, value):
        fingerprint(value)
        return value

    @field_validator("expires_at")
    @classmethod
    def expiry(cls, value):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("Operator expiry needs an explicit timezone.")
            return value.astimezone(timezone.utc)
        return value


class Request(Document):
    protocol: Literal[1]
    host_id: UUID
    request_id: UUID

    @field_validator("protocol", mode="before")
    @classmethod
    def protocol_number(cls, value):
        if type(value) is not int:
            raise ValueError("Use an integer protocol version.")
        return value


class Timed(Request):
    issued_at: datetime
    valid_until: datetime

    @field_validator("issued_at", "valid_until")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("Host operation times need an explicit timezone.")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def bounded_lifetime(self):
        if not timedelta() < self.valid_until - self.issued_at <= timedelta(hours=1):
            raise ValueError("Approve host work for at most one hour.")
        return self

    def current(self, now: datetime):
        if self.issued_at > now + timedelta(minutes=5) or self.valid_until <= now:
            raise HostControlError(
                "request_expired",
                "This approval expired or the device clock differs. Inspect the old operation before creating new work.",
            )


class Approved(Timed):
    approve_service_interruption: Literal[True]

    @field_validator("approve_service_interruption", mode="before")
    @classmethod
    def approval(cls, value):
        if value is not True:
            raise ValueError("Explicit approval is required.")
        return value


class Status(Request):
    action: Literal["host.status"]


class Service(Approved):
    action: Literal["service.start", "service.stop"]


class Plan(Timed):
    action: Literal["upgrade.plan"]


class Apply(Approved):
    action: Literal["upgrade.apply"]
    plan_id: UUID
    plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Operation(Request):
    action: Literal["operations.get"]
    operation_id: UUID


class Resolve(Timed):
    action: Literal["operations.resolve"]
    operation_id: UUID
    approve_current_state: Literal[True]
    settle: Literal["observe", "stop"] = "observe"
    approve_service_interruption: bool = Field(default=False, strict=True)

    @field_validator("approve_current_state", mode="before")
    @classmethod
    def explicit_approval(cls, value):
        if value is not True:
            raise ValueError("Explicit approval of the observed current state is required.")
        return value

    @model_validator(mode="after")
    def settling_approval(self):
        if self.settle == "stop" and self.approve_service_interruption is not True:
            raise ValueError(
                "Stopping an uncertain service requires explicit interruption approval."
            )
        return self


class ListOperators(Request):
    action: Literal["operators.list"]
    limit: int = Field(default=50, strict=True, ge=1, le=100)
    offset: int = Field(default=0, strict=True, ge=0, le=8192)


class ListOperations(Request):
    action: Literal["operations.list"]
    limit: int = Field(default=50, strict=True, ge=1, le=100)
    offset: int = Field(default=0, strict=True, ge=0, le=8192)


class Grant(Timed):
    action: Literal["operators.grant"]
    expected_revision: int = Field(strict=True, ge=1, le=2**53 - 1)
    operator: Operator


class Revoke(Timed):
    action: Literal["operators.revoke"]
    expected_revision: int = Field(strict=True, ge=1, le=2**53 - 1)
    operator_id: UUID


REQUEST = TypeAdapter(
    Annotated[
        Union[
            Status,
            Service,
            Plan,
            Apply,
            Operation,
            Resolve,
            ListOperators,
            ListOperations,
            Grant,
            Revoke,
        ],
        Field(discriminator="action"),
    ]
)


def parse(raw: bytes):
    if not raw or len(raw) > MAX_REQUEST:
        raise HostControlError("invalid_request", "Host requests must fit within 16 KiB.")
    try:
        return REQUEST.validate_json(raw)
    except ValueError:
        raise HostControlError(
            "invalid_request", "Use the published host-operation schema and explicit approval."
        ) from None
