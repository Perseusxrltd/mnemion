"""Authenticated MCP transport and privacy-preserving, structured tool errors."""

from __future__ import annotations

import logging
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
from .models import SCOPE_SELECTION_MESSAGE

logger = logging.getLogger(__name__)


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

    def __init__(self, app, authenticate):
        self.app = app
        self.authenticate = authenticate
        self.capacity = anyio.CapacityLimiter(32)

    async def reject(self, scope, receive, send, status, code, message):
        headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        if status == 401:
            headers["WWW-Authenticate"] = 'Bearer realm="Mnemion"'
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
                "Send your own Mnemion API key as a Bearer token.",
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
                    scope, receive, send, 401, "unauthorized", "The API key is invalid or revoked."
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
    )


class MnemionMCPServer(MCPServer):
    def __init__(self, *args, api_url, api_app=None, public_url=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_url = (
            "http://mnemion.internal"
            if api_app is not None
            else api_url.rstrip("/").removesuffix("/v1")
        )
        self.api_app = api_app
        self.public_url = public_url
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
        app = super().streamable_http_app(**kwargs)
        app.add_middleware(BodyLimitMiddleware)
        app.add_middleware(MCPBearerMiddleware, authenticate=self.authenticate)
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
                    )
                if isinstance(cause, ValidationError):
                    errors = cause.errors()
                    fields = [
                        {
                            "field": ".".join(str(part) for part in row["loc"])[:200],
                            "type": row["type"],
                        }
                        for row in errors[:20]
                    ]
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
