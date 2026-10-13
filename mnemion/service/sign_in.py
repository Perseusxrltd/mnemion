"""Individual accounts and device sessions without changing memory authority.

Passwords, invitations and refresh credentials are accepted through private
request bodies. Only digests enter PostgreSQL; public responses use explicit
allowlists and never serialize internal authentication rows.
"""

from __future__ import annotations

import re
import secrets
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from pydantic import Field, SecretStr, field_validator

from .db import Database, Identity, new_token, require_administrator, token_hash
from .errors import ServiceError, not_found
from .models import Command, json_value
from .passwords import hash_password, screen_password, verify_password


def normalize_username(value: str) -> str:
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._@+\-]{2,127}", value):
        raise ValueError("Use 3–128 letters, numbers, dots, dashes, +, _ or @ for the login name")
    return value


def device_label(value: str) -> str:
    if not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Choose a device name without control characters")
    return value.strip()


class PasswordInput(Command):
    username: str = Field(min_length=3, max_length=128)
    password: SecretStr = Field(min_length=15, max_length=128)
    current_password: SecretStr | None = Field(default=None, max_length=128)

    _username = field_validator("username")(normalize_username)


class SignInInput(Command):
    workspace_id: UUID
    username: str = Field(min_length=3, max_length=128)
    password: SecretStr = Field(min_length=1, max_length=128)
    device_name: str = Field(min_length=1, max_length=100)
    transport: Literal["native", "browser"]
    remember: bool = False

    _username = field_validator("username")(normalize_username)

    _device_name = field_validator("device_name")(device_label)


class InvitationInput(Command):
    principal_id: UUID
    purpose: Literal["enroll", "reset"] = "enroll"
    expires_in_seconds: int = Field(default=86400, ge=60, le=604800)


class InvitationAcceptInput(Command):
    invitation: SecretStr = Field(min_length=40, max_length=200)
    username: str = Field(min_length=3, max_length=128)
    password: SecretStr = Field(min_length=15, max_length=128)
    device_name: str = Field(min_length=1, max_length=100)
    transport: Literal["native", "browser"]
    remember: bool = False

    _username = field_validator("username")(normalize_username)
    _device_name = field_validator("device_name")(device_label)


def _unauthorized():
    return ServiceError(
        401,
        "sign_in_failed",
        "Sign-in could not be completed. Check your login or request a new invitation.",
    )


def _secret(prefix: str) -> tuple[str, str]:
    value = prefix + secrets.token_urlsafe(32)
    return value, token_hash(value)


def _digest(value: str, prefix: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        re.escape(prefix) + r"[A-Za-z0-9_-]{43}", value
    ):
        raise _unauthorized()
    return token_hash(value)


def _session_result(row, access: str, refresh: str, csrf: str | None) -> dict:
    """The HTTP layer removes refresh credentials from browser JSON responses."""
    return {
        "session_id": str(row.get("session_id", row.get("id"))),
        "tenant_id": str(row["tenant_id"]),
        "principal_id": str(row["principal_id"]),
        "access_token": access,
        "refresh_token": refresh,
        "csrf_token": csrf,
        "access_expires_at": json_value(row["access_expires_at"]),
        "expires_at": json_value(row["expires_at"]),
        "rotation": row.get("rotation", row.get("rotations", 0)),
    }


class SignInService:
    def __init__(self, database: Database):
        self.db = database

    def _admit(self, subject: str) -> None:
        if self.db.worker:
            raise _unauthorized()
        # Commit admission before expensive hashing; rejected credentials still
        # count even when the later account/session transaction rolls back.
        with self.db.pool.connection() as conn:
            admitted = conn.execute(
                "SELECT mnemion.admit_sign_in(%s) AS allowed", (token_hash(subject),)
            ).fetchone()["allowed"]
        if not admitted:
            raise ServiceError(
                429, "sign_in_throttled", "Too many sign-in attempts. Wait before trying again."
            )

    def _lookup(self, workspace: UUID, login: str):
        with self.db.pool.connection() as conn:
            return conn.execute(
                "SELECT * FROM mnemion.password_login_lookup(%s,%s)", (workspace, login)
            ).fetchone()

    def account(self, identity: Identity):
        with self.db.transaction(identity) as conn:
            person = conn.execute(
                "SELECT kind FROM mnemion.principals WHERE tenant_id=%s AND id=%s",
                (identity.tenant_id, identity.principal_id),
            ).fetchone()
            row = conn.execute(
                """SELECT username,reset_required,changed_at FROM mnemion.password_accounts
                   WHERE tenant_id=%s AND principal_id=%s""",
                (identity.tenant_id, identity.principal_id),
            ).fetchone()
            return {"account": json_value(row), "can_use_password": person["kind"] == "human"}

    def set_password(self, identity: Identity, command: PasswordInput):
        self._admit(f"password:{identity.tenant_id}:{identity.principal_id}")
        current = self.account(identity)["account"]
        previous = self._lookup(identity.tenant_id, current["username"]) if current else None
        old_password = (
            command.current_password.get_secret_value() if command.current_password else ""
        )
        if current and not verify_password(
            old_password, previous["password_hash"] if previous else None
        ):
            raise _unauthorized()
        password = command.password.get_secret_value()
        screen_password(password, context=[command.username])
        encoded = hash_password(password)
        try:
            with self.db.administration_transaction(identity) as conn:
                changed = conn.execute(
                    "SELECT mnemion.set_password_account(%s,%s,%s) AS changed",
                    (command.username, encoded, previous["password_hash"] if previous else None),
                ).fetchone()["changed"]
        except psycopg.errors.UniqueViolation:
            raise ServiceError(409, "login_unavailable", "Choose another login name.") from None
        if not changed:
            raise _unauthorized()
        return {"changed": True, "sessions_revoked": True}

    def _issue(self, conn, row, device_name: str, transport: str):
        access, access_digest = _secret("mnm_s_")
        refresh, refresh_digest = _secret("mnm_r_")
        csrf, csrf_digest = _secret("mnm_c_") if transport == "browser" else (None, None)
        _, anchor_hash = new_token()
        session = conn.execute(
            "SELECT * FROM mnemion.issue_password_session(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                row["tenant_id"],
                row["principal_id"],
                row["password_hash"],
                row["account_version"],
                uuid4(),
                uuid4(),
                anchor_hash,
                access_digest,
                refresh_digest,
                csrf_digest,
                device_name,
                transport,
            ),
        ).fetchone()
        if session is None:
            raise ServiceError(
                409,
                "session_unavailable",
                "The account changed or has 32 active sessions. Sign in again or ask an administrator to revoke an old session.",
            )
        return _session_result(session, access, refresh, csrf)

    def sign_in(self, command: SignInInput):
        self._admit(f"login:{command.workspace_id}:{command.username}")
        row = self._lookup(command.workspace_id, command.username)
        accepted = verify_password(
            command.password.get_secret_value(), row["password_hash"] if row else None
        )
        if not accepted or row is None:
            raise _unauthorized()
        with self.db.pool.connection() as conn:
            return self._issue(conn, row, command.device_name, command.transport)

    def refresh(
        self,
        refresh: str,
        *,
        transport: str,
        csrf: str | None = None,
        workspace: UUID | None = None,
        session: UUID | None = None,
    ):
        old_digest = _digest(refresh, "mnm_r_")
        csrf_digest = _digest(csrf, "mnm_c_") if csrf is not None else None
        access, access_digest = _secret("mnm_s_")
        new_refresh, refresh_digest = _secret("mnm_r_")
        with self.db.pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM mnemion.rotate_password_session(%s,%s,%s,%s,%s,%s,%s)",
                (
                    old_digest,
                    access_digest,
                    refresh_digest,
                    csrf_digest,
                    transport,
                    workspace,
                    session,
                ),
            ).fetchone()
        # A reused refresh token revokes its stable anchor. Do not raise inside
        # the transaction, which would accidentally undo that revocation.
        if row is None or row["result"] != "ok":
            raise _unauthorized()
        return _session_result(row, access, new_refresh, csrf)

    def sign_out(
        self,
        refresh: str,
        *,
        workspace: UUID,
        transport: str,
        csrf: str | None = None,
        session: UUID | None = None,
    ):
        refresh_digest = _digest(refresh, "mnm_r_")
        csrf_digest = _digest(csrf, "mnm_c_") if csrf is not None else None
        with self.db.pool.connection() as conn:
            result = conn.execute(
                "SELECT mnemion.sign_out_password_session(%s,%s,%s,%s,%s) AS signed_out",
                (refresh_digest, csrf_digest, transport, workspace, session),
            ).fetchone()["signed_out"]
        return {"signed_out": result}

    def sessions(self, identity: Identity):
        with self.db.transaction(identity) as conn:
            rows = conn.execute(
                """SELECT s.id,s.principal_id,s.device_name,s.transport,s.created_at,
                     s.last_refreshed_at,s.expires_at,k.revoked_at,s.key_id=%s AS current
                   FROM mnemion.sign_in_sessions s JOIN mnemion.api_keys k
                     ON k.tenant_id=s.tenant_id AND k.id=s.key_id
                   ORDER BY s.created_at DESC,s.id LIMIT 1000""",
                (identity.key_id,),
            ).fetchall()
        return {"items": json_value(rows)}

    def revoke(self, identity: Identity, session_id: UUID):
        with self.db.administration_transaction(identity) as conn:
            revoked = conn.execute(
                "SELECT mnemion.revoke_password_session(%s) AS revoked", (session_id,)
            ).fetchone()["revoked"]
        if not revoked:
            raise not_found()
        return {"id": str(session_id), "revoked": True}

    def invitations(self, identity: Identity):
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            rows = conn.execute(
                """SELECT id,principal_id,issued_by,purpose,permissions,created_at,expires_at,
                          consumed_at,revoked_at FROM mnemion.sign_in_invitations
                   ORDER BY created_at DESC,id LIMIT 1000"""
            ).fetchall()
        return {"items": json_value(rows)}

    def create_invitation(self, identity: Identity, command: InvitationInput):
        secret, digest = _secret("mnm_i_")
        with self.db.administration_transaction(identity) as conn:
            require_administrator(conn)
            result = conn.execute(
                "SELECT * FROM mnemion.create_sign_in_invitation(%s,%s,%s,%s)",
                (command.principal_id, command.purpose, digest, command.expires_in_seconds),
            ).fetchone()
            preview = (
                conn.execute(
                    "SELECT mnemion.preview_sign_in_invitation(%s) AS preview", (digest,)
                ).fetchone()["preview"]
                if result
                else None
            )
        if result is None:
            raise ServiceError(
                409,
                "invitation_unavailable",
                "Choose an active person and use password reset for an existing account.",
            )
        return {
            **json_value(result),
            "workspace_id": str(identity.tenant_id),
            "invitation_token": secret,
            "preview": preview,
        }

    def preview_invitation(self, secret: str):
        digest = _digest(secret, "mnm_i_")
        self._admit(f"invitation:{digest}")
        with self.db.pool.connection() as conn:
            preview = conn.execute(
                "SELECT mnemion.preview_sign_in_invitation(%s) AS preview", (digest,)
            ).fetchone()["preview"]
        if preview is None:
            raise _unauthorized()
        return preview

    def accept_invitation(self, command: InvitationAcceptInput):
        secret = command.invitation.get_secret_value()
        self.preview_invitation(secret)
        password = command.password.get_secret_value()
        screen_password(password, context=[command.username])
        encoded = hash_password(password)
        try:
            with self.db.pool.connection() as conn:
                row = conn.execute(
                    "SELECT * FROM mnemion.accept_sign_in_invitation(%s,%s,%s)",
                    (_digest(secret, "mnm_i_"), command.username, encoded),
                ).fetchone()
                if row is None:
                    raise _unauthorized()
                return self._issue(conn, row, command.device_name, command.transport)
        except psycopg.errors.UniqueViolation:
            raise ServiceError(409, "login_unavailable", "Choose another login name.") from None

    def revoke_invitation(self, identity: Identity, invitation_id: UUID):
        with self.db.administration_transaction(identity) as conn:
            require_administrator(conn)
            revoked = conn.execute(
                "SELECT mnemion.revoke_sign_in_invitation(%s) AS revoked", (invitation_id,)
            ).fetchone()["revoked"]
        if not revoked:
            raise not_found()
        return {"id": str(invitation_id), "revoked": True}
