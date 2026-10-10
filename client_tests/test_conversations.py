import json

import pytest

from mnemion.conversations import ConversationError, parse
from mnemion.connectors.protocol import Document


def test_codex_capture_keeps_raw_archive_and_canonical_turns_without_duplicates():
    rows = [
        {"type": "session_meta", "payload": {"id": "session-a"}},
        {
            "type": "event_msg",
            "timestamp": "2026-10-09T10:00:00Z",
            "payload": {"type": "user_message", "message": "Garde les décisons en français."},
        },
        {"type": "response_item", "payload": {"type": "message", "content": "synthetic duplicate"}},
        {
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "PostgreSQL avec sauvegarde vérifiée."},
        },
    ]
    raw = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    docs = list(
        Document("session.jsonl", "1", "session.jsonl", raw, normalize_conversations=True).items()
    )
    assert len(docs) == 2
    assert docs[0].memory.source.content == raw
    assert "synthetic duplicate" not in docs[1].memory.content
    assert "décisons" in docs[1].memory.content  # No spell correction of source words.
    assert docs[1].memory.metadata["conversation_turns"] == 2
    assert docs[1].memory.metadata["raw_source_external_id"] == "session.jsonl"
    assert all(item.memory.claim_status == "observed" for item in docs)
    # Appending a session turn revises the same companion identity.
    rows.append({"type": "event_msg", "payload": {"type": "user_message", "message": "Merci."}})
    extended = "\n".join(json.dumps(row) for row in rows)
    changed = list(
        Document(
            "session.jsonl", "2", "session.jsonl", extended, normalize_conversations=True
        ).items()
    )
    assert [item.external_id for item in changed] == [item.external_id for item in docs]


def test_chatgpt_active_branch_and_multiple_exported_conversations():
    def node(parent, children, text):
        return {
            "parent": parent,
            "children": children,
            "message": {"author": {"role": "assistant"}, "content": {"parts": [text]}},
        }

    conversation = {
        "id": "chat-1",
        "title": "Architecture",
        "current_node": "chosen",
        "mapping": {
            "root": node(None, ["discarded", "chosen"], "Question"),
            "discarded": node("root", [], "Discarded branch"),
            "chosen": node("root", [], "Final decision"),
        },
    }
    results = parse(json.dumps([conversation, {**conversation, "id": "chat-2"}]), "export.json")
    assert len(results) == 2 and results[0].identifier != results[1].identifier
    assert "Final decision" in results[0].text and "Discarded branch" not in results[0].text
    conversation["mapping"]["root"]["parent"] = "chosen"
    with pytest.raises(ConversationError, match="mapping_invalid"):
        parse(json.dumps(conversation), "export.json")


def test_claude_privacy_export_and_slack_do_not_invent_speaker_identity():
    claude = [
        {
            "uuid": "chat-a",
            "name": "Project",
            "chat_messages": [
                {"sender": "human", "text": "Keep [[Obsidian]] links."},
                {
                    "sender": "assistant",
                    "content": [{"type": "text", "text": "Markdown is portable."}],
                },
            ],
        }
    ]
    assert "[human]" in parse(json.dumps(claude), "claude.json")[0].text
    slack = [
        {
            "type": "message",
            "user": user,
            "text": user + " decision",
            "thread_ts": "123.0",
            "ts": f"123.{i}",
        }
        for i, user in enumerate(["U_ALICE", "U_BOB", "U_CAROL"])
    ]
    text = parse(json.dumps(slack), "slack.json")[0].text
    assert all(user in text for user in ("U_ALICE", "U_BOB", "U_CAROL"))
    assert "[assistant]" not in text


def test_unknown_json_stays_raw_and_incomplete_jsonl_does_not_certify_inventory():
    assert parse('{"ordinary": "project metadata"}', "project.json") == []
    with pytest.raises(ConversationError, match="incomplete"):
        list(
            Document(
                "session.jsonl",
                "1",
                "Session",
                '{"type":"session_meta"}\n{"type":',
                normalize_conversations=True,
            ).items()
        )
