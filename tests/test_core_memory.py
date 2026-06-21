import json
from mnemion import mcp_server


def test_kg_core_memory_direct(kg):
    # Direct database test
    assert kg.get_core_memory("test_key") == ""
    kg.update_core_memory("test_key", "hello world")
    assert kg.get_core_memory("test_key") == "hello world"
    kg.update_core_memory("test_key", "updated content")
    assert kg.get_core_memory("test_key") == "updated content"


def test_mcp_core_memory_tools(kg):
    # Override mcp_server._kg with our test kg
    original_kg = mcp_server._kg
    mcp_server._kg = kg
    try:
        # Retrieve non-existing core memory
        resp = mcp_server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 1,
                "params": {"name": "mnemion_get_core_memory", "arguments": {"key": "test_mcp"}},
            }
        )
        assert "error" not in resp
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result["key"] == "test_mcp"
        assert result["content"] == ""

        # Update core memory
        resp = mcp_server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 2,
                "params": {
                    "name": "mnemion_update_core_memory",
                    "arguments": {"key": "test_mcp", "content": "mcp content"},
                },
            }
        )
        assert "error" not in resp
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result["success"] is True
        assert result["content"] == "mcp content"

        # Verify update
        resp = mcp_server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 3,
                "params": {"name": "mnemion_get_core_memory", "arguments": {"key": "test_mcp"}},
            }
        )
        assert "error" not in resp
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result["content"] == "mcp content"
    finally:
        mcp_server._kg = original_kg
