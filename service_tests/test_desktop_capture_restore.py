"""Real helper recovery, fresh device authority and interrupted local publication."""

import base64
import hashlib
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from mnemion import backup_encryption as encryption
from mnemion import desktop_capture as capture, desktop_capture_restore as recovery
from mnemion import desktop_sources as desktop, local_state
from mnemion.connectors.capture_archive import CaptureArchiveError, export_archive
from mnemion.connectors.conversation_inbox import InboxError
from mnemion.desktop_capture_preview import normalize, selection_for
from mnemion.service.capture_models import CaptureGrantInput
from mnemion.service.models import KeyInput
from service_tests.test_desktop_durable_capture import (
    custody as custody,
    conversation_source as conversation_source,
    enrolled as enrolled,
    offline,
)
from service_tests.test_live_conversations import encoded


@pytest.fixture
def recovery_request(env, custody, enrolled, monkeypatch, tmp_path):
    original_root, source, scan, _ = enrolled
    log = Path(source.path) / "chat.jsonl"
    log.write_bytes(encoded("Pending evidence for the replacement desktop"))
    with monkeypatch.context() as patch:
        offline(patch, original_root, source)
        desktop.perform(original_root, scan)
    current = desktop.load(original_root)
    desktop.store(
        original_root, current.revision, [current.sources[0].model_copy(update={"enabled": False})]
    )
    original = desktop.load(original_root).sources[0]
    archive = tmp_path / "device.mnemion-capture"
    recovery_key = encryption.new_key()
    with capture.opened(original_root, original, scan["inbox_key"]) as (inbox, _):
        info = export_archive(
            inbox,
            capture.key_bytes(scan["inbox_key"]),
            archive,
            recovery_key,
            staging_root=tmp_path / "staging",
            name="Original desktop",
        )
    log.unlink()
    service, source_id, _, _, _ = custody
    old_key = UUID(service.status(env.owner, original.custody.grant_id)["device_key_id"])
    env.identities.revoke_key(env.owner, old_key)
    issued = env.identities.create_key(env.owner, source.principal_id, KeyInput(name="New desktop"))
    new_grant = uuid4()
    service.grant(env.owner, source_id, new_grant, CaptureGrantInput(device_key_id=issued["id"]))
    folder = tmp_path / "replacement-sessions"
    folder.mkdir()
    target = original.model_copy(
        update={
            "id": uuid4(),
            "path": str(folder),
            "enabled": False,
            "custody": original.custody.model_copy(update={"grant_id": new_grant}),
            "sealed_key": base64.b64encode(b"OS-sealed replacement application key").decode(),
            "sealed_inbox_key": base64.b64encode(
                b"OS-sealed independent replacement inbox key"
            ).decode(),
        }
    )
    root = local_state.directory(tmp_path / "replacement-device")
    request = {
        "operation": "capture_restore",
        "expected_revision": "not-configured",
        "file": str(archive),
        "recovery_key": recovery_key,
        "archive_sha256": info["archive_sha256"],
        "source": target.model_dump(mode="json", exclude_none=True),
        "preview_hash": normalize(root, selection_for(target), ()).fingerprint,
        "credential": issued["api_key"],
        "retirement_credential": env.token,
        "inbox_key": base64.b64encode(os.urandom(32)).decode(),
        "confirm": True,
    }
    return root, request, original_root, original


@pytest.mark.parametrize("copied_logs", [False, True])
def test_helper_restores_paused_device_and_delivers_without_original_key_or_logs(
    env, custody, recovery_request, copied_logs
):
    root, request, old_root, old_source = recovery_request
    if copied_logs:
        (Path(request["source"]["path"]) / "chat.jsonl").write_bytes(
            encoded("Pending evidence for the replacement desktop")
        )
    original_database = capture.inbox_path(old_root, old_source.id) / "inbox.sqlite3"
    digest = hashlib.sha256(original_database.read_bytes()).hexdigest()
    result = desktop.perform(root, request)
    assert result["recovery"]["source_enabled"] is False
    assert result["recovery"]["status"]["pending_events"] == 1
    assert desktop.perform(root, {"operation": "capture_restore_list"})["items"] == []
    saved = desktop.load(root)
    assert len(saved.sources) == 1 and saved.sources[0].enabled is False
    assert custody[0].status(env.owner, old_source.custody.grant_id)["revoked_at"]
    desktop.store(root, saved.revision, [saved.sources[0].model_copy(update={"enabled": True})])
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
    assert report["capture"]["pending_events"] == 0 and report["capture"]["stored_events"] == 1
    assert hashlib.sha256(original_database.read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("point", ["before_copy_publish", "before_settings", "after_settings"])
def test_interrupted_installation_finishes_from_protected_intent_without_duplicate_source(
    recovery_request, monkeypatch, point
):
    root, request, _, _ = recovery_request
    with monkeypatch.context() as patch:
        if point == "before_copy_publish":
            patch.setattr(
                recovery,
                "_rename_exclusive",
                lambda *a: (_ for _ in ()).throw(
                    OSError("Synthetic interruption before inbox publication")
                ),
            )
        else:
            original_write = local_state.write

            def interrupted(path, value, **options):
                if path == root / "sources.json":
                    if point == "after_settings":
                        original_write(path, value, **options)
                    raise OSError("Synthetic source-settings interruption")
                return original_write(path, value, **options)

            patch.setattr(local_state, "write", interrupted)
        with pytest.raises(OSError):
            desktop.perform(root, request)
    pending = desktop.perform(root, {"operation": "capture_restore_list"})["items"]
    assert len(pending) == 1 and pending[0]["copy_available"] == (point != "before_copy_publish")
    current = desktop.load(root)
    protected = desktop.perform(
        root,
        {
            "operation": "capture_restore_load",
            "id": request["source"]["id"],
            "expected_revision": current.revision,
        },
    )
    assert protected["source"]["sealed_inbox_key"] == request["source"]["sealed_inbox_key"]
    finish = {
        "operation": "capture_restore_finish",
        "id": request["source"]["id"],
        "expected_revision": current.revision,
        "credential": request["credential"],
        "inbox_key": request["inbox_key"],
        "confirm": True,
    }
    if point == "before_copy_publish":
        finish.update(file=request["file"], recovery_key=request["recovery_key"])
    result = desktop.perform(root, finish)
    assert (
        result["recovery"]["source_enrolled"]
        and result["recovery"]["status"]["pending_events"] == 1
    )
    assert len(desktop.load(root).sources) == 1
    assert desktop.perform(root, {"operation": "capture_restore_list"})["items"] == []


@pytest.mark.parametrize("invalid", ["changed_archive", "wrong_copy"])
def test_invalid_evidence_does_not_retire_the_previous_grant(
    env, custody, recovery_request, invalid
):
    root, request, _, original = recovery_request
    if invalid == "changed_archive":
        request["archive_sha256"] = "0" * 64
    else:
        (Path(request["source"]["path"]) / "chat.jsonl").write_bytes(encoded("Wrong copy"))
    with pytest.raises((CaptureArchiveError, local_state.LocalSetupError, InboxError)) as refused:
        desktop.perform(root, request)
    if invalid == "wrong_copy":
        assert refused.value.code == "source_conversation_copy_unverified"
    assert custody[0].status(env.owner, original.custody.grant_id)["revoked_at"] is None
    assert not desktop.load(root).sources
    assert not desktop.perform(root, {"operation": "capture_restore_list"})["items"]


def test_discard_of_unfinished_recovery_revokes_only_replacement_and_preserves_archive(
    env, custody, recovery_request, monkeypatch
):
    root, request, _, _ = recovery_request
    with monkeypatch.context() as patch:
        patch.setattr(
            recovery,
            "_publish",
            lambda *a: (_ for _ in ()).throw(OSError("Synthetic publication interruption")),
        )
        with pytest.raises(OSError):
            desktop.perform(root, request)
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
    assert result["discarded"] and result["replacement_grant_revoked"]
    assert custody[0].status(env.owner, UUID(request["source"]["custody"]["grant_id"]))[
        "revoked_at"
    ]
    assert Path(request["file"]).exists() and not desktop.load(root).sources
    assert not desktop.perform(root, {"operation": "capture_restore_list"})["items"]
