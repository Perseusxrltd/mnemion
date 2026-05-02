import json

from mnemion.backends.registry import get_backend
from mnemion.sweeper import parse_jsonl, sweep


def test_parse_jsonl_flattens_claude_message_content(tmp_path):
    jsonl = tmp_path / "session.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "sessionId": "sess-1",
                "uuid": "msg-1",
                "timestamp": "2026-05-01T00:00:00Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "First line"},
                        {"type": "tool_use", "name": "Read", "input": {"file": "a.py"}},
                    ],
                },
            }
        )
        + "\n"
    )

    rows = list(parse_jsonl(jsonl))

    assert rows[0]["session_id"] == "sess-1"
    assert rows[0]["uuid"] == "msg-1"
    assert rows[0]["role"] == "assistant"
    assert "First line" in rows[0]["content"]
    assert "tool_use: Read" in rows[0]["content"]


def test_parse_jsonl_reports_skipped_invalid_and_unsupported_rows(tmp_path):
    jsonl = tmp_path / "session.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                "{not-json",
                json.dumps({"role": "user"}),
                json.dumps(["not", "an", "object"]),
                json.dumps({"role": "assistant", "content": "Valid memory."}),
            ]
        )
        + "\n"
    )
    stats = {}

    rows = list(parse_jsonl(jsonl, stats=stats))

    assert [row["content"] for row in rows] == ["Valid memory."]
    assert stats == {"skipped_invalid": 1, "skipped_unsupported": 2}


def test_sweep_is_resumable_and_idempotent(tmp_path):
    jsonl = tmp_path / "session.jsonl"
    rows = [
        {
            "session_id": "sess-1",
            "uuid": "msg-1",
            "timestamp": "2026-05-01T00:00:00Z",
            "role": "user",
            "content": "Remember the pricing decision.",
        },
        {
            "session_id": "sess-1",
            "uuid": "msg-2",
            "timestamp": "2026-05-01T00:01:00Z",
            "role": "assistant",
            "content": "The pricing dashboard moved to GraphQL.",
        },
    ]
    jsonl.write_text("".join(json.dumps(row) + "\n" for row in rows))
    anaktoron = tmp_path / "anaktoron"

    first = sweep(str(jsonl), str(anaktoron))
    second = sweep(str(jsonl), str(anaktoron))

    assert first["filed"] == 2
    assert first["skipped_invalid"] == 0
    assert first["skipped_unsupported"] == 0
    assert second["filed"] == 0
    assert second["skipped_existing"] == 2

    collection = get_backend("chroma", anaktoron_path=str(anaktoron)).get_collection(
        "mnemion_drawers"
    )
    result = collection.get(include=["metadatas"])
    assert sorted(result.ids) == ["sweep_sess-1_msg-1", "sweep_sess-1_msg-2"]
    assert {m["message_uuid"] for m in result.metadatas} == {"msg-1", "msg-2"}
