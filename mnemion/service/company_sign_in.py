"""Company login handoff, explicit identity links and revocable local sessions."""

import json
import re
import secrets
from typing import Annotated, Literal
from urllib.parse import urlencode, urlsplit
from uuid import UUID, uuid4

import anyio
from fastapi import Depends, Request, Response
from pydantic import Field, SecretStr, field_validator, model_validator
from psycopg.types.json import Jsonb
from starlette.responses import HTMLResponse, RedirectResponse

from .company_identity import CompanyIdentity, company_failed, digest
from .db import Identity, new_token, require_administrator
from .errors import ServiceError, not_found
from .models import Command, json_value
from .oauth import https_url
from .sign_in import SignInService, _digest, _secret, _session_result, device_label
from .sign_in_api import BrowserPolicy, SessionTokens, deliver


class CompanyStart(Command):
    workspace_id: UUID
    provider_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    device_name: str = Field(min_length=1, max_length=100)
    transport: Literal["browser", "native"]
    callback_uri: str | None = Field(default=None, max_length=256)
    invitation: SecretStr | None = Field(default=None, min_length=40, max_length=200)
    remember: bool = False

    _device_name = field_validator("device_name")(device_label)

    @model_validator(mode="after")
    def callback(self):
        if self.transport == "browser":
            if self.callback_uri is not None:
                raise ValueError("Browser sign-in returns only to this workspace")
            return self
        try:
            target = urlsplit(self.callback_uri or "")
            accepted = (
                target.scheme == "http"
                and target.hostname == "127.0.0.1"
                and target.port is not None
                and 1024 <= target.port <= 65535
            )
        except ValueError:
            accepted = False
        if (
            not accepted
            or target.username
            or target.password
            or target.query
            or target.fragment
            or not re.fullmatch(r"/mnemion-company/[A-Za-z0-9_-]{43}", target.path)
        ):
            raise ValueError("Native company sign-in needs its temporary loopback callback")
        return self


class CompanyFinish(Command):
    state: SecretStr = Field(min_length=49, max_length=49)
    code_verifier: SecretStr = Field(min_length=43, max_length=128)
    code: SecretStr = Field(min_length=1, max_length=4096)
    transport: Literal["browser", "native"]


class CompanyLinkInput(Command):
    principal_id: UUID
    provider_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    subject: str = Field(min_length=1, max_length=255)

    @field_validator("subject")
    @classmethod
    def opaque_subject(cls, value):
        if not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Use the provider's stable subject identifier")
        return value


class CompanyConfigurationInput(Command):
    workspace_id: UUID


def external_hash(provider, subject):
    return digest(json.dumps([provider.issuer, provider.client_id, subject], separators=(",", ":")))


class CompanySignIn:
    def __init__(self, database, identity: CompanyIdentity, public_origin: str | None):
        self.db, self.identity, self.origin = database, identity, public_origin
        if identity.providers:
            https_url(public_origin or "")
        self.callback_uri = (public_origin + "/company/callback") if public_origin else None

    def configuration(self, workspace):
        return {
            "providers": [
                item.public()
                for item in self.identity.providers.values()
                if item.workspace_id == workspace
            ],
            "callback_uri": self.callback_uri,
        }

    def start(self, command: CompanyStart, *, consent: tuple[str, str] | None = None):
        provider = self.identity.provider(command.workspace_id, command.provider_id)
        state, state_hash = _secret("mnm_o_")
        verifier = secrets.token_urlsafe(32)
        SignInService(self.db)._admit("company-start:" + state_hash)
        invitation_hash = None
        if command.invitation:
            value = command.invitation.get_secret_value()
            preview = SignInService(self.db).preview_invitation(value)
            if (
                preview["workspace_id"] != str(command.workspace_id)
                or preview["purpose"] != "enroll"
            ):
                raise company_failed()
            invitation_hash = _digest(value, "mnm_i_")
        payload = {
            "device_name": command.device_name,
            "transport": command.transport,
            "callback_uri": command.callback_uri,
            "invitation_hash": invitation_hash,
            "remember": command.remember,
        }
        if consent:
            payload["consent"] = {"ticket_hash": consent[0], "browser_hash": consent[1]}
        with self.db.pool.connection() as conn:
            created = conn.execute(
                "SELECT mnemion.create_company_login(%s,%s,%s,%s,%s,%s) AS created",
                (
                    state_hash,
                    digest(verifier),
                    command.workspace_id,
                    provider.id,
                    provider.policy_hash,
                    Jsonb(payload),
                ),
            ).fetchone()["created"]
        if not created:
            raise ServiceError(
                429, "company_sign_in_busy", "Company sign-in is busy. Try again shortly."
            )
        return {
            "state": state,
            "code_verifier": verifier,
            "expires_in": 300,
            "authorization_url": self.identity.authorization(
                provider, self.callback_uri, state, verifier
            ),
            "provider": provider.public(),
        }

    def callback(self, state):
        state_hash = _digest(state, "mnm_o_")
        with self.db.pool.connection() as conn:
            value = conn.execute(
                "SELECT mnemion.company_login_callback(%s) AS value", (state_hash,)
            ).fetchone()["value"]
        if not value:
            raise company_failed()
        provider = self.identity.provider(UUID(value["workspace_id"]), value["provider_id"])
        if provider.policy_hash != value["policy_hash"]:
            raise company_failed()
        return value, provider

    def claim(self, command):
        verifier = command.code_verifier.get_secret_value()
        if not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier):
            raise company_failed()
        state_hash = _digest(command.state.get_secret_value(), "mnm_o_")
        SignInService(self.db)._admit("company-finish:" + state_hash)
        with self.db.pool.connection() as conn:
            value = conn.execute(
                "SELECT mnemion.claim_company_login(%s,%s) AS value", (state_hash, digest(verifier))
            ).fetchone()["value"]
        if not value or value["transport"] != command.transport:
            raise company_failed()
        provider = self.identity.provider(UUID(value["workspace_id"]), value["provider_id"])
        if value["policy_hash"] != provider.policy_hash:
            raise company_failed()
        return value, provider

    def issue(self, command, provider, subject):
        access, access_hash = _secret("mnm_s_")
        refresh, refresh_hash = _secret("mnm_r_")
        csrf, csrf_hash = _secret("mnm_c_") if command.transport == "browser" else (None, None)
        _, anchor_hash = new_token()
        with self.db.pool.connection() as conn:
            session = conn.execute(
                "SELECT * FROM mnemion.issue_company_session(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    _digest(command.state.get_secret_value(), "mnm_o_"),
                    digest(command.code_verifier.get_secret_value()),
                    provider.issuer,
                    provider.client_id,
                    subject,
                    external_hash(provider, subject),
                    provider.session_seconds,
                    uuid4(),
                    uuid4(),
                    anchor_hash,
                    access_hash,
                    refresh_hash,
                    csrf_hash,
                ),
            ).fetchone()
            if session is None:
                raise company_failed()
        return _session_result(session, access, refresh, csrf)

    def links(self, actor):
        with self.db.transaction(actor) as conn:
            return {
                "items": json_value(
                    conn.execute("""SELECT id,principal_id,provider_id,issuer,client_id,subject,
                created_at,changed_at,last_authenticated_at,revoked_at FROM mnemion.company_links ORDER BY created_at,id LIMIT 1000""").fetchall()
                )
            }

    def link(self, actor, command):
        provider = self.identity.provider(actor.tenant_id, command.provider_id)
        with self.db.administration_transaction(actor) as conn:
            require_administrator(conn)
            linked = conn.execute(
                "SELECT mnemion.link_company_identity(%s,%s,%s,%s,%s,%s,%s) AS id",
                (
                    command.principal_id,
                    provider.id,
                    provider.issuer,
                    provider.client_id,
                    command.subject,
                    external_hash(provider, command.subject),
                    provider.policy_hash,
                ),
            ).fetchone()["id"]
            if linked is None:
                raise ServiceError(
                    409,
                    "company_link_unavailable",
                    "Choose an active person and an unassigned company identity.",
                )
        return {
            "id": str(linked),
            "principal_id": str(command.principal_id),
            "provider_id": provider.id,
        }

    def revoke(self, actor, link_id):
        with self.db.administration_transaction(actor) as conn:
            changed = conn.execute(
                "SELECT mnemion.revoke_company_identity(%s) AS changed", (link_id,)
            ).fetchone()["changed"]
            if not changed:
                raise not_found()
        return {"id": str(link_id), "revoked": True}


def attach_company_sign_in(app, service: CompanySignIn, authenticated):
    policy = BrowserPolicy(service.origin)
    Auth = Annotated[Identity, Depends(authenticated)]

    @app.get("/v1/sign-in/company/configuration", tags=["Sign-in"], response_model=dict)
    def configuration(workspace_id: UUID):
        """List only the host-approved sign-in options for the requested workspace."""
        return service.configuration(workspace_id)

    @app.post("/v1/sign-in/company/configuration", tags=["Sign-in"], response_model=dict)
    def configuration_request(command: CompanyConfigurationInput):
        return service.configuration(command.workspace_id)

    @app.post("/v1/sign-in/company/start", tags=["Sign-in"], response_model=dict)
    def start(command: CompanyStart, request: Request):
        policy.check(request, command.transport)
        return service.start(command)

    @app.post("/v1/sign-in/company/finish", tags=["Sign-in"], response_model=SessionTokens)
    async def finish(command: CompanyFinish, request: Request, response: Response):
        origin = policy.check(request, command.transport)
        value, provider = await anyio.to_thread.run_sync(service.claim, command)
        if "consent" in value:
            raise company_failed()
        subject = await service.identity.exchange(
            provider,
            command.code.get_secret_value(),
            command.code_verifier.get_secret_value(),
            service.callback_uri,
        )
        result = await anyio.to_thread.run_sync(service.issue, command, provider, subject)
        return deliver(
            result,
            response,
            transport=command.transport,
            cookie=bool(value["remember"] and origin and origin.startswith("https://")),
        )

    @app.get("/v1/sign-in/company/links", tags=["Sign-in"], response_model=dict)
    def links(actor: Auth):
        return service.links(actor)

    @app.post("/v1/sign-in/company/links", tags=["Sign-in"], status_code=201, response_model=dict)
    def link(command: CompanyLinkInput, actor: Auth):
        """Approve a stable external subject for an existing person; space grants are unchanged."""
        return service.link(actor, command)

    @app.delete("/v1/sign-in/company/links/{link_id}", tags=["Sign-in"], response_model=dict)
    def revoke(link_id: UUID, actor: Auth):
        return service.revoke(actor, link_id)

    @app.get("/company/callback", include_in_schema=False)
    async def callback(request: Request):
        fields = request.query_params
        if len(str(request.url)) > 8192 or len(fields) != len(fields.multi_items()):
            raise company_failed()
        state = fields.get("state", "")
        value, provider = await anyio.to_thread.run_sync(service.callback, state)
        code = fields.get("code", "")
        failed = (
            "error" in fields
            or not 1 <= len(code) <= 4096
            or ("iss" in fields and fields["iss"] != provider.issuer)
        )
        message = {
            "type": "mnemion-company-callback",
            "state": state,
            **({"error": "company_sign_in_failed"} if failed else {"code": code}),
        }
        headers = {
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        }
        if value["transport"] == "native":
            target = value["callback_uri"]
            # Revalidate persisted callbacks before forwarding even a PKCE-bound code.
            CompanyStart(
                workspace_id=provider.workspace_id,
                provider_id=provider.id,
                transport="native",
                callback_uri=target,
                device_name="Callback",
            )
            return RedirectResponse(
                target
                + "?"
                + urlencode({key: item for key, item in message.items() if key != "type"}),
                status_code=303,
                headers=headers,
            )
        script_nonce = secrets.token_urlsafe(18)
        headers["Content-Security-Policy"] = (
            f"default-src 'none'; script-src 'nonce-{script_nonce}'; style-src 'nonce-{script_nonce}'; base-uri 'none'; frame-ancestors 'none'"
        )
        data = json.dumps(message).replace("<", "\\u003c").replace(">", "\\u003e")
        return HTMLResponse(
            f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mnemion · Company sign-in</title><style nonce="{script_nonce}">body{{margin:0;background:#080c12;color:#eae7df;font:16px system-ui;display:grid;min-height:100vh;place-items:center}}main{{max-width:32rem;padding:2rem}}h1{{color:#c5a05d}}</style>
<main><h1>Mnemion</h1><p id="status">Return to Mnemion to finish company sign-in.</p></main>
<script nonce="{script_nonce}">history.replaceState(null,'','/company/callback');if(typeof BroadcastChannel!=='undefined'){{const channel=new BroadcastChannel('mnemion-company:'+{data}.state);channel.postMessage({data});channel.close();document.getElementById('status').textContent='You can return to Mnemion and close this window.';}}</script></html>""",
            headers=headers,
        )
