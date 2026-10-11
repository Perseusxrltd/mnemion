"""Diagnostics must distinguish host failures without exposing connection contents."""

import asyncio
import json

import httpx
import pytest

from mnemion import connection_diagnostics as doctor
from mnemion import control_cli
from mnemion.agent_control import ControlError

SECRET = "fixture-private-key-never-print"
PRIVATE = "fixture-private-workspace-name"


def successful(request):
    assert not request.url.path.startswith("/health") or "authorization" not in request.headers
    if request.url.path.endswith("/health/live"):
        return httpx.Response(200, json={"status": "alive", "api_version": "v1"})
    if request.url.path.endswith("/health/ready"):
        return httpx.Response(200, json={"status": "ready", "generation_id": PRIVATE})
    assert request.headers["authorization"] == "Bearer " + SECRET
    if request.url.path.endswith("/v1/me"):
        return httpx.Response(
            200,
            json={
                "principal_id": PRIVATE,
                "tenant_id": PRIVATE,
                "name": SECRET,
                "tenant_name": PRIVATE,
                "administrator": False,
            },
        )
    if request.url.path.endswith("/v1/spaces"):
        return httpx.Response(
            200, json={"items": [{"name": SECRET, "id": PRIVATE, "role": "contributor"}]}
        )
    assert request.url.path.endswith("/mcp")
    if request.method == "DELETE":
        return httpx.Response(204)
    payload = json.loads(request.content)
    if payload["method"] == "initialize":
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "serverInfo": {"name": PRIVATE},
                    "capabilities": {"tools": {}},
                },
            },
        )
    if payload["method"] == "notifications/initialized":
        return httpx.Response(202)
    assert payload["method"] == "tools/list"
    return httpx.Response(
        200, json={"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": SECRET}]}}
    )


@pytest.mark.parametrize("roles,accessible", [([None], 0), ([None, "reader"], 1), ([], 0)])
def test_ungranted_administrative_spaces_are_valid_without_implying_memory_access(
    roles, accessible
):
    def handler(request):
        if request.url.path.endswith("/v1/spaces"):
            return httpx.Response(
                200,
                json={"items": [{"id": PRIVATE, "name": SECRET, "role": role} for role in roles]},
            )
        return successful(request)

    report = asyncio.run(
        doctor.diagnose(
            "https://private.example.invalid", SECRET, transport=httpx.MockTransport(handler)
        )
    )
    assert report["ready"] is bool(accessible)
    assert report["checks"]["spaces"] == {
        "ok": bool(accessible),
        "code": "ok" if accessible else "no_spaces",
        "count": len(roles),
        "accessible_count": accessible,
        "roles": {"reader": 1} if accessible else {},
    }
    assert report["checks"]["mcp"]["ok"]
    assert PRIVATE not in json.dumps(report) and SECRET not in json.dumps(report)


@pytest.mark.parametrize("item", [{}, {"role": "owner"}, {"role": []}, {"role": False}])
def test_missing_or_malformed_roles_remain_invalid(item):
    def handler(request):
        if request.url.path.endswith("/v1/spaces"):
            return httpx.Response(200, json={"items": [item]})
        return successful(request)

    report = asyncio.run(
        doctor.diagnose("https://test.invalid", SECRET, transport=httpx.MockTransport(handler))
    )
    assert report["checks"]["spaces"]["code"] == "invalid_response"
    assert not report["ready"]


def test_success_reports_only_validated_statuses_counts_and_roles():
    calls = []

    def handler(request):
        calls.append(request)
        return successful(request)

    report = asyncio.run(
        doctor.diagnose(
            "https://private.example.invalid", SECRET, transport=httpx.MockTransport(handler)
        )
    )
    assert report["ready"]
    assert len(calls) == 7
    assert report["checks"]["spaces"]["roles"] == {"contributor": 1}
    assert report["checks"]["mcp"]["tool_count"] == 1
    serialized = json.dumps(report)
    for private in (SECRET, PRIVATE, "private.example.invalid"):
        assert private not in serialized


def test_authenticated_gateway_health_checks_reuse_only_the_supplied_destination():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.startswith("/health"):
            if "authorization" not in request.headers:
                return httpx.Response(401, text=SECRET + PRIVATE)
            assert request.headers["authorization"] == "Bearer " + SECRET
            public_request = httpx.Request(request.method, request.url)
            return successful(public_request)
        return successful(request)

    report = asyncio.run(
        doctor.diagnose(
            "https://private.example.invalid", SECRET, transport=httpx.MockTransport(handler)
        )
    )
    assert report["ready"] and len(calls) == 9
    assert {request.url.host for request in calls} == {"private.example.invalid"}
    assert all(report["checks"][name]["ok"] for name in ("service", "readiness", "identity"))
    for private in (SECRET, PRIVATE, "private.example.invalid"):
        assert private not in json.dumps(report)


def test_protected_health_without_a_key_reports_authentication_required():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401, text=SECRET)

    report = asyncio.run(
        doctor.diagnose("https://test.invalid", None, transport=httpx.MockTransport(handler))
    )
    assert not report["ready"] and len(calls) == 2
    assert all("authorization" not in request.headers for request in calls)
    for name in ("service", "readiness"):
        assert report["checks"][name] == {
            "ok": False,
            "code": "authentication_required",
            "http_status": 401,
        }
    assert report["checks"]["identity"]["skipped"]
    assert doctor.HINTS["authentication_required"] in report["guidance"]
    assert doctor.HINTS["unauthorized"] not in report["guidance"]
    assert SECRET not in json.dumps(report)


@pytest.mark.parametrize("status,code", [(401, "unauthorized"), (403, "forbidden")])
def test_protected_health_rejection_does_not_claim_readiness(status, code):
    def handler(request):
        if request.url.path.startswith("/health"):
            return httpx.Response(status if "authorization" in request.headers else 401)
        return successful(request)

    report = asyncio.run(
        doctor.diagnose("https://test.invalid", SECRET, transport=httpx.MockTransport(handler))
    )
    assert not report["ready"]
    assert report["checks"]["identity"]["ok"]
    for name in ("service", "readiness"):
        assert report["checks"][name]["code"] == code
        assert report["checks"][name]["http_status"] == status


def test_authenticated_health_redirect_is_never_followed():
    calls = []

    def handler(request):
        calls.append(request)
        if "authorization" not in request.headers:
            return httpx.Response(401)
        return httpx.Response(302, headers={"location": "https://other.invalid/" + SECRET})

    report = asyncio.run(
        doctor.diagnose("https://test.invalid", SECRET, transport=httpx.MockTransport(handler))
    )
    assert not report["ready"] and len(calls) == 2
    assert {str(request.url) for request in calls} == {"https://test.invalid/health/live"}
    assert "authorization" not in calls[0].headers
    assert calls[1].headers["authorization"] == "Bearer " + SECRET
    assert report["checks"]["service"]["code"] == "redirect"
    assert report["checks"]["identity"]["skipped"]
    assert SECRET not in json.dumps(report)


@pytest.mark.parametrize(
    "status,headers,code",
    [
        (404, {"ngrok-error-code": "ERR_NGROK_3200"}, "tunnel_offline"),
        (302, {"location": "https://other.example.invalid/" + SECRET}, "redirect"),
    ],
)
def test_offline_tunnel_and_redirect_stop_before_sending_any_credential(status, headers, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers=headers, text=SECRET + PRIVATE)

    report = asyncio.run(
        doctor.diagnose(
            "https://private.example.invalid", SECRET, transport=httpx.MockTransport(handler)
        )
    )
    assert not report["ready"] and len(calls) == 1
    assert "authorization" not in calls[0].headers
    assert report["checks"]["service"]["code"] == code
    assert SECRET not in json.dumps(report) and PRIVATE not in json.dumps(report)


@pytest.mark.parametrize(
    "status,code", [(401, "unauthorized"), (403, "forbidden"), (200, "invalid_response")]
)
def test_auth_failure_is_distinct_from_an_online_host(status, code):
    def handler(request):
        if request.url.path.endswith("/v1/me"):
            return httpx.Response(status, text=SECRET)
        return successful(request)

    report = asyncio.run(
        doctor.diagnose(
            "https://private.example.invalid", SECRET, transport=httpx.MockTransport(handler)
        )
    )
    assert report["checks"]["readiness"]["ok"]
    assert report["checks"]["identity"]["code"] == code
    assert report["checks"]["mcp"]["skipped"]
    assert SECRET not in json.dumps(report)


def test_public_checks_do_not_claim_authenticated_readiness():
    report = asyncio.run(
        doctor.diagnose("http://127.0.0.1:7892", None, transport=httpx.MockTransport(successful))
    )
    assert report["checks"]["service"]["ok"]
    assert report["checks"]["identity"]["code"] == "no_credentials"
    assert not report["ready"]


def test_streamed_payload_limit_and_peer_trickling_are_bounded(monkeypatch):
    class Oversized(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(40):
                yield b"x" * 4096

    report = asyncio.run(
        doctor.diagnose(
            "https://test.invalid",
            None,
            transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Oversized())),
        )
    )
    assert report["checks"]["service"]["code"] == "response_too_large"

    class Trickle(httpx.AsyncByteStream):
        async def __aiter__(self):
            while True:
                await asyncio.sleep(0.002)
                yield b" "

    monkeypatch.setattr(doctor, "DEADLINE_SECONDS", 0.03)
    report = asyncio.run(
        doctor.diagnose(
            "https://test.invalid",
            None,
            transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Trickle())),
        )
    )
    assert report["checks"]["service"]["code"] == "timeout"


def test_open_sse_is_consumed_promptly_and_private_session_is_cleaned_up():
    closed = []
    methods = []

    class Events(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b': ping\r\n\r\ndata: {"jsonrpc":"2.0","id":2,"result":{"tools":[]}}\r\n\r\n'
            raise AssertionError("The doctor must close SSE immediately after its response")

        async def aclose(self):
            closed.append(True)

    def handler(request):
        if request.url.path == "/mcp":
            if request.method == "DELETE":
                methods.append("DELETE")
                assert request.headers["mcp-session-id"] == SECRET
                return httpx.Response(204)
            method = json.loads(request.content)["method"]
            methods.append(method)
            if method == "initialize":
                response = successful(request)
                response.headers["mcp-session-id"] = SECRET
                return response
            assert request.headers["mcp-session-id"] == SECRET
            if method == "tools/list":
                return httpx.Response(
                    200, headers={"content-type": "text/event-stream"}, stream=Events()
                )
        return successful(request)

    report = asyncio.run(
        doctor.diagnose("https://test.invalid", SECRET, transport=httpx.MockTransport(handler))
    )
    assert report["ready"] and closed and methods[-1] == "DELETE"
    assert SECRET not in json.dumps(report)


def test_cli_accepts_api_or_mcp_addresses_but_rejects_unsafe_credentials_urls(monkeypatch):
    monkeypatch.delenv("MNEMION_API_KEY", raising=False)
    for suffix in ("/mcp", "/v1/", "/"):
        assert control_cli.connection(
            None, "https://test.invalid/team" + suffix, require_key=False
        ) == ("https://test.invalid/team", None)
    assert control_cli.connection(None, "https://test.invalid/mcp/v1", require_key=False) == (
        "https://test.invalid/mcp",
        None,
    )
    for address in (
        "http://test.invalid",
        "https://test.invalid/?key=secret",
        "https://user:pass@test.invalid",
        "https://test.invalid\\evil",
    ):
        with pytest.raises(ControlError):
            control_cli.connection(None, address, require_key=False)


def test_cli_exit_status_and_credentials_stay_private(monkeypatch, tmp_path, capsys):
    credentials = tmp_path / "private.json"
    credentials.write_text(json.dumps({"api_url": "https://test.invalid/v1", "api_key": SECRET}))

    async def fake(address, key):
        assert address == "https://test.invalid" and key == SECRET
        return {"ready": False, "checks": {"service": {"code": "tunnel_offline"}}}

    monkeypatch.setattr(doctor, "diagnose", fake)
    assert control_cli.main(["--credentials", str(credentials), "doctor"]) == 1
    assert "tunnel_offline" in capsys.readouterr().out
