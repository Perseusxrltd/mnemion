"""
test_mcp_server.py — Tests for the MCP server tool handlers and dispatch.

Tests each tool handler directly (unit-level) and the handle_request
dispatch layer (integration-level). Uses isolated Anaktoron + KG fixtures
via monkeypatch to avoid touching real data.
"""

import json
import hashlib
import sqlite3
from pathlib import Path


def _patch_mcp_server(monkeypatch, config, kg):
    """Patch the mcp_server module globals to use test fixtures."""
    from mnemion import mcp_server
    from mnemion.hybrid_searcher import HybridSearcher
    from mnemion.trust_lifecycle import DrawerTrust
    import os

    monkeypatch.setattr(mcp_server, "_config", config)
    monkeypatch.setattr(mcp_server, "_kg", kg)
    # _hybrid and _trust are module-level globals init'd at import time;
    # they must point to the test Anaktoron/db, not the session temp dir.
    kg_path = os.path.join(os.path.dirname(config.anaktoron_path), "test_kg.sqlite3")
    monkeypatch.setattr(
        mcp_server, "_hybrid", HybridSearcher(anaktoron_path=config.anaktoron_path, kg_path=kg_path)
    )
    monkeypatch.setattr(mcp_server, "_trust", DrawerTrust(db_path=kg_path))
    monkeypatch.setattr(mcp_server, "_vector_disabled", False)
    monkeypatch.setattr(mcp_server, "_vector_health", {"status": "ok", "diverged": False})


def _get_collection(anaktoron_path, create=False):
    """Helper to get collection from test Anaktoron.

    Returns (client, collection) so callers can clean up the client
    when they are done.
    """
    from mnemion.chroma_compat import make_persistent_client
    from mnemion.config import DRAWER_HNSW_METADATA

    client = make_persistent_client(anaktoron_path)
    if create:
        return client, client.get_or_create_collection(
            "mnemion_drawers", metadata=DRAWER_HNSW_METADATA
        )
    return client, client.get_collection("mnemion_drawers")


# ── Protocol Layer ──────────────────────────────────────────────────────


class TestHandleRequest:
    def test_initialize(self):
        from mnemion.mcp_server import handle_request

        resp = handle_request({"method": "initialize", "id": 1, "params": {}})
        assert resp["result"]["serverInfo"]["name"] == "mnemion"
        assert resp["id"] == 1

    def test_notifications_initialized_returns_none(self):
        from mnemion.mcp_server import handle_request

        resp = handle_request({"method": "notifications/initialized", "id": None, "params": {}})
        assert resp is None

    def test_tools_list(self):
        from mnemion.mcp_server import handle_request

        resp = handle_request({"method": "tools/list", "id": 2, "params": {}})
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        assert "mnemion_status" in names
        assert "mnemion_search" in names
        assert "mnemion_add_drawer" in names
        assert "mnemion_kg_add" in names
        assert "mnemion_get_drawer" in names
        assert "mnemion_update_drawer" in names
        assert "mnemion_create_tunnel" in names
        assert "mnemion_reconnect" in names

    def test_unknown_tool(self):
        from mnemion.mcp_server import handle_request

        resp = handle_request(
            {
                "method": "tools/call",
                "id": 3,
                "params": {"name": "nonexistent_tool", "arguments": {}},
            }
        )
        assert resp["error"]["code"] == -32601

    def test_unknown_method(self):
        from mnemion.mcp_server import handle_request

        resp = handle_request({"method": "unknown/method", "id": 4, "params": {}})
        assert resp["error"]["code"] == -32601

    def test_tools_call_dispatches(self, monkeypatch, config, anaktoron_path, seeded_kg):
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from mnemion.mcp_server import handle_request

        # Create a collection so status works
        _client, _col = _get_collection(anaktoron_path, create=True)
        del _client

        resp = handle_request(
            {
                "method": "tools/call",
                "id": 5,
                "params": {"name": "mnemion_status", "arguments": {}},
            }
        )
        assert "result" in resp
        content = json.loads(resp["result"]["content"][0]["text"])
        assert "total_drawers" in content

    def test_tools_call_ignores_added_by_spoof(self, monkeypatch, config, anaktoron_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _client, col = _get_collection(anaktoron_path, create=True)
        del _client
        from mnemion.mcp_server import handle_request

        resp = handle_request(
            {
                "method": "tools/call",
                "id": 6,
                "params": {
                    "name": "mnemion_add_drawer",
                    "arguments": {
                        "wing": "audit",
                        "room": "mcp",
                        "content": "External MCP callers cannot spoof audit attribution.",
                        "added_by": "spoofed-client",
                    },
                },
            }
        )

        content = json.loads(resp["result"]["content"][0]["text"])
        metadata = col.get(ids=[content["drawer_id"]], include=["metadatas"])["metadatas"][0]
        assert metadata["added_by"] == "mcp"


# ── Read Tools ──────────────────────────────────────────────────────────


class TestReadTools:
    def test_status_empty_anaktoron(self, monkeypatch, config, anaktoron_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _client, _col = _get_collection(anaktoron_path, create=True)
        del _client
        from mnemion.mcp_server import tool_status

        result = tool_status()
        assert result["total_drawers"] == 0
        assert result["wings"] == {}

    def test_status_with_data(self, monkeypatch, config, anaktoron_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion.mcp_server import tool_status

        result = tool_status()
        assert result["total_drawers"] == 4
        assert "project" in result["wings"]
        assert "notes" in result["wings"]

    def test_list_wings(self, monkeypatch, config, anaktoron_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion.mcp_server import tool_list_wings

        result = tool_list_wings()
        assert result["wings"]["project"] == 3
        assert result["wings"]["notes"] == 1

    def test_list_rooms_all(self, monkeypatch, config, anaktoron_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion.mcp_server import tool_list_rooms

        result = tool_list_rooms()
        assert "backend" in result["rooms"]
        assert "frontend" in result["rooms"]
        assert "planning" in result["rooms"]

    def test_list_rooms_filtered(self, monkeypatch, config, anaktoron_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion.mcp_server import tool_list_rooms

        result = tool_list_rooms(wing="project")
        assert "backend" in result["rooms"]
        assert "planning" not in result["rooms"]

    def test_get_taxonomy(self, monkeypatch, config, anaktoron_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion.mcp_server import tool_get_taxonomy

        result = tool_get_taxonomy()
        assert result["taxonomy"]["project"]["backend"] == 2
        assert result["taxonomy"]["project"]["frontend"] == 1
        assert result["taxonomy"]["notes"]["planning"] == 1

    def test_no_anaktoron_returns_error(self, monkeypatch, config, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion.mcp_server import tool_status

        result = tool_status()
        assert "error" in result


# ── Search Tool ─────────────────────────────────────────────────────────


class TestSearchTool:
    def test_search_basic(self, monkeypatch, config, anaktoron_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion.mcp_server import tool_search

        result = tool_search(query="JWT authentication tokens")
        assert "results" in result
        assert len(result["results"]) > 0
        # Top result should be the auth drawer
        top = result["results"][0]
        assert "JWT" in top["text"] or "authentication" in top["text"].lower()

    def test_search_with_wing_filter(
        self, monkeypatch, config, anaktoron_path, seeded_collection, kg
    ):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion.mcp_server import tool_search

        result = tool_search(query="planning", wing="notes")
        assert all(r["wing"] == "notes" for r in result["results"])

    def test_search_with_room_filter(
        self, monkeypatch, config, anaktoron_path, seeded_collection, kg
    ):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion.mcp_server import tool_search

        result = tool_search(query="database", room="backend")
        assert all(r["room"] == "backend" for r in result["results"])


# ── Write Tools ─────────────────────────────────────────────────────────


class TestWriteTools:
    def test_add_drawer(self, monkeypatch, config, anaktoron_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _client, _col = _get_collection(anaktoron_path, create=True)
        del _client
        from mnemion.mcp_server import tool_add_drawer

        result = tool_add_drawer(
            wing="test_wing",
            room="test_room",
            content="This is a test memory about Python decorators and metaclasses.",
        )
        assert result["success"] is True
        assert result["wing"] == "test_wing"
        assert result["room"] == "test_room"
        assert result["drawer_id"].startswith("drawer_test_wing_test_room_")

    def test_add_drawer_duplicate_detection(self, monkeypatch, config, anaktoron_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _client, _col = _get_collection(anaktoron_path, create=True)
        del _client
        from mnemion.mcp_server import tool_add_drawer

        content = "This is a unique test memory about Rust ownership and borrowing."
        result1 = tool_add_drawer(wing="w", room="r", content=content)
        assert result1["success"] is True

        result2 = tool_add_drawer(wing="w", room="r", content=content)
        assert result2["success"] is True
        assert result2["reason"] == "already_exists"

    def test_delete_drawer(self, monkeypatch, config, anaktoron_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion.mcp_server import tool_delete_drawer

        result = tool_delete_drawer("drawer_proj_backend_aaa")
        assert result["success"] is True
        assert seeded_collection.count() == 3

    def test_delete_drawer_not_found(
        self, monkeypatch, config, anaktoron_path, seeded_collection, kg
    ):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion.mcp_server import tool_delete_drawer

        result = tool_delete_drawer("nonexistent_drawer")
        assert result["success"] is False

    def test_get_list_and_update_drawer(self, monkeypatch, config, anaktoron_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _client, _col = _get_collection(anaktoron_path, create=True)
        del _client
        from mnemion.mcp_server import (
            tool_add_drawer,
            tool_get_drawer,
            tool_list_drawers,
            tool_update_drawer,
        )

        added = tool_add_drawer("ops", "repair", "Initial repair note.")
        moved = tool_update_drawer(added["drawer_id"], wing="ops", room="status")
        assert moved["success"] is True
        fetched = tool_get_drawer(added["drawer_id"])
        assert fetched["metadata"]["room"] == "status"
        listed = tool_list_drawers(wing="ops", room="status")
        assert [d["drawer_id"] for d in listed["drawers"]] == [added["drawer_id"]]

        superseded = tool_update_drawer(added["drawer_id"], content="Replacement repair note.")
        assert superseded["success"] is True
        assert superseded["superseded"] == added["drawer_id"]
        old = fetched["trust"] or {}
        updated_old = tool_get_drawer(added["drawer_id"])["trust"]
        assert (old == {}) or updated_old["status"] == "superseded"

    def test_tunnel_tools(self, monkeypatch, config, anaktoron_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion.mcp_server import (
            tool_create_tunnel,
            tool_delete_tunnel,
            tool_follow_tunnels,
            tool_list_tunnels,
        )

        created = tool_create_tunnel("wing_a", "room_a", "wing_b", "room_b", label="related")
        tunnel_id = created["tunnel"]["tunnel_id"]
        assert tool_list_tunnels("wing_a")["tunnels"][0]["tunnel_id"] == tunnel_id
        assert tool_follow_tunnels("wing_a", "room_a")["tunnels"][0]["direction"] == "outbound"
        assert tool_delete_tunnel(tunnel_id)["success"] is True

    def test_vector_disabled_duplicate_reports_limitation(self, monkeypatch, config, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion import mcp_server

        monkeypatch.setattr(mcp_server, "_vector_disabled", True)
        monkeypatch.setattr(mcp_server, "_vector_health", {"status": "diverged"})
        result = mcp_server.tool_check_duplicate("same memory")
        assert result["is_duplicate"] is None
        assert "disabled" in result["warning"].lower()

    def test_vector_disabled_status_uses_sqlite_metadata_summary(self, monkeypatch, config, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion import mcp_server

        monkeypatch.setattr(mcp_server, "_vector_disabled", True)
        monkeypatch.setattr(mcp_server, "_vector_health", {"status": "diverged", "sqlite_count": 3})
        monkeypatch.setattr(
            mcp_server,
            "sqlite_metadata_summary",
            lambda *_args, **_kwargs: {
                "total_drawers": 3,
                "wing_count": 2,
                "room_count": 2,
                "wings": {"ops": 2, "notes": 1},
                "rooms": {"repair": 2, "planning": 1},
                "metadata_unavailable": False,
                "metadata_message": "from sqlite",
            },
        )

        result = mcp_server.tool_status()

        assert result["total_drawers"] == 3
        assert result["wings"] == {"ops": 2, "notes": 1}
        assert result["rooms"] == {"repair": 2, "planning": 1}
        assert result["metadata_unavailable"] is False

    def test_reconnect_clears_caches(self, monkeypatch, config, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion import mcp_server

        called = {"close": 0}

        def fake_close():
            called["close"] += 1

        monkeypatch.setattr(mcp_server, "close_chroma_handles", fake_close)
        monkeypatch.setattr(mcp_server, "_client_cache", object())
        monkeypatch.setattr(mcp_server, "_collection_cache", object())
        monkeypatch.setattr(mcp_server, "_hybrid", object())
        result = mcp_server.tool_reconnect()
        assert result["success"] is True
        assert called["close"] == 1
        assert mcp_server._client_cache is None
        assert mcp_server._collection_cache is None
        assert mcp_server._hybrid is not None

    def test_check_duplicate(self, monkeypatch, config, anaktoron_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion.mcp_server import tool_check_duplicate

        # Exact match text from seeded_collection should be flagged
        result = tool_check_duplicate(
            "The authentication module uses JWT tokens for session management. "
            "Tokens expire after 24 hours. Refresh tokens are stored in HttpOnly cookies.",
            threshold=0.5,
        )
        assert result["is_duplicate"] is True

        # Unrelated content should not be flagged
        result = tool_check_duplicate(
            "Black holes emit Hawking radiation at the event horizon.",
            threshold=0.99,
        )
        assert result["is_duplicate"] is False

    def test_update_drawer_rolls_back_new_row_when_supersede_trust_fails(
        self, monkeypatch, config, anaktoron_path, kg
    ):
        _patch_mcp_server(monkeypatch, config, kg)
        _client, col = _get_collection(anaktoron_path, create=True)
        del _client
        from mnemion import mcp_server

        added = mcp_server.tool_add_drawer("ops", "repair", "Original repair note.")
        old_id = added["drawer_id"]
        new_content = "Replacement repair note."
        new_id = (
            "drawer_ops_repair_"
            + hashlib.md5(new_content.encode(), usedforsecurity=False).hexdigest()[:16]
        )
        real_update = mcp_server._trust.update_status

        def fail_old_update(drawer_id, *args, **kwargs):
            if drawer_id == old_id:
                raise RuntimeError("trust supersede failed")
            return real_update(drawer_id, *args, **kwargs)

        monkeypatch.setattr(mcp_server._trust, "update_status", fail_old_update)

        result = mcp_server.tool_update_drawer(old_id, content=new_content)

        assert result["success"] is False
        assert not col.get(ids=[new_id])["ids"]
        with sqlite3.connect(mcp_server._hybrid.kg_path) as conn:
            fts_count = conn.execute(
                "SELECT COUNT(*) FROM drawers_fts WHERE drawer_id = ?", (new_id,)
            ).fetchone()[0]
        assert fts_count == 0


# ── KG Tools ────────────────────────────────────────────────────────────


class TestKGTools:
    def test_kg_add(self, monkeypatch, config, anaktoron_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion.mcp_server import tool_kg_add

        result = tool_kg_add(
            subject="Alice",
            predicate="likes",
            object="coffee",
            valid_from="2025-01-01",
        )
        assert result["success"] is True

    def test_kg_query(self, monkeypatch, config, anaktoron_path, seeded_kg):
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from mnemion.mcp_server import tool_kg_query

        result = tool_kg_query(entity="Max")
        assert result["count"] > 0

    def test_kg_invalidate(self, monkeypatch, config, anaktoron_path, seeded_kg):
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from mnemion.mcp_server import tool_kg_invalidate

        result = tool_kg_invalidate(
            subject="Max",
            predicate="does",
            object="chess",
            ended="2026-03-01",
        )
        assert result["success"] is True

    def test_kg_timeline(self, monkeypatch, config, anaktoron_path, seeded_kg):
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from mnemion.mcp_server import tool_kg_timeline

        result = tool_kg_timeline(entity="Alice")
        assert result["count"] > 0

    def test_kg_stats(self, monkeypatch, config, anaktoron_path, seeded_kg):
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from mnemion.mcp_server import tool_kg_stats

        result = tool_kg_stats()
        assert result["entities"] >= 4


class TestWalAndTrustTools:
    def test_wal_redacts_sensitive_fields(self):
        from mnemion import mcp_server

        redacted = mcp_server._redact_for_wal(
            {
                "drawer_id": "drawer_123",
                "content": "secret content",
                "object": "secret object",
                "label": "private label",
                "reason": "private reason",
                "resolution_note": "private note",
                "source_file": "C:/Users/name/private.txt",
            }
        )

        assert redacted["drawer_id"] == "drawer_123"
        for key in ["content", "object", "label", "reason", "resolution_note", "source_file"]:
            assert redacted[key]["redacted"] is True
            assert "secret" not in json.dumps(redacted[key])
            assert "private" not in json.dumps(redacted[key])

    def test_resolve_contest_writes_redacted_wal(self, monkeypatch, config, kg, tmp_path):
        _patch_mcp_server(monkeypatch, config, kg)
        from mnemion import mcp_server

        mcp_server._trust.create("drawer_loser", "ops", "repair")
        mcp_server._trust.create("drawer_winner", "ops", "repair")

        result = mcp_server.tool_resolve_contest(
            "drawer_loser", "drawer_winner", "this note contains sensitive detail"
        )

        wal_path = Path.home() / ".mnemion" / "wal" / "write_log.jsonl"
        record = json.loads(wal_path.read_text(encoding="utf-8").splitlines()[-1])
        assert result["success"] is True
        assert record["tool"] == "mnemion_resolve_contest"
        assert record["args"]["drawer_id"] == "drawer_loser"
        assert record["args"]["winner_id"] == "drawer_winner"
        assert record["args"]["resolution_note"]["redacted"] is True
        assert "sensitive detail" not in json.dumps(record)


# ── Diary Tools ─────────────────────────────────────────────────────────


class TestDiaryTools:
    def test_diary_write_and_read(self, monkeypatch, config, anaktoron_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _client, _col = _get_collection(anaktoron_path, create=True)
        del _client
        from mnemion.mcp_server import tool_diary_write, tool_diary_read

        w = tool_diary_write(
            agent_name="TestAgent",
            entry="Today we discussed authentication patterns.",
            topic="architecture",
        )
        assert w["success"] is True
        assert w["agent"] == "TestAgent"

        r = tool_diary_read(agent_name="TestAgent")
        assert r["total"] == 1
        assert r["entries"][0]["topic"] == "architecture"
        assert "authentication" in r["entries"][0]["content"]

    def test_diary_read_empty(self, monkeypatch, config, anaktoron_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _client, _col = _get_collection(anaktoron_path, create=True)
        del _client
        from mnemion.mcp_server import tool_diary_read

        r = tool_diary_read(agent_name="Nobody")
        assert r["entries"] == []
