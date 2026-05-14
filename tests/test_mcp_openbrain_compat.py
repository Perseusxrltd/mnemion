import json


def _call_tool(mcp_server, name, arguments, request_id=1):
    response = mcp_server.handle_request(
        {
            "method": "tools/call",
            "id": request_id,
            "params": {"name": name, "arguments": arguments},
        }
    )
    return json.loads(response["result"]["content"][0]["text"])


def test_openbrain_compat_tools_are_registered():
    from mnemion.mcp_server import TOOLS

    for name in [
        "capture_thought",
        "search_thoughts",
        "list_thoughts",
        "thought_stats",
        "search",
        "fetch",
    ]:
        assert name in TOOLS


def test_search_ids_can_be_fetched(monkeypatch, config, anaktoron_path, kg):
    from tests.test_mcp_server import _patch_mcp_server
    from mnemion import mcp_server

    _patch_mcp_server(monkeypatch, config, kg)
    drawer_id = "drawer_thoughts_general_roundtrip"

    class FakeCollection:
        def get(self, ids=None, include=None, **kwargs):
            if ids == [drawer_id]:
                return {
                    "ids": [drawer_id],
                    "documents": ["Hybrid retrieval source-backed wiki."],
                    "metadatas": [{"wing": "thoughts", "room": "general"}],
                }
            return {"ids": [], "documents": [], "metadatas": []}

    monkeypatch.setattr(mcp_server, "_get_collection", lambda create=False: FakeCollection())
    monkeypatch.setattr(
        mcp_server._hybrid,
        "search",
        lambda *args, **kwargs: [
            {
                "id": drawer_id,
                "text": "Hybrid retrieval source-backed wiki.",
                "wing": "thoughts",
                "room": "general",
                "score": 0.9,
                "trust_status": "current",
            }
        ],
    )

    search_resp = mcp_server.handle_request(
        {
            "method": "tools/call",
            "id": 1,
            "params": {"name": "search", "arguments": {"query": "source-backed wiki"}},
        }
    )
    search_payload = json.loads(search_resp["result"]["content"][0]["text"])
    typed_id = search_payload["results"][0]["id"]

    fetch_resp = mcp_server.handle_request(
        {
            "method": "tools/call",
            "id": 2,
            "params": {"name": "fetch", "arguments": {"id": typed_id}},
        }
    )
    fetch_payload = json.loads(fetch_resp["result"]["content"][0]["text"])

    assert typed_id.startswith("drawer:")
    assert "Hybrid retrieval" in fetch_payload["content"]


def test_registry_search_fetch_round_trip_for_source_chunk_wiki_and_quarantine(
    monkeypatch, tmp_path, config, anaktoron_path, kg
):
    from tests.test_mcp_server import _patch_mcp_server
    from mnemion import mcp_server
    from mnemion.sources.store import SourceStore
    from mnemion.wiki.compiler import WikiCompiler

    monkeypatch.setenv("MNEMION_SOURCE_PATH", str(tmp_path / "sources"))
    monkeypatch.setenv("MNEMION_WIKI_PATH", str(tmp_path / "wiki"))
    _patch_mcp_server(monkeypatch, config, kg)

    source_file = tmp_path / "roundtrip.md"
    source_file.write_text("Hybrid retrieval registry round trips through source chunks.")
    source_store = SourceStore(
        db_path=mcp_server._hybrid.kg_path,
        source_path=tmp_path / "sources",
        anaktoron_path=anaktoron_path,
    )
    source = source_store.add_path(source_file)
    WikiCompiler(
        db_path=mcp_server._hybrid.kg_path,
        wiki_path=tmp_path / "wiki",
        source_path=tmp_path / "sources",
    ).compile_all(apply=True)

    drawer_id = "drawer_thoughts_general_registry"

    class FakeCollection:
        def get(self, ids=None, include=None, **kwargs):
            if ids == [drawer_id]:
                return {
                    "ids": [drawer_id],
                    "documents": ["Hybrid retrieval drawer registry result."],
                    "metadatas": [{"wing": "thoughts", "room": "general"}],
                }
            return {"ids": [], "documents": [], "metadatas": []}

    monkeypatch.setattr(mcp_server, "_get_collection", lambda create=False: FakeCollection())
    monkeypatch.setattr(
        mcp_server._hybrid,
        "search",
        lambda *args, **kwargs: [
            {
                "id": drawer_id,
                "text": "Hybrid retrieval drawer registry result.",
                "wing": "thoughts",
                "room": "general",
                "score": 0.9,
                "trust_status": "current",
            }
        ],
    )

    search_payload = _call_tool(mcp_server, "search", {"query": "hybrid retrieval"})
    typed_ids = {result["id"] for result in search_payload["results"]}

    assert f"drawer:{drawer_id}" in typed_ids
    assert any(typed_id.startswith("chunk:") for typed_id in typed_ids)
    assert any(typed_id.startswith("wiki:") for typed_id in typed_ids)
    assert (
        "Hybrid retrieval"
        in _call_tool(mcp_server, "fetch", {"id": f"source:{source['source_id']}"}, request_id=2)[
            "text"
        ]
    )
    for typed_id in typed_ids:
        payload = _call_tool(mcp_server, "fetch", {"id": typed_id}, request_id=3)
        assert "error" not in payload

    import sqlite3

    with sqlite3.connect(mcp_server._hybrid.kg_path) as conn:
        conn.execute(
            "UPDATE raw_sources SET trust_status = 'quarantined' WHERE id = ?",
            (source["source_id"],),
        )
        conn.commit()

    quarantined_source = _call_tool(
        mcp_server, "fetch", {"id": f"source:{source['source_id']}"}, request_id=4
    )
    quarantined_wiki = _call_tool(
        mcp_server,
        "fetch",
        {"id": f"wiki:sources/roundtrip-{source['source_id']}.md"},
        request_id=5,
    )
    native_wiki = _call_tool(
        mcp_server,
        "mnemion_wiki_page_get",
        {"id_or_path": f"sources/roundtrip-{source['source_id']}.md"},
        request_id=6,
    )

    assert quarantined_source["error"].startswith("source is quarantined")
    assert "quarantined" in quarantined_wiki["error"]
    assert "quarantined" in native_wiki["error"]
