"""Same desktop helper entry used by the app and private native agents."""

import json
from pathlib import Path

import pytest

from mnemion import backup_encryption, desktop_sources as desktop
from mnemion.local_state import LocalSetupError
from mnemion.sdk import Client
from service_tests.test_desktop_durable_capture import (
    custody as custody,
    conversation_source as conversation_source,
    enrolled as enrolled,
    offline,
)
from service_tests.test_live_conversations import encoded


def test_offline_desktop_backup_needs_pause_and_inspection_survives_lost_settings(
    enrolled, monkeypatch, tmp_path
):
    root, source, scan, _ = enrolled
    (Path(source.path) / "pending.jsonl").write_bytes(encoded("Desktop pending backup marker"))
    with monkeypatch.context() as patch:
        offline(patch, root, source)
        captured = desktop.perform(root, scan)
    assert captured["capture"]["pending_events"] == 1
    monkeypatch.setattr(
        Client, "request", lambda *a, **kw: pytest.fail("Capture backup contacted a workspace")
    )
    current = desktop.load(root)
    request = {
        "operation": "capture_export",
        "id": str(source.id),
        "expected_revision": current.revision,
        "file": str(tmp_path / "portable.mnemion-capture"),
        "recovery_key": backup_encryption.new_key(),
        "inbox_key": scan["inbox_key"],
        "confirm": True,
    }
    with pytest.raises(LocalSetupError, match="Pause"):
        desktop.perform(root, request)
    assert not Path(request["file"]).exists()
    paused = desktop.store(
        root, current.revision, [current.sources[0].model_copy(update={"enabled": False})]
    )
    with pytest.raises(LocalSetupError, match="Refresh"):
        desktop.perform(root, request)
    request["expected_revision"] = paused["revision"]
    result = desktop.perform(root, request)
    assert (
        result["status"]["pending_events"] == 1
        and result["workspace_credentials_included"] is False
    )
    assert "inbox_key" not in json.dumps(result)
    (root / "sources.json").write_bytes(b"damaged settings retained")
    inspected = desktop.perform(
        root,
        {
            "operation": "capture_inspect",
            "file": request["file"],
            "recovery_key": request["recovery_key"],
        },
    )
    assert inspected == result
    assert (root / "sources.json").read_bytes() == b"damaged settings retained"
