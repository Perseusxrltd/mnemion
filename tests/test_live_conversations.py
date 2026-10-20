"""Synthetic live files exercise framing, checkpoints and source boundaries."""

import json
import os
from pathlib import Path

import pytest

from mnemion.connectors.config import ConversationConfig, read_config
from mnemion.connectors.live_conversations import ConversationProvider
from mnemion.connectors.providers import ProviderError
from mnemion.connectors.source_files import SourceReadError, read_selected


def line(text, role="user"):
    return (json.dumps({"role": role, "content": text}, ensure_ascii=False) + "\n").encode()


@pytest.fixture
def source(tmp_path):
    folder = tmp_path / "sessions"
    folder.mkdir()
    config = ConversationConfig(
        path=folder,
        state_directory=tmp_path / "capture",
        scope_id="synthetic-source",
        name="Synthetic conversations",
        members=["employee:reader"],
        publish_to_mapped_members=True,
        segment_bytes=1024,
        segment_records=2,
    )
    return folder / "session.jsonl", config


def capture(config, checkpoint=None, *, acknowledge=True):
    provider = ConversationProvider(config)
    identifier = provider.scopes()[0]
    with provider.snapshot(identifier, checkpoint) as scan:
        items = [value for value in scan.items() if value is not None]
        if acknowledge:
            scan.acknowledge()
        return items, scan.report, scan.checkpoint


def spoken(items):
    return [item for item in items if item.memory and item.memory.metadata.get("projection")]


def raw(items):
    return [item for item in items if item.memory and not item.memory.metadata.get("projection")]


@pytest.mark.parametrize("kind", ["generic", "codex", "claude", "acp"])
def test_message_only_capture_keeps_message_text_and_excludes_structured_private_events(
    source, kind
):
    path, config = source
    config.capture_mode = "messages"
    config.segment_records = 1
    if kind == "generic":
        rows = [
            {"role": "user", "content": "Visible café 東京"},
            {"role": "tool", "content": "Tool payload must stay local"},
            {"role": "assistant", "channel": "analysis", "content": "Reasoning stays local"},
            {"role": "system", "content": "Private instructions"},
            {"role": "assistant", "content": "Visible answer"},
        ]
    elif kind == "codex":
        rows = [
            {"type": "session_meta", "payload": {"id": "capture-fixture"}},
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "Visible café 東京"},
            },
            {
                "type": "event_msg",
                "payload": {"type": "agent_reasoning", "text": "Reasoning stays local"},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "output": "Tool payload must stay local",
                },
            },
            {
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "Visible answer"},
            },
        ]
    elif kind == "claude":
        rows = [
            {
                "type": "user",
                "sessionId": "capture-fixture",
                "message": {"content": "Visible café 東京"},
            },
            {
                "type": "assistant",
                "sessionId": "capture-fixture",
                "message": {
                    "content": [
                        {"type": "thinking", "text": "Reasoning stays local"},
                        {"type": "tool_use", "text": "Tool payload must stay local"},
                        {"type": "text", "text": "Visible answer"},
                    ]
                },
            },
        ]
    else:
        rows = [
            {
                "method": "session/update",
                "params": {
                    "sessionId": "capture-fixture",
                    "update": {"sessionUpdate": kind, "content": {"type": "text", "text": text}},
                },
            }
            for kind, text in [
                ("user_message_chunk", "Visible café 東京"),
                ("tool_call", "Tool payload must stay local"),
                ("agent_thought_chunk", "Reasoning stays local"),
                ("agent_message_chunk", "Visible answer"),
            ]
        ]
    data = b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode() for row in rows)
    path.write_bytes(data)
    items, report, checkpoint = capture(config)
    assert not raw(items) and spoken(items)
    visible = "\n".join(item.memory.content for item in spoken(items))
    assert "Visible café 東京" in visible and "Visible answer" in visible
    encoded = json.dumps([item.model_dump(mode="json") for item in items])
    for excluded in (
        "Reasoning stays local",
        "Tool payload must stay local",
        "Private instructions",
    ):
        assert excluded not in encoded
    assert all(item.memory.metadata["raw_evidence_stored"] is False for item in spoken(items))
    assert all("raw_source_external_id" not in item.memory.metadata for item in spoken(items))
    assert report["captured_prefix_bytes"] == len(data) and report["capture_mode"] == "messages"
    assert json.loads(checkpoint[9:])["capture_mode"] == "messages"
    again, report, _ = capture(config, checkpoint)
    assert all(item.action == "retain" for item in again) and report["bytes_read"] == 0


def test_capture_mode_change_reexamines_source_without_reusing_raw_references(source):
    path, config = source
    path.write_bytes(line("Message retained") + line("Tool data", "tool"))
    original, _, checkpoint = capture(config)
    raw_ids = {item.external_id for item in raw(original)}
    assert raw_ids
    config.capture_mode = "messages"
    selected, report, _ = capture(config, checkpoint)
    assert report["segments_reused"] == 0 and not raw(selected)
    assert not raw_ids.intersection(item.external_id for item in selected)
    assert all("Tool data" not in item.memory.content for item in spoken(selected))


def test_message_only_capture_cannot_disable_its_message_parser(source):
    _, config = source
    with pytest.raises(ValueError, match="requires conversation normalization"):
        ConversationConfig.model_validate(
            {**config.model_dump(), "capture_mode": "messages", "normalize_conversations": False}
        )


def test_half_record_and_split_unicode_are_deferred_then_captured_once(source):
    path, config = source
    complete, later = line("First turn"), line("Later café 東京", "assistant")
    cut = later.index("é".encode()) + 1
    path.write_bytes(complete + later[:cut])
    first, report, checkpoint = capture(config)
    assert len(spoken(first)) == 1
    assert "First turn" in spoken(first)[0].memory.content
    assert report["captured_prefix_bytes"] == len(complete) and report["pending_bytes"] == cut
    with path.open("ab") as stream:
        stream.write(later[cut:])
    second, report, checkpoint = capture(config, checkpoint)
    assert (
        len(spoken(second)) == 1 and spoken(second)[0].external_id == spoken(first)[0].external_id
    )
    assert spoken(second)[0].memory.content.count("First turn") == 1
    assert spoken(second)[0].memory.content.count("Later café 東京") == 1
    assert report["pending_bytes"] == 0
    repeated, report, _ = capture(config, checkpoint)
    assert all(value.action == "retain" and value.memory is None for value in repeated)
    assert report["bytes_read"] == 0


def test_bounded_segments_retain_every_byte_above_the_ordinary_selected_file_cap(source):
    path, config = source
    data = b"".join(line(f"Turn {number} · " + "x" * 300) for number in range(60))
    path.write_bytes(data)
    with pytest.raises(SourceReadError, match="source_too_large"):
        read_selected(path.parent, path.name, maximum=1000)
    items, report, _ = capture(config)
    fragments = raw(items)
    assert len(fragments) > 1
    assert b"".join(value.memory.source.content.encode() for value in fragments) == data
    offset = 0
    for value in fragments:
        metadata = value.memory.metadata
        assert metadata["source_byte_start"] == offset
        offset = metadata["source_byte_end"]
        assert len(value.memory.source.content.encode()) <= config.segment_bytes
    assert offset == report["captured_prefix_bytes"] == len(data)


def test_append_reuses_sealed_fragments_and_keeps_prior_evidence_identity(source):
    path, config = source
    path.write_bytes(b"".join(line(f"Old {i}") for i in range(8)))
    first, _, checkpoint = capture(config)
    with path.open("ab") as stream:
        stream.write(line("New tail"))
    appended, report, checkpoint = capture(config, checkpoint)
    assert report["change"] == "append" and report["segments_reused"] == 3
    assert report["records_rendered"] == 3
    assert {item.external_id for item in first} <= {item.external_id for item in appended}
    assert len([item for item in appended if item.action == "retain"]) == 8
    assert any("New tail" in item.memory.content for item in spoken(appended))
    # The private checkpoint holds source identities and hashes, never message bodies.
    assert b"New tail" not in (config.state_directory / "capture.sqlite3").read_bytes()


def test_prefix_edits_cannot_be_misclassified_as_safe_append(source):
    path, config = source
    original = b"".join(line(f"Old {i}") for i in range(8))
    path.write_bytes(original)
    _, _, checkpoint = capture(config)
    path.write_bytes(original.replace(b"Old 0", b"New 0") + line("Appended"))
    items, report, _ = capture(config, checkpoint)
    assert report["change"] == "rewrite" and report["segments_reused"] == 0
    assert items[0].action == "upsert"
    assert "New 0" in spoken(items)[0].memory.content


def test_append_during_scan_uses_a_frozen_boundary_and_retries_the_rest(source):
    path, config = source
    config.segment_records = 1
    initial = line("Before one") + line("Before two")
    path.write_bytes(initial)
    provider = ConversationProvider(config)
    identifier = provider.scopes()[0]
    with provider.snapshot(identifier, None) as scan:
        iterator = scan.items()
        values = [next(iterator)]
        with path.open("ab") as stream:
            stream.write(line("Arrived during scan"))
        values.extend(item for item in iterator if item is not None)
        assert not any("Arrived during scan" in value.memory.content for value in values)
        assert scan.report["pending_bytes"] > 0
        scan.acknowledge()
        checkpoint = scan.checkpoint
    next_items, report, _ = capture(config, checkpoint)
    assert any("Arrived during scan" in value.memory.content for value in spoken(next_items))
    assert report["pending_bytes"] == 0


def test_changed_earlier_bytes_during_scan_abort_without_acknowledging(source):
    path, config = source
    config.segment_records = 1
    original = line("Before one") + line("Before two")
    path.write_bytes(original)
    provider = ConversationProvider(config)
    identifier = provider.scopes()[0]
    with provider.snapshot(identifier, None) as scan:
        iterator = scan.items()
        next(iterator)
        path.write_bytes(original.replace(b"Before one", b"Edited one") + line("New tail"))
        with pytest.raises(ProviderError, match="source_changed_during_read"):
            list(iterator)
        with pytest.raises(ProviderError, match="inventory_incomplete"):
            scan.acknowledge()
    items, report, _ = capture(config)
    assert report["segments_reused"] == 0 and "Edited one" in spoken(items)[0].memory.content


def test_missing_acknowledgment_and_different_server_checkpoint_force_complete_evidence(source):
    path, config = source
    path.write_bytes(line("An unacknowledged save"))
    first, _, unacknowledged = capture(config, acknowledge=False)
    replay, report, checkpoint = capture(config, unacknowledged)
    assert replay == first and report["segments_reused"] == 0
    again, report, _ = capture(config, "jsonl:other-host-or-restored-database")
    assert again == first and report["segments_reused"] == 0
    assert checkpoint != unacknowledged


def test_codex_session_header_survives_segment_and_checkpoint_boundaries(source):
    path, config = source
    config.segment_records = 1
    header = {"type": "session_meta", "payload": {"id": "synthetic-codex"}}

    def event(text):
        return {"type": "event_msg", "payload": {"type": "user_message", "message": text}}

    path.write_text(
        "\n".join(json.dumps(row) for row in (header, event("First"), event("Second"))) + "\n"
    )
    items, _, checkpoint = capture(config)
    assert len(spoken(items)) == 2
    assert {value.memory.metadata["conversation_id"] for value in spoken(items)} == {
        "synthetic-codex"
    }
    with path.open("a") as stream:
        stream.write(json.dumps(event("Third")) + "\n")
    items, _, _ = capture(config, checkpoint)
    assert {value.memory.metadata["conversation_id"] for value in spoken(items)} == {
        "synthetic-codex"
    }
    assert any("Third" in value.memory.content for value in spoken(items))


def test_acp_event_identity_deduplicates_across_sealed_segments_and_detects_conflicts(source):
    from tests.test_acp_conversations import event

    path, config = source
    config.segment_records = 1
    one = event("agent_message_chunk", "Unique", eventId="one")
    two = event("user_message_chunk", "Continue", eventId="two")
    path.write_text("\n".join(json.dumps(row) for row in (one, two, one)) + "\n")
    items, _, checkpoint = capture(config)
    assert len(raw(items)) == 3 and len(spoken(items)) == 2
    existing = {item.external_id for item in items}
    with path.open("a") as stream:
        stream.write(json.dumps(one) + "\n")
    items, _, checkpoint = capture(config, checkpoint)
    assert {value.external_id for value in items if value.action == "retain"} == existing
    assert len(raw(items)) == 1
    assert not spoken(items)
    with path.open("a") as stream:
        stream.write(json.dumps(event("agent_message_chunk", "Conflicting", eventId="one")) + "\n")
    with pytest.raises(ProviderError, match="conversation_event_conflict"):
        capture(config, checkpoint)


@pytest.mark.parametrize("kind", ["truncate", "rotate", "rename", "delete"])
def test_source_changes_are_distinguished_from_append(source, kind):
    path, config = source
    path.write_bytes(line("First") + line("Second"))
    _, _, checkpoint = capture(config)
    original_scope = ConversationProvider(config).scopes()[0]
    if kind == "truncate":
        path.write_bytes(line("First"))
    elif kind == "rotate":
        alternate = path.with_suffix(".new")
        alternate.write_bytes(line("Rotated"))
        os.replace(alternate, path)
    elif kind == "rename":
        path.rename(path.with_name("renamed.jsonl"))
    else:
        path.unlink()
    current = ConversationProvider(config).scopes()
    if kind in {"rename", "delete"}:
        assert original_scope not in current
    else:
        _, report, _ = capture(config, checkpoint)
        assert report["change"] == {"truncate": "truncation", "rotate": "rotation"}[kind]
        assert report["segments_reused"] == 0


@pytest.mark.parametrize(
    "payload,code",
    [
        (b'{"role": }\n', "conversation_jsonl_record_invalid"),
        (b'{"format":"mnemion-memory-journal"}\n', "journal_requires_complete_connector"),
        (b'{"format":"mnemion-memory-journal-catalog"}\n', "journal_requires_complete_connector"),
        (b"\xff\n", "source_is_not_utf8_text"),
    ],
)
def test_bad_complete_records_and_memory_journals_fail_visibly(source, payload, code):
    path, config = source
    path.write_bytes(payload)
    with pytest.raises(ProviderError, match=code):
        capture(config)


def test_large_record_and_total_file_budgets_are_independent(source):
    path, config = source
    path.write_bytes(line("x" * 1000))
    config.max_record_bytes = 128
    with pytest.raises(ProviderError, match="conversation_record_limit"):
        capture(config)
    config.max_record_bytes = 2048
    config.max_file_bytes = 100
    with pytest.raises(ProviderError, match="conversation_file_limit"):
        capture(config)


def test_cache_owner_is_private_and_cannot_be_reused_for_another_source(source):
    path, config = source
    path.write_bytes(line("Scoped evidence"))
    capture(config)
    if os.name != "nt":
        assert config.state_directory.stat().st_mode & 0o077 == 0
        assert (config.state_directory / "capture.sqlite3").stat().st_mode & 0o077 == 0
    config.scope_id = "another-source"
    with pytest.raises(ProviderError, match="conversation_cache_source_mismatch"):
        capture(config)


def test_jsonl_catalog_excludes_notes_and_selected_symlink_cannot_escape(source, tmp_path):
    path, config = source
    path.write_bytes(line("Allowed"))
    path.with_name("unrelated.md").write_text("This belongs to an ordinary note connector")
    assert len(ConversationProvider(config).scopes()) == 1
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(line("Outside source"))
    link = path.with_name("linked.jsonl")
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks needs Windows developer mode or privilege")
    provider = ConversationProvider(config)
    scopes = provider.scopes()
    bad = next(scope for scope in scopes if provider.paths[scope] == link.name)
    with pytest.raises(ProviderError):
        provider.access(bad)
    good = next(scope for scope in scopes if provider.paths[scope] == path.name)
    assert provider.access(good).external_id == good


def test_configuration_resolves_the_private_checkpoint_beside_the_file(source, tmp_path):
    _, config = source
    value = {
        "service_url": "http://127.0.0.1",
        "service_token": {"env": "FIXTURE_KEY"},
        "connector_id": "00000000-0000-0000-0000-000000000001",
        "provider": {
            **config.model_dump(mode="json"),
            "path": "sessions",
            "state_directory": ".capture",
        },
    }
    selected = tmp_path / "connector.json"
    selected.write_text(json.dumps(value))
    result = read_config(selected)
    assert result.provider.path == tmp_path / "sessions"
    assert result.provider.state_directory == tmp_path / ".capture"
    assert isinstance(result.provider.path, Path)


def test_private_control_material_is_not_published_or_cached(source):
    path, config = source
    token = "mnm_" + "A" * 43
    path.write_bytes(line("Private control " + token))
    with pytest.raises(ProviderError, match="conversation_contains_private_control") as error:
        capture(config)
    assert token not in str(error.value)
    assert token.encode() not in (config.state_directory / "capture.sqlite3").read_bytes()


def test_renderer_upgrade_reexamines_evidence_without_changing_fragment_identity(
    source, monkeypatch
):
    from mnemion.connectors import live_conversations

    path, config = source
    path.write_bytes(line("Before update"))
    _, _, checkpoint = capture(config)
    with path.open("ab") as stream:
        stream.write(line("Appended before update"))
    current, _, checkpoint = capture(config, checkpoint)
    monkeypatch.setattr(live_conversations, "__version__", "99.0.0")
    rebuilt, report, _ = capture(config, checkpoint)
    assert rebuilt == current and report["segments_reused"] == 0


def test_invalidated_reference_cache_resends_evidence_and_deadlines_do_not_commit(source):
    path, config = source
    path.write_bytes(line("Reference cache fixture"))
    first, _, checkpoint = capture(config)
    provider = ConversationProvider(config)
    identifier = provider.scopes()[0]
    with provider.snapshot(identifier, checkpoint) as scan:
        assert all(item.action == "retain" for item in scan.items() if item is not None)
        scan.invalidate()
    rebuilt, report, checkpoint = capture(config, checkpoint)
    assert rebuilt == first and report["segments_reused"] == 0
    with provider.snapshot(identifier, checkpoint) as scan:
        scan.deadline = 0
        with pytest.raises(ProviderError, match="conversation_scan_deadline"):
            list(scan.items())
        with pytest.raises(ProviderError, match="conversation_inventory_incomplete"):
            scan.acknowledge()


def test_unknown_json_field_shapes_remain_raw_evidence(source):
    path, config = source
    path.write_bytes(b'{"format":[],"unknown":{"record":"retained"}}\n')
    items, _, _ = capture(config)
    assert len(raw(items)) == 1 and not spoken(items)
    assert raw(items)[0].memory.source.content.encode() == path.read_bytes()


def test_replacing_only_an_unfinished_tail_preserves_the_captured_generation(source):
    path, config = source
    complete = line("Already captured")
    path.write_bytes(complete + b'{"unfinished":"pending"')
    first, _, checkpoint = capture(config)
    path.write_bytes(complete + b"{")
    reset, report, _ = capture(config, checkpoint)
    assert [item.external_id for item in reset] == [item.external_id for item in first]
    assert all(item.action == "retain" for item in reset) and report["change"] == "tail_reset"


def test_raw_only_capture_does_not_interpret_agent_message_fields(source):
    path, config = source
    config.normalize_conversations = False
    path.write_bytes(b'{"type":"session_meta","payload":{"id":[]}}\n')
    items, _, _ = capture(config)
    assert len(raw(items)) == 1 and not spoken(items)
