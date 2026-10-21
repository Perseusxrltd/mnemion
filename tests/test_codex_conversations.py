"""Current Codex records from an actual isolated CLI, with legacy compatibility."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from mnemion.connectors.protocol import Document
from mnemion.conversations import Transcript, parse


FIXTURE = Path(__file__).resolve().parents[1] / "service_tests/fixtures/codex-0.163"
MANIFEST = json.loads((FIXTURE / "manifest.json").read_text())


@pytest.mark.parametrize("messages_only", [False, True])
@pytest.mark.parametrize("index,turns", [(0, [0, 1]), (1, [2])])
def test_real_codex_completed_items_preserve_spoken_turns_once(index, turns, messages_only):
    record = MANIFEST["files"][index]
    raw = (FIXTURE / record["file"]).read_bytes()
    assert len(raw) == record["bytes"]
    assert hashlib.sha256(raw).hexdigest() == record["sha256"]
    selection = []
    result = parse(raw.decode(), "fixture", messages_only=messages_only, selection=selection)
    assert len(result) == 1
    transcript = result[0]
    assert transcript.identifier == record["thread_id"]
    assert transcript.turns == len(turns) * 2
    assert selection.count("selected") == len(turns) * 2
    for turn in turns:
        for field in ("prompts", "replies"):
            assert transcript.text.count(MANIFEST[field][turn]) == 1
    assert "environment_context" not in transcript.text
    assert "model_provider" not in transcript.text
    assert len(selection) == len(raw.splitlines())


def test_current_codex_items_exclude_private_blocks_and_preserve_repeated_messages():
    rows = [json.loads(line) for line in (FIXTURE / "resumed.jsonl").read_text().splitlines()]
    user, assistant = [
        row for row in rows if row.get("payload", {}).get("type") == "item_completed"
    ][:2]
    user, assistant = deepcopy(user), deepcopy(assistant)
    user["payload"]["item"]["content"].extend(
        [{"type": kind, "text": "PRIVATE-BLOCK"} for kind in ("image", "Reasoning", "tool_result")]
    )
    reasoning = deepcopy(assistant)
    reasoning["payload"]["item"] = {
        "type": "Reasoning",
        "content": [{"type": "Text", "text": "PRIVATE-REASONING"}],
    }
    legacy = {"type": "event_msg", "payload": {"type": "user_message", "message": "Again"}}
    result = parse(
        json.dumps([rows[0], user, assistant, reasoning, legacy, legacy]),
        "fixture",
        messages_only=True,
    )
    assert len(result) == 1 and result[0].turns == 4
    assert "PRIVATE-" not in result[0].text
    assert result[0].text.count("Again") == 2


def test_invalid_completed_item_and_content_types_cannot_hide_valid_spoken_text():
    header = {"type": "session_meta", "payload": {"id": "fixture"}}
    for kind in (None, [], {}, 12):
        rows = [
            header,
            {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": kind}}},
            {
                "type": "event_msg",
                "payload": {
                    "type": "item_completed",
                    "item": {
                        "type": "UserMessage",
                        "content": [
                            {"type": kind, "text": "PRIVATE"},
                            {"type": "text", "text": "Spoken"},
                        ],
                    },
                },
            },
        ]
        result = parse(json.dumps(rows), "fixture", messages_only=True)
        assert len(result) == 1 and result[0].turns == 1
        assert "Spoken" in result[0].text and "PRIVATE" not in result[0].text


def test_changed_readable_output_has_a_new_revision_without_changing_source_or_identity(
    monkeypatch,
):
    import mnemion.conversations as conversations

    document = Document(
        "fixed-source", "fixed-raw-revision", "Fixture", "raw bytes", normalize_conversations=True
    )

    def render(text):
        monkeypatch.setattr(
            conversations,
            "parse",
            lambda *args: [Transcript("same-thread", "Fixture", "codex", text, 1)],
        )
        return list(document.items())

    before, after = render("Earlier readable output"), render("Corrected readable output")
    assert before[0] == after[0]
    assert before[1].external_id == after[1].external_id
    assert before[1].revision != after[1].revision
    assert before[1].memory.metadata["projection"] == after[1].memory.metadata["projection"]


def test_parser_upgrade_reexamines_a_previously_omitted_codex_prefix(tmp_path, monkeypatch):
    from mnemion.connectors.config import ConversationConfig
    import mnemion.connectors.live_conversations as live

    folder = tmp_path / "selected"
    folder.mkdir()
    original = (FIXTURE / "resumed.jsonl").read_bytes()
    (folder / "session.jsonl").write_bytes(original)
    config = ConversationConfig(
        path=folder,
        state_directory=tmp_path / "state",
        scope_id="fixture",
        name="Fixture",
        members=["reader"],
        publish_to_mapped_members=True,
        capture_mode="messages",
    )

    def scan(checkpoint=None):
        provider = live.ConversationProvider(config)
        scope = provider.scopes()[0]
        with provider.snapshot(scope, checkpoint) as snapshot:
            items = [item for item in snapshot.items() if item is not None]
            snapshot.acknowledge()
            return items, snapshot.checkpoint, snapshot.report

    with monkeypatch.context() as previous:
        previous.setattr(live, "RENDERER_REVISION", "fixture-old-parser")
        previous.setattr(live, "parse", lambda *args, **kwargs: [])
        items, checkpoint, _ = scan()
        assert items == []
    items, checkpoint, report = scan(checkpoint)
    assert report["segments_rendered"] > 0
    text = "\n".join(item.memory.content for item in items)
    for turn in (0, 1):
        assert text.count(MANIFEST["prompts"][turn]) == 1
        assert text.count(MANIFEST["replies"][turn]) == 1
    _, _, repeated = scan(checkpoint)
    assert repeated["segments_rendered"] == 0
    assert (folder / "session.jsonl").read_bytes() == original
