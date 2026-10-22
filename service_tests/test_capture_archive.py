"""Portable evidence recovery after producer and original process disappear."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from uuid import uuid4

import pytest

from mnemion import backup_encryption as encryption
from mnemion.capture_policy import CapturePolicy
from mnemion.connectors.capture_archive import (
    CaptureArchiveError,
    export_archive,
    inspect_archive,
    restore_new_inbox,
)
from mnemion.connectors.config import ConversationConfig
from mnemion.connectors.conversation_capture import capture_available
from mnemion.connectors.conversation_inbox import InboxError, open_inbox
from mnemion.connectors.live_conversations import ConversationProvider
from service_tests.test_conversation_inbox import receipt
from service_tests.test_live_conversations import encoded


@pytest.fixture
def captured(tmp_path, request):
    binding = {
        name: str(uuid4()) for name in ("tenant_id", "connector_id", "source_id", "grant_id")
    }
    expiry = getattr(request, "param", "until_deleted") == "expire_after"
    policy = CapturePolicy(
        preset="conversation",
        capture_mode="messages",
        retention="expire_after" if expiry else "until_deleted",
        **(
            {
                "format": "mnemion-capture-policy-v3",
                "retention_days": 30,
                "expiry_scope": "captured_fragment_family",
            }
            if expiry
            else {}
        ),
    )
    binding.update(
        namespace="portable-fixture",
        capture_mode="messages",
        capture_policy=policy.model_dump(mode="json"),
    )
    folder = tmp_path / "producer"
    folder.mkdir()
    config = ConversationConfig(
        path=folder,
        scope_id=binding["namespace"],
        name="Portable fixture",
        members=[],
        publish_to_mapped_members=True,
        capture_mode="messages",
        capture_policy=policy,
    )
    inbox_root, key = tmp_path / "original", os.urandom(32)
    with open_inbox(inbox_root, binding, key, create=True) as inbox:
        (folder / "first.jsonl").write_bytes(encoded("Remembered then deliberately forgotten"))
        capture_available(inbox, ConversationProvider(config))
        first = inbox.page()["page"]
        # Receipts contain the actual per-file lineage, not a synthetic common scope.
        from mnemion.capture_identity import capture_lineage_id

        def acknowledge(page):
            value = receipt(binding, page)
            for item, event in zip(value["items"], page["events"]):
                item["lineage_id"] = capture_lineage_id(event["producer_scope"], event["item"])
            inbox.acknowledge(value)
            return value

        first_receipt = acknowledge(first)
        inbox.forget(first_receipt["items"][0]["lineage_id"])
        (folder / "second.jsonl").write_bytes(encoded("Already accepted by the shared workspace"))
        capture_available(inbox, ConversationProvider(config))
        acknowledge(inbox.page()["page"])
        (folder / "pending.jsonl").write_bytes(
            encoded("PORTABLE_PENDING_MEMORY_é") + encoded("excluded tool marker", "tool")
        )
        capture_available(inbox, ConversationProvider(config))
        pending = inbox.page()["page"]
        inbox.observations.catalog_unavailable()
        state = inbox.status()
    shutil.rmtree(folder)
    return inbox_root, binding, key, pending, state


def exported(tmp_path, captured):
    root, binding, key, _, _ = captured
    archive, secret, staging = (
        tmp_path / "memory.capture",
        encryption.new_key(),
        tmp_path / "staging",
    )
    with open_inbox(root, binding, key) as inbox:
        result = export_archive(
            inbox, key, archive, secret, staging_root=staging, name="Portable fixture"
        )
    return archive, secret, staging, result


@pytest.mark.parametrize("captured", ["until_deleted", "expire_after"], indirect=True)
def test_policy_pending_delivery_fences_and_coverage_survive_fresh_process_recovery(
    tmp_path, captured
):
    archive, secret, staging, result = exported(tmp_path, captured)
    root, binding, key, pending, state = captured
    assert b"PORTABLE_PENDING_MEMORY" not in archive.read_bytes()
    assert b"excluded tool marker" not in archive.read_bytes()
    assert key not in archive.read_bytes()
    inspected = inspect_archive(archive, secret, staging_root=staging)
    assert inspected == result
    assert inspected["binding"] == binding and inspected["status"] == state
    assert (state["pending_events"], state["stored_events"], state["forgotten_events"]) == (1, 1, 1)
    assert not inspected["workspace_credentials_included"] and not inspected["source_enrolled"]
    assert "inbox_key" not in json.dumps(inspected)
    original_digest = hashlib.sha256((root / "inbox.sqlite3").read_bytes()).hexdigest()
    code = """
import json, sys
from pathlib import Path
from mnemion.connectors.capture_archive import restore_new_inbox
from mnemion.connectors.conversation_inbox import open_inbox
v = json.load(sys.stdin)
restored = restore_new_inbox(Path(v['archive']), v['secret'], Path(v['target']),
    staging_root=Path(v['staging']), expected_sha256=v['digest'])
with open_inbox(restored.directory, restored.binding, restored.inbox_key) as inbox:
    print(json.dumps({'status': inbox.status(), 'page': inbox.page(),
        'denials': inbox.connection.execute('SELECT COUNT(*) FROM denials').fetchone()[0],
        'producer_segments': inbox.connection.execute('SELECT COUNT(*) FROM producer_segments').fetchone()[0],
        'checkpoints': inbox.connection.execute('SELECT COUNT(*) FROM checkpoints').fetchone()[0]}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps(
            {
                "archive": str(archive),
                "secret": secret,
                "target": str(tmp_path / "new-device-inbox"),
                "staging": str(staging),
                "digest": inspected["archive_sha256"],
            }
        ),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    observed = json.loads(completed.stdout)
    assert observed["page"] == {"reconcile": True, "page": pending}
    assert observed["status"] == state
    assert observed["denials"] == 1 and observed["checkpoints"] == 3
    assert observed["producer_segments"] > 0
    assert hashlib.sha256((root / "inbox.sqlite3").read_bytes()).hexdigest() == original_digest
    assert not list(staging.iterdir())


@pytest.mark.parametrize("change", ["wrong_key", "tamper", "truncate", "changed_preview"])
def test_unverified_archive_never_publishes_a_replacement_inbox(tmp_path, captured, change):
    archive, secret, staging, result = exported(tmp_path, captured)
    original = archive.read_bytes()
    expected = result["archive_sha256"]
    if change == "wrong_key":
        secret = encryption.new_key()
    elif change == "tamper":
        corrupted = bytearray(original)
        corrupted[-20] ^= 1
        archive.write_bytes(corrupted)
    elif change == "truncate":
        archive.write_bytes(original[:-1])
    else:
        expected = "0" * 64
    destination = tmp_path / "recovered"
    with pytest.raises((CaptureArchiveError, encryption.EncryptionError)):
        restore_new_inbox(
            archive, secret, destination, staging_root=staging, expected_sha256=expected
        )
    assert not destination.exists() and not list(staging.iterdir())
    assert (captured[0] / "inbox.sqlite3").is_file()


def test_existing_evidence_and_cancelled_recovery_are_retained(tmp_path, captured):
    archive, secret, staging, result = exported(tmp_path, captured)
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "sentinel").write_bytes(b"existing evidence")
    with pytest.raises(CaptureArchiveError, match="existing evidence"):
        restore_new_inbox(
            archive,
            secret,
            destination,
            staging_root=staging,
            expected_sha256=result["archive_sha256"],
        )
    assert (destination / "sentinel").read_bytes() == b"existing evidence"
    with pytest.raises(encryption.EncryptionCancelled):
        restore_new_inbox(
            archive,
            secret,
            tmp_path / "cancelled",
            staging_root=staging,
            expected_sha256=result["archive_sha256"],
            cancelled=lambda: True,
        )
    assert not (tmp_path / "cancelled").exists() and not list(staging.iterdir())
    before = archive.read_bytes()
    with open_inbox(*captured[:3]) as inbox, pytest.raises(FileExistsError):
        export_archive(
            inbox, captured[2], archive, secret, staging_root=staging, name="No replacement"
        )
    assert archive.read_bytes() == before


def test_corrupt_local_ciphertext_is_not_blessed_by_a_new_encrypted_backup(tmp_path, captured):
    root, binding, key, _, _ = captured
    archive, staging = tmp_path / "invalid.capture", tmp_path / "staging"
    with open_inbox(root, binding, key) as inbox:
        inbox.connection.execute(
            "UPDATE events SET payload=? WHERE state='pending'", (b"corrupt cipher marker",)
        )
        with pytest.raises((CaptureArchiveError, InboxError)):
            export_archive(
                inbox,
                key,
                archive,
                encryption.new_key(),
                staging_root=staging,
                name="Damaged inbox",
            )
    assert not archive.exists() and not list(staging.iterdir())


def test_outer_decryption_size_limit_refuses_content_before_plaintext_publication(tmp_path):
    plain, archive, recovered = (tmp_path / name for name in ("payload", "archive", "recovered"))
    plain.write_bytes(b"private data" * 100)
    secret = encryption.new_key()
    encryption.encrypt_file(plain, archive, secret, kind="bundle")
    for action in (encryption.verify_file, encryption.decrypt_file):
        args = (
            (archive, recovered, secret) if action is encryption.decrypt_file else (archive, secret)
        )
        with pytest.raises(encryption.EncryptionError, match="size"):
            action(*args, maximum_plaintext_bytes=100)
    assert not recovered.exists()
    assert not any(path.name.startswith(".mnemion-decrypted-") for path in tmp_path.iterdir())


def test_extra_delivery_relationships_cannot_enter_an_authenticated_backup(tmp_path, captured):
    root, binding, key, pending, _ = captured
    archive, staging = tmp_path / "invalid.capture", tmp_path / "staging"
    with open_inbox(root, binding, key) as inbox:
        extra = inbox.connection.execute(
            "SELECT event_id FROM events WHERE state='stored'"
        ).fetchone()[0]
        inbox.connection.execute(
            "INSERT INTO page_events VALUES (?,?)", (pending["page_id"], extra)
        )
        with pytest.raises(CaptureArchiveError):
            export_archive(
                inbox, key, archive, encryption.new_key(), staging_root=staging, name="Damaged page"
            )
    assert not archive.exists() and not list(staging.iterdir())
