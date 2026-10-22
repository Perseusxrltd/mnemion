"""Device/key transfer keeps selected evidence and authenticates a separate copy."""

import hashlib
from dataclasses import replace
import json
import os
from uuid import uuid4

import pytest

from mnemion import backup_encryption as encryption
from mnemion.connectors.capture_archive import (
    CaptureArchiveError,
    export_archive,
    inspect_archive,
    restore_new_inbox,
)
from mnemion.connectors.capture_transfer import restore_device_copy, restore_policy_copy
from mnemion.connectors.conversation_inbox import Inbox, InboxError, Limits, open_inbox
from service_tests.test_capture_archive import captured as captured, exported
from service_tests.test_conversation_inbox import receipt


@pytest.mark.parametrize("rotate_key", [False, True])
def test_unretained_fence_pause_survives_archive_and_device_key_recovery(
    tmp_path, captured, rotate_key
):
    root, binding, key, pending, _ = captured
    limits = replace(Limits(), events=1)
    archive, secret, staging = (
        tmp_path / "paused.capture",
        encryption.new_key(),
        tmp_path / "staging",
    )
    with open_inbox(root, binding, key, limits=limits) as inbox:
        assert not inbox.apply_fences({"items": [{"lineage_id": "f" * 64}], "next_cursor": None})
        state = inbox.status()
        exported = export_archive(
            inbox, key, archive, secret, staging_root=staging, name="Paused history"
        )
    assert inspect_archive(archive, secret, staging_root=staging)["status"] == state
    args = {
        "staging_root": staging,
        "expected_sha256": exported["archive_sha256"],
    }
    if rotate_key:
        restored = restore_device_copy(
            archive,
            secret,
            tmp_path / "recovered",
            **args,
            selected_binding={**binding, "grant_id": str(uuid4())},
            inbox_key=os.urandom(32),
        )
    else:
        restored = restore_new_inbox(archive, secret, tmp_path / "recovered", **args)
    with open_inbox(
        restored.directory, restored.binding, restored.inbox_key, limits=limits
    ) as inbox:
        assert inbox.status() == state
        assert inbox.fence_history_blocked() and inbox.fence_cursor() is None
        assert inbox.page() == {"reconcile": True, "page": pending}
        with pytest.raises(InboxError, match="capture_fence_capacity"):
            inbox.accept(pending["events"][0]["producer_scope"], [], {}, verify=lambda: True)


def test_new_device_key_preserves_unknown_pages_fences_and_original_receipts(tmp_path, captured):
    archive, secret, staging, inspected = exported(tmp_path, captured)
    root, original, old_key, pending, status = captured
    before = hashlib.sha256((root / "inbox.sqlite3").read_bytes()).hexdigest()
    selected = {**original, "grant_id": str(uuid4())}
    new_key = os.urandom(32)
    target = tmp_path / "new-device"
    recovered = restore_device_copy(
        archive,
        secret,
        target,
        staging_root=staging,
        expected_sha256=inspected["archive_sha256"],
        selected_binding=selected,
        inbox_key=new_key,
    )
    assert recovered.binding == selected and recovered.inbox_key == new_key
    with open_inbox(target, selected, new_key) as inbox:
        assert inbox.status() == status and inbox.page() == {"reconcile": True, "page": pending}
        receipts = [
            json.loads(inbox._open(value, "receipt:" + page_id))
            for page_id, value in inbox.connection.execute(
                "SELECT page_id,receipt FROM pages WHERE receipt IS NOT NULL"
            )
        ]
        assert receipts and all(value["grant_id"] == original["grant_id"] for value in receipts)
        second = tmp_path / "after-device-recovery.capture"
        exported_again = export_archive(
            inbox, new_key, second, secret, staging_root=staging, name="New device"
        )
    assert inspect_archive(second, secret, staging_root=staging) == exported_again
    for binding, key in [(selected, old_key), (original, new_key), (original, old_key)]:
        with pytest.raises(InboxError), open_inbox(target, binding, key):
            pytest.fail("An old key or grant opened the new device inbox")
    assert hashlib.sha256((root / "inbox.sqlite3").read_bytes()).hexdigest() == before
    assert not list(staging.iterdir())


@pytest.mark.parametrize("pending", [True, False])
def test_policy_transfer_requires_settled_pages_and_keeps_history(tmp_path, captured, pending):
    root, binding, key, unknown, _ = captured
    if not pending:
        from mnemion.capture_identity import capture_lineage_id

        with open_inbox(root, binding, key) as inbox:
            accepted = receipt(binding, unknown)
            for item, event in zip(accepted["items"], unknown["events"], strict=True):
                item["lineage_id"] = capture_lineage_id(event["producer_scope"], event["item"])
            inbox.acknowledge(accepted)
            history = inbox.status()["history"]
            checkpoints = {
                scope: inbox.checkpoint(scope)
                for (scope,) in inbox.connection.execute("SELECT scope FROM checkpoints")
            }
    archive, secret, staging, inspected = exported(tmp_path, captured)
    before = archive.read_bytes()
    selected = {
        **binding,
        "grant_id": str(uuid4()),
        "capture_mode": "complete",
        "capture_policy": {
            **binding["capture_policy"],
            "capture_mode": "complete",
            "preset": "detailed",
        },
    }
    target, new_key = tmp_path / "new-policy", os.urandom(32)
    args = dict(
        staging_root=staging,
        expected_sha256=inspected["archive_sha256"],
        selected_binding=selected,
        inbox_key=new_key,
    )
    if pending:
        with pytest.raises(CaptureArchiveError, match="old-policy page"):
            restore_policy_copy(archive, secret, target, **args)
        assert not target.exists()
    else:
        restored = restore_policy_copy(archive, secret, target, **args)
        assert restored.original_binding == binding and restored.binding == selected
        with open_inbox(target, selected, new_key) as inbox:
            status = inbox.status()
            assert status["pending_events"] == status["unknown_pages"] == 0
            assert status["coverage"]["capture_mode"] == "complete"
            assert status["coverage"]["catalog"] == "unobserved"
            for field in ("events", "producer_events", "fragments", "delivery_pages", "denials"):
                assert status["history"][field] == history[field]
            assert all(inbox.checkpoint(scope) == value for scope, value in checkpoints.items())
            assert inbox.page() is None
            for page_id, value in inbox.connection.execute("SELECT page_id,receipt FROM pages"):
                assert (
                    json.loads(inbox._open(value, "receipt:" + page_id))["grant_id"]
                    == binding["grant_id"]
                )
    assert archive.read_bytes() == before and not list(staging.iterdir())


@pytest.mark.parametrize("change", ["tenant_id", "connector_id", "source_id", "namespace"])
def test_policy_transfer_cannot_move_evidence_to_another_source(tmp_path, captured, change):
    archive, secret, staging, inspected = exported(tmp_path, captured)
    selected = {**captured[1], "grant_id": str(uuid4()), change: str(uuid4())}
    selected["capture_policy"] = {**selected["capture_policy"], "exclude": ["private/*.jsonl"]}
    target = tmp_path / "wrong-policy-target"
    with pytest.raises(CaptureArchiveError, match="original source"):
        restore_policy_copy(
            archive,
            secret,
            target,
            staging_root=staging,
            expected_sha256=inspected["archive_sha256"],
            selected_binding=selected,
            inbox_key=os.urandom(32),
        )
    assert not target.exists()


@pytest.mark.parametrize("change", ["tenant_id", "source_id", "namespace", "capture_mode"])
def test_device_transfer_never_relabels_original_evidence(tmp_path, captured, change):
    archive, secret, staging, inspected = exported(tmp_path, captured)
    selected = {**captured[1], "grant_id": str(uuid4())}
    selected[change] = "complete" if change == "capture_mode" else str(uuid4())
    if change == "capture_mode":
        selected["capture_policy"] = {
            **selected["capture_policy"],
            "preset": "detailed",
            "capture_mode": "complete",
        }
    target = tmp_path / "wrong-identity"
    with pytest.raises(CaptureArchiveError):
        restore_device_copy(
            archive,
            secret,
            target,
            staging_root=staging,
            expected_sha256=inspected["archive_sha256"],
            selected_binding=selected,
            inbox_key=os.urandom(32),
        )
    assert not target.exists() and not list(staging.iterdir())


def test_interrupted_reencryption_never_publishes_a_partially_changed_copy(
    tmp_path, captured, monkeypatch
):
    archive, secret, staging, inspected = exported(tmp_path, captured)
    before = archive.read_bytes()
    seal, calls = Inbox._seal, 0

    def stop_during_write(self, *args):
        nonlocal calls
        value = seal(self, *args)
        calls += 1
        if calls == 3:
            raise encryption.EncryptionCancelled("Synthetic device-copy interruption")
        return value

    monkeypatch.setattr(Inbox, "_seal", stop_during_write)
    target = tmp_path / "interrupted"
    with pytest.raises(encryption.EncryptionCancelled):
        restore_device_copy(
            archive,
            secret,
            target,
            staging_root=staging,
            expected_sha256=inspected["archive_sha256"],
            selected_binding={**captured[1], "grant_id": str(uuid4())},
            inbox_key=os.urandom(32),
        )
    assert calls == 3 and not target.exists() and archive.read_bytes() == before
    assert not list(staging.iterdir())
    assert not any(path.name.startswith("capture-device-") for path in tmp_path.iterdir())
