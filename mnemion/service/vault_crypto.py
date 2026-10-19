"""Versioned AES-256-GCM envelopes; keys never enter SQL, search or logs."""

import base64
import hashlib
import json
import os
import re
import secrets
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, SecretStr

from .errors import ServiceError

KEY_PATTERN = r"^mnv_[A-Za-z0-9_-]{43}$"
MAX_SECRET_BYTES = 65536
MAX_ARCHIVE_BYTES = 1_000_000


def new_vault_key() -> str:
    return "mnv_" + secrets.token_urlsafe(32)


def decode_key(value: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(KEY_PATTERN, value):
        raise ValueError("Use a generated Mnemion vault key")
    decoded = base64.urlsafe_b64decode(value[4:] + "=")
    if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).decode().rstrip("=") != value[4:]:
        raise ValueError("Use a generated Mnemion vault key")
    return decoded


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


class VaultSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: SecretStr | None = None
    enabled: bool = False
    mcp_enabled: bool = False

    @classmethod
    def from_environment(cls):
        return cls(
            key=os.environ.get("MNEMION_VAULT_KEY") or None,
            enabled=os.environ.get("MNEMION_VAULT_ENABLED", "0") == "1",
            mcp_enabled=os.environ.get("MNEMION_VAULT_MCP_ENABLED", "0") == "1",
        )


class VaultCipher:
    def __init__(self, key: str):
        material = decode_key(key)
        self.key_id = hashlib.sha256(b"mnemion-vault-key-v1\0" + material).hexdigest()[:32]
        self._cipher = AESGCM(material)

    @staticmethod
    def _aad(tenant: UUID, entry: UUID, name: str, version: int) -> bytes:
        return canonical(
            {
                "format": "mnemion-secret",
                "version": 1,
                "tenant_id": str(tenant),
                "entry_id": str(entry),
                "name": name,
                "revision": version,
            }
        )

    def encrypt(self, tenant: UUID, entry: UUID, name: str, version: int, value: str):
        try:
            payload = value.encode("utf-8")
        except UnicodeError:
            raise ServiceError(422, "vault_value_encoding", "Use a valid UTF-8 secret.") from None
        if not 1 <= len(payload) <= MAX_SECRET_BYTES:
            raise ServiceError(422, "vault_value_size", "Use a secret of 1–65536 UTF-8 bytes.")
        nonce = secrets.token_bytes(12)
        return nonce, self._cipher.encrypt(nonce, payload, self._aad(tenant, entry, name, version))

    def decrypt(self, row: dict) -> str:
        if row["key_id"] != self.key_id:
            raise ServiceError(
                503,
                "vault_key_unavailable",
                "Restore this vault's original encryption key on its host.",
            )
        try:
            return self._cipher.decrypt(
                bytes(row["nonce"]),
                bytes(row["ciphertext"]),
                self._aad(row["tenant_id"], row["id"], row["name"], row["version"]),
            ).decode("utf-8")
        except (InvalidTag, ValueError, TypeError, UnicodeError):
            raise ServiceError(
                503,
                "vault_integrity",
                "The encrypted value could not be verified. Restore a verified copy.",
            ) from None

    def seal_archive(self, document: dict) -> dict:
        payload = canonical(document)
        if len(payload) > MAX_ARCHIVE_BYTES:
            raise ServiceError(
                413,
                "vault_export_size",
                "Select fewer credentials for this portable export; full workspace backups have separate limits.",
            )
        nonce = secrets.token_bytes(12)
        ciphertext = self._cipher.encrypt(nonce, payload, b"mnemion-vault-export-v1")
        return {
            "format": "mnemion-vault-export",
            "version": 1,
            "key_id": self.key_id,
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
        }

    def open_archive(self, envelope: dict) -> dict:
        try:
            if envelope["key_id"] != self.key_id:
                raise ValueError()
            nonce = base64.b64decode(envelope["nonce"], validate=True)
            ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
            if len(nonce) != 12 or not 17 <= len(ciphertext) <= MAX_ARCHIVE_BYTES + 16:
                raise ValueError()
            return json.loads(self._cipher.decrypt(nonce, ciphertext, b"mnemion-vault-export-v1"))
        except (InvalidTag, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise ServiceError(
                422,
                "vault_archive_invalid",
                "The export or its recovery key could not be verified.",
            ) from None
