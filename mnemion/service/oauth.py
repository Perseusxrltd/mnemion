"""Optional OAuth resource server; only operator configuration selects the issuer.

The authorization server owns login, PKCE, consent, registration and refresh.
Introspection authenticates the token, never grants Mnemion space permissions.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import UUID

import anyio
import httpx

from .errors import ServiceError

OAUTH_SCOPE = "mnemion:access"
MAX_TOKEN_BYTES = 4096
MAX_RESPONSE_BYTES = 32768


def https_url(value: str) -> str:
    """Require a fixed HTTPS URL safe for metadata, challenges and outbound HTTP."""
    try:
        parsed = urlsplit(value)
        valid_port = parsed.port is None or 1 <= parsed.port <= 65535
    except (ValueError, TypeError):
        raise ValueError(
            "OAuth URLs must be absolute HTTPS URLs without credentials or queries"
        ) from None
    if (
        not 1 <= len(value) <= 2048
        or parsed.scheme != "https"
        or not parsed.hostname
        or not valid_port
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(ord(c) < 33 or ord(c) > 126 or c in '\\"<>*' for c in value)
    ):
        raise ValueError("OAuth URLs must be absolute HTTPS URLs without credentials or queries")
    return value


def binding_hash(issuer: str, subject: str, client_id: str) -> bytes:
    return hashlib.sha256("\n".join((issuer, subject, client_id)).encode()).digest()


@dataclass(frozen=True)
class OAuthSettings:
    issuer: str
    introspection_url: str
    resource: str
    client_id: str
    client_secret: str = field(repr=False)
    tenant_id: UUID

    def __post_init__(self):
        if not isinstance(self.tenant_id, UUID):
            raise ValueError("OAuth requires an operator-approved Mnemion workspace UUID")
        for value in (self.issuer, self.introspection_url, self.resource):
            https_url(value)
        parsed = urlsplit(self.resource)
        if parsed.path != "/mcp":
            raise ValueError("OAuth resource must be the public HTTPS /mcp URL")
        for value in (self.client_id, self.client_secret):
            if (
                not isinstance(value, str)
                or not 1 <= len(value) <= 2048
                or any(ord(c) < 32 or ord(c) == 127 for c in value)
            ):
                raise ValueError("Configure nonempty, bounded OAuth introspection credentials")

    @classmethod
    def from_environment(cls) -> OAuthSettings | None:
        names = (
            "MNEMION_OAUTH_ISSUER",
            "MNEMION_OAUTH_INTROSPECTION_URL",
            "MNEMION_OAUTH_CLIENT_ID",
            "MNEMION_OAUTH_CLIENT_SECRET_FILE",
            "MNEMION_OAUTH_TENANT_ID",
        )
        values = [os.environ.get(name, "") for name in names]
        if not any(values):
            return None
        if not all(values) or not os.environ.get("MNEMION_PUBLIC_URL"):
            raise ValueError(
                "OAuth requires issuer, introspection URL, client ID, secret file, workspace ID and public URL"
            )
        public = https_url(os.environ["MNEMION_PUBLIC_URL"])
        parsed = urlsplit(public)
        if parsed.path not in {"", "/", "/mcp", "/mcp/"}:
            raise ValueError("OAuth public URL must be an HTTPS origin or its /mcp endpoint")
        try:
            with Path(values[3]).open("rb") as stream:
                raw = stream.read(4097)
                if len(raw) > 4096:
                    raise ValueError("OAuth introspection secret file exceeds its byte limit")
                secret = raw.decode("utf-8").rstrip("\r\n")
        except (OSError, UnicodeError):
            raise ValueError("Cannot read the OAuth introspection secret file") from None
        try:
            tenant_id = UUID(values[4])
        except ValueError:
            raise ValueError("OAuth workspace ID must be a UUID") from None
        return cls(
            values[0], values[1], f"https://{parsed.netloc}/mcp", values[2], secret, tenant_id
        )

    @property
    def metadata_url(self) -> str:
        parsed = urlsplit(self.resource)
        return f"https://{parsed.netloc}/.well-known/oauth-protected-resource/mcp"

    def metadata(self) -> dict:
        return {
            "resource": self.resource,
            "authorization_servers": [self.issuer],
            "scopes_supported": [OAUTH_SCOPE],
            "bearer_methods_supported": ["header"],
            "resource_name": "Mnemion",
        }

    def challenge(self, error: str | None = None) -> str:
        result = f'Bearer resource_metadata="{self.metadata_url}", scope="{OAUTH_SCOPE}"'
        if error == "insufficient_scope":
            result += (
                ', error="insufficient_scope", error_description="Mnemion access scope is required"'
            )
        elif error:
            result += ', error="invalid_token", error_description="Connect with a valid Mnemion access token"'
        return result


@dataclass(frozen=True)
class OAuthClaims:
    issuer: str
    subject: str
    client_id: str
    expires_at: float
    tenant_id: UUID


def unauthorized() -> ServiceError:
    return ServiceError(401, "unauthorized", "A valid, linked Mnemion access token is required.")


def unavailable() -> ServiceError:
    return ServiceError(
        503, "oauth_unavailable", "Sign-in verification is temporarily unavailable."
    )


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate field")
        result[key] = value
    return result


class OAuthVerifier:
    def __init__(self, settings: OAuthSettings, *, transport=None):
        self.settings = settings
        self.transport = transport
        self.capacity = anyio.CapacityLimiter(16)

    async def verify(self, token: str) -> OAuthClaims:
        if not token or len(token) > MAX_TOKEN_BYTES or any(not 33 <= ord(c) <= 126 for c in token):
            raise unauthorized()
        try:
            self.capacity.acquire_nowait()
        except anyio.WouldBlock:
            raise unavailable() from None
        try:
            # No redirects, environment proxies, bearer in URL, or token cache.
            # An absolute deadline also bounds peers that trickle their response.
            async with asyncio.timeout(4):
                async with httpx.AsyncClient(
                    transport=self.transport,
                    timeout=3,
                    trust_env=False,
                    follow_redirects=False,
                    auth=httpx.BasicAuth(
                        quote(self.settings.client_id, safe=""),
                        quote(self.settings.client_secret, safe=""),
                    ),
                ) as client:
                    async with client.stream(
                        "POST",
                        self.settings.introspection_url,
                        data={"token": token, "token_type_hint": "access_token"},
                        headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                    ) as response:
                        if response.status_code != 200:
                            raise unavailable()
                        if response.headers.get("content-encoding", "identity") != "identity":
                            raise unavailable()
                        length = response.headers.get("content-length")
                        if length is not None and (
                            not length.isascii()
                            or not length.isdigit()
                            or len(length) > 6
                            or int(length) > MAX_RESPONSE_BYTES
                        ):
                            raise unavailable()
                        body = bytearray()
                        async for chunk in response.aiter_raw():
                            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                                raise unavailable()
                            body.extend(chunk)
            claims = json.loads(body, object_pairs_hook=_json_object)
        except (httpx.HTTPError, TimeoutError, ValueError, RecursionError):
            raise unavailable() from None
        finally:
            self.capacity.release()
        return self.validate(claims)

    def validate(self, claims) -> OAuthClaims:
        if not isinstance(claims, dict) or claims.get("active") is not True:
            raise unauthorized()
        if claims.get("iss") != self.settings.issuer:
            raise unauthorized()
        audience = claims.get("aud")
        if isinstance(audience, str):
            audience = [audience]
        if (
            not isinstance(audience, list)
            or not audience
            or any(not isinstance(item, str) for item in audience)
            or self.settings.resource not in audience
        ):
            raise unauthorized()
        # Require aud, and reject a conflicting explicit resource claim as well.
        if "resource" in claims and claims["resource"] != self.settings.resource:
            raise unauthorized()
        now = time.time()
        for name in ("exp", "nbf", "iat"):
            value = claims.get(name)
            if name == "exp" or name in claims:
                if (
                    type(value) not in (int, float)
                    or abs(value) > 2**53
                    or not math.isfinite(value)
                ):
                    raise unauthorized()
                if (name == "exp" and value <= now) or (name != "exp" and value > now):
                    raise unauthorized()
        for name, maximum in (("sub", 255), ("client_id", 2048)):
            value = claims.get(name)
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > maximum
                or any(ord(c) < 32 or ord(c) == 127 for c in value)
            ):
                raise unauthorized()
        if "token_type" in claims and (
            not isinstance(claims["token_type"], str) or claims["token_type"].lower() != "bearer"
        ):
            raise unauthorized()
        scope = claims.get("scope")
        if not isinstance(scope, str) or any(not 32 <= ord(c) <= 126 for c in scope):
            raise unauthorized()
        if OAUTH_SCOPE not in scope.split(" "):
            raise ServiceError(
                403, "insufficient_scope", "The token requires the mnemion:access scope."
            )
        return OAuthClaims(
            claims["iss"],
            claims["sub"],
            claims["client_id"],
            claims["exp"],
            self.settings.tenant_id,
        )
