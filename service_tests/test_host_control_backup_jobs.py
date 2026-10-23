"""Standalone backup authority, state and recovery; capture is a bounded fixture.

Real encrypted Git/SSH transport is covered separately. These tests do not claim
production backup delivery or a restored independent host.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

from mnemion.host_control import HostControlError, adapter, backup, installation
from mnemion.host_control.receiver import dispatch
from mnemion.host_control.store import Store
from mnemion.service import service_updates, supervision, update_state
from service_tests.test_host_control_installation import prepared_host as prepared_host
from service_tests.test_host_control_store import grant, operator, request

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Unix adopted host backups")


@pytest.fixture
def backup_host(prepared_host, monkeypatch):
    service, root, owner, _, port = prepared_host
    identity = installation.adopt(root, service, owner, port=port)["connection"]
    store = Store(root / "authority")
    value = {"service_state": str(service)}
    captures = []
    monkeypatch.setattr(backup, "fingerprint", lambda _root, **_: "a" * 64)
    monkeypatch.setattr(
        backup, "configuration", lambda _: SimpleNamespace(key_id="b" * 24, maximum_bytes=1024**2)
    )

    def forbidden(*_, **__):
        raise AssertionError("A standalone backup must not start, stop or upgrade memory")

    monkeypatch.setattr(supervision, "start", forbidden)
    monkeypatch.setattr(supervision, "stop", forbidden)
    monkeypatch.setattr(service_updates, "_processes", forbidden)

    def capture(_root, _value, operation_id):
        captures.append(operation_id)
        now = datetime.now(timezone.utc).isoformat()
        receipt = {
            "operation_id": operation_id,
            "host_id": identity["host_id"],
            "key_id": "b" * 24,
            "verified_at": now,
            "snapshot_at": now,
            "ledger_at": now,
            "service_version": "4.46.3",
            "remote_storage": True,
            "remote_readback_verified": True,
            "independent_storage_confirmed": True,
            "independent_key_custody_confirmed": True,
            "destination_identity": "private-destination-canary",
            "private_path": "/private/credential-canary",
            "files": {
                kind: {"bytes": 16, "sha256": hashlib.sha256(kind.encode()).hexdigest()}
                for kind in ("bundle", "ledger")
            },
        }
        target = update_state.directory(root / "backups" / operation_id)
        update_state.write(target / "receipt.json", receipt)
        update_state.write(root / "backup-index.json", {"backups": [receipt]})
        return receipt

    monkeypatch.setattr(backup, "fresh", capture)
    return SimpleNamespace(
        root=root, service=service, store=store, value=value, identity=identity, captures=captures
    )


def queued(host, action="backup.create", *, actor=None, **fields):
    spec = request(
        host.identity, action, configuration_sha256="a" * 64, approve_backup_transfer=True, **fields
    )
    actor = actor or host.identity["operator_id"]
    host.store.enqueue(actor, spec)
    job = host.store.claim()
    assert job["operation_id"] == str(spec.request_id)
    return spec, job


def execute(host, spec, job):
    result, context = adapter.execute(
        host.root,
        host.value,
        host.store,
        job,
        spec,
        before_effect=lambda: host.store.guard(job["operation_id"], record_effect=True),
    )
    host.store.finish(job["operation_id"], result=result, context=context)
    return result


@pytest.mark.parametrize("approval", [False, 1, "true", None])
def test_backup_transfer_requires_an_explicit_boolean_approval(backup_host, approval):
    with pytest.raises(HostControlError, match="schema"):
        request(
            backup_host.identity,
            "backup.create",
            configuration_sha256="a" * 64,
            approve_backup_transfer=approval,
        )
    assert not backup_host.captures


def test_read_only_host_grant_cannot_queue_an_encrypted_transfer(backup_host):
    host = backup_host
    observer = grant((host.store, host.identity), operator("Observer", "observer"))
    spec = request(
        host.identity, "backup.create", configuration_sha256="a" * 64, approve_backup_transfer=True
    )
    reply = json.loads(dispatch(host.store, observer, spec.model_dump_json().encode()))
    assert not reply["ok"] and reply["error"]["code"] == "host_access_denied"
    assert host.store.claim() is None and not host.captures


def test_created_backup_retains_service_intent_and_lost_reply_does_not_repeat_capture(backup_host):
    host = backup_host
    before = host.store.service_policy()
    spec, job = queued(host)
    result = execute(host, spec, job)
    assert result["status"] == "created" and result["backup_id"] == job["operation_id"]
    after = host.store.service_policy()
    for name in ("desired", "operation_id"):
        assert after[name] == before[name]
    assert after["pending_work"] is False
    reopened = Store(host.store.root)
    assert reopened.enqueue(host.identity["operator_id"], spec)["phase"] == "succeeded"
    assert reopened.claim() is None and host.captures == [job["operation_id"]]
    inventory = backup.status(host.root)
    assert inventory["items"] == [{key: val for key, val in result.items() if key != "status"}]
    encoded = json.dumps({"result": result, "status": inventory})
    assert "private-destination-canary" not in encoded and "credential-canary" not in encoded
    assert result["controller_authority_included"] is False


def test_changed_backup_settings_refuse_before_capture_or_effect(backup_host, monkeypatch):
    host = backup_host
    spec, job = queued(host)
    monkeypatch.setattr(backup, "fingerprint", lambda _: "c" * 64)
    with pytest.raises(HostControlError) as error:
        execute(host, spec, job)
    assert error.value.code == "backup_configuration_changed" and not host.captures
    assert (
        host.store.operation(
            host.identity["operator_id"], host.identity["host_id"], job["operation_id"]
        )["effect_started_at"]
        is None
    )


def test_retirement_after_claim_refuses_before_any_backup(backup_host):
    host = backup_host
    actor = grant((host.store, host.identity), operator("Backup operator", "operator"))
    spec, job = queued(host, actor=actor)
    host.store.revoke(
        host.identity["operator_id"],
        request(host.identity, "operators.revoke", expected_revision=2, operator_id=actor),
    )
    with pytest.raises(HostControlError, match="authority changed"):
        execute(host, spec, job)
    assert not host.captures


def test_new_backup_refuses_an_interrupted_migration(backup_host):
    host = backup_host
    spec, job = queued(host)
    update_state.write(host.service / "updates/upgrade-journal.json", {"preserve": True})
    with pytest.raises(HostControlError) as error:
        execute(host, spec, job)
    assert error.value.code == "recovery_required" and not host.captures


def test_readback_during_recovery_preserves_original_receipt_and_unresolved_work(
    backup_host, monkeypatch
):
    host = backup_host
    created, job = queued(host)
    execute(host, created, job)
    original = (host.root / "backups" / job["operation_id"] / "receipt.json").read_bytes()
    unresolved = request(host.identity, "service.stop", approve_service_interruption=True)
    host.store.enqueue(host.identity["operator_id"], unresolved)
    old_job = host.store.claim()
    host.store.inspection(old_job["operation_id"])
    update_state.write(host.service / "updates/upgrade-journal.json", {"preserve": True})
    seen = []

    def readback(_root, _value, receipt):
        seen.append(receipt["operation_id"])
        return {"original_backup": receipt, "reverified_at": datetime.now(timezone.utc).isoformat()}

    monkeypatch.setattr(backup, "verify_existing", readback)
    spec, verifying = queued(host, "backup.verify", backup_id=job["operation_id"])
    result = execute(host, spec, verifying)
    assert result["status"] == "verified" and seen == [job["operation_id"]]
    assert (host.root / "backups" / job["operation_id"] / "receipt.json").read_bytes() == original
    assert (
        host.store.operation(
            host.identity["operator_id"], host.identity["host_id"], old_job["operation_id"]
        )["phase"]
        == "inspection_required"
    )
    assert host.captures == [job["operation_id"]]
    assert backup.status(host.root)["items"][0]["last_verified_at"] == result["last_verified_at"]


def test_retired_backup_id_cannot_create_a_readback_observation(backup_host):
    host = backup_host
    spec, job = queued(host, "backup.verify", backup_id=str(uuid4()))
    with pytest.raises(HostControlError) as error:
        execute(host, spec, job)
    assert error.value.code == "backup_not_found" and not host.captures


def test_corrupt_inventory_is_not_reported_as_no_backups(backup_host):
    update_state.write(backup_host.root / "backup-index.json", {"backups": [{}]})
    value = backup.status(backup_host.root)
    assert value["inspection_required"] is True and "items" not in value


def test_missing_target_of_a_linked_inventory_is_not_reported_as_no_backups(backup_host):
    (backup_host.root / "backup-index.json").symlink_to(backup_host.root / "missing.json")
    value = backup.status(backup_host.root)
    assert value["inspection_required"] is True and "items" not in value


def test_worker_persists_bounded_backup_failure_without_repeating_work(backup_host, monkeypatch):
    from mnemion.host_control import worker
    from mnemion.host_control.backup_git import BackupTransferError

    host = backup_host
    spec = request(
        host.identity, "backup.create", configuration_sha256="a" * 64, approve_backup_transfer=True
    )
    host.store.enqueue(host.identity["operator_id"], spec)
    calls = []

    def fail(_root, _value, _store, job, _request, *, before_effect):
        calls.append(job["operation_id"])
        before_effect()
        raise BackupTransferError("push", "deadline") from RuntimeError("private-token-path-canary")

    monkeypatch.setattr(adapter, "execute", fail)
    with update_state.lock(host.root / "worker") as descriptor:
        assert worker.work(host.root, os.dup(descriptor)) == 0
    reopened = Store(host.store.root)
    value = reopened.operation(
        host.identity["operator_id"], host.identity["host_id"], spec.request_id
    )
    assert value["phase"] == "inspection_required" and value["error"] == "operation_uncertain"
    assert value["result"] == {
        "backup_transfer": {"stage": "push", "reason": "deadline", "exit_code": None}
    }
    assert value["effect_started_at"] and "private-token-path-canary" not in json.dumps(value)
    assert calls == [str(spec.request_id)] and reopened.claim() is None
