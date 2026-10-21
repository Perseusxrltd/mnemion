"""Field exclusions must survive custody/recovery without retaining excluded values."""

from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from mnemion import backup_encryption
from mnemion.capture_fields import FieldSelectionLimit, select_fields
from mnemion.capture_policy import CapturePolicy
from mnemion.connectors.capture_archive import export_archive, inspect_archive, restore_new_inbox
from mnemion.connectors.config import ConversationConfig
from mnemion.connectors.conversation_capture import capture_available
from mnemion.connectors.conversation_inbox import open_inbox
from mnemion.connectors.live_conversations import ConversationProvider
from mnemion.conversations import parse
from mnemion.desktop_capture_preview import PreviewSelection, preview
from mnemion.service.capture_custody import selected_item
from mnemion.service.connector_models import ConnectorItemInput
from mnemion.service.errors import ServiceError
from service_tests.test_durable_conversation_capture import selected as selected


def policy(mode="messages", **changes):
    return CapturePolicy(
        format="mnemion-capture-policy-v2",
        preset="conversation" if mode == "messages" else "detailed",
        capture_mode=mode,
        retention="until_deleted",
        **{"exclude_fields": ["API_KEY", "password", "text"], **changes},
    )


def configured(selected, mode="messages", **changes):
    config, settings = selected
    chosen = policy(mode, **changes)
    config = ConversationConfig.model_validate(
        {**config.model_dump(), "capture_mode": mode, "capture_policy": chosen}
    )
    settings[1].update(capture_mode=mode, capture_policy=chosen.model_dump(mode="json"))
    return config, settings, chosen


def encoded(rows):
    return b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode() for row in rows)


def test_v1_policy_keeps_its_frozen_serialization_and_fingerprint():
    # This exact payload/hash was read from main d9b40cca before field selection.
    original = {
        "format": "mnemion-capture-policy-v1",
        "preset": "conversation",
        "capture_mode": "messages",
        "include": ["*.jsonl"],
        "exclude": [],
        "retention": "until_deleted",
        "max_file_bytes": 1_000_000_000,
        "max_record_bytes": 2_000_000,
    }
    restored = CapturePolicy.model_validate(original)
    assert restored.model_dump(mode="json") == original
    assert restored.revision == "f9ad9a000624866e894bb7db62ec9f08fae82e7dacc53dd179cdf9bd8b03e856"
    with pytest.raises(ValidationError, match="policy v2"):
        CapturePolicy.model_validate({**original, "exclude_fields": ["password"]})


@pytest.mark.parametrize(
    "names",
    [
        ["API_KEY", "api_key"],
        ["*"],
        ["/payload/password"],
        ["id"],
        ["sessionId"],
        ["role"],
        [""],
        ["a" * 129],
        [f"field_{index}" for index in range(33)],
    ],
)
def test_field_selection_refuses_ambiguous_names_and_identity_changes(names):
    with pytest.raises(ValidationError):
        policy(exclude_fields=names)


def test_wide_records_cannot_exceed_the_field_selection_work_budget():
    value = {"records": [0] * 250_000}
    with pytest.raises(FieldSelectionLimit):
        select_fields(value, ["password"])
    assert len(value["records"]) == 250_000


def test_opted_in_source_mirrors_use_the_same_field_exclusions(selected):
    original_config, _ = selected
    chosen = CapturePolicy.model_validate(
        {
            **policy("complete", exclude_fields=["password"]).model_dump(mode="json"),
            "retention": "source_mirror",
        }
    )
    config = ConversationConfig.model_validate(
        {
            **original_config.model_dump(),
            "capture_mode": "complete",
            "capture_policy": chosen,
        }
    )
    source = config.path / "mirror.jsonl"
    original = encoded(
        [
            {
                "role": "user",
                "content": "Visible mirror content",
                "nested": {"password": "MIRROR_FIELD_SENTINEL"},
            }
        ]
    )
    source.write_bytes(original)
    provider = ConversationProvider(config)
    with provider.snapshot(provider.scopes()[0], None) as snapshot:
        items = list(snapshot.items())
    payload = json.dumps([item.model_dump(mode="json") for item in items])
    assert "Visible mirror content" in payload and "MIRROR_FIELD_SENTINEL" not in payload
    assert source.read_bytes() == original


@pytest.mark.parametrize("mode", ["complete", "messages"])
def test_excluded_values_never_enter_selected_payload_or_recovered_archive(
    selected, tmp_path, mode
):
    config, settings, chosen = configured(selected, mode)
    rows = [
        {
            "role": "user",
            "content": "Visible café \u2028 memory",
            "API_KEY": "CAPTURE_API_SENTINEL",
            "nested": [{"PaSsWoRd": "CAPTURE_NESTED_SENTINEL", "kept": "public nested value"}],
        },
        {"role": "assistant", "content": [{"type": "text", "text": "CAPTURE_TEXT_SENTINEL"}]},
        {
            "role": "user",
            "content": 'Literal password=KEEP_THIS_TEXT and {"api_key":"UNCHANGED_STRING"}',
            "password": "CAPTURE_ROOT_SENTINEL",
        },
    ]
    assert "CAPTURE_TEXT_SENTINEL" in "\n".join(
        item.text for item in parse(json.dumps(rows), "fixture", messages_only=True)
    )
    original = encoded(rows)
    source = config.path / "fields.jsonl"
    source.write_bytes(original)
    selection = PreviewSelection(
        path=str(config.path), capture_mode=mode, capture_policy=chosen, keep_accepted=True
    )
    observed = preview(tmp_path / "preview-unused", selection.model_dump(mode="json"))
    assert observed["field_redaction"] == "json_field_names"
    assert observed["policy_revision"] == chosen.revision
    assert observed["files"][0]["prefix_bytes"] == len(original)
    assert observed["content_saved"] is False
    assert not (tmp_path / "preview-unused").exists()

    archive, secret, staging = (
        tmp_path / "selected.capture",
        backup_encryption.new_key(),
        tmp_path / "staging",
    )
    with open_inbox(*settings, create=True) as inbox:
        result = capture_available(inbox, ConversationProvider(config))
        assert result["completed"] and result["pending_events"] > 0
        page = inbox.page()["page"]
        contents = json.dumps(page, ensure_ascii=False)
        for value in (
            "CAPTURE_API_SENTINEL",
            "CAPTURE_NESTED_SENTINEL",
            "CAPTURE_TEXT_SENTINEL",
            "CAPTURE_ROOT_SENTINEL",
        ):
            assert value not in contents and value not in json.dumps(observed)
        assert (
            "Visible café" in contents
            and "KEEP_THIS_TEXT" in contents
            and "UNCHANGED_STRING" in contents
        )
        assert chosen.exclude_fields == ["api_key", "password", "text"]
        for event in page["events"]:
            item = event["item"]
            assert item["memory"]["metadata"]["field_redaction"] == "json_field_names"
            assert item["memory"]["source"]["content"] == item["memory"]["content"]
            selected_item(
                ConnectorItemInput.model_validate(item),
                mode,
                event["producer_scope"],
                config.scope_id,
                chosen.model_dump(mode="json"),
            )
            tampered = deepcopy(item)
            del tampered["memory"]["metadata"]["field_redaction"]
            with pytest.raises(ServiceError) as refusal:
                selected_item(
                    ConnectorItemInput.model_validate(tampered),
                    mode,
                    event["producer_scope"],
                    config.scope_id,
                    chosen.model_dump(mode="json"),
                )
            assert refusal.value.code == "capture_selection_invalid"
        exported = export_archive(
            inbox, settings[2], archive, secret, staging_root=staging, name="Selected field fixture"
        )
    assert source.read_bytes() == original
    source.unlink()
    assert inspect_archive(archive, secret, staging_root=staging)["binding"] == settings[1]
    restored = restore_new_inbox(
        archive,
        secret,
        tmp_path / "restored",
        staging_root=staging,
        expected_sha256=exported["archive_sha256"],
    )
    assert restored.binding == settings[1]
    with open_inbox(restored.directory, restored.binding, restored.inbox_key) as inbox:
        assert inbox.page()["page"] == page


def test_field_selection_limits_preserve_an_accepted_prefix_and_report_the_gap(selected, tmp_path):
    config, settings, chosen = configured(selected, "complete", exclude_fields=["api_key"])
    path = config.path / "bounded.jsonl"
    initial = encoded([{"role": "user", "content": "Previously accepted memory"}])
    path.write_bytes(initial)
    with open_inbox(*settings, create=True) as inbox:
        before = capture_available(inbox, ConversationProvider(config))
        scope = before["scopes"][0]["external_id"]
        accepted = inbox.page()["page"]
    nested = {"kept": "deep payload"}
    for _ in range(70):
        nested = {"child": nested}
    path.write_bytes(
        initial + encoded([{"role": "user", "content": "Not yet accepted", "nested": nested}])
    )
    observed = preview(
        tmp_path / "preview-unused",
        PreviewSelection(
            path=str(config.path),
            capture_mode="complete",
            capture_policy=chosen,
            keep_accepted=True,
        ).model_dump(mode="json"),
    )
    assert observed["files"][0]["status"] == "field_selection_limit"
    assert observed["files"][0]["prefix_bytes"] == 0
    with open_inbox(*settings) as inbox:
        result = capture_available(inbox, ConversationProvider(config))
        assert not result["completed"]
        assert "conversation_field_selection_limit" in result["errors"]
        assert result["pending_events"] == before["pending_events"]
        assert inbox.checkpoint(scope)["complete_end"] == len(initial)
        assert inbox.page()["page"] == accepted
