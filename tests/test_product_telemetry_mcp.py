"""Owned stdio tool dispatch with real private queues and synthetic API replies."""

import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from mcp.server.mcpserver import Context

from mnemion import mcp_measurement
from mnemion.product_telemetry import aggregate, catalog, policy, workflow
from mnemion.sdk import Client
from mnemion.service.mcp import create_mcp
from mnemion.service.mcp_transport import compact_tool_metadata


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "private-telemetry"
    monkeypatch.setattr(policy, "default_directory", lambda: root)
    monkeypatch.setattr(policy, "company_policy_file", lambda: tmp_path / "company.json")
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/telemetry")
    policy.configure(root, {"enabled": True, "expected_revision": 0, "disclosure_version": 1})
    return root


def cells(root):
    return [
        {**catalog.describe(row["cell"]), "count": row["count"]} for row in aggregate.preview(root)
    ]


def recall():
    return {
        "request_id": "PRIVATE_REQUEST",
        "query": "PRIVATE_QUERY",
        "hits": [],
        "warnings": [],
        "index": {
            "generation_id": None,
            "eligible_records": 0,
            "indexed_records": 0,
            "pending_records": 0,
            "observed_at": "PRIVATE_DATE",
        },
        "timing_ms": 3,
        "score_description": "PRIVATE_DESCRIPTION",
    }


def gateway(handler, *, stdio=True):
    server = create_mcp("http://127.0.0.1:1", stdio_token="PRIVATE_STDIO_KEY" if stdio else None)
    server.api_client = lambda token: Client(
        "http://fixture.invalid", token, transport=httpx.MockTransport(handler), retries=0
    )
    return server


def call(server, name, arguments=None, context=None):
    return asyncio.run(server.call_tool(name, arguments or {}, context=context))


def http_context(server):
    return Context(
        mcp_server=server,
        request_context=SimpleNamespace(
            request=SimpleNamespace(headers={"authorization": "Bearer PRIVATE_HTTP_KEY"}),
            request_id="PRIVATE_ID",
            meta=None,
            session=None,
            lifespan_context=None,
        ),
    )


def test_all_gateway_paths_and_legacy_tools_have_fixed_owners_or_exclusions():
    for filename, group in [
        ("mnemion/service/mcp.py", "gateway"),
        ("mnemion/mcp_server.py", "legacy"),
    ]:
        tree = ast.parse(Path(filename).read_text())
        if group == "gateway":
            names = set()
            for function in ast.walk(tree):
                if not isinstance(function, ast.AsyncFunctionDef):
                    continue
                for deco in function.decorator_list:
                    if (
                        isinstance(deco, ast.Call)
                        and isinstance(deco.func, ast.Attribute)
                        and deco.func.attr == "tool"
                    ):
                        names.add(
                            next(
                                (arg.value.value for arg in deco.keywords if arg.arg == "name"),
                                function.name,
                            )
                        )
            names |= {"legacy_search", "legacy_fetch"}
        else:
            names = next(
                {key.value for key in node.value.keys}
                for node in ast.walk(tree)
                if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "TOOLS" for t in node.targets)
            )
        assert names == set(mcp_measurement.ORIGINS[group])
        for value in mcp_measurement.ORIGINS[group].values():
            if "workflow" in value:
                assert value["workflow"] in catalog.WORKFLOW_IDS
                assert value["completion"] in catalog.OUTCOMES
            elif "exclusion" in value:
                assert value["exclusion"] in mcp_measurement.ORIGINS["exclusions"]


def test_stdio_search_and_alias_count_one_use_without_content(installation):
    requests = []

    def reply(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer PRIVATE_STDIO_KEY"
        assert json.loads(request.content)["query"] == "PRIVATE_QUERY"
        return httpx.Response(200, json=recall())

    server = gateway(reply)
    result = call(server, "search", {"query": "PRIVATE_QUERY"})
    assert not result.is_error and result.structured_content["query"] == "PRIVATE_QUERY"
    assert len(requests) == 1
    rows = cells(installation)
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == 1
    assert all(row["workflow"] == "memory.recall" and row["surface"] == "headless" for row in rows)
    assert b"PRIVATE" not in (installation / policy.DATABASE_NAME).read_bytes()


def test_http_never_uses_stdio_choice_or_allows_local_privacy_mutations(installation):
    def reply(request):
        assert request.headers["authorization"] == "Bearer PRIVATE_HTTP_KEY"
        return httpx.Response(200, json=recall())

    server = gateway(reply)
    result = call(server, "memory_search", {"query": "PRIVATE_QUERY"}, http_context(server))
    assert not result.is_error
    assert cells(installation) == []
    denied = call(
        server,
        "mnemion_telemetry",
        {"action": "configure", "choice": {"enabled": False, "expected_revision": 0}},
        http_context(server),
    )
    assert denied.is_error and denied.structured_content["code"] == "local_stdio_required"
    assert policy.status(installation)["effective_enabled"]
    public = gateway(reply, stdio=False)
    assert "mnemion_telemetry" not in [tool.name for tool in asyncio.run(public.list_tools())]


def test_local_agent_connection_controls_preserve_stale_opt_out_without_measuring_it(installation):
    server = gateway(lambda _request: pytest.fail("Privacy controls must stay local"))
    current = policy.status(installation)
    changed = call(
        server,
        "mnemion_telemetry",
        {
            "action": "configure",
            "choice": {
                "enabled": True,
                "expected_revision": current["revision"],
                "expected_generation": current["store_generation"],
                "disclosure_version": current["disclosure_version"],
                "connection_mode": "unmetered",
            },
        },
    )
    assert not changed.is_error
    assert changed.structured_content["connection_mode"] == "unmetered"
    off = call(
        server,
        "mnemion_telemetry",
        {
            "action": "configure",
            "choice": {
                "enabled": False,
                "expected_revision": 0,
                "disclosure_version": 0,
                "connection_mode": "metered",
            },
        },
    )
    assert not off.is_error
    assert off.structured_content["connection_mode"] == "unmetered"
    assert off.structured_content["reason"] == "user_disabled"
    assert cells(installation) == []


def test_local_stdio_report_review_uses_shared_cas_and_remote_callers_cannot_approve(
    installation, monkeypatch
):
    from mnemion.product_telemetry import inspection

    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/v1/report")
    monkeypatch.setattr(policy, "transport_available", lambda: True)
    monkeypatch.setattr(
        inspection,
        "read_review_clock",
        lambda **_: {"epoch": "a" * 32, "elapsed_ms": 1000},
    )
    server = gateway(lambda _: pytest.fail("Report review must not call a workspace or collector"))

    def control(action, state, **extra):
        return {
            "action": action,
            "review": {
                "expected_revision": state["status"]["revision"],
                "expected_generation": state["status"]["store_generation"],
                "expected_review_token": state["review"]["token"],
                **extra,
            },
        }

    initial = call(server, "mnemion_telemetry", {"action": "review_status"}).structured_content
    paused = call(server, "mnemion_telemetry", control("review_mode", initial, mode="review"))
    assert not paused.is_error and paused.structured_content["review"]["outcome"] == "paused"
    assert cells(installation) == []
    assert aggregate.record(
        installation,
        {"kind": "submission", "workflow": "memory.recall", "surface": "headless"},
        expected_revision=initial["status"]["revision"],
        expected_generation=initial["status"]["store_generation"],
    )
    staged = call(server, "mnemion_telemetry", control("inspect_report", paused.structured_content))
    assert not staged.is_error and staged.structured_content["packet"]["body_bytes"] == 4
    request = control("approve_report", staged.structured_content)
    denied = call(server, "mnemion_telemetry", request, http_context(server))
    assert denied.is_error and denied.structured_content["code"] == "local_stdio_required"
    assert inspection.status(installation)["review"]["outcome"] == "held"
    approved = call(server, "mnemion_telemetry", request)
    assert not approved.is_error and approved.structured_content["review"]["outcome"] == "approved"
    assert approved.structured_content["packet"] is None
    assert policy.status(installation)["delivery_budget"]["attempts_in_rolling_week"] == 0
    repeated = call(
        server, "mnemion_telemetry", control("inspect_report", approved.structured_content)
    )
    assert repeated.structured_content["packet"] == staged.structured_content["packet"]
    discarded = call(
        server, "mnemion_telemetry", control("discard_report", repeated.structured_content)
    )
    assert discarded.structured_content["review"]["outcome"] == "discarded"
    assert discarded.structured_content["review"]["mode"] == "review"
    assert discarded.structured_content["packet"] is None
    stale = call(server, "mnemion_telemetry", request)
    assert stale.is_error
    assert inspection.status(installation)["review"]["outcome"] == "discarded"
    assert cells(installation) == []


def test_only_owned_stdio_lifespan_registers_an_optional_delivery_owner(monkeypatch):
    from contextlib import asynccontextmanager
    from mnemion.product_telemetry import activity

    transitions = []

    @asynccontextmanager
    async def observed():
        transitions.append("start")
        try:
            yield
        finally:
            transitions.append("stop")

    monkeypatch.setattr(activity, "application_delivery", observed)
    local = gateway(lambda _request: pytest.fail("No API request expected"))
    remote = gateway(lambda _request: pytest.fail("No API request expected"), stdio=False)
    assert remote.settings.lifespan is None

    async def run():
        async with local.settings.lifespan(local):
            assert transitions == ["start"]

    asyncio.run(run())
    assert transitions == ["start", "stop"]


def test_new_keyed_save_is_accepted_but_cached_and_unknown_receipts_are_suppressed(installation):
    replies = iter(["new", "replayed", None])
    space = str(uuid4())

    def reply(request):
        assert json.loads(request.content)["content"] == "PRIVATE_MEMORY"
        value = next(replies)
        return httpx.Response(
            202,
            headers={"X-Mnemion-Idempotency": value} if value else {},
            json={
                "operation_id": "PRIVATE_OPERATION",
                "memory_id": "PRIVATE_MEMORY_ID",
                "space_id": space,
                "state": "accepted",
            },
        )

    server = gateway(reply)
    for _ in range(3):
        result = call(
            server,
            "memory_save",
            {
                "space_id": space,
                "content": "PRIVATE_MEMORY",
                "idempotency_key": "PRIVATE_REQUEST_KEY",
            },
        )
        assert not result.is_error
    rows = cells(installation)
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == 1
    assert [row["bucket"] for row in rows if row["metric"] == "outcomes"] == ["accepted"]


def test_generic_stdio_control_has_one_owner_and_final_opt_out_wins(installation):
    def reply(_):
        policy.configure(installation, {"enabled": False, "expected_revision": 0})
        return httpx.Response(200, json=recall())

    result = call(
        gateway(reply),
        "mnemion",
        {
            "action": "read",
            "operation": "retrieval.search",
            "request": {"body": {"query": "PRIVATE_QUERY"}},
        },
    )
    assert not result.is_error
    assert cells(installation) == []
    assert policy.status(installation)["reason"] == "user_disabled"


def test_local_privacy_tool_is_offline_and_compact_discovery_keeps_remote_scope(installation):
    server = gateway(lambda _: pytest.fail("Privacy controls must not call the workspace"))
    status = call(server, "mnemion_telemetry")
    assert not status.is_error and status.structured_content["effective_enabled"]
    schema = call(server, "mnemion_telemetry", {"action": "schema"})
    assert not schema.is_error
    coverage = schema.structured_content["owned_origin_coverage"]
    assert set(coverage) == {"desktop", "studio", "ui", "mcp", "maintenance"}
    assert coverage["mcp"] == mcp_measurement.ORIGINS
    result = call(
        server,
        "mnemion_telemetry",
        {"action": "configure", "choice": {"enabled": False, "expected_revision": 0}},
    )
    assert not result.is_error and result.structured_content["reason"] == "user_disabled"
    assert cells(installation) == []

    async def listing(local):
        names = ["search", "fetch", "mnemion", "memory_profile"] + (
            ["mnemion_telemetry"] if local else []
        )

        async def next_call(_):
            return {"tools": [{"name": name, "inputSchema": {"type": "object"}} for name in names]}

        return await compact_tool_metadata(SimpleNamespace(method="tools/list"), next_call)

    assert len(asyncio.run(listing(False))["tools"]) == 4
    assert len(asyncio.run(listing(True))["tools"]) == 5


def test_optional_import_failure_calls_the_original_action_only_once(installation, monkeypatch):
    import builtins

    original_import = builtins.__import__
    requests = []

    def unavailable(name, *args, **kwargs):
        if name == "mcp_measurement":
            raise ImportError("PRIVATE_IMPORT_ERROR")
        return original_import(name, *args, **kwargs)

    def reply(request):
        requests.append(request)
        return httpx.Response(200, json=recall())

    server = gateway(reply)
    monkeypatch.setattr(builtins, "__import__", unavailable)
    result = call(server, "memory_search", {"query": "PRIVATE_QUERY"})
    assert not result.is_error and len(requests) == 1
    assert cells(installation) == []


def test_optional_measurement_failure_preserves_the_original_tool_response(
    installation, monkeypatch
):
    def unavailable(*_args, **_kwargs):
        raise RuntimeError("PRIVATE_STORAGE_ERROR")

    monkeypatch.setattr(workflow, "begin", unavailable)
    result = call(
        gateway(lambda _: httpx.Response(200, json=recall())),
        "memory_search",
        {"query": "PRIVATE_QUERY"},
    )
    assert not result.is_error and result.structured_content["query"] == "PRIVATE_QUERY"
    assert cells(installation) == []


def test_legacy_stdio_owner_is_not_inferred_from_imported_handlers_or_json_fields(
    installation, monkeypatch
):
    from mnemion import mcp_server

    monkeypatch.setattr(mcp_server, "_write_heartbeat", lambda *_: None)
    monkeypatch.setitem(
        mcp_server.TOOLS["mnemion_search"], "handler", lambda **_: {"private": "PRIVATE_MEMORY"}
    )
    request = {
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "mnemion_search",
            "arguments": {"query": "PRIVATE_QUERY", "local_stdio": True},
        },
    }
    assert "PRIVATE_MEMORY" in json.dumps(mcp_server.handle_request(request))
    assert cells(installation) == []
    assert "PRIVATE_MEMORY" in json.dumps(mcp_server.handle_request(request, local_stdio=True))
    assert sum(row["count"] for row in cells(installation) if row["metric"] == "submissions") == 1
    denied = mcp_server.handle_request(
        {
            "method": "tools/call",
            "params": {
                "name": "mnemion_telemetry",
                "arguments": {"action": "configure", "enabled": False, "expected_revision": 0},
            },
        }
    )
    assert "error" in denied and policy.status(installation)["effective_enabled"]


def legacy_privacy(action="status", *, local=True, **values):
    from mnemion import mcp_server

    return mcp_server.handle_request(
        {
            "id": 1,
            "method": "tools/call",
            "params": {"name": "mnemion_telemetry", "arguments": {"action": action, **values}},
        },
        local_stdio=local,
    )


def privacy_result(response):
    assert "error" not in response, response.get("error")
    return json.loads(response["result"]["content"][0]["text"])


def test_legacy_privacy_discovery_covers_the_current_offline_control_contract():
    from mnemion import mcp_server
    from mnemion.product_telemetry import cli

    listed = mcp_server.handle_request({"id": 1, "method": "tools/list"}, local_stdio=True)
    schema = next(
        tool["inputSchema"]
        for tool in listed["result"]["tools"]
        if tool["name"] == "mnemion_telemetry"
    )
    actions = cli.execute(None, {"action": "schema"})["actions"]
    properties = schema["properties"]
    assert set(actions) == set(properties["action"]["enum"])
    for action in actions.values():
        assert set(action["fields"]) <= properties.keys()
    assert properties["disclosure_version"]["minimum"] == 0


def test_legacy_privacy_connection_choice_is_applied_without_measurement(installation, monkeypatch):
    from mnemion import mcp_server

    monkeypatch.setattr(mcp_server, "_write_heartbeat", lambda *_: pytest.fail("Privacy heartbeat"))
    current = privacy_result(legacy_privacy())
    result = privacy_result(
        legacy_privacy(
            "configure",
            enabled=True,
            expected_revision=current["revision"],
            expected_generation=current["store_generation"],
            disclosure_version=current["disclosure_version"],
            connection_mode="unmetered",
        )
    )
    assert result["connection_mode"] == "unmetered"
    assert cells(installation) == []


def test_legacy_privacy_report_review_and_optout_preserve_shared_fences(installation, monkeypatch):
    from mnemion import mcp_server
    from mnemion.product_telemetry import inspection

    monkeypatch.setattr(mcp_server, "_write_heartbeat", lambda *_: pytest.fail("Privacy heartbeat"))
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/v1/report")
    monkeypatch.setattr(policy, "transport_available", lambda: True)
    monkeypatch.setattr(
        inspection, "read_review_clock", lambda **_: {"epoch": "a" * 32, "elapsed_ms": 1000}
    )

    def request(action, state, **values):
        return legacy_privacy(
            action,
            expected_revision=state["status"]["revision"],
            expected_generation=state["status"]["store_generation"],
            expected_review_token=state["review"]["token"],
            **values,
        )

    initial = privacy_result(legacy_privacy("review_status"))
    paused = privacy_result(request("review_mode", initial, mode="review"))
    assert paused["review"]["outcome"] == "paused"
    assert cells(installation) == []
    assert aggregate.record(
        installation,
        {"kind": "submission", "workflow": "memory.recall", "surface": "headless"},
        expected_revision=paused["status"]["revision"],
        expected_generation=paused["status"]["store_generation"],
    )
    staged = privacy_result(request("inspect_report", paused))
    assert staged["packet"]["body_bytes"] == 4
    assert "error" in request("approve_report", staged, local=False)
    approved = privacy_result(request("approve_report", staged))
    assert approved["review"]["outcome"] == "approved"
    repeated = privacy_result(request("inspect_report", approved))
    assert repeated["packet"]["body_base64"] == staged["packet"]["body_base64"]
    assert repeated["status"]["delivery_budget"]["attempts_in_rolling_week"] == 0
    discarded = privacy_result(request("discard_report", repeated))
    assert not discarded["review"]["report_available"]
    assert "error" in request("approve_report", staged)
    disabled = privacy_result(
        legacy_privacy("configure", enabled=False, expected_revision=0, disclosure_version=0)
    )
    assert disabled["reason"] == "user_disabled"
    assert disabled["pending_records"] == 0
    assert disabled["delivery_budget"]["attempts_in_rolling_week"] == 0


@pytest.mark.parametrize(
    "invalid", ["fractional_revision", "string_revision", "unknown_field", "legacy_wait_field"]
)
def test_legacy_privacy_does_not_rewrite_invalid_choices(installation, invalid):
    current = policy.status(installation)
    request = {
        "enabled": True,
        "expected_revision": current["revision"],
        "expected_generation": current["store_generation"],
        "disclosure_version": current["disclosure_version"],
    }
    if invalid == "fractional_revision":
        request["expected_revision"] += 0.9
    elif invalid == "string_revision":
        request["expected_revision"] = str(request["expected_revision"])
    elif invalid == "legacy_wait_field":
        request["wait_for_previous"] = True
    else:
        request["unexpected_choice"] = True
    result = legacy_privacy("configure", **request)
    assert "error" in result
    assert policy.status(installation) == current


@pytest.mark.parametrize("arguments", [None, [], "invalid", 1])
def test_legacy_privacy_rejects_non_object_arguments(installation, arguments):
    from mnemion import mcp_server

    current = policy.status(installation)
    response = mcp_server.handle_request(
        {
            "id": 1,
            "method": "tools/call",
            "params": {"name": "mnemion_telemetry", "arguments": arguments},
        },
        local_stdio=True,
    )
    assert response["error"]["code"] == -32602
    assert policy.status(installation) == current
