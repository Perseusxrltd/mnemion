"""Bounded backfill preserves selected output, restart and deletion history."""

import hashlib
import json
import os
from types import SimpleNamespace

import pytest

from mnemion import backup_encryption
from mnemion.connectors import conversation_capture as capture
from mnemion.connectors import live_conversations as live
from mnemion.connectors.capture_archive import export_archive, restore_new_inbox
from mnemion.connectors.conversation_inbox import open_inbox
from service_tests.test_capture_custody import custody as custody
from service_tests.test_durable_conversation_capture import line, selected as selected
from service_tests.test_headless_durable_capture import cli, headless as headless, prepared
from service_tests.test_live_conversations import conversation_source as conversation_source


def identities(inbox):
    return inbox.connection.execute(
        "SELECT event_id,lineage,digest,state FROM events ORDER BY event_id"
    ).fetchall()


@pytest.mark.parametrize("mode", ["messages", "complete"])
def test_restart_windows_match_one_pass_without_rereading_old_reference_payloads(
    selected, tmp_path, monkeypatch, mode
):
    config, settings = selected
    config.capture_mode = settings[1]["capture_mode"] = mode
    raw = b"".join(line(f"Selected row {i}", "tool" if i % 4 == 3 else "user") for i in range(15))
    path = config.path / "backfill.jsonl"
    path.write_bytes(raw)
    with open_inbox(tmp_path / "reference", settings[1], os.urandom(32), create=True) as reference:
        complete = capture.capture_available(reference, live.ConversationProvider(config))
        assert complete["completed"]
        expected = identities(reference)
    monkeypatch.setattr(capture, "WINDOW_SEGMENTS", 2)
    ends = []
    for attempt in range(10):
        with open_inbox(*settings, create=attempt == 0) as inbox:
            result = capture.capture_available(inbox, live.ConversationProvider(config))
            report = result["scopes"][0]
            checkpoint = inbox.checkpoint(report["external_id"])
            ends.append(checkpoint["complete_end"])
            assert ends[-1] > (ends[-2] if len(ends) > 1 else 0)
            assert checkpoint["complete_sha256"] == hashlib.sha256(raw[: ends[-1]]).hexdigest()
            assert not result["errors"] and result["coverage"]["uncertain_intervals"] == 0
            if result["completed"]:
                assert not result["deferred"] and ends[-1] == len(raw)
                assert result["coverage"]["checking_scopes"] == 0
                assert result["coverage"]["complete_prefix_at"]
                assert identities(inbox) == expected
                assert result["coverage"]["records"] == complete["coverage"]["records"]
                break
            assert result["deferred"] and report["capture"]["segments_rendered"] == 2
            assert checkpoint["scan_complete"] is False
            assert checkpoint["sealed_end"] == checkpoint["complete_end"]
            assert result["coverage"]["checking_scopes"] == 1
            assert result["coverage"]["complete_prefix_at"] is None
    else:
        pytest.fail("Bounded backfill did not converge")
    assert len(ends) > 1
    with open_inbox(*settings) as inbox:
        decrypt = inbox._open

        def only_current_values(value, identity):
            assert not identity.startswith("segment:"), "A settled reference history was decrypted"
            return decrypt(value, identity)

        monkeypatch.setattr(inbox, "_open", only_current_values)
        unchanged = capture.capture_available(inbox, live.ConversationProvider(config))
        assert unchanged["completed"] and unchanged["scopes"][0]["locally_accepted"] == 0
        assert unchanged["scopes"][0]["capture"]["segments_reused"] > 2
        assert identities(inbox) == expected


def test_soft_time_window_commits_before_the_hard_deadline(selected, monkeypatch):
    config, settings = selected
    config.max_scan_seconds = 1
    (config.path / "slow.jsonl").write_bytes(b"".join(line(f"Row {i}") for i in range(20)))
    clock = [0.0]
    monkeypatch.setattr(live, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    render = live.ConversationSnapshot._segment

    def slow_segment(self, *args, **kwargs):
        yield from render(self, *args, **kwargs)
        clock[0] += 0.4

    monkeypatch.setattr(live.ConversationSnapshot, "_segment", slow_segment)
    with open_inbox(*settings, create=True) as inbox:
        result = capture.capture_available(inbox, live.ConversationProvider(config))
        assert result["deferred"] and not result["errors"] and result["pending_events"] > 0
        assert result["scopes"][0]["capture"]["segments_rendered"] == 2
        assert result["coverage"]["examined_prefix_bytes"] > 0
        assert result["coverage"]["unaccepted_observed_bytes"] > 0


def test_duplicate_producer_events_are_not_recaptured_across_windows(selected, monkeypatch):
    config, settings = selected
    config.capture_mode = settings[1]["capture_mode"] = "messages"
    config.segment_records = 1
    monkeypatch.setattr(capture, "WINDOW_SEGMENTS", 1)

    def event(identifier, text):
        return (
            json.dumps(
                {
                    "method": "session/update",
                    "params": {
                        "sessionId": "fixed-session",
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "eventId": identifier,
                            "content": {"type": "text", "text": text},
                        },
                    },
                }
            )
            + "\n"
        ).encode()

    (config.path / "events.jsonl").write_bytes(
        event("first", "One original message")
        + event("first", "One original message")
        + event("second", "One later message")
    )
    for attempt in range(3):
        with open_inbox(*settings, create=attempt == 0) as inbox:
            result = capture.capture_available(inbox, live.ConversationProvider(config))
            assert not result["errors"]
            assert result["completed"] is (attempt == 2)
            if attempt == 2:
                assert result["pending_events"] == 2
                assert result["coverage"]["records"] == {
                    "lines": 3,
                    "selected": 2,
                    "omitted": 1,
                    "unsupported": 0,
                }


@pytest.mark.parametrize("broken", [False, True])
def test_removed_unexamined_suffix_remains_visible_in_history(selected, monkeypatch, broken):
    config, settings = selected
    monkeypatch.setattr(capture, "WINDOW_SEGMENTS", 1)
    rows = [line(f"Raw observed row {i}") for i in range(12)]
    raw = b"".join(rows)
    path = config.path / "shortened.jsonl"
    path.write_bytes(raw)
    with open_inbox(*settings, create=True) as inbox:
        first = capture.capture_available(inbox, live.ConversationProvider(config))
        assert first["deferred"] and first["coverage"]["records"]["lines"] == 2
        prior = identities(inbox)
    shorter = b"".join(rows[:2]) + (b"broken json\n" if broken else rows[2])
    path.write_bytes(shorter)
    with open_inbox(*settings) as inbox:
        next_scan = capture.capture_available(inbox, live.ConversationProvider(config))
        coverage = next_scan["coverage"]
        assert coverage["uncertain_scopes"] == 1
        assert coverage["unresolved_previous_bytes"] == len(raw) - len(shorter)
        assert next_scan["completed"] is not broken
        if broken:
            assert next_scan["errors"] and identities(inbox) == prior
        else:
            repeated = capture.capture_available(inbox, live.ConversationProvider(config))
            assert (
                repeated["coverage"]["unresolved_previous_bytes"]
                == coverage["unresolved_previous_bytes"]
            )


def test_partial_archive_recovers_its_checkpoint_and_finishes_backfill(
    selected, tmp_path, monkeypatch
):
    config, settings = selected
    monkeypatch.setattr(capture, "WINDOW_SEGMENTS", 1)
    raw = b"".join(line(f"Recoverable row {i}") for i in range(5))
    (config.path / "archived.jsonl").write_bytes(raw)
    archive, recovery_key = tmp_path / "partial.capture", backup_encryption.new_key()
    with open_inbox(*settings, create=True) as inbox:
        first = capture.capture_available(inbox, live.ConversationProvider(config))
        assert first["deferred"]
        before = identities(inbox)
        exported = export_archive(
            inbox,
            settings[2],
            archive,
            recovery_key,
            staging_root=tmp_path / "staging",
            name="Partial backfill",
        )
    recovered = restore_new_inbox(
        archive,
        recovery_key,
        tmp_path / "restored",
        staging_root=tmp_path / "staging",
        expected_sha256=exported["archive_sha256"],
    )
    for _ in range(4):
        with open_inbox(recovered.directory, recovered.binding, recovered.inbox_key) as inbox:
            assert set(before) <= set(identities(inbox))
            progress = capture.capture_available(inbox, live.ConversationProvider(config))
            assert not progress["errors"]
            if progress["completed"]:
                assert progress["coverage"]["records"]["lines"] == 5
                assert progress["coverage"]["uncertain_intervals"] == 0
                assert progress["coverage"]["examined_prefix_bytes"] == len(raw)
                break
    else:
        pytest.fail("The recovered prefix did not resume")


def test_real_headless_process_drains_between_windows_and_converges(headless):
    config = headless["config"]
    config.provider.segment_records = 1
    headless["file"].write_text(config.model_dump_json(), encoding="utf-8")
    prepared(headless, child=True)
    raw = b"".join(line(f"Agent backfill message {i}") for i in range(130))
    (config.provider.path / "large.jsonl").write_bytes(raw)
    headless["offline"].set()
    headless["expected"].append(True)
    first = cli(headless, code=2)
    assert headless["observed"] == [64]
    assert first["capture"]["pending_events"] == 64
    assert not first["capture"]["capture_complete"]
    headless["offline"].clear()
    second = cli(headless, code=2)
    assert second["capture"]["reason_code"] == "capture_scan_pending"
    assert second["capture"]["stored_events"] == 128
    assert second["capture"]["pending_events"] == 0
    assert second["capture"]["delivery_complete"] and not second["capture"]["capture_complete"]
    final = cli(headless)
    assert final["completed"] and final["capture"]["stored_events"] == 130
    assert final["capture"]["coverage"]["records"]["selected"] == 130
    assert final["capture"]["coverage"]["examined_prefix_bytes"] == len(raw)
    unchanged = cli(headless)
    assert unchanged["capture"]["locally_accepted"] == 0
    assert unchanged["capture"]["stored_events"] == 130
