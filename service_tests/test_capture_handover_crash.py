"""Real helper process loss around committed grant retirement remains recoverable."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import UUID

import pytest

from mnemion import desktop_capture as capture, desktop_sources as desktop, local_state
from mnemion.connectors import headless_capture as device, headless_capture_control as control
from mnemion.connectors.conversation_inbox import InboxError
from mnemion.sdk import Client
from service_tests.test_desktop_capture_policy import policy_request as policy_request
from service_tests.test_desktop_durable_capture import enrolled as enrolled
from service_tests.test_headless_capture_policy import policy_recovery as policy_recovery
from service_tests.test_headless_durable_capture import (
    conversation_source as conversation_source,
    custody as custody,
    headless as headless,
)


CRASH = """
import json, os, sys
from pathlib import Path
from mnemion import desktop_sources
from mnemion.connectors.config import ConnectorConfig
from mnemion.connectors.headless_capture_control import perform
from mnemion.sdk import Client

fixture = json.load(sys.stdin)
original = Client.request
def interrupted(self, method, path, **options):
    selected = method == 'DELETE' and path == '/v1/capture-grants/' + fixture['old_grant']
    if selected and fixture['point'] == 'before':
        os._exit(73)
    result = original(self, method, path, **options)
    if selected:
        os._exit(73)
    return result
Client.request = interrupted
if fixture['kind'] == 'desktop':
    desktop_sources.perform(Path(fixture['root']), fixture['request'])
else:
    perform(ConnectorConfig.model_validate(fixture['config']), fixture['request'])
raise SystemExit('The selected retirement was not reached')
"""


def crash(fixture):
    result = subprocess.run(
        [sys.executable, "-c", CRASH],
        input=json.dumps(fixture),
        capture_output=True,
        text=True,
        timeout=45,
        cwd=Path(__file__).parents[1],
    )
    assert result.returncode == 73, "The fixture did not reach its hard process exit"
    assert not result.stdout and not result.stderr


@pytest.mark.parametrize("point", ["before", "after"])
def test_desktop_process_loss_retains_pending_recovery_and_reconciles_retirement(
    env, custody, policy_request, monkeypatch, point
):
    root, original, request, _ = policy_request
    original_database = capture.inbox_path(root, original.id) / "inbox.sqlite3"
    original_hash = hashlib.sha256(original_database.read_bytes()).hexdigest()
    archive_hash = hashlib.sha256(Path(request["file"]).read_bytes()).hexdigest()
    crash(
        {
            "kind": "desktop",
            "point": point,
            "old_grant": str(original.custody.grant_id),
            "root": str(root),
            "request": request,
        }
    )
    assert bool(custody[0].status(env.owner, original.custody.grant_id)["revoked_at"]) == (
        point == "after"
    )
    pending = desktop.perform(root, {"operation": "capture_restore_list"})["items"]
    assert len(pending) == 1, "Committed retirement must not lose its protected recovery intent"
    assert pending[0]["previous_grant_revoked"] is False
    assert not desktop.load(root).sources[0].enabled
    finish = {
        "operation": "capture_restore_finish",
        "id": request["source"]["id"],
        "expected_revision": desktop.load(root).revision,
        "credential": request["credential"],
        "inbox_key": request["inbox_key"],
        "file": request["file"],
        "recovery_key": request["recovery_key"],
        "confirm": True,
    }
    with pytest.raises(InboxError, match="capture_retirement_credentials"):
        desktop.perform(root, finish)
    sent = []
    call = Client.request

    def observed(client, method, path, **kwargs):
        if method == "DELETE":
            sent.append(path)
        return call(client, method, path, **kwargs)

    monkeypatch.setattr(Client, "request", observed)
    receipt = desktop.perform(root, {**finish, "retirement_credential": env.token})["recovery"]
    assert sent == ([] if point == "after" else [f"/v1/capture-grants/{original.custody.grant_id}"])
    assert receipt["previous_grant_revoked"] and receipt["status"]["forgotten_events"] == 1
    assert len(desktop.load(root).sources) == 1
    assert desktop.load(root).sources[0].id == UUID(request["source"]["id"])
    assert not desktop.load(root).sources[0].enabled
    assert not desktop.perform(root, {"operation": "capture_restore_list"})["items"]
    assert hashlib.sha256(original_database.read_bytes()).hexdigest() == original_hash
    assert hashlib.sha256(Path(request["file"]).read_bytes()).hexdigest() == archive_hash


@pytest.mark.parametrize("point", ["before", "after"])
def test_headless_process_loss_retains_pending_recovery_and_reconciles_retirement(
    env, policy_recovery, monkeypatch, point
):
    fixture, target, request = policy_recovery
    original = fixture["config"]
    database = device.paths(original)[2] / "inbox.sqlite3"
    original_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    archive_hash = hashlib.sha256(Path(request["archive"]).read_bytes()).hexdigest()
    crash(
        {
            "kind": "headless",
            "point": point,
            "old_grant": str(original.capture.grant_id),
            "config": target.model_dump(mode="json"),
            "request": request,
        }
    )
    assert bool(fixture["custody"].status(env.owner, original.capture.grant_id)["revoked_at"]) == (
        point == "after"
    )
    current = device.status(target)
    assert current["state"] == "recovering", "Committed retirement must retain agent recovery state"
    assert current["recovery"]["previous_grant_revoked"] is False
    assert not current["enabled"]
    finish = {
        "action": "finish",
        "expected_revision": current["revision"],
        "archive": request["archive"],
        "archive_sha256": request["archive_sha256"],
        "recovery_key": request["recovery_key"],
        "confirm": True,
    }
    with pytest.raises(InboxError, match="capture_retirement_credentials"):
        control.perform(target, finish)
    sent = []
    call = Client.request

    def observed(client, method, path, **kwargs):
        if method == "DELETE":
            sent.append(path)
        return call(client, method, path, **kwargs)

    monkeypatch.setattr(Client, "request", observed)
    receipt = control.perform(target, {**finish, "retirement_token": request["retirement_token"]})
    assert sent == ([] if point == "after" else [f"/v1/capture-grants/{original.capture.grant_id}"])
    assert receipt["state"] == "ready" and not receipt["enabled"]
    assert receipt["recovery"]["previous_grant_revoked"]
    with device.opened(target, device.read_record(target)) as (inbox, _, _):
        assert inbox.status()["forgotten_events"] == 1
    assert hashlib.sha256(database.read_bytes()).hexdigest() == original_hash
    assert hashlib.sha256(Path(request["archive"]).read_bytes()).hexdigest() == archive_hash


def test_failed_intent_storage_cannot_retire_the_original_device(
    env, custody, policy_request, monkeypatch
):
    root, original, request, _ = policy_request
    write = local_state.write

    def unavailable(path, value, **options):
        if path.name == f"inbox-recovery-{request['source']['id']}.json":
            raise OSError("Synthetic private storage unavailable")
        return write(path, value, **options)

    monkeypatch.setattr(local_state, "write", unavailable)
    with pytest.raises(OSError, match="private storage unavailable"):
        desktop.perform(root, request)
    assert not custody[0].status(env.owner, original.custody.grant_id)["revoked_at"]
    assert not desktop.perform(root, {"operation": "capture_restore_list"})["items"]
    assert desktop.load(root).sources[0].id == original.id


@pytest.mark.parametrize("point", ["before", "after"])
def test_discard_unconfirmed_retirement_changes_only_the_replacement(
    env, custody, policy_request, point
):
    root, original, request, _ = policy_request
    crash(
        {
            "kind": "desktop",
            "point": point,
            "old_grant": str(original.custody.grant_id),
            "root": str(root),
            "request": request,
        }
    )
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
    assert not desktop.perform(root, {"operation": "capture_restore_list"})["items"]
    assert not desktop.load(root).sources[0].enabled
    assert bool(custody[0].status(env.owner, original.custody.grant_id)["revoked_at"]) == (
        point == "after"
    )
    with capture.opened(root, original, request["previous_inbox_key"]) as (inbox, _):
        assert inbox.status()["forgotten_events"] == 1
