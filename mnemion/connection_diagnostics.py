"""Bounded, read-only connection checks with a deliberately content-free report."""

from __future__ import annotations

import asyncio
import json
import ssl
from collections import Counter

import httpx

MAX_BYTES = 128 * 1024
DEADLINE_SECONDS = 25
PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
ROLES = {"reader", "contributor", "reviewer", "administrator"}
HINTS = {
    "tunnel_offline": "The tunnel is offline. Use the host's operator controls to restart its network connection and Mnemion; changing the memory key will not repair an offline tunnel.",
    "network_error": "The host could not be reached. Check its address, network or VPN, and independent host-management access.",
    "tls_error": "The TLS connection could not be verified. Repair the host's certificate or trusted company certificate configuration; do not disable verification.",
    "timeout": "The host did not answer within the connection-check budget. Check the host and network, then retry.",
    "redirect": "The address redirected elsewhere. Use the final Mnemion HTTPS address; credentials were not forwarded to the redirect.",
    "unauthorized": "The service rejected the credential. Ask the workspace administrator for current individual access.",
    "forbidden": "The credential lacks permission for this check. Ask the workspace administrator to review its access.",
    "not_found": "A required route was not found. Check the workspace base address and API/MCP proxy routing.",
    "invalid_response": "This route did not return the expected Mnemion or MCP response. Check proxy sign-in pages, routing and service compatibility.",
    "response_too_large": "The response exceeded the diagnostic size limit; no content was included in this report.",
    "not_ready": "The service answered but did not report readiness. Check the service and database through the host's operator controls.",
    "http_error": "The host returned an HTTP error. Check its service status through the host's operator controls.",
    "no_credentials": "Public health checks only. Supply a private credentials file to verify identity, space access and MCP tools.",
    "no_spaces": "The credential is valid but has no accessible spaces. An administrator must grant the intended space access.",
}


class ProbeError(Exception):
    def __init__(self, code: str, status: int | None = None):
        self.code, self.status = code, status


def _json(data: bytes):
    try:
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise ProbeError("invalid_response") from None


async def _request(client, method, path, *, key=None, body=None, headers=None, rpc_id=None):
    request_headers = {
        "Accept": "application/json, text/event-stream",
        "Accept-Encoding": "identity",
    }
    if key:
        request_headers["Authorization"] = "Bearer " + key
    request_headers.update(headers or {})
    try:
        async with client.stream(method, path, headers=request_headers, json=body) as response:
            status = response.status_code
            if response.headers.get("ngrok-error-code") == "ERR_NGROK_3200":
                raise ProbeError("tunnel_offline", status)
            if 300 <= status < 400:
                raise ProbeError("redirect", status)
            if status in {401, 403, 404}:
                raise ProbeError(
                    {401: "unauthorized", 403: "forbidden", 404: "not_found"}[status], status
                )
            if not 200 <= status < 300:
                raise ProbeError(
                    "not_ready" if path.endswith("/health/ready") else "http_error", status
                )
            if response.headers.get("content-encoding", "identity") != "identity":
                raise ProbeError("invalid_response", status)
            # Initialization notifications and ephemeral session cleanup have no payload.
            if method == "DELETE" or (body and "id" not in body):
                return {}, response.headers
            length = response.headers.get("content-length", "")
            if length.isdecimal() and (len(length) > 10 or int(length) > MAX_BYTES):
                raise ProbeError("response_too_large", status)
            data = bytearray()
            is_sse = (
                response.headers.get("content-type", "").split(";", 1)[0] == "text/event-stream"
            )
            processed = 0
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise ProbeError("response_too_large", status)
                if is_sse:
                    # Stop at the matching response; a stateful server may leave SSE open.
                    frames = bytes(data).replace(b"\r\n", b"\n").split(b"\n\n")
                    for frame in frames[processed:-1]:
                        payload = b"\n".join(
                            line[5:].lstrip(b" ")
                            for line in frame.splitlines()
                            if line.startswith(b"data:")
                        )
                        if payload:
                            message = _json(payload)
                            if message.get("id") == rpc_id:
                                return message, response.headers
                    processed = len(frames) - 1
            if is_sse:
                raise ProbeError("invalid_response", status)
            return _json(data), response.headers
    except httpx.TimeoutException:
        raise ProbeError("timeout") from None
    except httpx.HTTPError as error:
        cause: BaseException | None = error
        while cause is not None:
            if isinstance(cause, ssl.SSLError):
                raise ProbeError("tls_error") from None
            cause = cause.__cause__
        raise ProbeError("network_error") from None


async def diagnose(address: str, key: str | None, *, transport=None) -> dict:
    """Never return a URL, credential, identity, memory, arbitrary header or server text."""
    checks: dict[str, dict] = {}
    stage = "service"
    report = {"format": 1, "ready": False, "checks": checks}

    def failed(name: str, error: ProbeError):
        checks[name] = {"ok": False, "code": error.code}
        if error.status is not None:
            checks[name]["http_status"] = error.status

    async def health(client, name, path, expected):
        try:
            value, _ = await _request(client, "GET", address + path)
            if value.get("status") != expected or (
                name == "service" and value.get("api_version") != "v1"
            ):
                raise ProbeError("invalid_response", 200)
            checks[name] = {"ok": True, "code": "ok"}
        except ProbeError as error:
            failed(name, error)
            # Don't repeatedly hit a known offline tunnel, or a redirect's destination.
            if error.code in {
                "tunnel_offline",
                "redirect",
                "network_error",
                "tls_error",
                "timeout",
            }:
                raise

    try:
        async with asyncio.timeout(DEADLINE_SECONDS):
            async with httpx.AsyncClient(
                timeout=5, follow_redirects=False, transport=transport
            ) as client:
                await health(client, "service", "/health/live", "alive")
                stage = "readiness"
                await health(client, "readiness", "/health/ready", "ready")
                if key:
                    stage = "identity"
                    value, _ = await _request(client, "GET", address + "/v1/me", key=key)
                    if not all(
                        isinstance(value.get(field), str) and value[field]
                        for field in ("principal_id", "tenant_id", "name", "tenant_name")
                    ) or not isinstance(value.get("administrator"), bool):
                        raise ProbeError("invalid_response", 200)
                    checks[stage] = {
                        "ok": True,
                        "code": "ok",
                        "administrator": value["administrator"],
                    }
                    stage = "spaces"
                    value, _ = await _request(client, "GET", address + "/v1/spaces", key=key)
                    items = value.get("items")
                    if not isinstance(items, list) or any(
                        not isinstance(item, dict)
                        or not isinstance(item.get("role"), str)
                        or item["role"] not in ROLES
                        for item in items
                    ):
                        raise ProbeError("invalid_response", 200)
                    checks[stage] = {
                        "ok": bool(items),
                        "code": "ok" if items else "no_spaces",
                        "count": len(items),
                        "roles": dict(Counter(item["role"] for item in items)),
                    }
                    stage = "mcp"
                    session = {}
                    try:
                        value, headers = await _request(
                            client,
                            "POST",
                            address + "/mcp",
                            key=key,
                            rpc_id=1,
                            body={
                                "jsonrpc": "2.0",
                                "id": 1,
                                "method": "initialize",
                                "params": {
                                    "protocolVersion": "2025-06-18",
                                    "capabilities": {},
                                    "clientInfo": {"name": "mnemion-doctor", "version": "1"},
                                },
                            },
                        )
                        result = value.get("result")
                        if (
                            value.get("id") != 1
                            or value.get("jsonrpc") != "2.0"
                            or "error" in value
                            or not isinstance(result, dict)
                            or not isinstance(result.get("protocolVersion"), str)
                            or result.get("protocolVersion") not in PROTOCOLS
                        ):
                            raise ProbeError("invalid_response", 200)
                        protocol = result["protocolVersion"]
                        session["MCP-Protocol-Version"] = protocol
                        if token := headers.get("mcp-session-id"):
                            if len(token) > 1024 or not all(
                                33 <= ord(char) <= 126 for char in token
                            ):
                                raise ProbeError("invalid_response", 200)
                            session["Mcp-Session-Id"] = token
                        await _request(
                            client,
                            "POST",
                            address + "/mcp",
                            key=key,
                            headers=session,
                            body={"jsonrpc": "2.0", "method": "notifications/initialized"},
                        )
                        value, _ = await _request(
                            client,
                            "POST",
                            address + "/mcp",
                            key=key,
                            headers=session,
                            rpc_id=2,
                            body={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                        )
                        result = value.get("result")
                        if (
                            value.get("id") != 2
                            or value.get("jsonrpc") != "2.0"
                            or "error" in value
                            or not isinstance(result, dict)
                            or not isinstance(result.get("tools"), list)
                            or any(
                                not isinstance(tool, dict) or not isinstance(tool.get("name"), str)
                                for tool in result["tools"]
                            )
                        ):
                            raise ProbeError("invalid_response", 200)
                        checks[stage] = {
                            "ok": True,
                            "code": "ok",
                            "protocol": protocol,
                            "tool_count": len(result["tools"]),
                            "more_tools": bool(result.get("nextCursor")),
                        }
                    finally:
                        if "Mcp-Session-Id" in session:
                            try:
                                await _request(
                                    client, "DELETE", address + "/mcp", key=key, headers=session
                                )
                            except ProbeError:
                                pass  # Optional ephemeral-session cleanup never hides the check.
                else:
                    for stage in ("identity", "spaces", "mcp"):
                        checks[stage] = {"ok": False, "code": "no_credentials", "skipped": True}
    except ProbeError as error:
        failed(stage, error)
    except TimeoutError:
        failed(stage, ProbeError("timeout"))
    for name in ("service", "readiness", "identity", "spaces", "mcp"):
        checks.setdefault(name, {"ok": False, "code": "not_checked", "skipped": True})
    report["ready"] = all(item["ok"] for item in checks.values())
    report["guidance"] = list(
        dict.fromkeys(HINTS[item["code"]] for item in checks.values() if item["code"] in HINTS)
    )
    return report
