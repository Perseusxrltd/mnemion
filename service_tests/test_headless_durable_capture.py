"""Headless process/HTTP custody tests on isolated PostgreSQL and local files."""

import asyncio
import base64
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
from uuid import uuid4

from fastapi.responses import JSONResponse
import pytest

from mnemion import local_state
from mnemion.connectors import headless_capture as device
from mnemion.connectors.config import ConnectorConfig, read_config
from mnemion.connectors.conversation_inbox import InboxError
from mnemion.connectors.capture_archive import CaptureArchiveError
from mnemion.connectors.headless_capture_control import perform
from mnemion.connectors.runner import sync
from mnemion.private_output import private_output
from mnemion.service.api import create_app
from mnemion.service.capture_models import CaptureGrantInput
from mnemion.service.models import KeyInput
from service_tests.test_clients import running
from service_tests.test_capture_custody import custody as custody
from service_tests.test_live_conversations import (
    conversation_source as conversation_source,
    encoded,
)
from service_tests.test_managed_connectors import setup as setup


@pytest.fixture
def headless(env, custody, conversation_source, tmp_path):
    _, connector, operator, reader, secret, original = conversation_source
    _, source_id, grant_id, _, _ = custody
    state = local_state.directory(tmp_path / "headless")
    token = state / "application.token"
    with private_output(token) as stream:
        stream.write(secret.encode())
    admin = state / "one-use-administrator.token"
    with private_output(admin) as stream:
        stream.write(env.token.encode())
    offline, hold, release, http_seen = (threading.Event() for _ in range(4))
    expected, observed = [], []
    app = create_app(env.db, env.embedder)
    config = None

    @app.middleware("http")
    async def outage(request, next_call):
        if expected:
            with sqlite3.connect(device.paths(config)[2] / "inbox.sqlite3") as connection:
                observed.append(
                    connection.execute(
                        "SELECT COUNT(*) FROM events WHERE state='pending'"
                    ).fetchone()[0]
                )
            expected.pop()
        if hold.is_set():
            http_seen.set()
            await asyncio.to_thread(release.wait, 8)
        if offline.is_set():
            return JSONResponse(
                {"error": {"code": "fixture_offline", "message": "Synthetic outage"}},
                status_code=503,
            )
        return await next_call(request)

    with running(app) as endpoint:
        data = original.model_dump(mode="json")
        data.update(service_url=endpoint, service_token={"file": str(token)}, remote_sync=True)
        data["provider"]["capture_mode"] = "messages"
        data["capture"] = {
            "id": str(uuid4()),
            "tenant_id": str(env.owner.tenant_id),
            "principal_id": str(operator.principal_id),
            "source_id": str(source_id),
            "grant_id": str(grant_id),
            "keep_accepted": True,
            "state_directory": str(state),
            "inbox_key": {"file": str(state / "inbox.key")},
        }
        config_file = state / "connector.json"
        config_file.write_text(json.dumps(data), encoding="utf-8")
        config_file.chmod(0o600)
        config = read_config(config_file)
        yield {
            "config": config,
            "file": config_file,
            "offline": offline,
            "expected": expected,
            "observed": observed,
            "secret": secret,
            "admin": admin,
            "reader": reader,
            "operator": operator,
            "custody": custody[0],
            "source_id": source_id,
            "hold": hold,
            "release": release,
            "http_seen": http_seen,
        }


def cli(fixture, request=None, *, code=0, arguments=()):
    command = [sys.executable, "-m", "mnemion.connectors.runner", "--config", str(fixture["file"])]
    if request is not None:
        command.append("--capture-control")
    result = subprocess.run(
        command + list(arguments),
        input=json.dumps(request) if request is not None else None,
        capture_output=True,
        text=True,
        timeout=45,
        cwd=Path(__file__).parents[1],
    )
    assert fixture["secret"] not in result.stdout + result.stderr
    assert result.returncode == code, result.stderr
    payload = json.loads(result.stdout if result.stdout else result.stderr)
    return payload["result"] if request is not None and code == 0 else payload


def prepared(fixture, *, child=False):
    config = fixture["config"]
    control = (
        (lambda value: cli(fixture, value)) if child else (lambda value: perform(config, value))
    )
    control({"action": "key", "confirm": True})
    preview = control({"action": "preview"})
    enrolled = control(
        {
            "action": "enroll",
            "expected_revision": "not-enrolled",
            "preview_hash": preview["configuration_hash"],
            "confirm": True,
        }
    )
    assert not enrolled["enabled"] and enrolled["state"] == "ready"
    return control({"action": "resume", "expected_revision": enrolled["revision"], "confirm": True})


def pause(config):
    return perform(
        config, {"action": "pause", "expected_revision": device.status(config)["revision"]}
    )


def archive(fixture):
    config = fixture["config"]
    paused = pause(config)
    key = {"file": str(device.root(config) / "recovery.key")}
    perform(
        config, {"action": "key", "key_purpose": "recovery", "recovery_key": key, "confirm": True}
    )
    path = str(device.root(config) / "portable.capture")
    result = perform(
        config,
        {
            "action": "backup",
            "expected_revision": paused["revision"],
            "archive": path,
            "recovery_key": key,
            "confirm": True,
        },
    )
    return path, key, result


def replacement(env, fixture):
    original = fixture["config"]
    issued = env.identities.create_key(
        env.owner, original.capture.principal_id, KeyInput(name="Replacement device")
    )
    operator = env.db.authenticate(issued["api_key"])
    grant_id = uuid4()
    fixture["custody"].grant(
        env.owner,
        original.capture.source_id,
        grant_id,
        CaptureGrantInput(device_key_id=operator.key_id),
    )
    root = local_state.directory(device.root(original).parent / ("replacement-" + uuid4().hex))
    logs = root.parent / ("replacement-logs-" + uuid4().hex)
    logs.mkdir()
    data = original.model_dump(mode="json")
    data["capture"].update(
        id=str(uuid4()),
        grant_id=str(grant_id),
        state_directory=str(root),
        inbox_key={"file": str(root / "inbox.key")},
    )
    data["provider"]["path"] = str(logs)
    data["provider"]["state_directory"] = str(root / "unused-provider-state")
    data["service_token"] = {"file": str(root / "application.token")}
    with private_output(Path(data["service_token"]["file"])) as stream:
        stream.write(issued["api_key"].encode())
    config = ConnectorConfig.model_validate(data)
    perform(config, {"action": "key", "confirm": True})
    return config


def recovery_request(fixture, config, bundle):
    path, key, inspected = bundle
    return {
        "action": "restore",
        "confirm": True,
        "expected_revision": "not-enrolled",
        "preview_hash": device.preview(config)["configuration_hash"],
        "archive": path,
        "archive_sha256": inspected["archive_sha256"],
        "recovery_key": key,
        "retirement_token": {"file": str(fixture["admin"])},
    }


def test_real_cli_offline_intake_restart_and_deleted_producer_delivery(env, headless):
    config = headless["config"]
    prepared(headless, child=True)
    text = "Headless selected conversation survives an offline restart"
    path = config.provider.path / "conversation.jsonl"
    path.write_bytes(encoded(text) + encoded("Excluded tool-only trace", "tool"))
    headless["offline"].set()
    headless["expected"].append(True)
    first = cli(headless, code=2)
    assert headless["observed"] == [1]
    assert first["capture"]["locally_accepted"] == first["capture"]["pending_events"] == 1
    assert first["capture"]["capture_complete"] and not first["capture"]["delivery_complete"]
    assert text.encode() not in (device.paths(config)[2] / "inbox.sqlite3").read_bytes()
    assert "Excluded tool-only trace" not in json.dumps(first)
    saved = cli(headless, {"action": "status"})
    assert saved["activity"]["report"]["capture"]["pending_events"] == 1
    path.unlink()
    config.provider.path.rmdir()
    headless["offline"].clear()
    second = cli(headless, code=2)
    assert second["capture"]["pending_events"] == 0 and second["capture"]["stored_events"] == 1
    assert second["capture"]["delivery_complete"] and second["changed"] == 1
    assert second["capture"]["reason_code"] == "capture_source_unavailable"
    with env.db.transaction(headless["reader"]) as connection:
        ids = [
            row["id"]
            for row in connection.execute(
                "SELECT id FROM mnemion.memories WHERE deleted_at IS NULL"
            )
        ]
    assert (
        sum(
            text in env.memory.fetch(headless["reader"], identifier)["content"]
            for identifier in ids
        )
        == 1
    )
    paused = cli(headless, {"action": "pause", "expected_revision": saved["revision"]})
    assert not paused["enabled"]
    assert cli(headless, code=2)["paused"]


def test_enrollment_requires_current_identity_preview_and_explicit_pause_controls(headless):
    config = headless["config"]
    perform(config, {"action": "key", "confirm": True})
    reviewed = device.preview(config)
    request = {
        "action": "enroll",
        "expected_revision": "not-enrolled",
        "preview_hash": "0" * 64,
        "confirm": True,
    }
    with pytest.raises(InboxError, match="capture_settings_changed"):
        perform(config, request)
    assert device.read_record(config, required=False) is None
    request["preview_hash"] = reviewed["configuration_hash"]
    wrong = config.model_copy(deep=True)
    wrong.capture.principal_id = uuid4()
    with pytest.raises(InboxError, match="capture_binding_mismatch"):
        perform(wrong, request)
    enrolled = perform(config, request)
    assert sync(config)["paused"]
    with pytest.raises(InboxError, match="capture_settings_changed"):
        perform(config, {"action": "resume", "expected_revision": "not-enrolled", "confirm": True})
    before = device.paths(config)[2].joinpath("inbox.sqlite3").read_bytes()
    original_key = config.capture.inbox_key.file.read_bytes()
    config.capture.inbox_key.file.write_bytes(base64.b64encode(os.urandom(32)))
    with pytest.raises(InboxError, match="capture_key_unavailable"):
        perform(
            config, {"action": "resume", "expected_revision": enrolled["revision"], "confirm": True}
        )
    assert device.paths(config)[2].joinpath("inbox.sqlite3").read_bytes() == before
    config.capture.inbox_key.file.write_bytes(original_key)
    resumed = perform(
        config, {"action": "resume", "expected_revision": enrolled["revision"], "confirm": True}
    )
    database = device.paths(config)[2] / "inbox.sqlite3"
    database.unlink()
    with pytest.raises(InboxError, match="capture_inbox_missing"):
        sync(config)
    assert not database.exists() and device.status(config)["revision"] == resumed["revision"]


def test_private_references_and_selection_change_never_reenroll_silently(headless):
    config = headless["config"]
    prepared(headless)
    config.capture.inbox_key.file.chmod(0o644)
    with pytest.raises(InboxError, match="capture_key_unavailable"):
        sync(config)
    config.capture.inbox_key.file.chmod(0o600)
    moved = config.model_copy(deep=True)
    moved.provider.members = ["another:audience"]
    with pytest.raises(InboxError, match="capture_settings_changed"):
        sync(moved)
    assert not device.status(moved)["configuration_matches"]
    budget = config.model_copy(deep=True)
    budget.capture.memory_limit_mib = 512
    budget.capture.pending_limit_mib = 32
    budget.provider.max_files = 100
    assert device.status(budget)["configuration_matches"]
    missing = config.service_token.file.with_suffix(".missing")
    config.service_token.file.rename(missing)
    assert device.status(config)["state"] == "ready"
    (config.provider.path / "first.jsonl").write_bytes(
        encoded("Capture does not require reading its API key")
    )
    report = sync(config)
    assert (
        report["capture"]["pending_events"] == 1
        and report["capture"]["reason_code"] == "capture_key_unavailable"
    )


def test_process_lock_prevents_duplicate_local_writers_and_status_survives(headless):
    config = headless["config"]
    prepared(headless)
    with device.locked(config):
        assert cli(headless, {"action": "status"})["state"] == "ready"
        assert cli(headless, code=2)["error"] == "workspace_busy"
    activity = {
        "format": device.FORMAT,
        "id": str(config.capture.id),
        "state": "scanning",
        "pid": 2147483646,
        "process": {},
        "started_at": "2026-10-21T00:00:00Z",
    }
    local_state.write(device.paths(config)[1], activity)
    assert cli(headless, {"action": "status"})["activity"]["state"] == "interrupted"


def test_archived_pending_events_restore_with_new_grant_then_deliver_once(env, headless):
    config = headless["config"]
    prepared(headless)
    (config.provider.path / "before.jsonl").write_bytes(
        encoded("Portable headless pending evidence")
    )
    headless["offline"].set()
    assert sync(config)["capture"]["pending_events"] == 1
    headless["offline"].clear()
    bundle = archive(headless)
    target = replacement(env, headless)
    request = recovery_request(headless, target, bundle)
    restored = perform(target, request)
    assert restored["state"] == "ready" and not restored["enabled"]
    old = headless["custody"].status(env.owner, config.capture.grant_id)
    assert old["revoked_at"] and not old["active"]
    perform(
        target, {"action": "resume", "expected_revision": restored["revision"], "confirm": True}
    )
    delivered = sync(target)
    assert (
        delivered["capture"]["stored_events"] == 1 and delivered["capture"]["pending_events"] == 0
    )
    assert delivered["changed"] == 1 and delivered["capture"]["delivery_complete"]
    assert sync(target)["capture"]["remote_committed_events"] == 0
    fresh = replacement(env, headless)
    with pytest.raises(InboxError, match="capture_policy_change_requires_migration"):
        perform(
            fresh,
            {
                "action": "enroll",
                "confirm": True,
                "expected_revision": "not-enrolled",
                "preview_hash": device.preview(fresh)["configuration_hash"],
            },
        )
    (target.provider.path / "new.jsonl").write_bytes(
        encoded("New evidence after headless device recovery")
    )
    assert sync(target)["capture"]["stored_events"] == 2


@pytest.mark.parametrize("resolution", ["finish", "discard"])
def test_interrupted_restore_finishes_without_recreating_key_or_copy(
    env, headless, monkeypatch, resolution
):
    config = headless["config"]
    prepared(headless)
    (config.provider.path / "before.jsonl").write_bytes(
        encoded("Recover an interrupted local publication")
    )
    headless["offline"].set()
    sync(config)
    headless["offline"].clear()
    bundle, target = archive(headless), replacement(env, headless)
    request = recovery_request(headless, target, bundle)
    write = device.write_record

    def interrupted(config, record, **updates):
        if config.capture.id == target.capture.id and updates.get("state") == "ready":
            raise OSError("Synthetic final record publication interruption")
        return write(config, record, **updates)

    with monkeypatch.context() as patch:
        patch.setattr(device, "write_record", interrupted)
        with pytest.raises(OSError, match="Synthetic final record"):
            perform(target, request)
    pending = device.status(target)
    assert pending["state"] == "recovering" and not pending["enabled"] and pending["inbox_present"]
    key = target.capture.inbox_key.file.read_bytes()
    if resolution == "discard":
        archive_bytes = Path(bundle[0]).read_bytes()
        discarded = perform(
            target, {**request, "action": "discard", "expected_revision": pending["revision"]}
        )
        assert discarded["state"] == "discarded" and not discarded["inbox_present"]
        assert headless["custody"].status(env.owner, target.capture.grant_id)["revoked_at"]
        assert Path(bundle[0]).read_bytes() == archive_bytes
        return
    finished = perform(
        target, {**request, "action": "finish", "expected_revision": pending["revision"]}
    )
    assert finished["state"] == "ready" and not finished["enabled"]
    assert target.capture.inbox_key.file.read_bytes() == key
    perform(
        target, {"action": "resume", "expected_revision": finished["revision"], "confirm": True}
    )
    delivered = sync(target)
    assert (
        delivered["capture"]["pending_events"] == 0 and delivered["capture"]["stored_events"] == 1
    )
    assert sync(target)["capture"]["remote_committed_events"] == 0


@pytest.mark.parametrize("problem", ["changed_prefix", "destination_exists", "capacity", "old_key"])
def test_local_recovery_failures_preserve_the_previous_grant(env, headless, monkeypatch, problem):
    config = headless["config"]
    prepared(headless)
    (config.provider.path / "before.jsonl").write_bytes(
        encoded("Original prefix requiring preservation")
    )
    headless["offline"].set()
    sync(config)
    headless["offline"].clear()
    bundle, target = archive(headless), replacement(env, headless)
    if problem == "changed_prefix":
        (target.provider.path / "before.jsonl").write_bytes(
            encoded("Unrelated replacement must fail prefix validation")
        )
    elif problem == "destination_exists":
        local_state.directory(device.paths(target)[2])
    elif problem == "capacity":
        monkeypatch.setattr(device, "DEVICE_PENDING_BYTES", 1)
    else:
        target.capture.inbox_key.file.write_bytes(config.capture.inbox_key.file.read_bytes())
    with pytest.raises((InboxError, CaptureArchiveError)):
        perform(target, recovery_request(headless, target, bundle))
    assert headless["custody"].status(env.owner, config.capture.grant_id)["active"]
    assert device.read_record(target, required=False) is None


def test_killed_cli_reports_interruption_and_recovers_committed_inbox(headless):
    config = headless["config"]
    prepared(headless)
    (config.provider.path / "chat.jsonl").write_bytes(
        encoded("Committed before a killed network request")
    )
    headless["hold"].set()
    process = subprocess.Popen(
        [sys.executable, "-m", "mnemion.connectors.runner", "--config", str(headless["file"])],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=Path(__file__).parents[1],
    )
    try:
        assert headless["http_seen"].wait(10), "The real child never reached post-commit delivery"
        active = device.status(config)
        assert (
            active["activity"]["state"] == "scanning" and active["activity"]["pid"] == process.pid
        )
        process.terminate()
        process.communicate(timeout=10)
        assert device.status(config)["activity"]["state"] == "interrupted"
    finally:
        headless["hold"].clear()
        headless["release"].set()
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
    resumed = cli(headless)
    assert resumed["capture"]["stored_events"] == 1 and resumed["capture"]["pending_events"] == 0
    assert cli(headless)["capture"]["remote_committed_events"] == 0


@pytest.mark.skipif(os.name != "posix", reason="Managed runtime supervision is Unix-only")
def test_managed_capture_saves_offline_and_still_refuses_unverified_or_old_runtimes(
    headless, setup, monkeypatch
):
    from mnemion.connectors import managed
    from mnemion.service import service_updates, update_state
    from mnemion.service.update_manifest import ManifestError
    from mnemion.version import __version__

    config = headless["config"]
    prepared(headless)
    (config.provider.path / "chat.jsonl").write_bytes(
        encoded("Offline capture through managed runtime")
    )
    headless["offline"].set()
    runtime = {
        "python": sys.executable,
        "directory": str(Path(__file__).parents[1]),
        "version": __version__,
        "isolated": False,
        "capture_protocol": 1,
    }
    monkeypatch.setattr(managed.supervision, "status", lambda _: {"ready": False})
    monkeypatch.setattr(service_updates, "resolved_runtime", lambda _: runtime)
    observation = managed.Observation(setup.entry, str(config.connector_id))
    with update_state.lock(setup.entry) as singleton:

        def scan():
            return managed._scan(
                setup.state,
                setup.root,
                config,
                setup.entry,
                singleton,
                observation,
                managed.Control(),
            )

        assert scan() == 2
        assert device.status(config)["activity"]["report"]["capture"]["pending_events"] == 1
        runtime["capture_protocol"] = 0
        with pytest.raises(ManifestError, match="does not support retained"):
            scan()
        runtime["capture_protocol"] = 1
        update_state.write(setup.root / "journal.json", {"phase": "starting"})
        assert scan() is None


def test_paused_watch_notices_local_resume_without_remote_polling(headless, monkeypatch):
    from mnemion.connectors import runner

    config = headless["config"]
    prepared(headless)
    paused = pause(config)
    elapsed = [0]

    def sleep(seconds):
        elapsed[0] += seconds
        if elapsed[0] >= 10:
            perform(
                config,
                {"action": "resume", "expected_revision": paused["revision"], "confirm": True},
            )

    def forbidden(*args, **kwargs):
        pytest.fail("A paused watcher must not open a remote control client")

    monkeypatch.setattr(runner, "Client", forbidden)
    assert runner.wait_for_sync(config, clock=lambda: elapsed[0], sleep=sleep) == "requested"
    assert elapsed[0] == 10


def test_revoked_grant_stops_future_intake_without_discarding_selected_queue(env, headless):
    config = headless["config"]
    prepared(headless)
    path = config.provider.path / "chat.jsonl"
    path.write_bytes(encoded("Already selected before the retirement observation"))
    headless["custody"].status(env.owner, config.capture.grant_id, revoke=True)
    report = sync(config)
    assert report["capture"]["pending_events"] == 1
    assert report["capture"]["reason_code"] == "capture_authorization_revoked"
    assert device.status(config)["state"] == "revoked" and not device.status(config)["enabled"]
    path.write_bytes(path.read_bytes() + encoded("Must not be accepted after observed revocation"))
    assert sync(config)["paused"]
    with device.opened(config, device.read_record(config)) as (inbox, _, _):
        assert inbox.status()["pending_events"] == 1
