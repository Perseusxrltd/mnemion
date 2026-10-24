"""Authenticated MCP transport and privacy-preserving, structured tool errors."""

from __future__ import annotations

import logging
import hashlib
import hmac
import os
import time
from urllib.parse import urlsplit
from uuid import uuid4

import anyio
import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent
from pydantic import ValidationError
from starlette.responses import JSONResponse

from ..sdk import Client, MnemionError
from ..validation_fields import safe_fields, schema_names
from .models import SCOPE_SELECTION_MESSAGE
from .oauth import OAUTH_SCOPE

logger = logging.getLogger(__name__)


def compact_schema(schema):
    """Remove explanatory schema metadata without changing validation keywords."""
    if not isinstance(schema, dict):
        return schema
    maps = {"properties", "$defs", "definitions", "patternProperties", "dependentSchemas"}
    singles = {
        "items",
        "additionalProperties",
        "contains",
        "not",
        "if",
        "then",
        "else",
        "propertyNames",
        "unevaluatedProperties",
    }
    sequences = {"anyOf", "oneOf", "allOf", "prefixItems"}
    result = {}
    for key, value in schema.items():
        if key in {"description", "title", "examples"}:
            continue
        if key in maps and isinstance(value, dict):
            value = {name: compact_schema(item) for name, item in value.items()}
        elif key in singles:
            value = compact_schema(value)
        elif key in sequences and isinstance(value, list):
            value = [compact_schema(item) for item in value]
        result[key] = value
    return result


async def compact_tool_metadata(ctx, call_next):
    result = await call_next(ctx)
    if ctx.method != "tools/list" or not isinstance(result, dict):
        return result
    descriptions = {
        "search": "Search authorized memory. Omit space_ids to use current accessible spaces.",
        "fetch": "Fetch a memory and its source evidence by memory_id.",
        "mnemion": "List operations (query, offset/next_offset), describe one, or explicitly read/write with operation and request. Private credentials require the CLI.",
        "memory_profile": "Identify the current account and workspace.",
    }
    tools = {tool["name"]: tool for tool in result.get("tools", [])}
    # Keep optional local privacy and vault tools discoverable only when the
    # actual transport/configuration registered them on this server.
    for name, description in {
        "mnemion_telemetry": "Local stdio only: disclose and control optional anonymous product counts; disable or re-enable while offline.",
        "vault_list": "List permitted credential names only; no values.",
        "vault_get": "Explicit sensitive credential read. Requires a vault grant; do not copy the value into memory.",
        "vault_put": "Encrypt a credential at its expected version. Creation requires administrator authority.",
    }.items():
        if name in tools:
            descriptions[name] = description
    compact = []
    for name, description in descriptions.items():
        tool = tools[name]
        compact.append(
            {
                **{
                    key: value
                    for key, value in tool.items()
                    if key not in {"outputSchema", "description", "title"}
                },
                "description": description,
                "inputSchema": compact_schema(tool["inputSchema"]),
            }
        )
    return {**result, "tools": compact}


class MCPSessionBindings:
    """Bind native SDK sessions to the bearer that created them; never cache access."""

    def __init__(self, app, *, maximum=128, idle_seconds=900):
        self.app = app
        self.maximum = maximum
        self.idle_seconds = idle_seconds
        self.bindings = {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = scope.get("headers", [])
        sessions = [value for name, value in headers if name.lower() == b"mcp-session-id"]
        credentials = [value for name, value in headers if name.lower() == b"authorization"]
        now = time.monotonic()
        self.bindings = {
            key: value for key, value in self.bindings.items() if now - value[1] < self.idle_seconds
        }
        session = sessions[0] if len(sessions) == 1 and 1 <= len(sessions[0]) <= 128 else None
        owner = hashlib.sha256(credentials[0]).digest() if len(credentials) == 1 else None
        binding = self.bindings.get(session)
        if sessions and (
            session is None
            or binding is None
            or owner is None
            or not hmac.compare_digest(binding[0], owner)
        ):
            return await JSONResponse(
                {
                    "error": {
                        "code": "mcp_session_unavailable",
                        "message": "Initialize a new MCP session with your current credential.",
                    }
                },
                status_code=404,
                headers={"Cache-Control": "no-store"},
            )(scope, receive, send)
        if not sessions and len(self.bindings) >= self.maximum:
            return await JSONResponse(
                {
                    "error": {
                        "code": "mcp_session_capacity",
                        "message": "The session limit is reached; retry shortly.",
                    }
                },
                status_code=503,
                headers={"Cache-Control": "no-store", "Retry-After": "1"},
            )(scope, receive, send)
        if session is not None:
            self.bindings[session] = (owner, now)

        async def bound_send(message):
            if message["type"] == "http.response.start":
                status = message["status"]
                if session is not None and (
                    status == 404 or (scope["method"] == "DELETE" and 200 <= status < 300)
                ):
                    self.bindings.pop(session, None)
                elif 200 <= status < 300:
                    for name, value in message.get("headers", []):
                        if name.lower() == b"mcp-session-id" and owner is not None:
                            self.bindings[value] = (owner, time.monotonic())
            await send(message)

        await self.app(scope, receive, bound_send)


async def oauth_tool_metadata(ctx, call_next):
    """Add the OpenAI auth extension after the SDK's core-protocol field sieve.

    Use the SDK's public middleware interface: typed Tool serialization and
    protocol-version conversion otherwise discard unknown top-level fields.
    """
    result = await call_next(ctx)
    if ctx.method == "tools/list" and isinstance(result, dict):
        schemes = [{"type": "oauth2", "scopes": [OAUTH_SCOPE]}]
        return {
            **result,
            "tools": [
                {
                    **tool,
                    "securitySchemes": schemes,
                    "_meta": {**(tool.get("_meta") or {}), "securitySchemes": schemes},
                }
                for tool in result.get("tools", [])
            ],
        }
    return result


def transport_security(public_url: str | None) -> TransportSecuritySettings:
    hosts = ["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "[::1]", "[::1]:*"]
    origins = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
    if public_url:
        try:
            url = urlsplit(public_url)
            hostname = (url.hostname or "").encode("idna").decode("ascii")
            port = url.port
        except (ValueError, UnicodeError):
            raise ValueError("Configure a valid public HTTPS origin for MCP") from None
        if (
            len(public_url) > 2048
            or not hostname
            or url.scheme not in {"https", "http"}
            or (url.scheme == "http" and hostname not in {"localhost", "127.0.0.1", "::1"})
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or url.path not in {"", "/", "/mcp", "/mcp/"}
            or (port is not None and not 1 <= port <= 65535)
            or any(character.isspace() or ord(character) < 33 for character in public_url)
            or any(character in public_url for character in ("\\", "*"))
        ):
            raise ValueError(
                "MCP public URL must be an HTTPS origin without credentials or query parameters"
            )
        authority = f"[{hostname}]" if ":" in hostname else hostname
        if port is not None:
            authority += f":{port}"
        hosts.append(authority)
        origins.append(f"{url.scheme}://{authority}")
        if (url.scheme, port) in {("https", 443), ("http", 80)}:
            hosts.append(hostname)
            origins.append(f"{url.scheme}://{hostname}")
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins
    )


class InProcessAPITransport(httpx.BaseTransport):
    """Run the same HTTP authorization/validation contract without a loopback socket.

    MCP tool functions run in a separate bounded AnyIO worker pool. Internal API
    dependencies therefore cannot deadlock behind the gateway's worker threads.
    This transport is for bounded JSON tools; bulk exports remain on HTTP/CLI.
    """

    def __init__(self, app, *, maximum=2_000_000):
        self.app = app
        self.maximum = maximum

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body = request.read()

        async def dispatch():
            size, exceeded = 0, False

            async def bounded(scope, receive, send):
                async def bounded_send(message):
                    nonlocal size, exceeded
                    if message["type"] == "http.response.body":
                        size += len(message.get("body", b""))
                        if size > self.maximum:
                            exceeded = True
                            raise httpx.ReadError(
                                "The internal API response exceeds its byte limit"
                            )
                    await send(message)

                await self.app(scope, receive, bounded_send)

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=bounded, raise_app_exceptions=False),
                follow_redirects=False,
            ) as client:
                response = await client.request(
                    request.method, request.url, headers=request.headers, content=body
                )
                if exceeded:
                    raise httpx.ReadError("The internal API response exceeds its byte limit")
                return httpx.Response(
                    response.status_code,
                    headers=response.headers,
                    content=response.content,
                    request=request,
                )

        return anyio.from_thread.run(dispatch)


class MCPBearerMiddleware:
    """Authenticate every HTTP request, including initialize and tools/list."""

    def __init__(self, app, authenticate, oauth_settings=None):
        self.app = app
        self.authenticate = authenticate
        self.oauth_settings = oauth_settings
        self.capacity = anyio.CapacityLimiter(32)

    async def reject(self, scope, receive, send, status, code, message):
        headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        if status == 401:
            headers["WWW-Authenticate"] = (
                self.oauth_settings.challenge("invalid_token")
                if self.oauth_settings
                else 'Bearer realm="Mnemion"'
            )
        if status == 403 and self.oauth_settings:
            headers["WWW-Authenticate"] = self.oauth_settings.challenge("insufficient_scope")
        if status == 503:
            headers["Retry-After"] = "1"
        response = JSONResponse(
            {"error": {"code": code, "message": message}, "request_id": str(uuid4())},
            status_code=status,
            headers=headers,
        )
        await response(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if (
            self.oauth_settings
            and scope.get("path")
            in {
                "/.well-known/oauth-protected-resource",
                "/.well-known/oauth-protected-resource/mcp",
            }
            and scope.get("method") in {"GET", "HEAD"}
        ):
            return await JSONResponse(
                self.oauth_settings.metadata(), headers={"Cache-Control": "no-store"}
            )(scope, receive, send)
        headers = [
            value for name, value in scope.get("headers", []) if name.lower() == b"authorization"
        ]
        token = None
        if len(headers) == 1 and 8 <= len(headers[0]) <= 4096:
            scheme, _, value = headers[0].partition(b" ")
            if scheme.lower() == b"bearer" and value and all(33 <= byte <= 126 for byte in value):
                token = value.decode("ascii")
        if token is None:
            return await self.reject(
                scope,
                receive,
                send,
                401,
                "unauthorized",
                "Send your own Mnemion access token as a Bearer token.",
            )
        try:
            self.capacity.acquire_nowait()
        except anyio.WouldBlock:
            return await self.reject(
                scope, receive, send, 503, "mcp_busy", "The gateway is busy; retry shortly."
            )
        try:
            try:
                with anyio.fail_after(5):
                    status = await self.authenticate(token)
            except (TimeoutError, httpx.HTTPError):
                status = 503
            if status == 401:
                return await self.reject(
                    scope,
                    receive,
                    send,
                    401,
                    "unauthorized",
                    "The access token is invalid, expired or revoked.",
                )
            if status == 403:
                return await self.reject(
                    scope,
                    receive,
                    send,
                    403,
                    "insufficient_scope",
                    "The token requires the mnemion:access scope.",
                )
            if status != 200:
                return await self.reject(
                    scope,
                    receive,
                    send,
                    503,
                    "service_unavailable",
                    "The memory service is temporarily unavailable.",
                )
            await self.app(scope, receive, send)
        finally:
            self.capacity.release()


def tool_error(
    code,
    message,
    *,
    status=None,
    request_id=None,
    fields=None,
    retry_after=None,
    outcome=None,
    retryable=None,
    challenge=None,
):
    data = {
        "code": code,
        "message": message,
        "retryable": status in {408, 429, 502, 503, 504} if retryable is None else retryable,
        "request_id": request_id,
    }
    if fields:
        data["fields"] = fields
    if retry_after is not None:
        data["retry_after_seconds"] = retry_after
    if outcome is not None:
        data["outcome"] = outcome
    return CallToolResult(
        is_error=True,
        structured_content=data,
        content=[TextContent(type="text", text=f"{code}: {message}")],
        _meta={"mcp/www_authenticate": [challenge]} if challenge else None,
    )


class MnemionMCPServer(MCPServer):
    def __init__(
        self, *args, api_url, api_app=None, public_url=None, oauth_settings=None, **kwargs
    ):
        profile = os.environ.get("MNEMION_MCP_TOOL_PROFILE", "full")
        if profile not in {"full", "compact"}:
            raise ValueError("MNEMION_MCP_TOOL_PROFILE must be full or compact")
        self.tool_profile = profile
        if profile == "compact":
            kwargs["middleware"] = [*(kwargs.get("middleware") or []), compact_tool_metadata]
        if oauth_settings:
            kwargs["middleware"] = [*(kwargs.get("middleware") or []), oauth_tool_metadata]
        super().__init__(*args, **kwargs)
        self.api_url = (
            "http://mnemion.internal"
            if api_app is not None
            else api_url.rstrip("/").removesuffix("/v1")
        )
        self.api_app = api_app
        self.public_url = public_url
        self.oauth_settings = oauth_settings
        self.worker_capacity = anyio.CapacityLimiter(8)
        # Validate configuration during startup, never on an agent's first call.
        self.transport_security = transport_security(public_url)

    def api_client(self, token):
        return Client(
            self.api_url,
            token,
            transport=InProcessAPITransport(self.api_app) if self.api_app is not None else None,
        )

    async def authenticate(self, token):
        async with httpx.AsyncClient(
            base_url=self.api_url,
            headers={"Authorization": "Bearer " + token},
            transport=httpx.ASGITransport(app=self.api_app, raise_app_exceptions=False)
            if self.api_app is not None
            else None,
            timeout=5,
            follow_redirects=False,
        ) as client:
            return (await client.get("/v1/me")).status_code

    def streamable_http_app(self, **kwargs):
        from .api import BodyLimitMiddleware

        if kwargs.get("transport_security") is None:
            kwargs["transport_security"] = self.transport_security
        kwargs["max_request_body_size"] = min(
            kwargs.get("max_request_body_size", 2_000_000), 2_000_000
        )
        sessions = os.environ.get("MNEMION_MCP_SESSIONS", "0")
        if sessions not in {"0", "1"}:
            raise ValueError("MNEMION_MCP_SESSIONS must be 0 or 1")
        if sessions == "1":
            kwargs["stateless_http"] = False
        if not kwargs.get("stateless_http", False):
            kwargs["max_sessions"] = 128
            kwargs["session_idle_timeout"] = 900
        app = super().streamable_http_app(**kwargs)
        app.add_middleware(BodyLimitMiddleware)
        if not kwargs.get("stateless_http", False):
            app.add_middleware(
                MCPSessionBindings,
                maximum=kwargs.get("max_sessions", 128),
                idle_seconds=kwargs.get("session_idle_timeout", 900),
            )
        app.add_middleware(
            MCPBearerMiddleware, authenticate=self.authenticate, oauth_settings=self.oauth_settings
        )
        return app

    async def call_tool(self, name, arguments, context=None):
        try:
            return await super().call_tool(name, arguments, context)
        except ToolError as error:
            cause = error
            # The maintained SDK wraps validation/tool failures. Never send its
            # raw Pydantic diagnostic, submitted values or HTTP exception text.
            for _ in range(8):
                if isinstance(cause, MnemionError):
                    return tool_error(
                        cause.code,
                        str(cause),
                        status=cause.status,
                        request_id=cause.request_id,
                        retry_after=getattr(cause, "retry_after", None),
                        outcome=getattr(cause, "outcome", None),
                        retryable=cause.retryable,
                        challenge=self.oauth_settings.challenge(cause.code)
                        if self.oauth_settings
                        and (cause.status == 401 or cause.code == "insufficient_scope")
                        else None,
                    )
                if isinstance(cause, ValidationError):
                    errors = cause.errors(
                        include_input=False, include_context=False, include_url=False
                    )
                    schema = next(
                        (
                            tool.input_schema
                            for tool in await self.list_tools()
                            if tool.name == name
                        ),
                        {},
                    )
                    fields = safe_fields(errors, schema_names(schema))
                    message = (
                        SCOPE_SELECTION_MESSAGE
                        if any(row["type"] == "memory_scope" for row in errors)
                        else "Check the named arguments against the tool schema."
                    )
                    return tool_error("invalid_arguments", message, fields=fields)
                if isinstance(cause, httpx.HTTPError):
                    return tool_error(
                        "service_unavailable",
                        "The memory service is temporarily unavailable.",
                        status=503,
                        retry_after=1,
                    )
                if cause.__cause__ is None:
                    break
                cause = cause.__cause__
            logger.warning("MCP tool failed (%s)", type(cause).__name__)
            return tool_error(
                "tool_error", "The tool call could not be completed; check its name and arguments."
            )
