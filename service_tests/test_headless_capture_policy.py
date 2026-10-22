"""Independent agent policy migration preserves delivery and deletion history."""

import hashlib
from uuid import uuid4

import pytest

from mnemion.capture_policy import CapturePolicy
from mnemion.connectors import headless_capture as device, headless_capture_control as control
from mnemion.connectors.capture_archive import CaptureArchiveError
from mnemion.connectors.conversation_inbox import InboxError
from mnemion.connectors.runner import sync
from mnemion.service.capture_models import CapturePolicyChange
from service_tests.test_headless_durable_capture import (
    archive,
    cli,
    conversation_source as conversation_source,
    custody as custody,
    encoded,
    headless as headless,
    pause,
    prepared,
    recovery_request,
    replacement,
)


def drain(config):
    return control.perform(
        config,
        {
            "action": "drain",
            "expected_revision": device.status(config)["revision"],
            "confirm": True,
        },
    )


def change_policy(env, fixture, policy):
    config, service = fixture["config"], fixture["custody"]
    review = service.policy_review(env.owner, config.connector_id, config.capture.source_id)
    service.change_policy(
        env.owner,
        config.connector_id,
        config.capture.source_id,
        uuid4(),
        CapturePolicyChange(
            expected_version=review["source"]["version"],
            review_token=review["review_token"],
            capture_policy=policy,
            previous_grants="retain",
            confirm=True,
        ),
    )


def new_policy_device(env, fixture, policy):
    target = replacement(env, fixture)
    target.provider.capture_mode = policy.capture_mode
    target.provider.capture_policy = policy
    for path in fixture["config"].provider.path.glob("*.jsonl"):
        (target.provider.path / path.name).write_bytes(path.read_bytes())
    return target


def test_real_agent_paused_delivery_does_not_collect_new_records(headless):
    config = headless["config"]
    prepared(headless)
    path = config.provider.path / "chat.jsonl"
    path.write_bytes(encoded("Queued under the approved policy"))
    headless["offline"].set()
    assert sync(config)["capture"]["pending_events"] == 1
    pause(config)
    path.write_bytes(path.read_bytes() + encoded("Wait until explicitly resumed"))
    headless["offline"].clear()
    result = cli(
        headless,
        {
            "action": "drain",
            "expected_revision": device.status(config)["revision"],
            "confirm": True,
        },
    )
    assert result["delivery_complete"] and result["remote_committed_events"] == 1
    assert result["status"]["stored_events"] == 1 and not result["source_enabled"]
    assert not device.status(config)["enabled"]
    assert drain(config)["remote_committed_events"] == 0


def test_drain_requires_a_paused_source(headless):
    config = headless["config"]
    prepared(headless)
    with pytest.raises(InboxError, match="capture_pause_required"):
        drain(config)


@pytest.fixture
def policy_recovery(env, headless):
    config = headless["config"]
    prepared(headless)
    (config.provider.path / "kept.jsonl").write_bytes(encoded("Kept independent policy evidence"))
    (config.provider.path / "forgotten.jsonl").write_bytes(
        encoded("Forgotten independent policy evidence")
    )
    assert sync(config)["capture"]["pending_events"] == 0
    with env.db.transaction(headless["reader"]) as connection:
        rows = connection.execute(
            "SELECT id FROM mnemion.memories WHERE deleted_at IS NULL"
        ).fetchall()
    memory = next(
        row["id"]
        for row in rows
        if "Forgotten independent policy evidence"
        in env.memory.fetch(headless["reader"], row["id"])["content"]
    )
    env.memory.forget(
        headless["reader"], memory, expected_version=1, key="independent-policy-forget"
    )
    pause(config)
    assert drain(config)["status"]["forgotten_events"] == 1
    bundle = archive(headless)
    policy = CapturePolicy(preset="detailed", capture_mode="complete", retention="until_deleted")
    change_policy(env, headless, policy)
    target = new_policy_device(env, headless, policy)
    request = {**recovery_request(headless, target, bundle), "policy_change": True}
    return headless, target, request


def test_reviewed_headless_policy_recovery_preserves_forgotten_evidence(env, policy_recovery):
    fixture, target, request = policy_recovery
    original = fixture["config"]
    database = device.paths(original)[2] / "inbox.sqlite3"
    digest = hashlib.sha256(database.read_bytes()).hexdigest()
    receipt = control.perform(target, request)
    assert receipt["state"] == "ready" and not receipt["enabled"]
    assert device.read_record(target)["recovery"]["policy_change"]
    assert drain(target)["status"]["coverage"]["catalog"] == "unobserved"
    assert fixture["custody"].status(env.owner, original.capture.grant_id)["revoked_at"]
    assert hashlib.sha256(database.read_bytes()).hexdigest() == digest
    control.perform(
        target, {"action": "resume", "expected_revision": receipt["revision"], "confirm": True}
    )
    result = sync(target)["capture"]
    assert result["delivery_complete"] and result["forgotten_events"] >= 1
    with env.db.transaction(fixture["reader"]) as connection:
        rows = connection.execute(
            "SELECT id FROM mnemion.memories WHERE deleted_at IS NULL"
        ).fetchall()
    assert rows and not any(
        "Forgotten independent policy evidence"
        in env.memory.fetch(fixture["reader"], row["id"])["content"]
        for row in rows
    )


def test_policy_recovery_is_never_an_implicit_restore(env, policy_recovery):
    fixture, target, request = policy_recovery
    request.pop("policy_change")
    with pytest.raises(CaptureArchiveError):
        control.perform(target, request)
    assert not fixture["custody"].status(env.owner, fixture["config"].capture.grant_id)[
        "revoked_at"
    ]
    assert device.status(target)["state"] == "not-enrolled"


def test_pending_archive_cannot_be_relabelled_to_a_new_headless_policy(env, policy_recovery):
    fixture, target, request = policy_recovery
    original = fixture["config"]
    current = device.status(original)
    control.perform(
        original, {"action": "resume", "expected_revision": current["revision"], "confirm": True}
    )
    (original.provider.path / "pending.jsonl").write_bytes(encoded("Old-policy pending evidence"))
    fixture["offline"].set()
    assert sync(original)["capture"]["pending_events"] == 1
    paused = pause(original)
    fixture["offline"].clear()
    archive_path = str(device.root(original) / "pending.capture")
    inspection = control.perform(
        original,
        {
            "action": "backup",
            "expected_revision": paused["revision"],
            "archive": archive_path,
            "recovery_key": request["recovery_key"],
            "confirm": True,
        },
    )
    request.update(archive=archive_path, archive_sha256=inspection["archive_sha256"])
    with pytest.raises(CaptureArchiveError, match="Deliver and confirm"):
        control.perform(target, request)
    assert not fixture["custody"].status(env.owner, original.capture.grant_id)["revoked_at"]
    assert device.status(target)["state"] == "not-enrolled"


def test_changed_current_policy_stops_before_old_grant_retirement(env, policy_recovery):
    fixture, target, request = policy_recovery
    change_policy(
        env,
        fixture,
        target.provider.capture_policy.model_copy(update={"exclude": ["private/*.jsonl"]}),
    )
    with pytest.raises(InboxError, match="capture_settings_changed"):
        control.perform(target, request)
    assert not fixture["custody"].status(env.owner, fixture["config"].capture.grant_id)[
        "revoked_at"
    ]
    assert device.status(target)["state"] == "not-enrolled"


@pytest.mark.parametrize("point", ["before_copy", "after_copy"])
def test_interrupted_policy_copy_finishes_with_its_reviewed_policy(
    policy_recovery, monkeypatch, point
):
    _, target, request = policy_recovery
    with monkeypatch.context() as patch:
        if point == "before_copy":

            def stop(*args):
                raise OSError("Interrupted policy copy publication")

            patch.setattr(control, "_rename_exclusive", stop)
        else:
            write = device.write_record

            def stop(config, record, **updates):
                if updates.get("state") == "ready":
                    raise OSError("Interrupted policy device completion")
                return write(config, record, **updates)

            patch.setattr(device, "write_record", stop)
        with pytest.raises(OSError, match="Interrupted policy"):
            control.perform(target, request)
    current = device.status(target)
    assert current["state"] == "recovering" and not current["enabled"]
    assert device.read_record(target)["recovery"]["policy_change"]
    finished = control.perform(
        target,
        {
            "action": "finish",
            "expected_revision": current["revision"],
            "archive": request["archive"],
            "archive_sha256": request["archive_sha256"],
            "recovery_key": request["recovery_key"],
            "confirm": True,
        },
    )
    assert finished["state"] == "ready" and not finished["enabled"]
    assert drain(target)["status"]["forgotten_events"] == 1


def test_discarded_policy_copy_preserves_original_and_allows_fresh_retry(
    env, policy_recovery, monkeypatch
):
    fixture, target, request = policy_recovery
    with monkeypatch.context() as patch:

        def stop(*args):
            raise OSError("Interrupted policy publication")

        patch.setattr(control, "_rename_exclusive", stop)
        with pytest.raises(OSError):
            control.perform(target, request)
    discarded = control.perform(
        target,
        {
            "action": "discard",
            "expected_revision": device.status(target)["revision"],
            "retirement_token": request["retirement_token"],
            "confirm": True,
        },
    )
    assert discarded["state"] == "discarded" and not discarded["enabled"]
    assert fixture["custody"].status(env.owner, target.capture.grant_id)["revoked_at"]
    assert not device.status(fixture["config"])["enabled"]
    with device.opened(fixture["config"], device.read_record(fixture["config"])) as (inbox, _, _):
        assert inbox.status()["forgotten_events"] == 1
    fresh = new_policy_device(env, fixture, target.provider.capture_policy)
    request["preview_hash"] = device.preview(fresh)["configuration_hash"]
    retried = control.perform(fresh, request)
    assert retried["state"] == "ready" and not retried["enabled"]
