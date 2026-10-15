"""Password/invitation HTTP boundaries and origin-bound browser refresh cookies."""

from datetime import datetime, timezone
import os
import re
import secrets
from typing import Annotated, Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from fastapi import Depends, Request, Response
from pydantic import AwareDatetime, Field, SecretStr

from .contracts import ResponseModel
from .db import Identity
from .errors import ServiceError
from .models import Command
from .mcp_transport import transport_security
from .sign_in import (
    InvitationAcceptInput,
    InvitationInput,
    PasswordInput,
    SignInInput,
    SignInService,
)


class SessionTokens(ResponseModel):
    session_id: UUID
    tenant_id: UUID
    principal_id: UUID
    access_token: str = Field(repr=False)
    refresh_token: str | None = Field(default=None, repr=False)
    csrf_token: str | None = Field(default=None, repr=False)
    access_expires_at: AwareDatetime
    expires_at: AwareDatetime
    persistence: Literal["native", "cookie", "memory"]
    rotation: int = Field(ge=0, le=4096)
    authentication: Literal["password", "company"] = "password"


class InvitationSecret(Command):
    invitation: SecretStr = Field(min_length=40, max_length=200)


class RefreshInput(Command):
    workspace_id: UUID
    session_id: UUID | None = None
    transport: Literal["native", "browser"]
    refresh_token: SecretStr | None = Field(default=None, min_length=40, max_length=200)


class BrowserPolicy:
    def __init__(self, public_url: str | None):
        self.public_origin = None
        if public_url:
            # This setting is shared with MCP. Preserve its supported loopback
            # HTTP and internationalized-host configurations during upgrades.
            transport_security(public_url)
            parsed = urlsplit(public_url)
            self.public_origin = self._canonical_origin(parsed)

    @staticmethod
    def _canonical_origin(parsed):
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        if ":" in host:
            host = f"[{host}]"
        port = parsed.port
        if port and port != (443 if parsed.scheme == "https" else 80):
            host += f":{port}"
        return urlunsplit((parsed.scheme, host, "", "", ""))

    def origin(self, request: Request) -> str | None:
        if self.public_origin:
            return self.public_origin
        # Unconfigured hosts only offer browser sign-in on the loopback origin.
        # A reverse-proxy Host/Forwarded header cannot invent a public login URL.
        url = request.url
        if url.hostname in {"localhost", "127.0.0.1", "::1"} and url.scheme in {"http", "https"}:
            return self._canonical_origin(urlsplit(str(url)))
        return None

    def check(self, request: Request, transport: str) -> str | None:
        origins = request.headers.getlist("origin")
        if transport == "native":
            if origins:
                raise ServiceError(
                    403,
                    "browser_origin_required",
                    "Use the browser sign-in flow on the workspace's own address.",
                )
            return None
        expected = self.origin(request)
        if expected is None:
            raise ServiceError(
                409,
                "public_sign_in_unconfigured",
                "The host operator must configure its public HTTPS address before enabling browser sign-in.",
            )
        if len(origins) != 1 or origins[0] != expected:
            raise ServiceError(
                403, "browser_origin_required", "Sign in from the workspace's own address."
            )
        if request.headers.get("sec-fetch-site") not in {None, "same-origin", "none"}:
            raise ServiceError(
                403, "browser_origin_required", "Sign in from the workspace's own address."
            )
        return expected


def cookie_names(workspace: UUID):
    # Independent cookies prevent one organization from replacing another
    # organization's connection on a shared origin. __Host forbids Domain and
    # subdomain cookie injection; persistent cookies are never sent over HTTP.
    return (f"__Host-mnemion-refresh-{workspace.hex}", f"__Host-mnemion-csrf-{workspace.hex}")


def clear_cookies(response: Response, workspace: UUID):
    for name in cookie_names(workspace):
        response.delete_cookie(
            name,
            path="/",
            secure=True,
            httponly=name.startswith("__Host-mnemion-refresh"),
            samesite="strict",
        )


def deliver(data: dict, response: Response, *, transport: str, cookie: bool):
    workspace = UUID(data["tenant_id"])
    if transport == "native":
        return {**data, "persistence": "native"}
    clear_cookies(response, workspace)
    if not cookie:
        # Loopback HTTP and an explicit non-remembered browser login keep their
        # credentials only in page memory. Never create insecure localhost cookies.
        return {**data, "persistence": "memory"}
    expires = datetime.fromisoformat(data["expires_at"]).astimezone(timezone.utc)
    age = max(0, min(30 * 86400, int((expires - datetime.now(timezone.utc)).total_seconds())))
    refresh_name, csrf_name = cookie_names(workspace)
    for name, value, protected in (
        (refresh_name, data["refresh_token"], True),
        (csrf_name, data["csrf_token"], False),
    ):
        response.set_cookie(
            name,
            value,
            max_age=age,
            expires=expires,
            path="/",
            secure=True,
            httponly=protected,
            samesite="strict",
        )
    return {**data, "refresh_token": None, "persistence": "cookie"}


def refresh_credentials(request: Request, command: RefreshInput, policy: BrowserPolicy):
    origin = policy.check(request, command.transport)
    csrf = None
    cookie = command.transport == "browser" and command.refresh_token is None
    if cookie:
        if not origin or not origin.startswith("https://"):
            raise ServiceError(
                403, "secure_cookie_required", "A remembered browser login requires HTTPS."
            )
        refresh_name, csrf_name = cookie_names(command.workspace_id)
        refresh = request.cookies.get(refresh_name)
        csrf_cookie = request.cookies.get(csrf_name)
        csrf_values = request.headers.getlist("x-mnemion-csrf")
        if (
            len(csrf_values) != 1
            or not csrf_cookie
            or not re.fullmatch(r"mnm_c_[A-Za-z0-9_-]{43}", csrf_cookie)
            or not re.fullmatch(r"mnm_c_[A-Za-z0-9_-]{43}", csrf_values[0])
            or not secrets.compare_digest(csrf_cookie, csrf_values[0])
        ):
            raise ServiceError(403, "csrf_required", "Refresh the sign-in page and try again.")
        csrf = csrf_values[0]
    else:
        refresh = command.refresh_token.get_secret_value() if command.refresh_token else None
        if command.transport == "browser":
            values = request.headers.getlist("x-mnemion-csrf")
            if len(values) != 1:
                raise ServiceError(403, "csrf_required", "Refresh the sign-in page and try again.")
            csrf = values[0]
    if not refresh:
        raise ServiceError(401, "sign_in_required", "Sign in to this workspace again.")
    return refresh, csrf, cookie


def attach_sign_in(
    app, database, authenticated, *, public_url: str | None = None, company_policies=()
):
    service = SignInService(database, company_policies=company_policies)
    policy = BrowserPolicy(public_url or os.environ.get("MNEMION_PUBLIC_URL"))
    Auth = Annotated[Identity, Depends(authenticated)]

    @app.get("/v1/sign-in/configuration", tags=["Sign-in"], response_model=dict)
    def configuration(request: Request):
        """Public capability information; no organization or account directory."""
        origin = policy.origin(request)
        return {
            "password_sign_in": True,
            "public_origin": policy.public_origin,
            "browser_sign_in": origin is not None,
            "remember_browser": bool(origin and origin.startswith("https://")),
            "minimum_password_characters": 15,
            "maximum_password_characters": 128,
        }

    @app.get("/v1/sign-in/account", tags=["Sign-in"], response_model=dict)
    def account(identity: Auth):
        return service.account(identity)

    @app.put("/v1/sign-in/account", tags=["Sign-in"], response_model=dict)
    def set_password(command: PasswordInput, identity: Auth):
        """Set up your own login or change it with your current password; revoke device sessions."""
        return service.set_password(identity, command)

    @app.post("/v1/sign-in/login", tags=["Sign-in"], response_model=SessionTokens)
    def login(command: SignInInput, request: Request, response: Response):
        origin = policy.check(request, command.transport)
        return deliver(
            service.sign_in(command),
            response,
            transport=command.transport,
            cookie=bool(command.remember and origin and origin.startswith("https://")),
        )

    @app.post("/v1/sign-in/refresh", tags=["Sign-in"], response_model=SessionTokens)
    def refresh(command: RefreshInput, request: Request, response: Response):
        credential, csrf, cookie = refresh_credentials(request, command, policy)
        data = service.refresh(
            credential,
            transport=command.transport,
            csrf=csrf,
            workspace=command.workspace_id,
            session=command.session_id,
        )
        return deliver(data, response, transport=command.transport, cookie=cookie)

    @app.post("/v1/sign-in/logout", tags=["Sign-in"], response_model=dict)
    def logout(command: RefreshInput, request: Request, response: Response):
        credential, csrf, _ = refresh_credentials(request, command, policy)
        result = service.sign_out(
            credential,
            workspace=command.workspace_id,
            transport=command.transport,
            csrf=csrf,
            session=command.session_id,
        )
        if command.transport == "browser" and result["signed_out"]:
            clear_cookies(response, command.workspace_id)
        return result

    @app.get("/v1/sign-in/sessions", tags=["Sign-in"], response_model=dict)
    def sessions(identity: Auth):
        return service.sessions(identity)

    @app.delete("/v1/sign-in/sessions/{session_id}", tags=["Sign-in"], response_model=dict)
    def revoke_session(session_id: UUID, identity: Auth):
        return service.revoke(identity, session_id)

    @app.get("/v1/sign-in/invitations", tags=["Sign-in"], response_model=dict)
    def invitations(identity: Auth):
        return service.invitations(identity)

    @app.post("/v1/sign-in/invitations", tags=["Sign-in"], response_model=dict, status_code=201)
    def create_invitation(command: InvitationInput, identity: Auth):
        """Create an expiring one-use invitation; reset suspends existing password sessions."""
        result = service.create_invitation(identity, command)
        origin = policy.public_origin
        return {
            **result,
            "invitation_url": f"{origin}/workspace#invitation={result['invitation_token']}"
            if origin
            else None,
            "sign_in_url": f"{origin}/workspace?workspace={identity.tenant_id}" if origin else None,
        }

    @app.post("/v1/sign-in/invitations/preview", tags=["Sign-in"], response_model=dict)
    def preview_invitation(command: InvitationSecret):
        """Possession of the private invitation permits previewing its specific permissions."""
        return service.preview_invitation(command.invitation.get_secret_value())

    @app.post("/v1/sign-in/invitations/accept", tags=["Sign-in"], response_model=SessionTokens)
    def accept_invitation(command: InvitationAcceptInput, request: Request, response: Response):
        origin = policy.check(request, command.transport)
        return deliver(
            service.accept_invitation(command),
            response,
            transport=command.transport,
            cookie=bool(command.remember and origin and origin.startswith("https://")),
        )

    @app.delete("/v1/sign-in/invitations/{invitation_id}", tags=["Sign-in"], response_model=dict)
    def revoke_invitation(invitation_id: UUID, identity: Auth):
        return service.revoke_invitation(identity, invitation_id)
