"""Operator-approved OpenID Connect providers for company sign-in.

Provider URLs and workspace admission come from the host's private configuration,
never from an ID token, company email address or tenant-admin request. This client
does not retain provider access/refresh tokens or send them to memory tools.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import math
import os
import re
import ssl
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlencode
from uuid import UUID

import anyio
from cryptography.hazmat.primitives.asymmetric import ec, rsa
import httpx
import jwt

from .errors import ServiceError
from .oauth import _json_object, https_url


def company_failed():
    return ServiceError(
        401,
        "company_sign_in_failed",
        "Company sign-in could not be completed. Try again or ask your administrator.",
    )


def company_unavailable():
    return ServiceError(
        503,
        "company_sign_in_unavailable",
        "Your company's sign-in service is temporarily unavailable.",
    )


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode()
        .rstrip("=")
    )


def nonce(verifier: str) -> str:
    return digest("mnemion-company-nonce:" + verifier)


def _bounded_label(value, limit):
    return (
        isinstance(value, str)
        and 1 <= len(value) <= limit
        and bool(value.strip())
        and not any(ord(c) < 32 or ord(c) == 127 for c in value)
    )


@dataclass(frozen=True)
class CompanyProvider:
    workspace_id: UUID
    id: str
    name: str
    issuer: str
    authorization_url: str
    token_url: str
    jwks_url: str
    client_id: str
    client_secret: str | None = field(default=None, repr=False)
    session_seconds: int = 28800

    def __post_init__(self):
        if (
            not isinstance(self.workspace_id, UUID)
            or not isinstance(self.id, str)
            or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", self.id)
        ):
            raise ValueError(
                "Company sign-in needs a workspace UUID and a short provider identifier"
            )
        if not _bounded_label(self.name, 100) or not _bounded_label(self.client_id, 512):
            raise ValueError("Company provider names and client IDs must be bounded, nonempty text")
        for value in (self.issuer, self.authorization_url, self.token_url, self.jwks_url):
            https_url(value)
        if self.client_secret is not None and not _bounded_label(self.client_secret, 2048):
            raise ValueError("Use a bounded company client secret in a private file")
        if type(self.session_seconds) is not int or not 900 <= self.session_seconds <= 86400:
            raise ValueError("Company sessions must last from 15 minutes to 24 hours")

    @property
    def policy_hash(self):
        # Secret rotation and display-name edits do not reassign a linked person.
        return digest(
            json.dumps(
                {
                    "workspace": str(self.workspace_id),
                    "id": self.id,
                    "issuer": self.issuer,
                    "authorization": self.authorization_url,
                    "token": self.token_url,
                    "jwks": self.jwks_url,
                    "client": self.client_id,
                    "seconds": self.session_seconds,
                    "confidential": self.client_secret is not None,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    def public(self):
        return {
            "id": self.id,
            "name": self.name,
            "issuer": self.issuer,
            "session_seconds": self.session_seconds,
        }


class CompanyIdentity:
    def __init__(self, providers=(), *, transport=None, ca_file=None, ca_pem=None):
        self.providers = {(item.workspace_id, item.id): item for item in providers}
        if len(self.providers) != len(providers) or len(providers) > 32:
            raise ValueError("Use at most 32 distinct workspace/company provider configurations")
        self.transport = transport
        self.tls = (
            ssl.create_default_context(cafile=ca_file, cadata=ca_pem) if ca_file or ca_pem else True
        )
        self.capacity = anyio.CapacityLimiter(8)

    @classmethod
    def from_environment(cls):
        filename = os.environ.get("MNEMION_COMPANY_SIGN_IN_FILE")
        if not filename:
            return cls()
        try:
            with Path(filename).open("rb") as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                raise ValueError("Company sign-in configuration exceeds its byte limit")
            data = json.loads(raw, object_pairs_hook=_json_object)
            if not isinstance(data, list) or len(data) > 32:
                raise ValueError("Company sign-in configuration must be a bounded provider list")
            providers = []
            allowed = {
                "workspace_id",
                "id",
                "name",
                "issuer",
                "authorization_url",
                "token_url",
                "jwks_url",
                "client_id",
                "client_secret_file",
                "session_seconds",
            }
            for entry in data:
                if not isinstance(entry, dict) or set(entry) - allowed:
                    raise ValueError("Unknown company sign-in configuration fields")
                entry = dict(entry)
                entry["workspace_id"] = UUID(entry["workspace_id"])
                secret_file = entry.pop("client_secret_file", None)
                if secret_file is not None:
                    with Path(secret_file).open("rb") as stream:
                        secret = stream.read(4097)
                    if len(secret) > 4096:
                        raise ValueError("Company client-secret file exceeds its byte limit")
                    entry["client_secret"] = secret.decode("utf-8").rstrip("\r\n")
                providers.append(CompanyProvider(**entry))
            return cls(providers, ca_file=os.environ.get("MNEMION_COMPANY_CA_FILE"))
        except (OSError, UnicodeError, TypeError, KeyError, ValueError, RecursionError):
            raise ValueError(
                "Check the private company sign-in configuration and credential files"
            ) from None

    @property
    def policies(self):
        return tuple(item.policy_hash for item in self.providers.values())

    def provider(self, workspace, provider_id):
        result = self.providers.get((workspace, provider_id))
        if result is None:
            raise ServiceError(
                409,
                "company_sign_in_unconfigured",
                "Company sign-in is not configured for this workspace.",
            )
        return result

    @staticmethod
    def authorization(provider, redirect_uri, state, verifier):
        return (
            provider.authorization_url
            + "?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": provider.client_id,
                    "redirect_uri": redirect_uri,
                    "scope": "openid",
                    "state": state,
                    "code_challenge": challenge(verifier),
                    "code_challenge_method": "S256",
                    "nonce": nonce(verifier),
                    "prompt": "select_account",
                }
            )
        )

    async def _json(self, client, method, url, **kwargs):
        async with client.stream(
            method,
            url,
            headers={"Accept": "application/json", "Accept-Encoding": "identity"},
            **kwargs,
        ) as response:
            if (
                response.status_code != 200
                or response.headers.get("content-encoding", "identity") != "identity"
            ):
                raise company_unavailable()
            body = bytearray()
            async for chunk in response.aiter_raw():
                if len(body) + len(chunk) > 65536:
                    raise company_unavailable()
                body.extend(chunk)
        result = json.loads(body, object_pairs_hook=_json_object)
        if not isinstance(result, dict):
            raise company_unavailable()
        return result

    async def exchange(self, provider, code, verifier, redirect_uri):
        if not _bounded_label(code, 4096) or not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier):
            raise company_failed()
        try:
            self.capacity.acquire_nowait()
        except anyio.WouldBlock:
            raise company_unavailable() from None
        try:
            async with asyncio.timeout(10):
                async with httpx.AsyncClient(
                    transport=self.transport,
                    verify=self.tls,
                    timeout=4,
                    trust_env=False,
                    follow_redirects=False,
                ) as client:
                    auth = (
                        httpx.BasicAuth(
                            quote(provider.client_id, safe=""),
                            quote(provider.client_secret, safe=""),
                        )
                        if provider.client_secret
                        else None
                    )
                    tokens = await self._json(
                        client,
                        "POST",
                        provider.token_url,
                        auth=auth,
                        data={
                            "grant_type": "authorization_code",
                            "client_id": provider.client_id,
                            "code": code,
                            "code_verifier": verifier,
                            "redirect_uri": redirect_uri,
                        },
                    )
                    encoded = tokens.get("id_token")
                    if not isinstance(encoded, str) or not 1 <= len(encoded) <= 16384:
                        raise company_failed()
                    header = jwt.get_unverified_header(encoded)
                    if (
                        header.get("alg") not in {"RS256", "ES256"}
                        or not _bounded_label(header.get("kid"), 256)
                        or any(key in header for key in ("jku", "x5u", "crit", "b64"))
                    ):
                        raise company_failed()
                    keyset = await self._json(client, "GET", provider.jwks_url)
                    keys = keyset.get("keys")
                    if not isinstance(keys, list) or not 1 <= len(keys) <= 32:
                        raise company_unavailable()
                    matching = [
                        key
                        for key in keys
                        if isinstance(key, dict) and key.get("kid") == header["kid"]
                    ]
                    if len(matching) != 1:
                        raise company_failed()
                    value = matching[0]
                    if (
                        value.get("use", "sig") != "sig"
                        or value.get("alg", header["alg"]) != header["alg"]
                        or ("key_ops" in value and value["key_ops"] != ["verify"])
                        or any(
                            key in value for key in ("d", "p", "q", "dp", "dq", "qi", "oth", "k")
                        )
                    ):
                        raise company_failed()
                    if header["alg"] == "RS256" and (
                        not isinstance(value.get("n"), str)
                        or not 342 <= len(value["n"]) <= 684
                        or not isinstance(value.get("e"), str)
                        or not 1 <= len(value["e"]) <= 12
                    ):
                        raise company_failed()
                    key = jwt.PyJWK.from_dict(value, algorithm=header["alg"]).key
                    if not (
                        header["alg"] == "RS256"
                        and isinstance(key, rsa.RSAPublicKey)
                        and 2048 <= key.key_size <= 4096
                        or header["alg"] == "ES256"
                        and isinstance(key, ec.EllipticCurvePublicKey)
                        and isinstance(key.curve, ec.SECP256R1)
                    ):
                        raise company_failed()
                    claims = jwt.decode(
                        encoded,
                        key,
                        algorithms=[header["alg"]],
                        audience=provider.client_id,
                        issuer=provider.issuer,
                        leeway=30,
                        options={"require": ["iss", "sub", "aud", "exp", "iat", "nonce"]},
                    )
                    self.validate(claims, provider, verifier, tokens.get("access_token"))
                    return claims["sub"]
        except (
            httpx.HTTPError,
            TimeoutError,
            ValueError,
            TypeError,
            KeyError,
            jwt.PyJWTError,
            RecursionError,
            OverflowError,
        ):
            raise company_failed() from None
        finally:
            self.capacity.release()

    @staticmethod
    def validate(claims, provider, verifier, access_token=None):
        if not _bounded_label(claims.get("sub"), 255):
            raise company_failed()
        expected_nonce = claims.get("nonce")
        if not isinstance(expected_nonce, str) or not hmac.compare_digest(
            expected_nonce, nonce(verifier)
        ):
            raise company_failed()
        now = time.time()
        for name in ("exp", "iat", "nbf"):
            value = claims.get(name)
            if value is None and name == "nbf":
                continue
            if type(value) not in (int, float) or not math.isfinite(value):
                raise company_failed()
        if claims["exp"] <= now or claims["iat"] > now + 30 or claims["iat"] < now - 600:
            raise company_failed()
        audience = claims["aud"]
        if isinstance(audience, str):
            audience = [audience]
        if (
            not isinstance(audience, list)
            or not audience
            or any(not isinstance(value, str) for value in audience)
        ):
            raise company_failed()
        if (len(audience) > 1 and claims.get("azp") != provider.client_id) or (
            "azp" in claims and claims["azp"] != provider.client_id
        ):
            raise company_failed()
        if "at_hash" in claims:
            if not isinstance(access_token, str) or not isinstance(claims["at_hash"], str):
                raise company_failed()
            expected = (
                base64.urlsafe_b64encode(hashlib.sha256(access_token.encode("ascii")).digest()[:16])
                .decode()
                .rstrip("=")
            )
            if not hmac.compare_digest(expected, claims["at_hash"]):
                raise company_failed()
