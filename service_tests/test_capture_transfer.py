"""Device/key transfer keeps selected evidence and authenticates a separate copy."""

import hashlib
import json
import os
from uuid import uuid4

import pytest

from mnemion import backup_encryption as encryption
from mnemion.connectors.capture_archive import CaptureArchiveError, export_archive, inspect_archive
from mnemion.connectors.capture_transfer import restore_device_copy
from mnemion.connectors.conversation_inbox import Inbox, InboxError, open_inbox
from service_tests.test_capture_archive import captured as captured, exported


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
