"""Hosted-agent OAuth endpoints with explicit personal-account consent."""

import hashlib
import hmac
import re
import secrets
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

import anyio
from fastapi import Depends, Request, Response
from mcp.server.auth.handlers.authorize import AuthorizationHandler
from mcp.server.auth.handlers.register import RegistrationHandler
from mcp.server.auth.handlers.revoke import RevocationHandler
from mcp.server.auth.handlers.token import TokenHandler
from mcp.server.auth.middleware.client_auth import ClientAuthenticator
from mcp.server.auth.settings import ClientRegistrationOptions
from pydantic import AwareDatetime, Field, SecretStr, field_validator
from starlette.responses import JSONResponse

from .company_identity import company_failed
from .company_sign_in import CompanyFinish, CompanySignIn, CompanyStart
from .db import Identity, token_hash
from .contracts import ResponseModel
from .errors import ServiceError, not_found
from .hosted_oauth import HostedOAuth, digest
from .models import Command, json_value
from .oauth import OAUTH_SCOPE
from .sign_in import SignInService, normalize_username
from .sign_in_api import BrowserPolicy
from ..agent_packages import (
    Provider as PackageProvider,
    Kind as PackageKind,
    build as build_agent_package,
)

COOKIE = "__Host-mnemion-oauth-browser"
PROTOCOL_PATHS = frozenset({"/oauth/register", "/oauth/authorize", "/oauth/token", "/oauth/revoke"})


class ConsentRequest(Command):
    ticket: SecretStr = Field(min_length=50, max_length=50)


class ConsentLogin(ConsentRequest):
    username: str = Field(min_length=3, max_length=128)
    password: SecretStr = Field(min_length=1, max_length=128)
    _username = field_validator("username")(normalize_username)


class ConsentApproval(ConsentRequest):
    proof: SecretStr = Field(min_length=50, max_length=50)


class ConsentCompanyStart(ConsentRequest):
    provider_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")


class ConsentCompanyFinish(CompanyFinish):
    ticket: SecretStr = Field(min_length=50, max_length=50)
    transport: Literal["browser"] = "browser"


class OAuthConnection(ResponseModel):
    session_id: UUID
    principal_id: UUID
    client_id: str
    issuer: str
    resource: str
    scopes: list[str]
    device_name: str
    created_at: AwareDatetime
    last_refreshed_at: AwareDatetime
    expires_at: AwareDatetime
    revoked_at: AwareDatetime | None


class OAuthConnections(ResponseModel):
    connections: list[OAuthConnection]


class OAuthConfiguration(ResponseModel):
    mode: Literal["disabled", "personal", "external"]
    mcp_enabled: bool
    resource: str | None
    issuer: str | None


class AgentPackageInput(Command):
    provider: PackageProvider


class AgentPackage(ResponseModel):
    provider: PackageProvider
    kind: PackageKind
    author: Literal["Perseus XR"]
    version: str
    filename: str
    media_type: Literal["application/zip"]
    sha256: str
    content_base64: str = Field(max_length=180000)
    contains_credentials: Literal[False]


class Disconnected(ResponseModel):
    id: UUID
    revoked: bool


def oauth_error(code, description, status=400):
    return JSONResponse(
        {"error": code, "error_description": description},
        status_code=status,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


async def form(request):
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/x-www-form-urlencoded"
    ):
        raise ServiceError(415, "invalid_oauth_request", "Use a URL-encoded OAuth request.")
    body = await request.body()
    if len(body) > 32768:
        raise ServiceError(413, "request_too_large", "The authorization request is too large.")
    fields = await request.form(max_fields=20, max_files=0)
    if len(fields) != len(fields.multi_items()) or len(fields) > 20:
        raise ServiceError(400, "invalid_oauth_request", "Use distinct OAuth parameters.")
    return fields


def attach_hosted_oauth(app, provider: HostedOAuth, authenticated, company: CompanySignIn):
    settings = provider.settings
    policy = BrowserPolicy(settings.origin)
    authenticator = ClientAuthenticator(provider)
    authorize_handler = AuthorizationHandler(provider)
    token_handler = TokenHandler(provider, authenticator)
    revoke_handler = RevocationHandler(provider, authenticator)
    register_handler = RegistrationHandler(
        provider,
        ClientRegistrationOptions(
            enabled=True, valid_scopes=[OAUTH_SCOPE], default_scopes=[OAUTH_SCOPE]
        ),
    )

    def finish(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        location = response.headers.get("location")
        if location and not location.startswith(settings.origin + "/oauth/consent#"):
            parsed = urlsplit(location)
            parameters = [
                (key, value)
                for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                if key != "iss"
            ]
            parameters.append(("iss", settings.issuer))
            response.headers["location"] = urlunsplit(parsed._replace(query=urlencode(parameters)))
        return response

    @app.get("/.well-known/oauth-authorization-server", include_in_schema=False)
    def metadata():
        return JSONResponse(
            {
                "issuer": settings.issuer,
                "authorization_endpoint": settings.origin + "/oauth/authorize",
                "token_endpoint": settings.origin + "/oauth/token",
                "registration_endpoint": settings.origin + "/oauth/register",
                "revocation_endpoint": settings.origin + "/oauth/revoke",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "token_endpoint_auth_methods_supported": ["none"],
                "revocation_endpoint_auth_methods_supported": ["none"],
                "code_challenge_methods_supported": ["S256"],
                "scopes_supported": [OAUTH_SCOPE],
                "authorization_response_iss_parameter_supported": True,
            },
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "public, max-age=300"},
        )

    @app.post("/oauth/register", include_in_schema=False)
    async def register(request: Request):
        if (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "application/json"
        ):
            return oauth_error("invalid_client_metadata", "Use JSON registration metadata.", 415)
        if len(await request.body()) > 32768:
            return oauth_error("invalid_client_metadata", "Client metadata is too large.", 413)
        return finish(await register_handler.handle(request))

    @app.get("/oauth/authorize", include_in_schema=False)
    async def authorize(request: Request):
        fields = request.query_params
        if len(str(request.url)) > 16384 or len(fields) != len(fields.multi_items()):
            return oauth_error("invalid_request", "Use bounded, distinct authorization parameters.")
        if fields.get("code_challenge_method") != "S256":
            return oauth_error("invalid_request", "S256 PKCE is required.")
        return finish(await authorize_handler.handle(request))

    @app.post("/oauth/token", include_in_schema=False)
    async def token(request: Request):
        fields = await form(request)
        await provider.admit("token:" + str(fields.get("client_id", ""))[:128])
        grant = fields.get("grant_type")
        if grant not in {"authorization_code", "refresh_token"}:
            return oauth_error("unsupported_grant_type", "Use authorization_code or refresh_token.")
        resource = fields.get("resource")
        if (
            grant == "authorization_code" or resource is not None
        ) and resource != settings.resource:
            return oauth_error("invalid_target", "Use this memory service's canonical resource.")
        if grant == "authorization_code" and not re.fullmatch(
            r"[A-Za-z0-9._~-]{43,128}", fields.get("code_verifier", "")
        ):
            return oauth_error("invalid_request", "Use a valid S256 PKCE verifier.")
        return finish(await token_handler.handle(request))

    @app.post("/oauth/revoke", include_in_schema=False)
    async def revoke(request: Request):
        fields = await form(request)
        await provider.admit("revoke:" + str(fields.get("client_id", ""))[:128])
        return finish(await revoke_handler.handle(request))

    def browser(request, ticket, *, create=False):
        policy.check(request, "browser")
        value = request.cookies.get(COOKIE, "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
            if not create:
                raise ServiceError(
                    403, "consent_browser_changed", "Restart the connection in this browser."
                )
            value = secrets.token_urlsafe(32)
        csrf = hmac.new(value.encode(), ticket.encode(), hashlib.sha256).hexdigest()
        if not create:
            supplied = request.headers.getlist("x-mnemion-consent-csrf")
            if len(supplied) != 1 or not hmac.compare_digest(csrf.encode(), supplied[0].encode()):
                raise ServiceError(403, "consent_browser_changed", "Refresh the permission review.")
        return value, csrf

    @app.post("/oauth/consent/request", include_in_schema=False)
    async def consent_request(command: ConsentRequest, request: Request, response: Response):
        ticket = command.ticket.get_secret_value()
        value, csrf = browser(request, ticket, create=True)
        details = await provider.request(ticket)
        response.set_cookie(
            COOKIE, value, max_age=600, httponly=True, secure=True, samesite="lax", path="/"
        )
        response.headers["Cache-Control"] = "no-store"
        return {
            "client_name": details["client_name"],
            "callback": details["parameters"]["redirect_uri"],
            "csrf": csrf,
            "expires_at": details["expires_at"],
            "company": company.configuration(settings.tenant_id),
        }

    @app.post("/oauth/consent/login", include_in_schema=False)
    async def consent_login(command: ConsentLogin, request: Request, response: Response):
        ticket = command.ticket.get_secret_value()
        value, _ = browser(request, ticket)
        response.headers["Cache-Control"] = "no-store"
        return await provider.login(
            ticket, value, command.username, command.password.get_secret_value()
        )

    @app.post("/oauth/consent/company/start", include_in_schema=False)
    async def consent_company_start(
        command: ConsentCompanyStart, request: Request, response: Response
    ):
        ticket = command.ticket.get_secret_value()
        value, _ = browser(request, ticket)
        details = await provider.request(ticket)
        login = CompanyStart(
            workspace_id=settings.tenant_id,
            provider_id=command.provider_id,
            device_name=("Agent: " + details["client_name"])[:100],
            transport="browser",
        )
        result = await anyio.to_thread.run_sync(
            lambda: company.start(login, consent=(digest(ticket, "mnm_ot_"), token_hash(value)))
        )
        response.headers["Cache-Control"] = "no-store"
        return result

    @app.post("/oauth/consent/company/finish", include_in_schema=False)
    async def consent_company_finish(
        command: ConsentCompanyFinish, request: Request, response: Response
    ):
        ticket = command.ticket.get_secret_value()
        value, _ = browser(request, ticket)
        await provider.request(ticket)
        flow, selected = await anyio.to_thread.run_sync(company.claim, command)
        if (
            selected.workspace_id != settings.tenant_id
            or flow.get("consent")
            != {"ticket_hash": digest(ticket, "mnm_ot_"), "browser_hash": token_hash(value)}
            or flow.get("invitation_hash") is not None
        ):
            raise company_failed()
        subject = await company.identity.exchange(
            selected,
            command.code.get_secret_value(),
            command.code_verifier.get_secret_value(),
            company.callback_uri,
        )
        result = await provider.company_login(ticket, value, command, selected, subject)
        response.headers["Cache-Control"] = "no-store"
        return result

    @app.post("/oauth/consent/approve", include_in_schema=False)
    async def consent_approve(command: ConsentApproval, request: Request, response: Response):
        ticket = command.ticket.get_secret_value()
        value, _ = browser(request, ticket)
        location = await provider.consent(ticket, command.proof.get_secret_value(), value)
        response.headers["Cache-Control"] = "no-store"
        return {"redirect": location}

    @app.post("/oauth/consent/cancel", include_in_schema=False)
    async def consent_cancel(command: ConsentRequest, request: Request, response: Response):
        ticket = command.ticket.get_secret_value()
        value, _ = browser(request, ticket)
        response.headers["Cache-Control"] = "no-store"
        return {"redirect": await provider.cancel(ticket, value)}


def attach_hosted_connections(
    app, database, authenticated, settings=None, *, personal=False, mcp_enabled=True
):
    Auth = Annotated[Identity, Depends(authenticated)]
    sign_in = SignInService(database)

    @app.get("/v1/oauth/configuration", tags=["Identity"], response_model=OAuthConfiguration)
    def configuration(identity: Auth):
        """Return this workspace's connection mode, without another tenant's configuration."""
        selected = settings is not None and identity.tenant_id == settings.tenant_id
        return OAuthConfiguration(
            mode=("personal" if personal else "external") if selected else "disabled",
            mcp_enabled=mcp_enabled,
            resource=settings.resource if selected else None,
            issuer=settings.issuer if selected else None,
        )

    @app.post("/v1/oauth/agent-package", tags=["Identity"], response_model=AgentPackage)
    def agent_package(command: AgentPackageInput, identity: Auth, response: Response):
        """Download a Perseus XR connection package for this workspace; no credentials or account creation."""
        if settings is None or identity.tenant_id != settings.tenant_id or not mcp_enabled:
            raise ServiceError(
                409,
                "agent_sign_in_unavailable",
                "Enable this workspace's HTTPS MCP sign-in before exporting a connection package.",
            )
        response.headers["Cache-Control"] = "no-store"
        try:
            return build_agent_package(command.provider, settings.resource)
        except ValueError:
            raise ServiceError(
                409,
                "agent_package_unavailable",
                "Check this workspace's HTTPS MCP address before exporting a connection package.",
            ) from None

    @app.get("/v1/oauth/connections", tags=["Identity"], response_model=OAuthConnections)
    def connections(identity: Auth):
        with database.transaction(identity) as conn:
            return {
                "connections": json_value(
                    conn.execute(
                        """SELECT c.session_id,c.principal_id,c.client_id,c.issuer,c.resource,c.scopes,
                          s.device_name,s.created_at,s.last_refreshed_at,s.expires_at,k.revoked_at
                   FROM mnemion.oauth_local_connections c
                   JOIN mnemion.sign_in_sessions s ON s.id=c.session_id
                   JOIN mnemion.api_keys k ON k.id=s.key_id AND k.tenant_id=s.tenant_id
                   ORDER BY s.created_at DESC,s.id LIMIT 1000"""
                    ).fetchall()
                )
            }

    @app.post(
        "/v1/oauth/connections/{session_id}/revoke", tags=["Identity"], response_model=Disconnected
    )
    def disconnect(session_id: UUID, identity: Auth):
        with database.transaction(identity) as conn:
            if not conn.execute(
                "SELECT session_id FROM mnemion.oauth_local_connections WHERE session_id=%s",
                (session_id,),
            ).fetchone():
                raise not_found()
        return sign_in.revoke(identity, session_id)
