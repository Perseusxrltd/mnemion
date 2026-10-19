"""Synthetic Grok Build/ACP logs; no private sessions are read by these tests."""

import json

import pytest

from mnemion.conversations import ConversationError, parse


def event(kind, text, *, session="synthetic-grok", timestamp="2026-10-19T00:00:00Z", **changes):
    return {
        "timestamp": timestamp,
        "method": "session/update",
        "params": {
            "sessionId": session,
            "update": {"sessionUpdate": kind, "content": {"type": "text", "text": text}, **changes},
        },
    }


def encoded(rows):
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)


def test_grok_build_native_minimal_fixture_is_readable_and_stable():
    rows = [
        event("user_message_chunk", "Remember the neutral fixture."),
        event("agent_message_chunk", "Neutral fixture recorded."),
    ]
    first = parse(encoded(rows), "fixture-grok")
    assert first == parse(encoded(rows), "fixture-grok")
    assert len(first) == 1 and first[0].identifier == "synthetic-grok"
    assert first[0].format == "acp-session" and first[0].turns == 2
    assert (
        first[0].text
        == "[user · 2026-10-19T00:00:00Z]\nRemember the neutral fixture.\n\n[assistant · 2026-10-19T00:00:00Z]\nNeutral fixture recorded."
    )


def test_streamed_chunks_preserve_spaces_unicode_and_message_time_bounds():
    rows = [
        event("user_message_chunk", "Keep ", messageId="user-1"),
        event(
            "user_message_chunk",
            "Mémoire 東京.",
            messageId="user-1",
            timestamp="2026-10-19T00:00:01Z",
        ),
        event("agent_message_chunk", "Saved ", messageId="reply-1"),
        event("agent_message_chunk", "🧠", messageId="reply-1"),
    ]
    result = parse(encoded(rows), "fixture")[0]
    assert result.turns == 2 and "Keep Mémoire 東京." in result.text and "Saved 🧠" in result.text
    assert "2026-10-19T00:00:00Z → 2026-10-19T00:00:01Z" in result.text


def test_duplicate_events_need_an_explicit_identity_and_conflicts_are_visible():
    one = event("agent_message_chunk", "ha", eventId="chunk-1")
    result = parse(
        encoded([one, one, event("agent_message_chunk", "ha", eventId="chunk-2")]), "fixture"
    )[0]
    assert result.text.endswith("haha")
    repeated_text = event("agent_message_chunk", "ha")
    assert parse(encoded([repeated_text, repeated_text]), "fixture")[0].text.endswith("haha")
    with pytest.raises(ConversationError, match="conversation_event_conflict"):
        parse(encoded([one, event("agent_message_chunk", "changed", eventId="chunk-1")]), "fixture")


def test_sessions_and_message_boundaries_are_not_combined():
    rows = [
        event("agent_message_chunk", "A1", session="one", messageId="first"),
        event("user_message_chunk", "B1", session="two"),
        event("agent_message_chunk", "A2", session="one", messageId="second"),
        event("agent_message_chunk", "B2", session="two"),
    ]
    first, second = parse(encoded(rows), "fixture")
    assert (first.identifier, second.identifier) == ("one", "two")
    assert first.turns == second.turns == 2
    assert "B1" not in first.text and "A1" not in second.text


def test_thought_tool_status_and_embedded_resources_never_become_spoken_text():
    rows = [
        event("user_message_chunk", "Visible request"),
        event("agent_thought_chunk", "Hidden thought"),
        event("tool_call", "Hidden command"),
        event("usage_update", "Hidden status"),
        event(
            "agent_message_chunk",
            "Hidden resource",
            content={"type": "resource", "text": "Hidden resource"},
        ),
        event("agent_message_chunk", "Visible answer"),
    ]
    result = parse(encoded(rows), "fixture")[0]
    assert result.turns == 2 and "Hidden" not in result.text
    assert "Visible request" in result.text and "Visible answer" in result.text


def test_partial_files_stay_strict_and_source_fallback_identity_stays_stable():
    row = event("user_message_chunk", "Complete message")
    del row["params"]["sessionId"]
    assert parse(encoded([row]), "same-source") == parse(encoded([row]), "same-source")
    assert (
        parse(encoded([row]), "same-source")[0].identifier
        != parse(encoded([row]), "other-source")[0].identifier
    )
    with pytest.raises(ConversationError, match="conversation_json_incomplete_or_invalid"):
        parse(encoded([row]) + '\n{"method":', "fixture")


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("eventId", [], "conversation_event_invalid"),
        ("messageId", {}, "conversation_message_invalid"),
    ],
)
def test_malformed_chunk_identifiers_report_fixed_errors(field, value, code):
    with pytest.raises(ConversationError, match=code):
        parse(encoded([event("user_message_chunk", "Fixture", **{field: value})]), "fixture")


def test_unknown_update_shapes_are_not_fabricated_as_messages():
    rows = [event({}, "Unknown data"), {"method": "session/update", "params": {"update": None}}]
    assert parse(encoded(rows), "fixture") == []
