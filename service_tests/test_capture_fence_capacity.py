"""Authenticated forgetting keeps working when admission/history budgets fill."""

from dataclasses import replace
import json

import pytest

from mnemion.capture_identity import capture_lineage_id
from mnemion.connectors.conversation_inbox import InboxError, Limits, open_inbox
from service_tests.test_conversation_inbox import (
    SCOPE,
    event,
    inbox_settings as inbox_settings,
    receipt,
)


@pytest.mark.parametrize("settled", [False, True])
def test_every_held_lineage_can_be_forgotten_after_lowering_limits(inbox_settings, settled):
    _, binding, _ = inbox_settings
    selected = [event(binding, external=f"held-{index}") for index in range(3)]
    with open_inbox(*inbox_settings, create=True) as inbox:
        inbox.accept(SCOPE, selected, {}, verify=lambda: True)
        page = inbox.page()["page"]
        if settled:
            inbox.acknowledge(receipt(binding, page))
    with open_inbox(*inbox_settings, limits=replace(Limits(), events=1, pending_bytes=1)) as inbox:
        for item in selected:
            inbox.forget(capture_lineage_id(SCOPE, item["item"]))
        assert inbox.status()["forgotten_events"] == 3
        assert inbox.status()["pending_events"] == 0
        assert (
            inbox.connection.execute(
                "SELECT COUNT(*) FROM events WHERE payload IS NOT NULL"
            ).fetchone()[0]
            == 0
        )
        assert inbox.page() is None
    with open_inbox(*inbox_settings) as inbox:
        repeated = [event(binding, external=f"held-{index}", revision="2") for index in range(3)]
        result = inbox.accept(SCOPE, repeated, {}, verify=lambda: True)
        assert result["locally_accepted"] == 0 and result["forgotten_events"] == 6


def test_forgotten_receipt_settles_all_accepted_items_above_the_new_limit(inbox_settings):
    _, binding, _ = inbox_settings
    selected = [event(binding, external=f"held-{index}") for index in range(3)]
    with open_inbox(*inbox_settings, create=True) as inbox:
        inbox.accept(SCOPE, selected, {}, verify=lambda: True)
        page = inbox.page()["page"]
    with open_inbox(*inbox_settings, limits=replace(Limits(), events=1)) as inbox:
        result = inbox.acknowledge(receipt(binding, page, [item["event_id"] for item in selected]))
        assert result["forgotten_events"] == 3 and result["pending_events"] == 0
        assert result["unknown_pages"] == 0 and inbox.page() is None


def test_full_foreign_fence_history_blocks_new_intake_but_purges_held_data(inbox_settings):
    _, binding, _ = inbox_settings
    selected = [event(binding, external=f"held-{index}") for index in range(3)]
    with open_inbox(*inbox_settings, create=True, limits=replace(Limits(), events=3)) as inbox:
        inbox.accept(SCOPE, selected, {}, verify=lambda: True)
        original = inbox.page()["page"]
        for prefix in "012":
            inbox.forget(prefix * 64)
        identifiers = sorted(
            ["3" * 64, *[capture_lineage_id(SCOPE, item["item"]) for item in selected]]
        )
        fences = {"items": [{"lineage_id": value} for value in identifiers], "next_cursor": None}
        assert inbox.apply_fences(fences) is False
        assert inbox.status()["history"]["fence_history_blocked"] is True
        assert inbox.status()["forgotten_events"] == 3
        assert inbox.status()["pending_events"] == 0
        assert inbox.fence_cursor() is None
        with pytest.raises(InboxError, match="capture_fence_capacity"):
            inbox.accept(SCOPE, [event(binding, external="new")], {}, verify=lambda: True)
        with pytest.raises(InboxError, match="capture_receipt_fenced"):
            inbox.acknowledge(receipt(binding, original))
    with open_inbox(*inbox_settings) as inbox:
        assert inbox.status()["history"]["fence_history_blocked"] is True
        assert inbox.apply_fences(fences) is True
        assert inbox.status()["history"]["fence_history_blocked"] is False
        repeated = [event(binding, external=f"held-{index}", revision="2") for index in range(3)]
        result = inbox.accept(
            SCOPE, [*repeated, event(binding, external="new")], {}, verify=lambda: True
        )
        assert result["locally_accepted"] == result["pending_events"] == 1
        assert result["forgotten_events"] == 6


def test_capacity_recovery_waits_for_the_complete_authenticated_fence_sweep(inbox_settings):
    _, binding, _ = inbox_settings
    with open_inbox(*inbox_settings, create=True, limits=replace(Limits(), events=1)) as inbox:
        first = {"items": [{"lineage_id": "b" * 64}], "next_cursor": "b" * 64}
        assert inbox.apply_fences(first)
        # A direct, earlier fence must restart the sweep, not merely wait for
        # the tail of the old sweep, which would not include this deletion.
        with pytest.raises(InboxError, match="capture_fence_capacity"):
            inbox.forget("a" * 64)
        assert inbox.fence_cursor() is None
    with open_inbox(*inbox_settings) as inbox:
        assert inbox.apply_fences({"items": [{"lineage_id": "a" * 64}], "next_cursor": "a" * 64})
        assert inbox.fence_history_blocked()
        with pytest.raises(InboxError, match="capture_fence_capacity"):
            inbox.accept(SCOPE, [event(binding)], {}, verify=lambda: True)
        assert inbox.apply_fences({"items": [{"lineage_id": "b" * 64}], "next_cursor": None})
        assert not inbox.fence_history_blocked()
        assert inbox.accept(SCOPE, [event(binding)], {}, verify=lambda: True)["pending_events"] == 1


@pytest.mark.parametrize("value", [1, "false", None, {"blocked": True}, "tampered"])
def test_invalid_fence_pause_is_preserved_and_never_treated_as_permission(inbox_settings, value):
    root, _, _ = inbox_settings
    with open_inbox(*inbox_settings, create=True) as inbox:
        ciphertext = inbox._seal(json.dumps(value).encode(), "fence_blocked")
        if value == "tampered":
            ciphertext = ciphertext[:-1] + bytes([ciphertext[-1] ^ 1])
        inbox.connection.execute(
            "INSERT INTO metadata(name,value) VALUES('fence_blocked',?)", (ciphertext,)
        )
        with pytest.raises(InboxError, match="capture_integrity_failed"):
            inbox.apply_fences({"items": [], "next_cursor": None})
    original = (root / "inbox.sqlite3").read_bytes()
    with pytest.raises(InboxError, match="capture_integrity_failed"):
        with open_inbox(*inbox_settings):
            pass
    assert (root / "inbox.sqlite3").read_bytes() == original
