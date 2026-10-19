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


def test_grok_companion_preserves_raw_provenance_and_stable_identity_on_repeat_and_append():
    from tests.test_acp_conversations import encoded, event

    rows = [
        event("user_message_chunk", "Keep this source."),
        event("agent_message_chunk", "Saved."),
    ]
    raw = encoded(rows)
    document = Document(
        "grok/updates.jsonl",
        "one",
        "Grok updates",
        raw,
        uri="https://example.invalid/source",
        normalize_conversations=True,
    )
    first = list(document.items())
    assert first == list(document.items()) and len(first) == 2
    assert first[0].memory.source.content == raw
    metadata = first[1].memory.metadata
    assert metadata["conversation_id"] == "synthetic-grok"
    assert metadata["conversation_format"] == "acp-session"
    assert metadata["raw_source_external_id"] == "grok/updates.jsonl"
    assert metadata["raw_document_sha256"] == first[0].memory.metadata["document_sha256"]
    assert first[1].memory.source.uri == document.uri
    assert first[1].memory.claim_status == "observed"
    rows.append(event("user_message_chunk", "Later addition."))
    after = list(
        Document(
            "grok/updates.jsonl", "two", "Grok updates", encoded(rows), normalize_conversations=True
        ).items()
    )
    assert [item.external_id for item in after] == [item.external_id for item in first]
    assert after[1].revision != first[1].revision
    assert after[1].memory.metadata["conversation_turns"] == 3
