"""Real encrypted SQLite restart, lost-reply, selection and forgetting boundaries."""

from dataclasses import replace
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from uuid import uuid4

import pytest

from mnemion.capture_identity import canonical_capture_json, capture_event_id, capture_lineage_id
from mnemion.connectors.conversation_inbox import InboxError, Limits, open_inbox
from mnemion.connectors.protocol import Document

SCOPE = "conversation:" + hashlib.sha256(b"synthetic-source\0selected.jsonl").hexdigest()


@pytest.fixture
def inbox_settings(tmp_path):
    binding = {
        name: str(uuid4()) for name in ("tenant_id", "connector_id", "source_id", "grant_id")
    }
    binding.update(namespace="synthetic-source", capture_mode="complete")
    return tmp_path / "private-inbox", binding, os.urandom(32)


def event(
    binding, text="Selected synthetic evidence", external="origin:1", revision="1", **changes
):
    start = int.from_bytes(hashlib.sha256(external.encode()).digest()[:4])
    generation = "a" * 32
    original = f"{SCOPE}:{generation}:bytes:{start}"
    metadata = {
        "path": "selected.jsonl",
        "capture": "mnemion-live-jsonl-v1",
        "source_fragment": True,
        "source_generation": generation,
        "source_byte_start": start,
        "source_byte_end": start + len(text.encode()),
        **changes,
    }
    if changes.get("capture_mode") == "messages":
        original += "#conversation:synthetic"
        metadata["projection"] = "mnemion-conversation-v1"
    item = next(
        Document(
            original,
            hashlib.sha256((revision + text).encode()).hexdigest(),
            "Synthetic fragment",
            text,
            metadata=metadata,
        ).items()
    ).model_dump(mode="json")
    return {
        "event_id": capture_event_id(binding["source_id"], SCOPE, item),
        "producer_scope": SCOPE,
        "item": item,
    }


def receipt(binding, page, forgotten=()):
    return {
        "page_id": page["page_id"],
        "source_id": binding["source_id"],
        "grant_id": binding["grant_id"],
        "durable": True,
        "items": [
            {
                "event_id": item["event_id"],
                "lineage_id": capture_lineage_id(SCOPE, item["item"]),
                "memory_id": str(uuid4()),
                "operation_id": str(uuid4()),
                "outcome": "forgotten" if item["event_id"] in forgotten else "stored",
            }
            for item in page["events"]
        ],
    }


def test_accepted_ciphertext_checkpoint_and_unknown_page_survive_process_restart(inbox_settings):
    root, binding, key = inbox_settings
    marker = "Raw selected marker that must never appear in SQLite"
    selected = event(binding, marker)
    with open_inbox(*inbox_settings, create=True) as inbox:
        result = inbox.accept(
            SCOPE, [selected], {"captured": 321, "context": marker}, verify=lambda: True
        )
        assert result["locally_accepted"] == result["pending_events"] == 1
        first = inbox.page()
        assert first["reconcile"] is False
        assert not inbox.connection.in_transaction
    assert marker.encode() not in (root / "inbox.sqlite3").read_bytes()
    code = """
import json, sys
from pathlib import Path
from mnemion.connectors.conversation_inbox import open_inbox
value = json.load(sys.stdin)
with open_inbox(Path(value['root']), value['binding'], bytes.fromhex(value['key'])) as inbox:
    print(json.dumps(inbox.page()))
"""
    # Synthetic test key goes only through a private child pipe, never argv/env.
    result = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps({"root": str(root), "binding": binding, "key": key.hex()}),
        text=True,
        capture_output=True,
        check=True,
        timeout=20,
    )
    reopened = json.loads(result.stdout)
    assert reopened == {"reconcile": True, "page": first["page"]}
    with open_inbox(*inbox_settings) as inbox:
        assert inbox.checkpoint(SCOPE) == {"captured": 321, "context": marker}
        result = inbox.acknowledge(receipt(binding, first["page"]))
        assert result["pending_events"] == 0 and result["stored_events"] == 1
        assert inbox.page() is None
        assert inbox.connection.execute("SELECT payload FROM events").fetchone()[0] is None
        assert inbox.connection.execute("SELECT payload FROM pages").fetchone()[0] is None
        assert (
            inbox.accept(SCOPE, [selected], {"captured": 321}, verify=lambda: True)[
                "locally_accepted"
            ]
            == 0
        )


@pytest.mark.parametrize("failure", ["verification", "iterator"])
def test_unverified_or_interrupted_capture_rolls_back_items_and_checkpoint(inbox_settings, failure):
    _, binding, _ = inbox_settings
    with open_inbox(*inbox_settings, create=True) as inbox:
        inbox.accept(SCOPE, [event(binding)], {"captured": 100}, verify=lambda: True)

        def selected():
            yield event(binding, external="origin:2")
            if failure == "iterator":
                raise RuntimeError("Synthetic producer changed")

        with pytest.raises((InboxError, RuntimeError)):
            inbox.accept(
                SCOPE, selected(), {"captured": 200}, verify=lambda: failure != "verification"
            )
        assert inbox.status()["pending_events"] == 1
        assert inbox.checkpoint(SCOPE) == {"captured": 100}


def test_quota_stops_before_acknowledging_partial_new_batch(inbox_settings):
    _, binding, _ = inbox_settings
    first = event(binding)
    limit = len(canonical_capture_json(first)) + 1
    with open_inbox(
        *inbox_settings, create=True, limits=replace(Limits(), pending_bytes=limit)
    ) as inbox:
        with pytest.raises(InboxError, match="capture_capacity_blocked"):
            inbox.accept(
                SCOPE,
                [first, event(binding, external="origin:2")],
                {"captured": 2},
                verify=lambda: True,
            )
        assert inbox.status()["pending_events"] == 0
        assert inbox.checkpoint(SCOPE) is None
        assert (
            inbox.accept(SCOPE, [first], {"captured": 1}, verify=lambda: True)["locally_accepted"]
            == 1
        )


def test_pages_are_bounded_and_keep_order_across_multiple_batches(inbox_settings):
    _, binding, _ = inbox_settings
    selected = [
        event(binding, "large selected evidence " * 1500, external=f"origin:{index}")
        for index in range(55)
    ]
    with open_inbox(*inbox_settings, create=True) as inbox:
        inbox.accept(SCOPE, selected, {"captured": 55}, verify=lambda: True)
        delivered = []
        while (next_page := inbox.page()) is not None:
            page = next_page["page"]
            assert 1 <= len(page["events"]) <= 50
            assert len(canonical_capture_json(page)) <= 1_500_000
            delivered.extend(item["event_id"] for item in page["events"])
            inbox.acknowledge(receipt(binding, page))
        assert delivered == [item["event_id"] for item in selected]


@pytest.mark.parametrize(
    "damage", ["grant", "source", "duplicate", "missing", "undurable", "lineage", "operation"]
)
def test_invalid_receipt_cannot_discard_pending_evidence(inbox_settings, damage):
    _, binding, _ = inbox_settings
    with open_inbox(*inbox_settings, create=True) as inbox:
        inbox.accept(SCOPE, [event(binding)], {"captured": 1}, verify=lambda: True)
        page = inbox.page()["page"]
        response = receipt(binding, page)
        if damage in {"grant", "source"}:
            response[damage + "_id"] = str(uuid4())
        if damage == "duplicate":
            response["items"] *= 2
        if damage == "missing":
            response["items"] = []
        if damage == "undurable":
            response["durable"] = False
        if damage == "lineage":
            response["items"][0]["lineage_id"] = "b" * 64
        if damage == "operation":
            response["items"][0]["operation_id"] = None
        with pytest.raises(InboxError, match="capture_receipt_invalid"):
            inbox.acknowledge(response)
        assert inbox.status()["pending_events"] == 1
        assert inbox.page() == {"reconcile": True, "page": page}


def test_forgotten_lineage_fences_unknown_pages_and_future_revisions(inbox_settings):
    _, binding, _ = inbox_settings
    first, other = event(binding), event(binding, external="other")
    with open_inbox(*inbox_settings, create=True) as inbox:
        inbox.accept(SCOPE, [first, other], {"captured": 2}, verify=lambda: True)
        unknown_page = inbox.page()["page"]
        lineage = capture_lineage_id(SCOPE, first["item"])
        inbox.forget(lineage)
        with pytest.raises(InboxError, match="capture_receipt_fenced"):
            inbox.acknowledge(receipt(binding, unknown_page))
        assert inbox.page()["page"]["events"] == [other]
        result = inbox.accept(
            SCOPE, [event(binding, revision="2")], {"captured": 3}, verify=lambda: True
        )
        assert result["locally_accepted"] == 0 and result["forgotten_events"] == 2
        assert result["pending_events"] == 1
    with open_inbox(*inbox_settings) as inbox:
        assert inbox.status()["forgotten_events"] == 2
        assert inbox.page()["page"]["events"] == [other]


def test_receipt_forgetting_purges_all_queued_revisions(inbox_settings):
    _, binding, _ = inbox_settings
    selected = [event(binding, revision="1"), event(binding, revision="2")]
    with open_inbox(*inbox_settings, create=True) as inbox:
        inbox.accept(SCOPE, selected, {"captured": 2}, verify=lambda: True)
        page = inbox.page()["page"]
        result = inbox.acknowledge(receipt(binding, page, forgotten={selected[0]["event_id"]}))
        assert result["pending_events"] == 0 and result["forgotten_events"] == 2
        assert inbox.page() is None


def test_message_selection_rejects_raw_fragment_and_only_stores_selected_projection(inbox_settings):
    root, binding, key = inbox_settings
    binding = {**binding, "capture_mode": "messages"}
    with open_inbox(root, binding, key, create=True) as inbox:
        with pytest.raises(InboxError, match="capture_event_invalid"):
            inbox.accept(
                SCOPE, [event(binding, "unselected raw tool/analysis row")], {}, verify=lambda: True
            )
        accepted = event(
            binding, "selected visible message", capture_mode="messages", raw_evidence_stored=False
        )
        inbox.accept(SCOPE, [accepted], {}, verify=lambda: True)
        assert inbox.page()["page"]["events"] == [accepted]
    assert b"unselected raw tool/analysis row" not in (root / "inbox.sqlite3").read_bytes()


def test_wrong_key_owner_and_missing_state_never_reinitialize(inbox_settings):
    root, binding, key = inbox_settings
    with open_inbox(*inbox_settings, create=True):
        pass
    original = (root / "inbox.sqlite3").read_bytes()
    for other_binding, other_key in [
        (binding, os.urandom(32)),
        ({**binding, "grant_id": str(uuid4())}, key),
    ]:
        with pytest.raises(InboxError, match="capture_integrity_failed"):
            with open_inbox(root, other_binding, other_key):
                pass
        assert (root / "inbox.sqlite3").read_bytes() == original
    with pytest.raises(InboxError, match="capture_already_exists"):
        with open_inbox(*inbox_settings, create=True):
            pass
    (root / "inbox.sqlite3").unlink()
    with pytest.raises(InboxError, match="capture_inbox_missing"):
        with open_inbox(*inbox_settings):
            pass


def test_ciphertext_tampering_and_links_are_rejected(inbox_settings, tmp_path):
    root, binding, _ = inbox_settings
    with open_inbox(*inbox_settings, create=True) as inbox:
        inbox.accept(SCOPE, [event(binding)], {}, verify=lambda: True)
    with sqlite3.connect(root / "inbox.sqlite3") as connection:
        connection.execute("UPDATE events SET payload=zeroblob(length(payload))")
    with open_inbox(*inbox_settings) as inbox:
        with pytest.raises(InboxError, match="capture_integrity_failed"):
            inbox.page()
    (root / "inbox.sqlite3").rename(root / "retained.sqlite3")
    try:
        (root / "inbox.sqlite3").symlink_to(root / "retained.sqlite3")
    except OSError:
        pytest.skip("This OS account cannot create symlinks")
    with pytest.raises(InboxError, match="capture_storage_not_private"):
        with open_inbox(*inbox_settings):
            pass


def test_lowered_admission_limits_keep_backlog_delivery_and_forgetting_available(inbox_settings):
    _, binding, _ = inbox_settings
    selected = [event(binding), event(binding, external="second")]
    with open_inbox(*inbox_settings, create=True) as inbox:
        inbox.accept(SCOPE, selected, {}, verify=lambda: True)
    with open_inbox(*inbox_settings, limits=replace(Limits(), pending_bytes=1, events=1)) as inbox:
        assert inbox.status()["over_limit"] is True
        with pytest.raises(InboxError, match="capture_capacity_blocked"):
            inbox.accept(SCOPE, [event(binding, external="third")], {}, verify=lambda: True)
        page = inbox.page()["page"]
        result = inbox.acknowledge(receipt(binding, page))
        assert result["pending_events"] == 0 and result["stored_events"] == 2
        lineage = capture_lineage_id(SCOPE, selected[0]["item"])
        inbox.forget(lineage)
        assert inbox.forget(lineage)["forgotten_events"] == 1
        with pytest.raises(InboxError, match="capture_fence_capacity"):
            inbox.forget("c" * 64)
        assert inbox.status()["history"]["fence_history_blocked"] is True


def test_actual_sqlite_page_size_and_reduced_database_limit_are_reported(inbox_settings):
    root, binding, _ = inbox_settings
    with open_inbox(*inbox_settings, create=True) as inbox:
        inbox.accept(SCOPE, [event(binding)], {}, verify=lambda: True)
    with sqlite3.connect(root / "inbox.sqlite3") as connection:
        connection.execute("PRAGMA page_size=8192")
        connection.execute("VACUUM")
    with open_inbox(*inbox_settings, limits=replace(Limits(), database_bytes=65536)) as inbox:
        result = inbox.status()
        assert result["database_bytes"] == (root / "inbox.sqlite3").stat().st_size
        assert result["database_bytes"] > 65536 and result["over_limit"] is True
        assert inbox.connection.execute("PRAGMA secure_delete").fetchone()[0] == 1
        with pytest.raises(InboxError, match="capture_capacity_blocked"):
            inbox.accept(SCOPE, [event(binding, external="new")], {}, verify=lambda: True)
        page = inbox.page()["page"]
        assert inbox.acknowledge(receipt(binding, page))["pending_events"] == 0


def test_capture_accounting_does_not_rescan_the_table_per_item(inbox_settings):
    _, binding, _ = inbox_settings
    with open_inbox(*inbox_settings, create=True) as inbox:
        statements = []
        inbox.connection.set_trace_callback(statements.append)
        inbox.accept(
            SCOPE,
            [event(binding, external=f"part:{index}") for index in range(100)],
            {},
            verify=lambda: True,
        )
        assert sum("SUM(CASE WHEN state='pending'" in sql for sql in statements) == 1


def test_settled_receipt_preserves_identity_and_only_advances_forgetting(inbox_settings):
    _, binding, _ = inbox_settings
    with open_inbox(*inbox_settings, create=True) as inbox:
        inbox.accept(SCOPE, [event(binding)], {}, verify=lambda: True)
        page = inbox.page()["page"]
        accepted = receipt(binding, page)
        inbox.acknowledge(accepted)
        original = inbox.connection.execute("SELECT receipt FROM pages").fetchone()[0]
        assert inbox.acknowledge(accepted)["stored_events"] == 1
        conflicting = json.loads(json.dumps(accepted))
        conflicting["items"][0]["memory_id"] = str(uuid4())
        with pytest.raises(InboxError, match="capture_receipt_conflict"):
            inbox.acknowledge(conflicting)
        current = json.loads(json.dumps(accepted))
        current["items"][0].update(outcome="forgotten", memory_id=None, operation_id=None)
        assert inbox.acknowledge(current)["forgotten_events"] == 1
        assert inbox.connection.execute("SELECT receipt FROM pages").fetchone()[0] == original
        with pytest.raises(InboxError, match="capture_receipt_stale"):
            inbox.acknowledge(accepted)


def test_messages_cannot_hide_raw_text_in_source_or_other_namespace(inbox_settings):
    root, binding, key = inbox_settings
    binding = {**binding, "capture_mode": "messages"}
    with open_inbox(root, binding, key, create=True) as inbox:
        for change in ("source", "scope"):
            selected = event(binding, capture_mode="messages", raw_evidence_stored=False)
            if change == "source":
                selected["item"]["memory"]["source"]["content"] = "unselected hidden raw content"
            else:
                selected["producer_scope"] = "conversation:" + "f" * 64
            selected["event_id"] = capture_event_id(
                binding["source_id"], selected["producer_scope"], selected["item"]
            )
            with pytest.raises(InboxError, match="capture_event_invalid"):
                inbox.accept(selected["producer_scope"], [selected], {}, verify=lambda: True)
        assert inbox.status()["pending_events"] == 0


def test_empty_checkpoint_cannot_save_a_private_scope_string(inbox_settings):
    with open_inbox(*inbox_settings, create=True) as inbox:
        with pytest.raises(InboxError, match="capture_checkpoint_invalid"):
            inbox.accept("private source name", [], {}, verify=lambda: True)
        with pytest.raises(InboxError, match="capture_checkpoint_invalid"):
            inbox.checkpoint("private source name")
