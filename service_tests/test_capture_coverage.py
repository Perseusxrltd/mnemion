"""Coverage is authenticated, restart-safe and separate from accepted bytes."""

from dataclasses import replace
import json
import os
from uuid import uuid4

import pytest

from mnemion.capture_identity import canonical_capture_json
from mnemion.connectors.config import ConversationConfig
from mnemion.connectors.conversation_capture import capture_available
from mnemion.connectors.conversation_inbox import InboxError, Limits, open_inbox
from mnemion.connectors.live_conversations import ConversationProvider
from mnemion.conversations import parse
from mnemion.sdk import Client


def line(value):
    return (json.dumps(value) + "\n").encode()


@pytest.fixture
def selected(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Local coverage made a service request")

    monkeypatch.setattr(Client, "request", forbidden)
    folder = tmp_path / "producer"
    folder.mkdir()
    config = ConversationConfig(
        path=folder,
        state_directory=tmp_path / "unused-mirror",
        scope_id="fixture",
        name="Selected",
        members=["employee:fixture"],
        publish_to_mapped_members=True,
        capture_mode="messages",
        segment_records=2,
        segment_bytes=1024,
    )
    binding = {key: str(uuid4()) for key in ("tenant_id", "connector_id", "source_id", "grant_id")}
    binding.update(namespace=config.scope_id, capture_mode=config.capture_mode)
    return config, (tmp_path / "inbox", binding, os.urandom(32))


@pytest.mark.parametrize("mode", ["messages", "complete"])
def test_selected_prefix_counts_survive_append_reuse_and_restart_without_double_counting(
    selected, mode
):
    config, settings = selected
    config.capture_mode = settings[1]["capture_mode"] = mode
    path = config.path / "session.jsonl"
    rows = [
        {"type": "session_meta", "payload": {"id": "one-session"}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": "First message"}},
        {
            "type": "response_item",
            "payload": {"type": "function_call_output", "output": "private tool marker"},
        },
        {"type": "future_unknown_frame", "payload": {"value": "unknown marker"}},
        {"type": "event_msg", "payload": {"type": "agent_message", "message": "Second message"}},
        {"type": "event_msg", "payload": {"type": "token_count", "tokens": 10}},
    ]
    prefix = b"".join(map(line, rows)) + b"\n"
    tail = b'{"type":"event_msg","payload":{"type":"user_message","message":"App'
    path.write_bytes(prefix + tail)
    expected = (
        {"lines": 7, "selected": 2, "omitted": 4, "unsupported": 1}
        if mode == "messages"
        else {
            "lines": 7,
            "selected": 7,
            "omitted": 0,
            "unsupported": 0,
        }
    )
    with open_inbox(*settings, create=True) as inbox:
        unobserved = inbox.status()["coverage"]
        assert unobserved["catalog"] == "unobserved"
        assert unobserved["capture_mode"] == mode
        first = capture_available(inbox, ConversationProvider(config))
        coverage = first["coverage"]
        assert coverage["capture_mode"] == mode
        assert coverage["records"] == expected
        assert coverage["observed_bytes"] == len(prefix + tail)
        assert coverage["examined_prefix_bytes"] == len(prefix)
        assert coverage["unaccepted_observed_bytes"] == len(tail)
        assert coverage["unknown_prefix_scopes"] == coverage["checking_scopes"] == 0
        assert coverage["history_before_tracking"] == "unknown"
        assert coverage["last_contact_at"] is coverage["last_acknowledged_at"] is None
        queued_since = coverage["queue_nonempty_since"]
        assert queued_since and coverage["complete_prefix_at"]
        assert "private tool marker" not in json.dumps(coverage)
    with open_inbox(*settings) as inbox:
        repeated = capture_available(inbox, ConversationProvider(config))
        assert repeated["coverage"]["records"] == expected
        assert repeated["coverage"]["queue_nonempty_since"] == queued_since
        assert all(not scope["locally_accepted"] for scope in repeated["scopes"])
        with path.open("ab") as stream:
            stream.write(b'end"}}\n')
        appended = capture_available(inbox, ConversationProvider(config))
        expected = {**expected, "lines": 8, "selected": expected["selected"] + 1}
        assert appended["coverage"]["records"] == expected
        assert appended["coverage"]["unaccepted_observed_bytes"] == 0
        assert appended["coverage"]["queue_nonempty_since"] == queued_since
        assert appended["pending_events"] > first["pending_events"]
    assert b"private tool marker" not in (settings[0] / "inbox.sqlite3").read_bytes()


def test_backpressure_records_unaccepted_observation_without_advancing_prefix(selected):
    config, settings = selected
    path = config.path / "large.jsonl"
    path.write_bytes(
        b"".join(line({"role": "user", "content": "message " * 20}) for _ in range(20))
    )
    with open_inbox(*settings, create=True, limits=replace(Limits(), pending_bytes=1024)) as inbox:
        rejected = capture_available(inbox, ConversationProvider(config))
        assert rejected["errors"] == ["capture_capacity_blocked"]
        assert rejected["pending_events"] == 0
        assert rejected["coverage"]["failed_scopes"] == 1
        assert rejected["coverage"]["unknown_prefix_scopes"] == 1
        assert rejected["coverage"]["unaccepted_observed_bytes"] == path.stat().st_size
        assert rejected["coverage"]["examined_prefix_bytes"] == 0
        assert rejected["coverage"]["complete_prefix_at"] is None
        assert inbox.connection.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 0
    with open_inbox(*settings) as inbox:
        recovered = capture_available(inbox, ConversationProvider(config))
        assert recovered["completed"]
        assert (
            recovered["coverage"]["failed_scopes"]
            == recovered["coverage"]["unknown_prefix_scopes"]
            == 0
        )
        assert recovered["coverage"]["records"]["selected"] == 20
        assert recovered["coverage"]["unaccepted_observed_bytes"] == 0


def test_missing_generation_retains_pending_memories_and_unresolved_tail(selected):
    config, settings = selected
    path = config.path / "rotated.jsonl"
    pending_tail = b'{"incomplete":'
    path.write_bytes(line({"role": "user", "content": "First generation"}) + pending_tail)
    with open_inbox(*settings, create=True) as inbox:
        before = capture_available(inbox, ConversationProvider(config))
        last_prefix = before["coverage"]["complete_prefix_at"]
        path.unlink()
        missing = capture_available(inbox, ConversationProvider(config))
        assert missing["pending_events"] == before["pending_events"]
        assert missing["coverage"]["missing_scopes"] == missing["coverage"]["uncertain_scopes"] == 1
        assert missing["coverage"]["complete_prefix_at"] == last_prefix
    path.write_bytes(line({"role": "user", "content": "Next generation"}))
    with open_inbox(*settings) as inbox:
        rotated = capture_available(inbox, ConversationProvider(config))
        assert rotated["pending_events"] > before["pending_events"]
        assert rotated["coverage"]["missing_scopes"] == 0
        assert rotated["coverage"]["uncertain_scopes"] == 1
        assert rotated["coverage"]["unresolved_previous_bytes"] == len(pending_tail)
        assert rotated["coverage"]["records"]["selected"] == 1, (
            "Current prefix, not lifetime fragments"
        )
        assert "First generation" in json.dumps(inbox.page())


def test_unavailable_catalog_is_not_zero_missing_history(selected):
    config, settings = selected
    path = config.path / "gone.jsonl"
    path.write_bytes(line({"role": "user", "content": "Previously observed"}))
    with open_inbox(*settings, create=True) as inbox:
        capture_available(inbox, ConversationProvider(config))
    path.unlink()
    config.path.rmdir()
    with open_inbox(*settings) as inbox:
        for _ in range(2):
            value = capture_available(inbox, ConversationProvider(config))
            assert value["coverage"]["catalog"] == "unavailable"
            assert value["coverage"]["uncertain_intervals"] == 1
            assert value["coverage"]["tracked_scopes"] == 1
    config.path.mkdir()
    with open_inbox(*settings) as inbox:
        value = capture_available(inbox, ConversationProvider(config))
        assert value["coverage"]["catalog"] == "available"
        assert value["coverage"]["missing_scopes"] == 1
        assert value["coverage"]["uncertain_intervals"] == 1


@pytest.mark.parametrize("missing", [False, True])
def test_previous_inbox_keeps_unknown_age_and_old_missing_prefixes(selected, missing):
    config, settings = selected
    path = config.path / "previous.jsonl"
    path.write_bytes(line({"role": "user", "content": "Previous evidence"}))
    with open_inbox(*settings, create=True) as inbox:
        before = capture_available(inbox, ConversationProvider(config))
        scope = before["scopes"][0]["external_id"]
        checkpoint = inbox.checkpoint(scope)
        del checkpoint["accounting"]
        inbox.connection.execute(
            "UPDATE checkpoints SET payload=? WHERE scope=?",
            (
                inbox._seal(canonical_capture_json(checkpoint), "checkpoint:" + scope),
                scope,
            ),
        )
        inbox.connection.execute(
            "DELETE FROM metadata WHERE name='coverage-summary' OR name LIKE 'coverage:%'"
        )
    if missing:
        path.unlink()
    with open_inbox(*settings) as inbox:
        result = capture_available(inbox, ConversationProvider(config))
        assert result["pending_events"] == before["pending_events"]
        assert result["coverage"]["queue_nonempty_since"] is None
        assert result["coverage"]["tracked_scopes"] == 1
        assert result["coverage"]["missing_scopes"] == int(missing)
        assert result["coverage"]["unknown_prefix_scopes"] == int(missing)
        assert result["coverage"]["records"]["selected"] == (0 if missing else 1)


def test_encrypted_coverage_corruption_cannot_be_replaced_with_zero_counters(selected):
    config, settings = selected
    (config.path / "one.jsonl").write_bytes(line({"role": "user", "content": "Evidence"}))
    with open_inbox(*settings, create=True) as inbox:
        capture_available(inbox, ConversationProvider(config))
        encrypted = inbox.connection.execute(
            "SELECT value FROM metadata WHERE name='coverage-summary'"
        ).fetchone()[0]
        inbox.connection.execute(
            "UPDATE metadata SET value=? WHERE name='coverage-summary'",
            (encrypted[:-1] + bytes([encrypted[-1] ^ 1]),),
        )
        with pytest.raises(InboxError, match="capture_integrity_failed"):
            inbox.status()


def test_damaged_checkpoint_records_failed_verification_without_advancing_prefix(selected):
    config, settings = selected
    (config.path / "one.jsonl").write_bytes(line({"role": "user", "content": "Evidence"}))
    with open_inbox(*settings, create=True) as inbox:
        before = capture_available(inbox, ConversationProvider(config))
        scope = before["scopes"][0]["external_id"]
        checkpoint = inbox.checkpoint(scope)
        checkpoint["accounting"]["current"]["selected"] += 1
        inbox.connection.execute(
            "UPDATE checkpoints SET payload=? WHERE scope=?",
            (inbox._seal(canonical_capture_json(checkpoint), "checkpoint:" + scope), scope),
        )
        result = capture_available(inbox, ConversationProvider(config))
        assert not result["completed"]
        assert result["errors"] == ["capture_checkpoint_invalid"]
        assert result["pending_events"] == before["pending_events"]
        assert result["coverage"]["records"] == before["coverage"]["records"]
        assert result["coverage"]["failed_scopes"] == 1
        assert result["coverage"]["checking_scopes"] == 0


def test_coverage_write_failure_rolls_back_selected_bytes_and_checkpoint(selected, monkeypatch):
    config, settings = selected
    (config.path / "one.jsonl").write_bytes(line({"role": "user", "content": "Atomic evidence"}))
    with open_inbox(*settings, create=True) as inbox:
        original = inbox.observations._save

        def fail_accepted(name, value):
            if name.startswith("coverage:") and value.outcome == "accepted":
                raise OSError("Injected local observation write failure")
            return original(name, value)

        monkeypatch.setattr(inbox.observations, "_save", fail_accepted)
        result = capture_available(inbox, ConversationProvider(config))
        assert not result["completed"] and result["pending_events"] == 0
        assert result["coverage"]["unknown_prefix_scopes"] == 1
        assert result["coverage"]["complete_prefix_at"] is None
        assert inbox.connection.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 0


def test_streamed_whitespace_is_counted_with_its_actual_message():
    rows = [
        {
            "method": "session/update",
            "params": {
                "sessionId": "one",
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": text},
                    "eventId": index,
                    "messageId": message,
                },
            },
        }
        for index, (text, message) in enumerate([("Hello", "a"), (" ", "a"), (" ", "b")])
    ]
    selection = []
    expected = parse(json.dumps(rows), "fixture", messages_only=True)
    actual = parse(json.dumps(rows), "fixture", messages_only=True, selection=selection)
    assert actual == expected and actual[0].text.endswith("Hello ")
    assert selection == ["selected", "selected", "omitted"]
