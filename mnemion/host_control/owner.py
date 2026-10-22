"""Local OS-owner recovery; deliberately absent from the remote request union."""

from datetime import datetime, timezone
import hashlib
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from . import HostControlError
from .installation import settings
from .protocol import Operator, Timed, canonical, fingerprint, timestamp
from .store import MAX_OPERATORS, MAX_OPERATOR_RECORDS, MAX_OPERATIONS, Store, _audit, identifier


class OwnerRecovery(Timed):
    action: Literal["owner.custodian"]
    expected_revision: int = Field(strict=True, ge=1, le=2**53 - 1)
    operator: Operator
    retire_operator_ids: list[UUID] = Field(default_factory=list, max_length=128)
    approve_authority_recovery: Literal[True]

    @field_validator("approve_authority_recovery", mode="before")
    @classmethod
    def explicit(cls, value):
        if value is not True:
            raise ValueError("Explicit local authority recovery approval is required.")
        return value

    @model_validator(mode="after")
    def permanent_custodian(self):
        if self.operator.role != "custodian" or self.operator.expires_at is not None:
            raise ValueError("Restore a permanent custodian using a fresh device key.")
        if len(set(self.retire_operator_ids)) != len(self.retire_operator_ids):
            raise ValueError("List each retired operator once.")
        return self


def status(root):
    root, value = settings(root)
    store = Store(root / "authority")
    with store.transaction() as conn:
        host = conn.execute("SELECT id,revision FROM host WHERE singleton=1").fetchone()
        operators = conn.execute(
            "SELECT id,name,fingerprint,role,expires_at,revoked_at FROM operators ORDER BY created_at,id"
        ).fetchall()
        return {
            "host_id": host["id"],
            "revision": host["revision"],
            "operators": [dict(row) for row in operators],
            "server_fingerprint": value["connection"]["host_key_fingerprint"],
            "scope": "owning_os_account",
        }


def recover(root, request):
    root, value = settings(root)
    store = Store(root / "authority")
    digest = hashlib.sha256(canonical(request.model_dump(mode="json"))).hexdigest()
    with store.transaction() as conn:
        host = conn.execute("SELECT * FROM host WHERE singleton=1").fetchone()
        if host["id"] != str(request.host_id):
            raise HostControlError("wrong_host", "Review this host's local authority first.")
        previous = conn.execute(
            "SELECT * FROM operations WHERE id=?", (str(request.request_id),)
        ).fetchone()
        if previous is not None:
            if previous["action"] != "owner.custodian" or previous["request_sha256"] != digest:
                raise HostControlError(
                    "operation_conflict", "This identity already names different work."
                )
            import json

            return json.loads(previous["result"])
        request.current(datetime.now(timezone.utc))
        if host["revision"] != request.expected_revision:
            raise HostControlError(
                "authority_changed", "Read current local host authority before recovery."
            )
        Store._space(conn, MAX_OPERATIONS)
        if conn.execute("SELECT count(*) FROM operators").fetchone()[0] >= MAX_OPERATOR_RECORDS:
            raise HostControlError(
                "operator_limit", "Inspect the full operator history before adding a recovery key."
            )
        key_id = fingerprint(request.operator.public_key)
        if conn.execute("SELECT 1 FROM operators WHERE fingerprint=?", (key_id,)).fetchone():
            raise HostControlError(
                "operator_exists", "Recover with a new device key; existing grants were retained."
            )
        at = timestamp()
        for retired in request.retire_operator_ids:
            operator_id = identifier(retired)
            if (
                conn.execute("SELECT 1 FROM operators WHERE id=?", (operator_id,)).fetchone()
                is None
            ):
                raise HostControlError(
                    "operator_not_found", "Review each operator selected for retirement."
                )
            conn.execute(
                "UPDATE operators SET revoked_at=?,revision=revision+1 WHERE id=? AND revoked_at IS NULL",
                (at, operator_id),
            )
            conn.execute(
                "UPDATE operations SET phase='cancelled',updated_at=?,error='operator_retired' WHERE actor=? AND phase='queued'",
                (at, operator_id),
            )
            _audit(conn, None, "owner_retired_operator", operator_id)
        active = conn.execute(
            "SELECT count(*) FROM operators WHERE revoked_at IS NULL AND (expires_at IS NULL OR expires_at>?)",
            (at,),
        ).fetchone()[0]
        if active >= MAX_OPERATORS:
            raise HostControlError(
                "operator_limit", "Review an unused operator for retirement before recovery."
            )
        operator_id = str(uuid4())
        Store._insert_operator(conn, operator_id, request.operator)
        conn.execute("UPDATE host SET revision=revision+1 WHERE singleton=1")
        _audit(conn, None, "owner_recovered_custodian", operator_id)
        result = {
            "recovered": True,
            "revision": host["revision"] + 1,
            "operator_id": operator_id,
            "retired_operator_ids": [str(value) for value in request.retire_operator_ids],
            "connection": {
                **value["connection"],
                "operator_id": operator_id,
                "operator_key_fingerprint": key_id,
            },
        }
        return Store._receipt(conn, operator_id, request, result)
