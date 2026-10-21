"""Real selected JSONL capture, offline restart/rotation and quota recovery."""

from dataclasses import replace
import json
import os
from uuid import uuid4

import pytest

from mnemion.connectors.config import ConversationConfig
from mnemion.connectors.conversation_capture import capture_available
from mnemion.connectors.conversation_inbox import Limits, open_inbox
from mnemion.connectors.live_conversations import ConversationProvider
from mnemion.sdk import Client


def line(content, role="user"):
    return (json.dumps({"role": role, "content": content}) + "\n").encode()


@pytest.fixture
def selected(tmp_path, monkeypatch):
    # Local acceptance must not even probe a remote control/health endpoint.
    def forbidden_request(*args, **kwargs):
        pytest.fail("Capture contacted the service before durable local acceptance")

    monkeypatch.setattr(Client, "request", forbidden_request)
    folder = tmp_path / "selected"
    folder.mkdir()
    config = ConversationConfig(
        path=folder,
        state_directory=tmp_path / "legacy-unused",
        scope_id="fixture",
        name="Fixture",
        members=["employee:fixture"],
        publish_to_mapped_members=True,
        segment_records=2,
        segment_bytes=1024,
    )
    binding = {
        name: str(uuid4()) for name in ("tenant_id", "connector_id", "source_id", "grant_id")
    }
    binding.update(namespace=config.scope_id, capture_mode=config.capture_mode)
    return config, (tmp_path / "inbox", binding, os.urandom(32))


@pytest.mark.parametrize("mode", ["complete", "messages"])
def test_offline_capture_survives_restart_producer_removal_and_rotation(selected, mode):
    config, settings = selected
    config.capture_mode = mode
    settings[1]["capture_mode"] = mode
    path = config.path / "chat.jsonl"
    initial = (
        line("Retain this first message")
        + line("private tool marker", "tool")
        + line("Retain this second message")
    )
    path.write_bytes(initial + b'{"role":"user","content":"unfinished')
    with open_inbox(*settings, create=True) as inbox:
        result = capture_available(inbox, ConversationProvider(config))
        assert result["completed"] and result["pending_events"] > 0
        scope = result["scopes"][0]["external_id"]
        assert inbox.checkpoint(scope)["complete_end"] == len(initial)
        count = result["pending_events"]
    with open_inbox(*settings) as inbox:
        repeated = capture_available(inbox, ConversationProvider(config))
        assert repeated["pending_events"] == count
        assert sum(item["locally_accepted"] for item in repeated["scopes"]) == 0
        path.unlink()
        absent = capture_available(inbox, ConversationProvider(config))
        assert absent["completed"] and absent["pending_events"] == count
        page = inbox.page()["page"]
        bodies = json.dumps(page)
        assert "Retain this first message" in bodies and "unfinished" not in bodies
        assert ("private tool marker" in bodies) == (mode == "complete")
        first_ids = {event["event_id"] for event in page["events"]}
    # A new producer generation cannot discard accepted offline evidence.
    path.write_bytes(line("New rotated generation"))
    with open_inbox(*settings) as inbox:
        rotated = capture_available(inbox, ConversationProvider(config))
        assert rotated["completed"] and rotated["pending_events"] > count
        assert inbox.page()["reconcile"] is True
        assert {event["event_id"] for event in inbox.page()["page"]["events"]} == first_ids
        assert inbox.checkpoint(scope)["complete_end"] == path.stat().st_size


def test_backpressure_rolls_back_parser_metadata_then_recovers_same_complete_file(selected):
    config, settings = selected
    path = config.path / "large.jsonl"
    path.write_bytes(
        b"".join(line(f"Selected record {index} " + "text " * 20) for index in range(80))
    )
    with open_inbox(*settings, create=True, limits=replace(Limits(), pending_bytes=2000)) as inbox:
        full = capture_available(inbox, ConversationProvider(config))
        assert not full["completed"] and full["errors"] == ["capture_capacity_blocked"]
        assert full["pending_events"] == 0
        assert inbox.connection.execute("SELECT COUNT(*) FROM producer_segments").fetchone()[0] == 0
        assert inbox.connection.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 0
    with open_inbox(*settings) as inbox:
        recovered = capture_available(inbox, ConversationProvider(config))
        assert recovered["completed"] and recovered["pending_events"] > 40
        scope = recovered["scopes"][0]["external_id"]
        assert inbox.checkpoint(scope)["complete_end"] == path.stat().st_size
        assert recovered["scopes"][0]["capture"]["segments_rendered"] == 40


def test_missing_root_preserves_delivery_queue_and_reports_capture_gap(selected):
    config, settings = selected
    path = config.path / "chat.jsonl"
    path.write_bytes(line("Accepted before root disappeared"))
    with open_inbox(*settings, create=True) as inbox:
        before = capture_available(inbox, ConversationProvider(config))
    path.unlink()
    config.path.rmdir()
    with open_inbox(*settings) as inbox:
        after = capture_available(inbox, ConversationProvider(config))
        assert not after["completed"] and after["errors"] == ["capture_source_unavailable"]
        assert after["pending_events"] == before["pending_events"]
        assert "Accepted before root disappeared" in json.dumps(inbox.page())
