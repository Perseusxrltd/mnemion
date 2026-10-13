"""Query-only agent calls use current accessible spaces, including source leases."""

import asyncio
from uuid import UUID

import httpx2
from mcp import Client as MCPClient
from mcp.client.streamable_http import streamable_http_client

from mnemion.service.api import create_app
from mnemion.service.connector_models import ScopeInput, utc_now
from mnemion.service.models import MemoryInput
from service_tests.test_clients import running
from service_tests.test_connectors import connected as connected
from service_tests.test_connectors import ingest, item


def test_query_only_mcp_reads_current_sources_and_never_widens_explicit_scope(env, connected):
    service, connection, first, operator, identities = connected
    saved = ingest(service, operator, first, item(text="First source billing evidence"))
    first_memory = saved["items"][0]["memory_id"]
    second = UUID(
        service.refresh_scope(
            operator,
            connection,
            ScopeInput(
                external_id="second-source",
                name="Second source",
                members=["U_reader"],
                observed_at=utc_now(),
            ),
        )["space_id"]
    )
    saved = ingest(service, operator, second, item(text="Second source billing evidence"))
    second_memory = saved["items"][0]["memory_id"]
    private = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="PRIVATE_OWNER_ONLY billing evidence"),
        "private-owner-memory",
    )["memory_id"]
    while env.worker.run_once():
        pass

    with running(create_app(env.db, env.embedder)) as url:

        async def exercise():
            async with httpx2.AsyncClient(
                headers={
                    "Authorization": "Bearer " + identities["reader"][1],
                }
            ) as http:
                async with MCPClient(
                    streamable_http_client(url + "/mcp", http_client=http),
                    read_timeout_seconds=15,
                ) as client:
                    tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                    for name in ("memory_search", "memory_context", "memory_map"):
                        assert "space_ids" not in tools[name].input_schema.get("required", [])
                        args = {} if name == "memory_map" else {"query": "billing"}
                        result = await client.call_tool(name, args)
                        assert not result.is_error, result
                        assert str(private) not in str(result)
                        assert "PRIVATE_OWNER_ONLY" not in str(result)
                        if name == "memory_search":
                            assert {
                                hit["memory_id"] for hit in result.structured_content["hits"]
                            } == {
                                first_memory,
                                second_memory,
                            }

                    scoped = await client.call_tool(
                        "memory_search",
                        {
                            "query": "billing",
                            "space_ids": [str(first)],
                        },
                    )
                    assert not scoped.is_error
                    assert [hit["memory_id"] for hit in scoped.structured_content["hits"]] == [
                        first_memory
                    ]
                    for selection in (
                        {"space_ids": []},
                        {"all_accessible": False},
                        {"space_ids": [str(first)], "all_accessible": True},
                        {"space_ids": [str(first), str(env.space)]},
                    ):
                        result = await client.call_tool(
                            "memory_search", {"query": "billing", **selection}
                        )
                        assert result.is_error, result
                    explicit = await client.call_tool(
                        "memory_search",
                        {
                            "query": "billing",
                            "space_ids": [],
                            "all_accessible": True,
                        },
                    )
                    assert not explicit.is_error and len(explicit.structured_content["hits"]) == 2

                    service.suspend(operator, first, "operator_paused")
                    for name in ("memory_search", "memory_context", "memory_map"):
                        args = {} if name == "memory_map" else {"query": "billing"}
                        result = await client.call_tool(name, args)
                        assert not result.is_error, result
                        assert first_memory not in str(result)
                        assert str(private) not in str(result)
                        if name == "memory_search":
                            assert [
                                hit["memory_id"] for hit in result.structured_content["hits"]
                            ] == [second_memory]

        asyncio.run(exercise())
