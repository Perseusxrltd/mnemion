"""Real same-device policy adoption, queue draining and interrupted handover."""

import base64
import hashlib
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from mnemion import backup_encryption as encryption
from mnemion import desktop_capture as capture, desktop_capture_restore as recovery
from mnemion import desktop_sources as desktop, local_state
from mnemion.capture_policy import CapturePolicy
from mnemion.connectors.capture_archive import CaptureArchiveError, export_archive
from mnemion.connectors.conversation_inbox import InboxError
from mnemion.desktop_capture_preview import normalize, selection_for
from mnemion.service.capture_models import CaptureGrantInput, CapturePolicyChange
from mnemion.service.models import KeyInput
from service_tests.test_desktop_durable_capture import (
    custody as custody,
    conversation_source as conversation_source,
    enrolled as enrolled,
    offline,
)
from service_tests.test_live_conversations import encoded


def paused(root):
    current = desktop.load(root)
    desktop.pause(root, current.revision, str(current.sources[0].id))
    return desktop.load(root)


def drain(root, source, scan):
    return desktop.perform(
        root,
        {
            "operation": "capture_drain",
            "id": str(source.id),
            "expected_revision": desktop.load(root).revision,
            "credential": scan["credential"],
            "inbox_key": scan["inbox_key"],
            "confirm": True,
        },
    )


def test_paused_delivery_does_not_read_new_conversations(enrolled, monkeypatch):
    root, source, scan, _ = enrolled
    path = Path(source.path) / "chat.jsonl"
    path.write_bytes(encoded("Old-policy queued evidence"))
    with monkeypatch.context() as patch:
        offline(patch, root, source)
        desktop.perform(root, scan)
    paused(root)
    path.write_bytes(path.read_bytes() + encoded("Must wait for a resumed source"))
    result = drain(root, source, scan)
    assert result["delivery_complete"] and result["remote_committed_events"] == 1
    assert result["status"]["stored_events"] == 1
    assert not desktop.load(root).sources[0].enabled
    assert drain(root, source, scan)["remote_committed_events"] == 0


@pytest.fixture
def policy_request(env, custody, enrolled, tmp_path):
    root, source, scan, reader = enrolled
    folder = Path(source.path)
    (folder / "kept.jsonl").write_bytes(encoded("Kept through policy change"))
    (folder / "forgotten.jsonl").write_bytes(encoded("Forgotten through policy change"))
    assert desktop.perform(root, scan)["capture"]["pending_events"] == 0
    with env.db.transaction(reader) as connection:
        rows = connection.execute(
            "SELECT id FROM mnemion.memories WHERE deleted_at IS NULL"
        ).fetchall()
    forgotten = next(
        row["id"]
        for row in rows
        if "Forgotten through policy change" in env.memory.fetch(reader, row["id"])["content"]
    )
    env.memory.forget(reader, forgotten, expected_version=1, key="desktop-policy-forget")
    original = paused(root).sources[0]
    assert drain(root, original, scan)["delivery_complete"]
    archive, recovery_key = tmp_path / "policy.capture", encryption.new_key()
    with capture.opened(root, original, scan["inbox_key"]) as (inbox, _):
        info = export_archive(
            inbox,
            capture.key_bytes(scan["inbox_key"]),
            archive,
            recovery_key,
            staging_root=tmp_path / "staging",
            name="Before policy change",
        )
    service, source_id, _, _, _ = custody
    policy = CapturePolicy(preset="detailed", capture_mode="complete", retention="until_deleted")
    review = service.policy_review(env.owner, source.connector_id, source_id)
    service.change_policy(
        env.owner,
        source.connector_id,
        source_id,
        uuid4(),
        CapturePolicyChange(
            expected_version=review["source"]["version"],
            review_token=review["review_token"],
            capture_policy=policy,
            previous_grants="retain",
            confirm=True,
        ),
    )
    issued = env.identities.create_key(
        env.owner, source.principal_id, KeyInput(name="Policy device")
    )
    grant = uuid4()
    service.grant(env.owner, source_id, grant, CaptureGrantInput(device_key_id=issued["id"]))
    target = desktop.SavedSource.model_validate(original.model_dump()).model_copy(
        update={
            "id": uuid4(),
            "capture_mode": "complete",
            "capture_policy": policy,
            "custody": original.custody.model_copy(update={"grant_id": grant}),
            "sealed_key": base64.b64encode(b"OS-sealed new policy device key").decode(),
            "sealed_inbox_key": base64.b64encode(b"OS-sealed new policy inbox key").decode(),
        }
    )
    request = {
        "operation": "capture_restore",
        "policy_change": True,
        "replace_id": str(original.id),
        "expected_revision": desktop.load(root).revision,
        "file": str(archive),
        "recovery_key": recovery_key,
        "archive_sha256": info["archive_sha256"],
        "source": target.model_dump(mode="json", exclude_none=True),
        "preview_hash": normalize(root, selection_for(target), ()).fingerprint,
        "credential": issued["api_key"],
        "retirement_credential": env.token,
        "inbox_key": base64.b64encode(os.urandom(32)).decode(),
        "previous_inbox_key": scan["inbox_key"],
        "confirm": True,
    }
    return root, original, request, reader


def test_same_device_policy_adoption_preserves_forgotten_lineage(env, custody, policy_request):
    root, original, request, reader = policy_request
    database = capture.inbox_path(root, original.id) / "inbox.sqlite3"
    original_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    result = desktop.perform(root, request)
    receipt = result["recovery"]
    assert receipt["policy_change"] and receipt["replaced_source_id"] == str(original.id)
    assert receipt["status"]["coverage"]["catalog"] == "unobserved"
    current = desktop.load(root)
    assert len(current.sources) == 1 and not current.sources[0].enabled
    assert capture.enrollment(root, original)["state"] == "retired"
    assert custody[0].status(env.owner, original.custody.grant_id)["revoked_at"]
    assert hashlib.sha256(database.read_bytes()).hexdigest() == original_hash
    assert not desktop.perform(root, {"operation": "capture_restore_list"})["items"]
    desktop.store(root, current.revision, [current.sources[0].model_copy(update={"enabled": True})])
    current = desktop.load(root).sources[0]
    report = desktop.perform(
        root,
        {
            "operation": "scan",
            "source": current.model_dump(mode="json", include=set(desktop.Source.model_fields)),
            "credential": request["credential"],
            "inbox_key": request["inbox_key"],
        },
    )
    assert report["capture"]["delivery_complete"] and report["capture"]["forgotten_events"] >= 1
    with env.db.transaction(reader) as connection:
        rows = connection.execute(
            "SELECT id FROM mnemion.memories WHERE deleted_at IS NULL"
        ).fetchall()
    assert rows and not any(
        "Forgotten through policy change" in env.memory.fetch(reader, row["id"])["content"]
        for row in rows
    )
    assert Path(request["file"]).exists()


def test_policy_adoption_counts_the_locked_original_in_aggregate_storage(
    env, custody, policy_request, monkeypatch
):
    root, original, request, _ = policy_request
    database = capture.inbox_path(root, original.id) / "inbox.sqlite3"
    original_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    with capture.opened(root, original, request["previous_inbox_key"]) as (inbox, _):
        original_bytes = inbox.status()["database_bytes"]
    # The replacement alone fits. Its still-retained original must also count,
    # including while its verified connection stays locked during policy copy.
    monkeypatch.setattr(capture, "DEVICE_DATABASE_BYTES", original_bytes)
    with pytest.raises(InboxError, match="capture_capacity_blocked"):
        desktop.perform(root, request)
    assert not custody[0].status(env.owner, original.custody.grant_id)["revoked_at"]
    assert not desktop.perform(root, {"operation": "capture_restore_list"})["items"]
    assert hashlib.sha256(database.read_bytes()).hexdigest() == original_hash
    assert desktop.load(root).sources[0].id == original.id


@pytest.mark.parametrize("point", ["before_copy_publish", "before_settings", "after_settings"])
def test_policy_handover_finishes_after_interruption(policy_request, monkeypatch, point):
    root, original, request, _ = policy_request
    with monkeypatch.context() as patch:
        if point == "before_copy_publish":

            def stop(*args):
                raise OSError("Synthetic interruption before policy copy publication")

            patch.setattr(recovery, "_rename_exclusive", stop)
        else:
            write = local_state.write

            def stop(path, value, **options):
                if path == root / "sources.json":
                    if point == "after_settings":
                        write(path, value, **options)
                    raise OSError("Synthetic policy settings interruption")
                return write(path, value, **options)

            patch.setattr(local_state, "write", stop)
        with pytest.raises(OSError):
            desktop.perform(root, request)
    pending = desktop.perform(root, {"operation": "capture_restore_list"})["items"]
    assert len(pending) == 1 and pending[0]["policy_change"]
    if point != "after_settings":
        current = desktop.load(root)
        with pytest.raises(InboxError, match="capture_recovery_pending"):
            desktop.store(
                root, current.revision, [current.sources[0].model_copy(update={"enabled": True})]
            )
    finish = {
        "operation": "capture_restore_finish",
        "id": request["source"]["id"],
        "expected_revision": desktop.load(root).revision,
        "credential": request["credential"],
        "inbox_key": request["inbox_key"],
        "confirm": True,
    }
    if point == "before_copy_publish":
        finish.update(file=request["file"], recovery_key=request["recovery_key"])
    assert desktop.perform(root, finish)["recovery"]["policy_change"]
    saved = desktop.load(root).sources
    assert len(saved) == 1 and saved[0].id == UUID(request["source"]["id"]) and not saved[0].enabled
    assert capture.inbox_path(root, original.id).exists()
    assert not desktop.perform(root, {"operation": "capture_restore_list"})["items"]


def test_stale_backup_with_same_counters_cannot_replace_device(env, custody, policy_request):
    root, original, request, _ = policy_request
    with capture.opened(root, original, request["previous_inbox_key"]) as (inbox, _):
        # Keep counts equal while changing retained provenance: only comparing
        # status or file lengths would miss this newer checkpoint.
        scope = inbox.connection.execute("SELECT scope FROM checkpoints LIMIT 1").fetchone()[0]
        value = inbox.checkpoint(scope)
        value["checkpoint"] = "newer local observation"
        with inbox._transaction():
            import json

            inbox.connection.execute(
                "UPDATE checkpoints SET payload=? WHERE scope=?",
                (
                    inbox._seal(json.dumps(value).encode(), "checkpoint:" + scope),
                    scope,
                ),
            )
    with pytest.raises(CaptureArchiveError, match="fresh capture backup"):
        desktop.perform(root, request)
    assert custody[0].status(env.owner, original.custody.grant_id)["revoked_at"] is None
    assert desktop.load(root).sources[0].id == original.id
    assert not desktop.perform(root, {"operation": "capture_restore_list"})["items"]


def test_discarded_handover_keeps_old_inbox_available_for_reviewed_retry(
    env, custody, policy_request, monkeypatch
):
    root, original, request, _ = policy_request
    write = local_state.write
    with monkeypatch.context() as patch:

        def stop(path, value, **options):
            if path == root / "sources.json":
                raise OSError("Synthetic policy interruption after retiring original enrollment")
            return write(path, value, **options)

        patch.setattr(local_state, "write", stop)
        with pytest.raises(OSError):
            desktop.perform(root, request)
    assert capture.enrollment(root, original)["state"] == "retired"
    result = desktop.perform(
        root,
        {
            "operation": "capture_restore_discard",
            "id": request["source"]["id"],
            "expected_revision": desktop.load(root).revision,
            "credential": request["credential"],
            "confirm": True,
        },
    )
    assert result["discarded"] and not desktop.load(root).sources[0].enabled
    assert capture.enrollment(root, original)["state"] == "revoked"
    with capture.opened(root, original, request["previous_inbox_key"]) as (inbox, _):
        assert inbox.status()["pending_events"] == 0
        assert inbox.status()["forgotten_events"] == 1
    service = custody[0]
    old_grant = service.status(env.owner, UUID(request["source"]["custody"]["grant_id"]))
    assert old_grant["revoked_at"]
    new_grant = uuid4()
    service.grant(
        env.owner,
        original.custody.source_id,
        new_grant,
        CaptureGrantInput(device_key_id=UUID(old_grant["device_key_id"])),
    )
    request["source"]["id"] = str(uuid4())
    request["source"]["custody"]["grant_id"] = str(new_grant)
    request["inbox_key"] = base64.b64encode(os.urandom(32)).decode()
    request["source"]["sealed_inbox_key"] = base64.b64encode(
        b"OS-sealed reviewed retry inbox key"
    ).decode()
    result = desktop.perform(root, request)
    assert result["recovery"]["policy_change"] and not result["recovery"]["source_enabled"]
    assert len(desktop.load(root).sources) == 1
