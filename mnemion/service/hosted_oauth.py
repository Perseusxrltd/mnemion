"""MCP SDK OAuth provider backed by the existing revocable password sessions."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import secrets
import time
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import anyio
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from psycopg.types.json import Jsonb

from .db import Identity, new_token, token_hash
from .errors import ServiceError
from .oauth import OAUTH_SCOPE, OAuthSettings, https_url, unauthorized
from .passwords import verify_password
from .sign_in import SignInService, normalize_username


@dataclass(frozen=True)
class HostedOAuthSettings:
    issuer: str
    resource: str
    tenant_id: UUID

    @classmethod
    def from_environment(cls):
        enabled = os.environ.get("MNEMION_OAUTH_BUILTIN", "0")
        if enabled not in {"0", "1"}:
            raise ValueError("MNEMION_OAUTH_BUILTIN must be 0 or 1")
        if enabled == "0":
            return None
        if any(
            os.environ.get("MNEMION_OAUTH_" + name)
            for name in ("ISSUER", "INTROSPECTION_URL", "CLIENT_ID", "CLIENT_SECRET_FILE")
        ):
            raise ValueError("Choose the built-in or external authorization server")
        try:
            tenant = UUID(os.environ.get("MNEMION_OAUTH_TENANT_ID", ""))
        except ValueError:
            raise ValueError("Select the workspace UUID for hosted sign-in") from None
        return cls.for_workspace(os.environ.get("MNEMION_PUBLIC_URL", ""), tenant)

    @classmethod
    def for_workspace(cls, public_url: str, tenant: UUID):
        """Build settings from explicit host-operator configuration."""
        public = urlsplit(https_url(public_url))
        if public.path not in {"", "/", "/mcp", "/mcp/"}:
            raise ValueError("Use the public HTTPS origin or its /mcp endpoint")
        host = public.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        origin = f"https://{host}" + (f":{public.port}" if public.port not in {None, 443} else "")
        return cls(origin + "/", origin + "/mcp", tenant)

    @property
    def origin(self):
        return self.issuer.rstrip("/")

    @property
    def metadata_url(self):
        return self.origin + "/.well-known/oauth-protected-resource/mcp"

    def metadata(self):
        return OAuthSettings.metadata(self)

    def challenge(self, error=None):
        return OAuthSettings.challenge(self, error)


def opaque(prefix):
    value = prefix + secrets.token_urlsafe(32)
    return value, token_hash(value)


def digest(value, prefix):
    if not isinstance(value, str) or not re.fullmatch(
        re.escape(prefix) + r"[A-Za-z0-9_-]{43}", value
    ):
        raise ValueError("Invalid authorization credential")
    return token_hash(value)


def redirect_uri(value):
    value = str(value)
    parsed = urlsplit(value)
    if (
        len(value) > 2048
        or any(ord(c) < 33 or ord(c) == 127 for c in value)
        or "\\" in value
        or "*" in value
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not parsed.hostname
        or (
            parsed.scheme != "https"
            and not (
                parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            )
        )
    ):
        raise RegistrationError(
            "invalid_redirect_uri",
            "Use an exact HTTPS or loopback callback without credentials or a fragment.",
        )
    return value


class HostedOAuth:
    def __init__(self, database, settings):
        self.db, self.settings = database, settings
        self.sign_in = SignInService(database)

    def _call(self, function, *arguments):
        # Function names are fixed in this module, never taken from requests.
        if not re.fullmatch(r"local_oauth_[a-z_]+", function):
            raise ValueError("Unknown hosted authorization operation")
        with self.db.pool.connection() as conn:
            return conn.execute(
                "SELECT mnemion."
                + function
                + "("
                + ",".join(["%s"] * len(arguments))
                + ") AS value",
                arguments,
            ).fetchone()["value"]

    async def call(self, function, *arguments):
        return await anyio.to_thread.run_sync(lambda: self._call(function, *arguments))

    async def admit(self, subject):
        maximum = {"registration": 20, "authorize": 60, "token": 120, "revoke": 60}[
            subject.partition(":")[0]
        ]
        if not await self.call("local_oauth_admit", token_hash(subject), maximum):
            raise ServiceError(
                429, "oauth_throttled", "Authorization is busy. Wait before trying again."
            )

    async def get_client(self, client_id):
        if not isinstance(client_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", client_id):
            return None
        value = await self.call("local_oauth_client", client_id)
        return OAuthClientInformationFull.model_validate(value) if value else None

    async def register_client(self, client_info):
        await self.admit("registration")
        if client_info.token_endpoint_auth_method != "none" or client_info.client_secret:
            raise RegistrationError(
                "invalid_client_metadata", "Use token_endpoint_auth_method=none with S256 PKCE."
            )
        if (
            "authorization_code" not in client_info.grant_types
            or set(client_info.grant_types) - {"authorization_code", "refresh_token"}
            or set(client_info.response_types) != {"code"}
        ):
            raise RegistrationError(
                "invalid_client_metadata",
                "Register the code response and authorization-code grant; refresh is optional.",
            )
        if not client_info.redirect_uris or not 1 <= len(client_info.redirect_uris) <= 10:
            raise RegistrationError(
                "invalid_redirect_uri", "Register one to ten exact callback URLs."
            )
        for value in client_info.redirect_uris:
            redirect_uri(value)
        name = client_info.client_name or "Registered application"
        if not 1 <= len(name.strip()) <= 100 or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise RegistrationError(
                "invalid_client_metadata", "Use a client name of 1–100 visible characters."
            )
        client_info.client_name = name.strip()
        value = client_info.model_dump(mode="json", exclude_none=True)
        if len(json.dumps(value).encode()) > 30000:
            raise RegistrationError("invalid_client_metadata", "Client metadata is too large.")
        if not await self.call("local_oauth_register", client_info.client_id, Jsonb(value)):
            raise RegistrationError(
                "invalid_client_metadata", "The host's client registration capacity is full."
            )

    async def authorize(self, client, params):
        await self.admit("authorize:" + client.client_id)
        if str(params.redirect_uri) not in {str(uri) for uri in client.redirect_uris}:
            raise AuthorizeError("invalid_request", "Use an exactly registered callback URL.")
        if params.resource != self.settings.resource:
            raise AuthorizeError(
                "invalid_target", "Select this memory service's canonical resource."
            )
        if set(params.scopes or []) != {OAUTH_SCOPE}:
            raise AuthorizeError("invalid_scope", "The mnemion:access scope is required.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", params.code_challenge):
            raise AuthorizeError("invalid_request", "A valid S256 PKCE challenge is required.")
        if params.state is not None and len(params.state) > 2048:
            raise AuthorizeError("invalid_request", "The authorization state is too large.")
        ticket, ticket_hash = opaque("mnm_ot_")
        stored = await self.call(
            "local_oauth_begin",
            uuid4(),
            ticket_hash,
            client.client_id,
            Jsonb(params.model_dump(mode="json")),
            self.settings.issuer,
            self.settings.resource,
        )
        if not stored:
            raise AuthorizeError(
                "temporarily_unavailable", "Authorization capacity is busy. Retry shortly."
            )
        return self.settings.origin + "/oauth/consent#request=" + ticket

    async def request(self, ticket):
        try:
            hashed = digest(ticket, "mnm_ot_")
        except ValueError:
            raise unauthorized() from None
        value = await self.call(
            "local_oauth_request", hashed, self.settings.issuer, self.settings.resource
        )
        if not value:
            raise ServiceError(
                409, "authorization_expired", "Start a fresh connection from your agent."
            )
        return value

    async def login(self, ticket, browser, username, password):
        await self.request(ticket)
        username = normalize_username(username)
        await anyio.to_thread.run_sync(
            self.sign_in._admit, "login:" + str(self.settings.tenant_id) + ":" + username
        )
        row = await anyio.to_thread.run_sync(
            self.sign_in._lookup, self.settings.tenant_id, username
        )
        accepted = await anyio.to_thread.run_sync(
            verify_password, password, row["password_hash"] if row else None
        )
        if not accepted or row is None:
            raise ServiceError(
                401, "sign_in_failed", "Check your login or request a new invitation."
            )
        proof, proof_hash = opaque("mnm_op_")
        preview = await self.call(
            "local_oauth_login",
            digest(ticket, "mnm_ot_"),
            self.settings.issuer,
            self.settings.resource,
            row["tenant_id"],
            row["principal_id"],
            row["password_hash"],
            row["account_version"],
            proof_hash,
            token_hash(browser),
        )
        if not preview:
            raise ServiceError(
                409, "authorization_changed", "The account or connection changed. Sign in again."
            )
        return {"proof": proof, "permissions": preview}

    async def consent(self, ticket, proof, browser):
        code, code_hash = opaque("mnm_oc_")
        try:
            ticket_hash, proof_hash = digest(ticket, "mnm_ot_"), digest(proof, "mnm_op_")
        except ValueError:
            raise unauthorized() from None
        params = await self.call(
            "local_oauth_consent",
            ticket_hash,
            self.settings.issuer,
            self.settings.resource,
            proof_hash,
            token_hash(browser),
            code_hash,
        )
        if not params:
            raise ServiceError(
                409,
                "authorization_changed",
                "Permissions or the connection changed. Review and sign in again.",
            )
        fields = {"code": code, "iss": self.settings.issuer}
        if params.get("state") is not None:
            fields["state"] = params["state"]
        return construct_redirect_uri(params["redirect_uri"], **fields)

    async def cancel(self, ticket, browser):
        params = await self.call(
            "local_oauth_cancel",
            digest(ticket, "mnm_ot_"),
            self.settings.issuer,
            self.settings.resource,
            token_hash(browser),
        )
        if not params:
            raise ServiceError(
                409, "authorization_expired", "Start a fresh connection from your agent."
            )
        fields = {"error": "access_denied", "iss": self.settings.issuer}
        if params.get("state") is not None:
            fields["state"] = params["state"]
        return construct_redirect_uri(params["redirect_uri"], **fields)

    async def load_authorization_code(self, client, authorization_code):
        try:
            hashed = digest(authorization_code, "mnm_oc_")
        except ValueError:
            return None
        value = await self.call(
            "local_oauth_code",
            hashed,
            client.client_id,
            self.settings.issuer,
            self.settings.resource,
        )
        if not value:
            return None
        params = value["parameters"]
        return AuthorizationCode(
            code=authorization_code,
            scopes=params["scopes"],
            expires_at=float(value["expires_at"]),
            client_id=client.client_id,
            code_challenge=params["code_challenge"],
            redirect_uri=params["redirect_uri"],
            redirect_uri_provided_explicitly=params["redirect_uri_provided_explicitly"],
            resource=self.settings.resource,
            subject=value["subject"],
        )

    @staticmethod
    def tokens(result, access, refresh):
        # A failed/reused credential has already committed its revocation.
        if not result or result.get("error"):
            raise TokenError("invalid_grant", "The authorization credential is no longer valid.")
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            refresh_token=refresh,
            expires_in=max(0, int(result["access_expires_at"] - time.time())),
            scope=OAUTH_SCOPE,
        )

    async def exchange_authorization_code(self, client, authorization_code):
        access, access_hash = opaque("mnmo_")
        refresh, refresh_hash = opaque("mnmr_")
        _, anchor_hash = new_token()
        result = await self.call(
            "local_oauth_exchange",
            digest(authorization_code.code, "mnm_oc_"),
            client.client_id,
            self.settings.issuer,
            self.settings.resource,
            uuid4(),
            uuid4(),
            anchor_hash,
            access_hash,
            refresh_hash,
            ("Agent: " + (client.client_name or "Connected application"))[:100],
        )
        return self.tokens(result, access, refresh)

    async def _token(self, value, kind):
        try:
            hashed = digest(value, "mnmo_" if kind == "access" else "mnmr_")
        except ValueError:
            return None
        return await self.call(
            "local_oauth_token", hashed, kind, self.settings.issuer, self.settings.resource
        )

    async def load_refresh_token(self, client, refresh_token):
        value = await self._token(refresh_token, "refresh")
        if not value or value["client_id"] != client.client_id:
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=value["scopes"],
            expires_at=int(value["expires_at"]),
            resource=self.settings.resource,
            subject=value["principal_id"],
        )

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        if set(scopes) != {OAUTH_SCOPE}:
            raise TokenError("invalid_scope", "The mnemion:access scope is required.")
        access, access_hash = opaque("mnmo_")
        refresh, refresh_hash = opaque("mnmr_")
        result = await self.call(
            "local_oauth_refresh",
            digest(refresh_token.token, "mnmr_"),
            client.client_id,
            self.settings.issuer,
            self.settings.resource,
            access_hash,
            refresh_hash,
        )
        return self.tokens(result, access, refresh)

    async def load_access_token(self, token):
        value = await self._token(token, "access")
        if not value:
            return None
        return AccessToken(
            token=token,
            client_id=value["client_id"],
            scopes=value["scopes"],
            expires_at=int(value["expires_at"]),
            resource=self.settings.resource,
            subject=value["principal_id"],
            claims={"iss": self.settings.issuer},
        )

    async def authenticate(self, token):
        value = await self._token(token, "access")
        if not value or UUID(value["tenant_id"]) != self.settings.tenant_id:
            raise unauthorized()
        return Identity(
            UUID(value["tenant_id"]),
            UUID(value["principal_id"]),
            UUID(value["key_id"]),
            float(value["expires_at"]),
            UUID(value["session_id"]),
        )

    async def revoke_token(self, token):
        kind = "refresh" if isinstance(token, RefreshToken) else "access"
        await self.call(
            "local_oauth_revoke",
            digest(token.token, "mnmr_" if kind == "refresh" else "mnmo_"),
            kind,
            token.client_id,
            self.settings.issuer,
            self.settings.resource,
        )
