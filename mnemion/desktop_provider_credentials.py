"""Ephemeral provider credentials received through Studio's private input pipe."""

from __future__ import annotations

import base64
import json
import re
import time

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .connectors.providers import ProviderError

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate provider credential field")
        value[key] = item
    return value


def _token(value, maximum=16384):
    if not isinstance(value, str) or not 16 <= len(value) <= maximum:
        raise ValueError("Use the provider's complete credential")
    if any(not 33 <= ord(c) <= 126 for c in value):
        raise ValueError("Provider tokens cannot contain whitespace or control characters")
    return value


class PrivateToken:
    def __init__(self, value: str):
        self._value = _token(value, 4096)

    def read(self) -> str:
        return self._value


class DriveServiceAccount:
    """Read-only, nondelegated Google access; short-lived tokens stay in memory."""

    def __init__(self, value: str, *, transport=None, now=time.time):
        try:
            data = json.loads(value, object_pairs_hook=_unique)
            if (
                not isinstance(data, dict)
                or data.get("type") != "service_account"
                or data.get("token_uri") != GOOGLE_TOKEN_URL
                or data.get("universe_domain", "googleapis.com") != "googleapis.com"
                or not isinstance(data.get("client_email"), str)
                or not re.fullmatch(
                    r"[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.gserviceaccount\.com",
                    data["client_email"],
                )
                or len(data["client_email"]) > 300
                or not isinstance(data.get("private_key"), str)
                or not isinstance(data.get("private_key_id"), str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", data["private_key_id"])
            ):
                raise ValueError()
            key = serialization.load_pem_private_key(data["private_key"].encode(), password=None)
            if not isinstance(key, rsa.RSAPrivateKey) or not 2048 <= key.key_size <= 4096:
                raise ValueError()
        except (ValueError, TypeError, KeyError, RecursionError):
            raise ValueError(
                "Use a valid Google service-account JSON key for read-only Drive access"
            ) from None
        self._key, self._key_id, self._email = key, data["private_key_id"], data["client_email"]
        self._transport, self._now = transport, now
        self._access, self._expires = None, 0

    def read(self) -> str:
        if self._access and self._now() < self._expires:
            return self._access
        issued = int(self._now())

        def encode(value):
            data = json.dumps(value, separators=(",", ":")).encode()
            return base64.urlsafe_b64encode(data).rstrip(b"=")

        content = b".".join(
            [
                encode({"alg": "RS256", "typ": "JWT", "kid": self._key_id}),
                encode(
                    {
                        "iss": self._email,
                        "scope": DRIVE_SCOPE,
                        "aud": GOOGLE_TOKEN_URL,
                        "iat": issued,
                        "exp": issued + 3600,
                    }
                ),
            ]
        )
        signature = self._key.sign(content, padding.PKCS1v15(), hashes.SHA256())
        assertion = content + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")
        try:
            with httpx.Client(
                timeout=20, follow_redirects=False, transport=self._transport
            ) as client:
                with client.stream(
                    "POST",
                    GOOGLE_TOKEN_URL,
                    data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                        "assertion": assertion.decode("ascii"),
                    },
                ) as response:
                    if response.status_code in {400, 401, 403}:
                        raise ProviderError("provider_access_lost", access_lost=True)
                    if response.status_code != 200:
                        raise ProviderError("provider_unavailable")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 65536:
                            raise ProviderError("provider_response_too_large")
            result = json.loads(body, object_pairs_hook=_unique)
            access = _token(result.get("access_token"))
            lifetime = result.get("expires_in")
            if type(lifetime) is not int or not 60 <= lifetime <= 3600:
                raise ValueError()
        except (httpx.HTTPError, ValueError, AttributeError, RecursionError):
            raise ProviderError("provider_unavailable") from None
        self._access = access
        self._expires = self._now() + lifetime - 60
        return access


def credential(provider: str, value: str, **options):
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 8192:
        raise ValueError("Supply the selected provider's private credential, up to 8 KiB")
    if provider == "slack":
        return PrivateToken(value)
    if provider == "gdrive":
        return DriveServiceAccount(value, **options)
    raise ValueError("This source does not use cloud-provider credentials")
